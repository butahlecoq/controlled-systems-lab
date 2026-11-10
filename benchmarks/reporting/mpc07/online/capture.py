"""Bounded source-frozen online policy evaluation; every action drives the plant."""
import argparse
import cProfile
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import sysconfig
import time
from benchmarks.reporting.mpc07.online.controller import prepare,CausalController
from benchmarks.reporting.mpc07.online.inputs import encoded,digest

ROOT=Path(__file__).resolve().parents[4]
INPUT=Path(__file__).with_name('profiles.json')


def plant(state,control,delta,w):
    p,q=state
    return [p+q+control/2,(1+delta)*q+control+w]


def execute(profile,family,repetition):
    start=time.perf_counter_ns();steps=[];prep_ns=None;state=[0.,0.]
    result=dict(status='failed',profile=profile['id'],family=family,repetition=repetition,warmup=repetition==-1,steps=steps)
    try:
        prep_start=time.perf_counter_ns();controller=CausalController(prepare(profile));prep_ns=time.perf_counter_ns()-prep_start
        for t in range(profile['horizon']):
            observed=list(state);row=dict(stage=t,observation=observed);steps.append(row)
            begin=time.perf_counter_ns();residual,innovation=controller.observe(observed);row['residual_update_ns']=time.perf_counter_ns()-begin
            row.update(past_residual=residual,past_innovation=innovation)
            begin=time.perf_counter_ns();action=controller.action();row['query_ns']=time.perf_counter_ns()-begin;row['control']=action
            # Plant uncertainty is selected/applied only AFTER the controller action.
            sign=1 if family=='positive' or t%2==0 else -1
            delta=float(Fraction(profile['epsilon']));w=float(sign);row.update(delta=delta,w=w)
            state=plant(observed,action,delta,w);row['next_state']=list(state)
        result.update(status='completed',terminal_cost=state[1]**2)
    except Exception as error:result.update(error=repr(error),terminal_cost=None)
    result.update(preparation_ns=prep_ns,episode_ns=time.perf_counter_ns()-start)
    return result


def worker(inputs):
    for rep in range(-1,inputs['measured_repetitions']):
        order=[(p,f) for p in inputs['profiles'] for f in inputs['trace_families']]
        if rep%2:order.reverse()
        for profile,family in order:
            try:result=execute(profile,family,rep)
            except Exception as error:result=dict(status='failed',profile=profile['id'],family=family,repetition=rep,warmup=rep==-1,error=repr(error))
            print(json.dumps(result,allow_nan=False),flush=True)


def source_files():
    files=[*Path(__file__).parent.glob('*.py'),INPUT,*Path(__file__).parents[1].glob('*.py'),ROOT/'scripts/reports/stage_mpc07_comparison.py']
    return {p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted(files)}


def admission():
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))


def supervised(command,folder):
    folder.mkdir();begin=time.perf_counter_ns()
    with (folder/'stdout.jsonl').open('wb') as out,(folder/'stderr.txt').open('wb') as err:
        process=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,preexec_fn=admission,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        expired=False
        while True:
            pid,status,usage=os.wait4(process.pid,os.WNOHANG)
            if pid:break
            if time.perf_counter_ns()-begin>60*10**9:
                expired=True;os.killpg(process.pid,signal.SIGKILL);_,status,usage=os.wait4(process.pid,0);break
            time.sleep(.005)
        code=os.waitstatus_to_exitcode(status);process.returncode=code
    return dict(command=command,status='timed-out' if expired else 'completed' if code==0 else 'failed',return_code=code,whole_process_ns=time.perf_counter_ns()-begin,user_cpu_seconds=usage.ru_utime,system_cpu_seconds=usage.ru_stime,peak_rss_kib=usage.ru_maxrss,
        stdout_sha256=digest((folder/'stdout.jsonl').read_bytes()),stderr_sha256=digest((folder/'stderr.txt').read_bytes()),limits=dict(cpu_seconds=30,wall_seconds=60,address_space_bytes=2*1024**3),scope='direct worker wait4 CPU/RSS; supervised wall includes startup, serialization and polling')


def capture(output):
    if output.exists():raise ValueError('new capture directory required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise ValueError('clean committed capture source required')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();sources=source_files()
    for name,data in sources.items():
        if subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT)!=data:raise ValueError('uncommitted source')
    output.mkdir();(output/'source').mkdir()
    for name,data in sources.items():
        p=output/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (output/'inputs.json').write_bytes(INPUT.read_bytes());clock=time.get_clock_info('perf_counter')
    pairs=[]
    for _ in range(1000):
        a=time.perf_counter_ns();pairs.append(time.perf_counter_ns()-a)
    environment=dict(schema='csl.mpc07.online-capture/1',source_revision=revision,source_sha256={n:digest(v) for n,v in sources.items()},input_sha256=digest(INPUT.read_bytes()),python=sys.version,executable=sys.executable,executable_sha256=digest(Path(sys.executable).read_bytes()),python_build_flags=sysconfig.get_config_var('CONFIG_ARGS'),platform=platform.platform(),cpu_count=os.cpu_count(),load_average=os.getloadavg(),clock=dict(implementation=clock.implementation,resolution_seconds=clock.resolution,monotonic=clock.monotonic,adjustable=clock.adjustable,empty_pair_ns=dict(minimum=min(pairs),maximum=max(pairs),median=sorted(pairs)[len(pairs)//2]),subtraction_applied=False),claim='initial configured Python causal policy evaluation costs only; no ranking, hard-real-time or MPC-replan latency')
    (output/'environment.json').write_bytes(encoded(environment))
    command=[sys.executable,'-B','-m','benchmarks.reporting.mpc07.online.capture','--worker','--inputs',str(output/'inputs.json')]
    process=supervised(command,output/'measured');(output/'measured/process.json').write_bytes(encoded(process))
    # Profile work is separately retained and excluded from all latency summaries.
    profile_command=command+['--profile',str(output/'profile.pstats')]
    profiled=supervised(profile_command,output/'profiled');(output/'profiled/process.json').write_bytes(encoded(profiled))
    import pstats
    if (output/'profile.pstats').exists():
        with (output/'profile.txt').open('w') as stream:pstats.Stats(str(output/'profile.pstats'),stream=stream).strip_dirs().sort_stats('cumulative').print_stats(30)
    hashes={p.relative_to(output).as_posix():digest(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()))
    return dict(status=process['status'],capture_source=revision,profile_status=profiled['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--worker',action='store_true');p.add_argument('--inputs',type=Path,default=INPUT);p.add_argument('--profile',type=Path);a=p.parse_args()
    if a.worker:
        values=json.loads(a.inputs.read_bytes())
        if a.profile:cProfile.runctx('worker(values)',globals(),locals(),str(a.profile))
        else:worker(values)
    elif a.output:print(json.dumps(capture(a.output.resolve())))
    else:p.error('--output or --worker required')

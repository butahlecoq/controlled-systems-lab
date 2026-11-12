"""Source-frozen offline tube construction/check/serialization observations."""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
try:import resource
except ImportError:resource=None
import signal
import subprocess
import sys
import time
from scripts.reports.mpc06_offline import builder

ROOT=Path(__file__).resolve().parents[3]
FILES=('scripts/reports/mpc06_offline/builder.py','scripts/reports/mpc06_offline/study.py','scripts/reports/mpc06_offline/check.py','scripts/reports/mpc06_offline/inputs.json','scripts/reports/mpc06_online/model.py','reports/algorithm-results/mpc06-online-anchor-v1/result.json')
HISTORICAL_FILES=tuple(sorted((*FILES,'scripts/reports/mpc06_offline/README.md')))
LIMITS=dict(cpu_seconds=15,wall_seconds=30,address_space_bytes=512*1024**2)
def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def episode(data,repetition):
    start=time.perf_counter_ns();result=dict(kind='episode',repetition=repetition,warmup=repetition==-1,status='failed',construction_ns=None,certificate_and_consumer_check_ns=None,artifact_serialization_ns=None)
    phase='construction'
    try:
        begin=time.perf_counter_ns();artifact=builder.construct(data);result['construction_ns']=time.perf_counter_ns()-begin
        # The same artifact is consumed by the existing nominal-QP constructor.
        phase='certificate-and-consumer-check';begin=time.perf_counter_ns();checked=builder.verify(data,artifact);result['certificate_and_consumer_check_ns']=time.perf_counter_ns()-begin
        phase='artifact-serialization';begin=time.perf_counter_ns();serialized=builder.encoded(artifact);result['artifact_serialization_ns']=time.perf_counter_ns()-begin
        result.update(status='completed',artifact_json=serialized.decode(),artifact_sha256=sha(serialized),verification=checked)
    except Exception as error:result.update(failed_phase=phase,error=repr(error))
    result['episode_ns']=time.perf_counter_ns()-start;return result

def worker(data):
    samples=[]
    for _ in range(1000):
        start=time.perf_counter_ns();samples.append(time.perf_counter_ns()-start)
    print(json.dumps(dict(kind='empty-counter-control',samples_ns=samples,subtraction_applied=False)),flush=True)
    for repetition in range(-1,5):print(json.dumps(episode(data,repetition),allow_nan=False),flush=True)

def admission():
    resource.setrlimit(resource.RLIMIT_CPU,(LIMITS['cpu_seconds'],)*2);resource.setrlimit(resource.RLIMIT_AS,(LIMITS['address_space_bytes'],)*2)

def supervised(command,folder):
    folder.mkdir();begin=time.perf_counter_ns();usage=None;code=None;status='spawn-failed';error=None;process=None;expired=False
    with (folder/'stdout.jsonl').open('wb') as out,(folder/'stderr.txt').open('wb') as err:
        try:
            process=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,preexec_fn=admission,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
            while True:
                pid,wait_status,usage=os.wait4(process.pid,os.WNOHANG)
                if pid:break
                if time.perf_counter_ns()-begin>LIMITS['wall_seconds']*10**9:
                    expired=True
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    _,wait_status,usage=os.wait4(process.pid,0);break
                time.sleep(.002)
            code=os.waitstatus_to_exitcode(wait_status);process.returncode=code;status='timed-out' if expired else 'completed' if code==0 else 'failed'
        except (OSError,subprocess.SubprocessError) as problem:error=repr(problem)
    return dict(command=command,status=status,return_code=code,timed_out=expired,error=error,whole_process_ns=time.perf_counter_ns()-begin,
        user_cpu_seconds=usage.ru_utime if usage else None,system_cpu_seconds=usage.ru_stime if usage else None,peak_rss_kib=usage.ru_maxrss if usage else None,
        stdout_sha256=sha((folder/'stdout.jsonl').read_bytes()),stderr_sha256=sha((folder/'stderr.txt').read_bytes()),limits=LIMITS,
        scope='direct Linux worker wait4 CPU/RSS and POSIX CPU/address-space limits; wall includes startup/imports/serialization/polling; no native heap cap')

def capture(output):
    if resource is None or not hasattr(os,'wait4') or sys.platform!='linux':raise ValueError('capture requires Linux POSIX resource/wait4 support')
    if output.exists():raise ValueError('new capture directory required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise ValueError('clean committed capture source required')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();sources={name:(ROOT/name).read_bytes() for name in FILES}
    for name,data in sources.items():
        if subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT)!=data:raise ValueError('capture source differs from committed bytes')
    inputs=builder.input_record();output.mkdir(parents=True)
    for name,data in sources.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (output/'inputs.json').write_bytes((ROOT/'scripts/reports/mpc06_offline/inputs.json').read_bytes())
    clock=time.get_clock_info('perf_counter');environment=dict(schema='csl.mpc06.offline-capture/1',source_revision=revision,source_sha256={n:sha(v) for n,v in sources.items()},input_sha256=sha((output/'inputs.json').read_bytes()),python=sys.version,executable=sys.executable,executable_sha256=sha(Path(sys.executable).read_bytes()),platform=platform.platform(),processor=platform.processor() or next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'unavailable'),cpu_count=os.cpu_count(),load_average=os.getloadavg(),clock=dict(implementation=clock.implementation,resolution_seconds=clock.resolution,monotonic=clock.monotonic,adjustable=clock.adjustable),limits=LIMITS,library_threads='no BLAS/native solver invoked; one Python worker at a time',measured_repetitions=5,warmup_repetitions=1,verdict='inconclusive performance; one configured offline construction with no comparative ranking or retrospective native timing')
    (output/'environment.json').write_bytes(encoded(environment))
    command=[sys.executable,'-B','-m','scripts.reports.mpc06_offline.study','--worker','--inputs',str(output/'inputs.json')]
    for arm in ('measured','profiled'):
        args=command+(['--profile',str(output/'profile.pstats')] if arm=='profiled' else [])
        receipt=supervised(args,output/arm);(output/arm/'process.json').write_bytes(encoded(receipt))
    if (output/'profile.pstats').exists():
        import pstats
        with (output/'profile.txt').open('w') as stream:pstats.Stats(str(output/'profile.pstats'),stream=stream).strip_dirs().sort_stats('cumulative').print_stats(25)
    hashes={p.relative_to(output).as_posix():sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()};(output/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()))
    return environment

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--inputs',type=Path);p.add_argument('--profile',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.worker:
        data=json.loads(a.inputs.read_bytes())
        if a.profile:cProfile.runctx('worker(data)',globals(),locals(),str(a.profile))
        else:worker(data)
    elif a.output:print(json.dumps(capture(a.output.resolve())))
    else:p.error('--worker or --output required')

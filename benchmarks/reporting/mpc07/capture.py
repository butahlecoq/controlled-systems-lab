#!/usr/bin/env python3
"""Bounded saved MPC07 attempts using the already reviewed public ConvexPort bridge."""
from __future__ import annotations
import argparse
import cProfile
import pstats
import io
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time
import threading
import zipfile
from fractions import Fraction as Q
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from benchmarks.reporting.mpc07 import policy

ROOT=Path(__file__).resolve().parents[3]
BRIDGE_SHA='266e1cda61b064b4603ff6499d76dc4db59106e4e673905f585c54caafa9c533'
README_ARCHIVE=ROOT/'benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip'
README_MEMBER='mpc07-report/RAW/source/README.md'
README_SHA256='631c84d73f1b228bd6797a0e2ccf5e4d409fafcf6ef9a3cf820be69f89cd40cb'


def encode(value):
    if isinstance(value,Q):return str(value)
    raise TypeError(type(value).__name__)


def write(path,value):path.write_text(json.dumps(value,indent=2,default=encode)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def archived_readme():
    with zipfile.ZipFile(README_ARCHIVE) as archive:
        members=[item for item in archive.infolist() if item.filename==README_MEMBER]
        if len(members)!=1 or members[0].is_dir() or members[0].file_size>100_000:
            raise ValueError('sealed MPC07 README member inventory differs')
        content=archive.read(members[0])
    if hashlib.sha256(content).hexdigest()!=README_SHA256:
        raise ValueError('sealed MPC07 README bytes differ')
    return content


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))


def attempt(folder,bridge,payload):
    write(folder/'program.json',payload)
    command=[str(bridge),str(folder/'program.json')]
    environment=os.environ.copy();environment.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    started=time.monotonic_ns();expired=threading.Event();finished=threading.Event()
    with (folder/'stdout.json').open('wb') as stdout,(folder/'stderr.txt').open('wb') as stderr:
        try:process=subprocess.Popen(command,stdout=stdout,stderr=stderr,
                env=environment,preexec_fn=limits,start_new_session=True)
        except OSError as error:
            (folder/'stderr.txt').write_text(str(error)+'\n');write(folder/'process-resource.txt',dict(status='not-started'))
            return dict(status='spawn-failed',returncode=None,timed_out=False,whole_process_ns=time.monotonic_ns()-started,command=command)
        def stop():
            if finished.is_set():return
            expired.set()
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        timer=threading.Timer(300,stop);timer.daemon=True;timer.start()
        try:
            _,status,usage=os.wait4(process.pid,0)
            process.returncode=os.waitstatus_to_exitcode(status)
        finally:finished.set();timer.cancel()
    write(folder/'process-resource.txt',dict(user_cpu_seconds=usage.ru_utime,system_cpu_seconds=usage.ru_stime,
        maximum_resident_set_kib=usage.ru_maxrss,scope='Linux wait4 direct native child; peak RSS in KiB, not address space'))
    status='wall-limit' if expired.is_set() else ('completed' if process.returncode==0 else 'process-failed')
    return dict(status=status,returncode=process.returncode,timed_out=expired.is_set(),whole_process_ns=time.monotonic_ns()-started,
        command=command,limits=dict(wall_seconds=300,cpu_seconds=300,address_space_bytes_per_process=8*1024**3,
        workers=1,threads_requested=1,mechanism='process-group wall kill; inherited POSIX RLIMIT_CPU/RLIMIT_AS; Linux wait4 child accounting',
        suite_memory='one sequential child; no cgroup aggregate memory cap'))



def coherent_receipt(receipt):
    status=receipt.get('status');code=receipt.get('returncode');timed_out=receipt.get('timed_out')
    if type(timed_out) is not bool:return False
    if status=='completed' and (type(code) is not int or code!=0 or timed_out):return False
    if timed_out and status!='wall-limit':return False
    if status=='completed' or receipt.get('purpose'):
        duration=receipt.get('whole_process_ns');limits=receipt.get('limits',{})
        if type(duration) is not int or not 0<=duration<=301_000_000_000:return False
        required={'wall_seconds':300,'cpu_seconds':300,'address_space_bytes_per_process':8*1024**3,'workers':1,'threads_requested':1}
        if any(type(limits.get(key)) is not int or limits[key]!=value for key,value in required.items()):return False
        if not isinstance(limits.get('mechanism'),str) or not isinstance(limits.get('suite_memory'),str):return False
    return True


def recheck(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    if not coherent_receipt(receipt):return dict(status='inconclusive-invalid-process-receipt')
    if receipt.get('purpose')=='provider-width-refusal':
        text=(folder/'stderr.txt').read_text()
        return dict(status='expected-native-admission-refusal' if receipt['status']=='process-failed' and receipt['returncode']==1 and not receipt['timed_out'] and 'unsupported variable count' in text else 'inconclusive-process-outcome')
    if receipt['status']!='completed' or receipt['returncode']!=0:return dict(status='inconclusive-process-outcome')
    if receipt.get('purpose')=='literal-contradictory-row':
        payload=json.loads((folder/'program.json').read_text());result=json.loads((folder/'stdout.json').read_text())
        csr=payload['constraints']
        if payload['rows'][-1]!=[None,-1.] or csr['row_offsets'][-1]!=csr['row_offsets'][-2]:
            raise ValueError('contradictory-row probe differs from literal zero <= -1')
        return dict(status='expected-literal-infeasibility' if result.get('termination')=='completed' and
                    result.get('mathematical_outcome')=='infeasible' else 'inconclusive-native-outcome',
                    proof='last constraint is exactly zero <= -1; native status remains numerical')
    payload=json.loads((folder/'program.json').read_text());result=json.loads((folder/'stdout.json').read_text())
    return policy.check_result(payload,result)


def capture(bridge,output,repetitions):
    bridge=bridge.resolve();output=output.resolve()
    if output.exists():raise ValueError('capture directory must be new')
    if sha(bridge)!=BRIDGE_SHA:raise ValueError('bridge differs from reviewed reused native artifact')
    if not 1<=repetitions<=5:raise ValueError('bounded capture requires 1..5 repetitions')
    source_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if source_status:raise ValueError('capture requires committed clean source')
    output.mkdir(parents=True);(output/'attempts').mkdir();(output/'source').mkdir()
    for path in Path(__file__).parent.iterdir():
        if path.is_file() and path.name!='README.md':(output/'source'/path.name).write_bytes(path.read_bytes())
    (output/'source/README.md').write_bytes(archived_readme())
    (output/'source/test_mpc07_policy.py').write_bytes((ROOT/'tests/reporting/test_mpc07_policy.py').read_bytes())
    (output/'native-CMakeCache.txt').write_bytes((bridge.parent/'CMakeCache.txt').read_bytes())
    for name in ('affine_bridge.cpp','CMakeLists.txt'):
        (output/'source'/('native-'+name)).write_bytes(subprocess.check_output(['git','show','--end-of-options','b3978a98a8bfb30e21841466244ed7f78e987886:benchmarks/reporting/mpc11/'+name],cwd=ROOT))
    environment=dict(schema='csl.mpc07.capture/1',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_status=source_status,source_sha256={p.name:sha(p) for p in sorted((output/'source').iterdir())},
        bridge_sha256=sha(bridge),native_source_commit='b3978a98a8bfb30e21841466244ed7f78e987886',
        native_build_scope='reused reviewed Release public CSL ConvexPort bridge; zero Hessian dispatches actual LP',
        python=sys.version,platform=platform.platform(),cpu_count=os.cpu_count(),
        load_start=subprocess.check_output(['uptime'],text=True).strip(),
        repetitions=repetitions,primary_scope='single batch policy synthesis only; no MPC recursive-feasibility or hard real-time claim')
    write(output/'environment.json',environment)
    # One complete retained warmup, then alternating formulation order per repeat.
    index=0
    for repetition in range(-1,repetitions):
        for n in policy.HORIZONS:
            for sigma in policy.SIGMAS:
                order=list(policy.KINDS)
                if repetition%2:order.reverse()
                for kind in order:
                    folder=output/'attempts'/f'{index:04d}';folder.mkdir();index+=1
                    started=time.monotonic_ns();payload=policy.program(n,sigma,kind);prepared=time.monotonic_ns()-started
                    receipt=attempt(folder,bridge,payload);receipt.update(repetition=repetition,warmup=repetition==-1,
                        horizon=n,sigma=str(sigma),policy_class=kind,python_prepare_ns=prepared,
                        variables=len(payload['variables']),rows=len(payload['rows']),nonzeros=len(payload['constraints']['values']))
                    write(folder/'receipt.json',receipt);checked_at=time.monotonic_ns()
                    try:checked=recheck(folder)
                    except Exception as error:checked=dict(status='incorrect-or-unverified',error_type=type(error).__name__,reason=str(error))
                    checked['independent_check_ns']=time.monotonic_ns()-checked_at
                    checked['bindings']={name:sha(folder/name) for name in ('program.json','receipt.json','stdout.json','stderr.txt','process-resource.txt')}
                    write(folder/'check.json',checked)
    # Retain two explicitly unpaired refusal/infeasibility probes outside timings.
    import copy
    (output/'probes').mkdir()
    for purpose in ('provider-width-refusal','literal-contradictory-row'):
        folder=output/'probes'/purpose;folder.mkdir();payload=copy.deepcopy(policy.program(2,Q(1),'adf'))
        if purpose=='provider-width-refusal':payload['q_diagonal']=[0.]*4097
        else:
            payload['rows'].append([None,-1.]);payload['constraints']['rows']+=1
            payload['constraints']['row_offsets'].append(payload['constraints']['row_offsets'][-1])
        payload['program_sha256']=hashlib.sha256(json.dumps({k:v for k,v in payload.items() if k!='program_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        receipt=attempt(folder,bridge,payload);receipt['purpose']=purpose;write(folder/'receipt.json',receipt)
        checked=recheck(folder);checked['bindings']={name:sha(folder/name) for name in ('program.json','receipt.json','stdout.json','stderr.txt','process-resource.txt')}
        write(folder/'check.json',checked)
    environment['load_end']=subprocess.check_output(['uptime'],text=True).strip();write(output/'environment.json',environment)
    # A separate Python profile identifies authored assembly/checker work, never native LP cost.
    def diagnostic():
        for n in policy.HORIZONS:
            for kind in policy.KINDS:policy.program(n,Q(5,4),kind)
        for folder in sorted((output/'attempts').iterdir())[:24]:recheck(folder)
    profiler=cProfile.Profile();profiler.runcall(diagnostic);profiler.dump_stats(output/'python-diagnostic.prof')
    profile_text=io.StringIO();pstats.Stats(profiler,stream=profile_text).sort_stats('cumulative').print_stats(25)
    (output/'python-diagnostic.txt').write_text(profile_text.getvalue())
    write(output/'profile-scope.json',dict(scope='separate untimed Python LP construction and saved exact checking; native LP limiter not isolated',
        native_timing_verdict='inconclusive; no native profiler or tuning sweep; no performance ranking'))
    files=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(output).as_posix()}\n' for p in files))
    return environment


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bridge',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--repetitions',type=int,default=5)
    a=p.parse_args();print(json.dumps(capture(a.bridge,a.output,a.repetitions)))

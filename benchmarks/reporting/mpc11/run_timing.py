#!/usr/bin/env python3
"""Resume immutable, serial, alternating NI1 timing captures on one host."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import inspect
import do_mpc
import json
import os
from pathlib import Path
import platform
import signal
import shutil
import subprocess
import sys
import time
from run_affine import write

ROOT=Path(__file__).resolve().parent
THREADS={key:'1' for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text())


def inventory(folder):
    return {p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p!=folder/'receipt.json'}


def validate_receipt(folder):
    receipt=load(folder/'receipt.json')
    if receipt['files']!=inventory(folder):raise ValueError('timing unit payload binding mismatch')
    return receipt


def unit(root,key,command,wall_seconds=1200):
    parent=root/key;parent.mkdir(parents=True,exist_ok=True)
    attempts=sorted(parent.glob('attempt-*'))
    for previous in attempts:
        if (previous/'receipt.json').exists():
            receipt=validate_receipt(previous)
            if receipt['command']!=command:raise ValueError('completed timing command changed')
            return previous,receipt
    target=parent/f'attempt-{len(attempts):03d}';target.mkdir()
    write(target/'started.json',{'command':command,'load_average':list(os.getloadavg()),'wall_limit_seconds':wall_seconds,'started_unix_ns':time.time_ns()})
    environment=os.environ.copy();environment.update(THREADS)
    start=time.monotonic();status='completed';usage=None;returncode=None
    with (target/'stdout.txt').open('wb') as out,(target/'stderr.txt').open('wb') as err:
        process=subprocess.Popen([*command,'--output',str(target/'capture')],stdout=out,stderr=err,env=environment,start_new_session=True)
        while True:
            pid,wait_status,usage=os.wait4(process.pid,os.WNOHANG)
            if pid:
                returncode=os.waitstatus_to_exitcode(wait_status);process.returncode=returncode
                if returncode!=0:status='failed'
                break
            if time.monotonic()-start>wall_seconds:
                os.killpg(process.pid,signal.SIGKILL);_,wait_status,usage=os.wait4(process.pid,0)
                returncode=os.waitstatus_to_exitcode(wait_status);process.returncode=returncode;status='timed_out';break
            time.sleep(.1)
    receipt={'command':command,'status':status,'return_code':returncode,'whole_process_seconds':time.monotonic()-start,
             'process_cpu_seconds':{'user':usage.ru_utime,'system':usage.ru_stime},'max_rss_kib':usage.ru_maxrss,
             'resource_scope':'wait4 child plus reaped descendants; maximum RSS is largest process high-water mark, not simultaneous tree sum',
             'ending_load_average':list(os.getloadavg()),'files':inventory(target)}
    write(target/'receipt.json',receipt)
    return target,receipt


def source_identity(affine_bridge,replay_bridge):
    files=[*sorted(ROOT.glob('*.py')),*sorted(ROOT.glob('*.cpp')),*sorted((ROOT/'scenarios').glob('*.json')),ROOT/'environment/requirements-linux-cp311.lock']
    files=[p for p in files if p.exists()]
    return {'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in files},
            'do_mpc_controller_source_sha256':sha(Path(inspect.getfile(do_mpc.controller.MPC))),'affine_bridge_sha256':sha(affine_bridge),'replay_bridge_sha256':sha(replay_bridge),
            'python':platform.python_version(),'distributions':{n:importlib.metadata.version(n) for n in ['do-mpc','casadi','numpy','scipy']},
            'requested_library_threads':THREADS,'repetitions':5,'collocation_elements':1,'affine_objective_multiplier':1000.}


def capture(output,affine_bridge,replay_bridge):
    output.mkdir(parents=True,exist_ok=True)
    with (output/'capture.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=source_identity(affine_bridge,replay_bridge)
        if (output/'environment.json').exists():
            if load(output/'environment.json')['identity']!=identity:raise ValueError('resume source/configuration/binary identity changed')
        else:
            write(output/'environment.json',{'identity':identity,'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
                'platform':platform.platform(),'cpu_count':os.cpu_count(),'starting_load_average':list(os.getloadavg()),
                'cpuinfo':Path('/proc/cpuinfo').read_text(),'profiler_available':{'perf':shutil.which('perf'),'external_time':shutil.which('time')},
                'claim':'Repeated descriptive configured workload costs; affine open-loop and NMPC receding policy are mathematically different. Comparative performance verdict inconclusive without limiter profile.'})
        python=sys.executable;order=[('warmup',['affine','nmpc'])]+[(f'rep-{i:02d}',['affine','nmpc'] if i%2==0 else ['nmpc','affine']) for i in range(5)]
        for repetition,arms in order:
            for arm in arms:
                prefix=repetition+'/'+arm
                if arm=='affine':
                    folder,receipt=unit(output,prefix+'/optimization',[python,str(ROOT/'run_affine.py'),'--bridge',str(affine_bridge),'--objective-multiplier','1000'])
                    if receipt['status']=='completed':unit(output,prefix+'/nonlinear',[python,str(ROOT/'run_nonlinear.py'),'--affine-bundle',str(folder/'capture'),'--bridge',str(replay_bridge)])
                else:unit(output,prefix,[python,str(ROOT/'run_nmpc.py'),'--scenario-directory',str(ROOT/'scenarios'),'--bridge',str(replay_bridge)])
        print('capture finished; check and summarize outside measured arms',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--affine-bridge',type=Path,required=True);p.add_argument('--replay-bridge',type=Path,required=True)
    a=p.parse_args();capture(a.output.resolve(),a.affine_bridge.resolve(strict=True),a.replay_bridge.resolve(strict=True))

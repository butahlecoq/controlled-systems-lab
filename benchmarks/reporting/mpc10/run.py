#!/usr/bin/env python3
"""Bounded actual-CSL/SCIP pilots; every attempted worker keeps raw evidence."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from benchmarks.reporting.mpc10.fixtures import fixtures
from benchmarks.reporting.mpc10.oracle import histories,solve as exact

ROOT=Path(__file__).resolve().parents[3]
SOURCE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(90,90));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))


def worker(s,folder):
    from benchmarks.reporting.mpc10.scip_reference import solve
    if s.get('external_unsupported'):
        write(folder/'results.json',{'status':'unsupported','reason':s['external_unsupported']});return
    rows=[]
    for number,path in enumerate([None,*histories(s)]):
        location=folder/('global' if path is None else f'branch-{number-1:03d}')
        r=solve(s,location,path);write(location/'result.json',r);rows.append({'relative_path':location.name,'result':r})
    if s['id']=='hybrid-T3':
        r=solve(s,folder/'node-limit',interrupted=True);write(folder/'node-limit/result.json',r);rows.append({'relative_path':'node-limit','result':r})
    write(folder/'results.json',{'status':'complete','attempts':rows})


def process(command,folder):
    folder.mkdir();started=time.monotonic();code=None;status='failed';stdout=b'';stderr=b''
    environment=os.environ.copy();environment.update({k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']})
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        p=subprocess.run(command,capture_output=True,env=environment,timeout=120,preexec_fn=limits)
        code=p.returncode;stdout=p.stdout;stderr=p.stderr;status='completed' if code==0 else 'failed'
    except subprocess.TimeoutExpired as e:status='timed_out';stdout=e.stdout or b'';stderr=e.stderr or b''
    after=resource.getrusage(resource.RUSAGE_CHILDREN);(folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
    r={'command':command,'status':status,'return_code':code,'whole_process_seconds':time.monotonic()-started,'user_cpu_seconds':after.ru_utime-before.ru_utime,'system_cpu_seconds':after.ru_stime-before.ru_stime,'cumulative_children_max_rss_kib':after.ru_maxrss,'memory_scope':'cumulative process-child high-water maximum, not per-worker isolated RSS or native heap accounting','stdout_sha256':sha(folder/'stdout.txt'),'stderr_sha256':sha(folder/'stderr.txt')};write(folder/'process.json',r);return r


def capture(output,bridge):
    output.mkdir(parents=True,exist_ok=False)
    source_files=[*sorted(SOURCE.glob('*.py')),*sorted(SOURCE.glob('*.cpp')),SOURCE/'CMakeLists.txt']
    snapshot=output/'source';snapshot.mkdir()
    for path in source_files:(snapshot/path.name).write_bytes(path.read_bytes())
    receipt={'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),'source_sha256':{p.name:sha(p) for p in source_files},'bridge_sha256':sha(bridge),'python':platform.python_version(),'pyscipopt':importlib.metadata.version('pyscipopt'),'platform':platform.platform(),'load_average':list(os.getloadavg()),'limits':{'worker_cpu_seconds':90,'worker_wall_seconds':120,'worker_address_space_bytes':2*1024**3,'scip_model_memory_megabytes':512,'scip_model_wall_seconds':15,'workers':1,'requested_library_threads':1},'claim':'initial bounded configured observations; no timing ranking, global hybrid-game or general scalability claim'}
    write(output/'environment.json',receipt);cases=[]
    for s in fixtures():
        s['fixture_sha256']=canonical(s);folder=output/s['id'];folder.mkdir();write(folder/'fixture.json',s)
        started=time.monotonic();oracle=exact(s);write(folder/'exact.json',oracle);write(folder/'exact-process.json',{'elapsed_seconds':time.monotonic()-started})
        native=process([str(bridge),str(folder/'fixture.json')],folder/'native')
        scip=process([sys.executable,'-m','benchmarks.reporting.mpc10.run','--worker','--fixture',str(folder/'fixture.json'),'--output',str(folder/'scip')],folder/'scip-process')
        cases.append({'id':s['id'],'native_process':native['status'],'scip_process':scip['status']})
    write(output/'manifest.json',{'cases':cases,'scope':'All raw attempted cases, including failures, refusals and bounded prefixes are retained.'})
    write(output/'file-hashes.json',{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--fixture',type=Path);p.add_argument('--bridge',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.worker:a.output.mkdir();worker(json.loads(a.fixture.read_text()),a.output)
    else:capture(a.output.resolve(),a.bridge.resolve(strict=True))

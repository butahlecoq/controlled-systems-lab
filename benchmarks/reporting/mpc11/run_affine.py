#!/usr/bin/env python3
"""Run bounded correctness pilots through the actual public CSL convex bridge."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import time

from affine import canonical_hash, check_solution, model, program
from check_scenarios import validate


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(300,300))
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))


def tiny_program():
    value={'schema':'csl.mpc11.affine-program/1','case_id':'ANALYTIC-JOINT-QP-01',
        'program_id':'analytic-joint-qp-01/public-joint-qp/1',
        'q_diagonal':[0,2,2],'linear':[0,-4,0],'offset':4,
        'variables':[[0,0],[-10,10],[-10,10]],'rows':[[0,0]],
        'constraints':{'rows':1,'cols':3,'row_offsets':[0,3],
                       'column_indices':[0,1,2],'values':[-1,1,-1]}}
    value['program_sha256']=canonical_hash(value)
    return value


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();bridge=args.bridge.resolve(strict=True);out=args.output.resolve()
    if out.exists() and any(out.iterdir()):parser.error('output must be new or empty')
    out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parent
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())
    environment=os.environ.copy()
    for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:environment[name]='1'
    attempts=[]
    for source in [None,*sorted((root/'scenarios').glob('*.json'))]:
        started=time.monotonic_ns()
        if source is None:
            scenario=None;coefficients=None;qp=tiny_program();case=qp['case_id']
        else:
            scenario=json.loads(source.read_text());validate(scenario);case=scenario['case_id']
            coefficients=model(scenario);qp=program(scenario,coefficients)
        folder=out/case.lower();folder.mkdir()
        if scenario is not None:write(folder/'scenario.json',scenario);write(folder/'model.json',coefficients)
        write(folder/'program.json',qp)
        construction_ns=time.monotonic_ns()-started
        start=time.monotonic_ns();stdout=b'';stderr=b'';status='failed';returncode=None;result=None
        try:
            process=subprocess.run([str(bridge),str(folder/'program.json')],capture_output=True,
                timeout=300,env=environment,preexec_fn=limits)
            stdout,stderr,returncode=process.stdout,process.stderr,process.returncode
            if process.returncode==0:result=json.loads(stdout);status='completed'
        except subprocess.TimeoutExpired as error:
            stdout,stderr=error.stdout or b'',error.stderr or b'';status='timed_out'
        except (ValueError,OSError) as error:
            stderr+=str(error).encode();status='invalid_output'
        process_ns=time.monotonic_ns()-start
        (folder/'stdout.json').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        if scenario is None:
            primal=(result or {}).get('primal',[])
            good=(result or {}).get('termination')=='completed' and (result or {}).get('mathematical_outcome')=='optimal' and not (result or {}).get('contract_diagnostics') and len(primal)==3 and max(abs(a-b) for a,b in zip(primal,[0,1,1]))<1e-6
            checks={'status':'verified-numerical-witness' if good else 'incorrect','oracle':'x0=0,x1=u; minimize (x1-2)^2+u^2 => x1=u=1,J=2'}
            if good:checks['objective']=(primal[1]-2)**2+primal[2]**2
        else:
            checks=check_solution(scenario,coefficients,qp,result or {})
        write(folder/'check.json',checks)
        attempts.append({'case_id':case,'process_status':status,'return_code':returncode,
            'configuration_construction_ns':construction_ns,'whole_process_ns':process_ns,
            'check_status':checks['status'],'program_sha256':qp['program_sha256'],
            'program_file_sha256':hashlib.sha256((folder/'program.json').read_bytes()).hexdigest(),
            'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest(),
            'command':['<BUILD_DIR>/csl_mpc11_affine',f'{case.lower()}/program.json']})
    write(out/'manifest.json',{'schema':'csl.mpc11.affine-pilot/1','source_revision':revision,
        'source_worktree_dirty':dirty,'bridge_sha256':hashlib.sha256(bridge.read_bytes()).hexdigest(),
        'python':platform.python_version(),'platform':platform.platform(),
        'numpy':importlib.metadata.version('numpy'),'scipy':importlib.metadata.version('scipy'),
        'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ['affine.py','affine_bridge.cpp','run_affine.py','CMakeLists.txt']},'attempts':attempts,
        'limits':{'cpu_seconds':300,'address_space_bytes':8*1024**3,'wall_seconds':300,
                  'mechanism':'POSIX RLIMIT_CPU/RLIMIT_AS + subprocess timeout; single bridge process'},
        'claim':'bounded correctness pilots, not repeated performance evidence; actual CSL joint convex program; no nonlinear execution or complete-family certificate'})
    print(json.dumps({'attempts':len(attempts),'checks':[r['check_status'] for r in attempts]}))
    return 0 if all(r['check_status']=='verified-numerical-witness' for r in attempts) else 1


if __name__=='__main__':raise SystemExit(main())

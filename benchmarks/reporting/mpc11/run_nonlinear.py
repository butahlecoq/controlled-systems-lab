#!/usr/bin/env python3
"""Bounded nonlinear execution and independent replay of verified affine controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
from affine import canonical_hash, check_solution
from check_affine_saved import check
from nonlinear import make_request, evaluate
from run_affine import write, limits


def capture(command,folder,environment):
    started=time.monotonic();status='failed';code=None;stdout=b'';stderr=b''
    try:
        p=subprocess.run(command,capture_output=True,env=environment,preexec_fn=limits,timeout=300)
        code=p.returncode;stdout=p.stdout;stderr=p.stderr
        status='completed' if code==0 else 'failed'
    except subprocess.TimeoutExpired as error:
        status='timed_out';stdout=error.stdout or b'';stderr=error.stderr or b''
    except OSError as error:stderr=str(error).encode()
    (folder/'stdout.json').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
    receipt={'process_status':status,'return_code':code,'whole_process_seconds':time.monotonic()-started,
             'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest()}
    write(folder/'process.json',receipt)
    return json.loads(stdout) if status=='completed' else None


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--affine-bundle',type=Path,required=True)
    p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();source=a.affine_bundle.resolve();out=a.output.resolve();bridge=a.bridge.resolve(strict=True)
    if out.exists() and any(out.iterdir()):p.error('output must be new or empty')
    checked=check(source)
    if not all(r['status']=='verified-numerical-witness' for r in checked):raise ValueError('source affine bundle unverified')
    out.mkdir(parents=True,exist_ok=True);root=Path(__file__).resolve().parent
    environment=os.environ.copy()
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:environment[key]='1'
    cases=[]
    for case in ['syn-nl-lv-01','syn-nl-fuel-01']:
        folder=source/case;s=json.loads((folder/'scenario.json').read_text());coeff=json.loads((folder/'model.json').read_text())
        qp=json.loads((folder/'program.json').read_text());native=json.loads((folder/'stdout.json').read_text())
        witness=check_solution(s,coeff,qp,native);controls=witness['physical_controls']
        target=out/case;target.mkdir()
        # Preserve the complete source subset so portable verification does not trust a summary.
        import shutil
        (target/'source').mkdir()
        for name in ['scenario.json','model.json','program.json','unscaled-program.json','stdout.json','stderr.txt']:
            if (folder/name).exists():shutil.copyfile(folder/name,target/'source'/name)
        write(target/'affine-witness.json',witness)
        records={}
        for mode in ['cvodes','cvodes-tight','rk4','rk4-tight']:
            attempt=target/mode;attempt.mkdir();request=make_request(s,controls,witness['witness_sha256'],sensitivity=mode.endswith('-tight'))
            write(attempt/'request.json',request)
            command=[sys.executable,str(root/'nonlinear.py'),str(attempt/'request.json')] if mode.startswith('cvodes') else [str(bridge),str(attempt/'request.json')]
            result=capture(command,attempt,environment)
            if result is not None:
                if not mode.startswith('cvodes'):
                    result.update(evaluate(s,result['physical_states'],controls))
                    if result['status']!='complete':result['objective']=None
                write(attempt/'record.json',result)
            records[mode]=result
        report={'case_id':s['case_id'],'witness_sha256':witness['witness_sha256'],'controls_sha256':canonical_hash(controls),
                'affine_objective':witness['objective'],'statuses':{k:v['status'] if v else 'process-incomplete' for k,v in records.items()},
                'objectives':{k:v['objective'] if v else None for k,v in records.items()},
                'claim':'numerical sampled execution and integrator sensitivity; no certified error, safety, global optimality, or reachable set'}
        if all(v and v['status']=='complete' for v in records.values()):
            cv=np.array(records['cvodes']['physical_states']);rk=np.array(records['rk4']['physical_states']);tight=np.array(records['rk4-tight']['physical_states'])
            report['max_physical_cvodes_sensitivity']=np.max(np.abs(np.array(records['cvodes-tight']['physical_states'])-cv),axis=0).tolist()
            report['max_physical_cvodes_rk4_difference']=np.max(np.abs(cv-rk),axis=0).tolist()
            report['max_physical_rk4_sensitivity']=np.max(np.abs(tight-rk),axis=0).tolist()
            endpoints=cv[::s['independent_replay']['report_subintervals_per_hold']]
            report['max_physical_affine_prediction_nonlinear_difference']=np.max(np.abs(endpoints-witness['physical_states']),axis=0).tolist()
        write(target/'comparison.json',report);cases.append(report)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    manifest={'schema':'csl.mpc11.nonlinear-pilot/1','source_revision':revision,
              'source_worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()),
              'affine_capture_source':json.loads((source/'manifest.json').read_text())['source_revision'],'bridge_sha256':hashlib.sha256(bridge.read_bytes()).hexdigest(),
              'python':platform.python_version(),'platform':platform.platform(),'cases':cases,
              'limits':{'cpu_seconds':300,'wall_seconds':300,'address_space_bytes':8*1024**3,'mechanism':'POSIX RLIMIT_CPU/RLIMIT_AS + subprocess timeout','workers':1},
              'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['nonlinear.py','run_nonlinear.py','nonlinear_replay_bridge.cpp']}}
    write(out/'manifest.json',manifest)
    files={str(path.relative_to(out)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob('*')) if path.is_file()}
    write(out/'file-hashes.json',files)
    print(json.dumps(cases,indent=2))
    return 0 if all(all(x=='complete' for x in r['statuses'].values()) for r in cases) else 1

if __name__=='__main__':raise SystemExit(main())

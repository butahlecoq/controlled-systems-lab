#!/usr/bin/env python3
"""Bounded shrinking-horizon NMPC correctness workers with durable prefixes."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
from affine import canonical_hash
from check_scenarios import validate
from nmpc import build_controller, initialize_guess, solve_update, execution_integrator, direct_tail_cost, references
from nonlinear import make_request, evaluate
from run_affine import write, limits


@contextmanager
def native_log(path):
    sys.stdout.flush();sys.stderr.flush();saved=[os.dup(1),os.dup(2)]
    with path.open('wb') as stream:
        os.dup2(stream.fileno(),1);os.dup2(stream.fileno(),2)
        try:yield
        finally:
            # Flush C stdio before restoring descriptors; solver output is native.
            import ctypes
            ctypes.CDLL(None).fflush(None);sys.stdout.flush();sys.stderr.flush()
            os.dup2(saved[0],1);os.dup2(saved[1],2)
            for fd in saved:os.close(fd)


def running_prefix(s,controls):
    u=np.asarray(controls)
    if not len(u):return 0.
    o=s['objective']
    return float(o['running_weight']/s['time']['intervals']*np.sum(((u-references(s)[:len(u)])/o['running_scale'])**2))


def worker(s,folder):
    validate(s);write(folder/'scenario.json',s);n=s['time']['intervals'];scales=np.array([v['scale'] for v in s['states']]);sub=s['independent_replay']['report_subintervals_per_hold']
    initial=np.array([v['initial'] for v in s['states']])/scales;states=[initial.tolist()];controls=[];previous=None;updates=[];execution=[];failure=None
    started=time.monotonic();integrator=execution_integrator(s)
    record={'schema':'csl.mpc11.controller-attempt/1','variant':'nominal-nmpc/nonlinear-replay','case_id':s['case_id'],
            'scenario_sha256':canonical_hash(s),'model_id':s['model_id'],'controller_id':s['controller_id'],'objective_id':s['objective_id'],
            'status':'in-progress','controls':controls,'scaled_states':states,'updates':updates,'execution_intervals':execution,
            'provider':'do-mpc5.1.2/CasADi3.8.0/IPOPT-MUMPS','assurance':'local NLP and numerical execution only; no minimax/global/safety/reachable-set guarantee'}
    def persist():
        physical=(np.asarray(states)*scales).tolist();record['physical_states']=physical
        record['times']=[s['time']['grid'][k]+s['time']['dt']*r/sub for k in range(len(controls)) for r in range(sub)]+[s['time']['grid'][len(controls)]]
        record['completed_holds']=len(controls);record['running_cost_prefix']=running_prefix(s,controls)
        record['completed_objective']=direct_tail_cost(s,0,physical[-1],controls) if len(controls)==n else None
        record['elapsed_seconds']=time.monotonic()-started
        record['controls_sha256']=canonical_hash(controls)
        record['witness_sha256']=canonical_hash({'scenario_sha256':canonical_hash(s),'controls':controls,'physical_states':physical,'variant':record['variant']})
        write(folder/'attempt.json',record)
    persist()
    for j in range(n):
        update=folder/f'update-{j:03d}';update.mkdir();write(update/'started.json',{'update_index':j,'remaining_horizon':n-j,'observed_scaled':states[-1],'stage':'setup'})
        try:
            with native_log(update/'solver.log'):
                mpc,meta=build_controller(s,j);guess=initialize_guess(mpc,s,j,np.array(states[-1]),previous)
                guess['source_solve_sha256']=updates[-1]['solve_sha256'] if updates else None
                write(update/'guess.json',guess)
                result,next_prediction=solve_update(mpc,s,j,np.array(states[-1]),guess,meta)
            write(update/'result.json',result);updates.append({'index':j,'solve_sha256':result['solve_sha256'],'accepted':result['accepted'],'status':result['status']})
            if not result['accepted']:failure={'kind':'solve-rejected','update':j,'status':result['status']};break
            control=result['predicted_controls'][0];cb=np.asarray([v['physical_bounds'] for v in s['controls']])
            if np.any(np.array(control)<cb[:,0]-1e-10) or np.any(np.array(control)>cb[:,1]+1e-10):
                failure={'kind':'input-bound-rejected','update':j};break
            start=time.monotonic()
            with native_log(update/'execution.log'):
                values=np.asarray(integrator(x0=states[-1],p=control)['xf']).T
            if not np.isfinite(values).all() or (len(scales)==4 and np.min(values[:,:2])<0):
                failure={'kind':'execution-model-domain-error','update':j};break
            execution.append({'update':j,'elapsed_seconds':time.monotonic()-start,'method':'cvodes','abstol':s['execution']['scaled_abstol'],'reltol':s['execution']['reltol']})
            controls.append(control);states.extend(values.tolist());previous=next_prediction;persist()
        except Exception as error:
            failure={'kind':'setup-solve-or-execution-error','update':j,'error':str(error)};write(update/'error.json',failure);break
    record['status']='complete' if len(controls)==n else 'incomplete';record['failure']=failure;persist()
    return record


def replay_prefix(s,record,folder,bridge):
    count=len(record['controls']);outcomes={}
    if count==0:return {'status':'unavailable-no-executed-holds'}
    import copy
    prefix=copy.deepcopy(s)
    # The existing seam consumes a complete declared history; explicitly declare
    # the executed prefix grid, while binding the unchanged full scenario too.
    prefix['time']['intervals']=count;prefix['time']['grid']=s['time']['grid'][:count+1];prefix['time']['final']=prefix['time']['grid'][-1]
    for mode in ['rk4','rk4-tight']:
        target=folder/mode;target.mkdir();request=make_request(prefix,record['controls'],record['witness_sha256'],sensitivity=mode.endswith('tight'))
        request['full_scenario_sha256']=canonical_hash(s);request['full_original_interval_count']=s['time']['intervals']
        write(target/'request.json',request);start=time.monotonic();stdout=b'';stderr=b'';code=None;status='failed'
        try:
            p=subprocess.run([str(bridge),str(target/'request.json')],capture_output=True,timeout=300,preexec_fn=limits)
            stdout,stderr,code=p.stdout,p.stderr,p.returncode;status='completed' if code==0 else 'failed'
        except subprocess.TimeoutExpired as error:stdout=error.stdout or b'';stderr=error.stderr or b'';status='timed_out'
        (target/'stdout.json').write_bytes(stdout);(target/'stderr.txt').write_bytes(stderr)
        write(target/'process.json',{'status':status,'return_code':code,'elapsed_seconds':time.monotonic()-start})
        if status=='completed':
            result=json.loads(stdout);physical=np.array(result['physical_states'])
            # Evaluate the original objective with original N, never the prefix N.
            result['running_cost_prefix']=running_prefix(s,record['controls'])
            result['completed_objective']=direct_tail_cost(s,0,physical[-1],record['controls']) if count==s['time']['intervals'] and result['status']=='complete' else None
            bounds=np.array([v['physical_bounds'] for v in s['states']]);result['sampled_physical_state_violation']=np.maximum(np.maximum(bounds[:,0]-physical,physical-bounds[:,1]),0).max(axis=0).tolist()
            result['full_scenario_sha256']=canonical_hash(s);result['full_original_interval_count']=s['time']['intervals'];write(target/'record.json',result)
            outcomes[mode]={'status':result['status'],'completed_objective':result['completed_objective'],
                            'max_physical_execution_difference':np.max(np.abs(physical-np.asarray(record['physical_states'])),axis=0).tolist() if len(physical)==len(record['physical_states']) else None}
        else:outcomes[mode]={'status':status}
    if all(outcomes[k]['status']=='complete' for k in ['rk4','rk4-tight']):
        a=json.loads((folder/'rk4/record.json').read_text());b=json.loads((folder/'rk4-tight/record.json').read_text())
        outcomes['max_physical_tolerance_sensitivity']=np.max(np.abs(np.asarray(a['physical_states'])-b['physical_states']),axis=0).tolist()
    write(folder/'replay-summary.json',outcomes);return outcomes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--scenario',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--bridge',type=Path)
    a=p.parse_args();folder=a.output.resolve();root=Path(__file__).resolve().parent
    if a.worker:
        return 0 if worker(json.loads(a.scenario.read_text()),folder)['status']=='complete' else 1
    if folder.exists() and any(folder.iterdir()):p.error('new or empty output required')
    folder.mkdir(parents=True,exist_ok=True);environment=os.environ.copy()
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:environment[key]='1'
    cases=[]
    for case in ['lv','fuel']:
        source=root/f'scenarios/syn-nl-{case}-01.json';target=folder/f'syn-nl-{case}-01';target.mkdir();start=time.monotonic();stdout=b'';stderr=b'';code=None;status='failed'
        try:
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--scenario',str(source),'--output',str(target)],capture_output=True,timeout=300,preexec_fn=limits,env=environment)
            stdout,stderr,code=proc.stdout,proc.stderr,proc.returncode;status='completed' if code==0 else 'failed'
        except subprocess.TimeoutExpired as error:status='timed_out';stdout=error.stdout or b'';stderr=error.stderr or b''
        (target/'worker-stdout.txt').write_bytes(stdout);(target/'worker-stderr.txt').write_bytes(stderr)
        receipt={'process_status':status,'return_code':code,'whole_process_seconds':time.monotonic()-start};write(target/'process.json',receipt)
        attempt=json.loads((target/'attempt.json').read_text()) if (target/'attempt.json').exists() else None
        if attempt is not None and attempt['status']=='in-progress':
            attempt['status']='incomplete';attempt['failure']={'kind':status};write(target/'attempt.json',attempt)
        replay=replay_prefix(json.loads(source.read_text()),attempt,target,a.bridge.resolve()) if attempt and a.bridge else None
        cases.append({'case_id':json.loads(source.read_text())['case_id'],'process':receipt,'completed_holds':attempt['completed_holds'] if attempt else 0,'status':attempt['status'] if attempt else 'unavailable','replay':replay})
    write(folder/'manifest.json',{'schema':'csl.mpc11.nmpc-pilot/1','source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()),'python':platform.python_version(),'platform':platform.platform(),
          'provider':'do-mpc5.1.2/CasADi3.8.0/IPOPT3.14.19/MUMPS5.8.2','cases':cases,'limits':{'cpu_seconds':300,'wall_seconds':300,'address_space_bytes':8*1024**3,'workers':1,'library_threads_requested':1,'mechanism':'POSIX RLIMIT_CPU/RLIMIT_AS and subprocess timeout'},
          'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['nmpc.py','run_nmpc.py']},'claim':'bounded correctness pilot, not repeated performance evidence or global nonlinear guarantee'})
    write(folder/'file-hashes.json',{str(path.relative_to(folder)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(folder.rglob('*')) if path.is_file()})
    print(json.dumps(cases,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())

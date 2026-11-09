#!/usr/bin/env python3
"""Rebuild saved NMPC transcriptions without optimization and verify execution associations."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import casadi as ca
import numpy as np
from affine import canonical_hash
from check_scenarios import validate
from nmpc import build_controller, initialize_guess, direct_tail_cost, vector
from nonlinear import make_request
from run_nmpc import running_prefix


def check(bundle):
    load=lambda path:json.loads(path.read_text())
    hashes=load(bundle/'file-hashes.json')
    for name,digest in hashes.items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('saved hash mismatch: '+name)
    reports=[]
    for case in ['lv','fuel']:
        folder=bundle/f'syn-nl-{case}-01';s=load(folder/'scenario.json');validate(s);attempt=load(folder/'attempt.json');controls=attempt['controls'];count=len(controls);n=s['time']['intervals'];sub=s['independent_replay']['report_subintervals_per_hold'];scales=np.array([v['scale'] for v in s['states']])
        if attempt['case_id']!=s['case_id'] or attempt['scenario_sha256']!=canonical_hash(s) or attempt['controller_id']!=s['controller_id'] or attempt['objective_id']!=s['objective_id'] or attempt['model_id']!=s['model_id']:raise ValueError('controller identity mismatch')
        physical=np.asarray(attempt['physical_states']);scaled=np.asarray(attempt['scaled_states'])
        if count>n or count!=attempt['completed_holds'] or physical.shape!=(count*sub+1,len(scales)) or scaled.shape!=physical.shape:raise ValueError('executed prefix dimensions')
        if not np.isfinite(physical).all() or not np.array_equal(scaled*scales,physical):raise ValueError('physical/scaled transform')
        initial=np.array([v['initial'] for v in s['states']])/scales
        if scaled[0].tolist()!=initial.tolist():raise ValueError('initial observation mismatch')
        expected_times=[s['time']['grid'][k]+s['time']['dt']*r/sub for k in range(count) for r in range(sub)]+[s['time']['grid'][count]]
        if attempt['times']!=expected_times:raise ValueError('executed hold grid mismatch')
        complete=attempt['status']=='complete'
        if complete!=(count==n):raise ValueError('controller outcome/prefix mismatch')
        objective=direct_tail_cost(s,0,physical[-1],controls) if complete else None
        if attempt['completed_objective']!=objective or attempt['running_cost_prefix']!=running_prefix(s,controls):raise ValueError('executed objective mismatch')
        witness=canonical_hash({'scenario_sha256':canonical_hash(s),'controls':controls,'physical_states':physical.tolist(),'variant':attempt['variant']})
        if witness!=attempt['witness_sha256'] or canonical_hash(controls)!=attempt['controls_sha256']:raise ValueError('executed witness association')
        control_violation=[]
        if count:
            u=np.asarray(controls);cb=np.asarray([v['physical_bounds'] for v in s['controls']])
            if u.shape!=(count,len(s['controls'])) or not np.isfinite(u).all():raise ValueError('executed control dimensions/nonfinite')
            control_violation=np.maximum(np.maximum(cb[:,0]-u,u-cb[:,1]),0).max(axis=0).tolist()
            if max(control_violation)>1e-10:raise ValueError('applied input violates physical bounds')
        previous=None;previous_id=None;max_objective_difference=0.;max_constraint_difference=0.;max_stationarity_difference=0.
        for j,entry in enumerate(attempt['updates']):
            folder_j=folder/f'update-{j:03d}';r=load(folder_j/'result.json');binding=dict(r);digest=binding.pop('solve_sha256')
            if canonical_hash(binding)!=digest or entry['solve_sha256']!=digest:raise ValueError('solve record identity')
            observation=scaled[j*sub]
            mpc,meta=build_controller(s,j);guess=initialize_guess(mpc,s,j,observation,previous);guess['source_solve_sha256']=previous_id
            if guess!=r['guess'] or guess!=load(folder_j/'guess.json'):raise ValueError('primal warm-start/observation mismatch')
            if r['source_solve_id']!=(None if j==0 else j-1) or r['observation_scaled']!=observation.tolist():raise ValueError('solve observation/source mismatch')
            for key in ['original_interval_count','remaining_horizon','update_index','absolute_initial_time','fixed_terminal_time','running_cost_semantics',
                        'nlp_objective_expression','nlp_variable_labels','constraint_lower','constraint_upper','variable_lower','variable_upper']:
                if r[key]!=meta[key]:raise ValueError('transcription rebuild mismatch: '+key)
            if r['parameters']!=vector(mpc.opt_p_num).tolist():raise ValueError('absolute schedule/initial parameter mismatch')
            primal=np.asarray(r['primal']);pnum=mpc.opt_p_num
            f=float(meta['objective_function'](primal,pnum));g=vector(meta['constraint_function'](primal,pnum))
            if not np.isfinite(primal).all() or not np.isfinite(g).all():raise ValueError('nonfinite NLP witness')
            error=abs(f-r['objective']);max_objective_difference=max(max_objective_difference,error)
            constraint_error=float(np.max(np.abs(g-r['constraint_values'])));max_constraint_difference=max(max_constraint_difference,constraint_error)
            if error>1e-10 or constraint_error>1e-10:raise ValueError('saved NLP value differs from rebuild')
            mpc.opt_x_num.master=ca.DM(primal);prediction=mpc.opt_x_num;h=n-j
            predicted_controls=[vector(prediction['_u',k,0,'u']).tolist() for k in range(h)]
            mesh=[vector(prediction['_x',k,0,-1,'z']).tolist() for k in range(h+1)]
            if predicted_controls!=r['predicted_controls'] or mesh!=r['predicted_mesh_scaled'] or (np.asarray(mesh)*scales).tolist()!=r['predicted_mesh_physical']:raise ValueError('prediction extraction mismatch')
            direct=direct_tail_cost(s,j,np.asarray(mesh[-1])*scales,predicted_controls)
            if direct!=r['objective_recomputed'] or abs(direct-f)>1e-8:raise ValueError('original-N direct stage objective mismatch')
            lo=np.array(meta['variable_lower']);hi=np.array(meta['variable_upper']);gl=np.array(meta['constraint_lower']);gu=np.array(meta['constraint_upper'])
            violation=float(max(np.max(np.maximum(lo-primal,0)),np.max(np.maximum(primal-hi,0)),np.max(np.maximum(gl-g,0)),np.max(np.maximum(g-gu,0))))
            if abs(violation-r['max_scaled_primal_violation'])>1e-10:raise ValueError('primal diagnostic mismatch')
            nodes=np.asarray([vector(prediction['_x',k,0,c,'z']) for k in range(h+1) for c in range(len(prediction['_x',k,0]))])*scales
            state_bounds=np.array([v['physical_bounds'] for v in s['states']])
            node_violation=np.maximum(np.maximum(state_bounds[:,0]-nodes,nodes-state_bounds[:,1]),0).max(axis=0).tolist()
            if node_violation!=r['optimization_node_max_physical_state_violation']:raise ValueError('optimization-node physical violations mismatch')
            grad,jac=meta['stationarity_function'](primal,pnum)
            stationarity=float(np.max(np.abs(vector(grad)+np.array(jac).T@np.array(r['dual_g'])+np.array(r['dual_x']))))
            stat_error=abs(stationarity-r['local_stationarity_infinity_norm']);max_stationarity_difference=max(max_stationarity_difference,stat_error)
            if stat_error>1e-10:raise ValueError('local stationarity diagnostic mismatch')
            expected_accepted=bool(r['success'] and np.isfinite(f) and violation<=1e-6 and abs(direct-f)<=1e-8)
            if r['accepted']!=expected_accepted or entry['accepted']!=r['accepted']:raise ValueError('local solve acceptance mismatch')
            if j<count and (not r['accepted'] or controls[j]!=predicted_controls[0]):raise ValueError('execution did not apply accepted first input')
            if not r['accepted'] and j!=len(attempt['updates'])-1:raise ValueError('continued after failed solve')
            previous=prediction;previous_id=digest
        bounds=np.array([v['physical_bounds'] for v in s['states']]);state_violation=np.maximum(np.maximum(bounds[:,0]-physical,physical-bounds[:,1]),0).max(axis=0).tolist()
        replay_records={}
        for mode in ['rk4','rk4-tight']:
            if not count:continue
            target=folder/mode;request=load(target/'request.json');prefix=copy.deepcopy(s);prefix['time']['intervals']=count;prefix['time']['grid']=s['time']['grid'][:count+1];prefix['time']['final']=prefix['time']['grid'][-1]
            expected=make_request(prefix,controls,witness,sensitivity=mode.endswith('tight'));expected['full_scenario_sha256']=canonical_hash(s);expected['full_original_interval_count']=n
            if request!=expected:raise ValueError('independent replay prefix association')
            raw=load(target/'stdout.json');record=load(target/'record.json')
            for key,value in raw.items():
                if record[key]!=value:raise ValueError('replay structured record differs from raw')
            if record['witness_sha256']!=witness or record['controls_sha256']!=canonical_hash(controls) or record['full_scenario_sha256']!=canonical_hash(s) or record['full_original_interval_count']!=n:raise ValueError('replay identity mismatch')
            rs=np.asarray(record['physical_states']);zs=np.asarray(record['scaled_states'])
            if rs.ndim!=2 or rs.shape[1]!=len(scales) or zs.shape!=rs.shape or not np.isfinite(rs).all():raise ValueError('replay dimensions/nonfinite')
            if (record['status']=='complete')!=(len(rs)==count*sub+1):raise ValueError('replay status/prefix inconsistency')
            if not np.array_equal(zs*scales,rs) or record['times']!=request['times'][:len(rs)] or len(rs)==0 or zs[0].tolist()!=initial.tolist():raise ValueError('replay physical/prefix transform')
            rcost=direct_tail_cost(s,0,rs[-1],controls) if complete and record['status']=='complete' else None
            if record['completed_objective']!=rcost or record['running_cost_prefix']!=running_prefix(s,controls):raise ValueError('independent replay original objective mismatch')
            v=np.maximum(np.maximum(bounds[:,0]-rs,rs-bounds[:,1]),0).max(axis=0).tolist()
            if record['sampled_physical_state_violation']!=v:raise ValueError('replay sampled constraint mismatch')
            replay_records[mode]=record
        summary=load(folder/'replay-summary.json') if count else None
        if count:
            for mode,r in replay_records.items():
                expected={'status':r['status'],'completed_objective':r['completed_objective'],'max_physical_execution_difference':np.max(np.abs(np.asarray(r['physical_states'])-physical),axis=0).tolist() if len(r['physical_states'])==len(physical) else None}
                if summary[mode]!=expected:raise ValueError('replay/execution comparison mismatch')
            if all(r['status']=='complete' for r in replay_records.values()):
                difference=np.max(np.abs(np.array(replay_records['rk4']['physical_states'])-replay_records['rk4-tight']['physical_states']),axis=0).tolist()
                if summary['max_physical_tolerance_sensitivity']!=difference:raise ValueError('replay sensitivity mismatch')
        reports.append({'case_id':s['case_id'],'status':attempt['status'],'completed_holds':count,'completed_objective':objective,'sampled_execution_physical_state_violation':state_violation,'applied_physical_control_violation':control_violation,
                        'max_nlp_objective_rebuild_difference':max_objective_difference,'max_nlp_constraint_rebuild_difference':max_constraint_difference,'max_stationarity_rebuild_difference':max_stationarity_difference,
                        'claim':'saved transcript/controls/cost/replay association and NLP rebuild; no solver rerun, global guarantee or ODE error certificate'})
    return reports

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True)
    print(json.dumps(check(parser.parse_args().bundle.resolve()),indent=2))

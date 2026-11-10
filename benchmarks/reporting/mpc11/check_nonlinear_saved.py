#!/usr/bin/env python3
"""Validate source affine witnesses, nonlinear trace identities and sampled costs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from affine import canonical_hash, check_solution
from check_affine_saved import verify_authored_transform, matches_rebuild
from check_scenarios import validate
from nonlinear import make_request, validate_request, evaluate
from replay_evidence import read_native_attempt


def check(bundle):
    hashes=json.loads((bundle/'file-hashes.json').read_text())
    for name,digest in hashes.items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('saved file identity mismatch: '+name)
    manifest=json.loads((bundle/'manifest.json').read_text());comparisons=[]
    reports=[]
    for case in ['syn-nl-lv-01','syn-nl-fuel-01']:
        folder=bundle/case;source=folder/'source'
        load=lambda path:json.loads(path.read_text())
        s=load(source/'scenario.json');validate(s);coeff=load(source/'model.json');qp=load(source/'program.json');native=load(source/'stdout.json')
        verify_authored_transform(s,coeff,qp,source)
        if native['program_sha256']!=qp['program_sha256']:raise ValueError('native program association')
        witness=check_solution(s,coeff,qp,native)
        saved_witness=load(folder/'affine-witness.json')
        if witness['status']!='verified-numerical-witness' or not matches_rebuild(saved_witness,witness):
            raise ValueError('affine witness differs from source verification')
        witness=saved_witness
        statuses={};objectives={};records={}
        for mode in ['cvodes','cvodes-tight','rk4','rk4-tight']:
            attempt=folder/mode;request=load(attempt/'request.json');validate_request(request)
            expected=make_request(s,witness['physical_controls'],witness['witness_sha256'],sensitivity=mode.endswith('-tight'))
            if request!=expected:raise ValueError('request differs from verified affine witness')
            receipt=load(attempt/'process.json')
            record=read_native_attempt(attempt,receipt,status_key='process_status',time_key='whole_process_seconds',
                extensions={'objective','sampled_state_violation_physical','control_violation_physical'} if mode.startswith('rk4') else set(),
                method='rk4' if mode.startswith('rk4') else 'cvodes',wall_seconds=manifest['limits']['wall_seconds'])
            if record is None:
                statuses[mode]='process-incomplete';objectives[mode]=None;continue
            for key in ['scenario_sha256','witness_sha256','controls_sha256','abstol','reltol']:
                if record[key]!=request[key]:raise ValueError('trace association mismatch: '+key)
            states=np.asarray(record['scaled_states']);physical=np.asarray(record['physical_states']);scales=np.array([v['scale'] for v in s['states']])
            if states.ndim!=2 or states.shape!=physical.shape or states.shape[1]!=len(scales) or not np.isfinite(states).all():raise ValueError('trace dimensions/nonfinite')
            if not np.array_equal(states*scales,physical):raise ValueError('scaled physical transform mismatch')
            if record['times']!=request['times'][:len(states)]:raise ValueError('trace prefix times mismatch')
            if len(states)==0 or states[0].tolist()!=request['initial_scaled']:raise ValueError('initial state mismatch')
            complete=record['status']=='complete'
            if complete!=(len(states)==len(request['times'])):raise ValueError('status and prefix disagree')
            metrics=evaluate(s,physical,witness['physical_controls'])
            if not complete:metrics['objective']=None
            for key,value in metrics.items():
                if not matches_rebuild(record[key],value):raise ValueError('independent cost/violation reconstruction mismatch: '+key)
            statuses[mode]=record['status'];objectives[mode]=record['objective'];records[mode]=record
        comparison=load(folder/'comparison.json')
        if comparison['statuses']!=statuses or comparison['objectives']!=objectives or comparison['affine_objective']!=witness['objective']:
            raise ValueError('comparison differs from checked records')
        for key,value in [('case_id',s['case_id']),('witness_sha256',witness['witness_sha256']),
                          ('controls_sha256',canonical_hash(witness['physical_controls']))]:
            if comparison[key]!=value:raise ValueError('comparison identity mismatch: '+key)
        difference_keys=['max_physical_cvodes_sensitivity','max_physical_cvodes_rk4_difference',
                         'max_physical_rk4_sensitivity','max_physical_affine_prediction_nonlinear_difference']
        if all(status=='complete' for status in statuses.values()):
            cv=np.asarray(records['cvodes']['physical_states']);rk=np.asarray(records['rk4']['physical_states'])
            cv_tight=np.asarray(records['cvodes-tight']['physical_states']);rk_tight=np.asarray(records['rk4-tight']['physical_states'])
            computed=[np.max(np.abs(cv_tight-cv),axis=0).tolist(),np.max(np.abs(cv-rk),axis=0).tolist(),
                      np.max(np.abs(rk_tight-rk),axis=0).tolist(),
                      np.max(np.abs(cv[::s['independent_replay']['report_subintervals_per_hold']]-witness['physical_states']),axis=0).tolist()]
            for key,value in zip(difference_keys,computed):
                if comparison[key]!=value:raise ValueError('comparison difference reconstruction mismatch: '+key)
        elif any(key in comparison for key in difference_keys):
            raise ValueError('incomplete comparison declares complete-trace differences')
        comparisons.append(comparison)
        reports.append({'case_id':s['case_id'],'statuses':statuses,'process_statuses':{mode:load(folder/mode/'process.json')['process_status'] for mode in statuses},'scope':'bound identities, source rebuild, sampled trace shape/cost/constraints; integration correctness requires replay'})
    if manifest['cases']!=comparisons:raise ValueError('manifest comparisons differ from checked case records')
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    print(json.dumps(check(p.parse_args().bundle.resolve()),indent=2))

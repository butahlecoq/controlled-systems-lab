#!/usr/bin/env python3
"""Validate source affine witnesses, nonlinear trace identities and sampled costs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from affine import canonical_hash, check_solution
from check_affine_saved import verify_authored_transform
from check_scenarios import validate
from nonlinear import make_request, validate_request, evaluate


def check(bundle):
    hashes=json.loads((bundle/'file-hashes.json').read_text())
    for name,digest in hashes.items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('saved file identity mismatch: '+name)
    reports=[]
    for case in ['syn-nl-lv-01','syn-nl-fuel-01']:
        folder=bundle/case;source=folder/'source'
        load=lambda path:json.loads(path.read_text())
        s=load(source/'scenario.json');validate(s);coeff=load(source/'model.json');qp=load(source/'program.json');native=load(source/'stdout.json')
        verify_authored_transform(s,coeff,qp,source)
        if native['program_sha256']!=qp['program_sha256']:raise ValueError('native program association')
        witness=check_solution(s,coeff,qp,native)
        if witness['status']!='verified-numerical-witness' or witness!=load(folder/'affine-witness.json'):
            raise ValueError('affine witness differs from source verification')
        statuses={};objectives={}
        for mode in ['cvodes','cvodes-tight','rk4','rk4-tight']:
            attempt=folder/mode;request=load(attempt/'request.json');validate_request(request)
            expected=make_request(s,witness['physical_controls'],witness['witness_sha256'],sensitivity=mode.endswith('-tight'))
            if request!=expected:raise ValueError('request differs from verified affine witness')
            receipt=load(attempt/'process.json')
            if receipt['process_status']!='completed':
                statuses[mode]=receipt['process_status'];objectives[mode]=None;continue
            for name,key in [('stdout.json','stdout_sha256'),('stderr.txt','stderr_sha256')]:
                if hashlib.sha256((attempt/name).read_bytes()).hexdigest()!=receipt[key]:raise ValueError('process receipt hash mismatch')
            record=load(attempt/'record.json');raw=load(attempt/'stdout.json')
            for key in raw:
                if key in ['objective','sampled_state_violation_physical','control_violation_physical'] and mode.startswith('rk4'):continue
                if raw[key]!=record[key]:raise ValueError('structured record differs from native stdout: '+key)
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
                if value!=record[key]:raise ValueError('independent cost/violation reconstruction mismatch: '+key)
            statuses[mode]=record['status'];objectives[mode]=record['objective']
        comparison=load(folder/'comparison.json')
        if comparison['statuses']!=statuses or comparison['objectives']!=objectives or comparison['affine_objective']!=witness['objective']:
            raise ValueError('comparison differs from checked records')
        reports.append({'case_id':s['case_id'],'statuses':statuses,'scope':'bound identities, source rebuild, sampled trace shape/cost/constraints; integration correctness requires replay'})
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    print(json.dumps(check(p.parse_args().bundle.resolve()),indent=2))

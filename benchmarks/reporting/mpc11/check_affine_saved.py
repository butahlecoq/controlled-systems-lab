#!/usr/bin/env python3
"""Recheck saved CSL affine witnesses and their bound input/output identities."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from affine import canonical_hash, check_solution, model, program, condense_program, permute_program, scale_objective
from run_affine import tiny_program
from check_scenarios import validate



# These tolerances apply only to an independently recomputed floating derivation.
# Stored files, submitted-program identities and immutable archives remain exact.
REBUILD_ATOL = 1e-13
REBUILD_RTOL = 1e-12


def matches_rebuild(saved, rebuilt):
    if isinstance(rebuilt, dict):
        return isinstance(saved, dict) and saved.keys()==rebuilt.keys() and all(
            matches_rebuild(saved[key],value) for key,value in rebuilt.items())
    if isinstance(rebuilt, list):
        return isinstance(saved, list) and len(saved)==len(rebuilt) and all(
            matches_rebuild(a,b) for a,b in zip(saved,rebuilt))
    if isinstance(rebuilt, float):
        return isinstance(saved,(int,float)) and not isinstance(saved,bool) and math.isfinite(saved) and math.isfinite(rebuilt) and math.isclose(
            saved,rebuilt,abs_tol=REBUILD_ATOL,rel_tol=REBUILD_RTOL)
    return type(saved) is type(rebuilt) and saved==rebuilt


def matches_program_rebuild(saved, rebuilt):
    return matches_rebuild({key:value for key,value in saved.items() if key!='program_sha256'},
                           {key:value for key,value in rebuilt.items() if key!='program_sha256'})


def verify_authored_transform(scenario, coefficients, qp, folder):
    # Rebuild from the fixed authored scenario, not the caller's rebound hashes.
    rebuilt_model=model(scenario)
    if not matches_rebuild(coefficients,rebuilt_model):
        raise ValueError('saved affine model differs from authored model rebuild')
    expected=program(scenario,coefficients)
    if 'joint_reconstruction' in qp:
        original=json.loads((folder/'joint-program.json').read_text())
        if not matches_program_rebuild(original,expected):
            raise ValueError('retained joint program differs from authored rebuild')
        expected=condense_program(scenario,coefficients,original)
    elif 'joint_indices' in qp.get('coordinates',{}):
        original=json.loads((folder/'joint-program.json').read_text())
        if not matches_program_rebuild(original,expected):
            raise ValueError('retained joint program differs from authored rebuild')
        n=len(scenario['states'])*(scenario['time']['intervals']+1)
        expected=permute_program(original,[*range(n,len(expected['variables'])),*range(n)])
    if 'source_unscaled_program_sha256' in qp:
        unscaled=json.loads((folder/'unscaled-program.json').read_text())
        if not matches_program_rebuild(unscaled,expected):
            raise ValueError('unscaled source differs from authored program/transform rebuild')
        expected=scale_objective(unscaled,qp['objective_multiplier'])
    if not matches_program_rebuild(qp,expected):
        raise ValueError('submitted program differs from authored coefficient/bound/transform rebuild')


def check(bundle):
    manifest=json.loads((bundle/'manifest.json').read_text())
    reports=[]
    for attempt in manifest['attempts']:
        folder=bundle/attempt['case_id'].lower()
        if attempt['process_status']!='completed' or attempt['return_code']!=0:
            reports.append({'case_id':attempt['case_id'],'status':'unavailable','reason':attempt['process_status']})
            continue
        for name,key in [('program.json','program_file_sha256'),('stdout.json','stdout_sha256'),('stderr.txt','stderr_sha256')]:
            if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=attempt[key]:
                raise ValueError(f'hash mismatch: {name}')
        qp=json.loads((folder/'program.json').read_text());authored=dict(qp);authored.pop('program_sha256')
        if canonical_hash(authored)!=qp['program_sha256'] or qp['program_sha256']!=attempt['program_sha256']:
            raise ValueError('program identity mismatch')
        if 'source_unscaled_program_sha256' in qp:
            unscaled=json.loads((folder/'unscaled-program.json').read_text());unscaled_hash=unscaled.pop('program_sha256')
            if canonical_hash(unscaled)!=unscaled_hash or unscaled_hash!=qp['source_unscaled_program_sha256']:
                raise ValueError('unscaled program identity mismatch')
        if 'source_joint_program_sha256' in qp:
            original=json.loads((folder/'joint-program.json').read_text()); original_hash=original.pop('program_sha256')
            if canonical_hash(original)!=original_hash or original_hash!=qp['source_joint_program_sha256']:
                raise ValueError('original joint-program identity mismatch')
        result=json.loads((folder/'stdout.json').read_text())
        if result.get('program_sha256')!=qp['program_sha256'] or result.get('case_id')!=attempt['case_id']:
            raise ValueError('result identity mismatch')
        if attempt['case_id']=='ANALYTIC-JOINT-QP-01':
            if canonical_hash(qp)!=canonical_hash(tiny_program()):
                raise ValueError('tiny analytic program differs from literal fixture')
            primal=result.get('primal',[])
            if result.get('termination')!='completed' or result.get('mathematical_outcome')!='optimal' or result.get('contract_diagnostics'):
                raise ValueError('tiny native result did not complete cleanly')
            if len(primal)!=3 or max(abs(a-b) for a,b in zip(primal,[0,1,1]))>1e-6:
                raise ValueError('tiny analytic oracle failed')
            reports.append({'case_id':attempt['case_id'],'status':'verified-numerical-witness'})
        else:
            scenario=json.loads((folder/'scenario.json').read_text());validate(scenario)
            coefficients=json.loads((folder/'model.json').read_text())
            if canonical_hash(scenario)!=qp['scenario_sha256'] or canonical_hash(coefficients)!=qp['model_sha256']:
                raise ValueError('scenario/model identity mismatch')
            verify_authored_transform(scenario,coefficients,qp,folder)
            report=check_solution(scenario,coefficients,qp,result)
            reports.append({'case_id':attempt['case_id'],'status':report['status'],
                            'objective':report.get('objective')})
    return reports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',required=True,type=Path)
    reports=check(parser.parse_args().bundle)
    print(json.dumps(reports,indent=2))
    raise SystemExit(0 if all(r['status']=='verified-numerical-witness' for r in reports) else 1)

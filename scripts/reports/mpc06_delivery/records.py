"""Build and independently validate the exact-reference delivery record."""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.reports.mpc06_delivery import reference
from scripts.reports.mpc06_online import evidence,model

UPSTREAM=ROOT/'reports/algorithm-results/mpc06-online-anchor-portable-v3'
REVIEWED_UPSTREAM_MANIFEST_SHA256='8edb28e2744b1b061a47971e5f0613c30be64e7c25727c70bd1ec52d4244034a'
SOURCE_FILES=('scripts/reports/mpc06_delivery/reference.py','scripts/reports/mpc06_delivery/records.py',
              'scripts/reports/mpc06_delivery/figures.py','scripts/reports/figure_style.py','scripts/reports/plot.py','scripts/reports/report_data.py','scripts/reports/requirements.txt',
              'scripts/reports/mpc06_online/evidence.py','scripts/reports/mpc06_online/model.py')


def encode(value):
    if isinstance(value,Q):return str(value)
    raise TypeError(type(value).__name__)


def plain(value):return json.loads(json.dumps(value,default=encode))


def inventory(source):
    contents=evidence.files(source);actual={name:evidence.digest(data) for name,data in contents.items() if name!='SHA256SUMS'}
    expected={}
    for line in contents['SHA256SUMS'].decode().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not match or match[2] in expected:raise ValueError('invalid delivery checksum list')
        expected[match[2]]=match[1]
    if expected!=actual:raise ValueError('delivery checksum inventory mismatch')
    return contents


def upstream(source):
    contents=inventory(source)
    if evidence.digest(contents['SHA256SUMS'])!=REVIEWED_UPSTREAM_MANIFEST_SHA256:
        raise ValueError('upstream differs from the independently reviewed immutable capture')
    record,receipt=evidence.checked_sources(source/'checked-inputs/mpc06-online-anchor-v1',source/'verification-v2.json')
    if receipt['verification']['status']!='verified' or receipt['verification']['completed_native_qps']!=180:
        raise ValueError('upstream online study is not the reviewed completed capture')
    return record,{name:evidence.digest(data) for name,data in contents.items()}


def geometry(record):
    r=Q(1,8)
    return dict(exact_Z_vertices=[[-r,0],[-r,2*r],[r,0],[r,-2*r]],
        original_X=[[-1,1],[-1,1]],original_U=[-1,1],
        tightened_state_halfwidths={kind:list(model.tightenings(kind)[0][:2]) for kind in ('polytope','inflated-zonotope','ellipsoid-certified')},
        native_APP04=record['processes'][0]['approximation'],
        scope='analytical invariant/tightening illustration from the bound stored model; not replayed algorithm steps')


def cases(record):
    initials=[]
    for attempt in record['attempts']:
        if attempt['status']=='completed' and attempt['initial'] not in initials:initials.append(attempt['initial'])
    return initials


def held_plan(initial,a):
    paths=[]
    for disturbances in reference.product((-reference.R,reference.R),repeat=3):
        row=reference.trajectory(initial,a,(-1,-2),disturbances)
        paths.append(dict(disturbances=disturbances,**row))
    if not all(path['safe'] for path in paths):raise ValueError('held native predicted plan is not robustly feasible')
    return dict(a=a,nominal_controls=paths[0]['nominal_controls'],paths=paths,
                worst_cost=max(path['cost'] for path in paths))


def make_record(online,upstream_files):
    result=dict(schema='csl.mpc06-delivery/1',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        source_files={name:evidence.digest((ROOT/name).read_bytes()) for name in SOURCE_FILES},
        upstream_files=upstream_files,upstream_report_id=UPSTREAM.name,native_source_commit=online['source_commit'],
        geometry=geometry(online),cases=[],
        scopes=dict(M0='fixed open-loop actual controls; nominal terminal z3=0',
            fixed_K='frozen nominal sequence, u=v+K(x-z); nominal terminal z3=0',
            held_native='first native N3 predicted plan held for three steps, matched to fixed_K reference',
            receding_native='three executed receding steps; distinct prefix/tail and terminal semantics',
            comparison='no bound ordering between M0 and fixed_K policy classes; no general causal optimum'),
        costs=dict(offline_gain='prescribed K; no gain optimization',
            offline_Z_terminal='exact nilpotent construction and nominal terminal {0}; previous pilot composite cost retained separately; standalone timings unavailable',
            offline_enclosure='actual saved APP-04 construction_ns',online='actual saved prepare_ns/setup_ns/solve_ns',
            checker='saved independent exact replay intervals; construction/checking are not native solve time'),
        limitations=['finite N3 reference only','same fixed full-state gains and independent continuous disturbance box',
            'finite initial feasibility grid is not a full feedback-winning set','native receding-prefix surrogate is not minimax',
            'no universal performance winner, hard real-time or general memory guarantee'])
    for initial_text in cases(online):
        initial=tuple(map(Q,initial_text));references=[reference.solve(initial,gain) for gain in reference.GAINS]
        k_value=references[1]['worst_cost'];held=[];receding=[]
        for attempt in online['attempts']:
            if attempt['status']!='completed' or attempt['initial']!=initial_text:continue
            first=attempt['steps'][0]['native'];a=Q(first['a']);value=held_plan(initial,a)
            held.append(dict(repetition=attempt['repetition'],method=attempt['method'],program=first['program'],
                **value,fixed_K_minimax_gap=value['worst_cost']-k_value))
            receding.append(dict(repetition=attempt['repetition'],method=attempt['method'],
                worst_cost=Q(attempt['actual']['worst']),scope='actual receding prefix; not matched to frozen-plan terminal constraint'))
        result['cases'].append(dict(initial=initial,references=references,held_first_native_plans=held,actual_receding_prefix_costs=receding))
    return result


def check(record,online,upstream_files,source_files=None):
    if not re.fullmatch('[0-9a-f]{40}',record['source_commit']):raise ValueError('invalid reference source commit')
    if record['schema']!='csl.mpc06-delivery/1' or record['source_status'] or record['upstream_report_id']!=UPSTREAM.name:
        raise ValueError('delivery scope/source mismatch')
    if record['upstream_files']!=upstream_files or record['native_source_commit']!=online['source_commit']:
        raise ValueError('delivery upstream source binding mismatch')
    expected_source_files=({name:evidence.digest((ROOT/name).read_bytes()) for name in SOURCE_FILES}
                           if source_files is None else source_files)
    if record['source_files']!=expected_source_files:
        raise ValueError('delivery reviewing source binding mismatch')
    if record['geometry']!=plain(geometry(online)):raise ValueError('geometry source binding mismatch')
    if record['scopes']['comparison']!='no bound ordering between M0 and fixed_K policy classes; no general causal optimum':raise ValueError('reference policy comparison scope changed')
    if [case['initial'] for case in record['cases']]!=cases(online):raise ValueError('initial-state case binding mismatch')
    reference_count=0;held_count=0
    for case in record['cases']:
        initial=tuple(map(Q,case['initial']))
        if [tuple(row['gain']) for row in case['references']]!=list(reference.GAINS):raise ValueError('reference policy classes changed')
        for value in case['references']:
            decoded=reference.decode(value)
            if decoded['initial']!=initial:raise ValueError('reference initial binding mismatch')
            reference.check(decoded);reference_count+=1
        k_value=Q(case['references'][1]['worst_cost']);expected_held=[];expected_receding=[]
        for attempt in online['attempts']:
            if attempt['status']!='completed' or attempt['initial']!=case['initial']:continue
            first=attempt['steps'][0]['native'];value=held_plan(initial,Q(first['a']))
            gap=value['worst_cost']-k_value
            if gap<0:raise ValueError('held-plan cost contradicts exact matched minimax lower bound')
            expected_held.append(dict(repetition=attempt['repetition'],method=attempt['method'],program=first['program'],
                **value,fixed_K_minimax_gap=gap))
            expected_receding.append(dict(repetition=attempt['repetition'],method=attempt['method'],
                worst_cost=Q(attempt['actual']['worst']),scope='actual receding prefix; not matched to frozen-plan terminal constraint'))
        if case['held_first_native_plans']!=plain(expected_held) or case['actual_receding_prefix_costs']!=plain(expected_receding):
            raise ValueError('native held-plan/receding-prefix extraction mismatch')
        held_count+=len(expected_held)
    return dict(schema='csl.mpc06-delivery-check/1',status='verified',
        result_sha256=evidence.digest(json.dumps(record,sort_keys=True,separators=(',',':')).encode()),exact_reference_cases=reference_count,
        held_native_plans=held_count,scope='exact frozen-plan class minima and matched held-native-plan gaps; receding-prefix cost remains separate')


def validate(source):
    contents=inventory(source);online,upstream_files=upstream(source/'online')
    record=evidence.json_value(contents['result.json'])
    costs=evidence.json_value(contents['cost-receipt.json'])
    if costs.get('schema')!='csl.mpc06-reference-costs/1' or costs.get('clock')!='time.monotonic_ns':
        raise ValueError('invalid exact-reference cost receipt')
    for key in ('construction_and_extraction_ns','independent_check_ns'):
        if type(costs.get(key)) is not int or costs[key]<0:raise ValueError('invalid exact-reference cost interval')
    captured_sources={}
    for name in SOURCE_FILES:
        copied='source/'+Path(name).name
        if copied not in contents or evidence.digest(contents[copied])!=record['source_files'].get(name):
            raise ValueError('delivery copied source binding mismatch: '+name)
        captured_sources[name]=evidence.digest(contents[copied])
    verification=check(record,online,upstream_files,captured_sources)
    if evidence.json_value(contents['verification.json'])!=verification:raise ValueError('delivery saved verification disposition mismatch')
    return record,online,verification,contents


def build(source,out):
    if out.exists():raise ValueError('delivery source must be new')
    online,upstream_files=upstream(source)
    begin=time.monotonic_ns();record=plain(make_record(online,upstream_files));constructed=time.monotonic_ns()
    verification=check(record,online,upstream_files);checked=time.monotonic_ns()
    costs=dict(schema='csl.mpc06-reference-costs/1',clock='time.monotonic_ns',
        construction_and_extraction_ns=constructed-begin,independent_check_ns=checked-constructed,
        scope='one descriptive Python exact-reference construction plus geometry/native-history extraction and independent check; upstream loading excluded; no timing ranking')
    out.mkdir(parents=True);shutil.copytree(source,out/'online');(out/'source').mkdir()
    for name in SOURCE_FILES:(out/'source'/Path(name).name).write_bytes((ROOT/name).read_bytes())
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    (out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    (out/'cost-receipt.json').write_text(json.dumps(costs,indent=2)+'\n',encoding='utf-8')
    paths=sorted(path for path in out.rglob('*') if path.is_file())
    (out/'SHA256SUMS').write_text(''.join(f'{evidence.digest(path.read_bytes())}  {path.relative_to(out).as_posix()}\n' for path in paths),encoding='utf-8')
    return verification


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path);parser.add_argument('--source',type=Path,default=UPSTREAM);parser.add_argument('--check',type=Path)
    args=parser.parse_args()
    if args.build:print(json.dumps(build(args.source,args.build)))
    elif args.check:print(json.dumps(validate(args.check)[2]))
    else:parser.error('--build or --check is required')

#!/usr/bin/env python3
"""Recheck saved MPC-06 native controls, matched references and worst costs."""
import argparse
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import time
from model import problem,optimizer,value,tightenings,replay,representation_checks
from study import exact_approximation_check,encode


def plain(value):return json.loads(json.dumps(value,default=encode))


def verify(record):
    begin=time.perf_counter_ns();count=0;program_index={}
    if record['schema']!='csl.mpc06-online-study/1' or record['policy']['kind']!='propagated-anchor':
        raise ValueError('unsupported schema or disturbance-dependent policy')
    if record['plant']['A']!=[[1,1],[0,1]] or record['plant']['B']!=[[0],[1]] or record['plant']['E']!=[[0],[1]] or record['plant']['W']!=['-1/8','1/8'] or record['plant']['X']!=[[-1,1],[-1,1]] or record['plant']['U']!=[-1,1]:raise ValueError('unsupported plant or uncertainty')
    if record['policy']['gain']!=[-1,-2] or record['policy']['terminal']!='z3=0':raise ValueError('policy mismatch')
    if record['representations']!=representation_checks():raise ValueError('representation evidence changed')
    for row in record['grid']['rows']:
        qp=problem(tuple(map(Q,row['anchor'])),tightenings(row['method']))
        if row['qp']!=plain(qp):raise ValueError('exact matched feasible interval changed')
        expected=plain(value(qp,optimizer(qp))) if qp['feasible'] else None
        if row['nominal_optimum']!=expected:raise ValueError('exact nominal optimum changed')
    for process in record['processes']:
        if process.get('status')=='inconclusive':continue
        checked=exact_approximation_check(process['approximation'])
        for key in ('status','enclosure','rpi','decision','counterexample'):
            if process['independent_approximation'][key]!=plain(checked[key]):raise ValueError('APP-04 check changed')
        if process['returncode']!=0:raise ValueError('completed process returned failure')
    for attempt in record['attempts']:
        if attempt['status']!='completed':continue
        initial=tuple(map(Q,attempt['initial']));anchor=initial;controls=[]
        if len(attempt['steps'])!=3:raise ValueError('completed controller omitted online steps')
        for stage,row in enumerate(attempt['steps']):
            if row['stage']!=stage or row['anchor']!=plain(anchor):raise ValueError('anchor was reset or stage changed')
            qp=problem(anchor,tightenings(attempt['method'],stage))
            if row['qp']!=plain(qp) or not qp['feasible']:raise ValueError('native QP has wrong tightened/terminal constraints')
            expected=' '.join(format(float(qp[k]),'.17g') for k in ('quadratic','linear','offset','lower','upper'))+'\n'
            if row['native_input']!=expected:raise ValueError('native input differs from independently derived QP')
            native=row['native'];a=Q(native['a'])
            index=program_index.get(attempt['repetition'],0)
            if native['schema']!='csl.mpc06-online-qp/1' or native['program']!='nominal-qp/'+str(index) or native['requested_threads']!=1:raise ValueError('native request/program binding mismatch')
            program_index[attempt['repetition']]=index+1
            if native['status']!='completed' or native['backend']!='csl.convex.highs':raise ValueError('missing native QP completion')
            if not qp['lower']<=a<=qp['upper'] or abs(a-optimizer(qp))>Q(1,1000000):raise ValueError('unsafe or wrong native optimum')
            if abs(Q(native['objective'])-value(qp,a))>Q(1,1000000):raise ValueError('wrong original native objective')
            controls.append(a);anchor=(anchor[0]+anchor[1],anchor[1]+a);count+=1
        if attempt['nominal_controls']!=plain(controls):raise ValueError('native nominal history binding changed')
        expected=replay(initial,controls)
        if attempt['actual']!=plain(expected):raise ValueError('actual cost/witness replay changed')
        if not all(row['safe'] for row in expected['paths']):raise ValueError('unsafe actual path')
    return dict(status='verified' if all(p.get('status')!='inconclusive' for p in record['processes']) else 'inconclusive',
                completed_native_qps=count,checker_ns=time.perf_counter_ns()-begin,
                scope='exact saved dyadic safety and continuous-box worst cost for deterministic anchored nominal policy; numerical native optimum agreement only')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args()
    # Validate existing frozen bytes before adding this new checker receipt.
    for line in (args.bundle/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1)
        if hashlib.sha256((args.bundle/name).read_bytes()).hexdigest()!=digest:raise ValueError('saved bundle digest mismatch: '+name)
    result=verify(json.loads((args.bundle/'result.json').read_text()))
    receipt=args.bundle/'verification.json'
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        if any(saved[key]!=result[key] for key in ('status','completed_native_qps','scope')):raise ValueError('saved checker disposition changed')
    else:
        receipt.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()

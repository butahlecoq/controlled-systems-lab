#!/usr/bin/env python3
"""Exact rational checks for DIMENSION-01 emitted candidate relations."""
from __future__ import annotations
import argparse, hashlib, json
from fractions import Fraction
from pathlib import Path
CASES={'n1-t2':(1,2),'n1-t4':(1,4),'n2-t2':(2,2),'n2-t4':(2,4)}
STRATEGIES={'csl.synthesis.reach-back','csl.synthesis.strategy-b'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def q(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)): raise ValueError('H coefficients and bounds must be finite JSON numbers')
    return Fraction.from_float(float(v)) if isinstance(v,float) else Fraction(v)
def canon(row,equality=False):
    values=tuple(q(x) for x in row)
    if not any(values): raise ValueError('zero H row')
    scale=abs(next(x for x in values if x)); values=tuple(x/scale for x in values)
    if equality and next(x for x in values if x)<0: values=tuple(-x for x in values)
    return values
def row(width,terms,rhs=0):
    out=[0]*(width+1)
    for i,v in terms.items(): out[i]=v
    out[-1]=rhs
    return out
def required(n,t):
    width=n*(t+1)+n*t; eq=set(); le=set()
    state=lambda stage,coord: stage*n+coord
    control=lambda stage,coord: n*(t+1)+stage*n+coord
    for c in range(n): eq.add(canon(row(width,{state(0,c):1}),True))
    for k in range(t):
        for c in range(n):
            eq.add(canon(row(width,{state(k+1,c):1,state(k,c):-1,control(k,c):-1}),True))
            le.add(canon(row(width,{control(k,c):-1}),False))
            le.add(canon(row(width,{control(k,c):1},1),False))
    for k in range(t+1):
        for c in range(n):
            le.add(canon(row(width,{state(k,c):1},t),False))
            le.add(canon(row(width,{state(k,c):-1},t),False))
    return width,eq,le

def expected_fixture(n,t):
    identity=[[int(i==j) for j in range(n)] for i in range(n)]
    box={'kind':'box','lower':[-t]*n,'upper':[t]*n}
    return {'schema':'csl.scenario/1','id':f'review05-dimension01-n{n}-t{t}','horizon':t,
            'model':{'kind':'linear_discrete','A':identity,'B':identity},'initial_state':[0]*n,
            'controls':{'kind':'box','lower':[0]*n,'upper':[1]*n},
            'states':{'kind':'stages','values':[box for _ in range(t+1)]},
            'objective':{'kind':'linear','coefficients':[1]*n},
            'metadata':{'state_labels':[f'x{i+1}' for i in range(n)],'control_labels':[f'u{i+1}' for i in range(n)],
                        'state_units':['dimensionless']*n,'control_units':['dimensionless']*n}}

def check(attempt,expected_hash):
    try:
        n,t=CASES[attempt['case']]; result=attempt['result']
        if attempt.get('process_status')!='completed' or not isinstance(result,dict): return 'unavailable',['process did not complete']
        if result.get('schema')!='csl.review05.dimension-attempt/1' or result.get('fixture')!='DIMENSION-01-vector-integrator': raise ValueError('wrong result schema/fixture')
        if result.get('horizon')!=t or result.get('scenario_sha256')!=expected_hash: raise ValueError('case or fixture hash mismatch')
        if result.get('strategy')!=attempt.get('strategy') or result.get('strategy') not in STRATEGIES: raise ValueError('strategy mismatch')
        if result.get('target')!='candidate_relaxation' or result.get('assurance')!='numerical': raise ValueError('unexpected target or assurance')
        if result.get('termination')=='unsupported': return 'inconclusive',['strategy explicitly reports this workload as unsupported']
        if result.get('termination')!='completed': return 'inconclusive',[f"strategy termination: {result.get('termination')}"]
        coords=result.get('candidate_coordinates')
        if coords!={'state_dimension':n,'control_dimension':n,'external_dimension':0,'horizon':t}: raise ValueError('candidate coordinate dimensions mismatch')
        relation=result.get('candidate_relation')
        if not isinstance(relation,dict): return 'inconclusive',['strategy returned no recordable candidate H-relation']
        width,eq_expected,le_expected=required(n,t)
        if relation.get('dimension')!=width: raise ValueError('candidate relation has wrong dimension')
        labels=relation.get('labels')
        if not isinstance(labels,list) or len(labels) not in (0,width) or not all(isinstance(x,str) for x in labels) or (labels and len(set(labels))!=width): raise ValueError('coordinate labels malformed')
        ineq,ub,eq,ev=(relation.get(k) for k in ('inequalities','upper_bounds','equalities','equality_values'))
        if not all(isinstance(x,list) for x in (ineq,ub,eq,ev)) or len(ineq)!=len(ub) or len(eq)!=len(ev): raise ValueError('malformed H representation')
        if any(not isinstance(r,list) or len(r)!=width for r in ineq+eq): raise ValueError('H row width mismatch')
        seen_eq={canon(list(r)+[b],True) for r,b in zip(eq,ev)}; seen_le={canon(list(r)+[b]) for r,b in zip(ineq,ub)}
        if not eq_expected<=seen_eq: raise ValueError('initial/dynamics rows missing')
        if not le_expected<=seen_le: raise ValueError('control or stage-state box rows missing')
        # Sum_i x_T_i <= 0 and x_T_i=sum_k u_ki with u_ki>=0 force every coordinate/history to zero.
        terminal=row(width,{(t*n+c):1 for c in range(n)})
        if canon(terminal) not in seen_le and canon(terminal,True) not in seen_eq: return 'inconclusive',['candidate omits analytic terminal optimum level']
        zero=[0]*width
        if any(sum(q(a)*b for a,b in zip(r,zero))>q(rhs) for r,rhs in zip(ineq,ub)): raise ValueError('zero witness violates inequality')
        if any(sum(q(a)*b for a,b in zip(r,zero))!=q(rhs) for r,rhs in zip(eq,ev)): raise ValueError('zero witness violates equality')
        incumbents=result.get('incumbents')
        if not isinstance(incumbents,list): raise ValueError('malformed incumbent list')
        if any(not isinstance(x,dict) or x.get('states')!=[[0]*n for _ in range(t+1)] or x.get('controls')!=[[0]*n for _ in range(t)] or x.get('original_objective')!=0 for x in incumbents): raise ValueError('incumbent contradicts exact zero witness')
        return 'verified',['initial/dynamics/control/stage-box rows and terminal objective force the unique zero history; all emitted rows contain it']
    except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError) as e: return 'incorrect',[str(e)]
def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True,type=Path);a=p.parse_args();b=a.bundle.resolve(strict=True)
    m=json.loads((b/'manifest.json').read_text()); records=[json.loads(x) for x in (b/'attempts.jsonl').read_text().splitlines() if x]
    if m.get('schema')!='csl.review05.dimension-manifest/1': p.error('wrong manifest schema')
    for key in CASES:
        path=b/'inputs'/f'dimension01-{key}.json'
        n,t=CASES[key]
        if not path.is_file() or sha(path)!=m['cases'][key]['scenario_sha256']: p.error(f'fixture hash mismatch: {key}')
        if json.loads(path.read_text())!=expected_fixture(n,t): p.error(f'fixture content differs from exact oracle: {key}')
    expected={(key,r,pos) for key in CASES for r in range(7) for pos in (0,1)}
    observed={(x.get('case'),x.get('repetition'),x.get('order_position')) for x in records}
    if len(records)!=56 or observed!=expected or len({x.get('attempt_id') for x in records})!=56: p.error('incomplete 56-attempt schedule')
    order=('csl.synthesis.reach-back','csl.synthesis.strategy-b')
    for row in records:
        if row.get('warmup') is not (row.get('repetition')==0): p.error('warmup flag must be true exactly for repetition zero')
        n,t=CASES[row['case']]; first=(row['repetition']+n+t//2)%2
        if row.get('strategy')!=order[(first+row['order_position'])%2]: p.error('strategy order violates alternating schedule')
    checks=[]
    for x in records:
        expected_hash=m['cases'][x['case']]['scenario_sha256']; status,reasons=check(x,expected_hash)
        for field in ('stdout','stderr'):
            path=b/str(x.get(f'{field}_path',''))
            if not path.is_file() or sha(path)!=x.get(f'{field}_sha256'): status,reasons='incorrect',[f'{field} artifact missing or hash mismatch'];break
        checks.append({'attempt_id':x.get('attempt_id'),'case':x.get('case'),'strategy':x.get('strategy'),'warmup':x.get('warmup'),'status':status,'reasons':reasons})
    (b/'checks.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in checks))
    counts={s:sum(x['status']==s for x in checks) for s in ('verified','inconclusive','incorrect','unavailable')}
    print(json.dumps({'attempts':len(checks),'statuses':counts},indent=2))
    return int(counts['incorrect']>0 or counts['verified']==0)
if __name__=='__main__': raise SystemExit(main())

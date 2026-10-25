import itertools, json
import argparse
import hashlib
from pathlib import Path
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('results',type=Path)
args=parser.parse_args()
root=args.results.parent
output=root/'independent-oracle-verification.json'
provenance=json.loads((root/'run-provenance.json').read_text())
assert provenance['schema']=='csl.issue6-b07-capture-provenance/1'
assert provenance['source_tree_clean'] is True
assert provenance['build_type']=='Release'
assert provenance['results_sha256']==hashlib.sha256(args.results.read_bytes()).hexdigest()
rows=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
expected={}
for stocks in range(2):
    for lam in range(2):
        for disturbance in range(2):
            case_id=f'B07-reconstruction-s{stocks}-l{lam}-d{disturbance}'
            expected[case_id]=((305,205) if stocks==0 else (302,207),lam,
                (0.05,-0.04) if disturbance==0 else (0.06,-0.05))
assert len(rows)==8 and len({row['case_id'] for row in rows})==8
assert {row['case_id'] for row in rows}==set(expected)
actions=np.array([1.,.3,0.,-.3,-1.])
corners=np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]])
hist=np.array(list(itertools.product(range(4),repeat=5)),dtype=int)
w=corners[hist]
checks=[]
for row in rows:
    stocks,lam,coefficients=expected[row['case_id']]
    assert (row['initial_stock_oxidizer_kg'],row['initial_stock_fuel_kg'])==stocks
    assert row['terminal_lambda']==lam and tuple(row['disturbance_coefficients'])==coefficients
    assert row['initial_flow_oxidizer_kg_per_second']==29.375
    assert row['initial_flow_fuel_kg_per_second']==20.4
    assert row['modeled_horizon_seconds']==10 and row['step_seconds']==2
    assert row['plans_total']==3125 and row['status']=='numerical_optimal'
    assert len(row['source_commit'])==40 and len(row['driver_sha256'])==64 and len(row['scenario_sha256'])==64
    assert row['build_type']=='Release' and row['compiler_id']=='GNU'
    for key in ('source_commit','driver_sha256','scenario_sha256','executable_sha256',
                'compiler_id','compiler_version','build_type'):
        assert row[key]==provenance[key]
    exe=row['executable_sha256']
    assert exe=='not-supplied' or (len(exe)==64 and all(ch in '0123456789abcdef' for ch in exe))
    samples=row['measured_elapsed_ns']
    assert len(samples)==7 and row['warmup_calls']==1 and row['measured_calls']==7
    assert row['median_elapsed_ns']==sorted(samples)[3]
    assert row['min_elapsed_ns']==min(samples) and row['max_elapsed_ns']==max(samples)
    terminal=np.asarray(row['winner_terminal_vertices_x1_x3_x2_x4'],dtype=float)
    assert terminal.shape==(1024,4)
    assert np.all((terminal[:,0]>=29-1e-10)&(terminal[:,0]<=31+1e-10))
    assert np.all((terminal[:,1]>=19.5-1e-10)&(terminal[:,1]<=20.5+1e-10))
    assert np.all(terminal[:,2]>=-1e-10) and np.all(terminal[:,3]>=-1e-10)
    s0=np.array([29.375,row['initial_stock_oxidizer_kg'],20.4,row['initial_stock_fuel_kg']])
    a,b=row['disturbance_coefficients']; lam=row['terminal_lambda']
    vals=[]; feasible=[]
    for index,plan in enumerate(itertools.product(range(5),repeat=5)):
        x=np.repeat(s0[None,:],len(hist),axis=0); ok=True
        for t,k in enumerate(plan):
            old=x.copy(); u=actions[k]
            x[:,0]=old[:,0]+.7*u+a*w[:,t,0]
            x[:,1]=old[:,1]-2*old[:,0]
            x[:,2]=old[:,2]-u/3+b*w[:,t,1]
            x[:,3]=old[:,3]-2*old[:,2]
            ok &= bool(np.all((x[:,0]>=29-1e-10)&(x[:,0]<=31+1e-10)&(x[:,2]>=19.5-1e-10)&(x[:,2]<=20.5+1e-10)&(x[:,1]>=-1e-10)&(x[:,3]>=-1e-10)))
            if not ok: break
        if ok:
            feasible.append(index)
            f=(30-x[:,0])**2+x[:,1]**2+2.25*(20-x[:,2])**2+2.25*x[:,3]**2+lam*(x[:,1]-1.5*x[:,3])**2
            vals.append((float(np.max(f)),index))
    best=min(v for v,_ in vals); winners=[i for v,i in vals if abs(v-best)<1e-8]
    checks.append({'case_id':row['case_id'],'solver_feasible':row['plans_feasible'],'oracle_feasible':len(feasible),'solver_winners':row['minimizing_plan_indices'],'oracle_winners':winners,'solver_squared':row['value_squared'],'oracle_squared':best,'abs_diff':abs(row['value_squared']-best)})
output.write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
if any(x['solver_feasible']!=x['oracle_feasible'] or x['solver_winners']!=x['oracle_winners'] or x['abs_diff']>1e-7 for x in checks): raise SystemExit(1)

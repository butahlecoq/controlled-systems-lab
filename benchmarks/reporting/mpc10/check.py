"""Independent exact row reconstruction, oracle values, branch identities and raw bindings."""
from fractions import Fraction as F
import hashlib
import math
import json
from pathlib import Path
import re
import tempfile
from benchmarks.reporting.mpc10.evidence import load,sha,checked_capture,inventory,checking_identity
from benchmarks.reporting.mpc10.fixtures import fixtures
from benchmarks.reporting.mpc10.oracle import solve as exact


def normalize(row,rhs,equality):
    row=tuple(map(F,row));rhs=F(rhs)
    first=next((x for x in row if x),None)
    if first is None:return None if (rhs==0 if equality else rhs>=0) else ('false',)
    divisor=first if equality else abs(first)
    return (tuple(x/divisor for x in row),rhs/divisor)


def expected_rows(s,path):
    T=s['horizon'];hybrid=s['product']=='hybrid';continuous=s['product']=='mixed';n=2+5*T if hybrid else 2*(T+1)+int(continuous)*T
    inequalities=set();equalities=set()
    def row(values):
        a=[F(0)]*n
        for i,v in values.items():a[i]+=F(v)
        return a
    def add(values,rhs,equality=False):
        r=normalize(row(values),rhs,equality)
        if r is not None:(equalities if equality else inequalities).add(r)
    def bound(i,b):add({i:1},b[1]);add({i:-1},-F(b[0]))
    def state(i,b):bound(i,b);add({i+1:1},0,True)
    add({0:1},s['initial_x'],True);add({1:1},0,True)
    if not hybrid:
        for k,b in enumerate(s['state_bounds']):state(2*k,b)
        for k,j in enumerate(path['actions']):
            coefficients={2*(k+1):1,2*k:-1}
            if continuous:
                u=2*(T+1)+k;coefficients[u]=-1;bound(u,s['continuous_bounds'])
            add(coefficients,s['catalogue'][j],True);add({2*(k+1)+1:1,2*k+1:-1},0,True)
        objective=[F(0)]*n;objective[2*T]=F(s['terminal_linear'][0]);offset=F(s['terminal_linear'][1])
    else:
        modes={m['id']:m for m in s['modes']};edges={e['id']:e for e in s['edges']}
        for k,name in enumerate(path['modes']):
            post=0 if k==0 else 2+5*(k-1)+3;state(post,modes[name]['invariants'][k])
            if k==T:continue
            m=modes[name];e=edges[path['edges'][k]];u=2+5*k;pre=u+1;nxt=u+3
            add({pre:1,post:-F(m['flow_a']),u:-1},m['flow_offset'],True);add({pre+1:1,post+1:-1},0,True)
            bound(u,m['control_bounds']);state(pre,m['invariants'][k+1]);state(pre,e['guards'][k]);r,d=e['reset']
            add({nxt:1,pre:-F(r)},d,True);add({nxt+1:1,pre+1:-1},0,True)
        objective=[F(0)]*n;final=0 if T==0 else 2+5*(T-1)+3;last=modes[path['modes'][-1]];objective[final]=F(last['terminal_linear'][0]);offset=F(last['terminal_linear'][1])
    return n,inequalities,equalities,objective,offset


def program_rows(p):
    n=len(p['linear']);inequalities=set();equalities=set()
    def add(row,rhs,equality=False):
        value=normalize(row,rhs,equality)
        if value is not None:(equalities if equality else inequalities).add(value)
    for row,(lo,hi) in zip(p['matrix'],p['row_bounds'],strict=True):
        if len(row)!=n:raise ValueError('program row width')
        if lo is not None and lo==hi:add(row,hi,True)
        else:
            if hi is not None:add(row,hi)
            if lo is not None:add([-F(v) for v in row],-F(lo))
    if len(p['variable_bounds'])!=n:raise ValueError('program variable bound count')
    for i,(lo,hi) in enumerate(p['variable_bounds']):
        row=[0]*n;row[i]=1
        if lo is not None and lo==hi:add(row,hi,True)
        else:
            if hi is not None:add(row,hi)
            if lo is not None:add([-F(v) for v in row],-F(lo))
    return inequalities,equalities


def check_program(s,path,p):
    n,inequalities,equalities,objective,offset=expected_rows(s,path)
    if len(p['linear'])!=n or list(map(F,p['linear']))!=objective or F(p['offset'])!=offset:raise ValueError('native objective differs from authored branch')
    if program_rows(p)!=(inequalities,equalities):raise ValueError('native rows differ from exact independently reconstructed timing')


def relation_rows(relation):
    inequalities={v for row,rhs in zip(relation['inequalities'],relation['upper'],strict=True) if (v:=normalize(row,rhs,False)) is not None}
    equalities={v for row,rhs in zip(relation['equalities'],relation['values'],strict=True) if (v:=normalize(row,rhs,True)) is not None}
    return inequalities,equalities


def check_faces(s,oracle,raw):
    faces=raw.get('candidate_optimal_faces')
    if faces is None:return 'not-supplied'
    expected=oracle['all_optimal_paths']
    if [f['path'] for f in faces]!=expected:raise ValueError('candidate optimal branch inventory differs from exact ties')
    for face in faces:
        _,inequalities,equalities,objective,offset=expected_rows(s,face['path'])
        cut=normalize(objective,F(oracle['optimum'])-offset,True)
        if cut is not None:equalities.add(cut)
        if relation_rows(face['optimal_relation'])!=(inequalities,equalities):raise ValueError('candidate face differs from full original relation and exact optimal-value cut')
    return 'exact-profile-candidate-face-relations-checked'


def check_native_clocks(raw):
    if 'total_ns' not in raw:return
    total=raw['total_ns']
    if isinstance(total,bool) or not isinstance(total,int) or total<0:raise ValueError('invalid native total clock')
    for name,value in raw.items():
        if name.endswith('_ns') and (isinstance(value,bool) or not isinstance(value,int) or value<0 or value>total):raise ValueError('native phase exceeds whole-flow span')
    inner=0.
    for branch in raw.get('branches',[]):
        if 'result' not in branch:continue
        for name in ['native.load_seconds','native.solve_seconds']:
            matches=re.findall(r'^'+re.escape(name)+r'=(.+)$',branch['result']['raw_diagnostics'],re.MULTILINE)
            if len(matches)!=1:raise ValueError('native cost diagnostic inventory')
            value=float(matches[0])
            if not math.isfinite(value) or value<0:raise ValueError('invalid native cost diagnostic')
            inner+=value
    if inner>raw.get('solve_portfolio_ns',0)/1e9+.001:raise ValueError('inner native costs exceed portfolio span')


def check_native(s,oracle,raw):
    check_native_clocks(raw)
    if raw['fixture_id']!=s['id'] or raw['fixture_sha256']!=s['fixture_sha256']:raise ValueError('native fixture association')
    if s.get('external_unsupported'):
        if raw['status']!='external-encoding-unsupported':raise ValueError('missing external unsupported status')
        return {'status':'unsupported'}
    if s['cancel'] or (s['product']=='hybrid' and len(oracle['branches'])>s['max_branches']):
        if raw['status']!='construction-refused' or raw.get('branches'):raise ValueError('hybrid refusal exposes successful portfolio')
        return {'status':'inconclusive-refused','construction':raw['construction']}
    if s['product']=='hybrid' and not oracle['branches']:
        errors=raw.get('construction',{}).get('diagnostics',[])
        if raw['status']!='construction-refused' or raw.get('branches') or not any(d['field']=='hybrid.portfolio.paths' and d['code']==3 for d in errors):raise ValueError('empty hybrid inventory lacks public no-path refusal')
        return {'status':'verified-empty-branch-inventory','branch_count':0,'complete_continuous_family':False,'native_construction':raw['construction']}
    expected=oracle['branches'][:s['max_branches']];branches=raw['branches']
    if [b['path'] for b in branches]!=[b['path'] for b in expected]:raise ValueError('native branch inventory/order differs')
    complete=len(expected)==len(oracle['branches'])
    if raw['status']!=('complete' if complete else 'incomplete-history-prefix'):raise ValueError('native completeness mismatch')
    for branch,wanted in zip(branches,expected):
        check_program(s,branch['path'],branch['program'])
        r=branch.get('result')
        if r is None:raise ValueError('native branch has no mathematical result')
        if r['contract_diagnostics']:raise ValueError('native program result contract diagnostics')
        if wanted['feasible']:
            if 'primal' not in r:raise ValueError('feasible native branch lacks witness')
            vector=r['primal'];p=branch['program']
            if len(vector)!=len(p['linear']):raise ValueError('native primal width')
            for row,(lo,hi) in zip(p['matrix'],p['row_bounds']):
                value=sum(a*b for a,b in zip(row,vector))
                if (lo is not None and value<lo-1e-7) or (hi is not None and value>hi+1e-7):raise ValueError('native witness violates original joint row')
            value=sum(a*b for a,b in zip(p['linear'],vector))+p['offset']
            if abs(value-float(F(wanted['value'])))>1e-7:raise ValueError('native branch value differs from exact oracle')
        elif r['outcome']!=1:raise ValueError('infeasible native branch was not retained as infeasible')
    faces=check_faces(s,oracle,raw) if s['product']=='hybrid' else 'not-applicable'
    return {'candidate_face_check':faces,'status':'verified-bounded-branches' if complete else 'inconclusive-prefix','branch_count':len(branches),'all_optimal_paths':oracle['all_optimal_paths'] if complete else None,'complete_continuous_family':raw.get('family_verification',{}).get('continuous_coverage')==1}


def check_scip_witness(s,r,raw_values):
    T=s['horizon'];tol=1e-7
    def inside(value,bounds):return bounds[0]-tol<=value<=bounds[1]+tol
    if len(r['states'])!=T+1 or len(r['controls'])!=T or abs(r['states'][0]-s['initial_x'])>tol:raise ValueError('SCIP witness dimensions/initial state')
    for k,value in enumerate(r['states']):
        if abs(raw_values[f'x_{k}']-value)>1e-12:raise ValueError('SCIP state differs from raw solution')
    for k,value in enumerate(r['controls']):
        if abs(raw_values[f'u_{k}']-value)>1e-12:raise ValueError('SCIP control differs from raw solution')
    if s['product']!='hybrid':
        for k,b in enumerate(s['state_bounds']):
            if not inside(r['states'][k],b):raise ValueError('SCIP original state bound')
        for k,j in enumerate(r['path']['actions']):
            if not 0<=j<len(s['catalogue']) or any(abs(raw_values[f'action_{k}_{i}']-int(i==j))>1e-8 for i in range(len(s['catalogue']))):raise ValueError('SCIP raw action identity')
            u=r['controls'][k]
            if not inside(u,s['continuous_bounds']) or abs(r['states'][k+1]-r['states'][k]-u-s['catalogue'][j])>tol:raise ValueError('SCIP original finite/mixed transition')
        c,offset=s['terminal_linear']
    else:
        modes={m['id']:m for m in s['modes']};edges={e['id']:e for e in s['edges']};path=r['path']
        if path['modes'][0]!=s['initial_mode'] or path['modes'][-1] not in s['allowed_terminal_modes']:raise ValueError('SCIP mode endpoint identity')
        for k,name in enumerate(path['modes']):
            if any(abs(raw_values[f'mode_{k}_{m}']-int(m==name))>1e-8 for m in modes):raise ValueError('SCIP raw mode identity')
            if not inside(r['states'][k],modes[name]['invariants'][k]):raise ValueError('SCIP post invariant')
        for k,name in enumerate(path['edges']):
            e=edges[name];m=modes[path['modes'][k]];u=r['controls'][k];pre=m['flow_a']*r['states'][k]+u+m['flow_offset']
            if e['source']!=path['modes'][k] or e['target']!=path['modes'][k+1] or any(abs(raw_values[f'edge_{k}_{edge}']-int(edge==name))>1e-8 for edge in edges):raise ValueError('SCIP raw edge identity/adjacency')
            if not inside(u,m['control_bounds']) or not inside(pre,m['invariants'][k+1]) or not inside(pre,e['guards'][k]):raise ValueError('SCIP source/pre/guard timing')
            a,b=e['reset']
            if abs(r['states'][k+1]-a*pre-b)>tol:raise ValueError('SCIP reset timing')
        c,offset=modes[path['modes'][-1]]['terminal_linear']
    if abs(c*r['states'][-1]+offset-r['objective'])>tol:raise ValueError('SCIP original terminal objective')


def check_scip(s,oracle,folder):
    results=load(folder/'results.json')
    if s.get('external_unsupported'):
        if results!={'status':'unsupported','reason':s['external_unsupported']}:raise ValueError('external refusal binding')
        return {'status':'unsupported'}
    expected=[None,*[b['path'] for b in oracle['branches']]]
    rows=results['attempts'];normal=[r for r in rows if r['relative_path']!='node-limit']
    if [r['result']['fixed_path'] for r in normal]!=expected:raise ValueError('SCIP fixed-branch inventory mismatch')
    for index,item in enumerate(normal):
        if item['relative_path']!=('global' if index==0 else f'branch-{index-1:03d}'):raise ValueError('unsafe SCIP attempt path')
        target=folder/item['relative_path'];r=item['result']
        from benchmarks.reporting.mpc10.scip_reference import formulate
        with tempfile.TemporaryDirectory() as temporary:
            location=Path(temporary);model,_=formulate(s,location,r['fixed_path'])
            counts={'variables':model.getNVars(),'constraints':model.getNConss(),'binary_variables':sum(v.vtype()=='BINARY' for v in model.getVars())}
            model.writeProblem(str(location/'model.cip'));model.freeProb()
            if (location/'model.cip').read_bytes()!=(target/'model.cip').read_bytes() or counts!=r['counts']:raise ValueError('SCIP submitted model differs from authored indicator rebuild')
        if r!=load(target/'result.json'):raise ValueError('SCIP extracted result differs from individual record')
        native=(target/'solver.log').read_text();statuses=re.findall(r'^SCIP Status\s*:\s*(.+)$',native,re.MULTILINE)
        if len(statuses)!=1:raise ValueError('SCIP native outcome inventory')
        if r['status']=='optimal' and 'optimal solution found' not in statuses[0]:raise ValueError('SCIP native optimality outcome differs')
        if r['status']=='infeasible' and 'infeasible' not in statuses[0]:raise ValueError('SCIP native infeasibility outcome differs')
        value=oracle['optimum'] if index==0 else oracle['branches'][index-1].get('value')
        if value is None:
            if r['status']!='infeasible' or 'objective' in r:raise ValueError('SCIP infeasibility differs from exact branch')
        else:
            if r['status']!='optimal' or abs(r['objective']-float(F(value)))>1e-7:raise ValueError('SCIP value differs from exact oracle')
            solution=(target/'solution.sol').read_text();match=re.search(r'^objective value:\s*(\S+)',solution,re.MULTILINE)
            if not match or abs(float(match[1])-r['objective'])>1e-10:raise ValueError('SCIP incumbent is not bound to raw solution')
            raw_values={}
            for line in solution.splitlines():
                parts=line.split()
                if len(parts)>=2:
                    try:value=float(parts[1])
                    except ValueError:continue
                    if not math.isfinite(value):raise ValueError('nonfinite raw SCIP variable')
                    raw_values[parts[0]]=value
            check_scip_witness(s,r,raw_values)
            if r['fixed_path'] is not None and r['path']!=r['fixed_path']:raise ValueError('SCIP fixed branch identity differs')
    if s['id']=='hybrid-T3':
        interrupted=next(r['result'] for r in rows if r['relative_path']=='node-limit')
        if interrupted['status']!='nodelimit' or 'objective' in interrupted:raise ValueError('interrupted SCIP search relabelled as a solution')
    return {'status':'verified-bounded-global-and-fixed-branches','branch_count':len(oracle['branches']),'complete_continuous_family':False}


def check(bundle):
    hashes=checked_capture(bundle)
    reports=[]
    for fixture in fixtures():
        folder=bundle/fixture['id'];s=load(folder/'fixture.json');original=dict(s);declared=original.pop('fixture_sha256')
        if original!=fixture or hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=declared:raise ValueError('scenario differs from authored registry')
        oracle=exact(s)
        if oracle!=load(folder/'exact.json'):raise ValueError('saved exact oracle differs')
        raw_path=folder/'native/stdout.txt';np=load(folder/'native/process.json');sp=load(folder/'scip-process/process.json')
        for process,path in [(np,folder/'native'),(sp,folder/'scip-process')]:
            if process['stdout_sha256']!=sha(path/'stdout.txt') or process['stderr_sha256']!=sha(path/'stderr.txt'):raise ValueError('native process stream binding')
        if np['status']!='completed' or sp['status']!='completed' or np['return_code']!=0 or sp['return_code']!=0:reports.append({'id':s['id'],'status':'inconclusive-process','native_process':np,'scip_process':sp});continue
        native=load(raw_path)
        if native.get('total_ns',0)/1e9>np['whole_process_seconds']+.001:raise ValueError('native whole-flow clock exceeds process span')
        if not s.get('external_unsupported'):
            attempts=load(folder/'scip/results.json')['attempts']
            duration=sum(a['result']['formulation_and_setup_seconds']+a['result']['optimization_seconds'] for a in attempts)
            if any(a['result'][k]<0 or not math.isfinite(a['result'][k]) for a in attempts for k in ['formulation_and_setup_seconds','optimization_seconds']) or duration>sp['whole_process_seconds']+.001:raise ValueError('SCIP clocks exceed worker span')
        reports.append({'id':s['id'],'native':check_native(s,oracle,native),'scip':check_scip(s,oracle,folder/'scip'),'exact_optimum':oracle.get('optimum'),'exact_all_optimal_paths':oracle.get('all_optimal_paths')})
    if inventory(bundle)!=hashes:raise ValueError('capture changed during verification')
    checking_revision,checking_sources=checking_identity()
    return {'schema':'csl.mpc10.check/1','reports':reports,'input_files':hashes,'checking_sources':checking_sources,'checking_revision':checking_revision,'scope':'exact independently reconstructed branch LP rows/objectives and interval oracle; numerical external witnesses/bounds; continuous family claims only where actual CSL verifier establishes them'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    a.output.write_text(json.dumps(check(a.bundle.resolve()),indent=2)+'\n')

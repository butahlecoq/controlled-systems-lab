"""Exact interval propagation and inverse construction, independent of CSL/SCIP."""
from fractions import Fraction as F
from itertools import product


def interval(bounds):return tuple(map(F,bounds))
def intersect(*values):
    lo=max(v[0] for v in values);hi=min(v[1] for v in values)
    return (lo,hi) if lo<=hi else None

def image(bounds,a,b=0):return tuple(sorted((a*bounds[0]+b,a*bounds[1]+b)))


def histories(s):
    T=s['horizon']
    if s['product']!='hybrid':return [{'actions':list(h)} for h in product(range(len(s['catalogue'])),repeat=T)]
    paths=[{'modes':[s['initial_mode']],'edges':[]}]
    for _ in range(T):paths=[{'modes':p['modes']+[e['target']],'edges':p['edges']+[e['id']]} for p in paths for e in s['edges'] if e['source']==p['modes'][-1]]
    return [p for p in paths if p['modes'][-1] in s['allowed_terminal_modes']]


def branch(s,path):
    x=F(s['initial_x']);current=(x,x);stages=[]
    modes={m['id']:m for m in s.get('modes',[])};edges={e['id']:e for e in s.get('edges',[])}
    for k in range(s['horizon']):
        if s['product']=='hybrid':
            m=modes[path['modes'][k]];e=edges[path['edges'][k]]
            source=interval(m['invariants'][k]);pre_inv=interval(m['invariants'][k+1]);guard=interval(e['guards'][k]);dest=interval(modes[path['modes'][k+1]]['invariants'][k+1]);control=interval(m['control_bounds']);a=F(m['flow_a']);b=F(m['flow_offset']);r,d=map(F,e['reset'])
        else:
            source=interval(s['state_bounds'][k]);pre_inv=interval(s['state_bounds'][k+1]);guard=pre_inv;dest=pre_inv;control=interval(s['continuous_bounds']);a=F(1);b=F(s['catalogue'][path['actions'][k]]);r,d=F(1),F(0)
        old=intersect(current,source)
        if old is None:return {'path':path,'feasible':False,'failed_stage':k,'reason':'source-invariant'}
        flow=image(old,a,b);flow=(flow[0]+control[0],flow[1]+control[1]);pre=intersect(flow,pre_inv,guard)
        if pre is None:return {'path':path,'feasible':False,'failed_stage':k,'reason':'pre-invariant-or-guard'}
        current=intersect(image(pre,r,d),dest)
        if current is None:return {'path':path,'feasible':False,'failed_stage':k,'reason':'destination-invariant'}
        stages.append((old,pre,control,a,b,r,d))
    terminal=interval(modes[path['modes'][-1]]['invariants'][-1]) if s['product']=='hybrid' else interval(s['state_bounds'][-1])
    current=intersect(current,terminal)
    if current is None:return {'path':path,'feasible':False,'failed_stage':s['horizon'],'reason':'terminal-invariant'}
    c,offset=map(F,modes[path['modes'][-1]]['terminal_linear'] if s['product']=='hybrid' else s['terminal_linear'])
    target=current[0] if c>=0 else current[1];value=c*target+offset;states=[target];controls=[];pres=[]
    for old,pre,control,a,b,r,d in reversed(stages):
        before=(target-d)/r if r else pre[0]
        candidates=image((before-b-control[1],before-b-control[0]),1/a)
        previous=intersect(old,candidates)
        if previous is None:raise AssertionError('inverse witness construction failed')
        target=previous[0];controls.append(before-a*target-b);pres.append(before);states.append(target)
    return {'path':path,'feasible':True,'terminal_interval':[str(v) for v in current],'value':str(value),'witness':{'states':list(map(str,reversed(states))),'pre_states':list(map(str,reversed(pres))),'continuous_controls':list(map(str,reversed(controls)))}}


def solve(s):
    if s.get('external_unsupported'):return {'status':'unsupported','reason':s['external_unsupported']}
    results=[branch(s,p) for p in histories(s)];feasible=[r for r in results if r['feasible']]
    optimum=min((F(r['value']) for r in feasible),default=None)
    return {'status':'complete','branches':results,'optimum':str(optimum) if optimum is not None else None,'all_optimal_paths':[r['path'] for r in feasible if F(r['value'])==optimum],'proof_scope':'exact reachable intervals per fixed branch for scalar active coordinate and independent bounded interval controls; y is identically zero; complete discrete histories, not arbitrary hybrid systems'}

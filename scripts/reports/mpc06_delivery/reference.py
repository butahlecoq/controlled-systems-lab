"""Exact tiny terminal-zero minimax references for two distinct policy classes.

For this N=3 fixture, nominal terminal equations leave one scalar a. Every
fixed disturbance history gives the same positive quadratic coefficient in a;
only its linear and constant terms differ. This is not a causal MPC optimizer.
"""
from fractions import Fraction as Q
from itertools import product

R=Q(1,8)
GAINS=((0,0),(-1,-2))
SCOPE='N=3 fixed nominal plan with z3=0; fixed specified gain; all independent stagewise continuous disturbances'


def nominal(initial,a):
    p,q=initial;inputs=(a,-p-3*q-2*a,p+2*q+a);states=[(p,q)]
    for v in inputs:
        p,q=p+q,q+v;states.append((p,q))
    if states[-1]!=(0,0):raise ValueError('nominal terminal elimination failed')
    return states,inputs


def trajectory(initial,a,gain,disturbances):
    if tuple(gain) not in GAINS or len(initial)!=2 or len(disturbances)!=3:raise ValueError('unsupported fixed policy profile')
    z_states,v=nominal(initial,a);x=tuple(initial);states=[x];inputs=[];cost=Q(0)
    safe=all(abs(coordinate)<=1 for coordinate in x)
    for stage,w in enumerate(disturbances):
        if not -R<=w<=R:raise ValueError('disturbance outside compact interval')
        error=(x[0]-z_states[stage][0],x[1]-z_states[stage][1])
        u=v[stage]+gain[0]*error[0]+gain[1]*error[1]
        cost+=x[0]**2+x[1]**2+u*u
        x=(x[0]+x[1],x[1]+u+w);states.append(x);inputs.append(u)
        safe=safe and abs(u)<=1 and all(abs(coordinate)<=1 for coordinate in x)
    cost+=x[0]**2+x[1]**2
    return dict(states=states,controls=inputs,nominal_states=z_states,nominal_controls=v,cost=cost,safe=safe)


def quadratic(path,a):return path['quadratic']*a*a+path['linear']*a+path['constant']


def build(initial,gain):
    if tuple(gain) not in GAINS:raise ValueError('unsupported gain/policy')
    paths=[];constraints=[];lower=None;upper=None;feasible=True
    for index,disturbances in enumerate(product((-R,R),repeat=3)):
        zero=trajectory(initial,Q(0),gain,disturbances)
        plus=trajectory(initial,Q(1),gain,disturbances)
        minus=trajectory(initial,Q(-1),gain,disturbances)
        f0,f1,fm=zero['cost'],plus['cost'],minus['cost']
        q=(f1+fm)/2-f0;b=(f1-fm)/2
        paths.append(dict(index=index,disturbances=disturbances,quadratic=q,linear=b,constant=f0))
        coordinates0=[x for state in zero['states'] for x in state]+list(zero['controls'])
        coordinates1=[x for state in plus['states'] for x in state]+list(plus['controls'])
        for coordinate,(constant,end) in enumerate(zip(coordinates0,coordinates1)):
            slope=end-constant
            for sign in (-1,1):
                coefficient=sign*slope;bound=1-sign*constant
                constraints.append(dict(path=index,coordinate=coordinate,coefficient=coefficient,bound=bound))
                if coefficient>0:upper=bound/coefficient if upper is None else min(upper,bound/coefficient)
                elif coefficient<0:lower=bound/coefficient if lower is None else max(lower,bound/coefficient)
                elif bound<0:feasible=False
    common={path['quadratic'] for path in paths}
    if len(common)!=1 or next(iter(common))<=0:raise ValueError('common positive quadratic premise failed')
    if lower is None or upper is None:raise ValueError('reference interval must be bounded')
    return dict(paths=paths,constraints=constraints,interval=(lower,upper),feasible=feasible and lower<=upper,
                common_quadratic=next(iter(common)))


def solve(initial,gain):
    initial=tuple(map(Q,initial));gain=tuple(gain);built=build(initial,gain)
    result=dict(initial=initial,gain=gain,policy_class='fixed-open-loop-M0' if gain==(0,0) else 'fixed-K-frozen-nominal-plan',
                scope=SCOPE,**built)
    if not built['feasible']:return result
    lo,hi=built['interval'];paths=built['paths'];candidates={lo,hi}
    for path in paths:candidates.add(-path['linear']/(2*path['quadratic']))
    for i,left in enumerate(paths):
        for right in paths[i+1:]:
            if left['linear']!=right['linear']:
                candidates.add((right['constant']-left['constant'])/(left['linear']-right['linear']))
    candidates=sorted(a for a in candidates if lo<=a<=hi)
    a=min(candidates,key=lambda a:(max(quadratic(path,a) for path in paths),a))
    worst=max(quadratic(path,a) for path in paths)
    active=[path['index'] for path in paths if quadratic(path,a)==worst]
    slopes=[2*paths[i]['quadratic']*a+paths[i]['linear'] for i in active]
    if lo==hi:certificate=dict(kind='singleton-interval')
    elif a==lo:
        index=active[slopes.index(max(slopes))];certificate=dict(kind='lower-endpoint',path=index,slope=max(slopes))
    elif a==hi:
        index=active[slopes.index(min(slopes))];certificate=dict(kind='upper-endpoint',path=index,slope=min(slopes))
    elif 0 in slopes:
        index=active[slopes.index(0)];certificate=dict(kind='stationary-active',paths=[index],weights=[Q(1)])
    else:
        i,j=slopes.index(min(slopes)),slopes.index(max(slopes));weight=slopes[j]/(slopes[j]-slopes[i])
        certificate=dict(kind='convex-active',paths=[active[i],active[j]],weights=[weight,1-weight])
    result.update(a=a,worst_cost=worst,candidates=candidates,active=active,certificate=certificate)
    return result


def check(result):
    """Check feasibility and a global lower bound, without candidate search."""
    built=build(result['initial'],result['gain'])
    for key in ('paths','constraints','interval','feasible','common_quadratic'):
        if result[key]!=built[key]:raise ValueError('reference fixture/constraint binding mismatch')
    expected_class='fixed-open-loop-M0' if tuple(result['gain'])==(0,0) else 'fixed-K-frozen-nominal-plan'
    if result['scope']!=SCOPE or result['policy_class']!=expected_class:raise ValueError('policy scope changed')
    if not built['feasible']:return True
    lo,hi=built['interval'];a=result['a'];paths=built['paths'];worst=result['worst_cost']
    if not lo<=a<=hi:raise ValueError('minimax candidate is infeasible')
    actual=[]
    for path in paths:
        replayed=trajectory(result['initial'],a,result['gain'],path['disturbances'])
        if not replayed['safe'] or replayed['cost']!=quadratic(path,a):raise ValueError('literal disturbance replay mismatch')
        actual.append(replayed['cost'])
    if max(actual)!=worst or result['active']!=[i for i,value in enumerate(actual) if value==worst]:raise ValueError('worst-cost/active-set mismatch')
    proof=result['certificate'];kind=proof['kind']
    if kind=='singleton-interval':
        if lo!=hi:raise ValueError('false singleton interval')
    elif kind in ('lower-endpoint','upper-endpoint'):
        index=proof['path'];slope=2*paths[index]['quadratic']*a+paths[index]['linear']
        if index not in result['active'] or slope!=proof['slope']:raise ValueError('endpoint active gradient mismatch')
        if (kind=='lower-endpoint' and (a!=lo or slope<0)) or (kind=='upper-endpoint' and (a!=hi or slope>0)):
            raise ValueError('endpoint does not minimize its active quadratic on the interval')
    elif kind in ('stationary-active','convex-active'):
        indices=proof['paths'];weights=proof['weights']
        if len(indices)!=len(weights) or not weights or sum(weights)!=1 or any(w<0 for w in weights):raise ValueError('invalid convex weights')
        if any(i not in result['active'] for i in indices):raise ValueError('lower bound contains inactive cost')
        derivative=sum(w*(2*paths[i]['quadratic']*a+paths[i]['linear']) for i,w in zip(indices,weights))
        if derivative!=0:raise ValueError('active convex lower bound is not stationary')
    else:raise ValueError('unsupported minimax optimality certificate')
    # The active convex quadratic is <= the envelope everywhere and is minimized
    # at a (or on the feasible endpoint). Equality there proves the global value.
    return True


def decode(record):
    """Decode only the declared rational fields; identifiers stay identifiers."""
    result=dict(record);result['initial']=tuple(map(Q,record['initial']));result['gain']=tuple(record['gain'])
    result['interval']=tuple(map(Q,record['interval']));result['common_quadratic']=Q(record['common_quadratic'])
    result['paths']=[dict(path,disturbances=tuple(map(Q,path['disturbances'])),
        **{key:Q(path[key]) for key in ('quadratic','linear','constant')}) for path in record['paths']]
    result['constraints']=[dict(row,coefficient=Q(row['coefficient']),bound=Q(row['bound'])) for row in record['constraints']]
    if record['feasible']:
        for key in ('a','worst_cost'):result[key]=Q(record[key])
        result['candidates']=list(map(Q,record['candidates']))
        proof=dict(record['certificate'])
        if 'slope' in proof:proof['slope']=Q(proof['slope'])
        if 'weights' in proof:proof['weights']=list(map(Q,proof['weights']))
        result['certificate']=proof
    return result

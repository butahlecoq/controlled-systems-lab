"""Exact fixture-specific reference for deterministic-anchor tube MPC.

All arithmetic is rational. This is an independent research oracle, not a
production synthesis or approximation implementation.
"""
from fractions import Fraction as Q
from itertools import product

R=Q(1,8)


def plan(anchor,a):
    p,q=anchor
    controls=(a,-p-3*q-2*a,p+2*q+a)
    states=[(p,q)]
    for v in controls:
        p,q=p+q,q+v
        states.append((p,q))
    return states,controls


def tightenings(kind):
    if kind=='finite-reference':
        # e0=0; e1=Ew0; e2 and all subsequent errors fill exactly Z.
        supports=[(Q(0),Q(0),Q(0)),(Q(0),R,2*R),(R,2*R,3*R)]
    elif kind in ('polytope','zonotope','parallelotope'):
        supports=[(R,2*R,3*R)]*3
    elif kind=='inflated-zonotope':
        supports=[(Q(3,16),Q(3,8),Q(9,16))]*3
    elif kind=='ellipsoid-certified':
        # In (s,t)=(e1,e1+e2): s²/(1/2)²+t²/(1/4)² <= 1.
        # Exact squared support comparisons justify the outward rational pads.
        assert Q(5,8)**2>=Q(1,2)**2+Q(1,4)**2
        assert Q(3,4)**2>=Q(1,2)**2+4*Q(1,4)**2
        supports=[(Q(1,2),Q(5,8),Q(3,4))]*3
    else:
        raise ValueError('unsupported or non-RPI enclosure')
    return [(1-a,1-b,1-c) for a,b,c in supports]


def feasible_plan(states,controls,bounds):
    return all(abs(p)<=hp and abs(q)<=hq and abs(v)<=hu
               for (p,q),v,(hp,hq,hu) in zip(states,controls,bounds)) and states[-1]==(0,0)


def cost(states,controls):
    return sum(p*p+q*q+v*v for (p,q),v in zip(states,controls))


def problem(anchor,bounds):
    """Eliminate terminal equalities; intersect every tightened affine row."""
    if len(bounds)!=3:raise ValueError('N=3 bounds required')
    s0,u0=plan(anchor,Q(0));s1,u1=plan(anchor,Q(1))
    lower=None;upper=None;feasible=True
    for k,(hp,hq,hu) in enumerate(bounds):
        for b,c,h in ((s0[k][0],s1[k][0]-s0[k][0],hp),
                      (s0[k][1],s1[k][1]-s0[k][1],hq),
                      (u0[k],u1[k]-u0[k],hu)):
            if h<0:feasible=False
            for a,rhs in ((c,h-b),(-c,h+b)):
                if a>0:upper=rhs/a if upper is None else min(upper,rhs/a)
                elif a<0:lower=rhs/a if lower is None else max(lower,rhs/a)
                elif rhs<0:feasible=False
    sm,um=plan(anchor,Q(-1))
    f0,f1,fm=cost(s0,u0),cost(s1,u1),cost(sm,um)
    quadratic=(f1+fm)/2-f0;linear=(f1-fm)/2
    if lower is None or upper is None:raise ValueError('fixture must bound first input')
    return dict(lower=lower,upper=upper,feasible=feasible and lower<=upper,
                quadratic=quadratic,linear=linear,offset=f0)


def optimizer(qp):
    if not qp['feasible']:raise ValueError('empty tightened feasible interval')
    return min(qp['upper'],max(qp['lower'],-qp['linear']/(2*qp['quadratic'])))


def value(qp,a):return qp['quadratic']*a*a+qp['linear']*a+qp['offset']


def representation_checks():
    # s=e1,t=e1+e2 gives (s+,t+)=(t,w). Exact Z is [-r,r]²
    # in these coordinates, so the nilpotent tail vanishes identically.
    result={kind:dict(direction='equivalent',contains_exact_Z=True,rpi=True,
                      proof='s,t in [-r,r] maps to (t,w) in the same square')
            for kind in ('polytope','zonotope','parallelotope')}
    result['inflated-zonotope']=dict(direction='outer',contains_exact_Z=True,rpi=True,
        proof='s,t in [-3r/2,3r/2]; |w|<=r<=3r/2')
    result['box']=dict(direction='outer',contains_exact_Z=True,rpi=False,
        counterexample={'error':[str(R),str(2*R)],'w':str(R),
                        'successor':[str(3*R),str(-2*R)]},
        proof='outer coordinate hull permits e1+e2=3r; next e1 exceeds r')
    result['ellipsoid-app04']=dict(direction='outer',contains_exact_Z=True,rpi=False,
        counterexample={'error':['0','5/32'],'w':str(R),'successor':['5/32','-1/32']},
        proof='APP-04 orientation s,t gives squared radii >=2r²; rational witness violates next circle',
        qualification='counterexample checked against actual emitted stored radii by native-output checker')
    assert R*R/Q(1,2)**2+R*R/Q(1,4)**2<=1
    assert Q(1,4)**2/Q(1,2)**2+R*R/Q(1,4)**2<=1
    result['ellipsoid-certified']=dict(direction='outer',contains_exact_Z=True,rpi=True,
        proof='s²/(1/2)²+t²/(1/4)²<=1; next value<=1/4+1/4; exact Z vertices have value<=5/16',
        source='independent proposed invariant outer ellipsoid; not the rejected APP-04 member')
    return result


def replay(anchor,nominal_controls,policy='propagated-anchor'):
    if policy!='propagated-anchor':raise ValueError('disturbance-dependent reoptimization is unsupported')
    paths=[]
    for disturbances in product((-R,R),repeat=len(nominal_controls)):
        z=anchor;x=anchor;states=[x];inputs=[];safe=True;total=Q(0)
        for v,w in zip(nominal_controls,disturbances):
            e=(x[0]-z[0],x[1]-z[1]);u=v-e[0]-2*e[1]
            total+=x[0]**2+x[1]**2+u*u
            x=(x[0]+x[1],x[1]+u+w);z=(z[0]+z[1],z[1]+v)
            safe=safe and abs(u)<=1 and all(abs(c)<=1 for c in x)
            states.append(x);inputs.append(u)
        total+=sum(c*c for c in x)
        paths.append(dict(disturbances=disturbances,states=states,inputs=inputs,cost=total,safe=safe))
    return dict(paths=paths,worst=max(p['cost'] for p in paths),
                proof='fixed deterministic nominal sequence: actual state/input affine in disturbance vector; convex quadratic maximum attained at a box vertex')

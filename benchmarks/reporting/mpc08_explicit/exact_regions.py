"""Fixture-specific exact region/predecessor evidence; not a general set engine."""
from fractions import Fraction as Q
from itertools import combinations
from math import comb
from time import perf_counter_ns
import explicit_double_integrator as producer

X=[(Q(1),Q(0),Q(3)),(Q(-1),Q(0),Q(3)),(Q(0),Q(1),Q(2)),(Q(0),Q(-1),Q(2))]


def hull(points):
    """Exact monotone chain, independent of the producer's polygon clipping."""
    points=sorted(set(points))
    if len(points)<3:return points
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    sides=[]
    for ordered in (points,list(reversed(points))):
        side=[]
        for p in ordered:
            while len(side)>1 and cross(side[-2],side[-1],p)<=0:side.pop()
            side.append(p)
        sides.append(side)
    return sides[0][:-1]+sides[1][:-1]


def vertices(rows):
    points=[]
    for (a,b,c),(d,e,f) in combinations(rows,2):
        det=a*e-b*d
        if not det:continue
        p=((c*e-b*f)/det,(a*f-c*d)/det)
        if all(h[0]*p[0]+h[1]*p[1]<=h[2] for h in rows):points.append(p)
    return hull(points)


def area(points):
    return abs(sum((a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1])),Q(0)))/2


def contained(points,rows):
    return all(a*p+b*v<=c for p,v in points for a,b,c in rows)


def target(s=Q(1),t=Q(1)):
    return [(Q(1),Q(1),s),(Q(-1),Q(-1),s),(Q(1),Q(2),t),(Q(-1),Q(-2),t)]


def predecessor(rows,radius=Q(0)):
    """Eliminate u from plant/target inequalities, with exists-u/forall-w order."""
    joint=[(a,b,Q(0),c) for a,b,c in X]+[(Q(0),Q(0),Q(1),Q(1)),(Q(0),Q(0),Q(-1),Q(1))]
    joint += [(a,a+b,b,c-abs(b)*radius) for a,b,c in rows]
    positive=[h for h in joint if h[2]>0];negative=[h for h in joint if h[2]<0]
    result=[(a,b,c) for a,b,u,c in joint if u==0]
    for a,b,u,c in positive:
        for d,e,v,f in negative:result.append((a/u-d/v,b/u-e/v,c/u-f/v))
    return result


def polynomial(control):
    a,b,c=control
    return [1+a*a,2+2*a*(1+b),1+(1+b)**2,2*a*c,2*(1+b)*c,c*c]


def region_record():
    feasible,regions=producer.build_regions()
    return dict(feasible_vertices=feasible,regions=[dict(lower=r.lower,upper=r.upper,mode=r.mode,
        rows=r.constraints,vertices=r.polygon,control=[r.control.p,r.control.v,r.control.c],
        value=polynomial([r.control.p,r.control.v,r.control.c])) for r in regions])


def check_regions(record):
    domain=predecessor(target());fv=vertices(domain)
    if hull(record['feasible_vertices'])!=fv:raise ValueError('feasible-domain projection mismatch')
    total=Q(0)
    for r in record['regions']:
        vs=vertices(r['rows'])
        if vs!=hull(r['vertices']) or area(vs)<=0 or not contained(vs,domain):raise ValueError('region containment/vertices mismatch')
        total+=area(vs);a,b,c=r['control']
        if r['value']!=polynomial(r['control']):raise ValueError('value polynomial mismatch')
        for p,v in vs:
            u=a*p+b*v+c
            lower=[-Q(1),-1-p-2*v,(-1-p-3*v)/2];upper=[Q(1),1-p-2*v,(1-p-3*v)/2]
            if not max(lower)<=u<=min(upper):raise ValueError('control not feasible on full region')
            if r['mode']=='free':valid=u==-v
            elif r['mode']=='lower':valid=u==lower[r['lower']] and v+u>=0
            elif r['mode']=='upper':valid=u==upper[r['upper']] and v+u<=0
            else:valid=False
            if not valid:raise ValueError('region scalar KKT identity fails')
    if total!=area(fv):raise ValueError('closed-region coverage area mismatch')
    boundaries=0
    for left,right in combinations(record['regions'],2):
        overlap=vertices(left['rows']+right['rows'])
        if area(overlap):raise ValueError('region interiors overlap')
        for p,v in overlap:
            if sum(x*y for x,y in zip(left['control'],(p,v,1)))!=sum(x*y for x,y in zip(right['control'],(p,v,1))):
                raise ValueError('boundary action differs')
        if overlap:boundaries+=1
    # A finite union of closed polygons contained in full-dimensional F is
    # closed. A nonempty relative complement has positive area. Equal exact
    # area plus no interior overlap therefore also covers every boundary point.
    return dict(status='verified-exact-fixture',regions=len(record['regions']),shared_boundaries=boundaries,
        area=area(fv),coverage='closed finite union, containment, exact area and disjoint interiors; no finite-sample inference')


def geometric_record():
    r=Q(1,8);terminal=target();robust_terminal=target(1-2*r,1)
    a=1-2*r
    inner=[(Q(1),Q(0),a/4),(Q(-1),Q(0),a/4),(Q(0),Q(1),a/4),(Q(0),Q(-1),a/4)]
    outer=[(Q(1),Q(0),2*a+1),(Q(-1),Q(0),2*a+1),(Q(0),Q(1),a+1),(Q(0),Q(-1),a+1)]
    targets={'T':terminal,'T_robust':robust_terminal,'inner_target_box':inner,'outer_target_box':outer}
    rows=dict(targets,nominal_pre_T=predecessor(terminal),nominal_pre_T_robust=predecessor(robust_terminal),
        robust_pre_T_robust=predecessor(robust_terminal,r),robust_pre_inner=predecessor(inner,r),robust_pre_outer=predecessor(outer,r))
    return dict(radius=r,sets={name:dict(rows=hs,vertices=vertices(hs)) for name,hs in rows.items()},
        original_T_not_robust=dict(state=[2,-1],control=0,disturbance=-r,successor=[1,-1-r]),
        semantics='nominal exists-u; robust exists-u forall independent w; target-box containment is not invariance')


def check_geometry(record):
    r=record['radius'];sets=record['sets']
    if r!=Q(1,8):raise ValueError('unreviewed disturbance radius')
    expected=geometric_record()
    if record!=expected:raise ValueError('geometry source/quantifier binding mismatch')
    inclusions=[('T_robust','T'),('inner_target_box','T_robust'),('T_robust','outer_target_box'),
        ('robust_pre_inner','robust_pre_T_robust'),('robust_pre_T_robust','robust_pre_outer'),
        ('robust_pre_T_robust','nominal_pre_T_robust'),('nominal_pre_T_robust','nominal_pre_T')]
    for inner,outer in inclusions:
        if not contained(sets[inner]['vertices'],sets[outer]['rows']):raise ValueError('whole-set inclusion fails')
    for name,radius in [('T',Q(0)),('T_robust',r)]:
        for p,v in sets[name]['vertices']:
            u=-p-2*v
            if abs(u)>1 or not contained([(p,v)],X):raise ValueError('terminal policy violates physical constraints')
            for w in (-radius,radius):
                if not contained([(p+v,v+u+w)],sets[name]['rows']):raise ValueError('whole-successor terminal invariance fails')
    c=record['original_T_not_robust'];p,v=c['state'];u=c['control'];w=c['disturbance']
    if c['successor']!=[p+v,v+u+w] or contained([c['successor']],sets['T']['rows']):raise ValueError('invalid robust-invariance counterexample')
    return dict(status='verified-exact-fixture',whole_set_inclusions=inclusions,
        invariant=['T under nominal K','T_robust under K forall w'],
        target_box_policy='only inner/outer containment; boxes not certified invariant')


def fiber_ladder(limit=1000):
    rows=[]
    for n in (1,2,4,8,12,16):
        begin=perf_counter_ns();count=1 if n==1 else comb(n,n//2)
        row=dict(horizon=n,control_facets=2*n,terminal_equalities=1,exact_vertex_count=count,
            selector_regions=3,scaling_velocity_domain=[-n-1,n+1],
            selector='ui=clamp(-v/N,-1,1), minimum-norm tie break',
            vertex_budget=limit,status='refused-output-budget' if count>limit else 'completed')
        if count<=limit:
            points=[[Q(0)]] if n==1 else [[Q(1) if j in plus else Q(-1) for j in range(n)] for plus in combinations(range(n),n//2)]
            if len(points)!=count or any(sum(p)!=0 or any(abs(x)>1 for x in p) for p in points):raise ValueError('cube-slice enumeration fails')
            row['vertices']=points
        row['construction_ns']=perf_counter_ns()-begin;rows.append(row)
    return dict(rows=rows,scope='full optimal control cube slice at v0=0; even N vertices are balanced sign vectors; no region-explosion claim',
        nonunique_N2=dict(domain=[[-3,3],[-2,2]],negative_velocity=dict(v=[-2,0],lower='-v-1',upper='1'),
            positive_velocity=dict(v=[0,2],lower='-1',upper='1-v'),selector='u0=u1=-v/2',value=0,
            proof='sum u=-v is feasible for all |v|<=2 and attains nonnegative terminal velocity squared zero',
            safety_limit='intermediate states are unconstrained; initial-domain X is not an invariant set under this selector'))


def check_fibers(record):
    if [r['horizon'] for r in record['rows']]!=[1,2,4,8,12,16]:raise ValueError('fiber horizon inventory changed')
    for row in record['rows']:
        n=row['horizon'];count=1 if n==1 else comb(n,n//2)
        if row['exact_vertex_count']!=count or row['control_facets']!=2*n or row['terminal_equalities']!=1:
            raise ValueError('fiber size identity changed')
        if count>row['vertex_budget']:
            if row['status']!='refused-output-budget' or 'vertices' in row:raise ValueError('fiber budget refusal was promoted')
        else:
            points=row['vertices']
            if row['status']!='completed' or len(points)!=count or len(set(map(tuple,points)))!=count:
                raise ValueError('fiber enumeration completeness/count mismatch')
            for p in points:
                if len(p)!=n or sum(p)!=0 or (n==1 and p!=[0]) or (n>1 and any(abs(x)!=1 for x in p)):
                    raise ValueError('fiber vertex invalid')
    return dict(status='verified-exact-fixture',scope='even-dimensional cube slice: at least N-1 active box faces force the last coordinate to +/-1; balanced sign count proves completeness at v0=0')


def build():
    begin=perf_counter_ns();regions=region_record();geometry=geometric_record();ladder=fiber_ladder();constructed=perf_counter_ns()
    checks=dict(regions=check_regions(regions),geometry=check_geometry(geometry),fibers=check_fibers(ladder));checked=perf_counter_ns()
    # Measure actual whole-domain location/evaluation, separately from construction.
    points=vertices(predecessor(target()))+[(Q(0),Q(0))];cost=[]
    for _ in range(6):
        start=perf_counter_ns()
        for point in points:
            matches=[sum(x*y for x,y in zip(r['control'],(*point,1))) for r in regions['regions'] if contained([point],r['rows'])]
            if not matches or len(set(matches))!=1:raise ValueError('point location inconsistent')
        cost.append(perf_counter_ns()-start)
    return dict(schema='csl.mpc08-exact-regions/1',regions=regions,geometry=geometry,fibers=ladder,checks=checks,
        costs=dict(construction_ns=constructed-begin,independent_check_ns=checked-constructed,
            point_location_ns=cost,point_location_queries_per_batch=len(points),first_batch='warmup; remaining five descriptive repetitions'),
        limitations=['fixture-specific rational oracle; not MPT3 execution','reference proofs do not promote CSL candidate samples',
            'fiber vertex growth is not critical-region growth','no performance ranking or general feedback-winning set'])

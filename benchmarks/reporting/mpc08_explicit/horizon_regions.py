"""Exact original-terminal-quadratic endpoint cells and full control fibers.

Bounded two-state fixture only. No general parametric-QP or CSL verifier claim.
"""
from fractions import Fraction as Q
from itertools import combinations, product
from time import perf_counter_ns
import exact_regions as E
import explicit_double_integrator as clipper


def affine_sum(*terms):
    return tuple(sum((factor*form[k] for factor,form in terms),Q(0)) for k in range(3))


def at(form,point):return sum(a*b for a,b in zip(form,(*point,1)))


def nonnegative(form):return (-form[0],-form[1],form[2])


def endpoint_rows(n):
    # Every generator direction (k,1) supplies a perpendicular facet normal.
    rows=[]
    for k in range(n):
        bound=sum(abs(j-k) for j in range(n))
        for sign in (-1,1):
            a,b=Q(sign),Q(-sign*k)
            rows.append((a,b,(a,a*n+b,Q(bound))))
    rows.extend((a,b,(Q(0),Q(0),c)) for a,b,c in E.target())
    return rows


def feasible_domain(n):
    # Independent V-construction: enumerate all box corners, then Minkowski T-Z.
    controls=E.hull([(sum(Q(n-1-j)*u[j] for j in range(n)),sum(u)) for u in product((-1,1),repeat=n)])
    endpoint_sum=E.hull([(t[0]-z[0],t[1]-z[1]) for t in E.vertices(E.target()) for z in controls])
    initial=[(p-n*v,v) for p,v in endpoint_sum]
    poly=E.hull(initial)
    return clipper.intersect(poly,E.X)


def produce(n):
    if n not in (2,4,8):raise ValueError('unsupported horizon; exhaustive endpoint reference cap is N8')
    started=perf_counter_ns();rows=endpoint_rows(n);zero=(Q(0),)*3
    candidates=[dict(active=[],endpoint=[zero,zero],multipliers=[])]
    for i,(a,b,rhs) in enumerate(rows):
        norm=a*a+b*b
        candidates.append(dict(active=[i],endpoint=[affine_sum((a/norm,rhs)),affine_sum((b/norm,rhs))],multipliers=[affine_sum((-1/norm,rhs))]))
    for i,j in combinations(range(len(rows)),2):
        a,b,r=rows[i];c,d,s=rows[j];det=a*d-b*c
        if not det:continue
        z=[affine_sum((d/det,r),(-b/det,s)),affine_sum((-c/det,r),(a/det,s))]
        candidates.append(dict(active=[i,j],endpoint=z,multipliers=[affine_sum((-d/det,z[0]),(c/det,z[1])),affine_sum((b/det,z[0]),(-a/det,z[1]))]))
    cells=[];empty=0;boundary_only=0
    box=[(Q(-3),Q(-2)),(Q(3),Q(-2)),(Q(3),Q(2)),(Q(-3),Q(2))]
    for candidate in candidates:
        z=candidate['endpoint'];hs=list(E.X)
        for a,b,rhs in rows:
            f=affine_sum((a,z[0]),(b,z[1]),(-1,rhs));hs.append((f[0],f[1],-f[2]))
        hs.extend(nonnegative(lam) for lam in candidate['multipliers'])
        poly=clipper.intersect(box,hs)
        if not poly:empty+=1;continue
        if not E.area(poly):boundary_only+=1;continue
        cells.append(dict(**candidate,rows=hs,vertices=poly))
    return dict(horizon=n,cells=cells,candidates=len(candidates),empty=empty,boundary_only=boundary_only,
                feasible_vertices=feasible_domain(n),construction_ns=perf_counter_ns()-started,
                family=produce_family(n))


def check(record):
    n=record['horizon']
    if n not in (2,4,8):raise ValueError('unsupported horizon')
    rows=endpoint_rows(n);expected=feasible_domain(n)
    if E.hull(record['feasible_vertices'])!=E.hull(expected):raise ValueError('independent Minkowski feasible domain differs')
    family=record['family']
    if family!=produce_family(n):raise ValueError('complete control-fiber map/model differs')
    total=Q(0);checked=[]
    for cell in record['cells']:
        polygon=E.vertices(cell['rows'])
        if E.hull(cell['vertices'])!=polygon or E.area(polygon)<=0:raise ValueError('cell H/V mismatch')
        for point in polygon:
            if any((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])<0
                   for a,b in zip(E.hull(expected),E.hull(expected)[1:]+E.hull(expected)[:1])):
                raise ValueError('cell outside independently constructed feasible domain')
        # All constraints below are affine identities/inequalities in parameters.
        for point in polygon:
            z=[at(f,point) for f in cell['endpoint']];lam=[at(f,point) for f in cell['multipliers']]
            if len(lam)!=len(cell['active']) or any(l<0 for l in lam):raise ValueError('negative or malformed KKT multiplier')
            if any(a*z[0]+b*z[1]>at(rhs,point) for a,b,rhs in rows):raise ValueError('endpoint infeasible')
            for i in cell['active']:
                a,b,rhs=rows[i]
                if a*z[0]+b*z[1]!=at(rhs,point):raise ValueError('active equality fails')
            if any(z[k]+sum(l*rows[i][k] for l,i in zip(lam,cell['active']))!=0 for k in range(2)):
                raise ValueError('endpoint stationarity fails')
        total+=E.area(polygon);checked.append(polygon)
    overlap=0
    for i,j in combinations(range(len(checked)),2):
        intersection=E.vertices(record['cells'][i]['rows']+record['cells'][j]['rows'])
        if E.area(intersection):raise ValueError('positive-area duplicate KKT cells require explicit union accounting')
        for point in intersection:
            if [at(f,point) for f in record['cells'][i]['endpoint']]!=[at(f,point) for f in record['cells'][j]['endpoint']]:raise ValueError('boundary endpoint differs')
        overlap+=bool(intersection)
    if total!=E.area(expected):raise ValueError('full feasible-domain coverage differs')
    return dict(status='verified-exact-fixture',horizon=n,cells=len(checked),area=total,shared_boundaries=overlap,
                proof='exact feasible-domain Minkowski construction; closed KKT cells cover by area with disjoint interiors; strict convex endpoint gives complete affine control slice',
                scope='endpoint-map cells, not necessarily minimal maximal critical regions; no CSL original-quadratic verifier claim')


def produce_family(n):
    return dict(coordinates='u0,...,uN-1; all intermediate states follow uniquely from dynamics',lower=[-1]*n,upper=[1]*n,
                terminal_map=[[n-1-j for j in range(n)],[1]*n],rhs='unique endpoint affine map minus (p+N*v,v)',
                objective='||xN||^2; no running cost',intermediate_states='unconstrained',initial_domain=[[-3,3],[-2,2]],terminal_rows=E.target())


if __name__=='__main__':
    for n in (2,4,8):
        record=produce(n);print(check(record))

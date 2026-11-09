"""Independent exact-dyadic family and witness checks for REVIEW-05 queries."""
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scalar_query_oracle import number,verify_history


def _rows(h,horizon):
    width=2*horizon+1
    if horizon not in (2,4,8) or h['dimension']!=width:raise ValueError('unsupported relation dimensions')
    result=[]
    for matrix,bounds,equality in ((h['equalities'],h['equality_values'],True),(h['inequalities'],h['upper_bounds'],False)):
        if len(matrix)!=len(bounds):raise ValueError('relation row count mismatch')
        for row,bound in zip(matrix,bounds):
            if len(row)!=width:raise ValueError('relation width mismatch')
            result.append(([number(x) for x in row],number(bound),equality))
    return result


def _feasible(rows,width):
    """Bounded rational Gaussian substitution then strict Fourier-Motzkin."""
    eq=[(a[:],b) for a,b,e,_ in rows if e]
    ine=[(a[:],b,s) for a,b,e,s in rows if not e]
    budget=0
    while eq:
        a,b=eq.pop(0)
        pivot=next((i for i,x in enumerate(a) if x),None)
        if pivot is None:
            if b:return False
            continue
        divisor=a[pivot];a=[x/divisor for x in a];b/=divisor
        def substitute(c,d):
            nonlocal budget
            factor=c[pivot];budget+=width
            if budget>5000000:raise ValueError('exact oracle operation budget exhausted')
            return ([x-factor*y for x,y in zip(c,a)],d-factor*b)
        eq=[substitute(c,d) for c,d in eq]
        ine=[(*substitute(c,d),s) for c,d,s in ine]
    remaining=set(range(width))
    while True:
        unique={}
        for a,b,s in ine:
            first=next((abs(x) for x in a if x),None)
            if first is None:
                if b<0 or (b==0 and s):return False
                continue
            a=tuple(x/first for x in a);b/=first
            if any(x.numerator.bit_length()>8192 or x.denominator.bit_length()>8192 for x in (*a,b)):
                raise ValueError('exact oracle integer budget exhausted')
            old=unique.get(a)
            if old is None or b<old[0] or (b==old[0] and s):unique[a]=(b,s)
        ine=[(list(a),b,s) for a,(b,s) in unique.items()]
        if not ine:return True
        active=[i for i in remaining if any(a[i] for a,_,_ in ine)]
        if not active:return True
        pivot=min(active,key=lambda i:sum(a[i]>0 for a,_,_ in ine)*sum(a[i]<0 for a,_,_ in ine))
        remaining.remove(pivot)
        pos=[r for r in ine if r[0][pivot]>0];neg=[r for r in ine if r[0][pivot]<0]
        out=[r for r in ine if r[0][pivot]==0]
        if len(pos)*len(neg)+len(out)>100000:raise ValueError('exact oracle row budget exhausted')
        for a,b,s in pos:
            for c,d,t in neg:
                budget+=width
                if budget>5000000:raise ValueError('exact oracle operation budget exhausted')
                p,q=a[pivot],-c[pivot]
                out.append(([x/p+y/q for x,y in zip(a,c)],b/p+d/q,s or t))
        ine=out


def verify_family(h,horizon,terminal_coefficient):
    if terminal_coefficient not in (0,1):raise ValueError('unsupported fixture objective')
    rows=_rows(h,horizon);width=2*horizon+1
    # The literal feasible family is the affine image of the unit control cube.
    # All its vertices suffice for inclusion in a convex H relation.
    vertices=product((0,1),repeat=horizon) if terminal_coefficient==0 else [(0,)*horizon]
    for controls in vertices:
        point=[Fraction(0)]
        for u in controls:point.append(point[-1]+u)
        point.extend(map(Fraction,controls))
        for a,b,equality in rows:
            value=sum(x*y for x,y in zip(a,point))
            if (value!=b if equality else value>b):raise ValueError('relation omits an optimal literal history')
    expected=[]
    def row(terms,b=0,equality=False):
        a=[Fraction(0)]*width
        for i,v in terms.items():a[i]=Fraction(v)
        expected.append((a,Fraction(b)))
        if equality:expected.append(([-x for x in a],Fraction(-b)))
    row({0:1},equality=True)
    for k in range(horizon):
        row({k+1:1,k:-1,horizon+1+k:-1},equality=True)
        row({horizon+1+k:1},1);row({horizon+1+k:-1})
    if terminal_coefficient:row({horizon:1})
    for a,b in expected:
        violation=([-x for x in a],-b,False,True)
        normalized=[(x,y,e,False) for x,y,e in rows]+[violation]
        if _feasible(normalized,width):raise ValueError('relation includes histories outside the literal optimizer family')
    return True

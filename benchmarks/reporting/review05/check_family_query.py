"""Independent exact-dyadic family and witness checks for REVIEW-05 queries."""
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scalar_query_oracle import number,verify_history


class OracleBudget(RuntimeError):
    """Exact oracle stopped without making a mathematical decision."""


def _rows(h,horizon):
    width=2*horizon+1
    if horizon not in (2,4,8) or h['dimension']!=width:raise ValueError('unsupported relation dimensions')
    if len(h['equalities'])+len(h['inequalities'])>100000:raise OracleBudget('exact oracle initial row budget exhausted')
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
            if budget>5000000:raise OracleBudget('exact oracle operation budget exhausted')
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
                raise OracleBudget('exact oracle integer budget exhausted')
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
        if len(pos)*len(neg)+len(out)>100000:raise OracleBudget('exact oracle row budget exhausted')
        for a,b,s in pos:
            for c,d,t in neg:
                budget+=width
                if budget>5000000:raise OracleBudget('exact oracle operation budget exhausted')
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


def verify_query(witness,direction,horizon,terminal_coefficient):
    verify_history(witness['states'],witness['controls'],witness['original_objective'],horizon,terminal_coefficient)
    if len(direction)!=horizon:raise ValueError('direction width mismatch')
    direction=list(map(number,direction))
    actual=sum(d*number(u[0]) for d,u in zip(direction,witness['controls']))
    optimum=sum(min(Fraction(0),d) for d in direction) if terminal_coefficient==0 else Fraction(0)
    if actual!=optimum:raise ValueError('witness does not attain its associated direction minimum')
    return True


def verify_attempt(record,scenario,scenario_hash):
    """Bind one structured raw record to a literal fixture and actual query calls."""
    import struct
    import time
    started=time.perf_counter_ns()
    t=scenario['horizon'];coefficient=scenario['objective']['coefficients'][0]
    if t not in (2,4,8) or coefficient not in (0,1):raise ValueError('unsupported fixture')
    if (scenario['model']!={'kind':'linear_discrete','A':[[1]],'B':[[1]]} or
        scenario['initial_state']!=[0] or scenario['controls']!={'kind':'box','lower':[0],'upper':[1]} or
        scenario['objective']!={'kind':'linear','coefficients':[coefficient]}):raise ValueError('fixture differs from literal oracle')
    if record['schema']!='csl.review05.family-query/1' or record['scenario_sha256']!=scenario_hash or record['horizon']!=t:
        raise ValueError('raw record/fixture binding mismatch')
    expected_fixture='HORIZON-01' if coefficient else 'FAMILY-QUERY-FLAT'
    if record['fixture']!=expected_fixture or record['target']!='exact_optimal_relation':raise ValueError('fixture/target mismatch')
    profiles={'csl.synthesis.reach-back':'strategy-a.nominal-linear-exact-v1','csl.synthesis.strategy-b':'strategy-b.nominal-linear-exact-v1'}
    if record['profile']!=profiles.get(record['strategy']):raise ValueError('strategy/profile binding mismatch')
    if record.get('termination')!='completed' or record.get('selector_termination')!='completed':
        return {'status':'inconclusive','reason':'retained noncompleted/refused synthesis or query'}
    if not record['family_registry_verified'] or record['outcome']!='optimal' or record['objective_lower']!=0 or record['objective_upper']!=0:
        raise ValueError('completed family lacks original optimality binding')
    binding=record['family_binding']
    if any(binding[key]!=record[key] for key in ('problem_id','profile','strategy','strategy_version')) or not record['selector_source_bound']:
        raise ValueError('family/selector source binding mismatch')
    verifier='csl.verifier.strategy-a.nominal-linear-exact' if record['strategy']=='csl.synthesis.reach-back' else 'csl.verifier.strategy-b.nominal-linear-exact'
    if record['compiled_verifier']['id']!=verifier or record['compiled_verifier']['version']!='1':raise ValueError('compiled verifier binding mismatch')
    verify_family(record['relation'],t,coefficient)
    family_ns=time.perf_counter_ns()-started
    witnesses=record['witnesses'];directions=record['directions']
    expected_directions=[]
    for k in range(t):
        d=[0]*t;d[k]=1;expected_directions.append(d);d=d[:];d[k]=-1;expected_directions.append(d)
    if directions!=expected_directions:raise ValueError('direction request differs from pinned basis schedule')
    if record['requested_witnesses']!=(1 if coefficient else 2*t):raise ValueError('witness request scope mismatch')
    if record['returned_witnesses']!=len(witnesses) or not witnesses:raise ValueError('witness count mismatch')
    if len(witnesses)>len(directions):raise ValueError('more witnesses than executed directions')
    replay_start=time.perf_counter_ns()
    for i,witness in enumerate(witnesses):
        if witness['problem_id']!=record['problem_id']:raise ValueError('witness problem binding mismatch')
        verify_query(witness,directions[i],t,coefficient)
    if coefficient and len(witnesses)!=1:raise ValueError('zero optimizer query must stop at requested one witness')
    if not coefficient and (len(witnesses)!=2*t or record['distinct_witnesses']<2):raise ValueError('constant fixture needs all queries and distinct histories')
    if not record['literal_replay_ok']:raise ValueError('driver literal replay failed')
    if record['instrumented']:
        observed=[s for s in record['selector_timing']['spans'] if s['operation']=='selector.lp.direction-query' and s['completed']]
        if len(observed)!=len(witnesses):raise ValueError('actual LP span/witness count mismatch')
        for i,span in enumerate(observed):
            bits=[str(struct.unpack('Q',struct.pack('d',float(x)))[0]) for x in directions[i]]
            expected='witness-selector-direction/'+str(i)+'/'+'/'.join(bits)
            if span['query']!=i or span['program']!=expected or span['termination']!='completed' or span['ticks'] is None or span['ticks']<0 or span['input_size']!=2*t+1 or span['output_size']!=2*t+1:
                raise ValueError('actual LP observation lacks matching program/query/size binding')
    return {'status':'verified','family_check_ns':family_ns,'independent_query_replay_ns':time.perf_counter_ns()-replay_start,
        'scope':'exact dyadic both-direction optimizer-family inclusion plus literal history and associated direction minimum; numerical driver assurance remains numerical'}


def check_process(receipt,stdout,scenario,scenario_hash):
    """A process stop is missing evidence, never a mathematical counterexample."""
    if receipt['returncode']!=0 or receipt['timed_out']:
        return {'status':'inconclusive','reason':'failed or timed-out process; mathematical result unestablished'}
    try:
        record=json.loads(stdout)
        if 'strategy' in receipt and receipt['strategy']!=record['strategy']:
            raise ValueError('raw record/receipt strategy binding mismatch')
        if 'mode' in receipt and (receipt['mode']=='on')!=record['instrumented']:
            raise ValueError('raw record/receipt collector-mode binding mismatch')
        return verify_attempt(record,scenario,scenario_hash)
    except OracleBudget as error:
        return {'status':'inconclusive','reason':str(error)}
    except (KeyError,ValueError,TypeError,IndexError,ZeroDivisionError) as error:
        return {'status':'incorrect','reason':str(error)}


def main():
    import argparse,hashlib
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args()
    results=[]
    for path in sorted((args.bundle/'attempts').glob('*/receipt.json')):
        receipt=json.loads(path.read_text());row={'attempt':str(path.parent.relative_to(args.bundle))}
        try:
            raw=(path.parent/'stdout.txt').read_bytes();stderr=(path.parent/'stderr.txt').read_bytes()
            if Path(receipt['scenario']).name!=receipt['scenario']:raise ValueError('unsafe scenario receipt path')
            scenario_path=args.bundle/'scenarios'/receipt['scenario']
            row['bindings']={'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'stdout_sha256':hashlib.sha256(raw).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest(),
                'scenario_sha256':hashlib.sha256(scenario_path.read_bytes()).hexdigest() if scenario_path.is_file() else None}
            if receipt['stdout_sha256']!=hashlib.sha256(raw).hexdigest() or receipt['stderr_sha256']!=hashlib.sha256(stderr).hexdigest():
                raise ValueError('raw stdout/stderr digest mismatch')
            if receipt['returncode']!=0 or receipt['timed_out']:
                row.update(check_process(receipt,raw,None,None))
            else:
                if Path(receipt['scenario']).name!=receipt['scenario']:raise ValueError('unsafe scenario receipt path')
                scenario_path=args.bundle/'scenarios'/receipt['scenario'];scenario=json.loads(scenario_path.read_text())
                row.update(check_process(receipt,raw,scenario,hashlib.sha256(scenario_path.read_bytes()).hexdigest()))
        except (OSError,KeyError,ValueError,TypeError) as error:
            row.update(status='incorrect',reason=str(error))
        results.append(row)
    errors=sum(x['status']=='incorrect' for x in results)
    (args.bundle/'checks.json').write_text(json.dumps({'schema':'csl.review05.family-query-checks/1',
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'attempts':results},indent=2)+'\n')
    print(json.dumps({'attempts':len(results),'incorrect':errors,'verified':sum(x['status']=='verified' for x in results),'inconclusive':sum(x['status']=='inconclusive' for x in results)}))
    return int(errors>0 or not results)

if __name__=='__main__':raise SystemExit(main())

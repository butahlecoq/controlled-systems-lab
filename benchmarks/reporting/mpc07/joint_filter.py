"""Independent joint diagonal-filter specialization of Chen v3 (24),(26),(36)."""
from fractions import Fraction as Q
import hashlib
import json
import math
from benchmarks.reporting.mpc07 import policy

EPS=Q(1,64)
RHO=Q(1,1024)
KINDS=('fixed-plan','fixed-gain','joint','fixed-filter')


def admitted(n,kind):
    if type(n) is not int or n not in (2,4,8) or kind not in KINDS:raise ValueError('unsupported joint-filter profile')


def oracle(n,kind):
    admitted(n,kind)
    if kind=='joint':bound=(1+EPS)**(n-1)
    elif kind=='fixed-plan':bound=sum((1+EPS)**k for k in range(n))
    elif kind=='fixed-gain':bound=sum((1-Q(1,16)+EPS)**k for k in range(n))
    else:bound=Q(5,4)*n-(n-1)
    return bound**2


def canonical(n):
    admitted(n,'joint')
    s=[[RHO,Q(1) if t==0 else 1+EPS*(1+EPS)**(t-1)] for t in range(n)]
    h=[[Q(0)]*(2*n) for _ in range(n)]
    for t in range(1,n):h[t][2*(t-1)+1]=Q(-1)
    return s,h


def check_policy(n,kind,s,h):
    """Exact response/filter induction independent of LP coefficients/auxiliaries."""
    admitted(n,kind)
    if len(s)!=n or any(len(row)!=2 for row in s) or len(h)!=n or any(len(row)!=2*n for row in h):
        raise ValueError('filter/policy dimensions differ')
    s=[list(map(Q,row)) for row in s];h=[list(map(Q,row)) for row in h]
    response=[[Q(0)]*(2*n) for _ in range(2)];responses=[response];supports=[]
    for t in range(n):
        if any(h[t][j] for j in range(2*t,2*n)):raise ValueError('noncausal normalized-disturbance access')
        if s[t][0]<RHO or s[t][1]<1:raise ValueError('noninvertible or inadmissible filter')
        if s[t][1]<1+EPS*sum(map(abs,response[1])):raise ValueError('uncertainty containment violated')
        if sum(map(abs,h[t]))>1:raise ValueError('robust control bound violated')
        if kind=='fixed-plan' and any(h[t]):raise ValueError('fixed-plan class differs')
        if kind=='fixed-gain' and h[t]!=[-Q(1,16)*value for value in response[1]]:raise ValueError('fixed gain differs')
        if kind=='fixed-filter' and s[t]!=[RHO,Q(5,4)]:raise ValueError('fixed filter differs')
        response=[[response[0][j]+response[1][j]+h[t][j]/2+(s[t][0] if j==2*t else 0) for j in range(2*n)],
                  [response[1][j]+h[t][j]+(s[t][1] if j==2*t+1 else 0) for j in range(2*n)]]
        bounds=[sum(map(abs,row)) for row in response]
        if bounds[0]>64 or bounds[1]>16:raise ValueError('robust state bound violated')
        responses.append(response);supports.append(bounds)
    bound=sum(map(abs,response[1]));lower=oracle(n,kind)
    return dict(virtual_terminal_absolute=bound,virtual_terminal_squared=bound**2,virtual_profile_oracle_squared=lower,physical_unrestricted_lower_squared=oracle(n,'joint'),
        upper_minus_virtual_profile_oracle_squared=bound**2-lower,
        upper_minus_physical_lower_squared=bound**2-oracle(n,'joint'),state_responses=responses,state_supports=supports,
        filter=s,normalized_policy=h,physical_information='zeta past=diag(s)^-1*(x_next-A*x-B*u); current/future zeta forbidden')


def program(n,kind):
    admitted(n,kind);b=policy.LinearBuilder();add=policy.add
    s=[[b.variable(f's-{t}-p',RHO,RHO if kind=='fixed-filter' else None),
        b.variable(f's-{t}-q',Q(5,4) if kind=='fixed-filter' else 1,Q(5,4) if kind=='fixed-filter' else None)] for t in range(n)]
    h=[[b.variable(f'H-{t}-{j}',0 if kind=='fixed-plan' else None,0 if kind=='fixed-plan' else None) if j<2*t else {}
        for j in range(2*n)] for t in range(n)]
    coordinates=dict(filter=[[next(iter(form)) for form in row] for row in s],
        control=[[next(iter(form)) if form else None for form in row] for row in h],state_response=[])
    response=[[{} for _ in range(2*n)] for _ in range(2)]
    for t in range(n):
        # Paper(36), zero subdiagonals, scalar uncertain lower-right A entry.
        enclosure=b.support({},response[1][:2*t],Q(1),f'enclosure-{t}')
        b.row(add((EPS,enclosure),(-1,s[t][1])),upper=-1)
        if kind=='fixed-gain':
            for j in range(2*t):b.row(add((1,h[t][j]),(Q(1,16),response[1][j])),0,0)
        b.row(b.support({},h[t][:2*t],Q(1),f'control-{t}'),upper=1)
        next_r=[[add((1,response[0][j]),(1,response[1][j]),(Q(1,2),h[t][j]),(1,s[t][0] if j==2*t else {})) for j in range(2*n)],
                [add((1,response[1][j]),(1,h[t][j]),(1,s[t][1] if j==2*t+1 else {})) for j in range(2*n)]]
        current=[[b.variable(f'R-{t+1}-{k}-{j}') if j<2*(t+1) else {} for j in range(2*n)] for k in range(2)]
        for k in range(2):
            for j in range(2*(t+1)):b.row(add((1,current[k][j]),(-1,next_r[k][j])),0,0)
            b.row(b.support({},current[k][:2*(t+1)],Q(1),f'state-{t+1}-{k}'),upper=(64,16)[k])
        response=current;coordinates['state_response'].append([[next(iter(form)) if form else None for form in row] for row in current])
    bound=b.variable('worst-terminal-absolute',0);coordinates['bound']=next(iter(bound))
    b.row(add((1,b.support({},response[1],Q(1),'terminal')),(-1,bound)),upper=0)
    offsets=[0];columns=[];values=[]
    for row in b.rows:
        for index,value in sorted(row.items()):columns.append(index);values.append(float(value))
        offsets.append(len(values))
    size=len(b.names);linear=[0.]*size;linear[coordinates['bound']]=1.
    plain=lambda rows:[[None if x is None else float(x) for x in row] for row in rows]
    p=dict(schema='csl.mpc11.affine-program/1',case_id=f'MPC07-joint-filter-T{n:02d}-{kind}',program_id=f'mpc07-joint-filter-{n}-{kind}',
        formulation='Chen-v3-joint-block-diagonal-filter-specialization-physical-q-uncertainty',q_diagonal=[0.]*size,
        linear=linear,offset=0.,variables=plain(b.variables),rows=plain(b.bounds),
        constraints=dict(rows=len(b.rows),row_offsets=offsets,column_indices=columns,values=values),coordinates=coordinates,
        variable_names=b.names,profile=dict(horizon=n,policy_class=kind,physical_delta_bound=str(EPS),position_filter_floor=str(RHO),
            physical_w_bounds=[0,1],source_equations='arXiv2203.11375v3:(24),(26),(36),(37)-(39); block-diagonal restriction',
            objective='virtual worst terminal velocity absolute; square is certified physical worst-cost upper bound',
            x0=[0,0],initial_action=0,state_bounds=[64,16],input_bound=1))
    p['program_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();return p


def check_result(p,r):
    profile=p['profile'];n=profile['horizon'];kind=profile['policy_class']
    if p!=program(n,kind):raise ValueError('joint input differs from authored profile')
    if r.get('program_sha256')!=p['program_sha256'] or r.get('case_id')!=p['case_id']:raise ValueError('joint native binding differs')
    if r.get('termination')!='completed' or r.get('mathematical_outcome')!='optimal':return dict(status='inconclusive-native-outcome')
    primal=r.get('primal',[])
    if len(primal)!=len(p['variables']) or any(not math.isfinite(x) for x in primal):raise ValueError('joint primal dimensions/nonfinite')
    if r.get('contract_diagnostics'):raise ValueError('joint native contract diagnostics')
    csr=p['constraints']
    for row,(lower,upper) in enumerate(p['rows']):
        value=math.fsum(csr['values'][k]*primal[csr['column_indices'][k]] for k in range(csr['row_offsets'][row],csr['row_offsets'][row+1]))
        if (lower is not None and value<lower-1e-7) or (upper is not None and value>upper+1e-7):raise ValueError('joint numerical LP row violation')
    # Propose exact rationals; feasibility is accepted only after exact replay.
    rational=[Q(value).limit_denominator(2**48) for value in primal];c=p['coordinates']
    s=[[rational[i] for i in row] for row in c['filter']]
    h=[[rational[i] if i is not None else Q(0) for i in row] for row in c['control']]
    checked=check_policy(n,kind,s,h)
    maximum_response_adjustment=0.
    for t,indices in enumerate(c['state_response'],1):
        for component,row in enumerate(indices):
            for column,index in enumerate(row):
                original=primal[index] if index is not None else 0.
                exact=checked['state_responses'][t][component][column]
                difference=abs(float(exact)-original);maximum_response_adjustment=max(maximum_response_adjustment,difference)
                if difference>1e-10:raise ValueError('joint response reconstruction too far from native witness')
    if checked['upper_minus_virtual_profile_oracle_squared']<0:raise ValueError('joint candidate contradicts exact oracle')
    if abs(primal[c['bound']]**2-float(oracle(n,kind)))>1e-6:raise ValueError('joint native optimum differs from literal oracle')
    return dict(status='verified-joint-rational-policy',maximum_native_response_adjustment=maximum_response_adjustment,
                response_reconstruction='exact recurrence from reconstructed filter/control; raw response arrays unchanged',rationalization='new candidate limit_denominator(2**48), exact response/filter/support replay',**checked)

"""Authored scalar-disturbance ADF/response LPs and separate exact policy replay.

This bounded benchmark is not a public CSL feedback strategy or an author-code
port. Sigma>1 is a fixed conservative filter, not jointly optimized SLS-MPC.
"""
from fractions import Fraction as Q
import hashlib
import json
import math

KINDS=('fixed-plan','fixed-gain','adf','response')
HORIZONS=(2,4,8)
SIGMAS=(Q(1),Q(5,4))
POSITION_BOUND=Q(64)
VELOCITY_BOUND=Q(16)


def admitted(n,sigma,kind):
    if type(n) is not int or n not in HORIZONS or sigma not in SIGMAS or kind not in KINDS:
        raise ValueError('unsupported bounded MPC07 profile')


def oracle(n,sigma,kind):
    """Exact optimum squared terminal velocity for the virtual additive box."""
    sigma=Q(sigma);admitted(n,sigma,kind)
    if kind=='fixed-plan':bound=n*sigma
    elif kind=='fixed-gain':
        alpha=Q(1) if sigma==1 else Q(1,16)
        bound=sigma*sum((1-alpha)**k for k in range(n))
    else:bound=n*sigma-(n-1)
    return bound**2


def check_policy(n,sigma,kind,v,m):
    """Exact stored-rational policy replay, independent of LP rows/auxiliaries.

    At decision t only eta[0:t] has been reconstructed from past full states.
    Enclosure supports are exact affine-image box supports, not samples.
    """
    sigma=Q(sigma);admitted(n,sigma,kind)
    if len(v)!=n or len(m)!=n or any(len(row)!=n for row in m):raise ValueError('policy dimensions differ')
    v=list(map(Q,v));m=[list(map(Q,row)) for row in m]
    if v[0]!=0 or any(m[t][j]!=0 for t in range(n) for j in range(t,n)):
        raise ValueError('noncausal policy or nonzero initial action')
    offset=[Q(0),Q(0)];response=[[Q(0)]*n for _ in range(2)]
    offsets=[offset];responses=[response]
    alpha=Q(1) if sigma==1 else Q(1,16)
    for t in range(n):
        if abs(v[t])+sigma*sum(map(abs,m[t]))>1:raise ValueError('robust control bound violated')
        if kind=='fixed-plan' and any(m[t]):raise ValueError('fixed-plan class violated')
        if kind=='fixed-gain' and (v[t]!=-alpha*offset[1] or m[t]!=[-alpha*x for x in response[1]]):
            raise ValueError('fixed-gain class violated')
        offset=[offset[0]+offset[1]+v[t]/2,offset[1]+v[t]]
        response=[[response[0][j]+response[1][j]+m[t][j]/2 for j in range(n)],
                  [response[1][j]+m[t][j]+int(j==t) for j in range(n)]]
        for k,bound in enumerate((POSITION_BOUND,VELOCITY_BOUND)):
            if abs(offset[k])+sigma*sum(map(abs,response[k]))>bound:raise ValueError('robust state bound violated')
        offsets.append(offset);responses.append(response)
    terminal=abs(offset[1])+sigma*sum(map(abs,response[1]))
    return dict(worst_terminal_absolute=terminal,worst_terminal_squared=terminal**2,
                terminal_offset=offset,terminal_response=response,state_offsets=offsets,state_responses=responses)


# Linear-form builder: None is the constant; integer keys identify variables.
def add(*terms):
    result={}
    for factor,form in terms:
        for key,value in form.items():result[key]=result.get(key,Q(0))+Q(factor)*value
    return {key:value for key,value in result.items() if value}


class LinearBuilder:
    def __init__(self):self.names=[];self.variables=[];self.rows=[];self.bounds=[]
    def variable(self,name,lower=None,upper=None):
        index=len(self.names);self.names.append(name);self.variables.append([lower,upper]);return {index:Q(1)}
    def row(self,form,lower=None,upper=None):
        constant=form.get(None,Q(0));self.rows.append({k:v for k,v in form.items() if k is not None})
        self.bounds.append([None if lower is None else Q(lower)-constant,None if upper is None else Q(upper)-constant])
    def absolute(self,form,name):
        value=self.variable(name,0);self.row(add((1,form),(-1,value)),upper=0);self.row(add((-1,form),(-1,value)),upper=0);return value
    def support(self,nominal,response,sigma,name):
        terms=[(1,self.absolute(nominal,name+'-nominal'))]
        terms.extend((sigma,self.absolute(form,name+'-'+str(j))) for j,form in enumerate(response))
        return add(*terms)


def program(n,sigma,kind):
    sigma=Q(sigma);admitted(n,sigma,kind);b=LinearBuilder()
    v=[b.variable(f'v-{t}',0 if t==0 else None,0 if t==0 else None) for t in range(n)]
    m=[[b.variable(f'M-{t}-{j}',0 if kind=='fixed-plan' else None,0 if kind=='fixed-plan' else None)
        if j<t else {} for j in range(n)] for t in range(n)]
    coordinates={'v':[next(iter(form)) for form in v],
                 'M':[[next(iter(form)) if form else None for form in row] for row in m],
                 'state_offset':[],'state_response':[]}
    nominal=[[{},{}]];responses=[[[{} for _ in range(n)] for _ in range(2)]]
    alpha=Q(1) if sigma==1 else Q(1,16)
    for t in range(n):
        prev=nominal[-1];prev_r=responses[-1]
        if kind=='fixed-gain':
            b.row(add((1,v[t]),(alpha,prev[1])),0,0)
            for j in range(t):b.row(add((1,m[t][j]),(alpha,prev_r[1][j])),0,0)
        next_x=[add((1,prev[0]),(1,prev[1]),(Q(1,2),v[t])),add((1,prev[1]),(1,v[t]))]
        next_r=[[add((1,prev_r[0][j]),(1,prev_r[1][j]),(Q(1,2),m[t][j])) for j in range(n)],
                [add((1,prev_r[1][j]),(1,m[t][j]),(1,{None:Q(1)} if j==t else {})) for j in range(n)]]
        if kind=='response':
            # Explicit finite-horizon SLS recurrence for embedded scalar forcing E.
            current=[b.variable(f'xbar-{t+1}-{k}') for k in range(2)]
            current_r=[[b.variable(f'Phi-{t+1}-{k}-{j}') if j<=t else {} for j in range(n)] for k in range(2)]
            for k in range(2):
                b.row(add((1,current[k]),(-1,next_x[k])),0,0)
                for j in range(t+1):b.row(add((1,current_r[k][j]),(-1,next_r[k][j])),0,0)
            next_x,next_r=current,current_r
            coordinates['state_offset'].append([next(iter(form)) for form in current])
            coordinates['state_response'].append([[next(iter(form)) if form else None for form in row] for row in current_r])
        nominal.append(next_x);responses.append(next_r)
        b.row(b.support(v[t],m[t][:t],sigma,f'control-{t}'),upper=1)
        for k,bound in enumerate((POSITION_BOUND,VELOCITY_BOUND)):
            b.row(b.support(next_x[k],next_r[k][:t+1],sigma,f'state-{t+1}-{k}'),upper=bound)
    bound=b.variable('worst-terminal-absolute',0);coordinates['bound']=next(iter(bound))
    b.row(add((1,b.support(nominal[-1][1],responses[-1][1],sigma,'terminal')),(-1,bound)),upper=0)
    offsets=[0];columns=[];values=[]
    for row in b.rows:
        for index,value in sorted(row.items()):columns.append(index);values.append(float(value))
        offsets.append(len(values))
    size=len(b.names);linear=[0.]*size;linear[coordinates['bound']]=1.
    plain=lambda rows:[[None if x is None else float(x) for x in row] for row in rows]
    sigma_id=str(sigma).replace('/','over')
    result=dict(schema='csl.mpc11.affine-program/1',case_id=f'MPC07-T{n:02d}-sigma{sigma_id}-{kind}',
        program_id=f'mpc07-{n}-{sigma}-{kind}',formulation='MPC07-experimental-causal-box-support-linear-program',
        q_diagonal=[0.]*size,linear=linear,offset=0.,variables=plain(b.variables),rows=plain(b.bounds),
        constraints=dict(rows=len(b.rows),row_offsets=offsets,column_indices=columns,values=values),
        coordinates=coordinates,variable_names=b.names,profile=dict(horizon=n,sigma=str(sigma),policy_class=kind,
            state_bounds=[str(POSITION_BOUND),str(VELOCITY_BOUND)],initial=[0,0],initial_action=0,
            objective='minimize exact virtual-box max abs(qT); squared value is original terminal quadratic cost',
            model_uncertainty='none' if sigma==1 else 'delta velocity coefficient +/-1/64; fixed Q16 enclosure sigma5/4'))
    result['program_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result


def check_result(payload,result):
    profile=payload['profile']
    if payload!=program(profile['horizon'],Q(profile['sigma']),profile['policy_class']):
        raise ValueError('input differs from authored bounded formulation')
    if result.get('program_sha256')!=payload['program_sha256'] or result.get('case_id')!=payload['case_id']:
        raise ValueError('native result input binding mismatch')
    if result.get('termination')!='completed' or result.get('mathematical_outcome')!='optimal':
        return dict(status='unavailable-native-outcome',termination=result.get('termination'),outcome=result.get('mathematical_outcome'))
    primal=result.get('primal',[])
    if len(primal)!=len(payload['variables']) or any(not math.isfinite(x) for x in primal):raise ValueError('native primal dimensions/nonfinite')
    if result.get('contract_diagnostics') or max(result['primal_check'][key] for key in ('row_violation','variable_violation'))>1e-7:
        raise ValueError('native numerical contract/primal check failed')
    for value,(lower,upper) in zip(primal,payload['variables']):
        if (lower is not None and value<lower-1e-7) or (upper is not None and value>upper+1e-7):
            raise ValueError('independent numerical primal variable bound')
    csr=payload['constraints']
    for row,(lower,upper) in enumerate(payload['rows']):
        actual=math.fsum(csr['values'][k]*primal[csr['column_indices'][k]]
                         for k in range(csr['row_offsets'][row],csr['row_offsets'][row+1]))
        if (lower is not None and actual<lower-1e-7) or (upper is not None and actual>upper+1e-7):
            raise ValueError('independent numerical primal row bound')
    # This creates a NEW rational candidate; it is never labelled exact binary64.
    rational=[Q(x).limit_denominator(2**32) for x in primal]
    c=payload['coordinates'];v=[rational[i] for i in c['v']]
    m=[[rational[i] if i is not None else Q(0) for i in row] for row in c['M']]
    p=payload['profile'];n=p['horizon'];sigma=Q(p['sigma']);kind=p['policy_class']
    checked=check_policy(n,sigma,kind,v,m)
    if kind=='response':
        for t,indices in enumerate(c['state_offset'],1):
            if [rational[i] for i in indices]!=checked['state_offsets'][t]:raise ValueError('response nominal extraction mismatch')
        for t,indices in enumerate(c['state_response'],1):
            if [[rational[i] if i is not None else Q(0) for i in row] for row in indices]!=checked['state_responses'][t]:
                raise ValueError('response causal coordinate extraction mismatch')
    exact=oracle(n,sigma,kind)
    if checked['worst_terminal_squared']!=exact:raise ValueError('rational policy does not attain exact restricted virtual-box oracle')
    if abs(primal[c['bound']]**2-float(exact))>1e-6:raise ValueError('native objective differs from analytic oracle')
    return dict(status='verified-rational-reconstruction',policy_v=v,policy_M=m,oracle_squared=exact,
                rationalization='new candidate from limit_denominator(2**32), exact robust replay; raw binary64 unchanged',**checked)


def physical_vertices_two_step(v,m,epsilon=Q(1,64)):
    """Exact physical T2 vertices; affine-multilinear maps attain convex maxima here.

    Delta0 is immaterial because q0=0. Delta1 and both physical w endpoints are
    independent. This oracle is not transferred to larger arbitrary policies.
    """
    from itertools import product
    if len(v)!=2 or len(m)!=2:raise ValueError('physical vertex oracle is T2 only')
    rows=[]
    for w0,delta1,w1 in product((-Q(1),Q(1)),(-epsilon,epsilon),(-Q(1),Q(1))):
        q1=w0;u1=Q(v[1])+Q(m[1][0])*w0
        p2=q1+u1/2;q2=(1+delta1)*q1+u1+w1
        rows.append(dict(w0=w0,delta1=delta1,w1=w1,control=u1,terminal=[p2,q2],cost=q2*q2))
    return rows

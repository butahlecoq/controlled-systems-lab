"""Binary64 causal evaluation only; no synthesis, plant or disturbance access."""
from dataclasses import dataclass
from fractions import Fraction
import math


@dataclass(frozen=True)
class CompiledPolicy:
    horizon:int
    encoding:str
    offsets:tuple
    feedback:tuple
    filters:tuple


def prepare(profile):
    n=profile['horizon'];p=profile['policy'];encoding=profile['encoding']
    matrix=p['policy_M'] if encoding=='past-eta' else p['normalized_policy']
    offsets=p['policy_v'] if encoding=='past-eta' else ['0']*n
    filters=[] if encoding=='past-eta' else p['filter']
    convert=lambda rows:tuple(tuple(float(Fraction(v)) for v in row) for row in rows)
    result=CompiledPolicy(n,encoding,tuple(float(Fraction(v)) for v in offsets),convert(matrix),convert(filters))
    width=n if encoding=='past-eta' else 2*n
    if len(result.feedback)!=n or any(len(row)!=width for row in result.feedback):raise ValueError('policy shape')
    if any(result.feedback[t][j]!=0 for t in range(n) for j in range(t if encoding=='past-eta' else 2*t,width)):raise ValueError('noncausal coefficients')
    if len(result.offsets)!=n or any(not math.isfinite(v) for row in result.feedback for v in row):raise ValueError('nonfinite policy')
    if encoding not in ('past-eta','past-zeta'):raise ValueError('policy encoding')
    if encoding=='past-zeta' and (len(result.filters)!=n or any(len(row)!=2 or any(not math.isfinite(v) or v<=0 for v in row) for row in result.filters)):raise ValueError('nonpositive filter')
    return result


class CausalController:
    def __init__(self,compiled):
        self.policy=compiled;self.stage=0;self.history=[];self.previous=None;self.last_action=None;self.observed=None
    def observe(self,state):
        if self.observed is not None or self.stage>=self.policy.horizon:raise ValueError('observation order')
        if len(state)!=2 or any(not math.isfinite(v) for v in state):raise ValueError('finite two-state observation required')
        state=tuple(state);residual=None;innovation=None
        if self.previous is not None:
            p,q=self.previous;u=self.last_action
            residual=(state[0]-p-q-u/2,state[1]-q-u)
            if self.policy.encoding=='past-eta':self.history.append(residual[1])
            else:
                scale=self.policy.filters[self.stage-1]
                innovation=tuple(v/s for v,s in zip(residual,scale));self.history.extend(innovation)
        self.observed=state
        return residual,innovation
    def action(self):
        if self.observed is None or self.stage>=self.policy.horizon:raise ValueError('action order')
        row=self.policy.feedback[self.stage]
        value=self.policy.offsets[self.stage]+math.fsum(row[j]*v for j,v in enumerate(self.history))
        if not math.isfinite(value):raise ValueError('nonfinite action')
        self.previous=self.observed;self.observed=None;self.last_action=value;self.stage+=1
        return value

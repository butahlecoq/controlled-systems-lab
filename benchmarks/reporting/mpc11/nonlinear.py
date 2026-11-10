"""Scaled nonlinear plant execution and portable held-control requests."""
import math
import time
import numpy as np
import casadi as ca
from affine import canonical_hash, model


def make_request(scenario, controls, witness_sha256, *, sensitivity=False):
    n=scenario['time']['intervals'];nu=len(scenario['controls'])
    if len(controls)!=n or any(len(u)!=nu or not all(math.isfinite(v) for v in u) for u in controls):
        raise ValueError('complete finite physical control history required')
    settings=scenario['independent_replay']
    tol=settings['sensitivity'] if sensitivity else settings
    sub=settings['report_subintervals_per_hold']
    grid=scenario['time']['grid']
    times=[grid[k]+(grid[k+1]-grid[k])*j/sub for k in range(n) for j in range(sub)]+[grid[-1]]
    repeated=[list(u) for u in controls for _ in range(sub)]
    return {'schema':'csl.mpc11.nonlinear-request/1','scenario':scenario,
            'scenario_sha256':canonical_hash(scenario),'witness_sha256':witness_sha256,
            'controls_sha256':canonical_hash(controls),'hold':'constant-on-original-interval',
            'original_controls':controls,'controls':repeated,'times':times,
            'initial_scaled':[x['initial']/x['scale'] for x in scenario['states']],
            'abstol':tol['scaled_abstol'],'reltol':tol['reltol'],
            'max_attempts':settings['step_attempts_per_hold_interval']//sub,
            'report_subintervals_per_hold':sub}


def validate_request(request):
    s=request['scenario']
    regenerated=make_request(s,request['original_controls'],request['witness_sha256'],
                            sensitivity=request['abstol']==s['independent_replay']['sensitivity']['scaled_abstol'])
    for key in regenerated:
        if regenerated[key]!=request[key]:raise ValueError('request association mismatch: '+key)


def evaluate(scenario, physical_states, controls):
    """Original cost only on complete traces; sampled physical violations in physical units."""
    x=np.asarray(physical_states);u=np.asarray(controls);o=scenario['objective']
    bounds=np.asarray([v['physical_bounds'] for v in scenario['states']])
    violations=np.maximum(np.maximum(bounds[:,0]-x,x-bounds[:,1]),0).max(axis=0)
    cb=np.asarray([v['physical_bounds'] for v in scenario['controls']])
    uv=np.maximum(np.maximum(cb[:,0]-u,u-cb[:,1]),0).max(axis=0)
    complete=len(x)==scenario['time']['intervals']*scenario['independent_replay']['report_subintervals_per_hold']+1
    cost=None
    if complete:
        refs=np.asarray(model(scenario)['reference_commands'])
        terminal=float(np.sum(np.asarray(o['terminal_weights'])*((x[-1]-o['terminal_target'])/o['terminal_scale'])**2))
        running=float(o['running_weight']/scenario['time']['intervals']*np.sum(((u-refs)/o['running_scale'])**2))
        cost={'terminal':terminal,'running':running,'total':terminal+running}
    return {'objective':cost,'sampled_state_violation_physical':violations.tolist(),
            'control_violation_physical':uv.tolist()}


def execute_cvodes(request):
    validate_request(request)
    s=request['scenario'];scales=np.array([v['scale'] for v in s['states']]);p={k:v['value'] for k,v in s['parameters'].items()}
    initial=np.asarray(request['initial_scaled']);states=[initial.tolist()];status='complete';error=None
    started=time.monotonic()
    if s['case_id']=='SYN-NL-FUEL-01' and min(initial[:2])<0:
        status='model-domain-error';error='negative initial mass'
    else:
        z=ca.MX.sym('z',len(scales));u=ca.MX.sym('u',len(s['controls']));x=z*ca.DM(scales)
        if s['case_id']=='SYN-NL-LV-01':
            f=ca.vertcat((p['a']-p['b']*x[1]-u[0])*x[0],(p['d']*x[0]-p['c'])*x[1])
        else:
            f=ca.vertcat(-x[2],-x[3],(p['Q_ox']*u[0]*ca.sqrt(x[0]/p['m_ox0'])-x[2])/p['tau_ox'],
                         (p['Q_f']*u[1]*ca.sqrt(x[1]/p['m_f0'])-x[3])/p['tau_f'])
        # One CVODES integration per original hold, with dense report output samples.
        step=ca.MX.sym('step');integrator=ca.integrator('mpc11_cvodes','cvodes',
            {'x':z,'p':ca.vertcat(u,step),'ode':step*f/ca.DM(scales)},0,
            [(j+1)/request['report_subintervals_per_hold'] for j in range(request['report_subintervals_per_hold'])],
            {'abstol':request['abstol'],'reltol':request['reltol'],'max_num_steps':request['max_attempts']})
        try:
            grid=s['time']['grid']
            for a,b,control in zip(grid,grid[1:],request['original_controls']):
                values=np.array(integrator(x0=states[-1],p=[*control,b-a])['xf']).T
                if not np.isfinite(values).all():raise ValueError('nonfinite CVODES state')
                if len(scales)==4 and np.min(values[:,:2])<0:raise ValueError('negative mass')
                states.extend(values.tolist())
        except Exception as exc:
            status='integration-failure';error=str(exc)
    physical=(np.asarray(states)*scales).tolist()
    metrics=evaluate(s,physical,request['original_controls'])
    if status!='complete':metrics['objective']=None
    return {'schema':'csl.mpc11.nonlinear-execution/1','method':'cvodes','casadi_version':ca.__version__,
            'status':status,'error':error,'scenario_sha256':request['scenario_sha256'],
            'witness_sha256':request['witness_sha256'],'controls_sha256':request['controls_sha256'],
            'times':request['times'][:len(states)],'scaled_states':states,'physical_states':physical,
            'elapsed_seconds':time.monotonic()-started,'abstol':request['abstol'],'reltol':request['reltol'],**metrics}

if __name__=='__main__':
    import json
    import sys
    from pathlib import Path
    request=json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(execute_cvodes(request),indent=2,allow_nan=False))

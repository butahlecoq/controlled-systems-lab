"""Synthetic MPC-11 actual do-mpc Radau transcription, shrinking to fixed T."""
import hashlib
import inspect
import time
import casadi as ca
import do_mpc
import numpy as np
from affine import canonical_hash


def references(s):
    n=s['time']['intervals'];grid=np.asarray(s['time']['grid']);nu=len(s['controls'])
    if s['case_id']=='SYN-NL-LV-01':return np.zeros((n,nu))
    p={k:v['value'] for k,v in s['parameters'].items()};mid=(grid[:-1]+grid[1:])/2
    return np.array([[2/(p['Q_ox']*np.sqrt((100-2*t)/p['m_ox0'])),.6/(p['Q_f']*np.sqrt((30-.6*t)/p['m_f0']))] for t in mid])


def physical_reference(s,t):
    return np.array([100.,80.]) if s['case_id']=='SYN-NL-LV-01' else np.array([100-2*t,30-.6*t,2.,.6])


def vector(value):return np.asarray(value.cat if hasattr(value,'cat') else value,dtype=float).reshape(-1)


def symbolic_ode(s,z,u):
    scale=ca.DM([v['scale'] for v in s['states']]);x=z*scale;p={k:v['value'] for k,v in s['parameters'].items()}
    if s['case_id']=='SYN-NL-LV-01':f=ca.vertcat((p['a']-p['b']*x[1]-u[0])*x[0],(p['d']*x[0]-p['c'])*x[1])
    elif s['case_id']=='SYN-NL-FUEL-01':
        f=ca.vertcat(-x[2],-x[3],(p['Q_ox']*u[0]*ca.sqrt(x[0]/p['m_ox0'])-x[2])/p['tau_ox'],
                    (p['Q_f']*u[1]*ca.sqrt(x[1]/p['m_f0'])-x[3])/p['tau_f'])
    else:raise ValueError('unsupported case')
    return f/scale


def direct_tail_cost(s,j,terminal,controls):
    o=s['objective'];terminal=np.asarray(terminal);controls=np.asarray(controls)
    phi=float(np.sum(np.asarray(o['terminal_weights'])*((terminal-o['terminal_target'])/o['terminal_scale'])**2))
    running=float(o['running_weight']/s['time']['intervals']*np.sum(((controls-references(s)[j:])/o['running_scale'])**2))
    return phi+running


def build_controller(s,j):
    started=time.monotonic();n=s['time']['intervals'];remaining=n-j
    if not 0<=j<n:raise ValueError('no solve at or after fixed terminal time')
    cfg=s['nmpc'];col=cfg['collocation'];o=s['objective'];nx=len(s['states']);nu=len(s['controls'])
    plant=do_mpc.model.Model('continuous');z=plant.set_variable('_x','z',(nx,1));u=plant.set_variable('_u','u',(nu,1));ref=plant.set_variable('_tvp','reference',(nu,1))
    plant.set_rhs('z',symbolic_ode(s,z,u));plant.setup();controller=do_mpc.controller.MPC(plant)
    solver=cfg['solver'];controller.set_param(n_horizon=remaining,t_step=s['time']['dt'],n_robust=cfg['n_robust'],
        state_discretization='collocation',collocation_type=col['method'],collocation_deg=col['degree'],collocation_ni=col['elements_per_interval'],
        cons_check_colloc_points=True,nl_cons_check_colloc_points=True,use_terminal_bounds=True,
        nlpsol_opts={'ipopt.tol':solver['tol'],'ipopt.acceptable_tol':solver['acceptable_tol'],'ipopt.max_iter':solver['max_iter'],
                     'ipopt.linear_solver':solver['linear_solver'],'ipopt.bound_relax_factor':0.0,'ipopt.print_level':5,'print_time':True})
    scales=np.array([v['scale'] for v in s['states']]);x=z*ca.DM(scales)
    phi=ca.dot(ca.DM(o['terminal_weights']),((x-ca.DM(o['terminal_target']))/ca.DM(o['terminal_scale']))**2)
    ell=o['running_weight']/n*ca.sumsqr((u-ref)/ca.DM(o['running_scale']))
    controller.set_objective(mterm=phi,lterm=ell)
    # Explicit zero input-change regularization. The authored effort is lterm.
    controller.set_rterm(u=np.zeros((nu,1)))
    bounds=np.asarray([v['physical_bounds'] for v in s['states']])/scales[:,None]
    cb=np.asarray([v['physical_bounds'] for v in s['controls']])
    controller.bounds['lower','_x','z']=bounds[:,0];controller.bounds['upper','_x','z']=bounds[:,1]
    controller.bounds['lower','_u','u']=cb[:,0];controller.bounds['upper','_u','u']=cb[:,1]
    controller.terminal_bounds['lower','z']=bounds[:,0];controller.terminal_bounds['upper','z']=bounds[:,1]
    template=controller.get_tvp_template();refs=references(s)
    def tvp(_):
        for k in range(remaining):template['_tvp',k,'reference']=refs[j+k]
        # mterm ignores reference; use the final valid held sample, never evaluate beyond T.
        template['_tvp',remaining,'reference']=refs[-1]
        return template
    controller.set_tvp_fun(tvp);controller.setup()
    # do-mpc 5.1.2 omits terminal-interval collocation bounds in _update_bounds.
    # Set every state slot, including the initial mesh endpoint and final collocation nodes.
    for k in range(remaining+1):
        for c in range(len(controller.opt_x_num['_x',k,0])):
            controller.lb_opt_x['_x',k,0,c,'z']=bounds[:,0]
            controller.ub_opt_x['_x',k,0,c,'z']=bounds[:,1]
    controller.opt_p_num['_tvp']=tvp(s['time']['grid'][j])['_tvp']
    obj=ca.Function('authored_nlp_objective',[controller.opt_x.cat,controller.opt_p.cat],[controller.nlp_obj])
    constraints=ca.Function('authored_nlp_constraints',[controller.opt_x.cat,controller.opt_p.cat],[controller.nlp_cons])
    grad=ca.gradient(controller.nlp_obj,controller.opt_x.cat);jac=ca.jacobian(controller.nlp_cons,controller.opt_x.cat)
    stationarity=ca.Function('local_stationarity',[controller.opt_x.cat,controller.opt_p.cat],[grad,jac])
    return controller,{'setup_seconds':time.monotonic()-started,'objective_function':obj,'constraint_function':constraints,'stationarity_function':stationarity,
                       'original_interval_count':n,'remaining_horizon':remaining,'update_index':j,'absolute_initial_time':s['time']['grid'][j],
                       'fixed_terminal_time':s['time']['final'],'running_cost_semantics':'direct sum of lterm, original N, no dt factor',
                       'nlp_objective_expression':str(controller.nlp_obj),'nlp_variable_labels':controller.opt_x.labels(),
                       'constraint_lower':vector(controller.nlp_cons_lb).tolist(),'constraint_upper':vector(controller.nlp_cons_ub).tolist(),
                       'variable_lower':vector(controller._lb_opt_x.cat).tolist(),'variable_upper':vector(controller._ub_opt_x.cat).tolist()}


def initialize_guess(mpc,s,j,observation,previous):
    h=s['time']['intervals']-j;scales=np.array([v['scale'] for v in s['states']]);dt=s['time']['dt'];grid=s['time']['grid'];cols=len(mpc.opt_x_num['_x',0,0])
    roots=ca.collocation_points(s['nmpc']['collocation']['degree'],s['nmpc']['collocation']['method'])
    for k in range(h+1):
        for c in range(cols):
            if previous is not None:value=previous['_x',k+1,0,c,'z']
            else:
                # do-mpc stores interval k-1 collocation stages at _x[k,:-1].
                if c==cols-1 or k==0:t=grid[j+k]
                else:
                    degree=s['nmpc']['collocation']['degree'];elements=s['nmpc']['collocation']['elements_per_interval']
                    element,local=divmod(c,degree+1)
                    t=grid[j+k-1]+dt/elements*(element+([0.]+roots)[local])
                value=physical_reference(s,t)/scales
            mpc.opt_x_num['_x',k,0,c,'z']=value
    refs=references(s)
    for k in range(h):mpc.opt_x_num['_u',k,0,'u']=previous['_u',k+1,0,'u'] if previous is not None else (np.array([.025]) if len(scales)==2 else refs[j+k])
    mpc.opt_x_num['_x',0,0,-1,'z']=observation;mpc.opt_p_num['_x0','z']=observation
    mpc.opt_p_num['_u_prev','u']=np.zeros(len(s['controls']))
    controls=[vector(mpc.opt_x_num['_u',k,0,'u']).tolist() for k in range(h)]
    mesh=[vector(mpc.opt_x_num['_x',k,0,-1,'z']).tolist() for k in range(h+1)]
    numeric=vector(mpc.opt_x_num).tolist()
    return {'policy':'initial-reference' if previous is None else 'drop-first-interval-no-terminal-repeat','dual_policy':'zero-every-solve',
            'controls':controls,'mesh_scaled':mesh,'full_primal':numeric,'guess_sha256':canonical_hash(numeric)}


def solve_update(mpc,s,j,observation,guess,meta):
    started=time.monotonic();h=s['time']['intervals']-j
    result=mpc.S(x0=mpc.opt_x_num,p=mpc.opt_p_num,lbx=mpc._lb_opt_x,ubx=mpc._ub_opt_x,
                 lbg=mpc.nlp_cons_lb,ubg=mpc.nlp_cons_ub,lam_x0=np.zeros(mpc.n_opt_x),lam_g0=np.zeros(mpc.n_opt_lagr))
    elapsed=time.monotonic()-started;stats=mpc.S.stats();primal=vector(result['x']);g=vector(result['g'])
    prediction=mpc.opt_x_num;prediction.master=result['x']
    controls=[vector(prediction['_u',k,0,'u']).tolist() for k in range(h)]
    scaled=[vector(prediction['_x',k,0,-1,'z']).tolist() for k in range(h+1)];scales=np.array([v['scale'] for v in s['states']]);physical=np.asarray(scaled)*scales
    direct=direct_tail_cost(s,j,physical[-1],controls);native=float(result['f']);difference=abs(direct-native)
    lo=np.array(meta['variable_lower']);hi=np.array(meta['variable_upper']);gl=np.array(meta['constraint_lower']);gu=np.array(meta['constraint_upper'])
    primal_violation=float(max(np.max(np.maximum(lo-primal,0)),np.max(np.maximum(primal-hi,0)),np.max(np.maximum(gl-g,0)),np.max(np.maximum(g-gu,0))))
    grad,jac=meta['stationarity_function'](primal,mpc.opt_p_num);lamx=vector(result['lam_x']);lamg=vector(result['lam_g'])
    stationarity=float(np.max(np.abs(vector(grad)+np.array(jac).T@lamg+lamx)))
    nodes=np.asarray([vector(prediction['_x',k,0,c,'z']) for k in range(h+1) for c in range(len(prediction['_x',k,0]))])*scales
    state_bounds=np.array([v['physical_bounds'] for v in s['states']])
    node_violation=np.maximum(np.maximum(state_bounds[:,0]-nodes,nodes-state_bounds[:,1]),0).max(axis=0).tolist()
    accepted=bool(stats.get('success',False) and np.isfinite(primal).all() and np.isfinite(native) and primal_violation<=1e-6 and difference<=1e-8)
    record={key:value for key,value in meta.items() if not key.endswith('_function')}
    record.update({'schema':'csl.mpc11.nlp-update/1','status':stats.get('return_status','unavailable'),'success':bool(stats.get('success',False)),
                   'accepted':accepted,'iteration_count':stats.get('iter_count'),'objective':native,'objective_recomputed':direct,'objective_reconstruction_difference':difference,
                   'optimization_node_max_physical_state_violation':node_violation,'max_scaled_primal_violation':primal_violation,'local_stationarity_infinity_norm':stationarity,'dual_x':lamx.tolist(),'dual_g':lamg.tolist(),
                   'solve_seconds':elapsed,'observation_scaled':np.asarray(observation).tolist(),'guess':guess,'primal':primal.tolist(),
                   'parameters':vector(mpc.opt_p_num).tolist(),'constraint_values':g.tolist(),'predicted_controls':controls,'predicted_mesh_scaled':scaled,
                   'predicted_mesh_physical':physical.tolist(),'solver_iterations':stats.get('iterations',{}),
                   'source_solve_id':None if j==0 else j-1,'assurance':'local NLP diagnostics only; no global nonlinear certificate'})
    record['solve_sha256']=canonical_hash(record)
    return record,prediction


def execution_integrator(s):
    nx=len(s['states']);nu=len(s['controls']);z=ca.MX.sym('z',nx);u=ca.MX.sym('u',nu);sub=s['independent_replay']['report_subintervals_per_hold'];settings=s['execution']
    return ca.integrator('closed_loop_execution','cvodes',{'x':z,'p':u,'ode':symbolic_ode(s,z,u)},0,
                        [s['time']['dt']*(j+1)/sub for j in range(sub)],
                        {'abstol':settings['scaled_abstol'],'reltol':settings['reltol'],'max_num_steps':100000})

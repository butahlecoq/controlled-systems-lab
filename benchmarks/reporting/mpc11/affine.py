"""Authored MPC-11 affine prediction and public joint-program construction."""
from __future__ import annotations
import hashlib
import json
import math
import numpy as np
from scipy.linalg import expm


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def discretize(a, b, c, dt):
    n, m = b.shape
    augmented = np.zeros((n+m+1, n+m+1))
    augmented[:n, :n], augmented[:n, n:n+m], augmented[:n, -1] = a, b, c
    result = expm(dt*augmented)
    return result[:n, :n], result[:n, n:n+m], result[:n, -1]


def tracking_quadratic(dimension, terminal_indices, target, scale, weights,
                       control_indices, reference, running_scale, control_scale,
                       running_weight, original_intervals):
    q, linear, offset = np.zeros((dimension, dimension)), np.zeros(dimension), 0.
    for index, goal, divisor, weight in zip(terminal_indices, target, scale, weights):
        coefficient = weight/divisor**2
        q[index, index] += 2*coefficient
        linear[index] -= 2*coefficient*goal
        offset += coefficient*goal**2
    for index, goal, divisor, multiplier in zip(control_indices, reference, running_scale, control_scale):
        coefficient = running_weight/original_intervals/divisor**2
        q[index, index] += 2*coefficient*multiplier**2
        linear[index] -= 2*coefficient*multiplier*goal
        offset += coefficient*goal**2
    return q, linear, offset


def model(scenario):
    n, m = len(scenario['states']), len(scenario['controls'])
    dt, count = scenario['time']['dt'], scenario['time']['intervals']
    scales = np.array([x['scale'] for x in scenario['states']])
    control_scales = np.array([x['physical_bounds'][1] for x in scenario['controls']])
    reference = np.zeros((count+1, n)); commands = np.zeros((count, m))
    if scenario['case_id'] == 'SYN-NL-FUEL-01':
        for k in range(count+1):
            reference[k] = [100-2*k*dt, 30-.6*k*dt, 2, .6]
        for k in range(count):
            t = (k+.5)*dt
            commands[k] = [2/(3*math.sqrt((100-2*t)/100)), .6/math.sqrt((30-.6*t)/30)]
    else:
        reference[:] = scenario['affine']['state_reference']
    physical, scaled = [], []
    for k in range(count):
        if scenario['case_id'] == 'SYN-NL-FUEL-01':
            midpoint = .5*(reference[k]+reference[k+1])
            a, b = np.zeros((4, 4)), np.zeros((4, 2))
            a[0, 2], a[1, 3] = -1, -1
            for mass, flow, initial, maximum, tau, control in [(0,2,100,3,2,0),(1,3,30,1,2,1)]:
                a[flow, mass] = maximum*commands[k,control]/(2*tau*initial*math.sqrt(midpoint[mass]/initial))
                a[flow, flow] = -1/tau
                b[flow, control] = maximum*math.sqrt(midpoint[mass]/initial)/tau
            ad, bd, _ = discretize(a,b,np.zeros(4),dt)
            cd = reference[k+1]-ad@reference[k]-bd@commands[k]
        else:
            p = {name: row['value'] for name, row in scenario['parameters'].items()}
            prey, predator = reference[k]
            a = np.array([[p['a']-p['b']*predator,-p['b']*prey],
                          [p['d']*predator,p['d']*prey-p['c']]])
            b = np.array([[-prey],[0.]])
            ad, bd, cd = discretize(a,b,-a@reference[k],dt)
        physical.append({'A':ad.tolist(),'B':bd.tolist(),'c':cd.tolist(),
                         'jacobian_A':a.tolist(),'jacobian_B':b.tolist()})
        scaled.append({'A':(ad*scales[None,:]/scales[:,None]).tolist(),
                       'B':(bd*control_scales[None,:]/scales[:,None]).tolist(),
                       'c':(cd/scales).tolist()})
    return {'schema':'csl.mpc11.affine-model/1','case_id':scenario['case_id'],
        'model_id':scenario['affine']['model_id'],'scenario_sha256':canonical_hash(scenario),
        'physical_coefficients':physical,'scaled_coefficients':scaled,
        'state_scale':scales.tolist(),'control_scale':control_scales.tolist(),
        'reference_states':reference.tolist(),'reference_commands':commands.tolist(),
        'coefficient_assurance':'binary64 scipy.linalg.expm numerical exponential; no validated arithmetic',
        'fuel_offset':'authored-reference-endpoint-matching' if n==4 else None}


def program(scenario, coefficients):
    n, m = len(scenario['states']), len(scenario['controls'])
    count = scenario['time']['intervals']; width = n*(count+1)+m*count
    scales, control_scales = np.array(coefficients['state_scale']), np.array(coefficients['control_scale'])
    refs, commands = np.array(coefficients['reference_states']), np.array(coefficients['reference_commands'])
    control_start = n*(count+1)
    terminal_indices = list(range(n*count,n*(count+1)))
    control_indices = list(range(control_start,width))
    objective = scenario['objective']
    q, linear, offset = tracking_quadratic(width,terminal_indices,
        np.array(objective['terminal_target'])/scales,
        np.array(objective['terminal_scale'])/scales,objective['terminal_weights'],
        control_indices,commands.reshape(-1),np.tile(objective['running_scale'],count),
        np.tile(control_scales,count),objective['running_weight'],count)
    variable_bounds = []
    for k in range(count+1):
        for i, row in enumerate(scenario['states']):
            physical = row['physical_bounds']; trust = scenario['affine']['trust_state_absolute'][i]
            lo, hi = max(physical[0],refs[k,i]-trust), min(physical[1],refs[k,i]+trust)
            if k==0:
                if not lo <= row['initial'] <= hi:
                    raise ValueError('initial state outside physical/affine trust intersection')
                lo=hi=row['initial']
            variable_bounds.append([lo/scales[i],hi/scales[i]])
    for k in range(count):
        for i, row in enumerate(scenario['controls']):
            physical = row['physical_bounds']; trust = scenario['affine']['trust_input_absolute'][i]
            variable_bounds.append([max(physical[0],commands[k,i]-trust)/control_scales[i],
                                    min(physical[1],commands[k,i]+trust)/control_scales[i]])
    starts, columns, values, rows = [0], [], [], []
    for k, stage in enumerate(coefficients['scaled_coefficients']):
        for i in range(n):
            terms = {n*(k+1)+i:1.}
            for j in range(n):terms[n*k+j] = -stage['A'][i][j]
            for j in range(m):terms[control_start+m*k+j] = -stage['B'][i][j]
            for j, value in sorted(terms.items()):
                if value != 0:columns.append(j);values.append(value)
            starts.append(len(values));rows.append([stage['c'][i],stage['c'][i]])
    result={'schema':'csl.mpc11.affine-program/1','case_id':scenario['case_id'],
        'program_id':scenario['case_id'].lower()+'/public-joint-qp/1',
        'scenario_sha256':canonical_hash(scenario),'model_sha256':canonical_hash(coefficients),
        'objective_id':scenario['objective_id'],'variables':variable_bounds,'rows':rows,
        'constraints':{'rows':len(rows),'cols':width,'row_offsets':starts,'column_indices':columns,'values':values},
        'q_diagonal':np.diag(q).tolist(),'linear':linear.tolist(),'offset':offset,
        'coordinates':{'states':'scaled physical states, stage-major, stages 0..N',
                       'controls':'scaled physical commands, stage-major, after states',
                       'state_dimension':n,'control_dimension':m,'intervals':count},
        'quadratic_convention':'0.5*y.T*Q*y + linear.T*y + offset',
        'formulation':'public-CSL-ConvexProgram-joint-state-control-history'}
    result['program_sha256']=canonical_hash(result)
    return result



def permute_program(original, native_to_joint):
    result = json.loads(json.dumps(original))
    width = len(original['q_diagonal'])
    if sorted(native_to_joint) != list(range(width)):
        raise ValueError('variable ordering must be a permutation')
    joint_to_native = [0]*width
    for native, joint in enumerate(native_to_joint):
        joint_to_native[joint] = native
    for name in ['q_diagonal','linear','variables']:
        result[name] = [original[name][joint] for joint in native_to_joint]
    matrix = original['constraints']; columns, values, starts = [], [], [0]
    for row in range(matrix['rows']):
        pairs = sorted((joint_to_native[matrix['column_indices'][k]], matrix['values'][k])
                       for k in range(matrix['row_offsets'][row], matrix['row_offsets'][row+1]))
        columns.extend(j for j, _ in pairs); values.extend(a for _, a in pairs); starts.append(len(values))
    result['constraints'] = {**matrix, 'row_offsets':starts,'column_indices':columns,'values':values}
    result['coordinates']['joint_indices'] = joint_to_native
    result['coordinates']['native_order'] = 'controls-first; joint_indices reconstructs states-then-controls'
    result['program_id'] += '/controls-first'
    result.pop('program_sha256',None)
    result['program_sha256'] = canonical_hash(result)
    return result



def condense_program(scenario, coefficients, original):
    n, m = len(scenario['states']), len(scenario['controls'])
    count = scenario['time']['intervals']; controls = count*m
    current_map = np.zeros((n, controls))
    current_offset = np.array([row['initial']/row['scale'] for row in scenario['states']])
    maps, offsets = [current_map.copy()], [current_offset.copy()]
    for k, stage in enumerate(coefficients['scaled_coefficients']):
        current_map = np.array(stage['A'])@current_map
        current_map[:,k*m:(k+1)*m] += stage['B']
        current_offset = np.array(stage['A'])@current_offset+stage['c']
        maps.append(current_map.copy()); offsets.append(current_offset.copy())
    transform = np.vstack([*maps,np.eye(controls)])
    offset = np.concatenate([*offsets,np.zeros(controls)])
    diagonal, linear = np.array(original['q_diagonal']), np.array(original['linear'])
    q = transform.T@(diagonal[:,None]*transform); q = .5*(q+q.T)
    c = transform.T@(diagonal*offset+linear)
    constant = .5*np.dot(diagonal,offset**2)+np.dot(linear,offset)+original['offset']
    starts, columns, values, rows = [0], [], [], []
    for i in range(n*(count+1)):
        for j, value in enumerate(transform[i]):
            if value != 0: columns.append(j); values.append(value)
        starts.append(len(values))
        lo, hi = original['variables'][i]; rows.append([lo-offset[i],hi-offset[i]])
    result = {**original,'program_id':original['program_id']+'/equality-eliminated',
        'source_joint_program_sha256':original['program_sha256'],
        'q_diagonal':np.diag(q).tolist(),'q_matrix':q.tolist(),'linear':c.tolist(),'offset':constant,
        'variables':original['variables'][n*(count+1):],'rows':rows,
        'constraints':{'rows':len(rows),'cols':controls,'row_offsets':starts,'column_indices':columns,'values':values},
        'coordinates':{**original['coordinates'],'native_order':'scaled controls only; full joint reconstruction retained'},
        'joint_reconstruction':{'matrix':transform.tolist(),'offset':offset.tolist(),'variables':original['variables'],
                               'scope':'algebraic equality elimination evaluated in binary64; independently replay full affine dynamics'},
        'formulation':'public-CSL-ConvexProgram-equality-eliminated-with-full-joint-reconstruction'}
    result.pop('program_sha256',None); result['program_sha256']=canonical_hash(result)
    return result



def scale_objective(original, factor):
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('objective multiplier must be finite and positive')
    result=json.loads(json.dumps(original))
    result['source_unscaled_program_sha256']=result.pop('program_sha256')
    for name in ['q_diagonal','linear']:result[name]=[factor*x for x in result[name]]
    if 'q_matrix' in result:result['q_matrix']=[[factor*x for x in row] for row in result['q_matrix']]
    result['offset']*=factor
    result['objective_multiplier']=factor*original.get('objective_multiplier',1.)
    result['solver_objective_id']=original.get('objective_id','authored-objective')+'/positive-uniform-scale/'+format(result['objective_multiplier'],'.17g')
    result['program_id']+='/objective-times-'+format(factor,'.17g')
    result['objective_map']='authored objective = native quadratic objective / objective_multiplier; same minimizers'
    result['program_sha256']=canonical_hash(result)
    return result


def check_solution(scenario, coefficients, qp, result):
    if result.get('termination') != 'completed' or result.get('mathematical_outcome') != 'optimal' or 'primal' not in result:
        return {'status':'unavailable','reason':'no completed numerical optimal primal','termination':result.get('termination')}
    if result.get('case_id') != scenario['case_id'] or result.get('program_sha256') != qp['program_sha256']:
        return {'status':'incorrect','reason':'bridge result identity mismatch'}
    if len(result['primal']) != len(qp['variables']) or not np.all(np.isfinite(result['primal'])):
        return {'status':'incorrect','reason':'nonfinite or malformed primal'}
    point = np.array(result['primal']); n, m = len(scenario['states']), len(scenario['controls'])
    count = scenario['time']['intervals']; start = n*(count+1)
    if 'joint_reconstruction' in qp:
        reconstruction = qp['joint_reconstruction']
        joint = np.array(reconstruction['matrix'])@point+reconstruction['offset']
    else:
        joint = point[np.array(qp['coordinates'].get('joint_indices',list(range(len(point)))))]
    states = joint[:start].reshape((count+1,n))*coefficients['state_scale']
    controls = joint[start:].reshape((count,m))*coefficients['control_scale']
    replay = [np.array([row['initial'] for row in scenario['states']])]
    for stage, control in zip(coefficients['physical_coefficients'],controls):
        replay.append(np.array(stage['A'])@replay[-1]+np.array(stage['B'])@control+stage['c'])
    objective = scenario['objective']
    terminal = sum(w*((x-target)/scale)**2 for w,x,target,scale in zip(
        objective['terminal_weights'],replay[-1],objective['terminal_target'],objective['terminal_scale']))
    refs = np.array(coefficients['reference_commands'])
    running = objective['running_weight']/count*float(np.sum(((controls-refs)/objective['running_scale'])**2))
    direct = terminal+running
    quadratic = float(point@np.array(qp['q_matrix'])@point) if 'q_matrix' in qp else float(np.dot(qp['q_diagonal'],point**2))
    solver_qp_cost = .5*quadratic+float(np.dot(qp['linear'],point))+qp['offset']
    multiplier=qp.get('objective_multiplier',1.)
    if not math.isfinite(multiplier) or multiplier <= 0:return {'status':'incorrect','reason':'invalid objective map'}
    qp_cost=solver_qp_cost/multiplier
    violation=max(max(lo-x,x-hi,0.) for x,(lo,hi) in zip(point,qp['variables']))
    if 'joint_reconstruction' in qp:
        violation=max(violation,max(max(lo-x,x-hi,0.) for x,(lo,hi) in zip(joint,qp['joint_reconstruction']['variables'])))
    replay_error=float(np.max(np.abs(states-np.array(replay))))
    objective_error=abs(direct-qp_cost)
    native_objective=result.get('primal_check',{}).get('objective')
    native_error=abs(direct-native_objective/multiplier) if isinstance(native_objective,(int,float)) and math.isfinite(native_objective) else None
    status='verified-numerical-witness' if (violation<=1e-7 and replay_error<=1e-6 and objective_error<=1e-7 and native_error is not None and native_error<=1e-7 and not result.get('contract_diagnostics')) else 'incorrect'
    return {'status':status,'physical_states':states.tolist(),'physical_controls':controls.tolist(),
        'affine_replay_states':np.array(replay).tolist(),'terminal_cost':terminal,'running_cost':running,
        'objective':direct,'qp_objective':qp_cost,'solver_qp_objective':solver_qp_cost,'objective_multiplier':multiplier,'objective_difference':objective_error,'native_objective_difference':native_error,
        'max_scaled_bound_violation':violation,'max_physical_affine_replay_difference':replay_error,
        'witness_sha256':canonical_hash({'states':states.tolist(),'controls':controls.tolist()}),
        'assurance':'numerical replay and cost consistency; no exact/global nonlinear or family certificate'}

import hashlib
import json
from pathlib import Path
import sys
import numpy as np

repo = Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/943-history-bridge-solver')
sys.path.insert(0, str(repo / 'benchmarks/reporting/closed_loop'))
from contracts import load_task, manifest_sha256
from task_models import source_scenario
import affine

def direct_cost(task, states, controls, stage=0):
    x=np.asarray(states,dtype=float); u=np.asarray(controls,dtype=float)
    original_n=task['episode']['intervals']
    if task['model']['case_id'] in {'SYN-NL-LV-01','SYN-NL-FUEL-01'}:
        source=source_scenario(task); spec=source['objective']
        terminal=float(np.sum(np.asarray(spec['terminal_weights']) * ((x[-1]-spec['terminal_target'])/spec['terminal_scale'])**2))
        references=np.asarray(affine.model(source)['reference_commands'])[stage:]
        running=float(spec['running_weight']/original_n*np.sum(((u-references)/spec['running_scale'])**2))
    else:
        target=task['objective']['target']
        terminal=float(np.hypot(target['radius_km']-x[-1,0],100000*(target['angular_rate_rad_s']-x[-1,3])))
        running=float(0.001*task['episode']['dt']*sum(np.hypot(*row) for k,row in enumerate(u,start=stage) if k<original_n-1))
    return {'terminal':terminal,'running':running,'total':terminal+running}

root = Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/history-full-f4-01')
output = root / 'independent-history-audit.json'
summary = {'schema': 'history-episode-independent-audit/1', 'source_commit': 'f4e73e08908c472801aef6637d94b1a03cb0b2a7', 'tasks': {}}
for name in ('syn-nl-lv-01', 'earth-orbit', 'syn-nl-fuel-01'):
    attempts = list((root / name / 'attempts').glob('*/attempt.json'))
    if len(attempts) != 1:
        summary['tasks'][name] = {'status': 'missing-or-ambiguous'}
        continue
    path = attempts[0]
    attempt = json.loads(path.read_text())
    task = load_task(name)
    n, nx, nu = task['episode']['intervals'], len(task['model']['states']), len(task['model']['controls'])
    rows = [json.loads(p.read_text()) for p in sorted(path.parent.glob('stage-[0-9][0-9][0-9].json'))]
    completed = [r for r in rows if r.get('status') == 'applied-and-observed']
    data = {'status': attempt.get('status'), 'completed_holds': len(completed), 'expected_holds': n,
            'task_sha256': manifest_sha256(task), 'original_horizon': n,
            'recorded_overall_status': attempt.get('overall_status'), 'errors': [],
            'max_h_inequality_violation': 0., 'max_h_equality_residual': 0.,
            'max_initial_residual': 0., 'max_dynamics_residual': 0., 'max_source_cost_difference': 0.,
            'provider_ids': []}
    states = [[item['initial'] for item in task['model']['states']]]
    controls = []
    providers = set()
    for i, row in enumerate(completed):
        try:
            assert row['update_index'] == i and row['original_task_sha256'] == data['task_sha256']
            assert np.array_equal(row['observed_physical'], states[-1])
            ref = row['native_query_capture']; meta_bytes = (path.parent / ref['path']).read_bytes()
            assert hashlib.sha256(meta_bytes).hexdigest() == ref['sha256']
            meta = json.loads(meta_bytes); req_bytes = (path.parent / meta['request']['path']).read_bytes()
            assert hashlib.sha256(req_bytes).hexdigest() == meta['request']['sha256'] == meta['request_sha256']
            req = json.loads(req_bytes)
            assert req['task_sha256'] == data['task_sha256'] and req['absolute_update_index'] == i
            assert req['original_horizon'] == n and len(req['predictor_stages']) == n-i
            assert req['action_profile_id'] == task['control_domains']['continuous']['problem_id']
            assert np.array_equal(req['observed_physical_state'], states[-1])
            receipt = row['solve_receipt']; bridge, solver = receipt['bridge_response'], receipt['solver']
            response_bytes=(path.parent/meta['response']['path']).read_bytes()
            assert hashlib.sha256(response_bytes).hexdigest()==meta['response']['sha256']==meta['bridge_response_sha256']
            assert json.loads(response_bytes)==bridge
            z = np.asarray(bridge['primal'] if bridge['status'] == 'solved' else solver['primal'])
            h = n-i; xs=z[:(h+1)*nx].reshape(h+1,nx); us=z[(h+1)*nx:].reshape(h,nu)
            assert np.array_equal(us[0], row['applied_control'])
            bounds=np.asarray(task['control_domains']['continuous']['bounds'],dtype=float)
            assert np.all(us>=bounds[:,0]-1e-7) and np.all(us<=bounds[:,1]+1e-7)
            for k,field in enumerate(task['model']['states']):
                if field.get('bounds') is not None:
                    lo,hi=field['bounds']; assert np.all(xs[:,k]>=lo-1e-7) and np.all(xs[:,k]<=hi+1e-7)
            if task['model']['case_id']=='ENV717-EARTH-ORBIT-CONTINUOUS-01': assert np.all(xs[:,0]>0)
            relation=bridge['history_relation']
            for matrix_key,bound_key,target in [('inequalities','upper_bounds','max_h_inequality_violation'),('equalities','equality_values','max_h_equality_residual')]:
                if relation[matrix_key]:
                    residual=np.asarray(relation[matrix_key])@z-np.asarray(relation[bound_key])
                    value=float(np.max(np.maximum(residual,0) if matrix_key=='inequalities' else np.abs(residual)))
                    data[target]=max(data[target],value)
            data['max_initial_residual']=max(data['max_initial_residual'],float(np.max(np.abs(xs[0]-states[-1]))))
            for j,predictor in enumerate(req['predictor_stages']):
                residual=xs[j+1]-(np.asarray(predictor['A'])@xs[j]+np.asarray(predictor['B'])@us[j]+np.asarray(predictor['c']))
                data['max_dynamics_residual']=max(data['max_dynamics_residual'],float(np.max(np.abs(residual))))
            actual=direct_cost(task,xs,us,stage=i)
            reported=receipt['independent_validation']['source_cost']
            data['max_source_cost_difference']=max(data['max_source_cost_difference'],abs(actual['total']-reported['total']))
            compiled=bridge['history_objective']; quadratic=compiled['quadratic']
            reconstructed=float(0.5*z@np.asarray(quadratic['Q'])@z+np.asarray(quadratic['linear'])@z+quadratic['offset'])
            for term in compiled['residual_norms']:
                residual=np.asarray(term['map'])@z-np.asarray(term['target'])
                reconstructed+=term['coefficient']*float(np.linalg.norm(np.sqrt(term['weights'])*residual))
            assert abs(actual['total']-reconstructed)<=1e-7+1e-8*max(abs(actual['total']),abs(reconstructed))
            assert receipt['independent_validation']['accepted']
            assert all(c['passed'] for c in receipt['independent_validation']['checks'].values())
            for call in row['controller_invocations']:
                if call['operation']=='controller.solve': providers.add(call['provider'])
            controls.append(row['applied_control']); states.append(row['execution']['physical_states'][-1])
            assert np.array_equal(row['observed_next_physical'],states[-1])
        except Exception as error:
            data['errors'].append({'stage':i,'type':type(error).__name__,'reason':str(error)})
    data['provider_ids']=sorted(providers)
    if len(controls)==n: data['applied_original_objective']=direct_cost(task,states,controls)
    data['audit_status']='pass' if len(controls)==n and not data['errors'] else 'incomplete-or-failed'
    summary['tasks'][name]=data
output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps(summary,indent=2))

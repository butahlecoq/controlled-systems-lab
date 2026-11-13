"""Read-only independent audit of frozen native episode records."""
import hashlib,json,pathlib,sys,numpy as np
R=pathlib.Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111');W=R/'943-native-campaign-a6-source';O=R/'943-fixed-tail-native-a6-episodes'
sys.path.insert(0,str(W/'benchmarks/reporting/closed_loop'))
from contracts import load_task,manifest_sha256
from history_validation import validate
from fixed_tail_validation import validate_regions
from task_models import objective
sha=lambda b:hashlib.sha256(b).hexdigest()
def checked(folder,ref):
 p=folder/ref['path'];assert p.resolve().is_relative_to(folder.resolve()) and not p.is_symlink();raw=p.read_bytes();assert len(raw)==ref['bytes'] and sha(raw)==ref['sha256'];return raw
rows=[]
for attempt in sorted(O.glob('runs/*/records/*/attempts/*/attempt.json')):
 folder=attempt.parent;episode=json.loads(attempt.read_bytes());taskname=attempt.parents[3].parent.name.rsplit('-',1)[0];task=load_task(taskname);n=len(task['model']['states']);m=len(task['model']['controls']);N=task['episode']['intervals'];tasksha=manifest_sha256(task)
 assert episode['task_sha256']==tasksha and episode['original_intervals']==N and episode['completed_holds']==N
 assert all(episode[field]=='complete' for field in ['algorithm_status','postcheck_status','render_status','overall_status'])
 assert 'shared process log' in episode['preparation_receipt']['adapter_receipt']['stderr_policy'];assert (folder/'worker-stderr.txt').is_file()
 indices=[json.loads(line) for line in (folder/'stage-records.jsonl').read_text().splitlines()];assert len(indices)==N
 previous=None;anchor_adjustments=0;command_adjustments=0;regions_checked=0
 for k,reference in enumerate(indices):
  assert reference['update_index']==k;stage=json.loads(checked(folder,reference));assert stage['status']=='applied-and-observed' and stage['update_index']==k
  metadata=json.loads(checked(folder,stage['native_query_capture']));request_raw=checked(folder,metadata['request']);response_raw=checked(folder,metadata['response']);request=json.loads(request_raw);response=json.loads(response_raw)
  assert response['status']=='accepted' and response['task_sha256']==request['task_sha256']==tasksha
  assert response['policy_id']==request['controller_id']==episode['controller_id']
  assert request['absolute_update_index']==k and request['original_horizon']==N
  assert response['control']==stage['applied_control']==episode['controls'][k]
  assert request['observed_physical_state']==stage['observed_physical']==episode['physical_states'][k]
  lower,upper=np.array(task['control_domains']['continuous']['bounds']).T;assert np.all(np.array(response['control'])>=lower) and np.all(np.array(response['control'])<=upper)
  initial=response['initialization']['initial_primal'];assert response['feasibility']['supplied_initial_primary']==initial
  assert np.allclose(response['feasibility']['provider_initial_primary_readback'],initial,rtol=1e-12,atol=1e-12)
  if k:
   assert request['previous_history']==previous
   old=previous['history'];T=previous['remaining_horizon'];expected=old[n:(T+1)*n]+old[(T+1)*n+m:];expected[:n]=request['observed_physical_state']
   assert expected==initial and response['initialization']['source_stage']==k-1
  else:assert 'previous_history' not in request and response['initialization']['source_stage'] is None
  for phase in ['feasibility','reduced_argmin']:
   assert all(value==0 for value in response[phase]['supplied_initial_duals'])
   assert 'native C++ CasADi' in response[phase]['diagnostics'] and 'IPOPT' in response[phase]['diagnostics']
  assert response['feasibility']['objective']==0
  checks=validate(task,k,request['observed_physical_state'],request['predictor_stages'],response['source_history'],response['history'],response['source_cost']['total']);assert checks['accepted']
  physical=validate_regions(response,n,N-k);assert physical['accepted'];regions_checked+=len(physical['stages'])
  recovery=response['source_recovery'];assert recovery['absolute_tolerance']==1e-10 and recovery['relative_tolerance']==1e-12
  for name in ['anchor_control_adjustments','command_adjustments']:
   for adjustment in recovery[name]:
    assert adjustment['recovered']==adjustment['source_bound'];assert abs(adjustment['recovered']-adjustment['raw'])<=adjustment['allowed_absolute_adjustment']
   if name=='anchor_control_adjustments':anchor_adjustments+=len(recovery[name])
   else:command_adjustments+=len(recovery[name])
  previous=response['next_warm_history']
 physical_cost=objective(task,np.array(episode['physical_states']),np.array(episode['controls']));assert abs(physical_cost['total']-episode['physical_objective']['total'])<1e-9
 row={'task_id':task['task_id'],'family':episode['resolved_graph']['role_bindings']['representation']['id'],'attempt':str(attempt.relative_to(O)),'source_commit':'a6b7d1cb','queries':N,'physical_regions_checked':regions_checked,'anchor_control_adjustments':anchor_adjustments,'command_adjustments':command_adjustments,'physical_objective':physical_cost,'warm_protocol':'native shifted primal/drop applied stage/replace observed x0; supplied zero duals','stderr':'retained shared worker/native stream','accepted':True};rows.append(row);print(json.dumps(row),flush=True)
(O/'independent-saved-record-audit.json').write_text(json.dumps({'schema':'csl.native-fixed-tail.saved-record-audit/1','scope':'Functional numerical/source/protocol audit, not performance or nonlinear safety proof','attempts':rows,'queries':sum(row['queries'] for row in rows),'physical_regions_checked':sum(row['physical_regions_checked'] for row in rows),'all_accepted':len(rows)==15 and all(row['accepted'] for row in rows)},indent=2)+'\n')
assert len(rows)==15

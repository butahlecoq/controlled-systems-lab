import pathlib,json,sys
R=pathlib.Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111');W=pathlib.Path('/home/butahlecoq/.codex/worktrees/f9d3/controlled-systems-lab');O=R/'943-native-role-probes-f940';sys.path.insert(0,str(W/'benchmarks/reporting/closed_loop'))
from contracts import load_task,manifest_sha256
from capabilities import resolve_graph,HISTORY_MANIFEST
from fixed_tail_validation import validate_regions,validate_construction_trace
from history_validation import validate
rows=[]
for p in sorted(O.glob('*/stdout.jsonl')):
 req=json.loads((p.parent/'input.jsonl').read_text());res=json.loads(p.read_text());name=p.parent.name.rsplit('-',1)[0];task=load_task(name);_,graph=resolve_graph(task,req['action_profile_id'],req['controller_id'],manifest_path=HISTORY_MANIFEST);opts=graph['controller']['factory_options'];assert res['status']=='accepted' and req['task_sha256']==manifest_sha256(task);assert res['build_backend_profile']==opts['build_backend_profile'];trace=validate_construction_trace(res,opts['geometry_roles']);physical=validate_regions(res,len(req['observed_physical_state']),req['original_horizon']);checks=validate(task,0,req['observed_physical_state'],req['predictor_stages'],res['source_history'],res['history'],res['source_cost']['total']);assert trace['accepted'] and physical['accepted'] and checks['accepted']
 for region in res['regions']:
  for event in region['construction']:
   assert graph['operation_roles'][event['operation']]==event['role'];assert graph['role_bindings'][event['role']]['id']==event['owner']
 row={'profile':p.parent.name,'graph_id':graph['graph_id'],'graph_fingerprint':graph['graph_fingerprint'],'physical_stages':len(res['regions']),'construction_events':sum(len(r['construction']) for r in res['regions']),'source_cost':checks['source_cost'],'declared_observed_roles_match':True,'accepted':True};rows.append(row)
result={'source_commit':json.loads((O/'manifest.json').read_text())['source_commit'],'scope':'15 current original-task initial queries, not a closed-loop campaign; role coverage is separate from historical a6 episode evidence','profiles':rows,'all_accepted':len(rows)==15,'physical_stages':sum(r['physical_stages'] for r in rows),'construction_events':sum(r['construction_events'] for r in rows)};(O/'independent-role-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result['all_accepted'],result['physical_stages'],result['construction_events'])

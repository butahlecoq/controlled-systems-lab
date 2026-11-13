"""Read-only audit of saved failed-query inputs; no feasibility claim for missing primals."""
import hashlib,json,re,zipfile
from pathlib import Path
import numpy as np
R=Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111');B=R/'943-warm-gap-publication-9540-v1';index=json.loads((B/'records.json').read_text());results=[]
for rec in index['records']:
 if rec['full_episode']:continue
 with zipfile.ZipFile(B/'records'/rec['id']/'raw.zip') as z:
  stages=sorted(n for n in z.namelist() if re.fullmatch(r'attempt/stage-[0-9]{3}\.json',n));last=json.loads(z.read(stages[-1]));meta_bytes=z.read('attempt/'+last['native_query_capture']['path']);assert hashlib.sha256(meta_bytes).hexdigest()==last['native_query_capture']['sha256'];meta=json.loads(meta_bytes);rb=z.read('attempt/'+meta['request']['path']);assert hashlib.sha256(rb).hexdigest()==meta['request']['sha256']==meta['request_sha256'];req=json.loads(rb)
  h=rec['original_intervals']-rec['completed_holds'];nx=len(req['observed_physical_state']);nu=len(req['control_bounds']);assert req['absolute_update_index']==rec['completed_holds'];assert req['original_horizon']==rec['original_intervals'] and len(req['predictor_stages'])==h;assert req['task_sha256']==rec['task_sha256'] and req['controller_id']==rec['controller_id'];submitted=np.asarray(req['initial_primal']);assert len(submitted)==(h+1)*nx+h*nu and np.isfinite(submitted).all();assert req['warm_start']['dual_policy']=='zero-every-solve'
  if rec['completed_holds']:
   previous=json.loads(z.read(stages[-2]));receipt=previous['solve_receipt'];bridge=receipt['bridge_response'];primal=np.asarray(bridge['primal'] if bridge['status']=='solved' else receipt['solver']['primal']);xs=primal[:(h+2)*nx].reshape(h+2,nx)[1:].copy();us=primal[(h+2)*nx:].reshape(h+1,nu)[1:];xs[0]=req['observed_physical_state'];assert np.array_equal(submitted,np.r_[xs.ravel(),us.ravel()]);assert req['warm_start']['source_stage']==rec['completed_holds']-1
  else:
   expected=np.zeros_like(submitted);xs=expected[:(h+1)*nx].reshape(h+1,nx);xs[0]=req['observed_physical_state']
   for k,p in enumerate(req['predictor_stages']):xs[k+1]=np.asarray(p['A'])@xs[k]+np.asarray(p['c'])
   assert np.array_equal(expected,submitted);assert req['warm_start']['policy']=='initial-zero-control-rollout'
  solver=last.get('solve_receipt',{}).get('solver',{});warm=solver.get('warm_start')
  if warm:
   assert np.array_equal(warm['initial_primal'],submitted);np.testing.assert_allclose(warm['provider_initial_primal'],submitted,rtol=1e-14,atol=1e-10);assert all(x==0 for x in warm['initial_duals']) and all(x==0 for x in warm['provider_initial_duals'])
  response=None
  if meta.get('response'):
   raw=z.read('attempt/'+meta['response']['path']);assert hashlib.sha256(raw).hexdigest()==meta['response']['sha256']==meta['bridge_response_sha256'];response=json.loads(raw)
  results.append({'record_id':rec['id'],'task':rec['task'],'family':rec['family'],'failed_query_index':rec['completed_holds'],'remaining_original_intervals':h,'request_hash':meta['request']['sha256'],'original_task_and_controller_binding_verified':True,'full_original_remaining_horizon_verified':True,'warm_shift_or_initial_rollout_verified':True,'provider_initialization_readback_verified':bool(warm),'response_available':response is not None,'accepted_prefix_queries_independently_checked':rec['audit']['accepted_queries_checked'] if rec['audit'] else 0,'outcome':rec['outcome'],'compact_reason':rec['reason'],'scope':'Saved failed inputs and available startup receipts verified; no unavailable solution, full cost, trajectory or mathematical infeasibility inferred.'})
assert len(results)==8
out={'source_commit':index['source_commit'],'sdk_source_commit':index['sdk_source_commit'],'status':'pass','checks':results};(B/'failed-query-audit.json').write_text(json.dumps(out,indent=2)+'\n');print('PASS all8 non-complete archive query inputs, original horizons and available provider startup/readback receipts')

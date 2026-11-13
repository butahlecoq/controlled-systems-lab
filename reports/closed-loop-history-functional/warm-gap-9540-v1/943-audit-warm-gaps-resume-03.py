"""Read-only saved-witness audit, separate from policy decisions and execution."""
import hashlib
import json
from pathlib import Path
import sys
import traceback
import numpy as np

R=Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111')
SOURCE=Path('/home/butahlecoq/.codex/worktrees/3e28/controlled-systems-lab')
ROOT=R/'943-warm-gap-functional-9540-resume-03'
sys.path.insert(0,str(SOURCE/'benchmarks/reporting/closed_loop'))
from contracts import load_task,manifest_sha256
from task_models import source_scenario
import affine

def cost(task,x,u,stage=0):
 x=np.asarray(x,dtype=float);u=np.asarray(u,dtype=float);n=task['episode']['intervals']
 if task['model']['case_id'] in {'SYN-NL-LV-01','SYN-NL-FUEL-01'}:
  source=source_scenario(task);spec=source['objective'];terminal=float(np.sum(np.asarray(spec['terminal_weights'])*((x[-1]-spec['terminal_target'])/spec['terminal_scale'])**2));refs=np.asarray(affine.model(source)['reference_commands'])[stage:];running=float(spec['running_weight']/n*np.sum(((u-refs)/spec['running_scale'])**2))
 else:
  target=task['objective']['target'];terminal=float(np.hypot(target['radius_km']-x[-1,0],100000*(target['angular_rate_rad_s']-x[-1,3])));running=float(.001*task['episode']['dt']*sum(np.hypot(*row) for k,row in enumerate(u,start=stage) if k<n-1))
 return {'terminal':terminal,'running':running,'total':terminal+running}

def bound(residual,scale=1):
 assert np.max(np.abs(residual),initial=0)<=1e-7+1e-8*scale, float(np.max(np.abs(residual),initial=0))

def read_ref(base,ref):
 raw=(base/ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];return raw

summary={'source_commit':'9540b8d0b441f3f3e544d2016abb4ee53c94da0b','scope':'saved accepted query witnesses and actual original source objective; failed/nonterminal outcomes remain separate','cells':[]}
for cell in sorted(ROOT.glob('[0-9][0-9]-*')):
 launch=json.loads((cell/'launch.json').read_text());task=load_task(launch['task']);n=task['episode']['intervals'];nx=len(task['model']['states']);nu=len(task['model']['controls']);family=launch['family'];entry={'task':launch['task'],'family':family,'cell':str(cell),'accepted_queries_checked':0,'warm_queries_checked':0,'memberships_checked':0,'support_certificates_checked':0,'errors':[]}
 attempts=list((cell/'results').glob('*/attempts/*/attempt.json'))
 if len(attempts)!=1:entry['lifecycle']='missing-or-ambiguous';summary['cells'].append(entry);continue
 ap=attempts[0];attempt=json.loads(ap.read_text());entry['attempt_status']={k:attempt.get(k) for k in ['status','algorithm_status','overall_status','completed_holds']};previous=None;states=[[s['initial'] for s in task['model']['states']]];controls=[]
 rows=[json.loads(p.read_text()) for p in sorted(ap.parent.glob('stage-[0-9][0-9][0-9].json'))];completed=[row for row in rows if row.get('status')=='applied-and-observed']
 for i,row in enumerate(completed):
  try:
   assert row['update_index']==i and row['original_task_sha256']==manifest_sha256(task)==launch['task_sha256'];assert np.array_equal(row['observed_physical'],states[-1]);meta=json.loads(read_ref(ap.parent,row['native_query_capture']));raw=read_ref(ap.parent,meta['request']);assert hashlib.sha256(raw).hexdigest()==meta['request_sha256'];req=json.loads(raw)
   assert req['task_sha256']==manifest_sha256(task) and req['controller_id']==launch['controller_id'];assert req['absolute_update_index']==i and req['original_horizon']==n and len(req['predictor_stages'])==n-i;assert req['action_profile_id']==task['control_domains']['continuous']['problem_id'];assert np.array_equal(req['observed_physical_state'],states[-1]);assert req['history_solver']==('csl.convex.highs' if family=='direct-highs' else 'casadi-ipopt')
   receipt=row['solve_receipt'];bridge=receipt['bridge_response'];solver=receipt['solver'];response=read_ref(ap.parent,meta['response']);assert hashlib.sha256(response).hexdigest()==meta['bridge_response_sha256'];assert json.loads(response)==bridge
   z=np.asarray(bridge['primal'] if bridge['status']=='solved' else solver['primal']);h=n-i;xs=z[:(h+1)*nx].reshape(h+1,nx);us=z[(h+1)*nx:].reshape(h,nu);assert np.isfinite(z).all();submitted=np.asarray(req['initial_primal'])
   if i:
    oldx=previous[:(h+2)*nx].reshape(h+2,nx)[1:].copy();oldu=previous[(h+2)*nx:].reshape(h+1,nu)[1:];oldx[0]=states[-1];assert np.array_equal(submitted,np.concatenate([oldx.ravel(),oldu.ravel()]));assert req['warm_start']['source_stage']==i-1;assert req['warm_start']['policy']=='shift-prior-primal-drop-applied-stage-no-terminal-repeat'
   else:
    expected=np.zeros_like(submitted);ex=expected[:(h+1)*nx].reshape(h+1,nx);ex[0]=states[-1]
    for k,p in enumerate(req['predictor_stages']):ex[k+1]=np.asarray(p['A'])@ex[k]+np.asarray(p['c'])
    assert np.array_equal(submitted,expected);assert req['warm_start']['policy']=='initial-zero-control-rollout'
   assert req['warm_start']['dual_policy']=='zero-every-solve'
   if bridge['status']=='solved':
    assert np.array_equal(bridge['warm_start']['initial_primal'],submitted);raw=solver['raw_diagnostics']
    for phase in ('feasibility','qp'):
     assert phase+'.primal_start.retained=true' in raw and phase+'.primal_start.zero_duals=true' in raw
   else:
    start=receipt.get('initial_solver',solver)['warm_start'];assert np.array_equal(start['initial_primal'],submitted);np.testing.assert_allclose(start['provider_initial_primal'],submitted,rtol=1e-14,atol=1e-10);assert all(v==0 for v in start['initial_duals']) and all(v==0 for v in start['provider_initial_duals']);assert all(v==0 for v in solver['warm_start']['provider_initial_duals'])
   entry['warm_queries_checked']+=1;previous=z.copy();assert np.array_equal(us[0],row['applied_control']);bounds=np.asarray(task['control_domains']['continuous']['bounds']);assert np.all(us>=bounds[:,0]-1e-7) and np.all(us<=bounds[:,1]+1e-7);assert np.all(us[0]>=bounds[:,0]) and np.all(us[0]<=bounds[:,1])
   for k,f in enumerate(task['model']['states']):
    if f.get('bounds') is not None:assert np.all(xs[:,k]>=f['bounds'][0]-1e-7) and np.all(xs[:,k]<=f['bounds'][1]+1e-7)
   if task['model']['case_id']=='ENV717-EARTH-ORBIT-CONTINUOUS-01':assert np.all(xs[:,0]>0)
   relation=bridge['history_relation']
   if relation['inequalities']:assert np.max(np.asarray(relation['inequalities'])@z-np.asarray(relation['upper_bounds']),initial=0)<=1e-7+1e-8*np.max(np.abs(relation['upper_bounds']),initial=0)
   if relation['equalities']:bound(np.asarray(relation['equalities'])@z-np.asarray(relation['equality_values']),np.max(np.abs(relation['equality_values']),initial=0))
   bound(xs[0]-states[-1])
   for k,p in enumerate(req['predictor_stages']):bound(xs[k+1]-np.asarray(p['A'])@xs[k]-np.asarray(p['B'])@us[k]-np.asarray(p['c']),np.max(np.abs(xs[k+1]),initial=0))
   if not family.startswith('direct'):
    geo=bridge['geometry'];assert req['geometry_family']==geo['family']==family and geo['status']=='complete' and len(geo['stages'])==h+1;factors=solver['geometry_factors'];fi=0
    for local,stage in enumerate(geo['stages']):
     assert stage['stage']==local and stage['coordinates']==list(range(nx));assert {m['role'] for m in stage['memberships']}=={'forward','backward','intersection'}
     for member in stage['memberships']:
      assert member['indices']==list(range(local*nx,(local+1)*nx));state=xs[local];factor=np.asarray(factors[fi],dtype=float);fi+=1
      if member['kind']=='h':
       assert len(factor)==0
       if member['inequalities']:assert np.max(np.asarray(member['inequalities'])@state-np.asarray(member['upper_bounds']),initial=0)<=1e-7+1e-8*np.max(np.abs(member['upper_bounds']),initial=0)
       if member['equalities']:bound(np.asarray(member['equalities'])@state-np.asarray(member['equality_values']),np.max(np.abs(member['equality_values']),initial=0))
      else:
       assert len(factor)==member['factor_count'];bound(state-np.asarray(member['center'])-np.asarray(member['factor'])@factor)
       assert (np.max(np.abs(factor),initial=0) if member['kind']=='zonotope' else np.linalg.norm(factor))<=1+1e-7
      hs=stage[member['role']+'_h']
      for cert in member['support_certificates']:
       assert cert['input_set']==hs['set_id'];A=np.asarray(hs['inequalities']).reshape(-1,nx);E=np.asarray(hs['equalities']).reshape(-1,nx);lam=np.asarray(cert['inequality_multipliers']);mu=np.asarray(cert['equality_multipliers']);assert np.all(lam>=0);rem=np.asarray(cert['direction'])-A.T@lam-E.T@mu;replay=lam@np.asarray(hs['upper_bounds'])+mu@np.asarray(hs['equality_values'])+np.maximum(rem*cert['carrier_lower'],rem*cert['carrier_upper']).sum();assert replay<=cert['bound']+1e-8*(1+abs(replay));entry['support_certificates_checked']+=1
      entry['memberships_checked']+=1
    assert fi==len(factors)
   actual=cost(task,xs,us,i);q=bridge['history_objective']['quadratic'];compiled=float(.5*z@np.asarray(q['Q'])@z+np.asarray(q['linear'])@z+q['offset'])
   for term in bridge['history_objective']['residual_norms']:compiled+=term['coefficient']*float(np.linalg.norm(np.sqrt(term['weights'])*(np.asarray(term['map'])@z-np.asarray(term['target']))))
   assert abs(actual['total']-compiled)<=1e-7+1e-8*max(abs(actual['total']),abs(compiled));assert abs(actual['total']-receipt['independent_validation']['source_cost']['total'])<=1e-7+1e-8*abs(actual['total']);assert receipt['independent_validation']['accepted']
   controls.append(row['applied_control']);states.append(row['execution']['physical_states'][-1]);assert np.array_equal(row['observed_next_physical'],states[-1]);entry['accepted_queries_checked']+=1
  except Exception as error:entry['errors'].append({'stage':i,'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()});break
 entry['completed_holds_proven']=len(controls);entry['audit_status']='pass' if not entry['errors'] else 'failed';entry['full_episode']=len(controls)==n
 if len(controls)==n:entry['applied_original_objective']=cost(task,states,controls)
 summary['cells'].append(entry)
(ROOT/'independent-saved-witness-audit.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps(summary,indent=2))
assert all(c.get('audit_status')!='failed' for c in summary['cells'])

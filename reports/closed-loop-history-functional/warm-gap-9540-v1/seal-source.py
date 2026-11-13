"""Seal existing attempt/2 records and outer supervision without running controllers."""
import hashlib,json,re,shutil,sys,tempfile
from pathlib import Path
R=Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111');S=Path('/home/butahlecoq/.codex/worktrees/3e28/controlled-systems-lab');OUT=R/'943-warm-gap-publication-9540-v1'
sys.path.insert(0,str(S/'scripts/reports'))
from package_history_functional import archive_attempt
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OUT.mkdir(exist_ok=False);(OUT/'records').mkdir()
pre=json.loads((R/'943-warm-gap-preflight.json').read_text());(OUT/'source-build-receipt.json').write_text(json.dumps(pre,indent=2)+'\n')
for name in ['943-isolated-worker-supervisor.py','943-run-warm-gaps.py','943-run-warm-gaps-resume-02.py','943-run-warm-gaps-resume-03.py','943-run-warm-gaps-resume-04.py','943-audit-warm-gaps.py','943-audit-warm-gaps-resume-03.py','943-audit-warm-gaps-resume-04.py','943-worker-isolation-oom-proof.json','943-warm-gap-9540-polytope-nonterminal-preservation.json','943-warm-gap-resume-02-oom-preservation.json','943-warm-gap-resume-02-oom-terminal.txt','943-warm-gap-resume-03-actual-envelope.txt']:
 shutil.copy2(R/name,OUT/name)
shutil.copy2(Path(__file__),OUT/'seal-source.py')
roots=[R/'943-warm-gap-functional-9540',R/'943-warm-gap-functional-9540-resume-02',R/'943-warm-gap-functional-9540-resume-03',R/'943-warm-gap-functional-9540-resume-04']
records=[]
for root in roots:
 auditpath=root/'independent-saved-witness-audit.json';audit=json.loads(auditpath.read_text()) if auditpath.exists() else {'cells':[]}
 if auditpath.exists():shutil.copy2(auditpath,OUT/(root.name+'-audit.json'))
 for cell in sorted(root.glob('[0-9][0-9]-*')):
  launch=json.loads((cell/'launch.json').read_text());aps=list((cell/'results').glob('*/attempts/*/attempt.json'));assert len(aps)==1;ap=aps[0];attempt=ap.parent;ep=json.loads(ap.read_text());run=json.loads((attempt/'run-manifest.json').read_text());graph=json.loads((attempt/'resolved-graph.json').read_text())
  assert run['source_commit']==pre['source_commit'];assert run['bridge_sha256']==pre['bridge_binaries']['nonlinear_replay'];assert run['task_sha256']==pre['tasks'][launch['task']]['task_sha256'];assert graph['graph_fingerprint']==run['graph_fingerprint'];assert graph['controller']['id']==launch['controller_id']
  adapter=ep['preparation_receipt']['adapter_receipt'];assert adapter['executable_sha256']==pre['bridge_binaries']['history_policy']
  data=next((x for x in audit['cells'] if x['cell']==str(cell)),None)
  if data:assert not data['errors'] and data['audit_status']=='pass'
  full=ep.get('overall_status')=='complete';holds=ep.get('completed_holds',0);original=ep['original_intervals']
  if full:assert data and data['full_episode'] and data['accepted_queries_checked']==holds==original
  rows=[json.loads(p.read_text()) for p in sorted(attempt.glob('stage-[0-9][0-9][0-9].json'))];last=rows[-1];solver=last.get('solve_receipt',{}).get('solver',{});error=solver.get('error','');match=re.search("return_status is '([^']+)'",error)
  terminalpath=attempt/'worker-systemd-terminal.json';unit=json.loads(terminalpath.read_text()) if terminalpath.exists() else None
  if full:outcome='complete';reason='All original holds, common/tighter numerical replay and rendering complete.'
  elif root.name.endswith('resume-02'):outcome='resource-limited';reason='Outer service Result=oom-kill during initial LV polytope query. No native response or inner supervisor terminal receipt; mathematical feasibility not established.'
  elif root.name=='943-warm-gap-functional-9540':outcome='inconclusive-nonterminal';reason='Original LV polytope lifecycle lacks terminal supervisor result; absence of processes does not identify timeout/cancellation/OOM.'
  elif unit and unit.get('properties',{}).get('Result')=='oom-kill':outcome='resource-limited';reason='Numerical worker service Result=oom-kill at its 2 GiB memory/2 GiB swap envelope; no native response. Not infeasibility.'
  elif match:outcome='solver-stopped';reason='IPOPT '+match.group(1)+' at observed query '+str(holds)+'. Local solver status, not proof of source infeasibility.'
  else:outcome='geometry-stopped';reason=str(last.get('controller_reason','Native geometry stopped before producing a control.'))
  geometry=None;capture=last.get('native_query_capture')
  if capture:
   raw=(attempt/capture['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==capture['sha256'];meta=json.loads(raw)
   for field in ['request','response']:
    if meta.get(field):assert sha(attempt/meta[field]['path'])==meta[field]['sha256']
   if meta.get('response'):
    response=json.loads((attempt/meta['response']['path']).read_text());g=response.get('geometry')
    if g:geometry={k:g.get(k) for k in ['status','stop_kind','stop_stage','stop_phase','diagnostics'] if k in g}
  rid=f'{len(records)+1:02d}-{launch["task"]}-{launch["family"]}';dest=OUT/'records'/rid;dest.mkdir()
  with tempfile.TemporaryDirectory(dir=R,prefix='943-wave-seal-') as tmp:
   stage=Path(tmp);shutil.copytree(attempt,stage/'attempt');(stage/'supervisor').mkdir()
   for name in ['launch.json','parent-stdout.log','parent-stderr.log','parent-terminal.json']:
    if (cell/name).exists():shutil.copy2(cell/name,stage/'supervisor'/name)
   inventory=archive_attempt(stage,dest/'raw.zip')
  record={'id':rid,'task':launch['task'],'family':launch['family'],'attempt_id':ep['attempt_id'],'task_id':ep['task_id'],'task_sha256':ep['task_sha256'],'controller_id':ep['controller_id'],'source_commit':pre['source_commit'],'sdk_source_commit':pre['sdk_producer_commit'],'native_sha256':pre['bridge_binaries']['history_policy'],'physical_bridge_sha256':pre['bridge_binaries']['nonlinear_replay'],'graph_id':graph['graph_id'],'graph_fingerprint':graph['graph_fingerprint'],'original_intervals':original,'completed_holds':holds,'outcome':outcome,'reason':reason,'geometry_terminal':geometry,'full_episode':full,'physical_objective':ep.get('physical_objective') if full else None,'audit':data,'unit_terminal':unit,'resource_envelope':launch.get('external_resource_envelope'),'worker_stderr_available':(attempt/'worker-stderr.txt').exists(),'attempt_prefix':'attempt/','archive_sha256':sha(dest/'raw.zip'),'archive_members':inventory,'scope':'Archive receipt/index only; authoritative algorithm result remains original csl.closed-loop.attempt/2 and source-bound stage records.','trace_qualification':'Original native stderr shares worker stream where retained. Initial nonterminal and outer-OOM attempts lack recovered final worker streams; no bytes reconstructed.'}
  (dest/'receipt.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n');records.append({k:v for k,v in record.items() if k!='archive_members'});print('SEALED',rid,outcome,holds,'/',original,flush=True)
index={'schema':'csl.closed-loop.saved-wave-index/1','source_commit':pre['source_commit'],'sdk_source_commit':pre['sdk_producer_commit'],'scope':'#943 initial functional warm-gap validation; not a #947 timing/exhaustive campaign or all-current-source/native-MPC claim. IPOPT orchestration remains Python/CasADi; C++ compiles model/history/cost/geometry.','attempt_count':len(records),'unique_selected_profiles':15,'complete_profiles':sum(r['full_episode'] for r in records),'records':records}
assert len(records)==16 and index['complete_profiles']==8
(OUT/'records.json').write_text(json.dumps(index,indent=2,allow_nan=False)+'\n')
files={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()};(OUT/'files.sha256').write_text(''.join(v+'  '+k+'\n' for k,v in files.items()));print('SEALED ALL',len(records),'attempts;',index['complete_profiles'],'full episodes',flush=True)

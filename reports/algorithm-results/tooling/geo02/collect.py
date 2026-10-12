"""GEO-02 collection and canonical saved-record validation."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, os, platform, subprocess, sys
from pathlib import Path
SCHEMA='csl.geo02-affine-sum-report/1'
HASH_SCOPE='canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope'
PHASES=('setup_ns','operation_ns','oracle_ns','total_ns')
SCENARIOS={
 'scalar_interval_affine_image': {'inputs':{'vertices':[[-1.0],[1.0]],'A':[[2.0]],'b':[0.0]},'outputs':[[-2.0],[2.0]],'directions':[[1.0],[-1.0]],'support':[2.0,2.0]},
 'rectangular_projection_box': {'inputs':{'vertices':[[0,0],[0,1],[1,0],[1,1]],'A':[[1.0,1.0]],'b':[0.0]},'outputs':[[0.0],[2.0]],'directions':[[1.0],[-1.0]],'support':[2.0,0.0]},
 'singular_map_box_segment': {'inputs':{'vertices':[[0,0],[0,1],[1,0],[1,1]],'A':[[1.0,1.0],[2.0,2.0]],'b':[0.0,0.0]},'outputs':[[0,0],[2,4]],'directions':[[1.0,0.0],[-1.0,0.0],[0.0,1.0],[0.0,-1.0]],'support':[2.0,0.0,4.0,0.0]},
 'minkowski_interval_sum': {'inputs':{'left_vertices':[[-1.0],[1.0]],'right_vertices':[[2.0],[3.0]]},'outputs':[[1.0],[4.0]],'directions':[[1.0],[-1.0]],'support':[4.0,-1.0]},
}
FIELDS=('scenario','repetition','status','detail','setup_ns','operation_ns','oracle_ns','total_ns','output_points','support_checks','support_values','oracle_passed')
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(v): return hashlib.sha256(v).hexdigest()
def summarize(trials,complete=True):
 result={}
 for name in SCENARIOS:
  rows=[t for t in trials if t.get('scenario')==name]; accepted=bool(complete and rows and all(t.get('status')=='passed' and t.get('oracle_passed') is True for t in rows)); phases={}
  for phase in PHASES:
   vals=sorted(t[phase] for t in rows) if accepted else []
   phases[phase]={'unit':'ns','successful_trials':len(vals),'median':(vals[(len(vals)-1)//2]+vals[len(vals)//2])//2 if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None,'range':max(vals)-min(vals) if vals else None,'trials_excluded_from_summary':len(rows)-len(vals)}
  passed=sum(t.get('status')=='passed' and t.get('oracle_passed') is True for t in rows)
  result[name]={'attempts':len(rows),'passed':passed,'failures':len(rows)-passed,'phases':phases}
 return result
def finalize(payload,stamp='manual'):
 payload.pop('payload_sha256',None);payload.pop('payload_hash_scope',None);payload['payload_hash_scope']=HASH_SCOPE
 payload['payload_sha256']=sha(canonical({k:v for k,v in payload.items() if k not in ('report_id','payload_sha256','payload_hash_scope')}))
 payload['report_id']='geo02-'+stamp+'-'+payload['payload_sha256'][:12];return payload
def fixture_payload(stamp='manual'):
 trials=[]
 for s,c in SCENARIOS.items():
  for r in range(7):trials.append({'scenario':s,'repetition':r,'status':'passed','detail':'','setup_ns':1,'operation_ns':2,'oracle_ns':3,'total_ns':6,'input_sha256':sha(canonical(c['inputs'])),'output_points':c['outputs'],'support_checks':len(c['directions']),'support_values':c['support'],'oracle_passed':True})
 warmups=[{'scenario':s,'repetition':0,'status':'passed','detail':'','output_points':c['outputs'],'support_checks':len(c['directions']),'support_values':c['support'],'oracle_passed':True} for s,c in SCENARIOS.items()]
 payload={'schema':SCHEMA,'report_id':None,'algorithm':{'id':'GEO-02','source_commit':'0'*40,'harness_commit':'0'*40},'collection':{'state':'complete','expected_trials':28,'actual_trials':28,'failures':0,'measured_repetitions':7,'warmups_per_scenario':1,'warmup_results':warmups,'warmup_failures':0,'warmup_parse_error':None,'process_return_code':0,'aborted_or_timed_out':False,'parse_error':None},'expected':SCENARIOS,'inputs':{'scenario_catalog_sha256':sha(canonical(SCENARIOS))},'summary':summarize(trials),'trials':trials,'evidence':{'arithmetic':'binary64','limiter_profile':'not collected','limitations':['tiny analytic fixtures','no competitor/speedup/application-scale/scalability claim','no exact or validated guarantee','candidate reducer validates but retains full candidate cloud']}}
 return finalize(payload,stamp)
def git(*args):return subprocess.check_output(['git',*args],text=True,encoding='utf8').strip()
def main():
 p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--source-commit',required=True);p.add_argument('--harness-commit',required=True);p.add_argument('--build-provenance',type=Path,required=True);p.add_argument('--concurrent-work',type=Path,required=True);p.add_argument('--profile-evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--repetitions',type=int,default=7);p.add_argument('--warmups',type=int,default=1);p.add_argument('--reviewed',action='store_true',help='required acknowledgement that fixed algorithm source and harness were independently reviewed');a=p.parse_args()
 if not a.reviewed: p.error('accepted timing collection requires --reviewed after fixed source SHA and harness review')
 if a.repetitions<7 or a.warmups<1:p.error('need at least 7 repetitions and one warmup')
 if a.out.exists():p.error('refusing to overwrite existing collection')
 import re
 if not re.fullmatch(r'[0-9a-f]{40}',a.source_commit) or not re.fullmatch(r'[0-9a-f]{40}',a.harness_commit):p.error('source and harness commits must be full lowercase 40-character Git SHAs')
 for commit in (a.source_commit,a.harness_commit):
  try:git('cat-file','-e',commit+'^{commit}')
  except subprocess.CalledProcessError:p.error(f'unknown Git commit: {commit}')
 out=a.out.resolve();out.mkdir(parents=True); exe=a.exe.resolve(); before=sha(exe.read_bytes())
 command=[str(exe),'--repetitions',str(a.repetitions),'--warmups',str(a.warmups)]
 try: proc=subprocess.run(command,capture_output=True,text=True,timeout=600,check=False); code=proc.returncode; stdout=proc.stdout; stderr=proc.stderr; aborted=False
 except subprocess.TimeoutExpired as e:code=None;stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else (e.stdout or '');stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else (e.stderr or '');aborted=True
 if sha(exe.read_bytes())!=before:raise SystemExit('executable changed during collection')
 (out/'raw-driver-output.csv').write_text(stdout,encoding='utf8');(out/'process-stderr.txt').write_text(stderr,encoding='utf8')
 (out/'measurement-command.txt').write_text(subprocess.list2cmdline(command)+'\n',encoding='utf8')
 (out/'build-provenance.txt').write_text(a.build_provenance.read_text(encoding='utf8'),encoding='utf8')
 (out/'concurrent-work.txt').write_text(a.concurrent_work.read_text(encoding='utf8'),encoding='utf8')
 (out/'profile-evidence.txt').write_text(a.profile_evidence.read_text(encoding='utf8'),encoding='utf8')
 (out/'scenarios.json').write_text(json.dumps(SCENARIOS,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
 import render
 warmups=[]
 try:
  for line in stderr.splitlines():
   if line.startswith('geo02_warmup='):
    warmups.append(json.loads(line[len('geo02_warmup='):]))
  warmup_keys={(row['scenario'],row['repetition']) for row in warmups}
  expected_warmups={(scenario,repetition) for scenario in SCENARIOS for repetition in range(a.warmups)}
  if len(warmup_keys)!=len(warmups) or warmup_keys!=expected_warmups:raise ValueError('missing/duplicate warmup outcomes')
  for row in warmups:
   if row['status']=='passed' and (not row['oracle_passed'] or not render.check_oracle(row['scenario'],row['output_points']) or not render.check_supports(row['scenario'],row['support_values'])):
    row['status']='oracle_failed';row['oracle_passed']=False
  warmup_failures=sum(row['status']!='passed' or row['oracle_passed'] is not True for row in warmups)
 except Exception as e:
  warmups=[];warmup_failures=a.warmups*len(SCENARIOS);warmup_parse_error=str(e)
 else:warmup_parse_error=None
 try:
  reader=csv.DictReader(stdout.splitlines())
  if tuple(reader.fieldnames or ())!=FIELDS:raise ValueError('unexpected driver CSV header')
  trials=[]
  for row in reader:
   x={k:row[k] for k in FIELDS};x['repetition']=int(x['repetition'])
   for phase in PHASES:x[phase]=int(x[phase]);
   if any(x[p]<0 for p in PHASES) or x['total_ns']<sum(x[p] for p in PHASES[:-1]):raise ValueError('invalid or non-covering phase durations')
   x['output_points']=json.loads(x['output_points']);x['support_values']=json.loads(x['support_values']);x['support_checks']=int(x['support_checks']);
   if x['oracle_passed'] not in ('true','false'):raise ValueError('invalid boolean')
   x['oracle_passed']=x['oracle_passed']=='true';x['input_sha256']=sha(canonical(SCENARIOS[x['scenario']]['inputs']));trials.append(x)
  expected={(s,r) for s in SCENARIOS for r in range(a.repetitions)}
  if {(x['scenario'],x['repetition']) for x in trials}!=expected or len(trials)!=len(expected):raise ValueError('missing/duplicate trial rows')
  parse_error=None
 except Exception as e:trials=[];parse_error=str(e)
 for x in trials:
  case=SCENARIOS[x['scenario']]
  if not render.check_oracle(x['scenario'],x['output_points']) or x['support_checks']!=len(case['directions']) or len(x['support_values'])!=len(case['support']) or any(abs(float(v)-y)>1e-8 for v,y in zip(x['support_values'],case['support'])):x['status']='oracle_failed';x['oracle_passed']=False
 passed=code==0 and not aborted and parse_error is None and warmup_parse_error is None and warmup_failures==0 and len(trials)==a.repetitions*len(SCENARIOS) and all(x['status']=='passed' and x['oracle_passed'] for x in trials)
 payload={'schema':SCHEMA,'report_id':None,'payload_hash_scope':HASH_SCOPE,'algorithm':{'id':'GEO-02','source_commit':a.source_commit,'harness_commit':a.harness_commit,'api':'csl.geometry.affine-sum'},'collection':{'state':'complete' if passed else 'failed','expected_trials':a.repetitions*len(SCENARIOS),'actual_trials':len(trials),'failures':a.repetitions*len(SCENARIOS)-sum(x['status']=='passed' and x['oracle_passed'] for x in trials),'measured_repetitions':a.repetitions,'warmups_per_scenario':a.warmups,'warmup_results':warmups,'warmup_failures':warmup_failures,'warmup_parse_error':warmup_parse_error,'process_return_code':code,'aborted_or_timed_out':aborted,'parse_error':parse_error,'order':'forward scenario order each repetition','timing_unit':'steady-clock nanoseconds'},'expected':SCENARIOS,'inputs':{'scenario_catalog_sha256':sha(canonical(SCENARIOS)),'executable_sha256':before,'build_provenance_sha256':sha(a.build_provenance.read_bytes()),'concurrent_work_sha256':sha(a.concurrent_work.read_bytes()),'profile_evidence_sha256':sha(a.profile_evidence.read_bytes())},'summary':summarize(trials,passed),'trials':trials,'evidence':{'arithmetic':'IEEE 754 binary64','scope':'four tiny deterministic analytic fixtures; descriptive measurements','limiter_profile':'not collected; no OS limiter/CPU sampling available','unavailable_counters':['per-trial CPU time','native thread count','peak memory','OS limiter profiling','internal LP timings'],'limitations':['tiny fixtures only','no competitor, speedup, application-scale, or scalability claim','no exact or validated geometry guarantee','candidate reducer validates output but retains full candidate cloud']}}
 finalize(payload,dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 (out/'records.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
 (out/'raw-events.jsonl').write_text(''.join(json.dumps(t,sort_keys=True,allow_nan=False)+'\n' for t in trials),encoding='utf8')
 (out/'environment.json').write_text(json.dumps({'os':platform.platform(),'architecture':platform.machine(),'cpu_model':platform.processor() or os.environ.get('PROCESSOR_IDENTIFIER'),'logical_cpu_count':os.cpu_count(),'python':platform.python_version(),'native_threads_requested':1,'native_threads_observed':None,'per_trial_cpu':None,'per_trial_peak_memory':None},indent=2)+'\n',encoding='utf8')
 (out/'collection-status.json').write_text(json.dumps({k:payload['collection'][k] for k in ('state','expected_trials','actual_trials','failures','warmups_per_scenario','warmup_results','warmup_failures','warmup_parse_error','process_return_code','aborted_or_timed_out','parse_error')},indent=2)+'\n',encoding='utf8')
 with (out/'summary.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.writer(f);w.writerow(['scenario','phase','unit','median','min','max','range','successful_trials','trials_excluded_from_summary'])
  for s,g in payload['summary'].items():
   for phase,stat in g['phases'].items():w.writerow([s,phase,stat['unit'],stat['median'],stat['min'],stat['max'],stat['range'],stat['successful_trials'],stat['trials_excluded_from_summary']])
 print(payload['report_id']);return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())

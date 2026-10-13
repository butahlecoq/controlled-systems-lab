"""Offline renderer for GEO-02 immutable saved numerical records."""
from __future__ import annotations
import argparse, hashlib, html, json, shutil, zipfile
from pathlib import Path
import collect
COLLECTION_FILES={'records.json','collection-status.json','raw-events.jsonl','summary.csv','raw-driver-output.csv','build-provenance.txt','measurement-command.txt','environment.json','scenarios.json','profile-evidence.txt','process-stderr.txt','concurrent-work.txt'}

def check_oracle(scenario,points,tol=1e-8):
 c=collect.SCENARIOS.get(scenario);expected=c.get('outputs',[]) if c else []
 if not expected or not isinstance(points,list) or not points:return False
 dim=len(expected[0])
 if any(not isinstance(p,list) or len(p)!=dim for p in points):return False
 # The current reducer may retain redundant interior candidates. Require every
 # literal extreme and verify that every retained point lies in the target segment.
 for extreme in (expected[0],expected[-1]):
  if not any(all(abs(float(x)-float(y))<=tol for x,y in zip(p,extreme)) for p in points):return False
 if dim==1:
  lo,hi=sorted((float(expected[0][0]),float(expected[-1][0])))
  return all(lo-tol<=float(p[0])<=hi+tol for p in points)
 if dim==2:
  a=[float(x) for x in expected[0]];b=[float(x) for x in expected[-1]];d=[b[i]-a[i] for i in range(2)];norm=sum(x*x for x in d)
  if norm==0:return all(all(abs(float(p[i])-a[i])<=tol for i in range(2)) for p in points)
  for p in points:
   q=[float(x)-a[i] for i,x in enumerate(p)];t=sum(q[i]*d[i] for i in range(2))/norm
   if t < -tol or t > 1+tol or any(abs(q[i]-t*d[i])>tol for i in range(2)):return False
  return True
 return False

def check_supports(scenario,values,tol=1e-8):
 expected=collect.SCENARIOS.get(scenario,{}).get('support',[])
 return isinstance(values,list) and len(values)==len(expected) and all(abs(float(x)-float(y))<=tol for x,y in zip(values,expected))

def validate(payload):
 if payload.get('schema')!=collect.SCHEMA or payload.get('algorithm',{}).get('id')!='GEO-02':raise ValueError('unsupported GEO-02 record schema')
 if payload.get('timing_scopes')!=collect.TIMING_SCOPES:raise ValueError('timing scopes differ from the pinned report contract')
 if not isinstance(payload.get('report_id'),str) or not payload['report_id'].startswith('geo02-') or not payload['report_id'].endswith(payload.get('payload_sha256','')[:12]):raise ValueError('invalid GEO-02 report identity')
 unsigned={k:v for k,v in payload.items() if k not in ('report_id','payload_sha256','payload_hash_scope')}
 if payload.get('payload_hash_scope')!=collect.HASH_SCOPE or payload.get('payload_sha256')!=hashlib.sha256(collect.canonical(unsigned)).hexdigest():raise ValueError('digest mismatch')
 if payload.get('expected')!=collect.SCENARIOS or payload.get('inputs',{}).get('scenario_catalog_sha256')!=hashlib.sha256(collect.canonical(collect.SCENARIOS)).hexdigest():raise ValueError('scenario catalog differs from pinned catalog')
 collection=payload.get('collection',{}); reps=collection.get('measured_repetitions')
 if type(reps)is not int or reps<1:raise ValueError('invalid repetition count')
 trials=payload.get('trials',[]);wanted={(s,r) for s in collect.SCENARIOS for r in range(reps)};actual={(t.get('scenario'),t.get('repetition')) for t in trials}
 if len(actual)!=len(trials) or actual!=wanted:raise ValueError('scenario/repetition matrix mismatch')
 for t in trials:
  name=t['scenario'];case=collect.SCENARIOS[name]
  if t.get('input_sha256')!=hashlib.sha256(collect.canonical(case['inputs'])).hexdigest():raise ValueError('trial input hash mismatch')
  for key in collect.PHASES:
   if type(t.get(key)) is not int or t[key]<0:raise ValueError('invalid nanosecond phase')
  if t['total_ns']<sum(t[k] for k in collect.PHASES[:-1]):raise ValueError('total duration does not cover measured phases')
  if t.get('oracle_passed') is True and (not check_oracle(name,t.get('output_points')) or not check_supports(name,t.get('support_values')) or t.get('support_checks')!=len(case['directions'])):raise ValueError('saved output fails independent point/support oracle')
 state=collection.get('state');actual_count=collection.get('actual_trials');expected_count=collection.get('expected_trials');failures=collection.get('failures')
 process_code=collection.get('process_return_code');aborted=collection.get('aborted_or_timed_out');parse_error=collection.get('parse_error')
 if state not in ('complete','failed') or type(actual_count)is not int or actual_count!=len(trials):raise ValueError('collection state/count does not match trial rows')
 if type(expected_count)is not int or expected_count<1 or type(failures)is not int or failures<0:raise ValueError('invalid expected/failure trial counts')
 passed=sum(t.get('status')=='passed' and t.get('oracle_passed') is True for t in trials)
 if failures!=expected_count-passed:raise ValueError('collection failure count differs from trial outcomes')
 if process_code is not None and type(process_code)is not int:raise ValueError('invalid collection process return code')
 if type(aborted)is not bool or (parse_error is not None and not isinstance(parse_error,str)):raise ValueError('invalid collection abort/parse metadata')
 warmups_per_scenario=collection.get('warmups_per_scenario');warmups=collection.get('warmup_results');warmup_failures=collection.get('warmup_failures');warmup_parse_error=collection.get('warmup_parse_error')
 if type(warmups_per_scenario)is not int or warmups_per_scenario<1 or not isinstance(warmups,list):raise ValueError('invalid warmup result inventory')
 expected_warmups={(scenario,repetition) for scenario in collect.SCENARIOS for repetition in range(warmups_per_scenario)}
 actual_warmups={(row.get('scenario'),row.get('repetition')) for row in warmups if isinstance(row,dict)}
 if len(actual_warmups)!=len(warmups) or actual_warmups!=expected_warmups:raise ValueError('warmup scenario/repetition matrix mismatch')
 for row in warmups:
  if not isinstance(row.get('status'),str) or not isinstance(row.get('detail'),str) or type(row.get('oracle_passed'))is not bool:raise ValueError('invalid warmup status/detail/oracle')
  if row['status']=='passed' and (not row['oracle_passed'] or not check_oracle(row['scenario'],row.get('output_points')) or not check_supports(row['scenario'],row.get('support_values')) or row.get('support_checks')!=len(collect.SCENARIOS[row['scenario']]['directions'])):raise ValueError('successful warmup fails its independent oracle')
 observed_warmup_failures=sum(row['status']!='passed' or row['oracle_passed'] is not True for row in warmups)
 if type(warmup_failures)is not int or warmup_failures!=observed_warmup_failures or (warmup_parse_error is not None and not isinstance(warmup_parse_error,str)):raise ValueError('warmup failure metadata differs from warmup outcomes')
 if state=='complete' and (expected_count!=len(wanted) or failures!=0 or process_code!=0 or aborted or parse_error is not None or passed!=len(wanted) or warmup_failures!=0 or warmup_parse_error is not None):
  raise ValueError('complete collection metadata does not describe a full successful process')
 expected_summary=collect.summarize(trials,collection.get('state')=='complete')
 if payload.get('summary')!=expected_summary:raise ValueError('phase summaries differ from trial rows')

def render_svg(payload):
 lines=[]
 for i,(name,row) in enumerate(payload['summary'].items()):
  v=row['phases']['total_ns']['median'];label='unavailable' if v is None else str(v)
  y=30+i*28;lines.append(f'<text x="12" y="{y}">{html.escape(name)}</text><text x="440" y="{y}">{label} ns</text>')
 return '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="'+str(max(140,40+28*len(lines)))+'" role="img" aria-label="GEO-02 scenario median total nanoseconds">'+''.join(lines)+'</svg>'

def render_html(payload):
 rows=''.join('<tr><td>'+html.escape(t['scenario'])+'</td><td>'+str(t['repetition'])+'</td><td>'+html.escape(t['status'])+'</td><td>'+str(t['setup_ns'])+'</td><td>'+str(t['operation_ns'])+'</td><td>'+str(t['oracle_ns'])+'</td><td>'+str(t['total_ns'])+'</td><td>'+html.escape(t.get('detail',''))+'</td></tr>' for t in payload['trials'])
 warmup_rows=''.join('<tr><td>'+html.escape(t['scenario'])+'</td><td>'+str(t['repetition'])+'</td><td>'+html.escape(t['status'])+'</td><td>'+('passed' if t['oracle_passed'] else 'failed')+'</td><td>'+html.escape(t.get('detail',''))+'</td></tr>' for t in payload['collection']['warmup_results'])
 svg=render_svg(payload)
 scope='Binary64; four tiny deterministic analytic fixtures. Descriptive only: no competitor, speedup, application-scale, or scalability claim. No exact or validated geometry guarantee. The reducer validates candidate outputs but retains the full candidate cloud (does not apply deletions). CPU counters, native-thread observations, peak-memory measurements, internal LP timings, and OS limiter profiling were unavailable/not collected.'
 timing='<ul>'+''.join('<li><code>'+html.escape(name)+'</code>: '+html.escape(description)+'</li>' for name,description in payload['timing_scopes'].items())+'</ul>'
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GEO-02 affine-sum report</title></head><body><h1>GEO-02 affine-sum report</h1><p>'+html.escape(scope)+'</p><h2>Timing scope</h2>'+timing+'<p><a href="timings.svg">Open timing chart (SVG)</a></p><h2>Warmup checks</h2><table><thead><tr><th>Scenario</th><th>Warmup</th><th>Status</th><th>Oracle</th><th>Detail</th></tr></thead><tbody>'+warmup_rows+'</tbody></table><h2>Raw trials</h2><div tabindex="0"><table><thead><tr><th>Scenario</th><th>Repetition</th><th>Status</th><th>Setup ns</th><th>Operation ns</th><th>Oracle ns</th><th>Total ns</th><th>Detail</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>Report '+html.escape(payload['report_id'])+'; payload SHA-256 '+html.escape(payload['payload_sha256'])+'</p></body></html>\n'

def main():
 p=argparse.ArgumentParser();p.add_argument('--collection',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();data_path=a.collection/'records.json'
 if data_path.is_symlink():p.error('collection records may not be a symlink')
 data=json.loads(data_path.read_text(encoding='utf8'));validate(data)
 actual={x.name for x in a.collection.iterdir() if x.is_file()}
 if actual!=COLLECTION_FILES:p.error('collection bundle inventory does not match the required file set')
 if any(x.is_symlink() for x in a.collection.iterdir()):p.error('collection artifacts may not be symlinks')
 if a.out.exists():p.error('refusing to overwrite bundle')
 zip_path=a.out.parent/(data['report_id']+'.zip')
 if zip_path.exists():p.error('refusing to overwrite offline ZIP')
 a.out.mkdir(parents=True)
 for f in a.collection.iterdir():
  if f.is_file():shutil.copyfile(f,a.out/f.name)
 (a.out/'index.html').write_text(render_html(data),encoding='utf8');(a.out/'timings.svg').write_text(render_svg(data),encoding='utf8')
 files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(a.out.iterdir()) if x.is_file() and x.name!='manifest.json'}
 (a.out/'manifest.json').write_text(json.dumps({'schema':'csl.geo02-bundle/1','report_id':data['report_id'],'files':files},sort_keys=True,indent=2)+'\n',encoding='utf8')
 with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for f in sorted(a.out.iterdir()):
   if f.is_file():
    info=zipfile.ZipInfo(f.name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
    z.writestr(info,f.read_bytes())
if __name__=='__main__':main()

from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, os, platform, statistics, subprocess, sys
from pathlib import Path

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def host_snapshot():
 try:
  code = "$c=Get-CimInstance Win32_Processor;$o=Get-CimInstance Win32_OperatingSystem;[pscustomobject]@{cpu_load_percent=($c|Measure-Object LoadPercentage -Average).Average;logical_processors=($c|Measure-Object NumberOfLogicalProcessors -Sum).Sum;visible_ram_kib=[int64]$o.TotalVisibleMemorySize;free_ram_kib=[int64]$o.FreePhysicalMemory}|ConvertTo-Json -Compress"
  r=subprocess.run(["powershell.exe","-NoProfile","-Command",code],capture_output=True,text=True,timeout=15,check=True); return json.loads(r.stdout)
 except Exception as e: return {"available":False,"reason":type(e).__name__}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--exe',type=Path,required=True); ap.add_argument('--code-commit',required=True); ap.add_argument('--build-log',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--concurrent-work',required=True); a=ap.parse_args()
 if a.out.exists(): raise SystemExit(f'refusing overwrite: {a.out}')
 a.out.mkdir(parents=True)
 started=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
 host_before=host_snapshot(); p=subprocess.run([str(a.exe)],capture_output=True,text=True,encoding='utf-8',errors='replace'); host_after=host_snapshot()
 (a.out/'raw-stdout.jsonl').write_text(p.stdout,encoding='utf-8',newline='\n'); (a.out/'raw-stderr.txt').write_text(p.stderr,encoding='utf-8',newline='\n')
 rows=[]; invalid=[]
 for n,line in enumerate(p.stdout.splitlines(),1):
  try: rows.append(json.loads(line))
  except Exception: invalid.append({'line':n,'raw':line})
 measured=[x for x in rows if not x.get('warmup')]; groups={}
 for x in measured: groups.setdefault((x.get('case_id','unknown'),x.get('method','unknown')),[]).append(x)
 summary=[]
 for (case,method),g in sorted(groups.items()):
  good=[x for x in g if x.get('verified') and x.get('status')=='complete']; times=[x['elapsed_ns'] for x in good if isinstance(x.get('elapsed_ns'),int)]
  def med(field):
   v=[x[field] for x in good if isinstance(x.get(field),(int,float))]; return statistics.median(v) if v else None
  summary.append({'case_id':case,'method':method,'attempts':len(g),'successes':len(good),'failures':len(g)-len(good),'median_ns':statistics.median(times) if times else None,'min_ns':min(times) if times else None,'max_ns':max(times) if times else None,'median_lp_calls':med('lp_calls'),'median_pivots':med('pivots'),'median_degenerate_pivots':med('degenerate_pivots'),'median_bulk_candidates':med('bulk_candidates'),'median_bulk_removals':med('bulk_removals')})
 cache={}
 for line in (a.exe.resolve().parents[1]/'CMakeCache.txt').read_text(errors='replace').splitlines():
  if ':' in line and '=' in line and not line.startswith(('#','//')): cache[line.split(':',1)[0]]=line.split('=',1)[1]
 build_raw=a.build_log.read_bytes(); buildtext=build_raw.decode('utf-8',errors='replace').replace(str(Path.cwd()),'$SOURCE_ROOT').replace(str(a.exe.resolve().parents[1]),'$BUILD_ROOT')
 (a.out/'release-build-log-sanitized.txt').write_text(buildtext,encoding='utf-8',newline='\n')
 srcroot=Path.cwd(); files=['src/geometry/basis_reuse_reducer.cpp','src/geometry/hull_reducer.cpp','include/csl/geometry/basis_reuse_reducer.hpp','include/csl/geometry/hull_reducer.hpp']
 harness=Path(__file__).resolve().parent/'harness'/'opt06_measure.cpp'
 build={'source_code_commit':a.code_commit,'source_identity_scope':'tracked algorithm sources at code_commit; harness is separately hashed','build_generator':cache.get('CMAKE_GENERATOR'),'build_platform':cache.get('CMAKE_GENERATOR_PLATFORM'),'configuration':'Release','compiler':'MSVC cl.exe (Hostx64/x64)','compiler_id':'MSVC','compiler_version':'19.44.35215.0','release_flags':cache.get('CMAKE_CXX_FLAGS_RELEASE'),'cxx_standard':'20','configured_dependency_highs':'1.11.0','executable_sha256':sha(a.exe),'build_log_sha256':hashlib.sha256(build_raw).hexdigest(),'cmake_cache_sha256':sha(a.exe.resolve().parents[1]/'CMakeCache.txt'),'algorithm_source_sha256':{f:sha(srcroot/f) for f in files},'harness_sha256':sha(harness),'build_command':'cmake --build opt06-report-build --config Release --target csl_opt06_measure --parallel 4 --verbose'}
 failed=sum(x['failures'] for x in summary)
 records={'schema':'csl.hull-benchmark-records/1','report_id':'opt06-basis-reuse-20261014-ef70e8c5','created_utc':started,'code_commit':a.code_commit,'source_worktree_head':a.code_commit,'algorithm':{'name':'within-solve phase-I basis-reuse hull classification','implementation':'CSL::geometry::reduce_hull_basis_reuse','source':'src/geometry/basis_reuse_reducer.cpp'},'backend':{'name':'HiGHS LP adapter','version':'1.11.0','configured_threads':1,'presolve':'off','parallel':'off'},'build':build,'environment':{'os':platform.platform(),'machine':platform.machine(),'python':sys.version,'host_before':host_before,'host_after':host_after,'concurrent_work_note':a.concurrent_work,'trial_policy':'one warmup per case and method; seven measured repetitions per case; baseline and basis-reuse order alternated each round; fresh workspace per invocation','timing_scope':'steady_clock around reduce_hull or reduce_hull_basis_reuse only; point cloud setup, HiGHS LP workspace creation, and independent hull-equivalence verification excluded','comparison_status':'descriptive paired timings; no speedup/winner claim; no separate limiter profile'},'fixtures':[{'case_id':'permuted','points':10,'description':'permuted square corners, edge points and interior points'},{'case_id':'degenerate','points':7,'description':'full-dimensional square with a duplicate corner and edge points'},{'case_id':'interior-basis','points':5,'description':'center geometric interior point at ID 0 plus square corners'}],'oracle':'Every timed pair is followed by untimed mutual LP-membership checks of both retained hulls against each other. The deterministic interior-basis fixture is covered by the unit test but excluded from timing because the LP baseline returned incomplete; raw failed attempts are preserved separately.','process':{'exit_code':p.returncode,'invalid_stdout_lines':invalid,'rows':len(rows),'measured_rows':len(measured),'warmup_rows':len(rows)-len(measured),'failures':failed + (1 if p.returncode else 0),'stderr_sha256':sha(a.out/'raw-stderr.txt')},'trials':rows,'summary':summary}
 (a.out/'records.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
 cols=['round','case_id','method','warmup','elapsed_ns','status','verified','lp_calls','pivots','degenerate_pivots','bulk_candidates','bulk_removals','retained','fallback','retained_points','basis_points']
 with (a.out/'trials.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow({k:json.dumps(x.get(k)) if k in ('basis_points','retained_points') else x.get(k) for k in cols}) for x in rows]
 sc=list(summary[0].keys()) if summary else ['case_id','method','attempts','successes','failures','median_ns','min_ns','max_ns']
 with (a.out/'summary.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=sc);w.writeheader();w.writerows(summary)
 if p.returncode or not rows: raise SystemExit(f'measurement process failed: rc={p.returncode}; see raw records')
 print(json.dumps({'rows':len(rows),'measured':len(measured),'failures':failed,'report_id':records['report_id']}))
if __name__=='__main__': main()

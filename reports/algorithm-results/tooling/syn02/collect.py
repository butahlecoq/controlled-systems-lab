#!/usr/bin/env python3
"""Build, measure, validate, and bundle the SYN-02 terminal relation report."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, html, json, os, platform, statistics, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TOOLING = Path(__file__).resolve().parent
SOURCE_COMMIT = "c234a1a04b2f90e34776a2bfa349a91a1d30257d"
UNIT_BOX = {"dimension":2,"inequalities":[[1,0],[-1,0],[0,1],[0,-1]],"upper_bounds":[1,0,1,0],"equalities":[],"equality_values":[]}
SCENARIOS = {
  "linear-face": {"input":{"type":"linear","coefficients":[1,0],"offset":7},"outcome":"optimal", "termination":"completed", "provider":"csl.lp.highs", "value":7.0, "relation":"x=0 in [0,1]^2", "samples":[([0,0],True),([0,.5],True),([0,1],True),([1,0],False),([.2,.8],False)]},
  "constant-linear": {"input":{"type":"linear","coefficients":[0,0],"offset":3},"outcome":"optimal", "termination":"completed", "provider":"csl.lp.highs", "value":3.0, "relation":"whole unit box", "samples":[([0,0],True),([0,1],True),([1,0],True),([1,1],True),([.4,.6],True),([1.01,.5],False)]},
  "psd-null-direction": {"input":{"type":"quadratic","Q":[[2,0],[0,0]],"linear":[0,0],"constant":0,"convention":"0.5*x'Q*x + q'x + c"},"outcome":"optimal", "termination":"completed", "provider":"csl.convex.highs", "value":0.0, "relation":"x=0 in [0,1]^2", "samples":[([0,0],True),([0,.5],True),([0,1],True),([1,0],False),([.2,.8],False)]},
  "rectangular-residual": {"input":{"type":"residual_norm","map":[[1,0]],"target":[0]},"outcome":"optimal", "termination":"completed", "provider":"csl.convex.highs", "value":0.0, "relation":"x=0 in [0,1]^2", "samples":[([0,0],True),([0,.5],True),([0,1],True),([1,0],False),([.2,.8],False)]},
  "shifted-residual-degenerate": {"input":{"type":"residual_norm","map":[[1,0]],"target":[0.5]},"outcome":"undetermined", "termination":"numerical_failure", "provider":"csl.convex.highs", "value":None, "relation":"not constructed", "samples":[],"backend_observation":"Native QP phase reports model status 7; adapter withholds optimality, reporting stationarity violation 1.0 and the diagnostic 'original-space checks unavailable or failing'."},
}
ALLOWLIST = {
 "CMakeLists.txt",
 "reports/algorithm-results/tooling/syn02/terminal_driver.cpp",
 "reports/algorithm-results/tooling/syn02/collect.py",
 "reports/algorithm-results/tooling/syn02/README.md",
 "reports/algorithm-results/tooling/syn02/test_report.py",
 "reports/algorithm-results/tooling/syn02/render_saved.py",
}

def run(command, *, cwd=ROOT, check=True, timeout=None):
    return subprocess.run(command, cwd=cwd, capture_output=True, check=check, timeout=timeout)
def out(command, **kwargs): return run(command, **kwargs).stdout.decode("utf-8", "replace").strip()
def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def canonical(value) -> bytes: return json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False).encode()
def git(*args): return out(["git", *args])
def require(ok, message):
    if not ok: raise ValueError(message)
def tracked_changes(): return set(git("diff", "--name-only", SOURCE_COMMIT, "HEAD").splitlines())
def verify_checkout(harness_commit):
    require(git("rev-parse","HEAD")==harness_commit,"harness commit mismatch")
    require(not git("status","--porcelain=v1","--untracked-files=no"),"tracked source dirty")
    unexpected=tracked_changes()-ALLOWLIST
    require(not unexpected,f"fixed source changed outside reporting-only allowlist: {sorted(unexpected)}")
    require(git("rev-parse",SOURCE_COMMIT)==SOURCE_COMMIT,"fixed source commit unavailable")

def proc_name():
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return str(winreg.QueryValueEx(k,"ProcessorNameString")[0]).strip()
    return platform.processor()

def redact_bytes(data: bytes, roots):
    text=data.decode("utf-8","replace")
    for path,token in roots:
        for spelling in (str(path),str(path).replace("\\","/")):
            text=text.replace(spelling,token)
    return text.encode("utf-8")

def validate_trial(row):
    name=row["scenario"]; oracle=SCENARIOS[name]; failures=[]
    if row.get("schema")!="csl.syn02-terminal-trial/1": failures.append("schema")
    if row.get("status")!="passed": failures.append("driver_status")
    if row.get("outcome")!=oracle["outcome"]: failures.append("outcome")
    if row.get("termination")!=oracle["termination"]: failures.append("termination")
    if row.get("provider")!=oracle["provider"]: failures.append("provider")
    if oracle["outcome"]=="optimal":
        if not all(row.get(k) is True for k in ("relation","optimization_present","optimum_present")): failures.append("optimal_result_presence")
        actual=row.get("primal_value")
        if actual is None or abs(actual-oracle["value"])>1e-7: failures.append("literal_objective")
        if row.get("relation_support")!="unestablished" or row.get("optimum_support")!="unestablished": failures.append("assurance_scope")
        observations=row.get("solver_observations",{})
        residual_keys=("native.primal_infeasibility","native.dual_infeasibility") if oracle["provider"]=="csl.lp.highs" else ("check.rows.violation","check.variables.violation","check.stationarity.violation")
        if any(key not in observations or abs(float(observations[key]))>1e-7 for key in residual_keys): failures.append("backend_residual")
        inequalities=row.get("inequalities",[]); upper=row.get("upper_bounds",[])
        equalities=row.get("equalities",[]); rhs=row.get("equality_values",[])
        expected_rows=[[1,0],[-1,0],[0,1],[0,-1]]
        if inequalities!=expected_rows or upper!=[1,0,1,0] or len(equalities)<1 or len(rhs)!=len(equalities): failures.append("relation_shape")
        for point, expected in oracle["samples"]:
            feasible=all(sum(a*x for a,x in zip(line,point))<=b+1e-7 for line,b in zip(inequalities,upper)) and all(abs(sum(a*x for a,x in zip(line,point))-b)<=1e-7 for line,b in zip(equalities,rhs))
            if feasible!=expected: failures.append("literal_relation_sample")
    else:
        if row.get("relation") is not False or row.get("optimization_present") is not True: failures.append("undetermined_relation_scope")
        if row.get("termination")!="numerical_failure" or not row.get("raw_diagnostics"): failures.append("undetermined_diagnostic")
        observations=row.get("solver_observations",{})
        if observations.get("phase.qp.model_status")!=7 or observations.get("optimality.withheld")!="original-space checks unavailable or failing" or observations.get("check.stationarity.violation")!=1: failures.append("retained_qp_diagnostic")
    return failures

def parse_solver_observations(raw_diagnostics):
    result={}
    for line in raw_diagnostics.splitlines():
        if line.startswith("native.log:"): break
        if "=" not in line: continue
        key,value=line.split("=",1)
        try: result[key]=float(value) if any(c in value.lower() for c in (".","e")) else int(value)
        except ValueError: result[key]=value
    return result

def summarize(rows):
    result=[]
    for name in SCENARIOS:
        trials=[r for r in rows if not r["warmup"] and r["scenario"]==name]
        matched=[r for r in trials if not r["validation_errors"]]
        successful=[r for r in matched if r["termination"]=="completed"]
        item={"scenario":name,"requested":len(trials),"matched_expected":len(matched),"completed":len(successful),"failed":len(trials)-len(matched),
              "non_success":sum(r["termination"]!="completed" for r in trials),"expected_outcome":SCENARIOS[name]["outcome"],"expected_termination":SCENARIOS[name]["termination"],"timings":{}}
        item["observed_outcomes"]={key:sum(r.get("outcome")==key for r in trials) for key in sorted({r.get("outcome","missing") for r in trials})}
        item["observed_terminations"]={key:sum(r.get("termination")==key for r in trials) for key in sorted({r.get("termination","missing") for r in trials})}
        item["observed_providers"]={key:sum(r.get("provider")==key for r in trials) for key in sorted({r.get("provider","missing") for r in trials})}
        item["relation_count"]=sum(r.get("relation") is True for r in trials)
        item["objective_bounds"]={"lower_available":sum(r.get("lower_bound") is not None for r in trials),"upper_available":sum(r.get("upper_bound") is not None for r in trials)}
        objective_values=[float(r["primal_value"]) for r in trials if r.get("primal_value") is not None]
        item["primal_objective_value"]={"min":min(objective_values),"max":max(objective_values),"count":len(objective_values)} if objective_values else None
        residual_fields=("native.primal_infeasibility","native.dual_infeasibility","check.rows.violation","check.variables.violation","check.stationarity.violation","check.signs.violation","check.complementarity.violation")
        item["residual_observations"]={field:{"max":max(float(r["solver_observations"][field]) for r in trials if field in r.get("solver_observations",{})),"count":sum(field in r.get("solver_observations",{}) for r in trials)} for field in residual_fields if any(field in r.get("solver_observations",{}) for r in trials)}
        for key in ("prepare_ns","solve_ns","oracle_ns","total_ns"):
            vals=[int(r[key]) for r in successful]
            item["timings"][key]={"median_ns":statistics.median(vals),"min_ns":min(vals),"max_ns":max(vals)} if len(vals)>=5 and len(successful)==len(trials) else None
        result.append(item)
    return result

def svg(summary):
    keys=["solve_ns","total_ns"]; colors={"solve_ns":"#146c94","total_ns":"#8b5cf6"}
    good=[s for s in summary if s["timings"]["solve_ns"]]
    width,height=920,360; left,top=235,36; rowh=48
    maximum=max((s["timings"][k]["max_ns"] for s in good for k in keys),default=1)
    scale=560/maximum
    bits=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc"><title id="title">SYN-02 measured latency ranges</title><desc id="desc">Median and min-to-max range for solve and input-to-verified-result intervals, in milliseconds.</desc><style>text{{font:13px system-ui,sans-serif}}.axis{{stroke:#64748b;stroke-width:1}}.range{{stroke-width:3}}.median{{stroke:#111827;stroke-width:2}}</style>']
    for i,s in enumerate(good):
        y=top+i*rowh; bits.append(f'<text x="12" y="{y+17}">{html.escape(s["scenario"])}</text>')
        for j,key in enumerate(keys):
            st=s["timings"][key]; yy=y+j*16
            x0=left+st["min_ns"]*scale;x1=left+st["max_ns"]*scale;xm=left+st["median_ns"]*scale
            bits.append(f'<line class="range" x1="{x0:.1f}" y1="{yy}" x2="{x1:.1f}" y2="{yy}" stroke="{colors[key]}"/><line class="median" x1="{xm:.1f}" y1="{yy-5}" x2="{xm:.1f}" y2="{yy+5}"/><text x="{left+565}" y="{yy+5}">{key.replace("_ns", "")} · {st["median_ns"]/1e6:.3f} ms</text>')
    bits.append(f'<line class="axis" x1="{left}" y1="{top-12}" x2="{left+560}" y2="{top-12}"/><text x="{left}" y="{height-12}">0 ms</text><text x="{left+430}" y="{height-12}">{maximum/1e6:.3f} ms maximum range</text></svg>')
    return "".join(bits)

def write_bundle(bundle, payload, raw, environment, provenance, profile, profile_raw, build_log, configure_log, command, profile_note):
    bundle.mkdir(parents=True,exist_ok=False)
    for row in raw:
        row["solver_observations"]=parse_solver_observations(row.get("raw_diagnostics",""))
    raw_bytes="".join(json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n" for row in raw).encode()
    rows=[r for r in raw if not r["warmup"]]
    with (bundle/"trials.csv").open("w",newline="",encoding="utf-8") as f:
        fields=["scenario","repetition","status","validation_errors","outcome","termination","relation","optimization_present","optimum_present","provider","primal_value","lower_bound","upper_bound","prepare_ns","solve_ns","oracle_ns","total_ns","solver_observations"]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows: writer.writerow({k:(json.dumps(r.get(k),separators=(",",":")) if isinstance(r.get(k),list) else r.get(k)) for k in fields})
    (bundle/"raw-events.jsonl").write_bytes(raw_bytes)
    (bundle/"records.json").write_text(json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    (bundle/"environment.json").write_text(json.dumps(environment,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (bundle/"build-provenance.json").write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (bundle/"profile-evidence.json").write_text(json.dumps(profile,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (bundle/"profile-raw.jsonl").write_bytes(profile_raw)
    (bundle/"etw-profile-attempt.txt").write_text("Command: wpr -start CPU -filemode\nResult: Failed to enable the policy to profile system performance.\nProfile Id: CPU.Verbose.File\nError code: 0xc5585011\n\nThe separate process-counter run remains in profile-evidence.json and profile-raw.jsonl; it contains no call-stack attribution.\n",encoding="utf-8")
    (bundle/"build-log.txt").write_bytes(build_log)
    (bundle/"configure-log.txt").write_bytes(configure_log)
    (bundle/"measurement-command.txt").write_text(command+"\n",encoding="utf-8")
    (bundle/"profile-note.txt").write_text(profile_note+"\n",encoding="utf-8")
    (bundle/"terminal_driver.cpp").write_bytes((TOOLING/"terminal_driver.cpp").read_bytes())
    for tool_name in ("collect.py", "render_saved.py", "test_report.py", "README.md"):
        (bundle/tool_name).write_bytes((TOOLING/tool_name).read_bytes())
    # Renderer consumes the just-written records file, keeping report generation
    # reproducible without invoking the measured executable again.
    subprocess.run([sys.executable, str(TOOLING/"render_saved.py"),
                    "--records", str(bundle/"records.json"), "--out-dir", str(bundle)],
                   cwd=ROOT, check=True)
    files={p.name:sha(p.read_bytes()) for p in sorted(bundle.iterdir()) if p.is_file() and p.name!="manifest.json"}
    manifest={"schema":"csl.syn02-report-manifest/1","report_id":payload["report_id"],"source_commit":SOURCE_COMMIT,"harness_commit":payload["harness_commit"],"files":files}
    (bundle/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    with zipfile.ZipFile(bundle.with_suffix(".zip"),"x",compression=zipfile.ZIP_STORED) as z:
        for p in sorted(bundle.iterdir()):
            if p.is_file(): z.write(p,p.name)

def render_html(p):
    table=[]
    for s in p["summary"]:
        time=s["timings"]["solve_ns"]
        stat="No success-only summary" if time is None else f"{time['median_ns']/1e6:.3f} ms median ({time['min_ns']/1e6:.3f}–{time['max_ns']/1e6:.3f} ms), n={s['completed']}"
        actual="; ".join(f"{html.escape(k)}: {v}" for k,v in s["observed_terminations"].items()) or "no result"
        value=s["primal_objective_value"]
        obj="unavailable" if value is None else (f"{value['min']:.8g}" if value['min']==value['max'] else f"{value['min']:.8g}–{value['max']:.8g}")
        residual="; ".join(f"{html.escape(k)} max {v['max']:.2g}" for k,v in s["residual_observations"].items()) or "unavailable"
        providers="; ".join(f"{html.escape(k)}: {v}" for k,v in s["observed_providers"].items())
        bounds=f"lower {s['objective_bounds']['lower_available']}/{s['requested']}; upper {s['objective_bounds']['upper_available']}/{s['requested']}"
        detail=SCENARIOS[s["scenario"]].get("backend_observation","")
        detail_html=f"<br><small>{html.escape(detail)}</small>" if detail else ""
        table.append(f"<tr><th>{html.escape(s['scenario'])}</th><td>{html.escape(s['expected_outcome'])} / {html.escape(s['expected_termination'])}<br>{actual}; {s['matched_expected']}/{s['requested']} matched; {s['non_success']} non-success{detail_html}</td><td>{providers}<br>{s['relation_count']} relations; {bounds}</td><td>{obj}</td><td>{residual}</td><td>{stat}</td></tr>")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SYN-02 terminal minimizer report {html.escape(p['report_id'])}</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#172033}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd3dd;padding:.55rem;text-align:left}}code{{overflow-wrap:anywhere}}figure{{margin:2rem 0}}.notice{{background:#f3f6fa;padding:1rem;border-left:4px solid #146c94}}</style></head><body><h1>Terminal minimizer relation construction (SYN-02)</h1><p><strong>Descriptive single-adapter latency report.</strong> Five analytic H-polyhedral fixtures exercise the public <code>TerminalOptimizer</code> with the real HiGHS LP and convex providers. No competitor, speedup, throughput, or scale claim is made.</p><div class="notice"><strong>Evidence limit:</strong> returned objective and relation checks use binary64 and finite literal sample points. Relation support and optimum support remain <em>Unestablished</em>; these checks do not certify exact equality, global optimality, or the complete optimizer relation. The shifted residual fixture retains its actual <code>undetermined</code> outcome, <code>numerical_failure</code> termination and missing relation. Its native QP phase reports model status 7, while the adapter withholds optimality; the retained stationarity violation is 1.0.</div><h2>Measured outcomes and latency</h2><table><thead><tr><th>Fixture</th><th>Expected and observed outcomes</th><th>Backend and evidence counts</th><th>Actual primal objective or witness</th><th>Backend residual observations</th><th>TerminalOptimizer::solve</th></tr></thead><tbody>{''.join(table)}</tbody></table><figure>{svg(p['summary'])}<figcaption>Median markers and observed minimum-to-maximum ranges. The measured interval covers the call to <code>TerminalOptimizer::solve</code>; provider selection/setup and output checks are recorded separately. No timing includes process startup, compilation, or rendering. HiGHS native logging and callback work are within the solve interval.</figcaption></figure><h2>Method</h2><p>Each measured attempt constructs a fresh resolved problem, unit-box terminal slice, provider registries and prepared providers, then calls <code>solve</code> using one configured worker/thread. One warmup is excluded per fixture. Seven measured rounds alternate forward and reverse fixture order. All attempts and non-success outcomes remain in the raw records. The shifted residual provides an unestablished primal witness value only; it is not reported as an optimum.</p><p><strong>Source:</strong> <code>{SOURCE_COMMIT}</code><br><strong>Harness/artifact commit:</strong> <code>{html.escape(p['harness_commit'])}</code><br><strong>Build:</strong> {html.escape(p['provenance']['compiler'])}; Release; {html.escape(p['environment']['os'])}; {html.escape(p['environment']['processor'])}</p><p>Profile result: {html.escape(p['profile_summary'])}</p><p>Files: <a href="records.json">records.json</a> · <a href="raw-events.jsonl">raw events</a> · <a href="trials.csv">trials.csv</a> · <a href="profile-evidence.json">profile evidence</a> · <a href="manifest.json">manifest</a>. Publication URL is pending independent report review and Pages deployment.</p></body></html>'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--cmake",type=Path,required=True);ap.add_argument("--build-dir",type=Path,required=True);ap.add_argument("--out-root",type=Path,required=True);ap.add_argument("--harness-commit",required=True);ap.add_argument("--generator",default="Visual Studio 17 2022");ap.add_argument("--architecture",default="x64");ap.add_argument("--repetitions",type=int,default=7);ap.add_argument("--warmups",type=int,default=1);ap.add_argument("--timeout",type=int,default=120);a=ap.parse_args()
    require(a.repetitions>=7 and a.warmups>=1,"accepted profile requires >=7 repetitions and >=1 warmup")
    verify_checkout(a.harness_commit);require(a.cmake.is_file(),"CMake executable not found");require(not a.build_dir.exists(),"build directory must be fresh")
    try: import psutil
    except ImportError as e: raise RuntimeError("psutil required for host/environment and profile observations") from e
    build=a.build_dir.resolve(); out_root=a.out_root.resolve(); build.mkdir(parents=True)
    (build/".cmake/api/v1/query").mkdir(parents=True);(build/".cmake/api/v1/query/codemodel-v2").touch();(build/".cmake/api/v1/query/toolchains-v1").touch()
    config=[str(a.cmake),"-S",str(ROOT),"-B",str(build),"-G",a.generator,"-A",a.architecture,"-DCSL_BUILD_SYN02_REPORT=ON","-DBUILD_TESTING=OFF","-DCMAKE_BUILD_TYPE=Release"]
    configured=run(config,check=False);configure_log=configured.stdout+configured.stderr;require(configured.returncode==0,"CMake configure failed; logs retained only in terminal output")
    built=run([str(a.cmake),"--build",str(build),"--config","Release","--target","csl_syn02_terminal_report","--parallel","4","--verbose"],check=False)
    build_log=built.stdout+built.stderr;require(built.returncode==0,"Release build failed; logs retained only in terminal output")
    require(git("rev-parse","HEAD")==a.harness_commit and not git("status","--porcelain=v1","--untracked-files=no"),"checkout changed during build")
    cache=(build/"CMakeCache.txt").read_text(errors="replace")
    require(f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT.as_posix()}" in cache or f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT}" in cache,"build is not sourced from pinned worktree")
    index_files=list((build/".cmake/api/v1/reply").glob("index-*.json"));require(index_files,"CMake File API reply absent")
    idx=json.loads(index_files[-1].read_text());cm=json.loads((build/".cmake/api/v1/reply"/idx["reply"]["codemodel-v2"]["jsonFile"]).read_text())
    config_model=next((c for c in cm["configurations"] if c["name"]=="Release"),None);require(config_model is not None,"Release codemodel absent")
    target=next((t for t in config_model["targets"] if t["name"]=="csl_syn02_terminal_report"),None);require(target is not None,"report executable absent from codemodel")
    target_doc=json.loads((build/".cmake/api/v1/reply"/target["jsonFile"]).read_text());groups=[g for g in target_doc.get("compileGroups",[]) if g.get("language")=="CXX"]
    require(len(groups)==1 and groups[0].get("languageStandard",{}).get("standard")=="20","driver must use C++20")
    flags=" ".join(f.get("fragment","") for f in groups[0].get("compileCommandFragments",[]));require(("/DNDEBUG" in flags or "-DNDEBUG" in flags) and ("/O2" in flags or "-O2" in flags),"Release/NDEBUG optimization flags missing")
    artifacts=[build/p["path"] for p in target_doc.get("artifacts",[]) if Path(p["path"]).suffix.lower()==".exe"];require(len(artifacts)==1 and artifacts[0].is_file(),"one built report executable required");exe=artifacts[0]
    host_cpu_before=psutil.cpu_percent(interval=1)
    args=[str(exe),str(a.repetitions),str(a.warmups)];start=__import__("time").perf_counter_ns();measured=run(args,check=False,timeout=a.timeout);elapsed=__import__("time").perf_counter_ns()-start
    host_cpu_after=psutil.cpu_percent(interval=1)
    output_lines=measured.stdout.splitlines();require(output_lines,"report executable emitted no identity/trials")
    run_identity=json.loads(output_lines[0].decode("utf-8"));require(run_identity=={"schema":"csl.syn02-terminal-run/1","source_commit":SOURCE_COMMIT,"harness_commit":a.harness_commit},"embedded executable source/harness identity mismatch")
    raw=[]
    for i,line in enumerate(output_lines[1:],1):
        try:
            row=json.loads(line.decode("utf-8"));row["attempt_index"]=i
            row["source_commit"]=SOURCE_COMMIT;row["harness_commit"]=a.harness_commit
            row["scenario_hash"]=sha(canonical({"scenario":SCENARIOS[row["scenario"]],"terminal_slice":UNIT_BOX}))
            row["trial_id"]=f"{SOURCE_COMMIT[:8]}-{a.harness_commit[:8]}-{row['scenario']}-{row['repetition']}"
            row["solver_observations"]=parse_solver_observations(row.get("raw_diagnostics",""))
            row["validation_errors"]=validate_trial(row);raw.append(row)
        except Exception as exc: raw.append({"schema":"csl.syn02-terminal-trial/1","status":"parse_failed","attempt_index":i,"validation_errors":[str(exc)],"warmup":False,"scenario":"unknown"})
    require(len(raw)==5*(a.repetitions+a.warmups),f"expected complete raw trial matrix; got {len(raw)} events")
    require(len([r for r in raw if not r["warmup"]])==5*a.repetitions,"measured matrix incomplete")
    for name in SCENARIOS:
        warm=[r for r in raw if r.get("scenario")==name and r.get("warmup")]
        measured_rows=[r for r in raw if r.get("scenario")==name and not r.get("warmup")]
        require(len(warm)==a.warmups and len(measured_rows)==a.repetitions,"per-fixture warmup/trial matrix incomplete: "+name)
        require(len({r["repetition"] for r in measured_rows})==a.repetitions,"duplicate measured repetition: "+name)
    summary=summarize(raw);results_ok=all(s["failed"]==0 and s["matched_expected"]==s["requested"] for s in summary)
    # Separate profiling run: time-sampled process counters, excluded from measured trials.
    profile_summary="No CPU stack profile: WPR could not enable the performance profiling policy (0xc5585011). Separate 1,000-round process CPU/RSS sampling completed; limiter unknown."
    profile={"schema":"csl.syn02-process-counters/1","separate_from_reported_trials":True,"source_commit":SOURCE_COMMIT,"command":"Separate 1000-repetition process CPU/RSS observation.","etw_stack_profile":"unavailable","etw_failure":"WPR -start CPU -filemode returned 0xc5585011: Failed to enable the policy to profile system performance.","status":"pending","limiter":"unknown","reason":"process counters do not attribute work to a source function"}
    # Capture process CPU/RSS during an independent long batch. It is a limiter observation only,
    # not source-level attribution or a reported latency sample.
    import time
    profile_args=[str(exe),"1000","1"];samples=[]
    profile_stdout_path=build/"profile-raw.jsonl";profile_stderr_path=build/"profile-stderr.txt"
    with profile_stdout_path.open("wb") as profile_stdout, profile_stderr_path.open("wb") as profile_stderr:
      p=subprocess.Popen(profile_args,cwd=ROOT,stdout=profile_stdout,stderr=profile_stderr)
      startp=time.perf_counter_ns();proc=psutil.Process(p.pid)
      while p.poll() is None:
          try:
              ct=proc.cpu_times();mi=proc.memory_info();samples.append({"elapsed_ns":time.perf_counter_ns()-startp,"process_cpu_seconds":ct.user+ct.system,"resident_bytes":mi.rss})
          except psutil.NoSuchProcess: break
          time.sleep(.01)
      p.wait()
    pout=profile_stdout_path.read_bytes();perr=profile_stderr_path.read_bytes();profile_raw=pout
    profile_wall=time.perf_counter_ns()-startp
    profile_lines=pout.splitlines();profile_identity=json.loads(profile_lines[0]) if profile_lines else {}
    require(profile_identity=={"schema":"csl.syn02-terminal-run/1","source_commit":SOURCE_COMMIT,"harness_commit":a.harness_commit},"profile executable identity mismatch")
    try: profile_events=[json.loads(line) for line in profile_lines[1:]]
    except Exception: profile_events=[]
    profile_validation=[validate_trial(r) for r in profile_events]
    profile.update({"status":"counter_profile_completed" if p.returncode==0 and not perr else "counter_profile_failed","wall_ns":profile_wall,"process_return_code":p.returncode,"stderr":perr.decode("utf-8","replace"),"samples":samples,"sample_interval_target_ms":10,"max_sampled_cpu_seconds":max((s["process_cpu_seconds"] for s in samples),default=0),"max_sampled_resident_bytes":max((s["resident_bytes"] for s in samples),default=0),"profile_trial_events":len(profile_events),"profile_non_success":sum(r.get("termination")!="completed" for r in profile_events if not r.get("warmup")),"profile_all_expected":bool(profile_events) and all(not errors for errors in profile_validation),"limiter":"unknown","limiter_reason":"sampling captured only process CPU and RSS counters, not call stacks; no source attribution is justified"})
    if p.returncode!=0 or len(profile_events)!=5*1001 or not profile["profile_all_expected"]:
        profile["status"]="process_counter_sampling_incomplete"
        profile["incomplete_reason"]="separate profile process returned incomplete output or an expected-result check failed"
    profile_summary="No CPU stack profile: WPR could not enable the performance profiling policy (0xc5585011). Separate 1,000-round process CPU/RSS sampling completed; limiter unknown."
    source_tree=git("rev-parse",f"{SOURCE_COMMIT}^{{tree}}")
    compiler_file=next((build/"CMakeFiles").glob("*/CMakeCXXCompiler.cmake"));compiler_text=compiler_file.read_text(errors="replace")
    import re
    compiler_id=re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)',compiler_text);compiler_version=re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)',compiler_text)
    target_by_id={t["id"]:t for t in config_model["targets"]};target_docs={}
    for item in config_model["targets"]:target_docs[item["id"]]=json.loads((build/".cmake/api/v1/reply"/item["jsonFile"]).read_text())
    closure={}
    def visit_target(target_id):
        if target_id in closure:return
        item=target_docs[target_id]
        closure[target_id]={"name":item["name"],"type":item["type"],"dependencies":[d["id"] for d in item.get("dependencies",[])],"sources":[str(Path(s["path"])) for s in item.get("sources",[])],"compile_groups":item.get("compileGroups",[]),"artifacts":item.get("artifacts",[])}
        for dep in item.get("dependencies",[]):
            if dep["id"] in target_docs:visit_target(dep["id"])
    visit_target(target["id"])
    provenance={"schema":"csl.syn02-build-provenance/1","source_commit":SOURCE_COMMIT,"source_tree":source_tree,"harness_commit":a.harness_commit,"configuration":"Release","cxx_standard":"20","release_flags":flags,"binary_sha256":sha(exe.read_bytes()),"driver_sha256":sha((TOOLING/"terminal_driver.cpp").read_bytes()),"compiler":(compiler_id.group(1)+" "+compiler_version.group(1)) if compiler_id and compiler_version else "unavailable","cmake_generator":a.generator,"target":"csl_syn02_terminal_report","configure_command":["cmake","-S","SOURCE_ROOT","-B","BUILD_ROOT","-G",a.generator,"-A",a.architecture,"-DCSL_BUILD_SYN02_REPORT=ON","-DBUILD_TESTING=OFF","-DCMAKE_BUILD_TYPE=Release"],"build_command":["cmake","--build","BUILD_ROOT","--config","Release","--target","csl_syn02_terminal_report","--parallel","4","--verbose"],"target_closure":closure,"checkout_clean_before":True,"checkout_clean_after":True}
    environment={"captured_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"os":platform.platform(),"machine":platform.machine(),"processor":proc_name(),"logical_cpus":psutil.cpu_count(logical=True),"physical_cpus":psutil.cpu_count(logical=False),"memory_bytes":psutil.virtual_memory().total,"cpu_percent_before":host_cpu_before,"cpu_percent_after":host_cpu_after,"simultaneous_work":"No intentional concurrent benchmark; background processes may affect host load.","requested_workers":1,"configured_native_threads":1,"observed_native_threads":"Unavailable; not inferred from the configured policy","cache_policy":"One excluded warmup per scenario; one process; fresh fixture, registries and prepared providers on every trial.","seed":None}
    payload={"schema":"csl.syn02-terminal-report/1","report_id":"pending","source_commit":SOURCE_COMMIT,"harness_commit":a.harness_commit,"scenario_catalog":SCENARIOS,"terminal_slice":UNIT_BOX,"scenario_hashes":{name:sha(canonical({"scenario":spec,"terminal_slice":UNIT_BOX})) for name,spec in SCENARIOS.items()},"environment":environment,"provenance":provenance,"profile_summary":profile_summary,"measurement":{"kind":"descriptive_single_adapter","scope":"Terminal optimizer on resolved objectives and a supplied terminal H-slice; not system simulation or complete control synthesis","adapter":"HiGHS LP and convex adapters selected through PreparedProvider","backend":{"name":"HiGHS","version":"1.11.0","source_archive_sha256":"2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275","lp_solver":"simplex","presolve":"off","parallel":"off","configured_native_threads":1,"random_seed":0,"absolute_and_relative_tolerance":1e-8,"small_matrix_value":1e-12,"iteration_limit":2147483647,"time_limit":"infinity"},"resource_policy":{"total_threads":1,"outer_workers":1,"threads_per_worker":1,"memory_bytes":None},"repetitions":a.repetitions,"warmups_per_scenario":a.warmups,"fixture_order":"alternating forward/reverse per round","timing_scopes":{"prepare_ns":"resolved problem, slice construction, LP/convex registration, provider selection/preparation","solve_ns":"TerminalOptimizer::solve call only, including internal program setup/workspace/run/anchor and relation construction","oracle_ns":"consumption of returned status/evidence and captured result fields; literal independent verification performed from saved rows after timing","total_ns":"fixture resolution through call and in-process output checks, excluding process startup, output serialization, destruction and rendering"},"interval_unit":"nanoseconds","number_of_process_trials":1,"process_startup_included":False,"driver_exit_code":measured.returncode,"process_elapsed_ns_outside_per_trial":elapsed},"summary":summary,"attempt_counts":{"measured":len([r for r in raw if not r["warmup"]]),"matched_expected":sum(s["matched_expected"] for s in summary),"failed":sum(s["failed"] for s in summary),"non_success":sum(s["non_success"] for s in summary),"missing":5*a.repetitions-len([r for r in raw if not r["warmup"]])},"evidence_limits":["binary64 literal fixture checks, not exact or validated arithmetic","relation samples and H representation checks do not certify full set equality or full minimizer-family completeness","global optimum and relation support remain Unestablished","the shifted residual case returns undetermined with numerical_failure and no constructed relation","tiny analytic fixtures only; no comparator, speedup, application-scale, throughput, or scalability claim","limiter unknown because no call-stack profile evidence was collected"]}
    payload["report_id"]="syn02-terminal-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")+"-"+SOURCE_COMMIT[:8]+"-"+sha(canonical({"summary":summary,"raw_sha":sha(measured.stdout),"binary_sha":provenance["binary_sha256"],"harness":a.harness_commit}))[:12]
    profile_note="Separate process-counter-only invocation (1000 rounds, excluded from reported trials). Process CPU and resident-memory snapshots were sampled every ~10 ms. WPR CPU stack capture could not be enabled: command returned 0xc5585011 and reported 'Failed to enable the policy to profile system performance'. The limiting function/path remains unknown; no performance cause is inferred."
    if profile["status"]=="counter_profile_completed":profile["status"]="process_counter_sampling_completed"
    out_dir=out_root/payload["report_id"]
    require(not out_dir.exists() and not out_dir.with_suffix(".zip").exists(),"versioned report destination already exists")
    out_dir.parent.mkdir(parents=True,exist_ok=True)
    provenance=json.loads(redact_bytes(canonical(provenance),[(ROOT,"SOURCE_ROOT"),(build,"BUILD_ROOT")]))
    payload["provenance"]=provenance
    write_bundle(out_dir,payload,raw,environment,provenance,profile,profile_raw,
                 redact_bytes(build_log,[(ROOT,"SOURCE_ROOT"),(build,"BUILD_ROOT")]),
                 redact_bytes(configure_log,[(ROOT,"SOURCE_ROOT"),(build,"BUILD_ROOT")]),
                 " ".join([str(exe).replace(str(build),"BUILD_ROOT"),str(a.repetitions),str(a.warmups)]),profile_note)
    require(results_ok,"one or more measured trials failed the literal oracle; complete report bundle retained at "+str(out_dir))
    print(json.dumps({"report_id":payload["report_id"],"bundle":str(out_dir),"source_commit":SOURCE_COMMIT,"harness_commit":a.harness_commit,"summary":summary,"profile_status":profile["status"]},indent=2))

if __name__=="__main__": main()

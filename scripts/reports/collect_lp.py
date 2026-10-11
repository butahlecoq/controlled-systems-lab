"""Process/provenance adapter for the fixed registered C++ LP fixture driver."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import report_data as data

PIN="2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275"
BACKEND={"id":"csl.lp.highs","version":"1.0.0+highs.1.11.0"}
ROOT=Path(__file__).resolve().parents[2]


def utc(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def sha_bytes(value): return hashlib.sha256(value).hexdigest()


def events_from_bytes(raw,aborted=False):
    events=[]
    lines=raw.splitlines(keepends=True)
    for index,line in enumerate(lines):
        if line.strip():
            try: event=data.parse_json(line.decode("utf-8"))
            except (ValueError,UnicodeDecodeError):
                # Only a killed/failed writer's unterminated last line may be partial.
                # Complete malformed lines remain errors; original bytes stay on disk.
                if aborted and index==len(lines)-1 and not line.endswith(b'\n'): break
                raise
            data.require(event["schema"]==data.EVENT_SCHEMA,"unknown event schema")
            events.append(event)
    return events


def scenarios(header):
    values=copy.deepcopy(header["scenarios"])
    for scenario in values:
        data.validate_input(scenario["input"])
        scenario["input_sha256"]=data.input_digest(scenario["input"])
        scenario["scenario_sha256"]=data.scenario_digest(scenario)
    return values


def event_payload(events,return_code,raw,stderr,provenance,environment,profile,aborted=False):
    data.require(events and events[0]["event"]=="header","missing event header")
    data.require(all(e["schema"]==data.EVENT_SCHEMA for e in events),"unknown event version")
    data.require(sum(e["event"]=="header" for e in events)==1,"duplicate header")
    header=events[0]
    data.require(header["purpose"] in ("test","measurement"),"profile/calibration cannot become latency view")
    end=[e for e in events if e["event"]=="end"]
    data.require(len(end)<=1,"duplicate completion marker")
    if end: data.require(events[-1] is end[0],"events after completion")
    known={"header","trial","serialization","calibration","end"}
    data.require(all(e["event"] in known for e in events),"unknown event kind")
    trials=[]
    for event in events:
        if event["event"]!="trial": continue
        trial=copy.deepcopy(event["trial"])
        if trial["purpose"]=="warmup":
            data.require(header["purpose"]=="measurement","warmup in smoke")
            continue
        data.require(trial["purpose"]==header["purpose"],"mixed trial purposes")
        result=trial["result"]
        trial["native_iterations"]=data.native_iterations(result["raw_diagnostics"]) if result else {"available":False,"reason":"no returned native diagnostic"}
        trials.append(trial)
    if end:
        data.require(end[0]["emitted_trials"]==len(trials),"end count mismatch")
        data.require(end[0]["failures"]==sum(not t["validation"]["passed"] for t in trials),"end failures mismatch")
    values=scenarios(header)
    expected=header["repetitions"]*len(values)
    environment={**environment,"clock":header["clock"]}
    return {"purpose":header["purpose"],"created_utc":utc(),"provenance":provenance,"environment":environment,
            "scenarios":values,"trials":trials,"process":{"expected_trials":expected,"emitted_trials":len(trials),
            "repetitions":header["repetitions"],"complete":bool(end) and not aborted,"aborted":aborted or not end,
            "warmups":header["warmups"],
            "return_code":return_code,"events_sha256":sha_bytes(raw),"stderr_sha256":sha_bytes(stderr),
            "failure_reason":"process aborted or missing completion marker" if aborted or not end else None},
            "profile":profile,"historical":[]}


def environment_base():
    return {"scalar":"binary64","absolute_tolerance":1e-8,"relative_tolerance":1e-8,"seed":0,
            "workspace_reuse":False,"process_warmup":True,"order":"fixed catalogue round robin",
            "resources":{"total_threads":1,"outer_workers":1,"threads_per_worker":1,"memory_bytes":None},
            "native_threads":{"available":True,"value":1,"unit":"threads","scope":"configured native adapter; not observed OS thread count"},
            "native_only_time":{"available":False,"reason":"not exposed"},
            "per_trial_cpu":{"available":False,"reason":"not instrumented"},
            "per_trial_peak_memory":{"available":False,"reason":"not instrumented"}}


def test_view(events,exe,return_code,raw,stderr):
    data.require(events[0]["purpose"]=="test","test adapter cannot relabel measurements")
    build=events[0]["build"]
    provenance={"source_commit":build["source_commit"],"tracked_clean":False,"executable_sha256":data.file_digest(exe),
                "backend":BACKEND,"build":build,"repository":"butahlecoq/controlled-systems-lab","native_archive_sha256":PIN,
                "purpose_note":"bounded functional test; build cleanliness not asserted"}
    environment={**environment_base(),"machine":{"available":False,"reason":"functional test, not measured environment"},
                 "concurrent_work":"not assessed in bounded functional test"}
    profile={"available":False,"reason":"no profile run in functional smoke"}
    view=data.seal(event_payload(events,return_code,raw,stderr,provenance,environment,profile))
    return data.validate_view(view)


def run_process(command,out,name,timeout=300):
    """Retain exact partial bytes and stderr on timeout; no shell invocation."""
    stdout=Path(out)/(name+".jsonl")
    stderr=Path(out)/(name+"-stderr.txt")
    aborted=False
    with stdout.open("xb") as target,stderr.open("xb") as errors:
        process=subprocess.Popen([str(x) for x in command],stdout=target,stderr=errors)
        try: code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            aborted=True;process.kill();code=process.wait(timeout=30)
    return code,aborted,stdout.read_bytes(),stderr.read_bytes()


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True,encoding="utf-8").strip()


def clean_commit(expected):
    data.require(git("rev-parse","HEAD")==expected,"source commit changed")
    data.require(not git("status","--porcelain=v1","--untracked-files=no"),"tracked source/index is dirty")


def sanitize(text,build):
    for actual,token in ((str(Path(build).resolve()),"BUILD_ROOT"),(str(ROOT.resolve()),"SOURCE_ROOT")):
        text=text.replace(actual.replace("/","\\").replace("\\","\\\\"),token)
        text=text.replace(actual.replace("\\","/"),token).replace(actual.replace("/","\\"),token)
    return text


def file_api(build,configuration="Release"):
    reply=Path(build)/".cmake/api/v1/reply"
    indices=sorted(reply.glob("index-*.json"))
    data.require(bool(indices),"CMake file API reply missing")
    index=data.parse_json(indices[-1].read_text(encoding="utf-8"))
    def load(name):
        return data.parse_json(data.local_file(reply,name).read_text(encoding="utf-8"))
    codemodel=load(index["reply"]["codemodel-v2"]["jsonFile"])
    configurations=[c for c in codemodel["configurations"] if c["name"]==configuration]
    data.require(len(configurations)==1,"actual configuration codemodel required")
    targets={t["id"]:load(t["jsonFile"]) for t in configurations[0]["targets"]}
    roots=[k for k,t in targets.items() if t["name"]=="csl_lp_report"]
    data.require(len(roots)==1,"report executable codemodel missing")
    chosen={}
    def visit(key):
        if key in chosen: return
        target=targets[key]
        chosen[key]={k:target[k] for k in ("name","type","compileGroups","link","archive","artifacts") if k in target}
        for dependency in target.get("dependencies",[]): visit(dependency["id"])
    visit(roots[0])
    names={t["name"] for t in chosen.values()}
    data.require({"csl_lp_report","csl_report_support","csl_highs_lp","highs","csl_optimization","csl_registry","csl_numeric","csl_contracts"}<=names,"incomplete dependency flags")
    toolchains=load(index["reply"]["toolchains-v1"]["jsonFile"])
    return {"cmake":index["cmake"],"configuration":configuration,"paths":codemodel["paths"],"targets":list(chosen.values()),"toolchains":toolchains}


def machine_snapshot():
    result={"utc":utc(),"os":platform.platform(),"logical_processors":os.cpu_count(),"python":platform.python_version()}
    try:
        if os.name=="nt":
            script="$cpu=Get-CimInstance Win32_Processor; $os=Get-CimInstance Win32_OperatingSystem; [pscustomobject]@{cpu=($cpu.Name -join '; '); load_percent=@($cpu.LoadPercentage); ram_bytes=([uint64]$os.TotalVisibleMemorySize*1024); processes=@(Get-Process | Where-Object {$null -ne $_.CPU} | Select-Object Id,ProcessName,CPU)} | ConvertTo-Json -Depth 4 -Compress"
            raw=subprocess.check_output(["powershell","-NoProfile","-NonInteractive","-Command",script],timeout=30,text=True,encoding="utf-8")
            result.update(data.parse_json(raw))
        elif sys.platform.startswith("linux"):
            cpu=Path("/proc/cpuinfo").read_text()
            result["cpu"]=next((line.split(":",1)[1].strip() for line in cpu.splitlines() if line.startswith("model name")),"unavailable")
            memory=Path("/proc/meminfo").read_text().splitlines()
            result["ram_bytes"]=int(next(line.split()[1] for line in memory if line.startswith("MemTotal:")))*1024
            result["load_average"]=list(os.getloadavg())
            result["processes"]={"available":False,"reason":"per-process CPU collection not implemented on Linux"}
        else: result["details"]={"available":False,"reason":"machine counters unavailable on this platform"}
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        result["details"]={"available":False,"reason":type(error).__name__+": machine counter collection failed"}
    return result


def public_load(before,after):
    first=before.pop("processes",None);last=after.pop("processes",None)
    summary={"available":False,"reason":"matching process CPU snapshots unavailable"}
    if isinstance(first,list) and isinstance(last,list):
        old={(p["Id"],p["ProcessName"]):p["CPU"] for p in first}
        totals={}
        for item in last:
            key=(item["Id"],item["ProcessName"])
            if key in old and item["CPU"]>=old[key]: totals[key[1]]=totals.get(key[1],0)+item["CPU"]-old[key]
        summary={"available":True,"unit":"process CPU seconds over collection interval","values":totals,
                 "scope":"matching observed processes only; no arguments/paths, new/exited processes omitted"}
    return {"before":before,"after":after,"process_cpu_deltas":summary}


def profile_assessment(event):
    data.require(event["purpose"]=="profile","profile purpose required")
    totals=event["phase_totals_ns"]
    data.require(len(totals)==len(data.PHASES) and all(type(x) is int and x>=0 for x in totals),"profile phase totals invalid")
    def delta(name):
        a,b=event["before"][name],event["after"][name]
        if not a["available"] or not b["available"]:
            return {"available":False,"reason":"process CPU counter unavailable"}
        data.require(a["unit"]==b["unit"]=="ns","CPU counter units differ")
        if b["value"]<a["value"]:
            return {"available":False,"reason":"process CPU counter reversed"}
        return {"available":True,"value":b["value"]-a["value"],"unit":"ns","scope":"separate profile process CPU delta"}
    dominant=data.PHASES[max(range(5),key=lambda i:totals[i])] if any(totals[:5]) else None
    return {"dominant_measured_phase":dominant,"phase_totals_ns":dict(zip(data.PHASES,totals)),
            "end_to_end_total_ns":totals[5],"user_cpu_delta":delta("user_cpu"),"kernel_cpu_delta":delta("kernel_cpu"),
            "peak_resident":event["after"]["peak_resident"],
            "source_path":"src/adapters/lp/highs.cpp through BoundWorkspace.run" if dominant=="public_run" else "benchmarks/reporting/lp_report.cpp named phase",
            "inner_limiter":"unresolved at current profile granularity; no sampling/call-stack profile",
            "scope":"largest accumulated sequential component, not throughput or exclusive native time; end_to_end is not added to components"}


def save_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def verify_build_identity(header,expected_commit,functional=False):
    build=header["build"]
    data.require(build["source_commit"]==expected_commit,"stale executable source identity")
    data.require(build["cxx_standard"]==20 and type(build["ndebug"]) is bool,"C++20 build identity required")
    if functional:
        data.require(header["purpose"]=="test" and build["configuration"] in ("Debug","Release","RelWithDebInfo","MinSizeRel"),"configured functional build required")
    else:
        data.require(build["configuration"]=="Release" and build["ndebug"] is True,"Release C++20 executable required")


def verify_artifact(header,graph,build,exe,source=ROOT):
    """Bind the described executable to this actual configured source/build graph."""
    paths=graph["paths"];identity=header["build"]
    data.require(Path(paths["source"]).samefile(source) and Path(paths["build"]).samefile(build),"codemodel source/build owner differs")
    data.require(identity["configuration"]==graph["configuration"],"artifact configuration differs")
    targets={t["name"]:t for t in graph["targets"]}
    target=targets["csl_lp_report"]
    data.require(target["type"]=="EXECUTABLE","report target is not executable")
    artifacts=[Path(paths["build"])/a["path"] for a in target["artifacts"]
               if Path(a["path"]).name in ("csl_lp_report","csl_lp_report.exe")]
    data.require(len(artifacts)==1 and artifacts[0].is_file() and artifacts[0].samefile(exe),"executable is not selected report artifact")
    compilers=[t["compiler"] for t in graph["toolchains"]["toolchains"] if t["language"]=="CXX"]
    data.require(len(compilers)==1,"actual C++ toolchain required")
    compiler=compilers[0]
    data.require((identity["compiler"],identity["compiler_version"])==(compiler["id"],compiler["version"]),"embedded compiler differs from actual toolchain")
    data.require(identity["generator"]==graph["cmake"]["generator"]["name"],"embedded generator differs")
    owner=sha_bytes((paths["source"]+'\n'+paths["build"]+'\n'+compiler["path"]).encode())
    data.require(identity["build_owner_sha256"]==owner,"embedded source/build/compiler owner differs")
    for name in ("csl_lp_report","csl_report_support"):
        groups=[g for g in targets[name]["compileGroups"] if g["language"]=="CXX"]
        data.require(bool(groups),"report compile groups missing")
        for group in groups:
            flags=' '.join(' '.join(f["fragment"] for f in group.get("compileCommandFragments",[])).split())
            for field in (("configured_flags","release_flags") if graph["configuration"]=="Release" else ("configured_flags",)):
                data.require(' '.join(identity[field].split()) in flags,"embedded flags differ from actual compile graph")


def collect(args):
    clean_commit(args.source_commit)
    build=args.build_info.resolve().parent
    metadata=data.parse_json(args.build_info.read_text(encoding="utf-8"))
    data.require(metadata["source_commit"]==args.source_commit,"stale configured source commit")
    api=file_api(build)
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    # Final build under recorded clean pre/post guards. Existing supplied verbose log is retained too.
    original_log=args.build_log.read_text(encoding="utf-8",errors="replace")
    command=[api["cmake"]["paths"]["cmake"],"--build",str(build),"--config","Release","--parallel","4","--verbose"]
    build_start=utc()
    final=subprocess.run(command,capture_output=True,timeout=1200)
    clean_commit(args.source_commit)
    data.require(final.returncode==0,"final provenance build failed")
    build_end=utc()
    api=file_api(build)
    safe_log=sanitize(original_log+"\nFINAL VERIFIED BUILD\n"+final.stdout.decode(errors="replace")+final.stderr.decode(errors="replace"),build)
    (out/"build-provenance.txt").write_text(safe_log+"\nFILE API\n"+sanitize(json.dumps(api,indent=2),build),encoding="utf-8")
    described=subprocess.run([str(args.exe),"--describe"],capture_output=True,timeout=30,check=True)
    header=events_from_bytes(described.stdout)[0]
    verify_build_identity(header,args.source_commit)
    verify_artifact(header,api,build,args.exe)
    save_json(out/"scenarios.json",scenarios(header))
    note=args.concurrent_work_file.read_text(encoding="utf-8").strip()
    data.require(bool(note),"concurrent-work note required")
    exe_sha=data.file_digest(args.exe)
    before=machine_snapshot()
    invocation=[str(args.exe),"--measure","--repetitions",str(args.repetitions),"--warmups",str(args.warmups)]
    code,aborted,raw,stderr=run_process(invocation,out,"raw-events")
    (out/"process-stderr.txt").write_bytes(stderr)
    after=machine_snapshot()
    clean_commit(args.source_commit)
    data.require(data.file_digest(args.exe)==exe_sha,"executable changed during collection")
    events=events_from_bytes(raw,aborted or code!=0)
    if not events and (aborted or code!=0):
        events=[{**header,"purpose":"measurement","repetitions":args.repetitions,"warmups":args.warmups}]
    data.require(events[0]["scenarios"]==header["scenarios"],"describe/run catalogue changed")
    verify_build_identity(events[0],args.source_commit)
    profile_command=[str(args.exe),"--profile","--rounds",str(args.profile_rounds)]
    pc,pabort,praw,pstderr=run_process(profile_command,out,"profile-events")
    pevents=events_from_bytes(praw,pabort or pc!=0)
    if pevents:
        data.require(pevents[0]["event"]=="header" and pevents[0]["purpose"]=="profile" and pevents[0]["scenarios"]==header["scenarios"],"profile source/catalogue differs")
        verify_build_identity(pevents[0],args.source_commit)
    data.require(data.file_digest(args.exe)==exe_sha,"executable changed during profile")
    profile={"schema":"csl.lp-profile/1","purpose":"profile","return_code":pc,"aborted":pabort,"events":pevents,
             "stderr":pstderr.decode("utf-8",errors="replace"),"limiter":"unresolved at current profile granularity; no sampling/call-stack profile",
             "phase_order":list(data.PHASES),"scope":"separate profile; nested totals are not additive to end_to_end"}
    bodies=[e for e in pevents if e["event"]=="profile"]
    if len(bodies)==1 and not pabort:
        body=bodies[0]
        data.require(body["rounds"]==args.profile_rounds and body["trials"]==args.profile_rounds*5,"profile work count mismatch")
        data.require(body["failures"]==0 or pc!=0,"profile failures hidden by successful exit")
        profile["assessment"]=profile_assessment(body)
    else:
        profile["assessment"]={"available":False,"reason":"profile process did not return exactly one complete body"}
    save_json(out/"profile.json",profile)
    clean_commit(args.source_commit)
    provenance={"source_commit":args.source_commit,"tracked_clean":True,"executable_sha256":exe_sha,
                "backend":BACKEND,"native_archive_sha256":PIN,"build":header["build"],"repository":"butahlecoq/controlled-systems-lab",
                "build_log_sha256":data.file_digest(out/"build-provenance.txt"),"build_clean_interval":{"before":build_start,"after":build_end},
                "commands":[sanitize(json.dumps(c),build) for c in (command,invocation,profile_command)],"file_api":data.parse_json(sanitize(json.dumps(api),build))}
    environment={**environment_base(),"machine_load":public_load(before,after),"concurrent_work":note,
                 "collector_python":platform.python_version(),"collection_timeout_seconds":300,"clock_calibration":[e for e in events if e["event"]=="calibration"]}
    profile_valid=pc==0 and not pabort and len(bodies)==1 and bodies[0]["failures"]==0
    payload=event_payload(events,code,raw,stderr,provenance,environment,{"available":True,"valid":profile_valid,"file":"profile.json","sha256":data.file_digest(out/"profile.json"),"scope":"separate profile"},aborted)
    view=data.validate_view(data.seal(payload));save_json(out/"records.json",view)
    return 0 if data.publishable(view) and pc==0 and not pabort else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("exe","build-info","build-log","concurrent-work-file","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--source-commit",required=True)
    parser.add_argument("--repetitions",type=int,default=7)
    parser.add_argument("--warmups",type=int,default=1)
    parser.add_argument("--profile-rounds",type=int,default=1000)
    args=parser.parse_args()
    data.require(5<=args.repetitions<=1000 and args.warmups==1 and 1<=args.profile_rounds<=10000,"bounded collection profile required")
    return collect(args)


if __name__=="__main__": raise SystemExit(main())

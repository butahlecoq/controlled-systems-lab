"""Build the pinned SYN-04 source and collect validated Strategy B T-S01 trials."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, statistics, subprocess, sys, threading, time, xml.etree.ElementTree as ET
from pathlib import Path
import report

try:
    import psutil
except ImportError:
    psutil=None

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,cwd=None,timeout=None):
    return subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True,check=False,timeout=timeout)
def git(root,*args): return subprocess.run(["git","-C",str(root),*args],text=True,capture_output=True,check=True).stdout.strip()
def checked(command,**kwargs):
    result=run(command,**kwargs)
    if result.returncode: raise SystemExit(f"command failed ({result.returncode}): {command!r}\n"+result.stderr.decode(errors="replace")[-5000:])
    return result
def profiled_workload(executable):
    started=time.perf_counter_ns();samples=[]
    process=subprocess.Popen([str(executable)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    tracked=psutil.Process(process.pid) if psutil else None
    while process.poll() is None:
        sample={"monotonic_ns":time.perf_counter_ns()}
        if tracked:
            try:
                sample["cpu_user_seconds"]=tracked.cpu_times().user
                sample["cpu_system_seconds"]=tracked.cpu_times().system
                sample["rss_bytes"]=tracked.memory_info().rss
            except psutil.NoSuchProcess: pass
            sample["host_cpu_percent"]=psutil.cpu_percent(interval=None)
        samples.append(sample);time.sleep(0.002)
    stdout,stderr=process.communicate()
    return {"return_code":process.returncode,"wall_ns":time.perf_counter_ns()-started,"samples":samples,
        "sampled_cpu_user_seconds_max":max((x["cpu_user_seconds"] for x in samples if "cpu_user_seconds" in x),default=None),
        "sampled_cpu_system_seconds_max":max((x["cpu_system_seconds"] for x in samples if "cpu_system_seconds" in x),default=None),
        "sampled_rss_bytes_max":max((x["rss_bytes"] for x in samples if "rss_bytes" in x),default=None),
        "stdout":stdout,"stderr":stderr}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake",type=Path,required=True)
    parser.add_argument("--dependency-cache",type=Path,required=True)
    parser.add_argument("--build-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[4]
    harness_commit=git(root,"rev-parse","HEAD")
    if git(root,"status","--porcelain"): raise SystemExit("measurement harness checkout must be clean and committed")
    if git(root,"rev-parse","HEAD")!=harness_commit: raise SystemExit("harness checkout changed")
    cmake=args.cmake.resolve(strict=True); cache=args.dependency_cache.resolve(strict=True)
    build_root=args.build_root.resolve(); out=args.out.resolve()
    build_root.mkdir(parents=True,exist_ok=False)
    source=build_root/"solver-source"; build=build_root/"release-build"
    checked(["git","-C",root,"worktree","add","--detach",source,report.SOURCE_COMMIT])
    if git(source,"rev-parse","HEAD")!=report.SOURCE_COMMIT or git(source,"status","--porcelain"):
        raise SystemExit("algorithm source worktree is not clean at the pinned commit")
    deps={"CSL_HIGHS":"csl_highs-src","CSL_OBJECTIVES_EIGEN":"csl_objectives_eigen-src","CSL_QHULL":"csl_qhull-src","CSL_JSON":"csl_json-src"}
    cmake_args=[cmake,"-S",root/"reports/algorithm-results/tooling/syn04/runner","-B",build,
        "-G","Visual Studio 17 2022","-A","x64",f"-DCSL_SOURCE_ROOT={source}","-DBUILD_TESTING=OFF"]
    for name,directory in deps.items():
        path=cache/directory
        if not path.is_dir(): raise SystemExit(f"required dependency source is unavailable: {path}")
        cmake_args.append(f"-DFETCHCONTENT_SOURCE_DIR_{name}={path}")
    configured=checked(cmake_args)
    (build_root/"configure.log").write_bytes(configured.stdout+configured.stderr)
    build_command=[cmake,"--build",build,"--config","Release","--target","csl_syn04_strategy_b_report","--parallel","4"]
    built=checked(build_command,timeout=2400)
    (build_root/"build.log").write_bytes(built.stdout+built.stderr)
    if git(source,"rev-parse","HEAD")!=report.SOURCE_COMMIT or git(source,"status","--porcelain"):
        raise SystemExit("pinned source changed during build")
    exe=build/"Release/csl_syn04_strategy_b_report.exe"
    if not exe.is_file(): raise SystemExit("configured Release executable is missing")
    target=build/"csl_syn04_strategy_b_report.vcxproj"
    cache_file=build/"CMakeCache.txt"
    project_root=ET.parse(target).getroot()
    namespace=project_root.tag.partition("}")[0].removeprefix("{")
    q=lambda name:"{"+namespace+"}"+name
    release_group=next((group for group in project_root.findall(q("ItemDefinitionGroup")) if "Release|x64" in group.attrib.get("Condition","")),None)
    cl=release_group.find(q("ClCompile")) if release_group is not None else None
    props={node.tag.rsplit("}",1)[-1]:(node.text or "") for node in cl} if cl is not None else {}
    if props.get("LanguageStandard")!="stdcpp20" or props.get("Optimization")!="MaxSpeed" or "NDEBUG" not in props.get("PreprocessorDefinitions",""):
        raise SystemExit("generated Release target does not prove C++20 optimized NDEBUG configuration")
    compiler_configs=list((build/"CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(compiler_configs)!=1: raise SystemExit("compiler configuration identity is ambiguous")
    compiler_config=compiler_configs[0]
    def git_identity(path):
        if (path/".git").exists(): return {"commit":git(path,"rev-parse","HEAD"),"dirty":bool(git(path,"status","--porcelain"))}
        return {"commit":"source-archive-no-git-metadata","directory_sha256":hash_tree(path)}
    def hash_tree(path):
        h=hashlib.sha256()
        for item in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
            rel=item.relative_to(path).as_posix().encode();h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(item.read_bytes())
        return h.hexdigest()
    dependency_state={key:{"source":str(cache/directory),**git_identity(cache/directory)} for key,directory in deps.items()}
    pre_cpu=psutil.cpu_percent(interval=1.0) if psutil else None
    # Separate, non-reported run: attempt Windows sampled CPU stacks; keep process counters regardless.
    profile_path=build_root/"separate-profile.etl"
    wpr_start=run(["wpr","-start","CPU","-filemode"])
    profile_start={"command":["wpr","-start","CPU","-filemode"],"return_code":wpr_start.returncode,
        "stdout":wpr_start.stdout.decode(errors="replace"),"stderr":wpr_start.stderr.decode(errors="replace")}
    profiler_started=wpr_start.returncode==0
    profile_proc=profiled_workload(exe)
    profile_file=None
    if profiler_started:
        stopped=run(["wpr","-stop",profile_path])
        profile_start["stop"]={"return_code":stopped.returncode,"stdout":stopped.stdout.decode(errors="replace"),"stderr":stopped.stderr.decode(errors="replace")}
        profile_file=str(profile_path) if stopped.returncode==0 and profile_path.exists() else None
    if profile_proc["return_code"]:
        raise SystemExit("separate profile workload failed; refusing to measure")
    measured_proc=run([exe],timeout=300)
    post_cpu=psutil.cpu_percent(interval=1.0) if psutil else None
    if measured_proc.returncode:
        raise SystemExit("accepted measurement executable failed; failed records are not silently summarized")
    if git(source,"rev-parse","HEAD")!=report.SOURCE_COMMIT or git(source,"status","--porcelain"):
        raise SystemExit("pinned source changed during run")
    if git(root,"status","--porcelain") or git(root,"rev-parse","HEAD")!=harness_commit:
        raise SystemExit("harness checkout changed during collection")
    try:
        events=[json.loads(line) for line in measured_proc.stdout.decode("utf-8",errors="strict").splitlines()]
    except (UnicodeError,json.JSONDecodeError) as error: raise SystemExit("measurement executable returned invalid JSONL") from error
    if len(events)!=8 or any(e.get("schema")!=report.EVENT_SCHEMA for e in events): raise SystemExit("wrong event schema or trial count")
    if [(e.get("repetition"),e.get("warmup")) for e in events]!=[(0,True),*[(i,False) for i in range(1,8)]]:
        raise SystemExit("warmup/trial order differs from the admitted profile")
    if any(e.get("status")!="passed" or e.get("result_disposition")!="complete_optimal_family" for e in events):
        raise SystemExit("failed, malformed, or downgraded trial; no success-only summary will be generated")
    if len({e["consumed_result_marker"] for e in events})!=1: raise SystemExit("result marker differs unexpectedly between identical canonical requests")
    build_text=(build/"CMakeCache.txt").read_text(encoding="utf-8",errors="replace")
    compiler_text=compiler_config.read_text(encoding="utf-8",errors="replace")
    version_line=next((line for line in compiler_text.splitlines() if line.startswith('set(CMAKE_CXX_COMPILER_VERSION "')),"unavailable")
    observations=[e["elapsed_ns"] for e in events[1:]]
    measurement={"schema":"csl.syn04-strategy-b-measurement/1","algorithm_source_commit":report.SOURCE_COMMIT,"harness_commit":harness_commit,
      "scope":"Fresh problem construction and resolution, registered Strategy B and HiGHS LP/convex provider creation/selection, StrategyRegistry preparation, exclusive public StrategyPort workspace creation and run, compiled T-S01 verifier acceptance, and exact canonical H-relation plus exact-membership validation. Excludes process startup, JSON serialization, build, file persistence, and rendering.",
      "order":"One excluded warmup followed by seven measured repetitions in one process; one strategy only, so side alternation is inapplicable.",
      "counts":{"warmup":1,"measured":7,"passed":7,"failed":0,"all_outputs_consumed_and_validated":True},
      "timing_ns":{"observations":observations,"median":statistics.median(observations),"min":min(observations),"max":max(observations),"range":max(observations)-min(observations)},
      "result_observation":{"termination":"completed","outcome":"optimal","disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","objective_lower":0,"objective_upper":0,"canonical_relation_checked_each_trial":True},
      "phase_counters":{"available":{"end_to_end":"The one timed interval described above"},"not_invoked":["An LP solve; the registered LP provider is an admitted dependency, but this T-S01 generated program is quadratic and dispatches to the convex provider."],"unavailable":["problem preparation/resolution","strategy registration/preparation","workspace creation","HiGHS QP native subphases","optimal-level extraction","compiled verifier","relation serialization/export"]},
      "performance_conclusion":"inconclusive","limiter":{"available":False,"reason":"WPR CPU sampled-stack profile could not start: Windows denied enabling system-performance profiling policy (0xc5585011). Separate workload ran and process counters were collected, but they cannot attribute a hot source path; no limiter is claimed."},
      "profile_attempt":{"wpr":profile_start,"separate_workload_return_code":profile_proc["return_code"],"separate_wall_ns":profile_proc["wall_ns"],"sampled_process_cpu_user_seconds_max":profile_proc["sampled_cpu_user_seconds_max"],"sampled_process_cpu_system_seconds_max":profile_proc["sampled_cpu_system_seconds_max"],"sampled_process_peak_rss_bytes":profile_proc["sampled_rss_bytes_max"],"process_samples":profile_proc["samples"],"separate_stdout_sha256":hashlib.sha256(profile_proc["stdout"]).hexdigest(),"separate_stderr_sha256":hashlib.sha256(profile_proc["stderr"]).hexdigest(),"etl_path":profile_file},
      "environment":{"os":platform.platform(),"processor":platform.processor() or "unavailable","logical_cpu_count":os.cpu_count(),"cpu_count_physical":psutil.cpu_count(logical=False) if psutil else None,"memory_total_bytes":psutil.virtual_memory().total if psutil else None,"cpu_percent_before":pre_cpu,"cpu_percent_after":post_cpu,"python":platform.python_version(),"clock":"std::chrono::steady_clock, integer nanoseconds","assurance":"numerical","absolute_tolerance":1e-8,"relative_tolerance":1e-8,"requested_resources":{"total_threads":1,"outer_workers":1,"threads_per_worker":1,"memory_bytes":None},"native_provider_thread_configuration":"HiGHS adapter reports threads=1 and parallel=off for the native phase; OS thread count per trial was not observed","seed":"No seed option is exposed/configured by this StrategyPort/HiGHS registration path","cache_policy":"One excluded in-process warmup; each repetition constructs a fresh problem, registries, provider selections, prepared strategy and exclusive workspace. Process/runtime may be warm; no cold-cache claim.","load_note":"All processor CPU percentage samples were taken immediately before and after the accepted process, outside accepted timing; no competing benchmark side and no dedicated quiet machine guarantee."},
      "build":{"cmake":str(cmake),"cmake_version":checked([cmake,"--version"]).stdout.decode(errors="replace").splitlines()[0],"generator":"Visual Studio 17 2022 x64","compiler":"MSVC","compiler_version":version_line,"configuration":"Release","cxx_standard":"C++20","ndebug":True,"release_properties":props,"dependencies":{"highs":{"pinned_sha256":"2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275","adapter_version":"1.0.0+highs.1.11.0"},"objectives_eigen":{"pinned_sha256":"8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72"},"qhull":{"pinned_sha256":"8774e9a12c70b0180b95d6b0b563c5aa4bea8d5960c15e18ae3b6d2521d64f8b"},"json":{"pinned_sha256":"0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406"},"resolved_sources":dependency_state},"cache_sha256":hashlib.sha256((build/"CMakeCache.txt").read_bytes()).hexdigest(),"project_sha256":sha(target),"compiler_config_sha256":sha(compiler_config),"configure_log_sha256":sha(build_root/"configure.log"),"build_log_sha256":sha(build_root/"build.log"),"executable_sha256":sha(exe),"executable_bytes":exe.stat().st_size,"report_driver_sha256":sha(root/"reports/algorithm-results/tooling/syn04/strategy_b_measure.cpp"),"runner_cmake_sha256":sha(root/"reports/algorithm-results/tooling/syn04/runner/CMakeLists.txt"),"configure_command":[str(x) for x in cmake_args],"build_command":[str(x) for x in build_command]},
      "source":{"head":git(source,"rev-parse","HEAD"),"tree":git(source,"rev-parse",f"{report.SOURCE_COMMIT}^{{tree}}"),"clean_before_build":True,"clean_after_run":True,"strategy_source_sha256":hashlib.sha256(run(["git","-C",source,"show",f"{report.SOURCE_COMMIT}:src/synthesis/strategy_b/direct_joint.cpp"]).stdout).hexdigest(),"strategy_header_sha256":hashlib.sha256(run(["git","-C",source,"show",f"{report.SOURCE_COMMIT}:include/csl/synthesis/strategy_b/direct_joint.hpp"]).stdout).hexdigest()},
      "raw_stdout_sha256":hashlib.sha256(measured_proc.stdout).hexdigest(),"raw_stderr_sha256":hashlib.sha256(measured_proc.stderr).hexdigest()}
    out.mkdir(parents=True,exist_ok=False)
    (out/"events.jsonl").write_bytes(measured_proc.stdout)
    (out/"process-stderr.txt").write_bytes(measured_proc.stderr)
    (out/"collection.json").write_text(json.dumps(measurement,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    (out/"profile.json").write_text(json.dumps(measurement["profile_attempt"],sort_keys=True,indent=2)+"\n",encoding="utf-8")
    (out/"build-provenance.json").write_text(json.dumps(measurement["build"],sort_keys=True,indent=2)+"\n",encoding="utf-8")
    (out/"commands.json").write_text(json.dumps({"configure":measurement["build"]["configure_command"],"build":measurement["build"]["build_command"],"measure":[str(exe)],"profile":["wpr","-start","CPU","-filemode",str(exe)]},sort_keys=True,indent=2)+"\n",encoding="utf-8")
    if profile_file: shutil.copyfile(profile_file,out/"separate-profile.etl")
    print(json.dumps({"source_commit":report.SOURCE_COMMIT,"harness_commit":harness_commit,"observations_ns":observations,"median_ns":statistics.median(observations),"range_ns":[min(observations),max(observations)],"failures":0,"output":str(out)},sort_keys=True))
if __name__=="__main__": main()

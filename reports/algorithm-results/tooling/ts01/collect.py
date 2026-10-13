"""Collect verified single-strategy T-S01 timings from a clean Release executable."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
try:
    import psutil
except ImportError:
    psutil = None


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--algorithm-source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    harness_commit = git(root, "rev-parse", "HEAD")
    if git(root, "status", "--porcelain"):
        raise SystemExit("measurement requires a clean committed source tree")
    if len(args.algorithm_source_commit) != 40 or any(c not in "0123456789abcdef" for c in args.algorithm_source_commit):
        raise SystemExit("algorithm source commit must be a full lowercase SHA")
    exe = args.exe.resolve(strict=True)
    build_log = args.build_log.resolve(strict=True)
    build_dir = args.build_dir.resolve(strict=True)
    cache = build_dir / "CMakeCache.txt"
    cache_text = cache.read_text(encoding="utf-8", errors="replace")
    if "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" not in cache_text:
        raise SystemExit("unexpected CMake generator in Release build provenance")
    target_project = build_dir / "csl_syn07_ts01_report.vcxproj"
    target_root = ET.parse(target_project).getroot()
    namespace = target_root.tag.partition("}")[0].removeprefix("{")
    qualified = lambda name: "{" + namespace + "}" + name
    groups = target_root.findall(qualified("ItemDefinitionGroup"))
    release = next((group for group in groups if "Release|x64" in group.attrib.get("Condition", "")), None)
    compile_node = release.find(qualified("ClCompile")) if release is not None else None
    props = {node.tag.rsplit("}",1)[-1]: (node.text or "") for node in compile_node} if compile_node is not None else {}
    if props.get("LanguageStandard") != "stdcpp20" or props.get("Optimization") != "MaxSpeed" or "NDEBUG" not in props.get("PreprocessorDefinitions", ""):
        raise SystemExit("generated target does not prove C++20 Release/NDEBUG settings")
    binary = exe.read_bytes()
    cpu_before = psutil.cpu_percent(interval=1.0) if psutil is not None else None
    result = subprocess.run([str(exe)], capture_output=True, check=False)
    cpu_after = psutil.cpu_percent(interval=1.0) if psutil is not None else None
    after = git(root, "status", "--porcelain")
    if after or git(root, "rev-parse", "HEAD") != harness_commit:
        raise SystemExit("source tree changed during measurement")
    try:
        lines = result.stdout.decode("utf-8", errors="strict").splitlines()
        events = [json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))) for line in lines]
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit("measurement executable emitted invalid JSONL") from error
    if result.returncode != 0 or len(events) != 8:
        raise SystemExit(f"incomplete measurement execution: exit={result.returncode}, events={len(events)}")
    if any(event.get("schema") != "csl.syn07-ts01-measurement-event/1" for event in events):
        raise SystemExit("unexpected T-S01 event schema")
    if [(event.get("repetition"), event.get("warmup")) for event in events] != [(0, True), *[(i, False) for i in range(1, 8)]]:
        raise SystemExit("T-S01 warmup/repetition sequence differs")
    failures = [event for event in events if event.get("status") != "passed" or not event.get("observation_token")]
    if failures or any(type(event.get("elapsed_ns")) is not int or event["elapsed_ns"] < 0 for event in events):
        raise SystemExit("one or more T-S01 attempts failed validation or returned invalid timing")
    measured = [event for event in events if not event["warmup"]]
    values = [event["elapsed_ns"] for event in measured]
    collection = {
        "schema": "csl.syn07-ts01-measurement-collection/1",
        "algorithm_source_commit": args.algorithm_source_commit,
        "harness_commit": harness_commit,
        "scope": "Fresh problem construction and resolution, strategy registration/selection/preparation, exclusive workspace creation, public bound-workspace run, and independent complete-H-relation plus exact-membership validation. Excludes process startup, JSON serialization, build, collection, and rendering.",
        "order": "One excluded warmup, followed by seven measured repetitions in one process. Single strategy only; alternation is inapplicable and no comparator was measured.",
        "counts": {"warmup": 1, "measured": len(measured), "passed": sum(e["status"] == "passed" for e in measured), "failed": sum(e["status"] != "passed" for e in measured), "unique_observation_tokens": len({e["observation_token"] for e in events}), "all_outputs_consumed_and_validated": len({e["observation_token"] for e in events}) == 1},
        "timing_ns": {"observations": values, "median": statistics.median(values), "min": min(values), "max": max(values), "range": max(values)-min(values)},
        "performance_conclusion": "inconclusive",
        "limiter": {"available": False, "reason": "No separate sampling/call-stack profile was collected; this record does not attribute the observed time or establish capacity."},
        "binary": {"path": "build/ts01-report/Release/csl_syn07_ts01_report.exe", "sha256": sha(binary), "bytes": len(binary), "configuration": "Release", "ndebug": True, "cxx_standard": "c++20", "release_properties": props},
        "build_provenance": {"cmake_cache_sha256": sha(cache.read_bytes()), "target_project_sha256": sha(target_project.read_bytes()), "build_log_sha256": sha(build_log.read_bytes()), "generator": "Visual Studio 17 2022 x64", "compiler": "MSVC", "configuration": "Release"},
        "environment": {"os": platform.platform(), "processor": platform.processor() or "unavailable", "logical_cpu_count": os.cpu_count(), "python": sys.version.split()[0], "clock": "std::chrono::steady_clock; elapsed duration in nanoseconds", "total_cpu_percent_1s_before": cpu_before, "total_cpu_percent_1s_after": cpu_after, "load_policy": "Unrelated processes were left running; the two CPU samples are outside the measured process. This is a single-side observation, so no interleaving or noise cancellation is claimed."},
        "raw_stdout_sha256": sha(result.stdout), "raw_stderr_sha256": sha(result.stderr),
    }
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    (out / "events.jsonl").write_bytes(result.stdout)
    (out / "stderr.txt").write_bytes(result.stderr)
    (out / "collection.json").write_text(json.dumps(collection, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "command.txt").write_text(f"{exe}  # one process; stdout is csl.syn07-ts01-measurement-event/1 JSONL\n", encoding="utf-8", newline="\n")
    print(json.dumps(collection, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

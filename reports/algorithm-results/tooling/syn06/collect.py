"""Collect one fixed-source Release SYN-06 report; never run from site staging."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_syn06 as report


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def git(*args: str) -> str:
    return run(["git", *args], capture_output=True, text=True).stdout.strip()


def measured_run(executable: Path, batch: int, warmups: int, trials: int) -> tuple[bytes, bytes]:
    result = run([str(executable), str(batch), str(warmups), str(trials)], capture_output=True)
    return result.stdout, result.stderr


def pilot(executable: Path) -> tuple[dict, bytes]:
    observations = []
    raw = bytearray()
    for batch in (100, 1000, 10000):
        stdout, stderr = measured_run(executable, batch, 1, 1)
        if stderr:
            raise RuntimeError("pilot emitted stderr")
        raw.extend(stdout)
        events = [json.loads(line) for line in stdout.splitlines()]
        trials = [event for event in events[1:] if not event["warmup"]]
        for event in trials:
            observations.append({"fixture": event["fixture"], "batch": batch,
                                 "elapsed_ns": event["elapsed_ns"]})
    per_call = max(event["elapsed_ns"] / event["batch"] for event in observations[-2:])
    selected = min(10_000_000, max(1000, math.ceil(125_000_000 / per_call / 1000) * 1000))
    return {"schema": "csl.syn06-pilot/1", "target_batch_ns": 125_000_000,
            "selected_batch": selected, "observations": observations,
            "raw_sha256": report.digest_bytes(raw)}, bytes(raw)


def profile_run(executable: Path, batch: int, source_commit: str) -> tuple[dict, bytes]:
    command = [str(executable), str(batch), "1", "1"]
    start = time.perf_counter_ns()
    with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        observer = psutil.Process(process.pid)
        samples = []
        while process.poll() is None:
            try:
                cpu = observer.cpu_times()
                memory = observer.memory_info()
                samples.append({"elapsed_ns": time.perf_counter_ns()-start,
                                "process_cpu_seconds": cpu.user+cpu.system,
                                "resident_bytes": memory.rss})
            except psutil.NoSuchProcess:
                break
            time.sleep(0.01)
        stdout, stderr = process.communicate()
        if process.returncode != 0 or stderr:
            raise RuntimeError("separate profile process failed")
    wall = time.perf_counter_ns()-start
    return {"schema": "csl.syn06-limiter-profile/1", "purpose": "non-report limiter observation",
            "source_commit": source_commit, "command": command[1:], "wall_ns": wall,
            "samples": samples, "max_observed_cpu_seconds": max((x["process_cpu_seconds"] for x in samples), default=0),
            "max_observed_resident_bytes": max((x["resident_bytes"] for x in samples), default=0),
            "raw_sha256": report.digest_bytes(stdout),
            "limits": "10 ms sampling; no source-level profiler attribution; excluded from report timings"}, stdout


def processor_name() -> str:
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    return platform.processor()


def compiler_info(build: Path) -> dict:
    candidates = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(candidates) != 1:
        raise RuntimeError("one configured C++ compiler identity required")
    text = candidates[0].read_text(encoding="utf-8")
    values = {}
    for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION", "CMAKE_CXX_COMPILER"):
        match = re.search(rf'set\({key} "([^"]+)"\)', text)
        if match:
            values[key] = match.group(1)
    if not values.get("CMAKE_CXX_COMPILER_VERSION"):
        raise RuntimeError("compiler identity absent from configured build")
    return values


def collect(executable: Path, build: Path, source_commit: str, cmake: Path) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("full fixed source commit required")
    if git("rev-parse", source_commit) != source_commit:
        raise ValueError("fixed source commit not available")
    if git("diff", "--name-only", source_commit, "HEAD", "--", "include/csl/verification", "src/verification"):
        raise ValueError("verifier code differs from fixed source commit")
    if git("status", "--porcelain", "--", "include/csl/verification", "src/verification"):
        raise ValueError("verifier source is dirty")
    if not executable.is_file() or not build.is_dir():
        raise ValueError("configured Release driver/build required")
    build_command = [str(cmake), "--build", str(build), "--config", "Release", "--target", "csl_syn06_verifier_report"]
    build_process = run(build_command, capture_output=True)
    build_log = build_process.stdout + build_process.stderr
    pilot_record, pilot_raw = pilot(executable)
    batch = pilot_record["selected_batch"]
    profile_record, profile_raw = profile_run(executable, max(batch, 100000), source_commit)
    host_cpu_before = psutil.cpu_percent(interval=1.0)
    command = [str(executable), str(batch), "7", "7"]
    raw, stderr = measured_run(executable, batch, 7, 7)
    host_cpu_after = psutil.cpu_percent(interval=1.0)
    trials = report.raw_projection(raw, batch, 7, 7)
    summary = report.summarize(trials, batch)
    if any(row["min_elapsed_ns"] < 50_000_000 for row in summary):
        raise RuntimeError("measurement interval under 50 ms; increase batch")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    source_id = f"syn06-verifier-{stamp}-{source_commit[:8]}"
    bundle = ROOT / "reports" / "algorithm-results" / source_id
    bundle.mkdir(exist_ok=False)
    report_driver = Path(__file__).with_name("verifier_driver.cpp")
    provenance = {
        "schema": "csl.syn06-build-provenance/1", "source_commit": source_commit,
        "collector_commit": git("rev-parse", "HEAD"), "configuration": "Release",
        "driver_sha256": report.digest_bytes(report_driver.read_bytes()),
        "binary_sha256": report.digest_bytes(executable.read_bytes()),
        "cmake_cache_sha256": report.digest_bytes((build / "CMakeCache.txt").read_bytes()),
        "compiler": compiler_info(build),
        "configuration_command": [str(cmake), "-S", ".", "-B", str(build),
                                  "-DCSL_BUILD_SYN06_REPORT=ON", "-DBUILD_TESTING=OFF"],
        "build_command": build_command,
    }
    environment = {
        "os": platform.platform(), "machine": platform.machine(), "processor": processor_name(),
        "logical_cpus": psutil.cpu_count(logical=True), "physical_cpus": psutil.cpu_count(logical=False),
        "memory_bytes": psutil.virtual_memory().total,
        "collection_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu_percent_before": host_cpu_before, "host_cpu_percent_after": host_cpu_after,
        "cache_policy": "one process, seven warmup batches per fixture, then seven measured batches",
        "seed": None, "simultaneous_work": "No intentional co-located benchmark; host may run background services",
    }
    command_text = " ".join(command[1:]) + " (Release driver; cwd repository root)\n"
    files = {
        "build-log.txt": build_log,
        "build-provenance.json": report.json_bytes(provenance),
        "measurement-command.txt": command_text.encode(),
        "pilot.json": report.json_bytes(pilot_record), "pilot-raw.jsonl": pilot_raw,
        "profile.json": report.json_bytes(profile_record), "profile-raw.jsonl": profile_raw,
        "process-stderr.txt": stderr, "raw-events.jsonl": raw,
        "trials.csv": report.csv_bytes(report.TRIAL_FIELDS, trials),
        "summary.csv": report.csv_bytes(report.SUMMARY_FIELDS, summary),
        "latency.svg": report.svg(summary).encode(),
        "verifier_driver.cpp": report_driver.read_bytes(),
    }
    payload = {
        "schema": "csl.syn06-verifier-report/1", "source_commit": source_commit,
        "module": {"id": "csl.trajectory.original", "version": "1"},
        "fixture": report.expected_fixture(), "environment": environment,
        "numerical": {"absolute": 1e-8, "relative": 1e-8},
        "workers": {"requested": 1, "actual": 1, "native_threads": 1},
        "batch": batch, "warmups": 7, "repetitions": 7,
        "timing_scope": "verify_trajectory, report assignment and complete result consumption; resolved problem and request prebuilt",
        "unavailable_timings": ["problem resolution", "setup", "end-to-end", "rendering", "internal phases"],
        "trials": trials, "summary": summary,
        "raw_sha256": report.digest_bytes(raw),
        "build_sha256": report.digest_bytes(files["build-provenance.json"]),
        "build_log_sha256": report.digest_bytes(build_log),
        "command_sha256": report.digest_bytes(files["measurement-command.txt"]),
        "pilot_sha256": report.digest_bytes(files["pilot.json"]),
        "profile_sha256": report.digest_bytes(files["profile.json"]),
        "stderr_sha256": report.digest_bytes(stderr),
    }
    record = {"schema": "csl.syn06-verifier-report/1", "report_id": source_id,
              "payload_sha256": report.digest(payload), "payload": payload}
    files["records.json"] = report.json_bytes(record)
    files["index.html"] = report.page(record, files["latency.svg"].decode()).encode()
    files["README.md"] = (f"# SYN-06 original-data verifier report\n\n"
                          f"Fixed verifier source: `{source_commit}`. Collector source: `{provenance['collector_commit']}`.\n\n"
                          "This saved report times two literal witnesses of a two-stage scalar integrator. "
                          "The original terminal objective is linear `x[2]`, so its value is 1. "
                          "One witness passes numerical checks; the other deliberately violates a control bound "
                          "and transition. Neither establishes optimal-family completeness or validated proof.\n\n"
                          "`records.json` and `raw-events.jsonl` contain the accepted measurements. "
                          "`pilot.json` and `profile.json` are separate, non-report observations. "
                          "Run `python scripts/reports/stage_syn06.py --source reports/algorithm-results/"
                          f"{source_id}` to regenerate the catalogue entry from saved files.\n").encode()
    if set(files) != report.SOURCE_FILES:
        raise RuntimeError("collector source inventory differs from typed report policy")
    for name, content in files.items():
        (bundle / name).write_bytes(content)
    manifest = {"schema": "csl.syn06-source-manifest/1", "report_id": source_id,
                "files": {name: report.digest_bytes(files[name]) for name in sorted(files)}}
    (bundle / "manifest.json").write_bytes(report.json_bytes(manifest))
    (bundle / "bundle.zip").write_bytes(report.registered.publication_zip(source_id,
        {**files, "manifest.json": (bundle / "manifest.json").read_bytes()}))
    report.validate(bundle)
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.executable.resolve(), args.build.resolve(), args.source_commit,
                  args.cmake.resolve()).relative_to(ROOT))


if __name__ == "__main__":
    main()

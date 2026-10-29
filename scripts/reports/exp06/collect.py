#!/usr/bin/env python3
"""Capture the bounded A29/QuickHull paired square pilot into saved records."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORT_ROOT = ROOT / "tools/legacy-ports/A29"
FIXTURE = PORT_ROOT / "fixtures/square.json"
METHOD_A29 = "csl.geometry.a29-a30-python"
METHOD_QUICKHULL = "csl.geometry.quickhull-2d"
REPETITIONS = 5
WARMUPS = 1


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes())


def identity_file(relative: str) -> dict:
    path = ROOT / relative
    return {"path": relative, "sha256": file_hash(path)}


def status_for(algorithm_status: str, quality_status: str) -> tuple[str, str]:
    if algorithm_status == "completed" and quality_status == "verified":
        return "completed", "passed"
    if algorithm_status == "timed_out":
        return "timed_out", "timed_out"
    if algorithm_status == "inconclusive" or quality_status == "inconclusive":
        return "incomplete", "incomplete"
    return "failed", "failed"


def execute_quickhull(executable: Path, fixture_path: Path, timeout: int) -> tuple[dict, str, str]:
    try:
        result = subprocess.run([str(executable), "--run", str(fixture_path)],
                                capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        return {"algorithm_status": "timed_out", "reason": "runner exceeded wall timeout",
                "indices": [], "duration_ns": None}, stdout, stderr
    if result.returncode != 0:
        return {"algorithm_status": "failed", "reason": f"runner exit {result.returncode}",
                "indices": [], "duration_ns": None}, result.stdout, result.stderr
    try:
        payload = json.loads(result.stdout)
        if payload.get("schema") != "csl.exp06-quickhull-result/1":
            raise ValueError("unknown QuickHull result schema")
        return {"algorithm_status": payload["status"], "duration_ns": payload["duration_ns"],
                "indices": payload["indices"], "runtime": payload["runtime"]}, result.stdout, result.stderr
    except (ValueError, KeyError, TypeError) as error:
        return {"algorithm_status": "failed", "reason": f"malformed runner output: {error}",
                "indices": [], "duration_ns": None}, result.stdout, result.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quickhull", type=Path, required=True)
    parser.add_argument("--packer", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"output already exists: {out}")
    harness_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    harness_dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=ROOT, text=True).strip())
    harness_sources = [identity_file(path) for path in (
        "scripts/reports/exp06/collect.py", "scripts/reports/exp06/render_saved.py",
        "scripts/reports/stage_exp06.py", "benchmarks/reporting/exp06/quickhull_run.cpp",
        "benchmarks/reporting/exp06/pack_comparison.cpp", "src/artifacts/comparison_manifest.cpp",
        "include/csl/artifacts/comparison_manifest.hpp")]
    load_average = os.getloadavg() if hasattr(os, "getloadavg") else None
    cpu_model = "unknown"
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.is_file():
        match = re.search(r"^model name\s*:\s*(.+)$", cpu_info.read_text(errors="replace"), re.M)
        if match:
            cpu_model = match.group(1).strip()
    process_count = len(list(Path("/proc").glob("[0-9]*"))) if Path("/proc").is_dir() else None
    quickhull = args.quickhull.resolve(strict=True)
    packer = args.packer.resolve(strict=True)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    source_points = fixture["points"]
    if len(source_points) != 9 or any(len(row) != 2 for row in source_points):
        raise SystemExit("EXP-06 pilot expects the bounded 9-point square fixture")
    points = [[float(value) for value in row] for row in source_points]
    manifest = {"schema": "csl.geometry-hull-input/1", "fixture_id": fixture["fixture_id"],
                "coordinate_order": fixture["coordinate_order"], "points": points}
    manifest_text = canonical(manifest)
    manifest_hash = sha256(manifest_text.encode())

    sys.path.insert(0, str(PORT_ROOT))
    from port import run as run_a29  # noqa: E402
    from oracle import check as check_hull  # noqa: E402

    source_a29 = [identity_file("tools/legacy-ports/A29/port.py"),
                  identity_file("tools/legacy-ports/A29/oracle.py")]
    source_quickhull = [identity_file("src/geometry/hull/quickhull_2d.cpp"),
                        identity_file("benchmarks/reporting/exp06/quickhull_run.cpp")]
    deviations_hash = file_hash(PORT_ROOT / "DEVIATIONS.md")
    python_exe_hash = file_hash(Path(sys.executable).resolve())
    quickhull_exe_hash = file_hash(quickhull)
    request_digest = sha256(canonical({"fixture_sha256": manifest_hash,
        "methods": [METHOD_A29, METHOD_QUICKHULL], "repetitions": REPETITIONS,
        "warmups": WARMUPS, "checker": "A29 exact Fraction source-hull oracle/1"}).encode())

    runtime_a29 = {"language": "Python", "implementation": platform.python_implementation(),
        "version": platform.python_version(), "executable_sha256": python_exe_hash,
        "os": platform.platform(), "architecture": platform.machine(),
        "compiler": "not-applicable", "compiler_version": "not-applicable", "build_type": "interpreted"}
    methods = [
        {"id": METHOD_A29, "version": "A29/A30-port-1", "sources": source_a29,
         "deviations_sha256": deviations_hash, "runtime_base": runtime_a29, "attempts": []},
        {"id": METHOD_QUICKHULL, "version": "1", "sources": source_quickhull,
         "deviations_sha256": None, "runtime_base": None, "attempts": []},
    ]
    raw_dir = out / "raw-attempts"
    raw_dir.mkdir(parents=True)

    schedule = [(0, 0), (1, 0)] + [
        (method_index, repetition + WARMUPS)
        for repetition in range(REPETITIONS)
        for method_index in ([0, 1] if repetition % 2 == 0 else [1, 0])]
    execution_order = []
    for method_index, repetition in schedule:
        method = methods[method_index]
        execution_order.append({"method_id": method["id"], "repetition": repetition})
        warmup = repetition == 0
        if method_index == 0:
            start = time.perf_counter_ns()
            algorithm = run_a29(points)
            duration = time.perf_counter_ns() - start
            output = algorithm.get("output")
            quality = check_hull(points, output)
            indices = quality.get("source_indices") or []
            runtime = runtime_a29
            raw_stdout = canonical({"algorithm": algorithm, "quality": quality}) + "\n"
            raw_stderr = ""
        else:
            fixture_dir = out / "fixture"
            fixture_dir.mkdir(exist_ok=True)
            fixture_path = fixture_dir / "square.json"
            fixture_path.write_text(manifest_text + "\n", encoding="utf-8")
            algorithm, raw_stdout, raw_stderr = execute_quickhull(quickhull, fixture_path,
                                                                  args.timeout_seconds)
            indices = algorithm.get("indices", [])
            output = [points[index] for index in indices if isinstance(index, int) and 0 <= index < len(points)]
            quality = check_hull(points, output)
            duration = algorithm.get("duration_ns")
            raw_runtime = algorithm.get("runtime", {})
            runtime = {"language": "C++", "implementation": raw_runtime.get("implementation", METHOD_QUICKHULL),
                "version": raw_runtime.get("version", "1"), "executable_sha256": quickhull_exe_hash,
                "os": raw_runtime.get("os", platform.platform()),
                "architecture": raw_runtime.get("architecture", platform.machine()),
                "compiler": "GNU-compatible", "compiler_version": raw_runtime.get("compiler", "unknown"),
                "build_type": raw_runtime.get("build_type", "Release")}
            if method["runtime_base"] is None:
                method["runtime_base"] = runtime

        attempt_status, event_status = status_for(algorithm.get("algorithm_status", "failed"),
                                                   quality.get("status", "inconclusive"))
        if duration is None:
            duration = 0
        result_payload = {"algorithm": algorithm, "checker": quality, "duration_ns": duration,
                          "indices": indices, "method_id": method["id"], "warmup": warmup}
        measurement = {"schema": "csl.external-method-event/1", "status": event_status,
            "method_id": method["id"], "instrumentation": "disabled", "repetition": repetition,
            "warmup": warmup, "duration_ns": duration}
        method["attempts"].append({"run_id": f"exp06-{method_index}-r{repetition:02d}",
            "status": attempt_status, "runtime": runtime, "result": result_payload,
            "measurement": measurement})
        stem = f"method-{method_index}-repetition-{repetition:02d}"
        (raw_dir / (stem + ".stdout")).write_text(raw_stdout, encoding="utf-8")
        (raw_dir / (stem + ".stderr")).write_text(raw_stderr, encoding="utf-8")

    for method in methods:
        config_payload = {"id": method["id"], "version": method["version"],
            "sources": method["sources"], "runtime": method["runtime_base"],
            "deviations_sha256": method["deviations_sha256"]}
        method["configuration_id"] = "csl.config.v1.sha256:" + sha256(canonical(config_payload).encode())
        del method["runtime_base"]

    controls = {
        "schema": "csl.exp06-checker-controls/1",
        "omitted_corner": check_hull(points, [points[index] for index in (1, 2, 3)]),
        "all_redundant_points_retained": check_hull(points, points),
    }
    if (controls["omitted_corner"]["status"] != "incorrect" or
            controls["all_redundant_points_retained"]["status"] != "verified"):
        raise SystemExit("exact checker negative controls did not produce expected statuses")

    request = {"schema": "csl.exp06-pack-request/1", "manifest": manifest_text,
        "request_digest": request_digest, "methods": methods}
    request_path = out / "pack-request.json"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    packed = subprocess.run([str(packer), str(request_path)], capture_output=True, text=True,
                            timeout=300, check=False)
    (out / "packer.stdout").write_text(packed.stdout, encoding="utf-8")
    (out / "packer.stderr").write_text(packed.stderr, encoding="utf-8")
    if packed.returncode:
        (out / "collection-status.json").write_text(json.dumps({"publishable": False,
            "packer_exit_code": packed.returncode}, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"comparison packer failed; raw evidence retained at {out}")

    (out / "comparison-record.json").write_text(packed.stdout, encoding="utf-8")
    metadata = {"schema": "csl.exp06-capture/1", "purpose": "bounded paired geometry pilot",
        "source_commit": harness_commit, "harness_dirty": harness_dirty,
        "harness_sources": harness_sources,
        "host": {"os": platform.platform(), "architecture": platform.machine(),
            "cpu_model": cpu_model, "logical_cpus": os.cpu_count(),
            "load_average_1m_5m_15m": list(load_average) if load_average is not None else None,
            "observed_process_count": process_count},
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixture_sha256": manifest_hash, "request_digest": request_digest,
        "warmups_per_method": WARMUPS, "measured_repetitions_per_method": REPETITIONS,
        "measurement_order": "alternating methods by repetition", "execution_order": execution_order,
        "timeout_seconds": args.timeout_seconds,
        "memory_limit": {"status": "not_enforced", "reason": "bounded nine-point fixture; process memory was not measured"},
        "timing_comparison": "inconclusive: Python/NumPy and C++ timings use different runtimes and intervals",
        "timing_intervals": {METHOD_A29: "perf_counter_ns around the Python port call; excludes exact checker",
            METHOD_QUICKHULL: "steady_clock around QuickHull call; excludes process startup, JSON intake and exact checker"},
        "limiter_profile": {"status": "not_collected", "reason": "different method runtimes and timing intervals do not have a shared source-level limiter profile"},
        "checker_controls": controls,
        "quickhull_executable_sha256": quickhull_exe_hash, "python_executable_sha256": python_exe_hash,
        "packer_exit_code": packed.returncode, "stderr": packed.stderr}
    (out / "capture.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

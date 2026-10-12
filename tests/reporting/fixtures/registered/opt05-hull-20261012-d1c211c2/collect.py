#!/usr/bin/env python3
"""Capture a bounded hull-reducer run; preserve all emitted trials and failures."""
from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.wintypes
import datetime as dt
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPORT_ID = "opt05-hull-20261012-d1c211c2"
SCHEMA = "csl.hull-benchmark-records/1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def powershell_load_snapshot() -> dict:
    script = (
        "$c=Get-CimInstance Win32_Processor;"
        "$o=Get-CimInstance Win32_OperatingSystem;"
        "[pscustomobject]@{cpu_load_percent=($c | Measure-Object LoadPercentage -Average).Average;"
        "visible_ram_kib=[int64]$o.TotalVisibleMemorySize;free_ram_kib=[int64]$o.FreePhysicalMemory;"
        "logical_processors=($c | Measure-Object NumberOfLogicalProcessors -Sum).Sum;"
        "cpu_name=($c | Select-Object -First 1 -ExpandProperty Name)} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                               capture_output=True, text=True, timeout=15, check=True)
        return json.loads(result.stdout)
    except Exception as exc:  # keep an explicit unavailable reason in raw provenance
        return {"available": False, "reason": f"system_snapshot_failed:{type(exc).__name__}"}


def system_cpu_snapshot() -> dict:
    if os.name != "nt":
        return {"available": False, "reason": "windows_GetSystemTimes_unavailable"}
    def counters():
        idle, kernel, user = ctypes.wintypes.FILETIME(), ctypes.wintypes.FILETIME(), ctypes.wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError("GetSystemTimes failed")
        def ticks(ft):
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
        return ticks(idle), ticks(kernel), ticks(user)
    try:
        first = counters()
        time.sleep(1.0)
        second = counters()
        idle = second[0] - first[0]
        kernel = second[1] - first[1]
        user = second[2] - first[2]
        total = kernel + user
        return {"available": total > 0, "sample_interval_ms": 1000,
                "busy_percent": round(100.0 * max(0, total - idle) / total, 1) if total else None}
    except Exception as exc:
        return {"available": False, "reason": f"system_cpu_sample_failed:{type(exc).__name__}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--code-commit", required=True)
    ap.add_argument("--build-log", type=Path, required=True)
    ap.add_argument("--concurrent-work", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing result directory: {args.out}")
    if not args.exe.is_file():
        raise SystemExit(f"executable missing: {args.exe}")
    args.out.mkdir(parents=True)
    build_root = args.exe.resolve().parents[1]
    cache_path = build_root / "CMakeCache.txt"
    cache = {}
    if cache_path.is_file():
        for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and not line.startswith("//") and not line.startswith("#") and ":" in line and "=" in line:
                key, value = line.split(":", 1)[0], line.split("=", 1)[1]
                cache[key] = value
    host_before = {"system": powershell_load_snapshot(), "cpu_sample": system_cpu_snapshot()}
    start = time.time_ns()
    proc = subprocess.run([str(args.exe), "measure"], capture_output=True, text=True)
    elapsed = time.time_ns() - start
    host_after = {"system": powershell_load_snapshot(), "cpu_sample": system_cpu_snapshot()}
    (args.out / "process-stdout.jsonl").write_text(proc.stdout, encoding="utf-8", newline="\n")
    (args.out / "process-stderr.txt").write_text(proc.stderr, encoding="utf-8", newline="\n")
    (args.out / "concurrent-work.txt").write_text(args.concurrent_work.strip() + "\n", encoding="utf-8")
    raw_build_log = args.build_log.read_text(encoding="utf-8", errors="replace")
    build_log = raw_build_log
    build_log = build_log.replace(str(Path.cwd()), "$SOURCE_ROOT")
    build_log = build_log.replace(str(args.exe.resolve().parents[1]), "$BUILD_ROOT")
    (args.out / "build-log-sanitized.txt").write_text(build_log, encoding="utf-8")
    source_root = Path.cwd()
    source_files = [source_root / "src/geometry/hull_reducer.cpp",
                    source_root / "include/csl/geometry/hull_reducer.hpp",
                    source_root / "reports/algorithm-results/opt05-hull-20261012-d1c211c2/harness/hull_measure.cpp"]
    build_info = {
        "source_code_commit": args.code_commit,
        "source_identity_scope": "tracked reducer/backend code at the specified commit; the separate harness source hash is recorded below",
        "build_generator": cache.get("CMAKE_GENERATOR", "unknown"),
        "build_platform": cache.get("CMAKE_GENERATOR_PLATFORM", "unknown"),
        "configuration": "Release",
        "cxx_compiler": cache.get("CMAKE_CXX_COMPILER", "unknown").replace(str(Path.home()), "$USER_ROOT"),
        "cxx_compiler_id": cache.get("CMAKE_CXX_COMPILER_ID", "unknown"),
        "cxx_compiler_version": cache.get("CMAKE_CXX_COMPILER_VERSION", "unknown"),
        "release_compile_flags": cache.get("CMAKE_CXX_FLAGS_RELEASE", "unknown"),
        "expected_flags_present": {flag: flag in raw_build_log for flag in ("/O2", "/DNDEBUG", "/std:c++20")},
        "configured_dependencies": {"HiGHS": "1.11.0"},
        "build_command": "cmake --build build-opt05-harness --config Release --target csl_hull_measure --parallel 4 --verbose",
        "release_build_log_sha256": hashlib.sha256(raw_build_log.encode("utf-8")).hexdigest(),
        "executable_sha256": sha256(args.exe),
        "source_sha256": {path.relative_to(source_root).as_posix(): sha256(path) for path in source_files},
        "cmake_cache_sha256": sha256(cache_path) if cache_path.is_file() else None,
    }
    (args.out / "build-provenance.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")
    trials = []
    invalid_lines = []
    for number, line in enumerate(proc.stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            trials.append(json.loads(line))
        except json.JSONDecodeError:
            invalid_lines.append({"line": number, "raw": line})
    measured = [trial for trial in trials if not trial.get("warmup")]
    groups = {}
    for trial in measured:
        groups.setdefault(trial.get("case_id", "unknown"), []).append(trial)
    summaries = []
    for case_id, group in sorted(groups.items()):
        successful = [t for t in group if t.get("verified") and t.get("status") == "complete"]
        values = [t["elapsed_ns"] for t in successful if isinstance(t.get("elapsed_ns"), int)]
        summaries.append({
            "case_id": case_id,
            "points": group[0].get("points"),
            "attempts": len(group),
            "successes": len(successful),
            "failures": len(group) - len(successful),
            "median_ns": statistics.median(values) if values else None,
            "min_ns": min(values) if values else None,
            "max_ns": max(values) if values else None,
            "median_lp_calls": statistics.median([t["lp_calls"] for t in successful]) if successful else None,
            "outcome_totals": {
                name: sum(t.get("outcomes", {}).get(name, 0) for t in group)
                for name in ("feasible", "infeasible", "unsupported", "stopped", "numerical_failure", "malformed_result")
            },
        })
    records = {
        "schema": SCHEMA,
        "report_id": REPORT_ID,
        "created_utc": utc_now(),
        "code_commit": args.code_commit,
        "source_worktree_head": args.code_commit,
        "algorithm": {"name": "LP-backed finite-point hull reduction", "implementation": "CSL::geometry::reduce_hull", "source": "src/geometry/hull_reducer.cpp"},
        "backend": {"name": "HiGHS LP adapter", "version": "1.11.0", "source": "src/adapters/lp/highs.cpp", "configured_threads": 1, "presolve": "off", "parallel": "off", "simplex_iteration_limit": None},
        "build": build_info,
        "environment": {
            "os": platform.platform(), "python": sys.version, "machine": platform.machine(),
            "host_before": host_before, "host_after": host_after,
            "concurrent_work_note": args.concurrent_work.strip(),
            "requested_native_threads": 1,
            "trial_policy": "one warmup per case; seven measured repetitions per case; round-robin interleaved case order; fresh LP workspace per invocation",
            "timing_scope": "steady_clock duration of reduce_hull only; cloud creation, adapter registration and workspace factory excluded; first lazy HiGHS initialization inside the reducer call is included",
            "process_wall_elapsed_ns": elapsed,
        },
        "fixture": {
            "definition": "all points (x/(s-1), y/(s-1)) on row-major s-by-s lattice over [0,1]^2",
            "cases": [{"case_id": f"grid-{side*side}", "side": side, "points": side*side,
                       "expected_retained": 4, "expected_removed": side*side-4,
                       "expected_lp_calls": side*side} for side in (5, 9, 13)],
            "oracle": "exact known unit-square extreme-corner IDs plus re-evaluation of every returned barycentric removal certificate; all output outcomes must be feasible/infeasible and reducer complete",
            "assurance": "binary64 numerical checks; not exact arithmetic or a validated global certificate",
        },
        "process": {"exit_code": proc.returncode, "invalid_stdout_lines": invalid_lines,
                    "trial_rows": len(trials), "measured_rows": len(measured), "warmup_rows": len(trials)-len(measured),
                    "failures": sum(1 for t in measured if not t.get("verified") or t.get("status") != "complete")},
        "trials": trials,
        "summary": summaries,
    }
    (args.out / "records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    with (args.out / "trials.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["case_id", "round", "points", "warmup", "elapsed_ns", "status", "verified", "lp_calls", "attempts", "removed", "retained", "feasible", "infeasible", "unsupported", "stopped", "numerical_failure", "malformed_result"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for trial in trials:
            row = {key: trial.get(key) for key in fields}
            for outcome, count in trial.get("outcomes", {}).items():
                row[outcome] = count
            writer.writerow(row)
    with (args.out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["case_id", "points", "attempts", "successes", "failures", "median_ns", "min_ns", "max_ns", "median_lp_calls"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: item.get(key) for key in fields} for item in summaries])
    if proc.returncode != 0 or invalid_lines or records["process"]["failures"] or len(trials) != 24 or len(summaries) != 3:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

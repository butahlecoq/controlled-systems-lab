#!/usr/bin/env python3
"""Collect an alternating, checked cold/warm OPT-12 measurement bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot() -> dict:
    if os.name != "nt":
        return {"available": False, "reason": "host snapshot currently implemented for Windows"}
    script = "$cpu=Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average; $os=Get-CimInstance Win32_OperatingSystem; $proc=Get-Process | Sort-Object CPU -Descending | Select-Object -First 12 ProcessName,Id,CPU,WorkingSet64; [pscustomobject]@{cpu_load_percent=$cpu.Average; free_physical_bytes=[int64]$os.FreePhysicalMemory*1024; processes=$proc} | ConvertTo-Json -Depth 4 -Compress"
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], check=True,
                                capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        return {"available": False, "reason": f"snapshot failed: {type(error).__name__}"}


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--build-log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error("at least five alternating paired repetitions are required")
    exe = args.exe.resolve(strict=True)
    build_log = args.build_log.resolve(strict=True)
    root = Path(__file__).resolve().parents[2]
    head = git_value(root, "rev-parse", "HEAD")
    dirty = git_value(root, "status", "--porcelain")
    if head != args.source_commit or dirty:
        parser.error("measurement requires the declared exact, clean source commit")
    if "release" not in str(exe.parent).lower():
        parser.error("measurement executable must come from a Release output directory")
    if args.out.exists():
        parser.error("output destination must be new")
    args.out.mkdir(parents=True)
    before = snapshot()
    run = subprocess.run([str(exe), str(args.repetitions)], capture_output=True, timeout=120)
    after = snapshot()
    raw_stdout = run.stdout
    raw_stderr = run.stderr
    (args.out / "raw-events.jsonl").write_bytes(raw_stdout)
    (args.out / "raw-stderr.txt").write_bytes(raw_stderr)
    build_root = exe.parents[1].resolve()
    build_text = build_log.read_text(encoding="utf-8", errors="replace")
    build_text = build_text.replace(str(build_root), "$BUILD_ROOT").replace(str(root), "$SOURCE_ROOT")
    build_bytes = build_text.encode("utf-8")
    (args.out / "release-build-log.txt").write_bytes(build_bytes)
    records = []
    parse_error = None
    try:
        records = [json.loads(line) for line in raw_stdout.decode("utf-8").splitlines() if line]
        for row in records:
            if row.get("schema") != "csl.opt12-cost-trial/1":
                raise ValueError("unknown record schema")
        expected_count = args.repetitions * 4
        if len(records) != expected_count:
            raise ValueError(f"expected {expected_count} trial rows, got {len(records)}")
        if any(row.get("status") != "verified" for row in records):
            raise ValueError("a trial did not pass its independent numerical checks")
        for pair in range(args.repetitions):
            for scenario in ("tiny-overhead", "small-reuse"):
                members = [r for r in records if r["pair"] == pair and r["scenario"] == scenario]
                if len(members) != 2 or {r["mode"] for r in members} != {"cold", "warm"}:
                    raise ValueError("trial pairing or alternation is incomplete")
                if [r["mode"] for r in sorted(members, key=lambda r: r["order"])] != (["cold", "warm"] if pair % 2 == 0 else ["warm", "cold"]):
                    raise ValueError("side order did not alternate")
        if run.returncode:
            raise ValueError(f"benchmark process exited with status {run.returncode}")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        parse_error = f"{type(error).__name__}: {error}"
    inputs = {
        "tiny-overhead": {"rows": 1, "columns": 1, "objective": [-1.0], "coefficient": [1.0], "source_rhs": 1.0, "changed_rhs": 0.5, "expected_objective": -0.5},
        "small-reuse": {"rows": 1, "columns": 40, "objective": [-1.0] * 40, "coefficient": [1.0] * 40, "source_rhs": 20.0, "changed_rhs": 19.0, "expected_objective": -19.0},
    }
    for fixture in inputs.values():
        fixture["sha256"] = digest(json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode())
    metadata = {
        "schema": "csl.opt12-cost-report/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": head,
        "adapter": "csl.lp.highs",
        "adapter_version": "1.1.0+highs.1.11.0",
        "native_solver": "HiGHS 1.11.0",
        "build_configuration": "Release",
        "build_log_sha256": digest(build_bytes),
        "executable_sha256": digest(exe.read_bytes()),
        "executable_path": "Release/csl_opt12_warm_start_measure.exe",
        "host": {"system": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count()},
        "policy": {"native_threads": 1, "presolve": "off", "parallel": "off", "seed": 0,
                   "simplex_iteration_limit": None, "repetitions_per_side_per_case": args.repetitions,
                   "warmup": "one unreported source solve in a fresh workspace per warm trial",
                   "order": "alternating cold/warm within each pair", "timing": "steady-clock wall around LPWorkspace.solve; native setup components are separately timed"},
        "input_fixtures": inputs,
        "process": {"return_code": run.returncode, "stderr_sha256": digest(raw_stderr),
                    "stdout_sha256": digest(raw_stdout), "retained_trial_count": len(records), "parse_error": parse_error},
        "system_before": before,
        "system_after": after,
    }
    (args.out / "environment.json").write_text(json.dumps({"before": before, "after": after}, indent=2) + "\n", encoding="utf-8")
    (args.out / "records.json").write_text(json.dumps({"metadata": metadata, "trials": records}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["scenario", "pair", "order", "mode", "status", "cache_state", "basis_accepted", "expected_objective", "objective", "wall_ns", "model_load_seconds", "basis_transfer_seconds", "solve_seconds", "simplex_iterations"]
    with (args.out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (args.out / "measurement-command.txt").write_text(
        f"{sys.executable} scripts/reports/opt12_collect.py --exe build/dev-windows/Release/csl_opt12_warm_start_measure.exe --source-commit {head} --build-log build/dev-windows/opt12-release-build.log --repetitions {args.repetitions} --out reports/algorithm-results/opt12-<source-prefix>/collection\n",
        encoding="utf-8")
    print(json.dumps({"output": str(args.out), "record_count": len(records), "return_code": run.returncode, "parse_error": parse_error}))
    return 1 if parse_error else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Measure complete CartPole report collection after one discarded warmup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

SCHEMA = "csl.env717-cartpole-report-generation/1"
RUNS = 5


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_once(executable: Path, checker: Path, profile: Path,
             evidence_path: Path, destination: Path):
    command = [sys.executable, str(checker), str(executable), "--repetitions", "9",
        "--output", str(destination), "--report-generation-evidence", str(evidence_path),
        "--limiter-profile", str(profile)]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError(completed.stderr[-4000:] or f"collector returned {completed.returncode}")
    result = json.loads((destination / "result.json").read_text(encoding="utf-8"))
    if (result["enumeration"]["plan_count"] != 16384 or
            result["enumeration"]["all_plans_completed"] is not True or
            result["performance"]["measured_repetitions"] != 9):
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError("collector output does not contain the complete expected run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.executable, args.checker, args.profile):
        if not path.is_file():
            parser.error(f"input file does not exist: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    with tempfile.TemporaryDirectory(prefix="cartpole-report-capture-", dir=args.output.parent) as temp:
        temporary_root = Path(temp)
        placeholder = {"schema": SCHEMA, "metric": "full_report_collection_elapsed",
            "measured_runs": RUNS, "warmup_runs": 1, "failed_runs": 0,
            "warmup_elapsed_ns": [1], "raw_elapsed_ns": [2, 3, 4, 5, 6],
            "minimum_elapsed_ns": 2, "maximum_elapsed_ns": 6, "median_elapsed_ns": 4,
            "scope": "temporary placeholder used only to validate the report writer",
            "process_statuses": ([{"kind": "warmup", "index": 0,
                "status": "completed", "elapsed_ns": 1, "error": None}] +
                [{"kind": "measured", "index": index, "status": "completed",
                  "elapsed_ns": index + 2, "error": None} for index in range(RUNS)]),
            "checker_sha256": digest(args.checker.resolve()),
            "runner_sha256": digest(Path(__file__).resolve()),
            "driver_sha256": json.loads(subprocess.run(
                [str(args.executable.resolve()), "--measure", "1"],
                check=True, capture_output=True, text=True).stdout)["driver_sha256"],
            "python": sys.version.split()[0], "host_logical_cpu_count": os.cpu_count()}
        evidence_path = temporary_root / "placeholder-report-generation.json"
        evidence_path.write_text(json.dumps(placeholder), encoding="utf-8")
        for kind, count in (("warmup", 1), ("measured", RUNS)):
            for index in range(count):
                started = time.perf_counter_ns()
                status, error = "completed", None
                destination = temporary_root / f"report-{kind}-{index}"
                try:
                    run_once(args.executable.resolve(), args.checker.resolve(), args.profile.resolve(),
                             evidence_path, destination)
                except Exception as exception:  # retain every failed attempt in the record
                    status, error = "failed", f"{type(exception).__name__}: {exception}"
                elapsed = time.perf_counter_ns() - started
                shutil.rmtree(destination, ignore_errors=True)
                attempts.append({"kind": kind, "index": index, "status": status,
                    "elapsed_ns": elapsed, "error": error})
    measured = [item["elapsed_ns"] for item in attempts if item["kind"] == "measured" and item["status"] == "completed"]
    ordered = sorted(measured)
    failed_runs = sum(item["kind"] == "measured" and item["status"] != "completed" for item in attempts)
    value = {"schema": SCHEMA, "metric": "full_report_collection_elapsed",
        "unit": "ns", "clock": "time.perf_counter_ns", "measured_runs": len(measured),
        "warmup_runs": 1, "failed_runs": failed_runs,
        "warmup_elapsed_ns": [item["elapsed_ns"] for item in attempts if item["kind"] == "warmup"],
        "raw_elapsed_ns": measured,
        "minimum_elapsed_ns": min(ordered) if ordered else None,
        "maximum_elapsed_ns": max(ordered) if ordered else None,
        "median_elapsed_ns": ordered[len(ordered) // 2] if ordered else None,
        "scope": "native executable collection (5 warmups plus 9 measured enumerations), independent exhaustive Python replay, figure generation, report serialization and writes; excludes CMake configuration/build, report staging and ZIP generation",
        "process_statuses": [{"kind": item["kind"], "index": item["index"],
            "status": item["status"], "elapsed_ns": item["elapsed_ns"], "error": item["error"]}
            for item in attempts],
        "checker_sha256": digest(args.checker), "runner_sha256": digest(Path(__file__).resolve()),
        "driver_sha256": json.loads(subprocess.run([str(args.executable), "--measure", "1"],
            check=True, capture_output=True, text=True).stdout)["driver_sha256"],
        "python": sys.version.split()[0], "host_logical_cpu_count": os.cpu_count()}
    args.output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "measured_runs": value["measured_runs"],
        "failed_runs": failed_runs, "median_elapsed_ns": value["median_elapsed_ns"]}))
    if failed_runs or len(measured) != RUNS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

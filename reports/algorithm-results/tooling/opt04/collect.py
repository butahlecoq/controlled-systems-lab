#!/usr/bin/env python3
"""Run the OPT-04 functional smoke or, after review, collect matched trials."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "csl.opt04-phase-one-report/1"
FIXTURES = {
    "triangle": {"rows": 3, "columns": 3, "matrix": [[0,1,0],[0,0,1],[1,1,1]], "rhs": [.25,.25,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.25,.25], "expected_auxiliary": 0.0},
    "signed_triangle": {"rows": 3, "columns": 3, "matrix": [[-1,1,-1],[-1,-1,1],[1,1,1]], "rhs": [-.5,-.5,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.25,.25], "expected_auxiliary": 0.0},
    "edge": {"rows": 3, "columns": 3, "matrix": [[0,1,0],[0,0,1],[1,1,1]], "rhs": [.5,0,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.5,0.0], "expected_auxiliary": 0.0},
    "duplicate_tie": {"rows": 2, "columns": 2, "matrix": [[1,1],[1,1]], "rhs": [1,1], "expected_status": "optimal", "expected_phase_one_primal": [1.0,0.0], "expected_auxiliary": 0.0},
    "contradictory_rows": {"rows": 2, "columns": 1, "matrix": [[1],[1]], "rhs": [0,1], "expected_status": "infeasible", "expected_phase_one_primal": [0.0], "expected_auxiliary": 1.0},
}
SIDES = ("phase-one-bland", "highs-reference")
PHASES = ("setup", "public_run", "verification", "end_to_end")


def parse_output(raw: str) -> tuple[list[dict], list[str]]:
    rows = []
    errors = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"stdout line {number} is not JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"stdout line {number} is not a trial object")
            continue
        rows.append(value)
    return rows, errors


def normalize_and_pair(rows: list[dict], repetitions: int = 7, warmups_per_fixture: int = 1) -> tuple[list[dict], list[dict], list[str], int]:
    warmups = [dict(r) for r in rows if r.get("warmup") is True]
    trials = [dict(r) for r in rows if r.get("warmup") is False]
    validation_errors = []
    for row in [*warmups, *trials]:
        if row.get("fixture") not in FIXTURES or row.get("side") not in SIDES:
            validation_errors.append("unknown fixture or side")
            continue
        fixture = FIXTURES[row["fixture"]]
        row["expected_status"] = fixture["expected_status"]
        row["tolerances"] = {"absolute": 1e-8, "relative": 0.0}
        if row.get("observed_status") != fixture["expected_status"] or row.get("status") != "passed" or row.get("oracle_match") is not True:
            validation_errors.append(f"failed status/oracle: {row['fixture']} / {row['side']}")
        if row.get("work_observed") is not True:
            validation_errors.append(f"work not observed: {row.get('fixture')} / {row.get('side')}")
        if not isinstance(row.get("oracle_checks"), list) or not row["oracle_checks"] or not all(c.get("passed") is True for c in row["oracle_checks"]):
            validation_errors.append(f"oracle check failure: {row.get('fixture')} / {row.get('side')}")
        if set(row.get("durations_ns", {})) != set(PHASES) or any(not isinstance(row["durations_ns"][p], int) or row["durations_ns"][p] < 0 for p in PHASES):
            validation_errors.append(f"invalid timing fields: {row.get('fixture')} / {row.get('side')}")
    for row in [*warmups, *trials]:
        row.pop("warmup", None)
    groups: dict[str, list[dict]] = {}
    for row in [*warmups, *trials]:
        groups.setdefault(row["pair_id"], []).append(row)
    for pair_id, pair in groups.items():
        by_side = {row["side"]: row for row in pair}
        if set(by_side) != set(SIDES) or len(pair) != 2:
            validation_errors.append(f"pair {pair_id} does not contain exactly one row per side")
            for row in pair:
                row["reference_status"] = None
                row["paired_outcomes"] = None
            continue
        phase, ref = by_side["phase-one-bland"], by_side["highs-reference"]
        if phase["fixture"] != ref["fixture"] or phase["repetition"] != ref["repetition"]:
            validation_errors.append("paired rows disagree on fixture/repetition")
        phase_out = {"status": phase["observed_status"], "termination": phase["result"]["termination"], "primal": phase["result"]["primal"], "auxiliary": phase["result"]["auxiliary"]}
        ref_out = {"status": ref["observed_status"], "termination": ref["result"]["termination"], "primal": ref["result"]["primal"]}
        for row in pair:
            row["reference_status"] = phase["observed_status"] if row["side"] == "highs-reference" else ref["observed_status"]
            row["paired_outcomes"] = {"phase_one": phase_out, "highs_reference": ref_out}
    expected_warmups = len(FIXTURES)*len(SIDES)*warmups_per_fixture
    expected_trials = len(FIXTURES)*len(SIDES)*repetitions
    missing = max(0, expected_warmups-len(warmups)) + max(0, expected_trials-len(trials))
    for fixture in FIXTURES:
        for side in SIDES:
            if sum(1 for r in trials if r.get("fixture")==fixture and r.get("side")==side) != repetitions:
                validation_errors.append(f"incomplete repetition group: {fixture}/{side}")
            if sum(1 for r in warmups if r.get("fixture")==fixture and r.get("side")==side) != warmups_per_fixture:
                validation_errors.append(f"incorrect warmup count: {fixture}/{side}")
    return warmups, trials, validation_errors, missing


def summarize(trials: list[dict], warmups: list[dict], valid: bool, missing: int) -> dict:
    rows = []
    for fixture in FIXTURES:
        for side in SIDES:
            subset = [r for r in trials if r["fixture"] == fixture and r["side"] == side]
            for phase in PHASES:
                values = [r["durations_ns"][phase] for r in subset if isinstance(r.get("durations_ns", {}).get(phase), int)]
                rows.append({"fixture": fixture, "side": side, "phase": phase,
                             "median_ns": statistics.median(values) if valid and values else None,
                             "min_ns": min(values) if valid and values else None,
                             "max_ns": max(values) if valid and values else None, "count": len(values)})
    return {"failure_count": sum(r.get("status") != "passed" or r.get("oracle_match") is not True for r in [*trials,*warmups]),
            "missing_count": missing, "valid": valid, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="functional coverage only; timing is discarded")
    mode.add_argument("--measure", action="store_true", help="seven matched repetitions; use only after fixed-source review")
    ap.add_argument("--exe", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="new collection directory; required for --measure")
    ap.add_argument("--build-dir", type=Path, help="configured CMake build directory; required for --measure")
    ap.add_argument("--source-commit", help="fixed algorithm source commit; required for --measure")
    ap.add_argument("--harness-commit", help="reviewed harness commit; required for --measure")
    ap.add_argument("--concurrent-work-file", type=Path, help="operator load/concurrent-work note; required for --measure")
    args = ap.parse_args()
    if args.measure and any(value is None for value in (args.out,args.build_dir,args.source_commit,args.harness_commit,args.concurrent_work_file)):
        ap.error("--measure requires --out, --build-dir, --source-commit, --harness-commit and --concurrent-work-file")
    try:
        completed = subprocess.run([str(args.exe), "--smoke"] if args.smoke else [str(args.exe)], text=True, capture_output=True, check=False)
        parsed, parse_errors = parse_output(completed.stdout)
        warmups, trials, validation_errors, missing = normalize_and_pair(parsed, repetitions=1 if args.smoke else 7,
                                                                         warmups_per_fixture=0 if args.smoke else 1)
        validation_errors.extend(parse_errors)
        if args.smoke:
            if completed.returncode or validation_errors or len(trials) != len(FIXTURES)*len(SIDES) or warmups:
                sys.stderr.write(completed.stderr)
                raise ValueError("functional smoke failed: " + "; ".join(validation_errors or ["wrong smoke matrix"]))
            print(f"OPT-04 smoke passed: {len(trials)} fixture-side trials; timings discarded")
            return 0
        build_dir=args.build_dir.resolve()
        exe=args.exe.resolve()
        if not exe.is_relative_to(build_dir):
            raise ValueError("measurement executable must be inside the named build directory")
        if not args.concurrent_work_file.is_file():
            raise ValueError("concurrent-work note does not exist")
        concurrent_work=args.concurrent_work_file.read_text(encoding="utf-8").strip()
        if not concurrent_work:
            raise ValueError("concurrent-work note must describe observed host load/work")
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        if head != args.harness_commit:
            raise ValueError("HEAD does not match the supplied reviewed harness commit")
        if subprocess.check_output(["git","status","--porcelain=v1","--untracked-files=no"],cwd=ROOT,text=True).strip():
            raise ValueError("tracked source tree is dirty")
        executable_sha=hashlib.sha256(exe.read_bytes()).hexdigest()
        cache=build_dir/"CMakeCache.txt"
        if not cache.is_file():
            raise ValueError("build directory has no CMakeCache.txt")
        cmake_cache_sha=hashlib.sha256(cache.read_bytes()).hexdigest()
        out = args.out.resolve()
        if out.exists():
            raise ValueError(f"output already exists: {out}")
        out.mkdir(parents=True)
        catalog = [{"id": name, **details,
                    "expected_reference_status": details["expected_status"], "absolute_tolerance": 1e-8, "relative_tolerance": 0.0}
                   for name, details in FIXTURES.items()]
        execution_order = []
        for repetition in range(7):
            schedule = sorted((r for r in trials if r.get("repetition")==repetition), key=lambda r:r.get("sequence",-1))
            execution_order.append({"repetition": repetition, "sequence": [{"fixture":r.get("fixture"),"side":r.get("side"),"order_index":i} for i,r in enumerate(schedule)]})
        id_hash = hashlib.sha256(completed.stdout.encode()).hexdigest()[:12]
        record = {"schema": SCHEMA, "report_id": f"opt04-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{id_hash}",
                  "evidence_support": "Unestablished", "claims": {"scope": "paired descriptive analytic fixtures", "speedup": False, "feasibility_numerics": "Unestablished"},
                  "algorithm": {"registration_id": "phase-one-bland", "version": "1"},
                  "reference": {"registration_id": "highs_lp", "version": "1.0.0+highs.1.11.0"},
                  "provenance": {"source_commit": args.source_commit, "harness_commit": args.harness_commit,
                                 "executable_sha256": executable_sha, "cmake_cache_sha256": cmake_cache_sha,
                                 "build_directory": "BUILD_ROOT", "executable_path": "BUILD_ROOT/"+exe.relative_to(build_dir).as_posix(),
                                 "host_platform": platform.platform(), "processor": platform.processor(),
                                 "python": platform.python_version(), "concurrent_work": concurrent_work,
                                 "limiter_profile": "required as a separate post-review profile-only execution; no profile data mixed with trials"},
                  "catalog": {"version": "opt04-analytic-v1", "fixtures": catalog},
                  "measurement": {"warmups_per_fixture": 1, "repetitions_per_fixture": 7, "sides": list(SIDES), "execution_order": execution_order,
                                  "timing_boundaries": {"setup": "program publication, registration, selection, preparation and fresh workspace creation", "public_run": "BoundWorkspace.run", "verification": "independent expected outcome, candidate, equality residual and nonnegativity checks", "end_to_end": "fixture construction through independent verification; excludes process startup and serialization"}},
                  "warmup_trials": warmups, "trials": trials, "summary": summarize(trials, warmups, not completed.returncode and not validation_errors and not missing, missing),
                  "collection_errors": validation_errors, "process_exit_code": completed.returncode}
        (out / "records.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (out / "stdout.jsonl").write_text("\n".join(json.dumps(r, separators=(",", ":"), allow_nan=False) for r in [*warmups,*trials]) + "\n", encoding="utf-8")
        (out / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        (out / "driver-stdout.txt").write_text(completed.stdout, encoding="utf-8")
        print(f"saved {len(trials)} measured trials and {len(warmups)} warmups to {out}")
        if completed.returncode or validation_errors or missing:
            print(f"collection retained with {len(validation_errors)} validation errors and {missing} missing trials", file=sys.stderr)
            return 2
        return 0
    except (OSError, ValueError) as exc:
        print(f"OPT-04 collection error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

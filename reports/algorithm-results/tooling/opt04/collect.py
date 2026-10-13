#!/usr/bin/env python3
"""Run the OPT-04 functional smoke or, after review, collect matched trials."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = "csl.opt04-phase-one-report/2"
FIXTURES = {
    "triangle": {"rows": 3, "columns": 3, "matrix": [[0,1,0],[0,0,1],[1,1,1]], "rhs": [.25,.25,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.25,.25], "expected_auxiliary": 0.0},
    "signed_triangle": {"rows": 3, "columns": 3, "matrix": [[-1,1,-1],[-1,-1,1],[1,1,1]], "rhs": [-.5,-.5,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.25,.25], "expected_auxiliary": 0.0},
    "edge": {"rows": 3, "columns": 3, "matrix": [[0,1,0],[0,0,1],[1,1,1]], "rhs": [.5,0,1], "expected_status": "optimal", "expected_phase_one_primal": [.5,.5,0.0], "expected_auxiliary": 0.0},
    "duplicate_tie": {"rows": 2, "columns": 2, "matrix": [[1,1],[1,1]], "rhs": [1,1], "expected_status": "optimal", "expected_phase_one_primal": [1.0,0.0], "expected_auxiliary": 0.0},
    "contradictory_rows": {"rows": 2, "columns": 1, "matrix": [[1],[1]], "rhs": [0,1], "expected_status": "infeasible", "expected_phase_one_primal": [0.0], "expected_auxiliary": 1.0},
}
SIDES = ("phase-one-bland", "highs-reference")
PHASES = ("setup", "public_run", "verification", "end_to_end")


def _canonical_sha256(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def fixture_fingerprints(fixture: dict, input_description: dict | None = None) -> dict[str, str]:
    description = input_description or {
        "matrix": fixture["matrix"], "rhs": fixture["rhs"], "row_relation": "equality",
        "variable_lower_bound": 0.0, "variable_upper_bound": None,
        "objective_coefficients": [0.0] * fixture["columns"], "objective_constant": 0.0,
    }
    inputs = {"matrix": [[float(value) for value in row] for row in description["matrix"]],
              "rhs": [float(value) for value in description["rhs"]]}
    input_sha256 = _canonical_sha256(inputs)
    scenario = {"input_sha256": input_sha256, "row_relation": description["row_relation"],
                "variable_lower_bound": description["variable_lower_bound"],
                "variable_upper_bound": description["variable_upper_bound"],
                "objective": {"coefficients": [float(value) for value in description["objective_coefficients"]],
                              "constant": float(description["objective_constant"])},
                "tolerances": {"absolute": 1e-8, "relative": 0.0}}
    return {"input_sha256": input_sha256, "scenario_sha256": _canonical_sha256(scenario)}


def execution_policy() -> dict:
    return {
        "arithmetic": {"format": "IEEE-754 binary64", "validated_arithmetic": False,
                       "rounding_mode": None, "rounding_mode_reason": "runtime rounding mode is not observed"},
        "seed": {"value": None, "status": "not_applicable",
                 "reason": "the fixtures and configured solver profiles use no randomized algorithm"},
        "requested": {
            "resource_context": {"total_threads": 1, "outer_workers": 1, "threads_per_worker": 1},
            "solver_profiles": {
                "phase-one-bland": {"native_threads": "not_applicable", "reason": "single-threaded in-process implementation"},
                "highs-reference": {"solver": "simplex", "presolve": "off", "parallel": "off", "native_threads": 1},
            },
        },
        "actual": {
            "outer_workers": {"value": None, "reason": "runtime worker observations are not emitted by this harness"},
            "native_threads": {"value": None, "reason": "OS/native thread observations are not collected by this harness"},
        },
    }


def validate_build_directory(build_dir: Path, executable: Path, source_root: Path) -> str:
    build_dir, executable, source_root = build_dir.resolve(), executable.resolve(), source_root.resolve()
    if not executable.is_relative_to(build_dir):
        raise ValueError("measurement executable must be inside the named build directory")
    values = _cmake_cache(build_dir)
    configured_source = values.get("CMAKE_HOME_DIRECTORY:INTERNAL")
    if not configured_source or not Path(configured_source).samefile(source_root):
        raise ValueError("CMake build directory is not configured from this source tree")
    configurations = values.get("CMAKE_CONFIGURATION_TYPES:STRING")
    if "NDEBUG" not in values.get("CMAKE_CXX_FLAGS_RELEASE:STRING", "").upper():
        raise ValueError("configured Release C++ flags do not define NDEBUG")
    if configurations:
        if "Release" not in configurations.split(";"):
            raise ValueError("multi-configuration build does not offer Release")
        expected = [build_dir / "Release" / ("csl_opt04_phase_one_report" + suffix) for suffix in (".exe", "")]
        if not any(path.is_file() and path.samefile(executable) for path in expected):
            raise ValueError("executable is not the csl_opt04_phase_one_report Release target")
    else:
        if values.get("CMAKE_BUILD_TYPE:STRING", "").lower() != "release":
            raise ValueError("single-configuration build must be configured as Release")
        expected = [build_dir / ("csl_opt04_phase_one_report" + suffix) for suffix in (".exe", "")]
        if not any(path.is_file() and path.samefile(executable) for path in expected):
            raise ValueError("executable is not the csl_opt04_phase_one_report target")
    return "Release"


def run_with_timeout(command: list[str], timeout_seconds: float) -> tuple[subprocess.CompletedProcess, bool]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False,
                              timeout=timeout_seconds), False
    except subprocess.TimeoutExpired as exc:
        def as_text(value: str | bytes | None) -> str:
            if value is None:
                return ""
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        return subprocess.CompletedProcess(command, 124, as_text(exc.stdout), as_text(exc.stderr)), True


def _failed_check(checks: list, name: str) -> list:
    if isinstance(checks, list) and all(isinstance(item, dict) and isinstance(item.get("passed"), bool) for item in checks):
        checks = list(checks)
        if not any(item.get("passed") is False for item in checks):
            checks.append({"name": name, "passed": False})
        return checks
    return [{"name": name, "passed": False}]


def _cmake_cache(build_dir: Path) -> dict[str, str]:
    path = build_dir / "CMakeCache.txt"
    if not path.is_file():
        raise ValueError("build directory has no CMakeCache.txt")
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _compiler_metadata(build_dir: Path) -> dict[str, str]:
    candidates = sorted((build_dir / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    for path in candidates:
        content = path.read_text(encoding="utf-8", errors="replace")
        compiler_id = re.search(r'^set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', content, re.MULTILINE)
        compiler_version = re.search(r'^set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', content, re.MULTILINE)
        if compiler_id and compiler_version:
            return {"id": compiler_id.group(1), "version": compiler_version.group(1)}
    raise ValueError("configured C++ compiler identity is unavailable")


def release_build_command(build_dir: Path) -> list[str]:
    cache = _cmake_cache(build_dir)
    cmake = cache.get("CMAKE_COMMAND:INTERNAL") or shutil.which("cmake")
    if not cmake or not Path(cmake).is_file():
        raise ValueError("CMake executable is unavailable from the configured build")
    return [cmake, "--build", str(build_dir), "--config", "Release", "--clean-first",
            "--target", "csl_opt04_phase_one_report", "--parallel", "4", "--verbose"]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def _clean_reviewed_source(source_commit: str, harness_commit: str) -> None:
    for name, value in (("source", source_commit), ("harness", harness_commit)):
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError(f"{name} commit must be a full lowercase SHA")
        subprocess.run(["git", "cat-file", "-e", value + "^{commit}"], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if _git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("HEAD does not match the supplied reviewed harness commit")
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, harness_commit], cwd=ROOT)
    if ancestry.returncode != 0:
        raise ValueError("algorithm source commit is not an ancestor of the reviewed harness commit")
    algorithm_paths = ["src/optimization/phase_one", "include/csl/optimization/phase_one.hpp"]
    algorithm_diff = subprocess.run(["git", "diff", "--quiet", source_commit, harness_commit, "--", *algorithm_paths], cwd=ROOT)
    if algorithm_diff.returncode != 0:
        raise ValueError("phase-I algorithm sources differ from the declared source commit")
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("source tree is dirty, including untracked nonignored files")


def _sanitize_build_log(text: str, build_dir: Path) -> str:
    for actual, token in ((str(ROOT.resolve()), "SOURCE_ROOT"), (str(build_dir.resolve()), "BUILD_ROOT"),
                          (str(Path.home().resolve()), "USER_HOME")):
        for normalized in {actual, actual.replace("/", "\\"), actual.replace("\\", "/")}:
            text = text.replace(normalized, token)
    return text


def parse_output(raw: str) -> tuple[list[dict], list[str]]:
    rows = []
    errors = []
    def reject_nonfinite(value: str):
        raise ValueError(f"nonstandard numeric value {value}")
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=reject_nonfinite)
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"stdout line {number} is not JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"stdout line {number} is not a trial object")
            continue
        rows.append(value)
    return rows, errors


def normalize_and_pair(rows: list[dict], repetitions: int = 7, warmups_per_fixture: int = 1) -> tuple[list[dict], list[dict], list[str], int]:
    warmups, trials = [], []
    validation_errors = []
    seen_keys, seen_sequences = set(), set()
    for original in rows:
        is_warmup = original.get("warmup")
        if type(is_warmup) is not bool:
            validation_errors.append("trial has no boolean warmup discriminator; raw line retained in driver-stdout.txt")
            continue
        row = dict(original)
        bucket = warmups if is_warmup else trials
        if row.get("fixture") not in FIXTURES or row.get("side") not in SIDES:
            validation_errors.append("trial has unknown fixture or side; raw line retained in driver-stdout.txt")
            continue
        required_identity = ("repetition", "sequence", "pair_id")
        if any(key not in row for key in required_identity):
            validation_errors.append(f"trial identity fields missing for {row['fixture']} / {row['side']}; raw line retained in driver-stdout.txt")
            continue
        if (not isinstance(row.get("repetition"), int) or isinstance(row.get("repetition"), bool)
                or not isinstance(row.get("sequence"), int) or isinstance(row.get("sequence"), bool)
                or not isinstance(row.get("pair_id"), str) or not row["pair_id"]):
            validation_errors.append(f"invalid trial identity for {row['fixture']} / {row['side']}; raw line retained in driver-stdout.txt")
            continue
        repetition = row["repetition"]
        if (is_warmup and repetition != 0) or (not is_warmup and not 0 <= repetition < repetitions):
            validation_errors.append(f"out-of-range repetition for {row['fixture']} / {row['side']}; raw line retained in driver-stdout.txt")
            continue
        key = (is_warmup, row["fixture"], row["side"], repetition)
        if key in seen_keys or row["sequence"] in seen_sequences:
            validation_errors.append(f"duplicate trial identity/order for {row['fixture']} / {row['side']}; duplicate line retained in driver-stdout.txt")
            continue
        seen_keys.add(key)
        seen_sequences.add(row["sequence"])
        fixture = FIXTURES[row["fixture"]]
        errors = []
        input_description = row.get("input")
        input_keys = {"matrix", "rhs", "row_relation", "variable_lower_bound", "variable_upper_bound",
                      "objective_coefficients", "objective_constant"}
        fingerprints = None
        if not isinstance(input_description, dict) or set(input_description) != input_keys:
            errors.append("driver input description is missing or malformed")
        else:
            try:
                matrix, rhs = input_description["matrix"], input_description["rhs"]
                if (not isinstance(matrix, list) or len(matrix) != fixture["rows"]
                        or any(not isinstance(values, list) or len(values) != fixture["columns"] for values in matrix)
                        or not isinstance(rhs, list) or len(rhs) != fixture["rows"]):
                    raise ValueError("dimensions differ")
                numeric = [value for values in matrix for value in values] + rhs + input_description["objective_coefficients"] + [input_description["objective_constant"]]
                if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in numeric):
                    raise ValueError("non-finite or non-numeric values")
                fingerprints = fixture_fingerprints(fixture, input_description)
                expected_description = {
                    "matrix": fixture["matrix"], "rhs": fixture["rhs"], "row_relation": "equality",
                    "variable_lower_bound": 0.0, "variable_upper_bound": None,
                    "objective_coefficients": [0.0] * fixture["columns"], "objective_constant": 0.0,
                }
                if input_description != expected_description:
                    errors.append("actual driver input differs from catalog")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                errors.append(f"driver input description is invalid: {exc}")
        row["input_sha256"] = fingerprints["input_sha256"] if fingerprints else None
        row["scenario_sha256"] = fingerprints["scenario_sha256"] if fingerprints else None
        row["input"] = input_description if fingerprints else None
        expected_pair_id = f"{row['fixture']}-warmup-{repetition}" if is_warmup else f"{row['fixture']}-{repetition}"
        if row["pair_id"] != expected_pair_id:
            errors.append("pair_id does not match fixture/repetition")
            row["pair_id"] = expected_pair_id
        required_fields = ("status", "observed_status", "oracle_match", "oracle_checks", "work_observed", "durations_ns", "result", "input")
        errors.extend(f"missing {field}" for field in required_fields if field not in row)
        if "status" in row and not isinstance(row["status"], str):
            errors.append("status is not text")
        if "observed_status" in row and not isinstance(row["observed_status"], str):
            errors.append("observed_status is not text")
        if "oracle_match" in row and not isinstance(row["oracle_match"], bool):
            errors.append("oracle_match is not boolean")
        if "work_observed" in row and not isinstance(row["work_observed"], bool):
            errors.append("work_observed is not boolean")
        result = row.get("result")
        if not isinstance(result, dict):
            result = {}
            errors.append("result is not an object")
        result_defaults = {"termination": "exception", "outcome": "undetermined", "primal": None,
                           "auxiliary": None, "pivots": None, "degenerate_pivots": None, "factorizations": None}
        for key, value in result_defaults.items():
            if key not in result:
                result[key] = value
                errors.append(f"result.{key} missing")
        if not isinstance(result.get("termination"), str) or not isinstance(result.get("outcome"), str):
            errors.append("result classification is not textual")
            result["termination"], result["outcome"] = "exception", "undetermined"
        primal = result.get("primal")
        if primal is not None and (not isinstance(primal, list) or any(
                not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in primal)):
            errors.append("result.primal is not a finite numeric vector")
        if row.get("status") == "passed" and row.get("observed_status") == "optimal" and not isinstance(primal, list):
            errors.append("successful optimal result has no primal vector")
        auxiliary = result.get("auxiliary")
        if auxiliary is not None and (not isinstance(auxiliary, (int, float)) or isinstance(auxiliary, bool) or not math.isfinite(auxiliary)):
            errors.append("result.auxiliary is not finite numeric data")
        if row["side"] == "phase-one-bland" and row.get("status") == "passed" and auxiliary is None:
            errors.append("successful phase-I result has no auxiliary value")
        if row["side"] == "highs-reference" and auxiliary is not None:
            errors.append("reference result contains phase-I-only auxiliary value")
        for field in ("pivots", "degenerate_pivots", "factorizations"):
            value = result.get(field)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                errors.append(f"result.{field} is not a nonnegative integer")
            if row["side"] == "phase-one-bland" and row.get("status") == "passed" and value is None:
                errors.append(f"successful phase-I result has no {field} diagnostic")
            if row["side"] == "highs-reference" and value is not None:
                errors.append(f"reference result contains phase-I-only {field}")
        row["result"] = result
        durations = row.get("durations_ns")
        if not isinstance(durations, dict):
            durations = {}
            errors.append("durations_ns is not an object")
        row["durations_ns"] = {phase: durations.get(phase) for phase in PHASES}
        if any(not isinstance(row["durations_ns"][phase], int) or isinstance(row["durations_ns"][phase], bool)
               or row["durations_ns"][phase] < 0 for phase in PHASES):
            errors.append("durations_ns is incomplete or invalid")
            row["durations_ns"] = {phase: None for phase in PHASES}
        checks = row.get("oracle_checks")
        if not isinstance(checks, list) or not all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                                   and bool(item["name"]) and isinstance(item.get("passed"), bool) for item in checks):
            errors.append("oracle_checks is malformed")
            checks = []
        row["oracle_checks"] = checks
        if "error" in row and row["error"] is not None and not isinstance(row["error"], str):
            errors.append("error diagnostic is not text")
        residual_fields = ("original_rows_max_violation", "nonnegative_max_violation", "objective_value", "auxiliary_residual", "auxiliary_value")
        for field in residual_fields:
            value = row.get(field)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)):
                errors.append(f"{field} is not finite numeric data")
        if row["side"] == "phase-one-bland" and row.get("status") == "passed" and any(row.get(field) is None for field in residual_fields):
            errors.append("successful phase-I row has missing residual diagnostics")
        if row["side"] == "highs-reference" and any(row.get(field) is not None for field in residual_fields):
            errors.append("reference row contains phase-I-only diagnostics")
        if errors:
            validation_errors.extend(f"{row['fixture']} / {row['side']}: {error}" for error in errors)
            row["status"] = "failed"
            row["observed_status"] = str(row.get("observed_status") or result.get("outcome") or "undetermined")
            result["outcome"] = row["observed_status"]
            result["termination"] = str(result.get("termination") or "exception")
            row["oracle_match"] = False
            row["oracle_checks"] = _failed_check(checks, "record_complete")
            row["work_observed"] = row.get("work_observed") is True
            existing_error = row.get("error")
            row["error"] = "; ".join(([str(existing_error)] if existing_error else []) + errors)
        elif (row.get("observed_status") != fixture["expected_status"] or row.get("status") != "passed"
              or row.get("oracle_match") is not True or row.get("work_observed") is not True
              or not row["oracle_checks"] or not all(c.get("passed") is True for c in row["oracle_checks"])
              or result.get("termination") != "completed" or result.get("outcome") != row.get("observed_status")):
            validation_errors.append(f"failed status/oracle/work check: {row['fixture']} / {row['side']}")
            row["status"] = "failed"
            row["oracle_match"] = False
            row["oracle_checks"] = _failed_check(row["oracle_checks"], "collection_validation")
        row["error"] = row.get("error") if isinstance(row.get("error"), str) else None
        row["expected_status"] = fixture["expected_status"]
        row["tolerances"] = {"absolute": 1e-8, "relative": 0.0}
        for field in ("original_rows_max_violation", "nonnegative_max_violation", "objective_value", "auxiliary_residual", "auxiliary_value"):
            row.setdefault(field, None)
        row.setdefault("error", None)
        row.setdefault("work_observed", False)
        bucket.append(row)
    for row in [*warmups, *trials]:
        row.pop("warmup", None)
    groups: dict[str, list[dict]] = {}
    for row in [*warmups, *trials]:
        groups.setdefault(row.get("pair_id", "malformed"), []).append(row)
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
    for fixture in FIXTURES:
        for side in SIDES:
            if sum(1 for r in trials if r.get("fixture")==fixture and r.get("side")==side) != repetitions:
                validation_errors.append(f"incomplete repetition group: {fixture}/{side}")
            if sum(1 for r in warmups if r.get("fixture")==fixture and r.get("side")==side) != warmups_per_fixture:
                validation_errors.append(f"incorrect warmup count: {fixture}/{side}")
    missing = sum(max(0, warmups_per_fixture - sum(1 for r in warmups if r.get("fixture") == fixture and r.get("side") == side))
                  + max(0, repetitions - sum(1 for r in trials if r.get("fixture") == fixture and r.get("side") == side))
                  for fixture in FIXTURES for side in SIDES)
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
    ap.add_argument("--timeout-seconds", type=float, default=300, help="outer driver timeout for --measure (default: 300)")
    args = ap.parse_args()
    if args.measure and any(value is None for value in (args.out,args.build_dir,args.source_commit,args.harness_commit,args.concurrent_work_file)):
        ap.error("--measure requires --out, --build-dir, --source-commit, --harness-commit and --concurrent-work-file")
    try:
        if args.smoke:
            completed, aborted = run_with_timeout([str(args.exe), "--smoke"], 60)
        else:
            completed, aborted = None, False
        if args.smoke and aborted:
            sys.stderr.write(completed.stderr)
            raise ValueError("functional smoke exceeded its 60-second timeout")
        if args.smoke:
            parsed, parse_errors = parse_output(completed.stdout)
            warmups, trials, validation_errors, missing = normalize_and_pair(parsed, repetitions=1,
                                                                              warmups_per_fixture=0)
            validation_errors.extend(parse_errors)
            if completed.returncode or validation_errors or len(trials) != len(FIXTURES)*len(SIDES) or warmups:
                sys.stderr.write(completed.stderr)
                raise ValueError("functional smoke failed: " + "; ".join(validation_errors or ["wrong smoke matrix"]))
            print(f"OPT-04 smoke passed: {len(trials)} fixture-side trials; timings discarded")
            return 0

        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        out = args.out.resolve()
        if out.exists():
            raise ValueError(f"output already exists: {out}")
        build_dir = args.build_dir.resolve()
        exe = args.exe.resolve()
        validate_build_directory(build_dir, exe, ROOT)
        if not args.concurrent_work_file.is_file():
            raise ValueError("concurrent-work note does not exist")
        concurrent_work=args.concurrent_work_file.read_text(encoding="utf-8").strip()
        if not concurrent_work:
            raise ValueError("concurrent-work note must describe observed host load/work")
        _clean_reviewed_source(args.source_commit, args.harness_commit)
        build_command = release_build_command(build_dir)
        build_result, build_aborted = run_with_timeout(build_command, 1200)
        release_build_log = _sanitize_build_log(build_result.stdout + build_result.stderr, build_dir)
        if build_aborted or build_result.returncode != 0:
            detail = release_build_log[-4000:]
            raise ValueError("fresh clean Release rebuild failed:\n" + detail)
        _clean_reviewed_source(args.source_commit, args.harness_commit)
        validate_build_directory(build_dir, exe, ROOT)
        if not exe.is_file():
            raise ValueError("clean Release rebuild did not produce the selected executable")
        build_cache = _cmake_cache(build_dir)
        compiler = _compiler_metadata(build_dir)
        executable_sha=hashlib.sha256(exe.read_bytes()).hexdigest()
        cache=build_dir/"CMakeCache.txt"
        cmake_cache_sha=hashlib.sha256(cache.read_bytes()).hexdigest()
        out.mkdir(parents=True)
        (out / "release-build.txt").write_text(release_build_log, encoding="utf-8", newline="\n")
        completed, aborted = run_with_timeout([str(exe)], args.timeout_seconds)
        parsed, parse_errors = parse_output(completed.stdout)
        warmups, trials, validation_errors, missing = normalize_and_pair(parsed)
        validation_errors.extend(parse_errors)
        if aborted:
            validation_errors.append(f"driver process timed out after {args.timeout_seconds:g} seconds")
        elif completed.returncode != 0:
            validation_errors.append(f"driver process returned {completed.returncode}")
        catalog = [{"id": name, **details, **fixture_fingerprints(details),
                    "expected_reference_status": details["expected_status"], "absolute_tolerance": 1e-8, "relative_tolerance": 0.0}
                   for name, details in FIXTURES.items()]
        execution_order = []
        for repetition in range(7):
            schedule = sorted((r for r in trials if r.get("repetition")==repetition), key=lambda r:r.get("sequence",-1))
            execution_order.append({"repetition": repetition, "sequence": [{"fixture":r.get("fixture"),"side":r.get("side"),"order_index":i} for i,r in enumerate(schedule)]})
        id_hash = hashlib.sha256(completed.stdout.encode()).hexdigest()[:12]
        record = {"schema": SCHEMA, "report_id": f"opt04-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{id_hash}",
                  "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "evidence_support": "Unestablished", "claims": {"scope": "paired descriptive analytic fixtures", "speedup": False, "feasibility_numerics": "Unestablished"},
                  "evidence_limits": ["Five small analytic equality/nonnegative fixtures only.",
                                      "No exact or validated arithmetic feasibility certificate is claimed.",
                                      "No application-scale, scalability, or speedup claim is made.",
                                      "The collinear-input acceptance case is not included; OPT-04 issue #29 remains open.",
                                      "A witness sample is not the complete feasible or optimal solution family."],
                  "algorithm": {"registration_id": "phase-one-bland", "version": "1"},
                  "reference": {"registration_id": "highs_lp", "version": "1.0.0+highs.1.11.0"},
                  "provenance": {"source_commit": args.source_commit, "harness_commit": args.harness_commit,
                                 "executable_sha256": executable_sha, "cmake_cache_sha256": cmake_cache_sha,
                                 "release_build_sha256": hashlib.sha256(release_build_log.encode("utf-8")).hexdigest(),
                                 "release_build_command": ["cmake", "--build", "BUILD_ROOT", "--config", "Release", "--clean-first", "--target", "csl_opt04_phase_one_report", "--parallel", "4", "--verbose"],
                                 "compiler_id": compiler["id"], "compiler_version": compiler["version"],
                                 "cxx_standard": 20, "release_ndebug": True,
                                 "cmake_generator": build_cache.get("CMAKE_GENERATOR:INTERNAL", "unknown"),
                                 "release_flags": _sanitize_build_log(build_cache.get("CMAKE_CXX_FLAGS_RELEASE:STRING", ""), build_dir),
                                 "logical_processors": os.cpu_count(),
                                 "build_directory": "BUILD_ROOT", "executable_path": "BUILD_ROOT/"+exe.relative_to(build_dir).as_posix(),
                                 "host_platform": platform.platform(), "processor": platform.processor(),
                                 "python": platform.python_version(), "concurrent_work": concurrent_work,
                                 "limiter_profile": "required as a separate post-review profile-only execution; no profile data mixed with trials"},
                  "catalog": {"version": "opt04-analytic-v1", "fixtures": catalog},
                  "measurement": {"warmups_per_fixture": 1, "repetitions_per_fixture": 7, "sides": list(SIDES), "execution_order": execution_order,
                                  "execution_policy": execution_policy(),
                                  "timing_boundaries": {"setup": "program publication, registration, selection, preparation and fresh workspace creation", "public_run": "BoundWorkspace.run", "verification": "independent expected outcome, candidate, equality residual and nonnegativity checks", "end_to_end": "fixture construction through independent verification; excludes process startup and serialization"}},
                  "warmup_trials": warmups, "trials": trials, "summary": summarize(trials, warmups, not completed.returncode and not aborted and not validation_errors and not missing, missing),
                  "collection_errors": validation_errors, "process_exit_code": completed.returncode, "aborted": aborted}
        (out / "records.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (out / "stdout.jsonl").write_text("\n".join(json.dumps(r, separators=(",", ":"), allow_nan=False) for r in [*warmups,*trials]) + "\n", encoding="utf-8")
        (out / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        (out / "driver-stdout.txt").write_text(completed.stdout, encoding="utf-8")
        print(f"saved {len(trials)} measured trials and {len(warmups)} warmups to {out}")
        if completed.returncode or aborted or validation_errors or missing:
            print(f"collection retained with {len(validation_errors)} validation errors and {missing} missing trials", file=sys.stderr)
            return 2
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"OPT-04 collection error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

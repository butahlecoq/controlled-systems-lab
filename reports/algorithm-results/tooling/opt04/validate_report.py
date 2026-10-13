#!/usr/bin/env python3
"""Validate saved OPT-04 report records, rendering, manifest, and offline bundle."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import tempfile
from pathlib import Path
import zipfile


SCHEMA = "csl.opt04-phase-one-report/2"
PHASES = ("setup", "public_run", "verification", "end_to_end")
SIDES = ("phase-one-bland", "highs-reference")
PACKAGE_NAMES = {"manifest.sha256", "bundle.zip", "bundle.zip.sha256"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def finite_number(value: object, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), f"{label} must be finite numeric")
    return float(value)


def _primal_residuals(problem: dict, primal: list, label: str) -> dict[str, float]:
    values = [finite_number(value, f"{label}.primal") for value in primal]
    matrix, rhs = problem["matrix"], problem["rhs"]
    row_violation = max(abs(sum(coefficient * value for coefficient, value in zip(row, values)) - target)
                        for row, target in zip(matrix, rhs))
    lower = problem["variable_lower_bound"]
    upper = problem["variable_upper_bound"]
    bound_violations = []
    if lower is not None:
        bound_violations.extend(max(0.0, lower - value) for value in values)
    if upper is not None:
        bound_violations.extend(max(0.0, value - upper) for value in values)
    bound_violation = max(bound_violations, default=0.0)
    objective = sum(coefficient * value for coefficient, value
                    in zip(problem["objective_coefficients"], values)) + problem["objective_constant"]
    return {"original_equalities": row_violation,
            "nonnegative_variables": bound_violation,
            "zero_original_objective": abs(objective)}


def nonnegative_ns(value: object, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{label} must be a nonnegative integer nanosecond count")
    return value


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _fixture_map(records: dict) -> dict[str, dict]:
    catalog = records.get("catalog")
    require(isinstance(catalog, dict) and isinstance(catalog.get("fixtures"), list)
            and bool(catalog["fixtures"]), "catalog.fixtures must be a nonempty list")
    found = {}
    for fixture in catalog["fixtures"]:
        require(isinstance(fixture, dict), "catalog fixture must be an object")
        fixture_id = fixture.get("id")
        require(isinstance(fixture_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", fixture_id),
                f"invalid fixture ID: {fixture_id!r}")
        require(fixture_id not in found, f"duplicate fixture ID: {fixture_id}")
        require(isinstance(fixture.get("rows"), int) and not isinstance(fixture["rows"], bool) and fixture["rows"] > 0
                and isinstance(fixture.get("columns"), int) and not isinstance(fixture["columns"], bool) and fixture["columns"] > 0,
                f"{fixture_id}: rows and columns must be positive integers")
        require(isinstance(fixture.get("expected_status"), str) and fixture["expected_status"],
                f"{fixture_id}: expected_status is required")
        absolute = finite_number(fixture.get("absolute_tolerance"), f"{fixture_id}.absolute_tolerance")
        relative = finite_number(fixture.get("relative_tolerance"), f"{fixture_id}.relative_tolerance")
        require(absolute >= 0 and relative >= 0, f"{fixture_id}: tolerances must be nonnegative")
        found[fixture_id] = fixture
    return found


def validate_records(records: dict) -> dict:
    require(isinstance(records, dict) and records.get("schema") == SCHEMA,
            f"unsupported records schema (expected {SCHEMA})")
    report_id = records.get("report_id")
    require(isinstance(report_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", report_id), "invalid report_id")
    require(records.get("evidence_support") == "Unestablished", "evidence_support must remain Unestablished")
    claims = records.get("claims")
    require(isinstance(claims, dict) and claims.get("speedup") is False
            and claims.get("feasibility_numerics") == "Unestablished", "claims overstate the evidence")
    fixtures = _fixture_map(records)
    for fid, fixture in fixtures.items():
        require(fixture.get("expected_status") in ("optimal", "infeasible"), f"{fid}: unsupported expected status")
        require(fixture.get("expected_reference_status") in ("optimal", "infeasible"), f"{fid}: missing expected reference status")
        matrix, rhs = fixture.get("matrix"), fixture.get("rhs")
        require(isinstance(matrix, list) and len(matrix) == fixture["rows"]
                and all(isinstance(row, list) and len(row) == fixture["columns"] for row in matrix),
                f"{fid}: matrix dimensions do not match catalog")
        require(isinstance(rhs, list) and len(rhs) == fixture["rows"], f"{fid}: rhs dimensions do not match catalog")
        for row in matrix:
            for value in row:
                finite_number(value, f"{fid}.matrix")
        for value in rhs:
            finite_number(value, f"{fid}.rhs")
        input_sha256 = canonical_sha256({"matrix": [[float(value) for value in row] for row in matrix],
                                         "rhs": [float(value) for value in rhs]})
        require(fixture.get("input_sha256") == input_sha256, f"{fid}: input hash does not match matrix and RHS")
        scenario = {"input_sha256": input_sha256, "row_relation": "equality",
                    "variable_lower_bound": 0.0, "variable_upper_bound": None,
                    "objective": {"coefficients": [0.0] * fixture["columns"], "constant": 0.0},
                    "tolerances": {"absolute": fixture["absolute_tolerance"], "relative": fixture["relative_tolerance"]}}
        require(fixture.get("scenario_sha256") == canonical_sha256(scenario),
                f"{fid}: scenario hash does not match the represented mathematical problem")
        finite_number(fixture.get("expected_auxiliary"), f"{fid}.expected_auxiliary")
        primal = fixture.get("expected_phase_one_primal")
        require(isinstance(primal, list) and len(primal) == fixture["columns"], f"{fid}: expected primal dimension mismatch")
        for value in primal:
            finite_number(value, f"{fid}.expected_phase_one_primal")

    measurement = records.get("measurement")
    require(isinstance(measurement, dict) and measurement.get("warmups_per_fixture") == 1
            and measurement.get("repetitions_per_fixture") == 7, "measurement must declare one warmup and seven repetitions")
    require(measurement.get("sides") == list(SIDES), f"measurement.sides must be {list(SIDES)}")
    policy = measurement.get("execution_policy")
    require(isinstance(policy, dict), "measurement.execution_policy is required")
    arithmetic = policy.get("arithmetic")
    require(isinstance(arithmetic, dict) and arithmetic.get("format") == "IEEE-754 binary64"
            and arithmetic.get("validated_arithmetic") is False,
            "execution arithmetic policy must describe unvalidated binary64")
    seed = policy.get("seed")
    require(isinstance(seed, dict) and seed.get("status") in ("not_applicable", "fixed", "unavailable")
            and isinstance(seed.get("reason"), str) and seed["reason"],
            "seed policy and its reason are required")
    requested = policy.get("requested")
    require(isinstance(requested, dict) and requested.get("resource_context") == {
        "total_threads": 1, "outer_workers": 1, "threads_per_worker": 1},
        "requested resource context differs from the measured driver")
    profiles = requested.get("solver_profiles", {})
    require(profiles.get("phase-one-bland") == {
        "native_threads": "not_applicable", "reason": "single-threaded in-process implementation"}
        and profiles.get("highs-reference") == {
            "solver": "simplex", "presolve": "off", "parallel": "off", "native_threads": 1},
        "requested solver profiles differ from the measured adapters")
    actual = policy.get("actual")
    require(isinstance(actual, dict), "actual execution resource observations are required")
    for name in ("outer_workers", "native_threads"):
        observation = actual.get(name)
        require(isinstance(observation, dict) and (observation.get("value") is None
                or isinstance(observation.get("value"), int) and not isinstance(observation.get("value"), bool)
                and observation["value"] > 0)
                and isinstance(observation.get("reason"), str) and observation["reason"],
                f"actual {name} count must be observed or explicitly unavailable")
    boundaries = measurement.get("timing_boundaries")
    require(isinstance(boundaries, dict) and all(isinstance(boundaries.get(p), str) and boundaries[p] for p in PHASES),
            "all four timing boundaries are required")
    trials, warmups = records.get("trials"), records.get("warmup_trials")
    require(isinstance(trials, list) and isinstance(warmups, list), "trials and warmup_trials must be lists")
    by_key: dict[tuple[str, str, int], dict] = {}
    warmup_keys: set[tuple[str, str]] = set()
    for is_warmup, trial_list in ((True, warmups), (False, trials)):
        for index, trial in enumerate(trial_list):
            label = f"{'warmup' if is_warmup else 'trial'}[{index}]"
            require(isinstance(trial, dict), f"{label} must be an object")
            fid, side = trial.get("fixture"), trial.get("side")
            require(fid in fixtures and side in SIDES, f"{label}: unknown fixture or side")
            rep = trial.get("repetition")
            require(isinstance(rep, int) and not isinstance(rep, bool), f"{label}: repetition must be integer")
            if is_warmup:
                require(rep == 0, f"{label}: warmup repetition must be 0")
                wk = (fid, side)
                require(wk not in warmup_keys, f"duplicate warmup {wk}")
                warmup_keys.add(wk)
            else:
                require(0 <= rep <= 6, f"{label}: measured repetition must be 0..6")
                key = (fid, side, rep)
                require(key not in by_key, f"duplicate measured trial {key}")
                by_key[key] = trial
            fixture = fixtures[fid]
            require(trial.get("expected_status") == fixture["expected_status"], f"{label}: expected_status differs from fixture")
            require(trial.get("status") in ("passed", "failed"), f"{label}: invalid trial status")
            require(isinstance(trial.get("error"), (str, type(None))), f"{label}: error must be string or null")
            require(isinstance(trial.get("work_observed"), bool), f"{label}: work_observed must be boolean")
            checks = trial.get("oracle_checks")
            require(isinstance(checks, list) and all(isinstance(c, dict) and isinstance(c.get("name"), str)
                    and c["name"] and isinstance(c.get("passed"), bool) for c in checks), f"{label}: invalid oracle_checks")
            names = [c["name"] for c in checks]
            require(len(names) == len(set(names)), f"{label}: duplicate oracle check name")
            durations = trial.get("durations_ns")
            require(isinstance(durations, dict) and set(durations) == set(PHASES), f"{label}: incomplete durations_ns")
            for phase in PHASES:
                if durations[phase] is None and trial["status"] == "failed":
                    continue
                nonnegative_ns(durations[phase], f"{label}.durations_ns.{phase}")
            tolerance = trial.get("tolerances")
            require(isinstance(tolerance, dict), f"{label}: tolerances missing")
            absolute = finite_number(tolerance.get("absolute"), f"{label}.tolerances.absolute")
            relative = finite_number(tolerance.get("relative"), f"{label}.tolerances.relative")
            require(absolute == fixture["absolute_tolerance"] and relative == fixture["relative_tolerance"],
                    f"{label}: tolerance differs from catalog")
            result = trial.get("result")
            require(isinstance(result, dict) and isinstance(result.get("termination"), str)
                    and isinstance(result.get("outcome"), str), f"{label}: missing result classification")
            require(trial.get("observed_status") == result["outcome"], f"{label}: observed_status differs from result")
            actual_input = trial.get("input")
            if actual_input is None:
                require(trial["status"] == "failed" and trial.get("input_sha256") is None
                        and trial.get("scenario_sha256") is None,
                        f"{label}: successful trial has no actual input identity")
            else:
                require(isinstance(actual_input, dict), f"{label}: actual input must be an object or unavailable")
                require(set(actual_input) == {"matrix", "rhs", "row_relation", "variable_lower_bound",
                        "variable_upper_bound", "objective_coefficients", "objective_constant"},
                        f"{label}: actual input fields differ from the schema")
                actual_matrix, actual_rhs = actual_input.get("matrix"), actual_input.get("rhs")
                require(isinstance(actual_matrix, list) and len(actual_matrix) == fixture["rows"]
                        and all(isinstance(row, list) and len(row) == fixture["columns"] for row in actual_matrix)
                        and isinstance(actual_rhs, list) and len(actual_rhs) == fixture["rows"],
                        f"{label}: actual input dimensions differ")
                for row_values in actual_matrix:
                    for value in row_values:
                        finite_number(value, f"{label}.input.matrix")
                for value in actual_rhs:
                    finite_number(value, f"{label}.input.rhs")
                coefficients = actual_input.get("objective_coefficients")
                require(isinstance(coefficients, list) and len(coefficients) == fixture["columns"],
                        f"{label}: actual objective coefficient count differs")
                for value in coefficients:
                    finite_number(value, f"{label}.input.objective_coefficients")
                finite_number(actual_input.get("objective_constant"), f"{label}.input.objective_constant")
                for bound in (actual_input.get("variable_lower_bound"), actual_input.get("variable_upper_bound")):
                    if bound is not None:
                        finite_number(bound, f"{label}.input.variable_bound")
                actual_input_hash = canonical_sha256({
                    "matrix": [[float(value) for value in row] for row in actual_matrix],
                    "rhs": [float(value) for value in actual_rhs],
                })
                actual_scenario = {"input_sha256": actual_input_hash,
                    "row_relation": actual_input.get("row_relation"),
                    "variable_lower_bound": actual_input.get("variable_lower_bound"),
                    "variable_upper_bound": actual_input.get("variable_upper_bound"),
                    "objective": {"coefficients": [float(value) for value in actual_input.get("objective_coefficients", [])],
                                  "constant": float(actual_input.get("objective_constant"))},
                    "tolerances": {"absolute": fixture["absolute_tolerance"], "relative": fixture["relative_tolerance"]}}
                actual_scenario_hash = canonical_sha256(actual_scenario)
                require(trial.get("input_sha256") == actual_input_hash
                        and trial.get("scenario_sha256") == actual_scenario_hash,
                        f"{label}: trial hashes do not match driver-emitted input")
                if trial["status"] == "passed":
                    expected_input = {"matrix": fixture["matrix"], "rhs": fixture["rhs"],
                        "row_relation": "equality", "variable_lower_bound": 0.0,
                        "variable_upper_bound": None, "objective_coefficients": [0.0] * fixture["columns"],
                        "objective_constant": 0.0}
                    require(actual_input == expected_input and actual_input_hash == fixture["input_sha256"]
                            and actual_scenario_hash == fixture["scenario_sha256"],
                            f"{label}: successful trial input differs from catalog")
            expected_outcome = fixture["expected_status"] if side == "phase-one-bland" else fixture["expected_reference_status"]
            expected_match = result["termination"] == "completed" and trial["observed_status"] == expected_outcome and bool(checks) and all(c["passed"] for c in checks)
            require(trial.get("oracle_match") is expected_match, f"{label}: oracle_match contradicts literal outcome/checks")
            require(trial["status"] == ("passed" if expected_match else "failed"), f"{label}: status contradicts oracle_match")
            if side == "phase-one-bland":
                residual_names = ("original_rows_max_violation", "nonnegative_max_violation", "objective_value", "auxiliary_residual", "auxiliary_value")
                residuals = {}
                for field in residual_names:
                    value = trial.get(field)
                    if value is None and not expected_match:
                        residuals[field] = None
                    else:
                        residuals[field] = finite_number(value, f"{label}.{field}")
                        require(residuals[field] >= 0 or field == "objective_value", f"{label}.{field} must be nonnegative")
                if expected_match:
                    limit = absolute + relative
                    primal = result.get("primal")
                    require(isinstance(primal, list) and len(primal) == fixture["columns"],
                            f"{label}: missing phase-I primal")
                    require(actual_input is not None, f"{label}: successful phase-I row has no actual input")
                    recomputed = _primal_residuals(actual_input, primal, label)
                    for field, key in (("original_rows_max_violation", "original_equalities"),
                                       ("nonnegative_max_violation", "nonnegative_variables"),
                                       ("objective_value", "zero_original_objective")):
                        require(abs(residuals[field] - recomputed[key]) <= limit,
                                f"{label}: saved {field} differs from recomputed phase-I witness")
                    require(residuals["nonnegative_max_violation"] <= limit
                            and residuals["objective_value"] <= limit
                            and residuals["auxiliary_residual"] <= limit,
                            f"{label}: nonnegativity, objective, or auxiliary residual exceeds authored tolerance")
                    require(abs(residuals["auxiliary_value"] - fixture["expected_auxiliary"]) <= limit,
                            f"{label}: auxiliary value differs from literal oracle")
                    if fixture["expected_status"] == "optimal":
                        require(residuals["original_rows_max_violation"] <= limit,
                                f"{label}: feasible phase-I witness residual exceeds authored tolerance")
                        expected_primal = fixture["expected_phase_one_primal"]
                        require(len(primal) == len(expected_primal), f"{label}: phase-I primal dimension differs from oracle")
                        require(all(abs(finite_number(a, f"{label}.primal") - b) <= limit
                                    for a, b in zip(primal, expected_primal)), f"{label}: phase-I primal differs from oracle")
                    if fixture["expected_status"] == "infeasible":
                        require(residuals["original_rows_max_violation"] > limit,
                                f"{label}: infeasible phase-I witness unexpectedly satisfies the original equalities")
                        require(residuals["auxiliary_value"] > limit, f"{label}: infeasible auxiliary must be positive")
            else:
                for field in ("original_rows_max_violation", "nonnegative_max_violation", "objective_value", "auxiliary_residual", "auxiliary_value"):
                    require(trial.get(field) is None, f"{label}: reference row contains phase-I-only {field}")
                if trial["status"] == "passed" and fixture["expected_reference_status"] == "optimal":
                    primal = result.get("primal")
                    require(isinstance(primal, list) and len(primal) == fixture["columns"],
                            f"{label}: successful HiGHS result has no primal witness")
                    require(actual_input is not None and actual_input.get("row_relation") == "equality",
                            f"{label}: successful HiGHS result has no supported input semantics")
                    residuals = _primal_residuals(actual_input, primal, label)
                    limit = absolute + relative
                    recomputed = {name: value <= limit for name, value in residuals.items()}
                    recorded = {check["name"]: check["passed"] for check in checks}
                    for name, passed in recomputed.items():
                        require(recorded.get(name) is passed,
                                f"{label}: HiGHS witness {name} check contradicts recomputed residual")
                    witness_passed = all(recomputed.values())
                    require(recorded.get("independent_feasible_witness") is witness_passed,
                            f"{label}: HiGHS witness check contradicts recomputed residuals")
            paired = trial.get("paired_outcomes")
            require(paired is None or (isinstance(paired, dict) and set(paired) == {"phase_one", "highs_reference"}),
                    f"{label}: malformed paired_outcomes")

    expected_warmups = len(fixtures) * len(SIDES)
    expected_trials = expected_warmups * 7
    missing_count = max(0, expected_warmups - len(warmups)) + max(0, expected_trials - len(trials))
    complete = len(warmups) == expected_warmups and len(trials) == expected_trials and len(warmup_keys) == expected_warmups and len(by_key) == expected_trials
    if complete:
        require(set(by_key) == {(fid, side, rep) for fid in fixtures for side in SIDES for rep in range(7)},
                "incomplete measured seven-trial group")
        require(warmup_keys == {(fid, side) for fid in fixtures for side in SIDES}, "incomplete warmup groups")

    pair_groups: dict[tuple[str, int, str], list[dict]] = {}
    for row in [*warmups, *trials]:
        pair_id = row.get("pair_id")
        require(isinstance(pair_id, str) and pair_id, "trial pair_id is required")
        pair_groups.setdefault((row["fixture"], row["repetition"], pair_id), []).append(row)
    for key, pair in pair_groups.items():
        sides_in_pair = [row["side"] for row in pair]
        require(len(sides_in_pair) <= 2 and len(set(sides_in_pair)) == len(sides_in_pair), f"duplicate side in pair {key}")
        if len(pair) != 2:
            require(not any(row.get("paired_outcomes") is not None for row in pair), f"orphan pair {key} has unsupported paired outcomes")
            continue
        left = next(row for row in pair if row["side"] == "phase-one-bland")
        right = next(row for row in pair if row["side"] == "highs-reference")
        paired = left.get("paired_outcomes")
        require(paired is not None and paired == right.get("paired_outcomes"), f"pair {key} paired outcomes differ")
        require(left.get("reference_status") == right.get("observed_status")
                and right.get("reference_status") == left.get("observed_status"), f"pair {key} reference status differs")
        require(left["observed_status"] == paired["phase_one"]["status"]
                and right["observed_status"] == paired["highs_reference"]["status"], f"pair {key} outcome copy differs")

    schedule = measurement.get("execution_order")
    require(isinstance(schedule, list), "measurement.execution_order must be a list")
    scheduled: dict[tuple[str, str, int], int] = {}
    for round_entry in schedule:
        require(isinstance(round_entry, dict) and isinstance(round_entry.get("repetition"), int)
                and isinstance(round_entry.get("sequence"), list), "invalid grouped execution-order row")
        rep = round_entry["repetition"]
        require(0 <= rep <= 6, "execution-order repetition must be 0..6")
        for order_index, item in enumerate(round_entry["sequence"]):
            require(isinstance(item, dict) and item.get("order_index") == order_index,
                    "execution-order indices must be contiguous within each repetition")
            fid, side = item.get("fixture"), item.get("side")
            require(fid in fixtures and side in SIDES, "execution-order entry has unknown fixture or side")
            key = (fid, side, rep)
            require(key not in scheduled, f"duplicate execution-order entry {key}")
            scheduled[key] = order_index
    require(set(scheduled) == set(by_key), "execution order differs from saved measured rows")
    ordinals = [row.get("sequence") for row in [*warmups, *trials]]
    require(all(isinstance(n, int) and not isinstance(n, bool) for n in ordinals)
            and len(set(ordinals)) == len(ordinals), "trial sequence ordinals must be globally unique integers")
    if complete:
        require(sorted(ordinals) == list(range(len(ordinals))), "complete report sequence ordinals must be contiguous")
        actual_order = [(key, row["sequence"]) for key, row in by_key.items()]
        ordered_by_schedule = [key for key, _ in sorted(scheduled.items(), key=lambda item: (item[0][2], item[1]))]
        ordered_by_sequence = [key for key, _ in sorted(actual_order, key=lambda item: item[1])]
        require(ordered_by_schedule == ordered_by_sequence, "grouped execution order differs from trial sequence ordinals")
        for rep in range(7):
            round_record = next(item for item in schedule if item["repetition"] == rep)
            round_entries = sorted(round_record["sequence"], key=lambda item: item["order_index"])
            observed_fixture_order = list(dict.fromkeys(item["fixture"] for item in round_entries))
            expected_fixture_order = list(fixtures) if rep % 2 == 0 else list(reversed(fixtures))
            require(observed_fixture_order == expected_fixture_order,
                    f"repetition {rep}: fixture traversal did not alternate")
            for fixture_index, fid in enumerate(fixtures):
                ordered = sorted(((scheduled[(fid, side, rep)], side) for side in SIDES))
                first_expected = "phase-one-bland" if (rep + fixture_index) % 2 == 0 else "highs-reference"
                require(ordered[0][1] == first_expected, f"{fid} repetition {rep}: side order did not alternate")

    summary = records.get("summary")
    require(isinstance(summary, dict) and isinstance(summary.get("rows"), list), "summary.rows must be a list")
    failures = sum(row.get("status") != "passed" or row.get("oracle_match") is not True for row in [*trials, *warmups])
    errors = records.get("collection_errors")
    require(isinstance(errors, list) and all(isinstance(e, str) for e in errors), "collection_errors must be a list of strings")
    exit_code = records.get("process_exit_code")
    require(isinstance(exit_code, int) and not isinstance(exit_code, bool), "process_exit_code must be an integer")
    aborted = records.get("aborted")
    require(isinstance(aborted, bool), "aborted must be boolean")
    valid = complete and failures == 0 and missing_count == 0 and not errors and exit_code == 0 and not aborted
    require(summary.get("valid") is valid, "summary.valid does not match saved evidence")
    require(summary.get("missing_count") == missing_count, "summary.missing_count mismatch")
    require(summary.get("failure_count") == failures, "summary.failure_count mismatch")
    expected_summary = []
    for fid in fixtures:
        for side in SIDES:
            subset = [row for row in trials if row["fixture"] == fid and row["side"] == side]
            for phase in PHASES:
                values = [row["durations_ns"][phase] for row in subset
                          if isinstance(row["durations_ns"][phase], int) and not isinstance(row["durations_ns"][phase], bool)]
                expected_summary.append({"fixture": fid, "side": side, "phase": phase,
                    "median_ns": sorted(values)[len(values)//2] if valid else None,
                    "min_ns": min(values) if valid else None,
                    "max_ns": max(values) if valid else None,
                    "count": len(values)})
    actual_rows = summary["rows"]
    require(len(actual_rows) == len(expected_summary), "summary row inventory mismatch")
    for actual, expected in zip(actual_rows, expected_summary):
        require(actual == expected, f"summary row mismatch for {expected['fixture']}/{expected['side']}/{expected['phase']}")
    provenance = records.get("provenance")
    require(isinstance(provenance, dict), "provenance is required")
    for name in ("source_commit", "harness_commit"):
        require(isinstance(provenance.get(name), str) and re.fullmatch(r"[0-9a-fA-F]{40,64}", provenance[name]),
                f"provenance.{name} must be a full commit hash")
    for name in ("executable_sha256", "cmake_cache_sha256", "release_build_sha256"):
        require(isinstance(provenance.get(name), str) and re.fullmatch(r"[0-9a-f]{64}", provenance[name]),
                f"provenance.{name} must be a SHA-256 digest")
    require(isinstance(provenance.get("release_build_command"), list)
            and "--clean-first" in provenance["release_build_command"]
            and "Release" in provenance["release_build_command"], "clean Release rebuild command is required")
    require(provenance.get("cxx_standard") == 20 and provenance.get("release_ndebug") is True,
            "C++20 Release/NDEBUG build identity is required")
    for name in ("compiler_id", "compiler_version", "cmake_generator"):
        require(isinstance(provenance.get(name), str) and provenance[name], f"provenance.{name} is required")
    require(isinstance(provenance.get("release_flags"), str) and "NDEBUG" in provenance["release_flags"].upper(),
            "Release flags must record NDEBUG")
    logical_processors = provenance.get("logical_processors")
    require(logical_processors is None or isinstance(logical_processors, int) and not isinstance(logical_processors, bool)
            and logical_processors > 0, "logical_processors must be a positive integer or unavailable")
    return records


def report_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()
                  and p.relative_to(root).as_posix() not in PACKAGE_NAMES
                  and "__pycache__" not in p.parts and p.suffix != ".pyc")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_manifest(root: Path, files: list[Path]) -> bytes:
    return "".join(f"{sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}\n"
                   for path in files).encode("ascii")


def validate_package(root: Path, files: list[Path]) -> None:
    manifest_path = root / "manifest.sha256"
    require(manifest_path.read_bytes() == expected_manifest(root, files),
            "manifest.sha256 inventory or file hash mismatch")
    archive_path = root / "bundle.zip"
    sidecar = root / "bundle.zip.sha256"
    require(sidecar.read_bytes() == f"{sha256(archive_path.read_bytes())}  bundle.zip\n".encode("ascii"),
            "bundle.zip.sha256 mismatch")
    expected = {f"{root.name}/{p.relative_to(root).as_posix()}": p.read_bytes() for p in [*files, manifest_path]}
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "bundle.zip contains duplicate paths")
        require(set(names) == set(expected), "bundle.zip inventory mismatch")
        for name in names:
            require(".." not in Path(name).parts, f"escaping path in bundle: {name}")
            info = archive.getinfo(name)
            require(info.date_time == (1980, 1, 1, 0, 0, 0)
                    and info.compress_type == zipfile.ZIP_DEFLATED
                    and info.external_attr == 0o100644 << 16,
                    f"bundle.zip metadata mismatch: {name}")
            require(archive.read(name) == expected[name], f"bundle.zip bytes differ: {name}")


def validate_report(root: Path) -> dict:
    records_path = root / "records.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    validate_records(records)
    build_log = root / "release-build.txt"
    require(build_log.is_file() and hashlib.sha256(build_log.read_bytes()).hexdigest()
            == records["provenance"]["release_build_sha256"], "retained Release build log digest mismatch")
    spec = importlib.util.spec_from_file_location("opt04_render_for_validation", Path(__file__).with_name("render.py"))
    renderer = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(renderer)
    with tempfile.TemporaryDirectory(prefix="opt04-render-check-") as temporary:
        temp = Path(temporary)
        renderer.render_report(records, temp)
        for name in ("index.html", "performance.svg"):
            require((root / name).read_bytes() == (temp / name).read_bytes(),
                    f"{name} is not reproducible from saved records")
    files = report_files(root)
    validate_package(root, files)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="directory containing saved records and report bundle")
    args = parser.parse_args()
    try:
        records = validate_report(args.report)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f"PASS: {len(records['trials'])} measured trials; schedule, oracle, timings, summary, HTML/SVG and ZIP verified")
    print(f"Report: {records['report_id']}; bundle SHA-256: {sha256((args.report / 'bundle.zip').read_bytes())}")


if __name__ == "__main__":
    main()

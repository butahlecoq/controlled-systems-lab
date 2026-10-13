#!/usr/bin/env python3
"""Tests for OPT-04 saved-record rendering and report validation."""
from __future__ import annotations

import html
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render = _load("opt04_render", "render.py")
validate = _load("opt04_validate", "validate_report.py")


def fixture_records() -> dict:
    sides = ["phase-one-bland", "highs-reference"]
    matrix, rhs = [[1.0, 0.0], [0.0, 1.0]], [1.0, 1.0]
    normalized_inputs = {"matrix": [[float(value) for value in row] for row in matrix],
                         "rhs": [float(value) for value in rhs]}
    input_sha256 = hashlib.sha256(json.dumps(normalized_inputs, sort_keys=True,
                                            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    driver_input = {"matrix": [list(row) for row in matrix], "rhs": list(rhs),
                "row_relation": "equality", "variable_lower_bound": 0.0,
                "variable_upper_bound": None,
                "objective_coefficients": [0.0, 0.0], "objective_constant": 0.0}
    scenario = {"input_sha256": input_sha256, "row_relation": driver_input["row_relation"],
                "variable_lower_bound": driver_input["variable_lower_bound"],
                "variable_upper_bound": driver_input["variable_upper_bound"],
                "objective": {"coefficients": driver_input["objective_coefficients"],
                              "constant": driver_input["objective_constant"]},
                "tolerances": {"absolute": 1e-8, "relative": 0.0}}
    scenario_sha256 = hashlib.sha256(json.dumps(scenario, sort_keys=True, separators=(",", ":"),
                                                allow_nan=False).encode()).hexdigest()
    record = {
        "schema": "csl.opt04-phase-one-report/2", "report_id": "opt04-fixture",
        "evidence_support": "Unestablished",
        "claims": {"scope": "paired descriptive analytic fixtures", "speedup": False,
                   "feasibility_numerics": "Unestablished"},
        "algorithm": {"registration_id": "phase-one-bland", "version": "1"},
        "reference": {"registration_id": "highs_lp", "version": "1.0.0+highs.1.11.0"},
        "catalog": {"version": "opt04-analytic-v1", "fixtures": [{
            "id": "tiny-feasible", "rows": 2, "columns": 2,
            "matrix": matrix, "rhs": rhs, "input_sha256": input_sha256, "scenario_sha256": scenario_sha256,
            "expected_status": "optimal", "expected_phase_one_primal": [1.0, 1.0],
            "expected_auxiliary": 0.0, "expected_reference_status": "optimal",
            "absolute_tolerance": 1e-8, "relative_tolerance": 0.0,
        }]},
        "measurement": {"warmups_per_fixture": 1, "repetitions_per_fixture": 7,
                        "sides": sides,
                        "timing_boundaries": {"setup": "publication through fresh workspace",
                                              "public_run": "solver call", "verification": "oracle checks",
                                              "end_to_end": "fixture construction through verification"},
                        "execution_policy": {
                            "arithmetic": {"format": "IEEE-754 binary64", "validated_arithmetic": False,
                                           "rounding_mode": None, "rounding_mode_reason": "not observed"},
                            "seed": {"value": None, "status": "not_applicable", "reason": "deterministic test fixture"},
                            "requested": {
                                "resource_context": {"total_threads": 1, "outer_workers": 1, "threads_per_worker": 1},
                                "solver_profiles": {
                                    "phase-one-bland": {"native_threads": "not_applicable", "reason": "single-threaded in-process implementation"},
                                    "highs-reference": {"solver": "simplex", "presolve": "off", "parallel": "off", "native_threads": 1},
                                },
                            },
                            "actual": {"outer_workers": {"value": None, "reason": "not observed"},
                                       "native_threads": {"value": None, "reason": "not observed"}},
                        },
                        "execution_order": []},
        "warmup_trials": [], "trials": [], "summary": {"failure_count": 0, "missing_count": 0, "valid": True, "rows": []},
        "provenance": {"source_commit": "a" * 40, "harness_commit": "b" * 40,
                       "executable_sha256": "c" * 64, "cmake_cache_sha256": "d" * 64,
                       "release_build_sha256": hashlib.sha256(b"test Release build\n").hexdigest(),
                       "release_build_command": ["cmake", "--config", "Release", "--clean-first"],
                       "compiler_id": "TestCC", "compiler_version": "1.0", "cxx_standard": 20,
                       "release_ndebug": True, "cmake_generator": "Test Generator", "release_flags": "-DNDEBUG",
                       "logical_processors": 4,
                       "build_directory": "BUILD_ROOT", "executable_path": "BUILD_ROOT/test.exe",
                       "host_platform": "test", "processor": "test", "python": "3.x",
                       "concurrent_work": "none", "limiter_profile": "not measured"},
        "collection_errors": [], "process_exit_code": 0, "aborted": False,
    }

    def make_trial(side: str, repetition: int, sequence: int, pair: str) -> dict:
        result = {"termination": "completed", "outcome": "optimal", "primal": [1.0, 1.0],
                  "auxiliary": 0.0, "pivots": repetition, "degenerate_pivots": 0, "factorizations": 1}
        data = {
            "fixture": "tiny-feasible", "side": side, "repetition": repetition,
            "sequence": sequence, "pair_id": pair, "status": "passed", "error": None,
            "expected_status": "optimal", "observed_status": "optimal", "reference_status": "optimal",
            "oracle_match": True,
            "oracle_checks": [{"name": name, "passed": True} for name in (
                ("expected_status", "literal_expected_candidate", "original_equalities",
                 "nonnegative_variables", "zero_original_objective", "literal_auxiliary_value")
                if side == "phase-one-bland" else
                ("expected_status", "independent_feasible_witness", "original_equalities",
                 "nonnegative_variables", "zero_original_objective"))],
            "work_observed": True, "input": driver_input,
            "input_sha256": input_sha256, "scenario_sha256": scenario_sha256,
            "tolerances": {"absolute": 1e-8, "relative": 0.0},
            "original_rows_max_violation": 0.0, "nonnegative_max_violation": 0.0,
            "objective_value": 0.0, "auxiliary_residual": 0.0, "auxiliary_value": 0.0,
            "durations_ns": {"setup": 10, "public_run": 100 * (repetition + 1),
                             "verification": 20, "end_to_end": 130 * (repetition + 1)},
            "result": result,
            "paired_outcomes": {
                "phase_one": {"status": "optimal", "termination": "completed", "primal": [1.0, 1.0], "auxiliary": 0.0},
                "highs_reference": {"status": "optimal", "termination": "completed", "primal": [1.0, 1.0]},
            },
        }
        if side == "highs-reference":
            data["original_rows_max_violation"] = None
            data["nonnegative_max_violation"] = None
            data["objective_value"] = None
            data["auxiliary_residual"] = None
            data["auxiliary_value"] = None
            result.update({"auxiliary": None, "pivots": None, "degenerate_pivots": None, "factorizations": None})
        return data

    sequence = 0
    for side in sides:
        record["warmup_trials"].append(make_trial(side, 0, sequence, "tiny-feasible-warmup"))
        sequence += 1
    for repetition in range(7):
        order = sides if repetition % 2 == 0 else list(reversed(sides))
        for side in order:
            if not record["measurement"]["execution_order"] or record["measurement"]["execution_order"][-1]["repetition"] != repetition:
                record["measurement"]["execution_order"].append({"repetition": repetition, "sequence": []})
            round_sequence = record["measurement"]["execution_order"][-1]["sequence"]
            round_sequence.append({"fixture": "tiny-feasible", "side": side, "order_index": len(round_sequence)})
            record["trials"].append(make_trial(side, repetition, sequence, f"tiny-feasible-{repetition}"))
            sequence += 1
    for side in sides:
        for phase in ("setup", "public_run", "verification", "end_to_end"):
            values = [t["durations_ns"][phase] for t in record["trials"] if t["side"] == side]
            record["summary"]["rows"].append({"fixture": "tiny-feasible", "side": side,
                "phase": phase, "median_ns": sorted(values)[3], "min_ns": min(values),
                "max_ns": max(values), "count": 7})
    return record


def write_report(path: Path, records: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    (path / "release-build.txt").write_bytes(b"test Release build\n")
    render.render_report(records, path)


class ReportToolsTests(unittest.TestCase):
    def test_valid_saved_record_and_render_are_consistent(self) -> None:
        records = fixture_records()
        validate.validate_records(records)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report"
            write_report(path, records)
            validate.validate_report(path)
            before = {name: (path / name).read_bytes() for name in
                      ("manifest.sha256", "bundle.zip", "bundle.zip.sha256")}
            render.render_report(records, path)
            self.assertEqual(before, {name: (path / name).read_bytes() for name in before})
            self.assertIn("opt04-fixture", (path / "index.html").read_text(encoding="utf-8"))
            self.assertIn("phase-one-bland", (path / "performance.svg").read_text(encoding="utf-8"))

    def test_accepts_checked_infeasible_phase_one_witness_with_positive_original_residual(self) -> None:
        records = fixture_records()
        fixture = records["catalog"]["fixtures"][0]
        matrix, rhs = [[1.0, 0.0], [1.0, 0.0]], [0.0, 1.0]
        fixture["id"] = "tiny-infeasible"
        fixture["matrix"], fixture["rhs"] = matrix, rhs
        fixture["expected_status"] = fixture["expected_reference_status"] = "infeasible"
        fixture["expected_phase_one_primal"], fixture["expected_auxiliary"] = [0.0, 0.0], 1.0
        input_sha256 = hashlib.sha256(json.dumps({"matrix": matrix, "rhs": rhs}, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        fixture["input_sha256"] = input_sha256
        scenario = {"input_sha256": input_sha256, "row_relation": "equality",
            "variable_lower_bound": 0.0, "variable_upper_bound": None,
            "objective": {"coefficients": [0.0, 0.0], "constant": 0.0},
            "tolerances": {"absolute": 1e-8, "relative": 0.0}}
        fixture["scenario_sha256"] = hashlib.sha256(json.dumps(scenario, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        driver_input = {"matrix": matrix, "rhs": rhs, "row_relation": "equality",
            "variable_lower_bound": 0.0, "variable_upper_bound": None,
            "objective_coefficients": [0.0, 0.0], "objective_constant": 0.0}
        for trial in [*records["warmup_trials"], *records["trials"]]:
            trial["fixture"] = fixture["id"]
            trial["expected_status"] = trial["observed_status"] = "infeasible"
            trial["reference_status"] = "infeasible"
            trial["input"] = driver_input
            trial["input_sha256"] = input_sha256
            trial["scenario_sha256"] = fixture["scenario_sha256"]
            phase_one = trial["side"] == "phase-one-bland"
            trial["result"].update({"outcome": "infeasible",
                "primal": [0.0, 0.0] if phase_one else [0.0, 1.0],
                "auxiliary": 1.0 if phase_one else None})
            trial["original_rows_max_violation"] = 1.0 if phase_one else None
            trial["nonnegative_max_violation"] = 0.0 if phase_one else None
            trial["objective_value"] = 0.0 if phase_one else None
            trial["auxiliary_residual"] = 0.0 if phase_one else None
            trial["auxiliary_value"] = 1.0 if phase_one else None
            names = ("expected_status", "literal_auxiliary_value") if phase_one else ("expected_status",)
            trial["oracle_checks"] = [{"name": name, "passed": True} for name in names]
            trial["paired_outcomes"] = {
                "phase_one": {"status": "infeasible", "termination": "completed",
                              "primal": [0.0, 0.0], "auxiliary": 1.0},
                "highs_reference": {"status": "infeasible", "termination": "completed",
                                    "primal": [0.0, 1.0]},
            }
        for round_entry in records["measurement"]["execution_order"]:
            for entry in round_entry["sequence"]:
                entry["fixture"] = fixture["id"]
        for row in records["summary"]["rows"]:
            row["fixture"] = fixture["id"]

        validate.validate_records(records)
        corrupted = json.loads(json.dumps(records))
        corrupted["warmup_trials"][0]["original_rows_max_violation"] = 0.0
        with self.assertRaisesRegex(ValueError, "recomputed phase-I witness"):
            validate.validate_records(corrupted)

    def test_rejects_corrupt_literal_outcome_and_summary_count(self) -> None:
        records = fixture_records()
        row = records["trials"][0]
        row["observed_status"] = "infeasible"
        row["result"]["outcome"] = "infeasible"
        with self.assertRaises(ValueError):
            validate.validate_records(records)
        records = fixture_records()
        records["summary"]["rows"][0]["count"] = 6
        with self.assertRaises(ValueError):
            validate.validate_records(records)

    def test_recomputes_highs_witness_residuals_from_saved_input(self) -> None:
        records = fixture_records()
        row = next(row for row in records["trials"] if row["side"] == "highs-reference")
        row["result"]["primal"] = [2.0, 1.0]
        row["paired_outcomes"]["highs_reference"]["primal"] = [2.0, 1.0]
        paired_phase = next(candidate for candidate in records["trials"]
                            if candidate["side"] == "phase-one-bland" and candidate["pair_id"] == row["pair_id"])
        paired_phase["paired_outcomes"]["highs_reference"]["primal"] = [2.0, 1.0]
        with self.assertRaisesRegex(ValueError, "reference.*residual|HiGHS.*residual|witness"):
            validate.validate_records(records)

    def test_rejects_fixture_hash_mismatch_and_missing_execution_policy(self) -> None:
        records = fixture_records()
        records["catalog"]["fixtures"][0]["matrix"][0][0] = 2.0
        with self.assertRaisesRegex(ValueError, "input hash"):
            validate.validate_records(records)
        records = fixture_records()
        del records["measurement"]["execution_policy"]
        with self.assertRaisesRegex(ValueError, "execution_policy"):
            validate.validate_records(records)
        records = fixture_records()
        records["trials"][0]["input"]["rhs"][0] = 0.5
        with self.assertRaisesRegex(ValueError, "trial hashes do not match"):
            validate.validate_records(records)
    def test_rejects_corrupt_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report"
            write_report(path, fixture_records())
            (path / "manifest.sha256").write_text("0" * 64 + "  records.json\n", encoding="ascii")
            with self.assertRaises(ValueError):
                validate.validate_report(path)

    def test_rejects_corrupt_bundle_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report"
            write_report(path, fixture_records())
            bundle = path / "bundle.zip"
            bundle.write_bytes(bundle.read_bytes() + b"corruption")
            with self.assertRaises(ValueError):
                validate.validate_report(path)

    def test_failed_and_missing_attempts_remain_explicit_and_ineligible(self) -> None:
        records = fixture_records()
        failed = records["trials"][0]
        failed["status"] = "failed"
        failed["oracle_match"] = False
        failed["oracle_checks"][0]["passed"] = False
        failed["input"] = None
        failed["input_sha256"] = None
        failed["scenario_sha256"] = None
        records["trials"].pop()
        orphan = records["trials"][-1]
        orphan["paired_outcomes"] = None
        orphan["reference_status"] = None
        records["measurement"]["execution_order"][-1]["sequence"].pop()
        records["summary"]["valid"] = False
        records["summary"]["failure_count"] = 1
        records["summary"]["missing_count"] = 1
        records["process_exit_code"] = 2
        records["collection_errors"] = ["one oracle failure", "one trial missing"]
        for row in records["summary"]["rows"]:
            row["median_ns"] = row["min_ns"] = row["max_ns"] = None
            if row["fixture"] == "tiny-feasible" and row["side"] == "highs-reference":
                row["count"] = 6
        validate.validate_records(records)
        page = render.page(records)
        self.assertIn("1 attempts failed and 1 expected attempts are missing", page)
        self.assertIn("ineligible", page)
        self.assertIn("one oracle failure", page)

    def test_aborted_collection_is_ineligible_even_with_complete_trial_rows(self) -> None:
        records = fixture_records()
        records["aborted"] = True
        records["summary"]["valid"] = False
        for row in records["summary"]["rows"]:
            row["median_ns"] = row["min_ns"] = row["max_ns"] = None

        validate.validate_records(records)
        page = render.page(records)
        self.assertIn("aborted: True", page)

    def test_html_hostile_content_is_escaped(self) -> None:
        records = fixture_records()
        records["trials"][0]["error"] = '<script>alert("x")</script>'
        records["trials"][0]["status"] = "failed"
        page = render.page(records)
        self.assertNotIn("<script>alert", page)
        self.assertIn(html.escape(records["trials"][0]["error"]), page)


if __name__ == "__main__":
    unittest.main()

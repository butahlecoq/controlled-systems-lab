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
    record = {
        "schema": "csl.opt04-phase-one-report/1", "report_id": "opt04-fixture",
        "evidence_support": "Unestablished",
        "claims": {"scope": "paired descriptive analytic fixtures", "speedup": False,
                   "feasibility_numerics": "Unestablished"},
        "algorithm": {"registration_id": "phase-one-bland", "version": "1"},
        "reference": {"registration_id": "highs_lp", "version": "1.0.0+highs.1.11.0"},
        "catalog": {"version": "opt04-analytic-v1", "fixtures": [{
            "id": "tiny-feasible", "rows": 2, "columns": 2,
            "matrix": [[1.0, 0.0], [0.0, 1.0]], "rhs": [1.0, 1.0],
            "expected_status": "optimal", "expected_phase_one_primal": [1.0, 1.0],
            "expected_auxiliary": 0.0, "expected_reference_status": "optimal",
            "absolute_tolerance": 1e-8, "relative_tolerance": 0.0,
        }]},
        "measurement": {"warmups_per_fixture": 1, "repetitions_per_fixture": 7,
                        "sides": sides,
                        "timing_boundaries": {"setup": "publication through fresh workspace",
                                              "public_run": "solver call", "verification": "oracle checks",
                                              "end_to_end": "fixture construction through verification"},
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
                "expected_status", "literal_expected_candidate", "original_equalities",
                "nonnegative_variables", "zero_original_objective", "literal_auxiliary_value")],
            "work_observed": True, "tolerances": {"absolute": 1e-8, "relative": 0.0},
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

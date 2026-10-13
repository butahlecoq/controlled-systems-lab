"""Saved SYN-01 numerical record validation and rendering tests."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import report as syn01


def event(scenario, repetition, bounds):
    return {
        "schema": syn01.EVENT_SCHEMA,
        "scenario": scenario,
        "repetition": repetition,
        "warmup": repetition == 0,
        "status": "passed",
        "outcome": "forward_tube",
        "expected_marginals": syn01.EXPECTED[scenario],
        "observed_marginals": bounds,
        "oracle_passed": True,
        "setup_ns": 100,
        "setup_state": "available",
        "solve_ns": 200,
        "solve_state": "available",
        "oracle_ns": 30,
        "oracle_state": "available",
        "execute_ns": 330,
        "execute_state": "available",
        "provider_identities": provider_ids(),
        "provider_operation_counts": {"csl.geometry.polyhedral-projection": 3,
                                       "csl.geometry.affine-sum": 6},
        "provider_operation_timing_ns": None,
        "detail": "",
    }


def valid_provenance(source="a" * 40):
    return {"algorithm_module": {"id": "csl.reachability.nominal-forward", "version": "0.1.0"},
            "providers": {name: {"id": name, "version": "1.0.0"} for name in (
                "projection", "affine_sum", "conversion", "lp_backend", "hull_reducer")},
            "dependency_edges": {"affine_sum": ["hull_reducer", "lp_backend", "conversion"],
                                 "conversion": ["lp_backend"]}}


def provider_ids():
    return valid_provenance()["providers"]


def complete_events():
    return [event(name, repetition, expected) for repetition in range(8)
            for name, expected in syn01.EXPECTED.items()]


class Syn01ReportTests(unittest.TestCase):
    def test_literal_analytic_marginals_and_exact_attempt_matrix_validate(self):
        trials = complete_events()
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertEqual({"measured": 14, "warmups": 2, "failures": 0, "missing_or_duplicate": 0},
                         record["collection"]["counts"])
        self.assertEqual(14, sum(row["attempts"] for row in record["summary"]))
        self.assertEqual([], syn01.validate_record(record))

    def test_changed_endpoint_fails_the_literal_h_bound_oracle(self):
        trials = complete_events()
        trials[1] = event("integrator", 0, [[0, 0], [0, 1], [0, 2.0000001]])
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertIn("literal_marginal_mismatch", syn01.validate_record(record))

    def test_driver_failure_is_preserved_and_excludes_timing_summary(self):
        trials = complete_events()
        trials[2] = {**trials[2], "status": "failed", "outcome": "driver_exception",
                     "oracle_passed": False, "detail": "synthetic test failure"}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertEqual("failed", record["collection"]["state"])
        self.assertEqual("synthetic test failure", record["trials"][2]["detail"])
        self.assertIsNone(record["summary"][0]["phases"]["execute_ns"]["median_ns"])

    def test_setup_failure_preserves_partial_setup_and_marks_later_phases_unreached(self):
        trials = complete_events()
        trials[0] = {**trials[0], "status": "failed", "outcome": "driver_exception",
                     "setup_ns": 42, "setup_state": "partial", "solve_ns": None,
                     "solve_state": "not_reached", "oracle_ns": None,
                     "oracle_state": "not_reached", "oracle_passed": False}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertEqual([], syn01.validate_record(record))
        self.assertEqual("partial", record["trials"][0]["setup_state"])
        self.assertIsNone(record["trials"][0]["solve_ns"])
        self.assertEqual("not_reached", record["trials"][0]["oracle_state"])

    def test_nominal_forward_failure_has_completed_solve_and_oracle_timings(self):
        trials = complete_events()
        trials[1] = {**trials[1], "status": "failed", "outcome": "operation_stopped_or_failed",
                     "oracle_passed": False, "detail": "typed provider failure"}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertEqual([], syn01.validate_record(record))
        self.assertEqual("available", record["trials"][1]["solve_state"])
        self.assertEqual("available", record["trials"][1]["oracle_state"])

    def test_provider_versions_are_required_and_visible_in_html(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        self.assertIn("1.0.0", syn01.render_html(record))
        record["provenance"]["providers"]["lp_backend"].pop("version")
        self.assertIn("provider_provenance_incomplete", syn01.validate_record(record))

    def test_saved_html_discloses_scope_and_support_limit(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        page = syn01.render_html(record)
        self.assertIn("complete 1-d h-row bounds over returned binary64 data", page.lower())
        self.assertIn("Unestablished", page)
        self.assertIn("no speedup", page.lower())
        self.assertNotIn("<script", page.lower())


if __name__ == "__main__":
    unittest.main()

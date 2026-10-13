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
        "solve_ns": 200,
        "oracle_ns": 30,
        "execute_ns": 330,
        "provider_operation_counts": {"csl.geometry.polyhedral-projection": 3,
                                       "csl.geometry.affine-sum": 6},
        "provider_operation_timing_ns": None,
        "detail": "",
    }


def complete_events():
    return [event(name, repetition, expected) for repetition in range(8)
            for name, expected in syn01.EXPECTED.items()]


class Syn01ReportTests(unittest.TestCase):
    def test_literal_analytic_marginals_and_exact_attempt_matrix_validate(self):
        trials = complete_events()
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance={})
        self.assertEqual({"measured": 14, "warmups": 2, "failures": 0, "missing_or_duplicate": 0},
                         record["collection"]["counts"])
        self.assertEqual(14, sum(row["attempts"] for row in record["summary"]))
        self.assertEqual([], syn01.validate_record(record))

    def test_changed_endpoint_fails_the_literal_h_bound_oracle(self):
        trials = complete_events()
        trials[1] = event("integrator", 0, [[0, 0], [0, 1], [0, 2.0000001]])
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance={})
        self.assertIn("literal_marginal_mismatch", syn01.validate_record(record))

    def test_driver_failure_is_preserved_and_excludes_timing_summary(self):
        trials = complete_events()
        trials[2] = {**trials[2], "status": "failed", "outcome": "driver_exception",
                     "oracle_passed": False, "detail": "synthetic test failure"}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance={})
        self.assertEqual("failed", record["collection"]["state"])
        self.assertEqual("synthetic test failure", record["trials"][2]["detail"])
        self.assertIsNone(record["summary"][0]["phases"]["execute_ns"]["median_ns"])

    def test_saved_html_discloses_scope_and_support_limit(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance={})
        page = syn01.render_html(record)
        self.assertIn("complete 1-d h-row bounds over returned binary64 data", page.lower())
        self.assertIn("Unestablished", page)
        self.assertIn("no speedup", page.lower())
        self.assertNotIn("<script", page.lower())


if __name__ == "__main__":
    unittest.main()

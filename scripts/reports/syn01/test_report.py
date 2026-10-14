"""Saved SYN-01 numerical record validation and rendering tests."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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
        "execution_settings": syn01.RUNTIME_SETTINGS,
        "provider_operation_counts": {"csl.geometry.polyhedral-projection": 3,
                                       "csl.geometry.affine-sum": 6},
        "provider_operation_timing_ns": None,
        "detail": "",
    }


def valid_provenance():
    return {"algorithm_module": {"id": "csl.reachability.nominal-forward", "version": "0.1.0"},
            "providers": {name: {"id": name, "version": "1.0.0"} for name in (
                "projection", "affine_sum", "conversion", "lp_backend", "hull_reducer")},
            "dependency_edges": {"affine_sum": ["hull_reducer", "lp_backend", "conversion"],
                                 "conversion": ["lp_backend"]},
            "runtime_settings": syn01.RUNTIME_SETTINGS,
            "native_thread_observation": {"status": "unavailable", "observed_threads": None,
                "reason": "The driver has no supported runtime API to observe effective native worker threads."},
            "build_configuration": {"configuration": "Release", "cxx_standard": "c++20",
                "generator": "Visual Studio 17 2022", "generator_platform": "x64",
                "compiler_id": "MSVC", "compiler_version": "19.44.35215.0", "compiler_executable": "cl.exe",
                "cmake_version": "3.31.6", "cmake_release_flags": "/O2 /Ob2 /DNDEBUG",
                "target_release_properties": {"LanguageStandard": "stdcpp20", "Optimization": "MaxSpeed"},
                "effective_release_flags": ["/std:c++20", "/O2", "/Ob2", "/DNDEBUG", "/W4", "/WX", "/permissive-"],
                "evidence_sha256": {"CMakeCache.txt": "a" * 64, "build_configuration_file": "b" * 64,
                                     "release_build_log": "c" * 64}}}


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
        self.assertIn("driver entry through verified result",
                      record["measurement"]["timing_scopes"]["execute_ns"])
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
        stats = record["summary"][0]["phases"]["execute_ns"]
        self.assertEqual(7, stats["available_trials"])
        self.assertEqual("complete", stats["coverage"])
        self.assertEqual(330, stats["median_ns"])

    def test_passed_trial_cannot_skip_solve_phase(self):
        trials = complete_events()
        trials[0] = {**trials[0], "solve_ns": None, "solve_state": "not_reached",
                     "oracle_ns": None, "oracle_state": "not_reached"}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        errors = syn01.validate_record(record)
        self.assertIn("invalid_phase_order_solve", errors)
        self.assertIn("passed_trial_phase_incomplete", errors)

    def test_failure_retains_completed_phase_summary_with_incomplete_coverage(self):
        trials = complete_events()
        trials[2] = {**trials[2], "status": "failed", "outcome": "driver_exception",
                     "oracle_passed": False, "provider_identities": {},
                     "setup_ns": 47, "setup_state": "partial", "solve_ns": None,
                     "solve_state": "not_reached", "oracle_ns": None,
                     "oracle_state": "not_reached", "detail": "setup failed"}
        record = syn01.make_record(trials, source_commit="a" * 40, harness_commit="b" * 40,
                                   environment={}, provenance=valid_provenance())
        self.assertEqual([], syn01.validate_record(record))
        setup = record["summary"][0]["phases"]["setup_ns"]
        self.assertEqual(6, setup["available_trials"])
        self.assertEqual(1, setup["partial_trials"])
        self.assertEqual("incomplete", setup["coverage"])
        self.assertEqual(100, setup["median_ns"])
        self.assertIn("incomplete coverage", syn01.render_html(record))
        solve = record["summary"][0]["phases"]["solve_ns"]
        self.assertEqual(6, solve["available_trials"])
        self.assertEqual(1, solve["not_reached_trials"])
        self.assertEqual("failed", record["collection"]["state"])

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

    def test_effective_numerical_backend_and_release_configuration_are_required_and_rendered(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        page = syn01.render_html(record)
        self.assertIn("absolute_tolerance", page)
        self.assertIn("1e-08", page)
        self.assertIn("c++20", page)
        self.assertIn("/O2 /Ob2 /DNDEBUG", page)
        del record["provenance"]["runtime_settings"]["highs"]["threads"]
        self.assertIn("effective_settings_incomplete", syn01.validate_record(record))

    def test_native_thread_observation_is_explicitly_unavailable_and_config_is_distinguished(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        page = syn01.render_html(record)
        self.assertIn("observed effective native threads: unavailable", page.lower())
        self.assertIn("requested workers: 1", page.lower())
        self.assertIn("configured native threads: 1", page.lower())
        record["provenance"]["native_thread_observation"]["observed_threads"] = 1
        self.assertIn("native_thread_observation_must_be_unavailable", syn01.validate_record(record))
        record["provenance"]["native_thread_observation"]["observed_threads"] = None
        record["measurement"]["requested_workers"] = 2
        self.assertIn("thread_configuration_must_be_one", syn01.validate_record(record))

    def test_execute_scope_must_include_driver_entry_configuration_time(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        record["measurement"]["timing_scopes"]["execute_ns"] = "setup through verification"
        self.assertIn("timing_scope_metadata_mismatch", syn01.validate_record(record))

    def test_saved_html_discloses_scope_and_support_limit(self):
        record = syn01.make_record(complete_events(), source_commit="a" * 40,
                                   harness_commit="b" * 40, environment={}, provenance=valid_provenance())
        page = syn01.render_html(record)
        self.assertIn("complete 1-d h-row bounds over returned binary64 data", page.lower())
        self.assertIn("Unestablished", page)
        self.assertIn("no speedup", page.lower())
        self.assertIn("Median execute interval (driver entry through verified result)", page)
        self.assertIn("direct stage-provider lineage and exclude nested LP/hull operations", page)
        self.assertNotIn("<script", page.lower())


if __name__ == "__main__":
    unittest.main()

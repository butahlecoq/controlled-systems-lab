"""Contract tests for GEO-05's versioned phase-one report harness."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("geo05_report", HERE / "report.py")
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)
SPEC = importlib.util.spec_from_file_location("geo05_smoke", HERE / "smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)
SPEC = importlib.util.spec_from_file_location("geo05_render", HERE / "render.py")
render = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render
SPEC.loader.exec_module(render)
SPEC = importlib.util.spec_from_file_location("geo05_collect", HERE / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collect
SPEC.loader.exec_module(collect)


class Geo05ReportTests(unittest.TestCase):
    def test_source_delta_rejects_algorithm_changes_and_allows_harness_paths(self):
        self.assertIn("CMakeLists.txt", report.HARNESS_PATH_ALLOWLIST)
        report.validate_source_tree_delta([
            "CMakeLists.txt",
            "reports/algorithm-results/tooling/geo05/projection_predecessor_driver.cpp",
            "reports/algorithm-results/tooling/geo05/report.py",
        ])
        with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
            report.validate_source_tree_delta(["src/geometry/polyhedral/projection.cpp"])

    def test_strict_json_reader_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            report.strict_json_loads('{"status":"passed","status":"failed"}')
        with self.assertRaisesRegex(ValueError, "nonfinite JSON number"):
            report.strict_json_loads('{"duration":NaN}')

    def test_collector_accepts_only_prefix_of_required_order_for_aborted_process(self):
        rows = []
        for scenario in report.SCENARIOS:
            row = report.synthetic_trial(scenario, 0)
            row["purpose"] = "warmup"
            rows.append(row)
        for repetition in range(7):
            for scenario in report.scenario_order(repetition):
                row = report.synthetic_trial(scenario, repetition)
                row["purpose"] = "measurement"
                rows.append(row)
        collect._matrix_error(rows[:-1], 7)
        with self.assertRaisesRegex(ValueError, "fixed alternating order"):
            collect._matrix_error(rows[:4] + [rows[5], rows[4]] + rows[6:], 7)

    def test_timeout_capture_preserves_partial_stdout_and_stderr(self):
        with patch.object(collect.subprocess, "run", side_effect=collect.subprocess.TimeoutExpired(
                ["driver"], 600, output=b'{"scenario":"partial"}\n', stderr=b"timed out")):
            stdout, stderr, code, timed_out = collect._run_capture(["driver"])
        self.assertEqual(stdout, '{"scenario":"partial"}\n')
        self.assertEqual(stderr, "timed out")
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)

    def test_cmake_delta_allows_only_the_exact_report_option_and_target(self):
        baseline = report.GEO04_CMAKE_OPTION + "\n" + report.GEO04_CMAKE_TARGET + "\nadd_library(core src/core.cpp)\n"
        expected = baseline.replace(report.GEO04_CMAKE_OPTION,
                                    report.GEO04_CMAKE_OPTION + "\n" + report.GEO05_CMAKE_OPTION, 1)
        expected = expected.replace(report.GEO04_CMAKE_TARGET,
                                    report.GEO04_CMAKE_TARGET + "\n" + report.GEO05_CMAKE_TARGET, 1)
        report.validate_cmake_delta(baseline, expected)
        with self.assertRaisesRegex(ValueError, "beyond the exact GEO-05 report-target insertion"):
            report.validate_cmake_delta(baseline, expected + "add_compile_definitions(LEAK=1)\n")

    def test_catalog_has_four_bounded_scenarios_and_literal_checks(self):
        self.assertEqual(report.SCENARIOS, (
            "singular_a", "unreachable_equality_target",
            "integrator_predecessor", "v_projection_preserves_ray"))
        self.assertEqual(report.CATALOG_VERSION, "geo05-analytic-v1")
        self.assertEqual(set(report.ORACLES), set(report.SCENARIOS))

    def test_record_binds_full_fixture_inputs_and_scenario_hashes(self):
        record = report.make_record([report.synthetic_trial(name, 0) for name in report.SCENARIOS],
            purpose="test", provenance={"source_commit": "fixture", "harness_commit": "fixture"})
        row = next(item for item in record["trials"] if item["scenario"] == "integrator_predecessor")
        self.assertEqual(row["input_sha256"], report.sha256_json(report.ORACLES["integrator_predecessor"]["inputs"]))
        self.assertEqual(row["scenario_sha256"], report.sha256_json(report.ORACLES["integrator_predecessor"]))
        record["catalog"]["oracles"]["integrator_predecessor"]["inputs"]["A"][0][0] = 99
        report.resign_record(record)
        with self.assertRaisesRegex(ValueError, "catalog digest|pinned catalog"):
            report.validate_record(record)

    def test_fixed_alternating_order_reverses_each_other_round(self):
        self.assertEqual(report.scenario_order(0), report.SCENARIOS)
        self.assertEqual(report.scenario_order(1), tuple(reversed(report.SCENARIOS)))

    def test_smoke_requires_four_passed_work_observed_trials_and_pinned_row_counts(self):
        rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        for row in rows:
            row["purpose"] = "smoke"
            if row["scenario"] == "integrator_predecessor":
                row.update({"output_rows": 4, "input_rows": 6, "expected_fm_peak_rows": 6})
        decoded = smoke.validate_smoke("\n".join(json.dumps(row) for row in rows))
        self.assertEqual(len(decoded), 4)
        rows[0]["work_observed"] = False
        with self.assertRaisesRegex(ValueError, "failed or incomplete"):
            smoke.validate_smoke("\n".join(json.dumps(row) for row in rows))

    def test_failure_or_unsupported_invalidates_all_success_summaries(self):
        rows = [report.synthetic_trial(name, rep) for rep in range(7) for name in report.SCENARIOS]
        rows[-1]["status"] = "unsupported"
        summary = report.summarize(rows, measured_repetitions=7, warmups=1)
        self.assertEqual(summary["counts"]["unsupported"], 1)
        self.assertFalse(summary["valid_success_summary"])
        self.assertTrue(all(value["median_ns"] is None for value in summary["phases"].values()))

    def test_failed_attempt_retains_identity_without_fabricating_output_and_timeout_invalidates(self):
        rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        failed = rows[0]
        failed.update({"status": "oracle_failed", "oracle_passed": False, "output_rows": None,
                       "result_kind": None, "result_encoding": None, "work_observed": False})
        record = report.make_record(rows, purpose="test", provenance={"source_commit": "fixture", "harness_commit": "fixture"})
        self.assertEqual(record["trials"][0]["status"], "oracle_failed")
        timeout = report.summarize(rows, 1, 0, process_return_code=124, timed_out=True)
        self.assertTrue(timeout["timed_out"])
        self.assertFalse(timeout["valid_success_summary"])
        self.assertTrue(all(phase["median_ns"] is None for phase in timeout["phases"].values()))

    def test_content_digest_binds_payload_and_report_identity(self):
        record = report.make_record([report.synthetic_trial(name, 0) for name in report.SCENARIOS],
                                    purpose="test", provenance={"source_commit": "fixture", "harness_commit": "fixture"})
        report.validate_record(record)
        record["trials"][0]["max_rows"] = 129
        with self.assertRaisesRegex(ValueError, "payload digest mismatch"):
            report.validate_record(record)

    def test_resigned_record_cannot_omit_or_invent_scenario_row_limit(self):
        for scenario, bad_value in (("singular_a", None), ("v_projection_preserves_ray", 128)):
            with self.subTest(scenario=scenario):
                record = report.make_record([report.synthetic_trial(name, 0) for name in report.SCENARIOS],
                    purpose="test", provenance={"source_commit": "fixture", "harness_commit": "fixture"})
                row = next(item for item in record["trials"] if item["scenario"] == scenario)
                row["max_rows"] = bad_value
                report.resign_record(record)
                with self.assertRaisesRegex(ValueError, "max_rows does not match"):
                    report.validate_record(record)

    def test_record_reproduction_rejects_wrong_trial_matrix(self):
        trials = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        record = report.make_record(trials, purpose="test", provenance={"source_commit": "fixture", "harness_commit": "fixture"})
        record["trials"].append(dict(record["trials"][0]))
        report.resign_record(record)
        with self.assertRaisesRegex(ValueError, "trial matrix"):
            report.validate_record(record)

    def test_failed_warmup_is_retained_and_invalidates_measured_summary(self):
        warmups = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        for row in warmups:
            row["purpose"] = "warmup"
        warmups[0]["status"] = "unsupported"
        measured = [report.synthetic_trial(name, repetition)
                    for repetition in range(7) for name in report.SCENARIOS]
        summary = report.summarize(measured, measured_repetitions=7, warmups=1,
                                   warmup_trials=warmups)
        self.assertEqual(summary["counts"]["unsupported"], 1)
        self.assertFalse(summary["valid_success_summary"])
        self.assertIsNone(summary["phases"]["end_to_end_ns"]["median_ns"])

    def test_partial_process_record_retains_attempts_and_missing_count(self):
        warmups = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        for row in warmups:
            row["purpose"] = "warmup"
        trials = [report.synthetic_trial(name, repetition)
                  for repetition in range(7) for name in report.SCENARIOS]
        trials.pop()
        record = report.make_record(trials, purpose="measurement",
            provenance={"source_commit": "fixture", "harness_commit": "fixture"},
            measured_repetitions=7, warmups=1, warmup_trials=warmups)
        self.assertEqual(record["collection"]["counts"]["missing"], 1)
        self.assertFalse(record["collection"]["valid_success_summary"])
        report.validate_record(record)

    def test_nonzero_process_exit_invalidates_success_rows(self):
        trials = [report.synthetic_trial(name, repetition)
                  for repetition in range(7) for name in report.SCENARIOS]
        summary = report.summarize(trials, 7, 1,
            [report.synthetic_trial(name, 0) for name in report.SCENARIOS], process_return_code=2)
        self.assertFalse(summary["valid_success_summary"])
        self.assertTrue(all(item["median_ns"] is None for item in summary["phases"].values()))

    def test_saved_record_renderer_escapes_failure_text_without_running_driver(self):
        rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        rows[0]["status"] = "failed"
        rows[0]["detail"] = "<script>bad()</script>"
        rows[0]["oracle_passed"] = False
        rows[0]["output_rows"] = None
        rows[0]["result_kind"] = None
        rows[0]["result_encoding"] = None
        record = report.make_record(rows, purpose="test", provenance={
            "source_commit": "fixture", "harness_commit": "fixture",
            "configuration": "Release", "cxx_standard": "20",
            "build_log_sha256": "log-hash", "executable": {"name": "driver.exe", "sha256": "exe-hash"},
            "dependency_targets": ["driver", "polyhedral"],
            "compiler": {"id": "MSVC", "version": "19.44"},
            "environment": {"os": "fixture-os", "processor": "fixture-cpu"}})
        page = render.render_html(record)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", page)
        self.assertNotIn("<script>bad()", page)
        self.assertIn("timings are smoke/test evidence only", page)
        self.assertIn("<svg", page)
        self.assertIn("integrator_predecessor", page)
        self.assertIn("Build provenance", page)
        self.assertIn("fixture-os", page)
        self.assertIn("MSVC", page)
        self.assertIn("Release", page)
        self.assertIn("exe-hash", page)
        self.assertIn("log-hash", page)
        self.assertIn("Input SHA-256", page)
        self.assertIn("Scenario SHA-256", page)
        self.assertIn(report.sha256_json(report.ORACLES["integrator_predecessor"]["inputs"]), page)


if __name__ == "__main__":
    unittest.main()

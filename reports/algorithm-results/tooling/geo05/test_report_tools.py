"""Contract tests for GEO-05's versioned phase-one report harness."""
from __future__ import annotations

import importlib.util
import copy
import csv
import hashlib
import json
import sys
import unittest
import tempfile
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


def predecessor_failure_fixture():
    return {
        "predecessor": {"identity": {"problem": "nested-problem", "request": "<predecessor-request>",
            "ideal_output": "predecessor-ideal"}, "inputs": ["X", "U", "S"]},
        "projection": {"identity": {"problem": "nested-problem", "request": "projection-request",
            "ideal_output": "projection-ideal"}, "inputs": ["joint-set"]},
        "projection_provider": {"request": "projection-request", "port": "geometry",
            "requested_module": "requested-projection", "requested_version": "requested-v1",
            "actual_module": "actual-projection", "actual_version": "actual-v2"},
        "completed_lineage": [{
            "reference": {"identity": {"problem": "nested-problem", "request": "lineage-request",
                "ideal_output": "lineage-ideal"}, "inputs": ["lineage-input"]},
            "scope": "support_value", "support": {"kind": "numerical_check", "absolute_tolerance": 0.125,
                "relative_tolerance": 0.25, "max_residual": 0.5, "verifier": "numeric-verifier"},
            "assumptions": ["numerical assumption"],
            "error_bound": {"metric": "distance-metric", "bound": 0.75, "units": "meters"}}],
        "cause": {"kind": "operation_stopped", "reason": "cancelled", "diagnostics": "child projection cancelled"}}


def measurement_rows():
    rows = []
    for purpose, repetitions in (("warmup", 1), ("measurement", 7)):
        for repetition in range(repetitions):
            for name in report.scenario_order(repetition):
                row = report.synthetic_trial(name, repetition)
                row["purpose"] = purpose
                rows.append(row)
    return rows


HISTORICAL_ARTIFACT_PATHS = [
    "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/build-log.redacted.txt",
    "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/concurrent-work.txt",
    "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/measurement-interpretation.md",
    "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/post-collection-validation.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/public-companions.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72.zip",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/command.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/index.html",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/manifest.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/parse-errors.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/provenance.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/records.json",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/stderr.txt",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/stdout.jsonl",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/trials.csv",
    "reports/algorithm-results/geo05-7fddaba0c7698f72/trials.jsonl",
]


class Geo05ReportTests(unittest.TestCase):
    def test_source_delta_admits_the_reviewed_historical_artifact_snapshot(self):
        try:
            report.validate_source_tree_delta(HISTORICAL_ARTIFACT_PATHS + [
                "CMakeLists.txt", "reports/algorithm-results/tooling/geo05/collect.py"])
        except ValueError as error:
            self.fail(f"reviewed historical artifact snapshot must not block recollection: {error}")

    def test_source_delta_admits_known_artifact_filenames_for_a_new_hash_report_id(self):
        paths = [path.replace("7fddaba0c7698f72", "0123456789abcdef") for path in HISTORICAL_ARTIFACT_PATHS]
        try:
            report.validate_source_tree_delta(paths)
        except ValueError as error:
            self.fail(f"subsequent hash-named GEO-05 artifacts must not block recollection: {error}")

    def test_artifact_directories_do_not_admit_arbitrary_files_or_source_build_configuration(self):
        roots = ["reports/algorithm-results/geo05-7fddaba0c7698f72",
                 "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence",
                 "reports/algorithm-results/geo05-0123456789abcdef",
                 "reports/algorithm-results/geo05-0123456789abcdef-evidence"]
        for root in roots:
            for name in ("driver.cpp", "provider.hpp", "collect.py", "CMakeLists.txt", "CMakeCache.txt",
                         "config.json", "toolchain.cmake", "build.ninja", "driver.exe", "unreviewed.json",
                         "unknown.txt", "another.zip", "nested/records.json"):
                with self.subTest(path=f"{root}/{name}"):
                    with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
                        report.validate_source_tree_delta(HISTORICAL_ARTIFACT_PATHS + [f"{root}/{name}"])
        with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
            report.validate_source_tree_delta(["reports/algorithm-results/geo05-another-id/records.json"])

    def test_artifact_classifier_rejects_malformed_unrelated_and_nested_report_paths(self):
        for path in (
            "reports/algorithm-results/geo05-0123456789abcde/records.json",
            "reports/algorithm-results/geo05-0123456789abcdef0/records.json",
            "reports/algorithm-results/geo05-0123456789abcdeg/records.json",
            "reports/algorithm-results/geo05-0123456789ABCDEF/records.json",
            "reports/algorithm-results/geo03-0123456789abcdef/records.json",
            "reports/algorithm-results/geo05-0123456789abcdef-evidence/records.json",
            "reports/algorithm-results/geo05-0123456789abcdef/measurement-interpretation.md",
            "reports/algorithm-results/geo05-0123456789abcdef-evidence.zip",
            "reports/algorithm-results/geo05-0123456789abcdef.zip.cpp",
            "reports/algorithm-results/geo05-0123456789abcdef/records.json.py",
            "reports/algorithm-results/geo05-0123456789abcdef/../collect.py",
            "reports/algorithm-results/nested/geo05-0123456789abcdef/records.json",
            "reports/algorithm-results/geo05-0123456789abcdef/nested/records.json",
            "reports/algorithm-results/geo05-0123456789abcdef-evidence/nested/public-companions.json",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
                    report.validate_source_tree_delta([path])

    def test_source_delta_rejects_algorithm_changes_and_allows_harness_paths(self):
        self.assertIn("CMakeLists.txt", report.HARNESS_PATH_ALLOWLIST)
        report.validate_source_tree_delta([
            "CMakeLists.txt",
            "reports/algorithm-results/tooling/geo05/projection_predecessor_driver.cpp",
            "reports/algorithm-results/tooling/geo05/report.py",
            "reports/algorithm-results/tooling/geo05/test_driver_outcomes.cpp",
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

    def test_oracle_failure_retains_observed_output_and_suppresses_every_summary(self):
        for scenario in report.SCENARIOS:
            with self.subTest(scenario=scenario):
                rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
                failed = next(row for row in rows if row["scenario"] == scenario)
                failed.update(status="oracle_failed", oracle_passed=False, output_rows=17)
                record = report.make_record(rows, purpose="test", provenance={
                    "source_commit": "fixture", "harness_commit": "fixture"})
                report.validate_record(record)
                self.assertEqual(record["trials"][rows.index(failed)]["output_rows"], 17)
                self.assertEqual(record["collection"]["counts"], {
                    "passed": 3, "failed": 1, "unsupported": 0, "cancelled": 0, "missing": 0})
                self.assertFalse(record["collection"]["valid_success_summary"])
                groups = [record["collection"], *record["collection"]["by_scenario"].values()]
                for group in groups:
                    for phase in group["phases"].values():
                        for statistic in ("median_ns", "min_ns", "max_ns"):
                            self.assertIsNone(phase[statistic])

    def test_typed_non_success_records_retain_status_and_diagnostic_detail(self):
        for status in ("unsupported", "cancelled"):
            with self.subTest(status=status):
                rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
                rows[0].update(status=status, oracle_passed=False, work_observed=False,
                    output_rows=None, result_kind=None, result_encoding=None,
                    detail="unsupported: projection.rows: configured row limit exceeded" if status == "unsupported"
                           else "cancelled: operation stopped before projection")
                record = report.make_record(rows, purpose="test", provenance={
                    "source_commit": "fixture", "harness_commit": "fixture"})
                self.assertEqual(record["trials"][0]["status"], status)
                self.assertIn("projection", record["trials"][0]["detail"])
                self.assertEqual(record["collection"]["counts"][status], 1)
                self.assertEqual(record["collection"]["counts"]["failed"], 0)
                self.assertFalse(record["collection"]["valid_success_summary"])

    def test_optional_end_to_end_scope_rejects_unknown_values_and_renders_observed_scope(self):
        rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
        record = report.make_record(rows, purpose="test", provenance={
            "source_commit": "fixture", "harness_commit": "fixture"})
        rows[0]["end_to_end_scope"] = "invented_scope"
        report.resign_record(record)
        with self.assertRaisesRegex(ValueError, "end-to-end scope"):
            report.validate_record(record)
        rows[0]["end_to_end_scope"] = "through_verification_and_fixture_teardown"
        report.resign_record(record)
        report.validate_record(record)
        self.assertIn("through_verification_and_fixture_teardown", render.render_html(record))

    def test_nested_failure_context_round_trips_saved_formats_and_escaped_rendering(self):
        context = predecessor_failure_fixture()
        rows = measurement_rows()
        for index in (0, 4):
            rows[index].update(status="cancelled", oracle_passed=False, work_observed=False,
                output_rows=None, result_kind=None, result_encoding=None,
                predecessor_failure=copy.deepcopy(context))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "report"
            collect._write_collection(out, "", "", rows, {"source_commit": "fixture", "harness_commit": "fixture"},
                ["fixture-driver"], 7, 0, [])
            record = report.strict_json_loads((out / "records.json").read_text(encoding="utf-8"))
            report.validate_record(record)
            self.assertEqual(record["trials"][0]["predecessor_failure"], context)
            self.assertEqual(record["warmup_trials"][0]["predecessor_failure"], context)
            jsonl = [report.strict_json_loads(line) for line in (out / "trials.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(jsonl[4]["predecessor_failure"], context)
            with (out / "trials.csv").open(encoding="utf-8", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertIn("predecessor_failure", csv_rows[0])
            self.assertEqual(json.loads(csv_rows[0]["predecessor_failure"]), context)
            self.assertEqual(json.loads(csv_rows[4]["predecessor_failure"]), context)
            page = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("&lt;predecessor-request&gt;", page)
            self.assertNotIn("<predecessor-request>", page)
            for value in ("joint-set", "requested-projection", "requested-v1", "actual-projection", "actual-v2",
                          "lineage-request", "numeric-verifier", "numerical assumption", "distance-metric", "meters"):
                self.assertIn(value, page)

    def test_raw_capture_survives_observed_encoding_rejection(self):
        rows = measurement_rows()
        rows[4].update(status="oracle_failed", oracle_passed=False, result_encoding="v_generators")
        stdout = "\n".join(json.dumps(row) for row in rows) + "\n"
        stderr = "driver diagnostic retained\n"
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "report"
            with self.assertRaisesRegex(ValueError, "representation and encoding"):
                collect._write_collection(out, stdout, stderr, rows,
                    {"source_commit": "fixture", "harness_commit": "fixture"}, ["fixture-driver"], 7, 124, [], True)
            self.assertTrue(out.exists(), "raw capture must be persisted before record validation")
            self.assertEqual((out / "stdout.jsonl").read_text(encoding="utf-8"), stdout)
            self.assertEqual((out / "stderr.txt").read_text(encoding="utf-8"), stderr)
            capture = json.loads((out / "process-capture.json").read_text(encoding="utf-8"))
            self.assertEqual(capture["process_return_code"], 124)
            self.assertTrue(capture["timed_out"])
            diagnostic = json.loads((out / "validation-error.json").read_text(encoding="utf-8"))
            self.assertIn("representation and encoding", diagnostic["error"])
            self.assertFalse((out / "records.json").exists())
            self.assertFalse((out / "manifest.json").exists())
            self.assertFalse(out.with_suffix(".zip").exists())

    def test_main_raw_capture_survives_attempt_order_rejection(self):
        rows = measurement_rows()
        rows[0], rows[1] = rows[1], rows[0]
        stdout = "\n".join(json.dumps(row) for row in rows) + "\n"
        stderr = "out-of-order driver diagnostic\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fixture-driver.exe"
            executable.write_bytes(b"synthetic fixture executable identity")
            note = root / "concurrent-work.txt"
            note.write_text("synthetic fixture", encoding="utf-8")
            out = root / "report"
            argv = ["collect.py", "--measure", "--exe", str(executable), "--build-dir", str(root),
                "--build-log", str(root / "build.log"), "--source-commit", "fixture", "--harness-commit", "fixture",
                "--concurrent-work", str(note), "--out", str(out)]
            with patch.object(sys, "argv", argv), patch.object(collect, "build_provenance", return_value={
                    "source_commit": "fixture", "harness_commit": "fixture", "executable": {
                        "sha256": hashlib.sha256(b"synthetic fixture executable identity").hexdigest()}}), \
                    patch.object(collect, "_run_capture", return_value=(stdout, stderr, 2, False)):
                with self.assertRaisesRegex(ValueError, "fixed alternating order"):
                    collect.main()
            self.assertTrue(out.exists(), "raw capture must be persisted before ordering validation")
            self.assertEqual((out / "stdout.jsonl").read_text(encoding="utf-8"), stdout)
            self.assertEqual((out / "stderr.txt").read_text(encoding="utf-8"), stderr)
            self.assertEqual(json.loads((out / "command.json").read_text(encoding="utf-8")),
                [str(executable), "--measure", "--repetitions", "7", "--warmups", "1"])
            capture = json.loads((out / "process-capture.json").read_text(encoding="utf-8"))
            self.assertEqual(capture["process_return_code"], 2)
            self.assertFalse(capture["timed_out"])
            diagnostic = json.loads((out / "validation-error.json").read_text(encoding="utf-8"))
            self.assertIn("fixed alternating order", diagnostic["error"])
            self.assertFalse((out / "records.json").exists())
            self.assertFalse(out.with_suffix(".zip").exists())

    def test_successful_collection_keeps_existing_bundle_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "report"
            collect._write_collection(out, "", "", measurement_rows(),
                {"source_commit": "fixture", "harness_commit": "fixture"}, ["fixture-driver"], 7, 0, [])
            self.assertEqual({path.name for path in out.iterdir()}, {
                "records.json", "provenance.json", "command.json", "stdout.jsonl", "stderr.txt", "parse-errors.json",
                "trials.jsonl", "trials.csv", "index.html", "manifest.json"})
            self.assertTrue(out.with_suffix(".zip").exists())

    def test_nested_failure_context_validation_rejects_incomplete_or_mistyped_payloads(self):
        context = predecessor_failure_fixture()
        malformed = []
        for key in ("predecessor", "projection", "projection_provider", "completed_lineage", "cause"):
            value = copy.deepcopy(context)
            del value[key]
            malformed.append(value)
        value = copy.deepcopy(context)
        value["projection_provider"]["actual_version"] = 7
        malformed.append(value)
        value = copy.deepcopy(context)
        value["completed_lineage"][0]["support"]["max_residual"] = True
        malformed.append(value)
        value = copy.deepcopy(context)
        value["completed_lineage"][0]["scope"] = "invented_scope"
        malformed.append(value)
        value = copy.deepcopy(context)
        value["cause"]["reason"] = "resource_limit"
        malformed.append(value)
        for value in malformed:
            with self.subTest(value=value):
                rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
                rows[0].update(status="cancelled", oracle_passed=False, work_observed=False,
                    output_rows=None, result_kind=None, result_encoding=None, predecessor_failure=value)
                with self.assertRaisesRegex(ValueError, "predecessor failure"):
                    report.make_record(rows, purpose="test", provenance={
                        "source_commit": "fixture", "harness_commit": "fixture"})

    def test_nested_context_schema_and_semantics_agree_for_variants_and_status(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("optional JSON Schema validator is unavailable")
        import jsonschema
        schema = json.loads((HERE / "schema-v1.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        supports = [
            {"kind": "unestablished"},
            {"kind": "numerical_check", "absolute_tolerance": 0.125, "relative_tolerance": 0.25,
                "max_residual": 0.5, "verifier": "numeric-verifier"},
            {"kind": "symbolic_argument", "reference": "symbolic-reference", "assumptions": "symbolic conditions"},
            {"kind": "certificate_reference", "artifact": "certificate-artifact", "verifier": "certificate-verifier"}]
        causes = [("cancelled", {"kind": "operation_stopped", "reason": "cancelled", "diagnostics": "cancelled"}),
                  ("cancelled", {"kind": "operation_stopped", "reason": "deadline_expired", "diagnostics": "deadline"}),
                  ("failed", {"kind": "operation_stopped", "reason": "resource_limit", "diagnostics": "capacity"}),
                  ("failed", {"kind": "operation_stopped", "reason": "numerical_failure", "diagnostics": "residual"}),
                  ("unsupported", {"kind": "unsupported", "diagnostics": [
                      {"code": "unsupported", "field": "projection.rows", "explanation": "configured limit"}]})]
        for status, cause in causes:
            for support in supports:
                rows = [report.synthetic_trial(name, 0) for name in report.SCENARIOS]
                context = predecessor_failure_fixture()
                context["completed_lineage"][0]["support"] = support
                context["projection_provider"].update(requested_version=None, actual_module=None, actual_version=None)
                context["cause"] = cause
                rows[0].update(status=status, oracle_passed=False, work_observed=False,
                    output_rows=None, result_kind=None, result_encoding=None, predecessor_failure=context)
                record = report.make_record(rows, purpose="test", provenance={
                    "source_commit": "fixture", "harness_commit": "fixture"})
                validator.validate(record)
        record["trials"][0]["predecessor_failure"]["cause"] = {
            "kind": "operation_stopped", "reason": "cancelled", "diagnostics": "cancelled"}
        report.resign_record(record)
        with self.assertRaisesRegex(ValueError, "predecessor failure"):
            report.validate_record(record)
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            validator.validate(record)
        del record["trials"][0]["predecessor_failure"]
        report.resign_record(record)
        report.validate_record(record)
        validator.validate(record)
        record["trials"][0]["predecessor_failure"] = None
        report.resign_record(record)
        report.validate_record(record)
        validator.validate(record)

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
        self.assertIn("pre{white-space:pre-wrap;overflow-wrap:anywhere", page)
        self.assertIn(report.sha256_json(report.ORACLES["integrator_predecessor"]["inputs"]), page)


if __name__ == "__main__":
    unittest.main()

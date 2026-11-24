from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "reports" / "algorithm-results" / "tooling" / "ts01"
sys.path.insert(0, str(ROOT / "scripts" / "reports"))


def load_tool(name):
    spec = importlib.util.spec_from_file_location("csl_test_ts01_" + name, TOOLS / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = load_tool("report")
with patch.dict(sys.modules, {"report": report}):
    collector = load_tool("collect")
publication_map = load_tool("publication_map")
build_bundle = load_tool("build_bundle")
ts01_registered_reports = importlib.import_module("ts01_registered_reports")


class Ts01SavedReportTests(unittest.TestCase):
    def setUp(self):
        self.bundle = ROOT / "reports" / "algorithm-results" / "syn07-ts01-20261014-e22d9c2aeb05"
        self.record = json.loads((self.bundle / "records.json").read_text(encoding="utf-8"))

    def test_exact_membership_matrix_matches_saved_outcomes(self):
        self.assertEqual(report.validate(self.record), [])
        self.assertEqual(sum(row["actual_member"] for row in self.record["membership_examples"]), 4)
        self.assertEqual(
            sum(not row["actual_member"] for row in self.record["membership_examples"]), 3
        )

    def test_changed_membership_result_is_rejected(self):
        changed = json.loads(json.dumps(self.record))
        changed["membership_examples"][0]["actual_member"] = False
        self.assertIn("membership_result:s=0", report.validate(changed))

    def test_changed_timing_summary_is_rejected(self):
        for field in ("median", "min", "max", "range"):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(self.record))
                changed["measurement"]["timing_ns"][field] += 1
                self.assertIn("measurement_summary", report.validate(changed))

    def test_scenario_and_input_hashes_are_canonical_and_checked(self):
        scenario = self.record["scenario"]
        self.assertEqual(scenario["sha256"], report.digest(scenario["value"]))
        self.assertEqual(
            self.record["input"]["sha256"], report.digest(self.record["input"]["value"])
        )
        changed = json.loads(json.dumps(self.record))
        changed["scenario"]["sha256"] = "0" * 64
        self.assertIn("scenario_hash", report.validate(changed))

    def test_actual_strategy_observations_are_separate_from_analytic_expectations(self):
        expected = self.record["canonical_relation"]["objective_minimum"]
        observed = self.record["measurement"]["strategy_observation"]
        self.assertEqual(expected, 0)
        self.assertEqual(observed["termination"], "completed")
        self.assertEqual(observed["outcome"], "optimal")
        self.assertEqual(observed["objective_lower"], 0)
        self.assertEqual(observed["objective_upper"], 0)
        self.assertEqual(
            observed["residuals"],
            {"available": False, "reason": "StrategyPort result exposes no residual fields"},
        )
        changed = json.loads(json.dumps(self.record))
        changed["measurement"]["strategy_observation"]["objective_upper"] = 1
        self.assertIn("strategy_objective_observation", report.validate(changed))

    def test_html_is_projected_from_saved_record(self):
        page = report.render_html(self.record)
        self.assertIn("(0,s,1,s,1−s)", page)
        self.assertIn("Exact binary64 membership examples", page)
        self.assertIn(self.record["source_commit"], page)
        self.assertIn("Observed StrategyPort result", page)
        self.assertIn(self.record["scenario"]["sha256"], page)

    def test_publication_map_describes_exploratory_measurements(self):
        projection = publication_map.project(self.record)
        scope = projection["publication_contract"]["measured_scope"]
        self.assertIn("exploratory timings available", scope)
        self.assertIn("inconclusive", scope)
        self.assertNotIn("performance unavailable", scope)

    def test_bundle_builder_requires_measurement_input(self):
        with self.assertRaisesRegex(ValueError, "--measurement-dir is required"):
            build_bundle.build()

    def test_saved_collection_rebuilds_the_exact_archived_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            measurement = scratch / "measurement"
            measurement.mkdir()
            (measurement / "collection.json").write_bytes(
                (self.bundle / "measurement.json").read_bytes()
            )
            (measurement / "events.jsonl").write_bytes(
                (self.bundle / "measurement-events.jsonl").read_bytes()
            )
            output = scratch / self.bundle.name
            subprocess.run(
                [
                    sys.executable,
                    TOOLS / "build_bundle.py",
                    "--measurement-dir",
                    measurement,
                    "--out-dir",
                    output,
                ],
                check=True,
                capture_output=True,
            )
            self.assertCountEqual(
                [path.name for path in output.iterdir()],
                [path.name for path in self.bundle.iterdir()],
            )
            for path in self.bundle.iterdir():
                self.assertEqual((output / path.name).read_bytes(), path.read_bytes(), path.name)

    def test_interrupted_measurement_retains_flushed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            build_root = Path(directory)

            def interrupted_process(command, **outputs):
                if "stdout" in outputs:
                    outputs["stdout"].write(b"partial stdout")
                    outputs["stderr"].write(b"partial stderr")
                raise KeyboardInterrupt

            with (
                patch.object(collector, "subprocess", Mock(run=interrupted_process)),
                redirect_stderr(io.StringIO()),
                self.assertRaises(KeyboardInterrupt),
                collector.measurement_attempt(
                    build_root, build_root / "driver.exe", "b" * 64, "a" * 40
                ),
            ):
                self.fail("interrupted process has no result")

            (attempt,) = build_root.glob("measurement-attempt.*")
            self.assertEqual((attempt / "stdout.bin").read_bytes(), b"partial stdout")
            self.assertEqual((attempt / "stderr.bin").read_bytes(), b"partial stderr")
            receipt = json.loads((attempt / "attempt.json").read_bytes())
            self.assertEqual(receipt["status"], "cancelled")
            self.assertIsNone(receipt["returncode"])
            self.assertEqual(
                receipt["stdout_sha256"], hashlib.sha256(b"partial stdout").hexdigest()
            )
            self.assertEqual(
                receipt["stderr_sha256"], hashlib.sha256(b"partial stderr").hexdigest()
            )

    def test_collector_records_native_attempts_and_exports_only_accepted_results(self):
        attempts = (
            (7, b"partial native output\r\n", "measurement executable failed with status 7", None),
            (0, b"invalid JSONL\n", "measurement executable emitted invalid JSONL", None),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, None),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, "receipt"),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, "prepare-receipt"),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, "collection"),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, "output-empty"),
            (0, (self.bundle / "measurement-events.jsonl").read_bytes(), None, "output-nonempty"),
        )
        for returncode, stdout, reason, fail_at in attempts:
            with (
                self.subTest(
                    returncode=returncode,
                    reason=reason,
                    fail_at=fail_at,
                ),
                tempfile.TemporaryDirectory() as directory,
            ):
                scratch = Path(directory)
                cmake = scratch / "cmake"
                cmake.touch()
                build_root = scratch / "build"
                output = build_root / "measurement-attempt"
                stderr = b"native diagnostic\r\n"

                def build_step(command, build_root=build_root):
                    if "--build" in command:
                        build = build_root / "release-build"
                        build.mkdir()
                        (build / "CMakeCache.txt").write_text(
                            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022\n"
                            "CMAKE_GENERATOR_PLATFORM:INTERNAL=x64\n",
                            encoding="utf-8",
                        )
                        (build / "csl_syn07_ts01_report.vcxproj").write_text(
                            '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
                            '<ItemDefinitionGroup Condition="Release|x64"><ClCompile>'
                            "<LanguageStandard>stdcpp20</LanguageStandard>"
                            "<Optimization>MaxSpeed</Optimization>"
                            "<PreprocessorDefinitions>NDEBUG</PreprocessorDefinitions>"
                            "</ClCompile></ItemDefinitionGroup></Project>",
                            encoding="utf-8",
                        )
                        executable = build / "Release" / "csl_syn07_ts01_report.exe"
                        executable.parent.mkdir()
                        executable.write_bytes(b"simulated executable")
                        config = build / "CMakeFiles" / "stub" / "CMakeCXXCompiler.cmake"
                        config.parent.mkdir(parents=True)
                        config.write_text(
                            'set(CMAKE_CXX_COMPILER "stub")\n'
                            'set(CMAKE_CXX_COMPILER_VERSION "1.0")\n',
                            encoding="utf-8",
                        )
                    if "--version" in command:
                        return subprocess.CompletedProcess(command, 0, b"cmake simulator\n", b"")
                    return subprocess.CompletedProcess(command, 0, b"", b"")

                def git_response(root, *args, build_root=build_root):
                    if args == ("status", "--porcelain"):
                        return ""
                    return (
                        report.SOURCE_COMMIT if root == build_root / "solver-source" else "a" * 40
                    )

                argv = [
                    "collect.py",
                    "--cmake",
                    str(cmake),
                    "--build-root",
                    str(build_root),
                    "--out",
                    str(output),
                ]

                def run_driver(
                    command,
                    *,
                    stdout,
                    stderr,
                    check,
                    raw_stdout=stdout,
                    raw_stderr=stderr,
                    status=returncode,
                ):
                    stdout.write(raw_stdout)
                    stderr.write(raw_stderr)
                    return subprocess.CompletedProcess(command, status)

                expected = (
                    self.assertRaisesRegex(OSError, "simulated .* failure")
                    if fail_at is not None
                    else nullcontext()
                    if reason is None
                    else self.assertRaisesRegex(SystemExit, reason)
                )
                replace = Path.replace
                mkdir = Path.mkdir

                def reject_accepted_receipt(path, target, *, failure=fail_at, replace_path=replace):
                    if failure in {"receipt", "prepare-receipt"} and path.name == "attempt.tmp":
                        status = json.loads(path.read_text(encoding="utf-8"))["status"]
                        if failure == "receipt" and status == "accepted":
                            raise OSError("simulated accepted receipt write failure")
                        if failure == "prepare-receipt" and status == "ready_to_publish":
                            raise OSError("simulated ready receipt write failure")
                    if (
                        failure == "collection"
                        and path.name == "collection.json.tmp"
                        and target.name == "collection.json"
                    ):
                        raise OSError("simulated collection publish failure")
                    return replace_path(path, target)

                def create_competing_output_before_publish(
                    path, *args, failure=fail_at, mkdir_path=mkdir, output_path=output, **kwargs
                ):
                    if (
                        isinstance(failure, str)
                        and failure.startswith("output")
                        and path == output_path
                    ):
                        mkdir_path(path, parents=True, exist_ok=False)
                        if failure == "output-nonempty":
                            (output_path / "collection.json").write_bytes(
                                b"another collector's result"
                            )
                        try:
                            return mkdir_path(path, *args, **kwargs)
                        except OSError as error:
                            raise OSError(f"simulated output publish failure: {error}") from error
                    return mkdir_path(path, *args, **kwargs)

                with (
                    patch.object(sys, "argv", argv),
                    patch.object(collector, "git", side_effect=git_response),
                    patch.object(collector, "run", side_effect=build_step),
                    patch.object(collector, "psutil", None),
                    patch.object(collector, "subprocess", Mock(run=run_driver)),
                    patch.object(
                        Path, "replace", autospec=True, side_effect=reject_accepted_receipt
                    ),
                    patch.object(
                        Path,
                        "mkdir",
                        autospec=True,
                        side_effect=create_competing_output_before_publish,
                    ),
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                    expected,
                ):
                    collector.main()

                (attempt,) = build_root.glob("measurement-attempt.*")
                self.assertEqual((attempt / "stdout.bin").read_bytes(), stdout)
                self.assertEqual((attempt / "stderr.bin").read_bytes(), stderr)
                receipt = json.loads((attempt / "attempt.json").read_bytes())
                self.assertEqual(receipt["returncode"], returncode)
                self.assertEqual(receipt["source_commit"], report.SOURCE_COMMIT)
                self.assertEqual(receipt["harness_commit"], "a" * 40)
                self.assertEqual(receipt["stdout_sha256"], hashlib.sha256(stdout).hexdigest())
                self.assertEqual(receipt["stderr_sha256"], hashlib.sha256(stderr).hexdigest())
                if fail_at and fail_at.startswith("output"):
                    self.assertEqual(receipt["status"], "failed")
                    if fail_at == "output-empty":
                        self.assertEqual(list(output.iterdir()), [])
                    else:
                        self.assertEqual(
                            (output / "collection.json").read_bytes(),
                            b"another collector's result",
                        )
                    self.assertEqual(list(build_root.glob(".measurement-attempt.incomplete-*")), [])
                    continue
                if fail_at == "receipt":
                    self.assertEqual(receipt["status"], "failed")
                    self.assertEqual(
                        json.loads((output / "collection.json").read_bytes())["raw_stdout_sha256"],
                        hashlib.sha256(stdout).hexdigest(),
                    )
                    continue
                if fail_at == "prepare-receipt":
                    self.assertEqual(receipt["status"], "failed")
                    self.assertEqual(receipt["reason"], "simulated ready receipt write failure")
                    self.assertEqual(len(receipt["collection_sha256"]), 64)
                    self.assertFalse(output.exists())
                    self.assertEqual(list(build_root.glob(".measurement-attempt.incomplete-*")), [])
                    continue
                if fail_at is not None:
                    self.assertEqual(receipt["status"], "failed")
                    self.assertIn("simulated", receipt["reason"])
                    self.assertFalse(output.exists())
                    if fail_at in {"receipt", "collection"}:
                        output.mkdir()
                        output.rmdir()
                    continue
                if reason is None:
                    self.assertEqual(receipt["status"], "accepted")
                    self.assertNotIn("reason", receipt)
                    self.assertCountEqual(
                        [path.name for path in output.iterdir()],
                        ["events.jsonl", "stderr.txt", "collection.json", "command.txt"],
                    )
                    self.assertEqual((output / "events.jsonl").read_bytes(), stdout)
                    self.assertEqual((output / "stderr.txt").read_bytes(), stderr)
                    collection = json.loads((output / "collection.json").read_bytes())
                    self.assertEqual(collection["counts"]["failed"], 0)
                    self.assertEqual(collection["raw_stdout_sha256"], receipt["stdout_sha256"])
                else:
                    self.assertEqual(receipt["status"], "failed")
                    self.assertEqual(receipt["reason"], reason)
                    self.assertFalse(output.exists())

    def test_registered_adapter_checks_bundle_and_creates_offline_archive(self):
        publication = ts01_registered_reports.adapt(self.bundle)
        self.assertEqual(publication.source_commit, report.SOURCE_COMMIT)
        self.assertEqual(publication.source_report_id, self.record["report_id"])
        archive = ts01_registered_reports.offline_zip(self.bundle, publication)
        catalog = json.loads((self.bundle.parent / "catalog.json").read_bytes())
        rows = [
            row for row in catalog["reports"] if row.get("source_report_id") == self.bundle.name
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["report_id"], publication.report_id)
        self.assertEqual(row["payload_sha256"], publication.payload_sha256)
        self.assertEqual(row["zip_sha256"], hashlib.sha256(archive).hexdigest())


if __name__ == "__main__":
    unittest.main()

"""Fresh Release build admission tests for GEO-05 measurement collection."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect
import report


class FreshBuildTests(unittest.TestCase):
    def test_source_delta_allows_focused_fresh_build_test_only(self):
        try:
            report.validate_source_tree_delta([
                "reports/algorithm-results/tooling/geo05/test_fresh_build.py"])
        except ValueError as error:
            self.fail(f"focused harness regression must be an allowed source delta: {error}")
        with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
            report.validate_source_tree_delta(["reports/algorithm-results/tooling/geo05/unreviewed.py"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name).resolve() / "Private User"
        self.source.mkdir()
        self.build = self.source / "build"
        self.exe = self.build / "Release" / "driver.exe"
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"stale executable")
        self.log = self.build / "build.log"
        self.log.write_text("unrelated old successful build", encoding="utf-8")
        self.out = self.source / "collection"
        self.note = self.source / "concurrent-work.txt"
        self.note.write_text("test fixture", encoding="utf-8")
        reply = self.build / ".cmake" / "api" / "v1" / "reply"
        reply.mkdir(parents=True)
        names = ["csl_geo05_projection_predecessor_report", "csl_polyhedral", "csl_sets",
                 "csl_optimization", "csl_registry", "csl_numeric", "csl_contracts"]
        targets = []
        for name in names:
            target = {"name": name, "type": "STATIC_LIBRARY"}
            if name == names[0]:
                target.update({"type": "EXECUTABLE", "artifacts": [{"path": "Release/driver.exe"}],
                    "dependencies": [{"id": dependency} for dependency in names[1:]],
                    "compileGroups": [{"language": "CXX", "languageStandard": {"standard": "20"},
                                       "compileCommandFragments": [{"fragment": "-O3 -DNDEBUG"}]}]})
            (reply / f"{name}.json").write_text(json.dumps(target), encoding="utf-8")
            targets.append({"id": name, "jsonFile": f"{name}.json"})
        (reply / "codemodel.json").write_text(json.dumps({
            "paths": {"source": str(self.source), "build": str(self.build)},
            "configurations": [{"name": "Release", "targets": targets}]}), encoding="utf-8")
        (reply / "toolchains.json").write_text(json.dumps({"toolchains": [
            {"language": "CXX", "compiler": {"id": "test", "path": str(self.source / "c++")}}]}), encoding="utf-8")
        (reply / "index-test.json").write_text(json.dumps({"reply": {
            "codemodel-v2": {"jsonFile": "codemodel.json"},
            "toolchains-v1": {"jsonFile": "toolchains.json"}}}), encoding="utf-8")
        self.source_cmake = report.GEO04_CMAKE_OPTION + "\n" + report.GEO04_CMAKE_TARGET + "\n"
        self.harness_cmake = self.source_cmake.replace(report.GEO04_CMAKE_OPTION,
            report.GEO04_CMAKE_OPTION + "\n" + report.GEO05_CMAKE_OPTION).replace(
            report.GEO04_CMAKE_TARGET, report.GEO04_CMAKE_TARGET + "\n" + report.GEO05_CMAKE_TARGET)
        self.head_checks = 0
        self.change_after_build = False
        self.dirty_after_build = False
        self.commands = []
        self.tracked_paths = []
        self.source_delta = []
        self.addCleanup(patch.stopall)
        self.real_check_output = collect.subprocess.check_output
        patch.object(collect, "_git", side_effect=self.git).start()
        patch.object(collect.subprocess, "check_output", side_effect=self.git_show).start()

    def git(self, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.source)
        if args == ("rev-parse", "HEAD"):
            self.head_checks += 1
            return "changed-head" if self.change_after_build and self.head_checks > 1 else "harness-head"
        if args == ("status", "--porcelain=v1"):
            return " M src/geometry.cpp" if self.dirty_after_build and self.commands else ""
        if args == ("diff", "--name-only", "source-head", "harness-head"):
            return "\n".join(self.source_delta)
        if args == ("rev-parse", "source-head^{tree}"):
            return "source-tree"
        if args == ("rev-parse", "harness-head^{tree}"):
            return "harness-tree"
        if args == ("-C", str(self.source), "ls-files", "-z"):
            return "\0".join(self.tracked_paths)
        raise AssertionError(f"unexpected git command: {args}")

    def git_show(self, command, **kwargs):
        if command == ["git", "show", "source-head:CMakeLists.txt"]:
            return self.source_cmake
        if command == ["git", "show", "harness-head:CMakeLists.txt"]:
            return self.harness_cmake
        raise AssertionError(f"unexpected command: {command}")

    def build_process(self, command, **kwargs):
        self.commands.append(command)
        self.exe.write_bytes(b"fresh executable")
        return collect.subprocess.CompletedProcess(command, 0,
            stdout=f"compiled {self.source / 'driver.cpp'}\n", stderr=f"warning in {self.build}\n")

    def provenance(self):
        return collect.build_provenance(self.build, self.exe, "source-head", "harness-head", self.log)

    def main(self):
        args = ["collect.py", "--measure", "--exe", str(self.exe), "--build-dir", str(self.build),
                "--build-log", str(self.log), "--source-commit", "source-head",
                "--harness-commit", "harness-head", "--concurrent-work", str(self.note),
                "--out", str(self.out)]
        with patch.object(sys, "argv", args):
            return collect.main()

    def test_success_requires_clean_verbose_release_rebuild_and_binds_its_output(self):
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            provenance = self.provenance()
        self.assertEqual(self.commands, [["cmake", "--build", str(self.build), "--config", "Release",
            "--target", "csl_geo05_projection_predecessor_report", "--clean-first", "--verbose"]])
        self.assertEqual(provenance["executable"]["sha256"], hashlib.sha256(b"fresh executable").hexdigest())
        self.assertEqual(provenance["fresh_build"]["stdout"], "compiled SOURCE_ROOT/driver.cpp\n".replace("/", "\\")
                         if sys.platform == "win32" else "compiled SOURCE_ROOT/driver.cpp\n")
        self.assertEqual(provenance["fresh_build"]["stderr"], "warning in BUILD_ROOT\n")
        self.assertEqual(provenance["fresh_build"]["return_code"], 0)
        self.assertFalse(provenance["fresh_build"]["timed_out"])
        self.assertEqual(provenance["build_log_sha256"], hashlib.sha256(self.log.read_bytes()).hexdigest())
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("compiled SOURCE_ROOT", log)
        self.assertIn("warning in BUILD_ROOT", log)
        self.assertNotIn("Private User", log)
        self.assertNotIn("unrelated old", log)

    def test_reviewed_artifacts_are_classified_separately_and_still_require_fresh_rebuild(self):
        self.source_delta = [
            "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/measurement-interpretation.md",
            "reports/algorithm-results/geo05-7fddaba0c7698f72/records.json"]
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            try:
                provenance = self.provenance()
            except ValueError as error:
                self.fail(f"reviewed artifact delta must reach fresh rebuild admission: {error}")
        self.assertEqual(provenance["tracked_tree_binding"]["actual_reviewed_artifact_delta"], [
            "reports/algorithm-results/geo05-7fddaba0c7698f72-evidence/measurement-interpretation.md",
            "reports/algorithm-results/geo05-7fddaba0c7698f72/records.json"])
        self.assertNotIn("reports/algorithm-results/geo05-7fddaba0c7698f72/records.json",
                         provenance["tracked_tree_binding"]["allowed_harness_delta"])
        self.assertIn("reports/algorithm-results/geo05-7fddaba0c7698f72/records.json",
                      provenance["tracked_tree_binding"]["allowed_reviewed_artifact_delta"])
        self.assertEqual(provenance["executable"]["sha256"], hashlib.sha256(b"fresh executable").hexdigest())
        self.assertEqual(provenance["fresh_build"]["return_code"], 0)
        self.assertEqual(len(self.commands), 1)

    def test_source_configuration_inside_artifact_directory_is_rejected_before_rebuild(self):
        self.source_delta = ["reports/algorithm-results/geo05-7fddaba0c7698f72/config.json"]
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
                self.provenance()
        self.assertEqual(self.exe.read_bytes(), b"stale executable")
        self.assertEqual(self.commands, [])

    def test_failed_rebuild_rejects_stale_executable_without_measurements(self):
        def fail(command, **kwargs):
            self.commands.append(command)
            return collect.subprocess.CompletedProcess(command, 2,
                stdout=f"compile started in {self.source}\n", stderr=f"compiler failed in {self.build}\n")
        with patch.object(collect.subprocess, "run", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "fresh Release rebuild failed"):
                self.main()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.commands[0][0], "cmake")
        self.assertEqual(self.exe.read_bytes(), b"stale executable")
        self.assertFalse(self.out.exists())
        self.assertIn("compiler failed in BUILD_ROOT", self.log.read_text(encoding="utf-8"))
        self.assertNotIn("Private User", self.log.read_text(encoding="utf-8"))

    def test_timeout_rebuild_retains_partial_diagnostics_without_measurements(self):
        def timeout(command, **kwargs):
            self.commands.append(command)
            raise collect.subprocess.TimeoutExpired(command, kwargs["timeout"],
                output=f"partial compile {self.source}".encode(), stderr=b"compiler hung")
        with patch.object(collect.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(ValueError, "fresh Release rebuild timed out"):
                self.main()
        self.assertEqual(len(self.commands), 1)
        self.assertFalse(self.out.exists())
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("partial compile SOURCE_ROOT", log)
        self.assertIn("compiler hung", log)
        self.assertIn("124", log)
        self.assertNotIn("Private User", log)

    def test_head_change_during_rebuild_rejects_admission(self):
        self.change_after_build = True
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "HEAD"):
                self.provenance()
        self.assertEqual(len(self.commands), 1)

    def test_source_edit_during_rebuild_rejects_admission(self):
        self.dirty_after_build = True
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "clean"):
                self.provenance()
        self.assertEqual(len(self.commands), 1)

    def test_executable_swap_after_rebuild_rejects_measurement(self):
        actual_provenance = collect.build_provenance
        def swap(*args):
            provenance = actual_provenance(*args)
            self.exe.write_bytes(b"swapped executable")
            return provenance
        with patch.object(collect.subprocess, "run", side_effect=self.build_process), \
                patch.object(collect, "build_provenance", side_effect=swap):
            with self.assertRaisesRegex(SystemExit, "executable changed after the fresh Release rebuild"):
                self.main()
        self.assertEqual(len(self.commands), 1)
        self.assertFalse(self.out.exists())

    def test_missing_cmake_retains_launch_error_without_measurements(self):
        with patch.object(collect.subprocess, "run", side_effect=FileNotFoundError("cmake unavailable")):
            with self.assertRaisesRegex(ValueError, "fresh Release rebuild failed"):
                self.main()
        self.assertFalse(self.out.exists())
        self.assertIn("cmake unavailable", self.log.read_text(encoding="utf-8"))

    def test_successful_rebuild_without_artifact_rejects_admission(self):
        def missing(command, **kwargs):
            self.commands.append(command)
            self.exe.unlink()
            return collect.subprocess.CompletedProcess(command, 0, stdout="build complete", stderr="")
        with patch.object(collect.subprocess, "run", side_effect=missing):
            with self.assertRaisesRegex(ValueError, "did not produce the configured executable"):
                self.main()
        self.assertFalse(self.out.exists())

    def test_reconfigured_nonrelease_flags_reject_admission(self):
        def reconfigure(command, **kwargs):
            result = self.build_process(command, **kwargs)
            target = self.build / ".cmake/api/v1/reply/csl_geo05_projection_predecessor_report.json"
            value = json.loads(target.read_text(encoding="utf-8"))
            value["compileGroups"][0]["compileCommandFragments"] = [{"fragment": "-O0"}]
            target.write_text(json.dumps(value), encoding="utf-8")
            return result
        with patch.object(collect.subprocess, "run", side_effect=reconfigure):
            with self.assertRaisesRegex(ValueError, "Release/NDEBUG"):
                self.provenance()

    def test_build_log_outside_build_directory_is_rejected_before_build(self):
        self.log = self.source / "README.md"
        self.log.write_bytes(b"source documentation")
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "build log must resolve inside"):
                self.provenance()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.log.read_bytes(), b"source documentation")
        self.assertEqual(self.exe.read_bytes(), b"stale executable")

    def test_build_log_cannot_be_executable_before_build(self):
        self.log = self.exe
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "build log must not alias the executable"):
                self.provenance()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.exe.read_bytes(), b"stale executable")

    def test_build_log_hardlink_to_executable_is_rejected_before_build(self):
        self.log.unlink()
        self.log.hardlink_to(self.exe)
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "build log must not alias the executable"):
                self.provenance()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.exe.read_bytes(), b"stale executable")

    def test_build_log_tracked_in_overlapping_build_directory_is_rejected(self):
        self.tracked_paths = ["build/build.log"]
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "build log must not alias a tracked source file"):
                self.provenance()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.log.read_text(encoding="utf-8"), "unrelated old successful build")

    def test_build_log_hardlink_to_tracked_source_is_rejected_before_build(self):
        tracked = self.source / "driver.cpp"
        tracked.write_bytes(b"tracked source")
        self.tracked_paths = ["driver.cpp"]
        self.log.unlink()
        self.log.hardlink_to(tracked)
        with patch.object(collect.subprocess, "run", side_effect=self.build_process):
            with self.assertRaisesRegex(ValueError, "build log must not alias a tracked source file"):
                self.provenance()
        self.assertEqual(self.commands, [])
        self.assertEqual(tracked.read_bytes(), b"tracked source")

    def test_tracked_source_guard_covers_repository_root_from_nested_working_directory(self):
        tracked = self.source / "driver.cpp"
        tracked.write_bytes(b"tracked source")
        self.real_check_output(["git", "init", "--quiet"], cwd=self.source)
        self.real_check_output(["git", "add", "driver.cpp"], cwd=self.source)
        self.log.unlink()
        self.log.hardlink_to(tracked)
        def git_from_nested_directory(*args):
            return self.real_check_output(["git", *args], cwd=self.exe.parent,
                                          text=True, encoding="utf-8").strip()
        with patch.object(collect, "_git", side_effect=git_from_nested_directory):
            with self.assertRaisesRegex(ValueError, "build log must not alias a tracked source file"):
                collect._validate_build_log(self.log, self.build, self.exe, self.source)
        self.assertEqual(tracked.read_bytes(), b"tracked source")

    def assert_main_preflight_rejects(self, message):
        stderr = io.StringIO()
        with patch.object(collect.subprocess, "run", side_effect=AssertionError(
                "build or driver launched before preflight rejection")), \
                patch.object(collect.sys, "stderr", stderr):
            with self.assertRaises(SystemExit) as failure:
                self.main()
        self.assertEqual(failure.exception.code, 2)
        self.assertIn(message, stderr.getvalue())

    def test_build_log_inside_output_is_rejected_before_build(self):
        self.out = self.build / "collection"
        self.log = self.out / "fresh.json"
        self.assert_main_preflight_rejects("build log and output directory must not overlap")
        self.assertFalse(self.out.exists())
        self.assertEqual(self.exe.read_bytes(), b"stale executable")

    def test_output_inside_build_log_is_rejected_before_build(self):
        self.log = self.build / "fresh.json"
        self.out = self.log / "collection"
        self.assert_main_preflight_rejects("build log and output directory must not overlap")
        self.assertFalse(self.log.exists())

    def test_equal_build_log_and_output_is_rejected_before_build(self):
        self.log = self.out = self.build / "collection"
        self.assert_main_preflight_rejects("build log and output directory must not overlap")
        self.assertFalse(self.out.exists())

    def test_existing_output_is_rejected_before_build(self):
        self.out.mkdir()
        sentinel = self.out / "saved.txt"
        sentinel.write_bytes(b"previous collection")
        self.assert_main_preflight_rejects("output directory must not already exist")
        self.assertEqual(sentinel.read_bytes(), b"previous collection")
        self.assertEqual(self.exe.read_bytes(), b"stale executable")

    def test_missing_concurrent_work_note_is_rejected_before_build(self):
        self.note.unlink()
        self.assert_main_preflight_rejects("concurrent-work note must be readable")
        self.assertFalse(self.out.exists())
        self.assertEqual(self.exe.read_bytes(), b"stale executable")


if __name__ == "__main__":
    unittest.main()

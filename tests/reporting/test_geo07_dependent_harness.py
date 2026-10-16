"""Synthetic admission tests for the frozen GEO-07 dependent-sum harness."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "geo07_dependent_collect", ROOT / "scripts/reports/geo07_dependent/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def raw_rows(repetitions=7, batch=5):
    names = list(collect.EXPECTED)
    order = [(name, 0, True) for name in names]
    order += [(name, index, False) for index in range(repetitions)
              for name in (names if index % 2 == 0 else names[::-1])]
    return [{"schema": collect.TRIAL_SCHEMA, "fixture": name, "round": index,
             "warmup": warmup, "batch": batch, "checked_calls": batch,
             "elapsed_ns": 50_000_000 + index, "status": "passed", "error": None,
             "result": deepcopy(collect.EXPECTED[name])} for name, index, warmup in order]


def encoded(rows):
    return b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)


class DependentHarness(unittest.TestCase):
    def test_exact_source_and_authored_input_catalogue(self):
        self.assertEqual(collect.SOURCE, "5411e37ad456f0d5b3bf775130f149622ef5ebfa")
        self.assertEqual(list(collect.INPUTS), ["shared_cancellation", "constrained_shared"])
        self.assertEqual(collect.INPUTS["constrained_shared"]["right"]["equalities"],
                         {"rows": 1, "cols": 2, "values": [1.0, 1.0]})
        description = {"schema": collect.DESCRIPTION_SCHEMA, "source_commit": collect.SOURCE,
                       "module": "CSL::generator_adapter",
                       "registration": "csl.geometry.generators.operations@1.1.0",
                       "scalar": "binary64", "fixtures": list(collect.EXPECTED),
                       "timed_scope": collect.INTERVAL, "inputs": collect.INPUTS}
        payload, hashes = collect.admit_description(encoded([description]))
        self.assertEqual(payload, collect.json_bytes(collect.INPUTS))
        self.assertEqual(hashes["constrained_shared"], hashlib.sha256(
            collect.json_bytes(collect.INPUTS["constrained_shared"])).hexdigest())
        for mutate in (
            lambda row: row["inputs"]["constrained_shared"]["right"]["equalities"]["values"].__setitem__(1, 2),
            lambda row: row["inputs"]["shared_cancellation"]["public_request"].update({"registration_version": "1.0.0"}),
            lambda row: row.update({"source_commit": "0" * 40}),
            lambda row: row.update({"timed_scope": "operation only"}),
        ):
            candidate = deepcopy(description)
            mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_description(encoded([candidate]))

    def test_smoke_and_measure_rows_require_literal_outputs_and_complete_work(self):
        rows, summary = collect.admit_rows(encoded(raw_rows()), repetitions=7, batch=5)
        self.assertEqual(len(rows), 16)
        self.assertEqual(summary["constrained_shared"]["successes"], 7)
        self.assertEqual([row["fixture"] for row in rows[4:6]],
                         ["constrained_shared", "shared_cancellation"])
        smoke = raw_rows(repetitions=0, batch=1)[:2]
        for row in smoke:
            row["warmup"] = False
            row["elapsed_ns"] = 1
        self.assertEqual(len(collect.admit_rows(encoded(smoke), repetitions=1, batch=1,
                                                 smoke=True)[0]), 2)
        for mutate in (
            lambda value: value[3]["result"]["equalities"].append(9),
            lambda value: value[3].update({"checked_calls": 0}),
            lambda value: value[3].update({"status": "oracle_failed"}),
            lambda value: value[3].update({"elapsed_ns": 19_999_999}),
            lambda value: value.pop(),
        ):
            candidate = raw_rows()
            mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_rows(encoded(candidate), repetitions=7, batch=5)
        with self.assertRaises(ValueError):
            collect.admit_rows(encoded(raw_rows(repetitions=6)), repetitions=6, batch=5)
        for bad in (encoded(raw_rows())[:-1],
                    encoded(raw_rows()).replace(b'"schema":', b'"schema":"dup","schema":', 1)):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                collect.admit_rows(bad, repetitions=7, batch=5)

    def test_fresh_checkout_seal_requires_metadata_only_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Harness Test")
            git("config", "user.email", "harness@example.invalid")
            git("config", "core.autocrlf", "false")
            source = root / "src" / "geometry" / "generators" / "adapter.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("source\n")
            git("add", ".")
            git("commit", "-qm", "source")
            old_source = collect.SOURCE
            try:
                collect.SOURCE = git("rev-parse", "HEAD")
                harness = root / "scripts" / "reports" / "geo07_dependent" / "collect.py"
                harness.parent.mkdir(parents=True)
                harness.write_text("harness\n")
                git("add", ".")
                git("commit", "-qm", "harness")
                reviewed = git("rev-parse", "HEAD")
                tree = git("rev-parse", "HEAD^{tree}")
                self.assertEqual(collect.admit_source(root, reviewed, sealed=False)["source_commit"],
                                 collect.SOURCE)
                seal = {"schema": collect.SCHEMA + "-review-seal/1",
                        "source_commit": collect.SOURCE, "reviewed_code_commit": reviewed,
                        "reviewed_code_tree": tree}
                (root / collect.SEAL_PATH).write_bytes(collect.json_bytes(seal))
                git("add", ".")
                git("commit", "-qm", "seal")
                head = git("rev-parse", "HEAD")
                self.assertEqual(collect.admit_source(root, head, sealed=True)["reviewed_code_commit"],
                                 reviewed)
                driver = root / "benchmarks" / "reporting" / "geo07_dependent" / "driver.cpp"
                driver.parent.mkdir(parents=True)
                driver.write_text("later code\n")
                git("add", ".")
                git("commit", "-qm", "later code")
                with self.assertRaises(ValueError):
                    collect.admit_source(root, git("rev-parse", "HEAD"), sealed=True)
                (root / collect.SEAL_PATH).write_text("{}\n")
                with self.assertRaises(ValueError):
                    collect.admit_source(root, git("rev-parse", "HEAD"), sealed=True)
            finally:
                collect.SOURCE = old_source

    def test_failed_process_retains_exact_partial_output_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = ["python", "-c", "import sys; sys.stdout.buffer.write(b'partial\\r\\n'); sys.stderr.buffer.write(b'failure\\n'); sys.exit(2)"]
            stdout, stderr, code, timeout = collect.captured(command, root, root / "attempt", "trials", 5)
            self.assertEqual((stdout, stderr, code, timeout), (b"partial\r\n", b"failure\n", 2, False))
            self.assertEqual((root / "attempt" / "trials.stdout").read_bytes(), stdout)
            self.assertEqual((root / "attempt" / "trials.stderr").read_bytes(), stderr)
            capture = json.loads((root / "attempt" / "trials.capture.json").read_text())
            self.assertEqual(capture["stdout_sha256"], hashlib.sha256(stdout).hexdigest())
            self.assertEqual(capture["exit_code"], 2)

    def test_timeout_retains_partial_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = ["python", "-c", "import sys,time; sys.stdout.buffer.write(b'partial\\n'); sys.stdout.flush(); sys.stderr.buffer.write(b'waiting\\n'); sys.stderr.flush(); time.sleep(2)"]
            stdout, stderr, code, timeout = collect.captured(command, root, root / "attempt", "build", 0.2)
            self.assertEqual((stdout, stderr, code, timeout), (b"partial\n", b"waiting\n", None, True))
            self.assertEqual((root / "attempt" / "build.stdout").read_bytes(), stdout)
            self.assertEqual((root / "attempt" / "build.stderr").read_bytes(), stderr)
            capture = json.loads((root / "attempt" / "build.capture.json").read_text())
            self.assertTrue(capture["timed_out"])

    def test_release_gate_checks_algorithm_link_and_x64_flags(self):
        build = Path("C:/review/build")
        settings = {**collect.RELEASE_FLAGS,
                    "CSL_BUILD_GEO07_DEPENDENT_REPORT": "ON", "CSL_ENABLE_HIGHS": "OFF",
                    "CSL_ENABLE_QHULL": "OFF", "CMAKE_GENERATOR": "Visual Studio 17 2022",
                    "CMAKE_GENERATOR_PLATFORM": "x64"}
        common = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                  "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                  "PreprocessorDefinitions": "NDEBUG;OTHER"}
        projects = {name: {"compile": {**common, "AdditionalOptions": ""},
                           "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}}
                    for name in ("adapter_library", "generator_library")}
        projects["driver"] = {"compile": {**common, "AdditionalOptions":
                              '%(AdditionalOptions) /external:I "C:/review/build/_deps/csl_json-src/include"'},
                              "link": {"AdditionalDependencies":
                                       "Release\\csl_generator_adapter.lib;Release\\csl_geometry_generators.lib"}}
        collect.admit_release(settings, projects, build)
        altered = deepcopy(projects)
        altered["driver"]["link"]["AdditionalDependencies"] = "Release\\csl_generator_adapter.lib"
        with self.assertRaises(ValueError):
            collect.admit_release(settings, altered, build)
        altered = deepcopy(settings)
        altered["CMAKE_CXX_FLAGS_RELEASE"] = "/Od /DNDEBUG"
        with self.assertRaises(ValueError):
            collect.admit_release(altered, projects, build)


if __name__ == "__main__":
    unittest.main()

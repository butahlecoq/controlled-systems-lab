"""Synthetic GEO-07 registered-port report admission tests; no timed runs."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "geo07_port_collect", ROOT / "scripts/reports/geo07_port/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def encoded(rows):
    return b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)


def fake_rows(repetitions=7, batch=5):
    names = list(collect.EXPECTED)
    order = [(name, 0, True) for name in names]
    order += [(name, index, False) for index in range(repetitions)
              for name in (names if index % 2 == 0 else names[::-1])]
    return [{"schema": collect.TRIAL_SCHEMA, "fixture": name, "round": index,
             "warmup": warmup, "batch": batch, "checked_calls": batch,
             "elapsed_ns": 50_000_000 + index, "status": "passed", "error": None,
             "result": deepcopy(collect.EXPECTED[name])} for name, index, warmup in order]


class PortReportAdmission(unittest.TestCase):
    def test_review_seal_rejects_forged_sha_and_later_clean_code_commit(self):
        code, sealed, later, tree = "a" * 40, "b" * 40, "c" * 40, "d" * 40
        seal = {"schema": "csl.geo07-port-review-seal/1", "source_commit": collect.SOURCE,
                "reviewed_code_commit": code, "reviewed_code_tree": tree}
        collect.admit_reviewed_head(sealed, sealed, code, tree,
                                    {collect.SEAL_PATH}, seal)
        for actual, claimed, parent, changed in (
            (later, later, sealed, {"benchmarks/reporting/geo07_port/adapter_driver.cpp"}),
            (later, later, code, {"benchmarks/reporting/geo07_port/adapter_driver.cpp", collect.SEAL_PATH}),
            (later, sealed, code, {collect.SEAL_PATH}),
        ):
            with self.subTest(actual=actual, parent=parent, changed=changed), self.assertRaises(ValueError):
                collect.admit_reviewed_head(actual, claimed, parent, tree, changed, seal)

    def test_real_checkout_admission_rejects_later_clean_code_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Harness Test")
            git("config", "user.email", "harness@example.invalid")
            git("config", "core.autocrlf", "false")
            code = root / "adapter_driver.cpp"
            code.write_text("reviewed code\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "reviewed code")
            reviewed = git("rev-parse", "HEAD")
            seal_path = root / collect.SEAL_PATH
            seal_path.parent.mkdir(parents=True)
            seal_path.write_bytes(collect.json_bytes({
                "schema": "csl.geo07-port-review-seal/1", "source_commit": collect.SOURCE,
                "reviewed_code_commit": reviewed,
                "reviewed_code_tree": git("rev-parse", "HEAD^{tree}")}))
            git("add", ".")
            git("commit", "-qm", "seal reviewed code")
            sealed = git("rev-parse", "HEAD")
            self.assertEqual(collect.admit_checkout(root, sealed)[:2], (sealed, reviewed))
            with self.assertRaises(ValueError):
                collect.admit_checkout(root, reviewed)
            code.write_text("later unreviewed code\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "later code")
            with self.assertRaises(ValueError):
                collect.admit_checkout(root, git("rev-parse", "HEAD"))

    def test_host_preflight_requires_fresh_idle_structured_observation(self):
        build_end = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        start = build_end + timedelta(seconds=8)
        note = {"schema": "csl.geo07-port-host-observation/1",
                "observed_utc": (build_end + timedelta(seconds=5)).isoformat(),
                "cpu_load_percent": 7, "logical_processors": 16,
                "build_processes": {"cmake": 0, "MSBuild": 0, "cl": 0}}
        raw = collect.json_bytes(note)
        self.assertEqual(collect.admit_host_observation(raw, build_end, start), note)
        for change in (
            lambda item: item.update({"observed_utc": (build_end - timedelta(seconds=1)).isoformat()}),
            lambda item: item.update({"observed_utc": (start - timedelta(seconds=31)).isoformat()}),
            lambda item: item.update({"cpu_load_percent": 90}),
            lambda item: item["build_processes"].update({"cl": 1}),
            lambda item: item.pop("logical_processors"),
        ):
            candidate = deepcopy(note)
            change(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                collect.admit_host_observation(collect.json_bytes(candidate), build_end, start)
        with self.assertRaises(ValueError):
            collect.admit_host_observation(raw, build_end, start + timedelta(seconds=31))
        with self.assertRaises(ValueError):
            collect.admit_host_observation(b"idle host confirmed", build_end, start)

    def test_saved_host_and_collection_window_bind_exact_bytes(self):
        raw = b'{"schema":"csl.geo07-port-host-observation/1"}\r\n'
        start, end = "2026-10-16T12:00:08+00:00", "2026-10-16T12:00:10+00:00"
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            collect.save_host_observation(out, raw)
            collect.save_capture(out, b'{}\r\n', b"", 0, ["driver", "--measure"],
                                 collection_start_utc=start, collection_end_utc=end)
            self.assertEqual((out / "host-observation.json").read_bytes(), raw)
            capture = json.loads((out / "process-capture.json").read_bytes())
            self.assertEqual(capture["host_observation_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual((capture["collection_start_utc"], capture["collection_end_utc"]),
                             (start, end))
            self.assertEqual(collect.manifest(out, "test")["files"]["host-observation.json"],
                             hashlib.sha256(raw).hexdigest())

    def test_frozen_source_and_report_only_delta(self):
        self.assertEqual(collect.SOURCE, "41b4b58f2ef982e75554519862afdd803e30f717")
        collect.admit_changed_paths({"CMakeLists.txt", "cmake/OptionalReports.cmake",
                                     "benchmarks/reporting/geo07_port/adapter_driver.cpp"})
        with self.assertRaises(ValueError):
            collect.admit_changed_paths({"src/geometry/generators/adapter.cpp"})

    def test_description_binds_literal_inputs_scope_and_per_fixture_hashes(self):
        self.assertEqual(list(collect.INPUTS),
                         ["affine_box", "constrained_disjoint_sum", "finite_v"])
        self.assertEqual(collect.INPUTS["affine_box"]["source"]["center"], [1.0, 2.0])
        self.assertEqual(collect.INPUTS["constrained_disjoint_sum"]["right"]["equalities"],
                         {"rows": 1, "cols": 2, "values": [1.0, 1.0]})
        self.assertEqual(collect.INPUTS["finite_v"]["vertex_cap"], 4)
        self.assertEqual(collect.INPUTS["finite_v"]["public_request"],
                         {"problem_id": "geo07-port", "request_id": "finite-v",
                          "assurance": "numerical", "prepared_scalar": "binary64",
                          "prepared_output_relation": "equivalent"})
        description = {"schema": collect.DESCRIPTION_SCHEMA,
                       "source_commit": collect.SOURCE, "module": "CSL::generator_adapter",
                       "scalar": "binary64", "fixtures": list(collect.EXPECTED),
                       "timed_scope": collect.INTERVAL, "inputs": collect.INPUTS}
        payload, hashes = collect.admit_description(encoded([description]))
        self.assertEqual(payload, collect.json_bytes(collect.INPUTS))
        self.assertEqual(hashes["finite_v"], hashlib.sha256(
            collect.json_bytes(collect.INPUTS["finite_v"])).hexdigest())
        for mutate in (
            lambda value: value.update({"timed_scope": "operations only"}),
            lambda value: value["inputs"]["affine_box"]["affine_map"]["values"].__setitem__(0, 9),
            lambda value: value["inputs"]["constrained_disjoint_sum"]["right"]["equalities"]["values"].__setitem__(1, 9),
            lambda value: value["inputs"]["finite_v"].update({"vertex_cap": 3}),
            lambda value: value["inputs"]["finite_v"]["public_request"].update({"assurance": "validated"}),
        ):
            candidate = deepcopy(description)
            mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_description(encoded([candidate]))

    def test_raw_rows_require_alternating_complete_checked_literal_batches(self):
        rows, summary = collect.admit_raw(encoded(fake_rows()), repetitions=7, batch=5)
        self.assertEqual(len(rows), 24)
        self.assertEqual([row["fixture"] for row in rows[6:9]],
                         ["finite_v", "constrained_disjoint_sum", "affine_box"])
        self.assertEqual(summary["finite_v"]["successes"], 7)
        for mutate in (
            lambda value: value[4]["result"].update({"vertices": [9]}),
            lambda value: value[4].update({"checked_calls": 0}),
            lambda value: value[4].update({"fixture": "finite_v"}),
            lambda value: value[4].update({"status": "oracle_failed"}),
            lambda value: value[4].update({"elapsed_ns": 19_999_999}),
            lambda value: value.pop(),
        ):
            candidate = fake_rows()
            mutate(candidate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_raw(encoded(candidate), repetitions=7, batch=5)

    def test_duplicate_nonfinite_unterminated_and_short_profile_rejected(self):
        raw = encoded(fake_rows())
        for bad in (raw.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
                    raw.replace(b'50000000', b'NaN', 1), raw[:-1]):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                collect.admit_raw(bad, repetitions=7, batch=5)
        with self.assertRaises(ValueError):
            collect.admit_raw(raw, repetitions=6, batch=5)

    def test_release_gate_checks_both_algorithm_libraries(self):
        build = Path("C:/reviewed/build")
        cache = {**collect.RELEASE_FLAGS, "CSL_BUILD_GEO07_PORT_REPORT": "ON",
                 "CSL_ENABLE_HIGHS": "OFF", "CSL_ENABLE_QHULL": "OFF",
                 "BUILD_TESTING": "OFF",
                 "CMAKE_GENERATOR": "Visual Studio 17 2022", "CMAKE_GENERATOR_PLATFORM": "x64"}
        common = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                  "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                  "PreprocessorDefinitions": "NDEBUG;OTHER"}
        targets = {name: {"compile": {**common, "AdditionalOptions": ""},
                          "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}}
                   for name in ("adapter_library", "generator_library")}
        targets["driver"] = {"compile": {**common, "AdditionalOptions":
                             '%(AdditionalOptions) /external:I "C:/reviewed/build/_deps/csl_json-src/include"'},
                             "link": {"GenerateDebugInformation": "false",
                                      "AdditionalOptions": "%(AdditionalOptions) /machine:x64",
                                      "AdditionalDependencies": "Release\\csl_generator_adapter.lib;Release\\csl_geometry_generators.lib"}}
        collect.admit_release(cache, targets, build)
        for change in (
            lambda c, t: c.update({"CMAKE_CXX_FLAGS_RELEASE": "/Od /DNDEBUG"}),
            lambda c, t: c.update({"CSL_ENABLE_HIGHS": "ON"}),
            lambda c, t: c.update({"BUILD_TESTING": "ON"}),
            lambda c, t: t["driver"]["link"].update({"AdditionalDependencies": "kernel32.lib"}),
            lambda c, t: t["driver"]["link"].update({"AdditionalDependencies": "Release\\csl_generator_adapter.lib"}),
            lambda c, t: t["adapter_library"]["compile"].update({"Optimization": "Disabled"}),
            lambda c, t: t["generator_library"]["compile"].update({"Optimization": "Disabled"}),
            lambda c, t: t["generator_library"]["archive"].update({"AdditionalOptions": ""}),
        ):
            candidate_cache, candidate_targets = deepcopy(cache), deepcopy(targets)
            change(candidate_cache, candidate_targets)
            with self.subTest(change=change), self.assertRaises(ValueError):
                collect.admit_release(candidate_cache, candidate_targets, build)

    def test_failure_capture_retains_raw_bytes_and_nonpublishable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            stdout, stderr = b'{"bad":true}\r\n', b"fatal\r\n"
            collect.save_host_observation(out, b'{"observed":"synthetic"}\r\n')
            collect.save_capture(out, stdout, stderr, 2,
                                 ["driver", "--measure", "7", "1", "5"])
            collect.reject(out, "synthetic rejected output")
            self.assertEqual((out / "trials.jsonl").read_bytes(), stdout)
            self.assertEqual((out / "driver.stderr").read_bytes(), stderr)
            self.assertFalse(json.loads((out / "collection-status.json").read_text())["publishable"])
            self.assertEqual(json.loads((out / "process-capture.json").read_text())["stdout_sha256"],
                             hashlib.sha256(stdout).hexdigest())

    def test_crlf_compiler_evidence_and_deterministic_manifest(self):
        for newline in (b"\r\n", b"\n"):
            raw = b'set(CMAKE_CXX_COMPILER_VERSION "19.44.35215.0")' + newline
            self.assertEqual(collect.compiler_version(raw), "19.44.35215.0")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "trials.jsonl").write_bytes(encoded(fake_rows()))
            manifest = collect.manifest(out, "geo07-port-test")
            self.assertEqual(manifest["files"]["trials.jsonl"], hashlib.sha256(
                (out / "trials.jsonl").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()

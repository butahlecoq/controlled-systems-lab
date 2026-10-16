"""Synthetic admission checks for the EXT-04 fixed-source replay report."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ext04_collect", ROOT / "scripts/reports/ext04/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def rows(batch=5, repetitions=7):
    names = list(collect.EXPECTED)
    sequence = [(name, 0, True) for name in names]
    sequence += [(name, index, False) for index in range(repetitions)
                 for name in (names if index % 2 == 0 else names[::-1])]
    return [{"schema": collect.TRIAL_SCHEMA, "fixture": name, "round": index,
             "warmup": warmup, "batch": batch, "checked_calls": batch,
             "elapsed_ns": 30_000_000 + index, "status": "passed", "error": None,
             "result": collect.EXPECTED[name]} for name, index, warmup in sequence]


def encoded(events):
    return b"".join((json.dumps(event, separators=(",", ":")) + "\n").encode() for event in events)


class Admission(unittest.TestCase):
    def test_description_binds_full_authored_inputs_and_scope(self):
        description = {"schema": "csl.ext04-replay-driver/1", "source_commit": collect.SOURCE,
                       "module": "CSL::controllers", "scalar": "binary64",
                       "fixtures": list(collect.EXPECTED), "timed_scope": collect.INTERVAL,
                       "inputs": collect.INPUTS}
        payload, hashes = collect.admit_description(encoded([description]))
        self.assertEqual(payload, collect.json_bytes(collect.INPUTS))
        self.assertEqual(hashes["post_feedthrough"],
                         hashlib.sha256(collect.json_bytes(collect.INPUTS["post_feedthrough"])).hexdigest())
        candidate = deepcopy(description)
        candidate["inputs"]["post_feedthrough"]["channels"][0]["Du"] = [0]
        with self.assertRaises(ValueError):
            collect.admit_description(encoded([candidate]))

    def test_release_gate_rejects_unreviewed_flags_and_library(self):
        build = Path("C:/reviewed/build")
        settings = {**collect.RELEASE_FLAGS, "CSL_BUILD_EXT04_REPORT": "ON",
                    "CSL_ENABLE_HIGHS": "OFF", "CSL_ENABLE_QHULL": "OFF",
                    "BUILD_TESTING": "OFF", "CMAKE_GENERATOR": "Visual Studio 17 2022",
                    "CMAKE_GENERATOR_PLATFORM": "x64"}
        compile_flags = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                         "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                         "PreprocessorDefinitions": "NDEBUG;OTHER"}
        targets = {
            "driver": {"compile": {**compile_flags, "AdditionalOptions":
                       '%(AdditionalOptions) /external:I "C:/reviewed/build/_deps/csl_json-src/include"'},
                       "link": {"GenerateDebugInformation": "false",
                                "AdditionalOptions": "%(AdditionalOptions) /machine:x64",
                                "AdditionalDependencies": "Release\\csl_controllers.lib"}},
            "controller_library": {"compile": {**compile_flags, "AdditionalOptions": ""},
                                   "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}},
        }
        collect.admit_release(settings, targets, build)
        for change in (lambda c, t: c.update({"CMAKE_CXX_FLAGS_RELEASE": "/Od /DNDEBUG"}),
                       lambda c, t: t["driver"]["link"].update({"AdditionalDependencies": "kernel32.lib"}),
                       lambda c, t: t["controller_library"]["compile"].update({"Optimization": "Disabled"})):
            c, t = deepcopy(settings), deepcopy(targets)
            change(c, t)
            with self.subTest(change=change), self.assertRaises(ValueError):
                collect.admit_release(c, t, build)

    def test_compiler_version_accepts_crlf_but_rejects_ambiguous_evidence(self):
        version = b'set(CMAKE_CXX_COMPILER_VERSION "19.44.35215.0")'
        self.assertEqual(collect.compiler_version(version + b"\r\n"), "19.44.35215.0")
        self.assertEqual(collect.compiler_version(version + b"\n"), "19.44.35215.0")
        with self.assertRaises(ValueError):
            collect.compiler_version(version + b"\n" + version + b"\n")

    def test_complete_alternating_rows_have_literal_results(self):
        admitted, summary = collect.admit_raw(encoded(rows()), repetitions=7, batch=5)
        self.assertEqual(len(admitted), 24)
        self.assertEqual([event["fixture"] for event in admitted[6:9]],
                         list(reversed(collect.EXPECTED)))
        self.assertEqual(summary["partial_noisy_delayed"]["successes"], 7)

    def test_wrong_oracle_missing_work_and_partial_stream_are_rejected(self):
        for mutate in (
            lambda events: events[4]["result"]["states"][-1].__setitem__(0, 8),
            lambda events: events[4].update({"checked_calls": 0}),
            lambda events: events[4].update({"status": "oracle_failed"}),
            lambda events: events.pop(),
        ):
            events = json.loads(json.dumps(rows()))
            mutate(events)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_raw(encoded(events), repetitions=7, batch=5)
        raw = encoded(rows())
        for bad in (raw[:-1], raw.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
                    raw.replace(b'30000000', b'NaN', 1)):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                collect.admit_raw(bad, repetitions=7, batch=5)

    def test_failed_capture_preserves_exact_raw_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            stdout, stderr = b'{"partial":true}\r\n', b"failed\r\n"
            collect.save_capture(output, stdout, stderr, 2, ["driver", "--measure", "7", "1", "5"])
            collect.reject(output, "synthetic failure")
            self.assertEqual((output / "trials.jsonl").read_bytes(), stdout)
            self.assertEqual((output / "driver.stderr").read_bytes(), stderr)
            self.assertEqual(json.loads((output / "process-capture.json").read_text())["stdout_sha256"],
                             hashlib.sha256(stdout).hexdigest())
            self.assertEqual(json.loads((output / "process-capture.json").read_text())["command"],
                             ["REPORT_EXE", "--measure", "7", "1", "5"])
            self.assertFalse(json.loads((output / "collection-status.json").read_text())["publishable"])


if __name__ == "__main__":
    unittest.main()

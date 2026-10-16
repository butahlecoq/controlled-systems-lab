"""GEO-07 report admission tests use synthetic rows, never measured runs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("geo07_collect", ROOT / "scripts/reports/geo07/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def fake_rows(repetitions=7, batch=5):
    names = list(collect.EXPECTED)
    sequence = [(name, 0, True) for name in names]
    sequence += [(name, index, False) for index in range(repetitions)
                 for name in (names if index % 2 == 0 else names[::-1])]
    return [{"schema": collect.TRIAL_SCHEMA, "fixture": name, "round": index,
             "warmup": warmup, "batch": batch, "checked_calls": batch,
             "elapsed_ns": 50_000_000 + index, "status": "passed", "error": None,
             "result": json.loads(json.dumps(collect.EXPECTED[name]))} for name, index, warmup in sequence]


def encoded(rows):
    return b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)


class ReportAdmission(unittest.TestCase):
    def test_release_gate_rejects_changed_flags_or_library(self):
        build = Path("C:/reviewed/build")
        cache = {**collect.RELEASE_FLAGS, "CSL_BUILD_GEO07_REPORT": "ON",
                 "CMAKE_GENERATOR": "Visual Studio 17 2022", "CMAKE_GENERATOR_PLATFORM": "x64"}
        common = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                  "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                  "PreprocessorDefinitions": "NDEBUG;OTHER"}
        targets = {
            "driver": {"compile": {**common, "AdditionalOptions":
                       '%(AdditionalOptions) /external:I "C:/reviewed/build/_deps/csl_json-src/include"'},
                       "link": {"GenerateDebugInformation": "false",
                                "AdditionalOptions": "%(AdditionalOptions) /machine:x64",
                                "AdditionalDependencies": "Release\\csl_geometry_generators.lib"}},
            "generator_library": {"compile": {**common, "AdditionalOptions": ""},
                                  "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}},
        }
        collect.admit_release(cache, targets, build)
        for change in (lambda c, t: c.update({"CMAKE_CXX_FLAGS_RELEASE": "/Od /DNDEBUG"}),
                       lambda c, t: t["driver"]["link"].update({"AdditionalDependencies": "kernel32.lib"}),
                       lambda c, t: t["generator_library"]["compile"].update({"Optimization": "Disabled"})):
            c, t = deepcopy(cache), deepcopy(targets)
            change(c, t)
            with self.subTest(change=change), self.assertRaises(ValueError):
                collect.admit_release(c, t, build)

    def test_literal_rows_and_alternating_order(self):
        rows, summary = collect.admit_raw(encoded(fake_rows()), repetitions=7, batch=5)
        self.assertEqual(len(rows), 24)
        self.assertEqual([row["fixture"] for row in rows[6:9]],
                         ["constrained_sum", "shared_cancellation", "box_image"])
        self.assertEqual(summary["box_image"]["attempts"], 7)
        self.assertEqual(summary["box_image"]["failures"], 0)

    def test_rejects_wrong_oracle_work_and_missing_row(self):
        for mutate in (lambda rows: rows[4]["result"].update({"generators": [9]}),
                       lambda rows: rows[4]["result"].update({"generators": [False]}),
                       lambda rows: rows[4].update({"checked_calls": 0}),
                       lambda rows: rows[4].update({"fixture": "box_image"}),
                       lambda rows: rows[4].update({"status": "oracle_failed"}),
                       lambda rows: rows.pop()):
            rows = fake_rows()
            mutate(rows)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_raw(encoded(rows), repetitions=7, batch=5)

    def test_rejects_duplicate_keys_nonfinite_and_short_interval(self):
        rows = fake_rows()
        rows[3]["elapsed_ns"] = 1
        with self.assertRaises(ValueError):
            collect.admit_raw(encoded(rows), repetitions=7, batch=5)
        rows = fake_rows()
        raw = encoded(rows)
        for bad in (raw.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
                    raw.replace(b'50000000', b'NaN', 1), raw[:-1]):
            with self.subTest(raw=bad[:40]), self.assertRaises(ValueError):
                collect.admit_raw(bad, repetitions=7, batch=5)

    def test_failure_capture_keeps_exact_bytes_and_nonpublishable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            stdout, stderr = b'{"bad":true}\r\n', b"fatal\r\n"
            collect.save_capture(out, stdout, stderr, 2, ["driver", "--measure", "7", "1", "5"])
            collect.reject(out, "synthetic rejected output")
            self.assertEqual((out / "trials.jsonl").read_bytes(), stdout)
            self.assertEqual((out / "driver.stderr").read_bytes(), stderr)
            self.assertFalse(json.loads((out / "collection-status.json").read_text())["publishable"])
            self.assertEqual(json.loads((out / "process-capture.json").read_text())["stdout_sha256"],
                             hashlib.sha256(stdout).hexdigest())

    def test_deterministic_records_and_manifest_bytes(self):
        rows, summary = collect.admit_raw(encoded(fake_rows()), repetitions=7, batch=5)
        payload = {"schema": collect.RECORD_SCHEMA, "rows": rows, "summary": summary}
        self.assertEqual(collect.json_bytes(payload), collect.json_bytes(payload))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "trials.jsonl").write_bytes(encoded(fake_rows()))
            (out / "records.json").write_bytes(collect.json_bytes(payload))
            manifest = collect.manifest(out, "geo07-test")
            self.assertEqual(manifest["files"]["records.json"],
                             hashlib.sha256((out / "records.json").read_bytes()).hexdigest())
            self.assertNotIn("manifest.json", manifest["files"])


if __name__ == "__main__":
    unittest.main()

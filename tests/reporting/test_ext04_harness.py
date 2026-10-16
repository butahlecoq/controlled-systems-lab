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
        candidate = deepcopy(description)
        candidate["timed_scope"] = candidate["timed_scope"].replace("result JSON construction and assignment/replacement",
                                                                  "result JSON construction")
        with self.assertRaises(ValueError):
            collect.admit_description(encoded([candidate]))

    def test_release_gate_rejects_unreviewed_flags_and_library(self):
        build = Path("C:/reviewed/build")
        settings = {**collect.RELEASE_FLAGS, "CSL_BUILD_EXT04_REPORT": "ON",
                    "CSL_ENABLE_HIGHS": "OFF", "CSL_ENABLE_QHULL": "OFF",
                    "BUILD_TESTING": "OFF", "CMAKE_GENERATOR": "Visual Studio 17 2022",
                    "CMAKE_GENERATOR_PLATFORM": "x64", "CMAKE_GENERATOR_TOOLSET": "",
                    "CMAKE_GENERATOR_INSTANCE": "C:/Program Files/Microsoft Visual Studio/2022/Community"}
        compile_flags = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                         "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                         "PreprocessorDefinitions": "NDEBUG;OTHER"}
        targets = {
            "driver": {"configuration": {"PlatformToolset": "v143"},
                       "compile": {**compile_flags, "AdditionalOptions":
                       '%(AdditionalOptions) /external:I "C:/reviewed/build/_deps/csl_json-src/include"'},
                       "link": {"GenerateDebugInformation": "false",
                                "AdditionalOptions": "%(AdditionalOptions) /machine:x64",
                                "AdditionalDependencies": "Release\\csl_controllers.lib"}},
            "controller_library": {"configuration": {"PlatformToolset": "v143"},
                                   "compile": {**compile_flags, "AdditionalOptions": ""},
                                   "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}},
        }
        collect.admit_release(settings, targets, build)
        for change in (lambda c, t: c.update({"CMAKE_CXX_FLAGS_RELEASE": "/Od /DNDEBUG"}),
                       lambda c, t: c.update({"CMAKE_GENERATOR_TOOLSET": "ClangCL"}),
                       lambda c, t: t["driver"]["configuration"].update({"PlatformToolset": "ClangCL"}),
                       lambda c, t: t["driver"]["link"].update({"AdditionalDependencies": "kernel32.lib"}),
                       lambda c, t: t["controller_library"]["compile"].update({"Optimization": "Disabled"})):
            c, t = deepcopy(settings), deepcopy(targets)
            change(c, t)
            with self.subTest(change=change), self.assertRaises(ValueError):
                collect.admit_release(c, t, build)

    def test_compiler_identity_requires_fixed_msvc_path_and_unambiguous_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "Microsoft Visual Studio/2022/Community"
            compiler = instance / "VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"synthetic compiler")
            settings = {"CMAKE_GENERATOR_INSTANCE": instance.as_posix(),
                        "CMAKE_GENERATOR_TOOLSET": ""}
            lines = [f'set(CMAKE_CXX_COMPILER "{compiler.as_posix()}")',
                     'set(CMAKE_CXX_COMPILER_ID "MSVC")',
                     'set(CMAKE_CXX_COMPILER_VERSION "19.44.35215.0")',
                     'set(CMAKE_CXX_COMPILER_FRONTEND_VARIANT "MSVC")',
                     'set(CMAKE_CXX_COMPILER_ARCHITECTURE_ID x64)']
            raw = ("\n".join(lines) + "\n").encode()
            identity = collect.compiler_identity(raw.replace(b"\n", b"\r\n"), settings)
            self.assertEqual(identity["id"], "MSVC")
            self.assertEqual(identity["toolset"], "v143")
            self.assertEqual(identity["path"], compiler.resolve().as_posix())
            for candidate in (raw.replace(b'ID "MSVC"', b'ID "Clang"'),
                              raw.replace(b'VERSION "19.44.35215.0"', b'VERSION "99.99.99"'),
                              raw.replace(b'Hostx64/x64/cl.exe', b'Hostx64/x64/clang-cl.exe'),
                              raw + (lines[1] + "\n").encode()):
                with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                    collect.compiler_identity(candidate, settings)
            with self.assertRaises(ValueError):
                collect.compiler_identity(raw, {**settings, "CMAKE_GENERATOR_TOOLSET": "ClangCL"})

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

    def test_replay_event_identity_mutations_are_rejected(self):
        mutations = (
            lambda result: result["decision_stages"].__setitem__(0, 1),
            lambda result: result["released"][0].__setitem__("sample", 1),
            lambda result: result["available"][1][0].__setitem__("channel", 1),
            lambda result: result["available"][1][0].__setitem__("released_index", 1),
            lambda result: result["available"][1][1].__setitem__("released_at", "after(0)"),
        )
        for mutate in mutations:
            events = deepcopy(rows())
            mutate(events[3]["result"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collect.admit_raw(encoded(events), repetitions=7, batch=5)

    def test_failed_capture_preserves_exact_raw_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            stdout, stderr = b'{"partial":true}\r\n', b"failed\r\n"
            collect.save_capture(output, stdout, stderr, 2, ["driver", "--measure", "7", "1", "5"])
            cache, compiler = b"CMAKE_GENERATOR_TOOLSET:INTERNAL=\r\n", b'set(CMAKE_CXX_COMPILER_ID "MSVC")\r\n'
            collect.save_build_evidence(output, cache, compiler, b"build\r\n", b"warning\r\n")
            collect.reject(output, "synthetic failure")
            self.assertEqual((output / "trials.jsonl").read_bytes(), stdout)
            self.assertEqual((output / "driver.stderr").read_bytes(), stderr)
            self.assertEqual((output / "CMakeCache.raw.txt").read_bytes(), cache)
            self.assertEqual((output / "CMakeCXXCompiler.raw.cmake").read_bytes(), compiler)
            self.assertEqual(collect.manifest(output, "synthetic")["files"]["CMakeCache.raw.txt"],
                             hashlib.sha256(cache).hexdigest())
            self.assertEqual(json.loads((output / "process-capture.json").read_text())["stdout_sha256"],
                             hashlib.sha256(stdout).hexdigest())
            self.assertEqual(json.loads((output / "process-capture.json").read_text())["command"],
                             ["REPORT_EXE", "--measure", "7", "1", "5"])
            self.assertFalse(json.loads((output / "collection-status.json").read_text())["publishable"])


if __name__ == "__main__":
    unittest.main()

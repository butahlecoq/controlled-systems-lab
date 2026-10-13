from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

import collect


class CollectionTests(unittest.TestCase):
    def test_malformed_failed_pair_is_retained_without_aborting_collection(self) -> None:
        rows = [
            {"warmup": False, "fixture": "triangle", "side": "phase-one-bland", "repetition": 0,
             "sequence": 0, "pair_id": "triangle-0", "status": "failed", "error": "setup exception"},
            {"warmup": False, "fixture": "triangle", "side": "highs-reference", "repetition": 0,
             "sequence": 1, "pair_id": "triangle-0", "status": "failed", "error": "setup exception"},
        ]

        try:
            warmups, trials, errors, missing = collect.normalize_and_pair(rows, repetitions=1, warmups_per_fixture=0)
        except Exception as exc:
            self.fail(f"malformed driver rows must be retained instead of aborting: {type(exc).__name__}: {exc}")

        self.assertEqual(warmups, [])
        self.assertEqual(len(trials), 2)
        self.assertTrue(errors)
        self.assertEqual(missing, 8)
        self.assertTrue(all(row["status"] == "failed" for row in trials))
        self.assertTrue(all(row["result"]["termination"] == "exception" for row in trials))

    def test_measurement_build_must_be_release_configuration_and_owned_by_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            build = root / "build"
            release_exe = build / "Release" / "csl_opt04_phase_one_report.exe"
            build.mkdir(parents=True)
            release_exe.parent.mkdir()
            release_exe.write_bytes(b"executable")
            cache = {
                "CMAKE_HOME_DIRECTORY:INTERNAL": str(root),
                "CMAKE_CONFIGURATION_TYPES:STRING": "Debug;Release;RelWithDebInfo;MinSizeRel",
                "CMAKE_CXX_FLAGS_RELEASE:STRING": "-O2 -DNDEBUG",
                "CMAKE_COMMAND:INTERNAL": sys.executable,
            }
            (build / "CMakeCache.txt").write_text(
                "\n".join(f"{key}={value}" for key, value in cache.items()), encoding="utf-8"
            )

            validator = getattr(collect, "validate_build_directory", lambda *_: False)
            self.assertTrue(validator(build, release_exe, root))
            self.assertIn("--clean-first", collect.release_build_command(build))

            (build / "CMakeCache.txt").write_text(
                "\n".join(
                    f"{key}={('Debug' if key == 'CMAKE_CONFIGURATION_TYPES:STRING' else value)}"
                    for key, value in cache.items()
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                collect.validate_build_directory(build, release_exe, root)

    def test_driver_timeout_returns_partial_output_and_aborted_status(self) -> None:
        runner = getattr(collect, "run_with_timeout", lambda *_: (None, False))
        result, aborted = runner([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(2)"], 0.05)

        self.assertTrue(aborted)
        self.assertEqual(result.returncode, 124)
        self.assertIn("started", result.stdout)


class FixtureProvenanceTests(unittest.TestCase):
    def test_fixture_fingerprints_bind_inputs_and_problem_semantics(self) -> None:
        fingerprints = getattr(collect, "fixture_fingerprints", None)
        self.assertIsNotNone(fingerprints, "collector must expose canonical fixture fingerprints")
        fixture = collect.FIXTURES["triangle"]
        original = fingerprints(fixture)
        self.assertEqual(len(original["input_sha256"]), 64)
        self.assertEqual(len(original["scenario_sha256"]), 64)
        changed_input = dict(fixture, rhs=[0.5, 0.25, 1])
        self.assertNotEqual(original["input_sha256"], fingerprints(changed_input)["input_sha256"])
        description = {"matrix": fixture["matrix"], "rhs": fixture["rhs"], "row_relation": "equality",
                       "variable_lower_bound": 0.0, "variable_upper_bound": None,
                       "objective_coefficients": [0.0] * fixture["columns"], "objective_constant": 0.0}
        changed_semantics = fingerprints(fixture, description)
        relaxed_semantics = fingerprints(fixture, {**description, "variable_lower_bound": None})
        self.assertNotEqual(changed_semantics["scenario_sha256"], relaxed_semantics["scenario_sha256"])

    def test_execution_policy_records_requested_and_unobserved_counts(self) -> None:
        policy = getattr(collect, "execution_policy", lambda: None)()
        self.assertIsInstance(policy, dict, "collector must serialize its execution policy")
        self.assertEqual(policy["requested"]["resource_context"], {
            "total_threads": 1, "outer_workers": 1, "threads_per_worker": 1,
        })
        self.assertEqual(policy["actual"]["native_threads"]["value"], None)
        self.assertTrue(policy["actual"]["native_threads"]["reason"])
        self.assertEqual(policy["seed"]["status"], "not_applicable")

    def test_trial_hashes_bind_the_driver_emitted_input(self) -> None:
        fixture = collect.FIXTURES["triangle"]
        driver_input = {
            "matrix": [[float(value) for value in row] for row in fixture["matrix"]],
            "rhs": [float(value) for value in fixture["rhs"]],
            "row_relation": "equality", "variable_lower_bound": 0.0,
            "variable_upper_bound": None, "objective_coefficients": [0.0] * fixture["columns"],
            "objective_constant": 0.0,
        }
        row = {"warmup": False, "fixture": "triangle", "side": "phase-one-bland", "repetition": 0,
               "sequence": 0, "pair_id": "triangle-0", "input": driver_input,
               "status": "failed", "error": "injected failure", "observed_status": "undetermined",
               "oracle_match": False, "oracle_checks": [{"name": "run", "passed": False}],
               "work_observed": False, "result": {"termination": "exception", "outcome": "undetermined"},
               "durations_ns": {name: 0 for name in collect.PHASES}}
        _, trials, errors, _ = collect.normalize_and_pair([row], repetitions=1, warmups_per_fixture=0)
        self.assertTrue(trials)
        self.assertEqual(trials[0]["input_sha256"], collect.fixture_fingerprints(fixture)["input_sha256"])
        self.assertEqual(trials[0]["scenario_sha256"], collect.fixture_fingerprints(fixture)["scenario_sha256"])
        self.assertTrue(errors)

        changed = dict(row, input={**driver_input, "rhs": [0.5, 0.25, 1.0]})
        _, changed_trials, changed_errors, _ = collect.normalize_and_pair([changed], repetitions=1, warmups_per_fixture=0)
        self.assertNotEqual(changed_trials[0]["input_sha256"], trials[0]["input_sha256"])
        self.assertTrue(any("actual driver input differs from catalog" in error for error in changed_errors))


if __name__ == "__main__":
    unittest.main()

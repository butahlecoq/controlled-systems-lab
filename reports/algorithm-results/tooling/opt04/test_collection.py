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


if __name__ == "__main__":
    unittest.main()

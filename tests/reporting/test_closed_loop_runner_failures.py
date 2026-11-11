from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import run_closed_loop


class ClosedLoopRunnerFailureTests(unittest.TestCase):
    def fake_executable(self, folder: Path, source: str) -> Path:
        path = folder / "fake-bridge"
        if not source.startswith("#!"):
            source = "#!/usr/bin/env python3\n" + source
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_replay_failure_is_not_overall_success(self):
        result = {"status": "complete", "independent_replay": {
            "common": {"status": "failed-or-incomplete"}, "tight": {"status": "complete"}},
            "render": {"status": "complete"}}
        outcome = run_closed_loop.derive_outcome_status(result)
        self.assertEqual(outcome["algorithm_status"], "complete")
        self.assertEqual(outcome["postcheck_status"], "failed")
        self.assertEqual(outcome["overall_status"], "incomplete")

    def test_bridge_invalid_response_retains_both_streams(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            bridge = self.fake_executable(folder,
                "import sys\nprint('truncated-json {')\nprint('native diagnostic', file=sys.stderr)\n")
            request = folder / "request.json"; request.write_text("{}", encoding="utf-8")
            row = {}
            with self.assertRaises(json.JSONDecodeError):
                run_closed_loop.execute_held_step_bridge(bridge, request, folder, 3, row)
            self.assertEqual(row["execution_process"]["response_parse_failure"].split(":", 1)[0], "JSONDecodeError")
            self.assertEqual((folder / "execution-stdout-003.txt").read_text().strip(), "truncated-json {")
            self.assertEqual((folder / "execution-stderr-003.txt").read_text().strip(), "native diagnostic")

    def test_bridge_timeout_retains_partial_output_and_scope(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            bridge = self.fake_executable(folder,
                "#!/bin/sh\nprintf 'partial stdout\\n'\nprintf 'partial stderr\\n' >&2\nsleep 5\n")
            request = folder / "request.json"; request.write_text("{}", encoding="utf-8")
            row = {}
            with self.assertRaises(subprocess.TimeoutExpired):
                run_closed_loop.execute_held_step_bridge(bridge, request, folder, 0, row, timeout_seconds=0.1)
            self.assertEqual(row["execution_process"]["status"], "timed_out")
            self.assertEqual(row["execution_process"]["timeout_seconds"], 0.1)
            self.assertIn("partial stdout", (folder / "execution-stdout-000.txt").read_text())
            self.assertIn("partial stderr", (folder / "execution-stderr-000.txt").read_text())

    def test_resolution_refusal_creates_attempt_and_coverage_row(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            refusal = run_closed_loop.run_task("syn-nl-lv-01", out, out / "unused-bridge",
                controller_id="controller-that-is-not-admitted")
            self.assertEqual(refusal["overall_status"], "refused")
            attempt = Path(refusal["attempt"])
            self.assertTrue((attempt / "request.json").is_file())
            self.assertTrue((attempt / "resolution-refusal.json").is_file())
            self.assertEqual(json.loads((attempt / "attempt.json").read_text())["actual_solver_invocations"], 0)
            coverage = json.loads(run_closed_loop.write_coverage(out).read_text())
            self.assertEqual(coverage["attempts"][0]["overall_status"], "refused")

    def test_replay_only_returns_nonzero_when_replay_fails(self):
        source = ROOT / "reports/closed-loop-pilot/syn-nl-lv-01/attempts/syn-nl-lv-01-20261111T114908Z-8dc20bed/attempt.json"
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            attempt = folder / "attempt"; attempt.mkdir()
            shutil.copyfile(source, attempt / "attempt.json")
            bridge = self.fake_executable(folder, "print('{\"status\":\"failed\"}')\n")
            with mock.patch.object(sys, "argv", ["run_closed_loop.py", "--replay-only", str(attempt), "--bridge", str(bridge)]):
                self.assertEqual(run_closed_loop.main(), 1)
            records = list(attempt.glob("postcheck-*.json"))
            self.assertEqual(len(records), 1)
            postcheck = json.loads(records[0].read_text())
            self.assertEqual(postcheck["overall_status"], "incomplete")
            self.assertEqual(postcheck["postcheck_status"], "failed")


if __name__ == "__main__":
    unittest.main()

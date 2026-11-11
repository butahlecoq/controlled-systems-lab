from __future__ import annotations

import json
import os
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
    def test_initial_only_receipts_remain_interpretable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); attempt = root / "syn-nl-lv-01" / "attempts" / "attempt-1"
            attempt.mkdir(parents=True)
            (attempt / "attempt.json").write_text(json.dumps({
                "attempt_id": "attempt-1", "task_id": "syn-nl-lv-01/continuous-receding/1",
                "status": "complete", "algorithm_status": "complete", "overall_status": "complete",
                "completed_holds": 30, "independent_replay": {
                    "common": {"status": "complete"}, "tight": {"status": "complete"}},
                "render": {"status": "complete"}}), encoding="utf-8")
            (attempt / "postcheck-initial.json").write_text(json.dumps({
                "postcheck_id": "initial", "postcheck_status": "complete", "render_status": "complete",
                "results": {"common": {"status": "complete"}, "tight": {"status": "complete"}}}),
                encoding="utf-8")
            coverage = json.loads(run_closed_loop.write_coverage(root).read_text(encoding="utf-8"))
            row = coverage["attempts"][0]
            self.assertEqual(row["phase_receipt_ordering"], "initial-record-only")
            self.assertEqual(row["overall_status"], "complete")

    def coverage_with_retry(self, *, original_overall: str, retry_postcheck: str,
                            retry_render: str, event_order: tuple[str, ...] | None = ("postcheck-retry", "render-retry"),
                            receipt_mtimes: tuple[int, int] | None = None) -> tuple[dict, bool]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt = root / "syn-nl-lv-01" / "attempts" / "attempt-1"
            attempt.mkdir(parents=True)
            record = {"schema": "csl.closed-loop.attempt/1", "attempt_id": "attempt-1",
                "task_id": "syn-nl-lv-01/continuous-receding/1", "status": "complete",
                "algorithm_status": "complete", "overall_status": original_overall,
                "completed_holds": 30, "independent_replay": {
                    "common": {"status": "complete"}, "tight": {"status": "complete"}},
                "render": {"status": "complete"}}
            record_path = attempt / "attempt.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            original_bytes = record_path.read_bytes()
            postcheck_statuses = ("complete", "complete") if retry_postcheck == "complete" else ("failed", "complete")
            postcheck_path = attempt / "postcheck-retry.json"
            postcheck_path.write_text(json.dumps({
                "postcheck_id": "postcheck-retry", "postcheck_status": retry_postcheck,
                "render_status": retry_render, "results": {
                    "common": {"status": postcheck_statuses[0]},
                    "tight": {"status": postcheck_statuses[1]}}}), encoding="utf-8")
            render_path = attempt / "render-retry-1.json"
            render_path.write_text(json.dumps({"render_id": "render-retry", "status": retry_render}), encoding="utf-8")
            if event_order is not None:
                for event_type in event_order:
                    if event_type == "postcheck-retry":
                        run_closed_loop.append_phase_event(attempt, event_type, "postcheck-retry", postcheck_path)
                    else:
                        run_closed_loop.append_phase_event(attempt, event_type, "render-retry", render_path)
            if receipt_mtimes is not None:
                os.utime(postcheck_path, ns=(receipt_mtimes[0], receipt_mtimes[0]))
                os.utime(render_path, ns=(receipt_mtimes[1], receipt_mtimes[1]))
            coverage = json.loads(run_closed_loop.write_coverage(root).read_text(encoding="utf-8"))
            return coverage["attempts"][0], record_path.read_bytes() == original_bytes

    def test_failed_retry_downgrades_coverage_without_rewriting_attempt(self):
        row, unchanged = self.coverage_with_retry(original_overall="complete",
            retry_postcheck="failed", retry_render="complete")
        self.assertEqual((row["algorithm_status"], row["postcheck_status"], row["render_status"]),
                         ("complete", "failed", "complete"))
        self.assertEqual(row["overall_status"], "incomplete")
        self.assertTrue(unchanged)

    def test_successful_retry_upgrades_coverage_without_rewriting_attempt(self):
        row, unchanged = self.coverage_with_retry(original_overall="incomplete",
            retry_postcheck="complete", retry_render="complete")
        self.assertEqual((row["algorithm_status"], row["postcheck_status"], row["render_status"]),
                         ("complete", "complete", "complete"))
        self.assertEqual(row["overall_status"], "complete")
        self.assertTrue(unchanged)

    def test_phase_event_order_survives_reversed_and_equal_receipt_mtimes(self):
        # Premise under test: receipt file mtimes do not define retry chronology.
        # The same append ledger must produce the same phases after copy/reorder.
        cases = [
            (("postcheck-retry", "render-retry"), "failed", "complete"),
            (("render-retry", "postcheck-retry"), "failed", "failed"),
        ]
        for order, postcheck, render in cases:
            with self.subTest(order=order):
                reordered, _ = self.coverage_with_retry(original_overall="complete",
                    retry_postcheck=postcheck, retry_render=render, event_order=order,
                    receipt_mtimes=(20_000_000, 10_000_000))
                equal, _ = self.coverage_with_retry(original_overall="complete",
                    retry_postcheck=postcheck, retry_render=render, event_order=order,
                    receipt_mtimes=(10_000_000, 10_000_000))
                expected_render = render
                self.assertEqual(reordered["phase_receipt_ordering"], "sequenced")
                self.assertEqual(equal["phase_receipt_ordering"], "sequenced")
                self.assertEqual((reordered["postcheck_status"], reordered["render_status"]),
                                 (equal["postcheck_status"], equal["render_status"]))
                self.assertEqual(reordered["postcheck_status"], postcheck)
                self.assertEqual(reordered["render_status"], expected_render)

    def test_legacy_cross_type_retries_remain_explicitly_ambiguous_after_copy(self):
        first, _ = self.coverage_with_retry(original_overall="complete", retry_postcheck="failed",
            retry_render="complete", event_order=(), receipt_mtimes=(20_000_000, 10_000_000))
        equal, _ = self.coverage_with_retry(original_overall="complete", retry_postcheck="failed",
            retry_render="complete", event_order=(), receipt_mtimes=(10_000_000, 10_000_000))
        for row in (first, equal):
            self.assertEqual(row["phase_receipt_ordering"], "ambiguous_legacy_unsequenced_retries")
            self.assertEqual(row["postcheck_status"], "ordering_ambiguous")
            self.assertEqual(row["render_status"], "ordering_ambiguous")
            self.assertEqual(row["overall_status"], "incomplete")

    def test_legacy_postcheck_mtime_cannot_select_authoritative_retry(self):
        def coverage_with_mtimes(first_mtime: int, second_mtime: int) -> dict:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw); attempt = root / "syn-nl-lv-01" / "attempts" / "attempt-1"
                attempt.mkdir(parents=True)
                (attempt / "attempt.json").write_text(json.dumps({
                    "attempt_id": "attempt-1", "task_id": "syn-nl-lv-01/continuous-receding/1",
                    "status": "complete", "algorithm_status": "complete", "overall_status": "complete",
                    "postcheck_status": "complete", "render_status": "complete", "completed_holds": 30,
                    "independent_replay": {"common": {"status": "complete"}, "tight": {"status": "complete"}},
                    "render": {"status": "complete"}}), encoding="utf-8")
                receipts = [
                    attempt / "postcheck-a.json",
                    attempt / "postcheck-b.json",
                ]
                for path, status in zip(receipts, ("complete", "failed")):
                    path.write_text(json.dumps({"postcheck_id": path.stem,
                        "postcheck_status": status, "render_status": "complete",
                        "results": {"common": {"status": status}, "tight": {"status": "complete"}}}),
                        encoding="utf-8")
                os.utime(receipts[0], ns=(first_mtime, first_mtime))
                os.utime(receipts[1], ns=(second_mtime, second_mtime))
                coverage = json.loads(run_closed_loop.write_coverage(root).read_text(encoding="utf-8"))
                return coverage["attempts"][0]

        failed_newer = coverage_with_mtimes(10_000_000, 20_000_000)
        complete_newer = coverage_with_mtimes(20_000_000, 10_000_000)
        equal = coverage_with_mtimes(10_000_000, 10_000_000)
        for row in (failed_newer, complete_newer, equal):
            self.assertEqual(row["phase_receipt_ordering"], "ambiguous_legacy_unsequenced_retries")
            self.assertEqual(row["postcheck_status"], "ordering_ambiguous")
            self.assertEqual(row["overall_status"], "incomplete")

    def test_phase_ledger_rejects_duplicate_receipts_and_changed_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); attempt = root / "syn-nl-lv-01" / "attempts" / "attempt-1"
            attempt.mkdir(parents=True)
            (attempt / "attempt.json").write_text(json.dumps({
                "attempt_id": "attempt-1", "task_id": "syn-nl-lv-01/continuous-receding/1",
                "status": "complete", "algorithm_status": "complete", "overall_status": "complete",
                "postcheck_status": "complete", "render_status": "complete", "completed_holds": 30,
                "independent_replay": {"common": {"status": "complete"}, "tight": {"status": "complete"}},
                "render": {"status": "complete"}}), encoding="utf-8")
            postcheck = attempt / "postcheck-retry-1.json"
            postcheck.write_text(json.dumps({"postcheck_id": "postcheck-retry-1", "postcheck_status": "failed",
                "render_status": "failed", "results": {"common": {"status": "failed"},
                    "tight": {"status": "complete"}}}), encoding="utf-8")
            render = attempt / "render-retry-1.json"
            render.write_text(json.dumps({"render_id": "render-retry-1", "status": "complete"}), encoding="utf-8")
            run_closed_loop.append_phase_event(attempt, "postcheck-retry", "postcheck-retry-1", postcheck)
            with self.assertRaises(ValueError):
                run_closed_loop.append_phase_event(attempt, "postcheck-retry", "postcheck-retry-1", postcheck)
            run_closed_loop.append_phase_event(attempt, "render-retry", "render-retry-1", render)
            ledger = attempt / "phase-events.jsonl"
            original_ledger = ledger.read_text(encoding="utf-8")
            events = [json.loads(line) for line in original_ledger.splitlines()]
            events[1]["sequence"] = events[0]["sequence"]
            ledger.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
            coverage = json.loads(run_closed_loop.write_coverage(root).read_text(encoding="utf-8"))
            self.assertEqual(coverage["attempts"][0]["phase_receipt_ordering"], "ambiguous_unsequenced_receipt")
            ledger.write_text(original_ledger, encoding="utf-8")
            postcheck.write_text(postcheck.read_text(encoding="utf-8") + " ", encoding="utf-8")
            another = attempt / "postcheck-retry-2.json"
            another.write_text(json.dumps({"postcheck_id": "postcheck-retry-2", "postcheck_status": "complete"}),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                run_closed_loop.append_phase_event(attempt, "postcheck-retry", "postcheck-retry-2", another)
            coverage = json.loads(run_closed_loop.write_coverage(root).read_text(encoding="utf-8"))
            row = coverage["attempts"][0]
            self.assertEqual(row["phase_receipt_ordering"], "ambiguous_unsequenced_receipt")
            self.assertEqual(row["render_status"], "ordering_ambiguous")
            self.assertEqual(row["overall_status"], "incomplete")

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
            self.assertEqual(json.loads((attempt / "attempt.json").read_text())["mathematical_support_status"],
                "not_evaluated")
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

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import capabilities
import run_closed_loop


def probe_worker_exit(mode: str, caller_owned: bool) -> None:
    assert not tracemalloc.is_tracing()
    graph = next(row for row in capabilities.build_native_manifest()["graphs"]
        if row["task_id"].startswith("syn-nl-lv-01/")
        and row["controller"]["id"] == "native-exact-polytope-backward-graph/1")
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        attempt = folder / "attempt"
        attempt.mkdir()
        bridge = folder / "plant-bridge"
        bridge.write_bytes(b"plant bridge")
        graph_path = folder / "graph.json"
        graph_path.write_text(json.dumps(graph))
        if caller_owned:
            tracemalloc.start(3)
            marker = bytearray(4096)
            marker_traceback = tracemalloc.get_object_traceback(marker)
            assert marker_traceback is not None
        try:
            if mode == "validation":
                try:
                    run_closed_loop.worker("syn-nl-lv-01", attempt, bridge)
                except ValueError as error:
                    assert "worker requires an admitted resolved graph" in str(error)
                else:
                    raise AssertionError("Expected graph validation failure")
                assert not (attempt / "attempt.json").exists()
            elif mode == "terminal":
                with mock.patch.object(run_closed_loop, "prepare_graph", return_value=(None, {})), \
                     mock.patch.object(run_closed_loop, "controller_query", return_value={
                         "status": "rejected", "policy_id": graph["controller"]["id"],
                         "invocations": []}):
                    result = run_closed_loop.worker("syn-nl-lv-01", attempt, bridge,
                        graph_path=graph_path)
                record = json.loads((attempt / "attempt.json").read_text())
                assert result == 2
                assert record["status"] == "incomplete"
                assert record["completed_holds"] == 0
                scope = record["resource_limits"]["observed"]["python_traced_memory_scope"]
                assert ("caller-owned" in scope) == caller_owned, scope
            else:
                with mock.patch.dict(os.environ, {"CSL_NATIVE_POLICY_BRIDGE": ""}):
                    result = run_closed_loop.worker("syn-nl-lv-01", attempt, bridge,
                        graph_path=graph_path)
                record = json.loads((attempt / "attempt.json").read_text())
                assert result == 2
                assert record["status"] == "preparation_failed"
                assert record["mathematical_support_status"] == "not_evaluated"
                assert "CSL_NATIVE_POLICY_BRIDGE" in record["preparation_failure"]["reason"]
            assert tracemalloc.is_tracing() == caller_owned, "Worker changed tracing ownership"
            if caller_owned:
                assert tracemalloc.get_traceback_limit() == 3
                assert tracemalloc.get_object_traceback(marker) == marker_traceback
        finally:
            if caller_owned:
                tracemalloc.stop()


def probe_reader_with_caller_trace() -> None:
    sys.path.insert(0, str(ROOT))
    from tests.reporting.test_closed_loop_attempt_records import ClosedLoopAttemptRecordTests

    assert not tracemalloc.is_tracing()
    tracemalloc.start(3)
    marker = bytearray(8 * 1024 * 1024)
    marker_traceback = tracemalloc.get_object_traceback(marker)
    try:
        case = ClosedLoopAttemptRecordTests(
            "test_v1_reader_skips_large_embedded_stage_field_without_allocating_it")
        result = unittest.TestResult()
        case.run(result)
        assert result.wasSuccessful(), result.errors + result.failures
        assert tracemalloc.is_tracing(), "Reader allocation test stopped caller tracing"
        assert tracemalloc.get_traceback_limit() == 3
        assert tracemalloc.get_object_traceback(marker) == marker_traceback
    finally:
        tracemalloc.stop()


class ClosedLoopTracingTests(unittest.TestCase):
    def test_worker_restores_ownership_on_preparation_failure(self):
        self._check_exit("preparation")

    def test_worker_restores_ownership_on_validation_exception(self):
        self._check_exit("validation")

    def test_terminal_record_preserves_ownership_and_labels_session_scope(self):
        self._check_exit("terminal")

    def test_reader_allocation_check_preserves_caller_trace(self):
        result = subprocess.run([sys.executable, "-E", str(Path(__file__).resolve()),
            "reader-probe"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _check_exit(self, mode: str) -> None:
        for caller_owned in (False, True):
            with self.subTest(caller_owned=caller_owned):
                result = subprocess.run([sys.executable, "-E", str(Path(__file__).resolve()),
                    "probe", mode, str(int(caller_owned))], cwd=ROOT,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "probe":
        probe_worker_exit(sys.argv[2], bool(int(sys.argv[3])))
    elif len(sys.argv) == 2 and sys.argv[1] == "reader-probe":
        probe_reader_with_caller_trace()
    else:
        unittest.main()

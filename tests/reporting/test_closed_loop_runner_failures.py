from __future__ import annotations

import hashlib
import json
import multiprocessing
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
from attempt_records import (IO_LOG, STAGE_INDEX, finalize_stage, summarize_io,
    verify_v2_attempt, write_attempt, write_stage)


def _measure_worker_memory(send, attempt: Path, stage_count: int) -> None:
    try:
        import copy

        task = copy.deepcopy(run_closed_loop.load_task("syn-nl-lv-01"))
        task["episode"]["intervals"] = stage_count
        task["episode"]["final_time"] = stage_count * task["episode"]["dt"]
        task_hash = "a" * 64
        graph = {"task_sha256": task_hash,
            "action_profile_id": task["control_domains"]["continuous"]["problem_id"],
            "controller": {"id": "memory-fixture-controller", "version": "1"},
            "execution": {"id": "memory-fixture-execution", "version": "1", "provider": "fixture"},
            "role_bindings": {}}
        graph_path = attempt.parent / "graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        bridge = attempt.parent / "bridge"
        bridge.write_text("fixture", encoding="utf-8")
        attempt.mkdir()

        def query(_task, _graph, _state, stage, _previous, _prepared):
            telemetry = [[float(stage), float(point), float((stage * 13 + point) % 997)]
                         for point in range(4096)]
            return {"status": "accepted", "control": [0.0],
                "policy_id": graph["controller"]["id"], "invocations": [],
                "predicted_sets": [{"role": "large-stage-telemetry", "points": telemetry}]}

        def execution(request, _response):
            state = request["observed_state"]["physical"]
            start = request["absolute_time"]
            return {"status": "complete", "physical_states": [state, state],
                "times": [start, start + task["episode"]["dt"]],
                "integration_receipts": [{"accepted_steps": 1, "rejected_steps": 0}]}

        with mock.patch.object(run_closed_loop, "load_task", new=lambda _name: task), \
             mock.patch.object(run_closed_loop, "validate_source_binding", new=lambda _task: None), \
             mock.patch.object(run_closed_loop, "manifest_sha256", new=lambda _task: task_hash), \
             mock.patch.object(run_closed_loop, "prepare_graph", new=lambda *_args: (None, {})), \
             mock.patch.object(run_closed_loop, "controller_query", new=query), \
             mock.patch.object(run_closed_loop, "execute_held_step_bridge", new=lambda *_args: {}), \
             mock.patch.object(run_closed_loop, "validate_held_step_response", new=execution), \
             mock.patch.object(run_closed_loop, "objective", new=lambda *_args: {
                 "terminal": 0.0, "running": 0.0, "total": 0.0}):
            status = run_closed_loop.worker("syn-nl-lv-01", attempt, bridge, graph_path=graph_path)
        record = json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))
        telemetry_hashes = []
        for reference in run_closed_loop.iter_stage_references(attempt):
            row = json.loads((attempt / reference["path"]).read_text(encoding="utf-8"))
            payload = row["predicted_sets"][0]["points"]
            telemetry_hashes.append(hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest())
        send.send({"status": status, "record_status": record["status"],
            "traced_peak_bytes": record["resource_limits"]["observed"]["worker_python_traced_peak_bytes"],
            "rss_peak_kib": record["resource_limits"]["observed"]["worker_max_rss_kib"],
            "rss_scope": record["resource_limits"]["observed"]["rss_accounting_scope"],
            "traced_scope": record["resource_limits"]["observed"]["python_traced_memory_scope"],
            "stage_count": stage_count, "distinct_telemetry_stages": len(set(telemetry_hashes)),
            "stage_json_bytes_written": summarize_io(attempt)["stage_json_bytes_written"],
            "attempt_json_bytes": (attempt / "attempt.json").stat().st_size})
    except BaseException as error:
        send.send({"error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        send.close()


class ClosedLoopRunnerFailureTests(unittest.TestCase):
    def test_supervisor_wall_clock_covers_worker_lifecycle_and_overrides_stage_sum(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_bytes(b"bridge")

            clock = [0.0]
            exited = [False]
            read_attempt = run_closed_loop.read_attempt

            def parse_after_exit(path):
                if exited[0]:
                    clock[0] += 10.0
                return read_attempt(path)

            class WorkerProcess:
                pid = 999999999
                returncode = 0
                def communicate(self, timeout):
                    record_path = next(root.glob("syn-nl-lv-01/attempts/*/attempt.json"))
                    record = json.loads(record_path.read_text())
                    record.update(status="incomplete", resource_limits={"observed": {
                        "worker_stage_interval_seconds_sum": 0.25}})
                    record_path.write_text(json.dumps(record))
                    clock[0] = 2.0
                    exited[0] = True
                    return "", ""

            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=WorkerProcess()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"), \
                 mock.patch.object(run_closed_loop.time, "monotonic", side_effect=lambda: clock[0]), \
                 mock.patch.object(run_closed_loop, "read_attempt", parse_after_exit):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            record = json.loads((Path(result["attempt"]) / "attempt.json").read_text())
            observed = record["resource_limits"]["observed"]
            self.assertEqual(observed["worker_wall_seconds"], record["supervisor"]["wall_seconds"])
            self.assertEqual(observed["worker_wall_seconds"], 2.0)
            self.assertGreater(record["end_to_end"]["wall_seconds"], 2.0)
            self.assertGreater(observed["worker_wall_seconds"], observed["worker_stage_interval_seconds_sum"])
            self.assertIn("terminal serialization", observed["worker_wall_scope"])

    def test_supervisor_records_wall_clock_when_worker_preparation_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_bytes(b"bridge")

            class PreparationFailureProcess:
                pid = 999999999
                returncode = 2
                def communicate(self, timeout):
                    record_path = next(root.glob("syn-nl-lv-01/attempts/*/attempt.json"))
                    record = json.loads(record_path.read_text())
                    record.update(status="preparation_failed", resource_limits={})
                    record_path.write_text(json.dumps(record))
                    return "", ""

            ticks = iter(float(i) for i in range(20))
            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=PreparationFailureProcess()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"), \
                 mock.patch.object(run_closed_loop.time, "monotonic", side_effect=lambda: next(ticks)):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            record = json.loads((Path(result["attempt"]) / "attempt.json").read_text())
            self.assertEqual(record["status"], "preparation_failed")
            self.assertEqual(record["resource_limits"]["observed"]["worker_wall_seconds"],
                             record["supervisor"]["wall_seconds"])

    def test_controller_query_duration_is_not_extended_by_execution_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt = root / "attempt"; attempt.mkdir()
            task = run_closed_loop.load_task("syn-nl-lv-01")
            graph = {"task_sha256": run_closed_loop.manifest_sha256(task),
                "action_profile_id": task["control_domains"]["continuous"]["problem_id"],
                "controller": {"id": "test-controller", "version": "1"},
                "execution": {"id": "test-execution", "version": "1", "provider": "test"},
                "role_bindings": {}}
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            bridge = root / "bridge"

            def fail_execution(_bridge, _request, _attempt, _index, row):
                import time
                time.sleep(0.25)
                row["execution_process"] = {"status": "failed", "wall_seconds": 0.25}
                raise RuntimeError("deterministic execution failure")

            with mock.patch.object(run_closed_loop, "prepare_graph", return_value=(None, {})), \
                 mock.patch.object(run_closed_loop, "controller_query", return_value={
                     "status": "accepted", "control": [0.0], "policy_id": "test-controller",
                     "invocations": []}), \
                 mock.patch.object(run_closed_loop, "execute_held_step_bridge", side_effect=fail_execution):
                self.assertEqual(run_closed_loop.worker("syn-nl-lv-01", attempt, bridge,
                    graph_path=graph_path), 2)

            row = json.loads((attempt / "stage-000.json").read_text())
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(row["execution_process"]["wall_seconds"], 0.25)
            self.assertLess(row["controller_query_wall_seconds"], 0.1)
            self.assertIn("immediately before the final stage record/index write",
                record["timing_scopes"]["stage_interval_seconds"])

    def test_supervisor_recovers_torn_stage_index_and_records_incomplete_status(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_text("bridge")
            torn = b'{"schema":"csl.closed-loop.stage-reference/1","update_index":1'

            class InterruptedWorker:
                pid = 999999999
                returncode = -15

                def communicate(self, timeout):
                    attempt = next(root.glob("syn-nl-lv-01/attempts/*"))
                    record_path = attempt / "attempt.json"
                    record = json.loads(record_path.read_text())
                    task = run_closed_loop.load_task("syn-nl-lv-01")
                    initial = [row["initial"] for row in task["model"]["states"]]
                    finalize_stage(attempt, 0, {"update_index": 0, "status": "applied-and-observed",
                        "observed_physical": initial, "applied_control": [0.0],
                        "observed_next_physical": initial})
                    write_stage(attempt, 1, {"update_index": 1, "status": "started",
                        "observed_physical": initial})
                    with (attempt / STAGE_INDEX).open("ab") as stream:
                        stream.write(torn)
                    record.update(status="in-progress", completed_holds=1,
                        selected_initial_state_physical=initial)
                    record["stage_records"]["count"] = 1
                    write_attempt(attempt, record)
                    return "", "worker interrupted during reference append"

            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=InterruptedWorker()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            attempt = Path(result["attempt"])
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(record["status"], "incomplete")
            self.assertEqual(record["terminal_supervisor_failure"]["status"], "failed")
            self.assertEqual(record["completed_holds"], 1)
            self.assertEqual(record["stage_records"]["count"], 2)
            self.assertEqual(record["stage_recovery"]["recovered_orphan_stages"], 1)
            preserved = record["stage_recovery"]["diagnostics"][0]
            self.assertEqual((attempt / preserved["path"]).read_bytes(), torn)
            self.assertEqual(record["controls"], [[0.0]])
            self.assertEqual(record["physical_states"], [
                record["selected_initial_state_physical"], record["selected_initial_state_physical"]])

    def test_supervisor_reconciles_applied_stage_before_terminal_persistence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_text("bridge")

            class InterruptedAfterStageFinalization:
                pid = 999999999
                returncode = -15

                def communicate(self, timeout):
                    attempt = next(root.glob("syn-nl-lv-01/attempts/*"))
                    record = json.loads((attempt / "attempt.json").read_text())
                    task = run_closed_loop.load_task("syn-nl-lv-01")
                    initial = [row["initial"] for row in task["model"]["states"]]
                    finalize_stage(attempt, 0, {"update_index": 0, "status": "applied-and-observed",
                        "observed_physical": initial, "applied_control": [0.0],
                        "observed_next_physical": initial})
                    # Match the crash window after the durable stage index append but
                    # before the worker checkpoints the updated attempt ledger.
                    self.stale_completed_holds = record["completed_holds"]
                    return "", "worker interrupted after final stage record"

            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=InterruptedAfterStageFinalization()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            attempt = Path(result["attempt"])
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(record["status"], "incomplete")
            self.assertEqual(record["completed_holds"], 1)
            self.assertEqual(record["controls"], [[0.0]])
            self.assertEqual(len(record["physical_states"]), 2)
            self.assertEqual(record["controls_sha256"], hashlib.sha256(
                json.dumps(record["controls"], separators=(",", ":"), allow_nan=False).encode()).hexdigest())
            verify_v2_attempt(attempt, record)
            coverage = json.loads(run_closed_loop.write_coverage(root).read_text())
            self.assertEqual(coverage["attempts"][0]["completed_holds"], 1)
            self.assertEqual(coverage["attempts"][0]["ledger_status"], "incomplete")

    def test_supervisor_preserves_torn_record_io_tail_and_marks_metrics_incomplete(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_text("bridge")
            torn = b'{"schema":"csl.closed-loop.record-io/1","operation":"stage-checkpoint","bytes_written":'

            class InterruptedDuringTelemetryAppend:
                pid = 999999999
                returncode = -15

                def communicate(self, timeout):
                    attempt = next(root.glob("syn-nl-lv-01/attempts/*"))
                    task = run_closed_loop.load_task("syn-nl-lv-01")
                    initial = [row["initial"] for row in task["model"]["states"]]
                    finalize_stage(attempt, 0, {"update_index": 0, "status": "applied-and-observed",
                        "observed_physical": initial, "applied_control": [0.0],
                        "observed_next_physical": initial})
                    with (attempt / IO_LOG).open("ab") as stream:
                        stream.write(torn)
                    return "", "worker interrupted during record I/O append"

            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=InterruptedDuringTelemetryAppend()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            attempt = Path(result["attempt"])
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(record["status"], "incomplete")
            self.assertEqual(record["completed_holds"], 1)
            integrity = record["record_io"]
            self.assertEqual(integrity["integrity_status"], "incomplete")
            self.assertFalse(integrity["metric_totals_complete"])
            preserved = integrity["recovery_evidence"][0]
            self.assertEqual((attempt / preserved["path"]).read_bytes(), torn)
            self.assertEqual(integrity["record_io_recovery_evidence_bytes_written"], len(torn))
            lines = (attempt / IO_LOG).read_bytes().splitlines()
            self.assertTrue(lines)
            self.assertTrue(all(json.loads(line)["schema"] == "csl.closed-loop.record-io/1" for line in lines))
            verify_v2_attempt(attempt, record)

    def test_completed_malformed_record_io_row_is_reported_without_losing_attempt_status(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); bridge = root / "bridge"; bridge.write_text("bridge")
            malformed = b'{"schema":"csl.closed-loop.record-io/1","operation":}\n'

            class InterruptedWithCorruptTelemetry:
                pid = 999999999
                returncode = -15

                def communicate(self, timeout):
                    attempt = next(root.glob("syn-nl-lv-01/attempts/*"))
                    with (attempt / IO_LOG).open("ab") as stream:
                        stream.write(malformed)
                    return "", "worker interrupted after malformed telemetry row"

            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=InterruptedWithCorruptTelemetry()), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

            attempt = Path(result["attempt"])
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(record["status"], "incomplete")
            self.assertEqual(record["record_io"]["integrity_status"], "invalid")
            self.assertFalse(record["record_io"]["metric_totals_complete"])
            self.assertIn("malformed completed row", record["record_io"]["integrity_diagnostic"])
            self.assertIn(malformed, (attempt / IO_LOG).read_bytes())

    def test_telemetry_fault_matrix_never_blocks_canonical_terminal_attempt(self):
        faults = {
            "invalid-json": b'{"schema":"csl.closed-loop.record-io/1","operation":}\n',
            "invalid-prefix-plus-tail": (
                b'{"schema":"csl.closed-loop.record-io/1","operation":}\n'
                b'{"schema":"csl.closed-loop.record-io/1","operation":"torn"'),
            "missing-required-field": json.dumps({"schema": "csl.closed-loop.record-io/1",
                "operation": "stage-checkpoint"}).encode() + b"\n",
            "wrong-required-field-type": json.dumps({"schema": "csl.closed-loop.record-io/1",
                "operation": "stage-checkpoint", "bytes_written": "not-an-integer"}).encode() + b"\n",
        }
        for label, damaged_bytes in faults.items():
            with self.subTest(fault=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); bridge = root / "bridge"; bridge.write_text("bridge")
                captured = {}

                class InterruptedWithTelemetryFault:
                    pid = 999999999
                    returncode = -15

                    def communicate(self, timeout):
                        attempt = next(root.glob("syn-nl-lv-01/attempts/*"))
                        with (attempt / IO_LOG).open("ab") as stream:
                            stream.write(damaged_bytes)
                        captured["log_bytes"] = (attempt / IO_LOG).read_bytes()
                        return "", "worker interrupted with damaged telemetry"

                with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=InterruptedWithTelemetryFault()), \
                     mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                    result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge)

                attempt = Path(result["attempt"])
                record = json.loads((attempt / "attempt.json").read_text())
                self.assertEqual(record["status"], "incomplete")
                self.assertEqual(record["record_io"]["integrity_status"], "invalid")
                self.assertFalse(record["record_io"]["metric_totals_complete"])
                self.assertNotIn("stage_json_bytes_written", record["record_io"])
                verify_v2_attempt(attempt, record)
                coverage = json.loads(run_closed_loop.write_coverage(root).read_text())
                self.assertEqual(len(coverage["attempts"]), 1)
                self.assertEqual(coverage["attempts"][0]["ledger_status"], "incomplete")
                self.assertIn(damaged_bytes.rstrip(b"\n").splitlines()[0],
                    (attempt / IO_LOG).read_bytes())
                if label == "invalid-prefix-plus-tail":
                    self.assertEqual((attempt / IO_LOG).read_bytes(), captured["log_bytes"])
                    status = json.loads((attempt / "record-io-integrity.json").read_text())
                    preserved = status["recovery_evidence"][0]
                    self.assertEqual((attempt / preserved["path"]).read_bytes(),
                        damaged_bytes.splitlines()[-1])

    def test_invalid_generated_telemetry_event_is_diagnostic_not_a_write_prerequisite(self):
        with tempfile.TemporaryDirectory() as raw:
            attempt = Path(raw)
            record = {"schema": "csl.closed-loop.attempt/2", "format_version": 2,
                "attempt_id": "append-schema-fixture", "task_id": "task/1", "task_sha256": "a" * 64,
                "status": "in-progress", "completed_holds": 0,
                "stage_records": {"path": STAGE_INDEX, "count": 0}}
            write_attempt(attempt, record)
            from attempt_records import append_io_event
            append_io_event(attempt, {"operation": "stage-checkpoint", "bytes_written": "bad"})
            record.update(status="incomplete", terminal_reason="fixture")
            write_attempt(attempt, record)
            saved = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(saved["status"], "incomplete")
            status = json.loads((attempt / "record-io-integrity.json").read_text())
            self.assertEqual(status["integrity_status"], "invalid")

    def test_worker_retained_memory_stays_bounded_as_stage_telemetry_grows(self):
        def measure(stage_count: int) -> dict:
            with tempfile.TemporaryDirectory() as raw:
                context = multiprocessing.get_context("fork")
                receive, send = context.Pipe(duplex=False)
                attempt = Path(raw) / "attempt"
                process = context.Process(target=_measure_worker_memory,
                    args=(send, attempt, stage_count))
                process.start()
                send.close()
                observed = receive.recv()
                process.join(timeout=30)
                self.assertEqual(process.exitcode, 0)
                self.assertNotIn("error", observed)
                return observed

        short = measure(4)
        long = measure(24)
        self.assertEqual((short["record_status"], long["record_status"]), ("complete", "complete"))
        self.assertEqual(short["distinct_telemetry_stages"], short["stage_count"])
        self.assertEqual(long["distinct_telemetry_stages"], long["stage_count"])
        self.assertGreater(long["stage_json_bytes_written"], 5 * short["stage_json_bytes_written"])
        self.assertLess(long["attempt_json_bytes"], long["stage_json_bytes_written"] // 5)
        # A 6x longer episode writes 6x as many large stage payloads, but the worker
        # holds only its current telemetry plus O(n) controls/states. Allow 2 MiB for
        # one live Python telemetry object, JSON serialization temporaries, and noise.
        self.assertLessEqual(long["traced_peak_bytes"], short["traced_peak_bytes"] + 2 * 1024**2)
        # ru_maxrss is coarse and includes imported/native runtime pages; keep its
        # process-only scope separate from Python tracemalloc and allow 16 MiB noise.
        self.assertLessEqual(long["rss_peak_kib"], short["rss_peak_kib"] + 16 * 1024)
        self.assertIn("worker process only", long["rss_scope"])
        self.assertIn("worker Python allocations", long["traced_scope"])

    def test_retry_modes_reject_changed_v2_stage_before_receipt_creation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            attempt = root / "attempt"
            attempt.mkdir()
            task = run_closed_loop.load_task("syn-nl-lv-01")
            count = task["episode"]["intervals"]
            initial = [row["initial"] for row in task["model"]["states"]]
            control = [0.0]
            states = [initial for _ in range(count + 1)]
            controls = [control for _ in range(count)]
            for index in range(count):
                finalize_stage(attempt, index, {"update_index": index,
                    "status": "applied-and-observed", "observed_physical": states[index],
                    "applied_control": control, "observed_next_physical": states[index + 1]})
            import hashlib
            import json
            from contracts import manifest_sha256
            record = {"schema": "csl.closed-loop.attempt/2", "format_version": 2,
                "attempt_id": "retry-guard", "task_id": task["task_id"],
                "task_sha256": manifest_sha256(task), "status": "complete",
                "algorithm_status": "complete", "overall_status": "complete",
                "completed_holds": count, "original_intervals": count,
                "selected_initial_state_physical": initial, "controls": controls,
                "physical_states": states,
                "controls_sha256": hashlib.sha256(json.dumps(controls, separators=(",", ":"),
                    allow_nan=False).encode()).hexdigest(),
                "stage_records": {"path": STAGE_INDEX, "count": count}}
            write_attempt(attempt, record)
            self.assertIsNotNone(run_closed_loop.verify_v2_attempt(attempt, record))
            (attempt / "stage-000.json").unlink()
            bridge = root / "bridge"; bridge.write_text("must not be invoked")
            original_attempt = (attempt / "attempt.json").read_bytes()
            for option, argv in (("render-only", ["--render-only", str(attempt)]),
                                 ("replay-only", ["--bridge", str(bridge), "--replay-only", str(attempt)])):
                with self.subTest(option=option), \
                     mock.patch.object(sys, "argv", ["run_closed_loop.py", *argv]), \
                     mock.patch.object(run_closed_loop, "render_attempt") as render, \
                     mock.patch.object(run_closed_loop, "replay_attempt") as replay, \
                     self.assertRaises(SystemExit) as raised:
                    run_closed_loop.main()
                    self.assertEqual(raised.exception.code, 2)
                    render.assert_not_called()
                    replay.assert_not_called()
            self.assertEqual((attempt / "attempt.json").read_bytes(), original_attempt)
            self.assertFalse(list(attempt.glob("render-retry-*.json")))
            self.assertFalse(list(attempt.glob("full-replay-retry-*")))

    def test_attempt_resource_budget_is_positive_recorded_and_enforced(self):
        profile = run_closed_loop.attempt_resource_profile(1800, 1800)
        self.assertEqual(profile["profile_id"], "worker-wall-1800-cpu-1800/1")
        self.assertEqual(profile["requested"], {"wall_seconds": 1800, "cpu_seconds": 1800})
        self.assertEqual(profile["enforced"]["wall_seconds"], profile["requested"]["wall_seconds"])
        self.assertEqual(profile["enforced"]["cpu_seconds_soft"], profile["requested"]["cpu_seconds"])
        for invalid in (0, -1, "not-a-number", "1.5"):
            with self.subTest(invalid_budget=invalid), self.assertRaises(ValueError):
                run_closed_loop.attempt_resource_profile(invalid, 300)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bridge = root / "unused-bridge"; bridge.write_bytes(b"execution bridge")
            class FinishedProcess:
                pid = 999999999
                returncode = 17
                timeout = None
                def communicate(self, timeout):
                    self.timeout = timeout
                    return "", ""
            process = FinishedProcess()
            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=process) as popen, \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"):
                result = run_closed_loop.run_task("syn-nl-lv-01", root, bridge,
                    attempt_wall_seconds=1800, attempt_cpu_seconds=1800)
            self.assertEqual(process.timeout, 1800)
            preexec = popen.call_args.kwargs["preexec_fn"]
            self.assertEqual(preexec.keywords["cpu_seconds"], 1800)
            attempt = Path(result["attempt"])
            record = json.loads((attempt / "attempt.json").read_text())
            self.assertEqual(record["resource_profile_id"], profile["profile_id"])
            self.assertEqual(record["resource_limits"]["requested"], profile["requested"])
            self.assertEqual(record["resource_limits"]["enforced"]["wall_seconds"], process.timeout)
            self.assertEqual(record["supervisor"]["enforced_cpu_rlimit_soft_hard_seconds"], [1800, 1801])

            class TimedOutProcess(FinishedProcess):
                returncode = -15
                calls = 0
                timeouts = []
                def communicate(self, timeout):
                    self.timeout = timeout
                    self.timeouts.append(timeout)
                    self.calls += 1
                    if self.calls == 1:
                        attempt_record = next(path for path in root.glob("syn-nl-lv-01/attempts/*/attempt.json")
                            if json.loads(path.read_text()).get("status") == "prepared")
                        current = json.loads(attempt_record.read_text())
                        current["status"] = "in-progress"
                        attempt_record.write_text(json.dumps(current))
                        raise subprocess.TimeoutExpired("worker", timeout)
                    return "", ""
            timed_out_process = TimedOutProcess()
            with mock.patch.object(run_closed_loop.subprocess, "Popen", return_value=timed_out_process), \
                 mock.patch.object(run_closed_loop.subprocess, "check_output", return_value="test-commit\n"), \
                 mock.patch.object(run_closed_loop.os, "killpg"):
                timed_out = run_closed_loop.run_task("syn-nl-lv-01", root, bridge,
                    attempt_wall_seconds=1800, attempt_cpu_seconds=1800)
            timeout_record = json.loads((Path(timed_out["attempt"]) / "attempt.json").read_text())
            self.assertEqual(timed_out_process.timeouts, [1800, 5])
            self.assertEqual(timeout_record["supervisor"]["status"], "timed_out")
            self.assertEqual(timeout_record["terminal_supervisor_failure"]["prior_ledger_status"], "in-progress")
            self.assertEqual(timeout_record["mathematical_support_status"], "not_evaluated")

        limited = subprocess.run([sys.executable, "-c",
            "import json,resource; print(json.dumps(resource.getrlimit(resource.RLIMIT_CPU)))"],
            capture_output=True, text=True,
            preexec_fn=lambda: run_closed_loop.limited_worker(cpu_seconds=1800), check=True)
        self.assertEqual(json.loads(limited.stdout), [1800, 1801])

    def test_cli_rejects_nonpositive_attempt_wall_budget(self):
        with tempfile.TemporaryDirectory() as raw:
            for option in ("--attempt-wall-seconds", "--attempt-cpu-seconds"):
                with self.subTest(option=option), mock.patch.object(sys, "argv", ["run_closed_loop.py",
                        "--bridge", str(Path(raw) / "bridge"), "--output-root", raw, option, "0"]):
                    with self.assertRaises(SystemExit) as raised:
                        run_closed_loop.main()
                    self.assertEqual(raised.exception.code, 2)

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

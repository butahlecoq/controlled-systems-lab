from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import tracemalloc
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))

from attempt_records import (IO_LOG, STAGE_INDEX, append_io_event, finalize_stage,
    iter_stage_references, materialize_episode_summary, persist_native_capture,
    read_attempt, read_native_capture_metadata, read_object_fields, register_orphan_stages,
    summarize_io, verify_v2_attempt, write_attempt, write_stage)


class ClosedLoopAttemptRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.attempt = Path(self.temporary.name) / "attempt"
        self.attempt.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _record(self) -> dict:
        return {"schema": "csl.closed-loop.attempt/2", "format_version": 2,
            "attempt_id": "attempt-1", "task_id": "task/1", "task_sha256": "task-hash",
            "status": "in-progress", "selected_initial_state_physical": [0.0, 1.0],
            "completed_holds": 0, "stage_records": {"path": STAGE_INDEX, "count": 0}}

    def test_large_stage_payload_is_written_once_outside_compact_checkpoints(self):
        record = self._record()
        write_attempt(self.attempt, record)
        payload = "g" * (256 * 1024)
        expected_stage_bytes = 0
        expected_checkpoint_bytes = 0
        for index in range(8):
            row = {"update_index": index, "status": "applied-and-observed",
                "observed_physical": [float(index), 1.0], "applied_control": [0.25],
                "observed_next_physical": [float(index + 1), 1.0],
                "native_geometry_evidence": payload}
            reference = finalize_stage(self.attempt, index, row)
            expected_stage_bytes += reference["bytes"]
            record["stage_records"]["count"] = index + 1
            record["completed_holds"] = index + 1
            write_receipt = write_attempt(self.attempt, record)
            expected_checkpoint_bytes += write_receipt.bytes_written

        saved, _ = read_attempt(self.attempt / "attempt.json")
        self.assertNotIn("stages", saved)
        self.assertNotIn("native_geometry_evidence", saved)
        self.assertLess(expected_checkpoint_bytes, expected_stage_bytes // 100)
        summary = summarize_io(self.attempt)
        self.assertEqual(summary["stage_writes"], 8)
        self.assertEqual(summary["stage_json_bytes_written"], expected_stage_bytes)
        self.assertEqual(len(list(iter_stage_references(self.attempt))), 8)

    def test_interrupted_active_stage_is_indexed_and_summary_keeps_only_applied_holds(self):
        record = self._record()
        first = {"update_index": 0, "status": "applied-and-observed",
            "observed_physical": [0.0, 1.0], "applied_control": [0.5],
            "observed_next_physical": [0.5, 1.0]}
        finalize_stage(self.attempt, 0, first)
        record["stage_records"]["count"] = 1
        interrupted = {"update_index": 1, "status": "started", "observed_physical": [0.5, 1.0],
            "failure_category": "controller_execution_failed"}
        write_stage(self.attempt, 1, interrupted)
        torn_tail = b'{"schema":"csl.closed-loop.stage-reference/1","update_index":1'
        with (self.attempt / STAGE_INDEX).open("ab") as stream:
            stream.write(torn_tail)
        diagnostics = []
        self.assertEqual(register_orphan_stages(self.attempt, diagnostics), 1)
        self.assertEqual(len(diagnostics), 1)
        tail_path = self.attempt / diagnostics[0]["path"]
        self.assertEqual(tail_path.read_bytes(), torn_tail)
        self.assertEqual(diagnostics[0]["sha256"], __import__("hashlib").sha256(torn_tail).hexdigest())
        self.assertEqual(len(list(iter_stage_references(self.attempt))), 2)
        self.assertEqual(register_orphan_stages(self.attempt), 0)
        record["stage_records"]["count"] = 2
        controls, states, _ = materialize_episode_summary(self.attempt, record)
        self.assertEqual(controls, [[0.5]])
        self.assertEqual(states, [[0.0, 1.0], [0.5, 1.0]])
        self.assertEqual([row["update_index"] for row in iter_stage_references(self.attempt)], [0, 1])

    def test_recovery_refuses_malformed_newline_terminated_index_row(self):
        finalize_stage(self.attempt, 0, {"update_index": 0, "status": "started"})
        with (self.attempt / STAGE_INDEX).open("ab") as stream:
            stream.write(b'{"truncated":true}\n')
        with self.assertRaisesRegex(ValueError, "not contiguous"):
            register_orphan_stages(self.attempt)

    def test_stage_reference_rejects_changed_raw_member(self):
        finalize_stage(self.attempt, 0, {"update_index": 0, "status": "started"})
        stage = self.attempt / "stage-000.json"
        stage.write_text(stage.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "byte count changed"):
            list(iter_stage_references(self.attempt))

    def test_native_request_and_response_are_saved_once_and_verified(self):
        request = '{"request":"' + "r" * (64 * 1024) + '"}\n'
        response = '{"response":"' + "s" * (64 * 1024) + '"}\n'
        capture = {"schema": "csl.closed-loop.native-query-capture/2", "capture_kind": "bridge-exchange",
            "bridge_request_sent": True, "bridge_request_transmission_status": "sent",
            "request_sha256": "request-hash", "bridge_request_raw": request,
            "bridge_response_raw": response, "bridge_response_sha256": "response-hash",
            "response_parse_status": "parsed"}
        saved = {}
        capture["bridge_response_raw"] = None
        capture["response_parse_status"] = "not_received"
        first_reference = persist_native_capture(self.attempt, 0, capture, saved)
        finalize_stage(self.attempt, 0, {"update_index": 0, "status": "complete",
            "native_query_capture": first_reference})
        second = {**capture, "bridge_request_raw": None, "bridge_response_raw": response,
            "bridge_response_sha256": "response-hash", "response_parse_status": "parsed"}
        second_reference = persist_native_capture(self.attempt, 0, second, saved)
        self.assertNotEqual(first_reference["path"], second_reference["path"])
        self.assertTrue((self.attempt / first_reference["path"]).is_file())
        first_metadata, first_payloads = read_native_capture_metadata(self.attempt, first_reference)
        metadata, payloads = read_native_capture_metadata(self.attempt, second_reference)
        self.assertEqual(first_payloads["request"].read_text(), request)
        self.assertEqual(first_metadata["request_sha256"], "request-hash")
        self.assertEqual((payloads["request"].read_text(), payloads["response"].read_text()),
            (request, response))
        self.assertEqual(metadata["request_sha256"], "request-hash")
        self.assertEqual(metadata["bridge_response_sha256"], "response-hash")
        self.assertLess((self.attempt / second_reference["path"]).stat().st_size, 2048)
        self.assertEqual(sum(1 for path in self.attempt.glob("native-query-000-*.jsonl")), 2)
        self.assertEqual(sum(1 for path in self.attempt.glob("native-query-000-*.json")), 2)
        stage_ref = list(iter_stage_references(self.attempt))[0]
        from attempt_records import read_stage_fields
        stage, _ = read_stage_fields(self.attempt, stage_ref, {"native_query_capture"})
        self.assertEqual(stage["native_query_capture"], first_reference)
        stage_metadata, stage_payloads = read_native_capture_metadata(self.attempt, stage["native_query_capture"])
        self.assertEqual(stage_metadata["response_parse_status"], "not_received")
        self.assertEqual(stage_payloads["request"].read_text(), request)

    def test_v2_attempt_summary_must_match_checked_stage_records(self):
        first = {"update_index": 0, "status": "applied-and-observed", "observed_physical": [0.0, 1.0],
            "applied_control": [0.25], "observed_next_physical": [0.5, 1.0]}
        finalize_stage(self.attempt, 0, first)
        record = self._record()
        record.update({"original_intervals": 1, "completed_holds": 1, "status": "complete",
            "controls": [[0.25]], "physical_states": [[0.0, 1.0], [0.5, 1.0]],
            "controls_sha256": __import__("hashlib").sha256(b"[[0.25]]").hexdigest()})
        record["stage_records"]["count"] = 1
        verified = verify_v2_attempt(self.attempt, record)
        self.assertEqual(verified[0:2], (record["controls"], record["physical_states"]))
        record["physical_states"][1][0] = 99.0
        with self.assertRaisesRegex(ValueError, "cached attempt states differ"):
            verify_v2_attempt(self.attempt, record)

    def test_deterministic_large_telemetry_recovery_replay_render_and_constraints(self):
        import hashlib

        import run_closed_loop
        from check_replay import rk4_step
        from contracts import load_task, manifest_sha256
        from task_models import objective

        task = load_task("syn-nl-lv-01")
        task_hash = manifest_sha256(task)
        intervals = task["episode"]["intervals"]
        dt = task["episode"]["dt"]
        control = [0.0]
        state = [field["initial"] for field in task["model"]["states"]]
        states = [state]
        telemetry = {"kind": "deterministic-2d-point-cloud",
            "points": [[float(i), float((i * 7) % 101)] for i in range(1024)]}
        for index in range(intervals):
            next_state = state
            for _ in range(20):
                next_state = rk4_step(task["model"]["case_id"], task["model"]["parameters"],
                    next_state, control, dt / 20)
            row = {"update_index": index, "status": "applied-and-observed",
                "observed_physical": state, "observed_scaled": [
                    value / field["scale"] for value, field in zip(state, task["model"]["states"])],
                "applied_control": control, "observed_next_physical": next_state,
                "geometry_telemetry": telemetry}
            if index < intervals - 1:
                finalize_stage(self.attempt, index, row)
            else:
                write_stage(self.attempt, index, row)
            state = next_state
            states.append(state)

        torn_reference = b'{"schema":"csl.closed-loop.stage-reference/1","update_index":29'
        with (self.attempt / STAGE_INDEX).open("ab") as stream:
            stream.write(torn_reference)
        diagnostics = []
        self.assertEqual(register_orphan_stages(self.attempt, diagnostics), 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual((self.attempt / diagnostics[0]["path"]).read_bytes(), torn_reference)

        controls = [control for _ in range(intervals)]
        record = {"schema": "csl.closed-loop.attempt/2", "format_version": 2,
            "attempt_id": "deterministic-integration", "task_id": task["task_id"],
            "task_sha256": task_hash, "status": "complete", "algorithm_status": "complete",
            "overall_status": "complete", "completed_holds": intervals,
            "source_sha256": task["source"]["sha256"], "original_intervals": intervals,
            "selected_initial_state_physical": states[0],
            "controls": controls, "physical_states": states,
            "controls_sha256": hashlib.sha256(json.dumps(controls, separators=(",", ":"),
                allow_nan=False).encode()).hexdigest(),
            "physical_objective": objective(task, states, controls),
            "stage_records": {"path": STAGE_INDEX, "count": intervals}}
        write_attempt(self.attempt, record)
        recovered_controls, recovered_states, _ = verify_v2_attempt(self.attempt, record)
        self.assertEqual((recovered_controls, recovered_states), (controls, states))
        io = summarize_io(self.attempt)
        stage_bytes = sum(reference["bytes"] for reference in iter_stage_references(self.attempt))
        self.assertEqual(io["stage_json_bytes_written"], stage_bytes)
        self.assertEqual(io["recovery_evidence_bytes_written"], len(torn_reference))
        self.assertGreater(io["index_repair_bytes_written"], 0)

        bridge = self.attempt / "deterministic-replay-bridge"
        bridge.write_text("#!" + sys.executable + "\n"
            "import json, sys\n"
            f"sys.path.insert(0, {str(ROOT / 'benchmarks/reporting/closed_loop')!r})\n"
            "from check_replay import rk4_step\n"
            "request = json.load(open(sys.argv[1], encoding='utf-8'))\n"
            "scenario = request['scenario']\n"
            "scales = [row['scale'] for row in scenario['states']]\n"
            "state = [value * scale for value, scale in zip(request['initial_scaled'], scales)]\n"
            "states = [state]\n"
            "for left, right, control in zip(request['times'], request['times'][1:], request['controls']):\n"
            "    state = rk4_step(scenario['case_id'], scenario['parameters'], state, control, right-left)\n"
            "    states.append(state)\n"
            "print(json.dumps({'status':'complete','physical_states':states}, allow_nan=False))\n",
            encoding="utf-8")
        bridge.chmod(0o755)
        constraints = run_closed_loop.physical_constraints(task, states, controls)
        self.assertEqual(max(constraints["sampled_state_bound_violation_by_coordinate"]), 0.0)
        run_closed_loop.replay_attempt(task, record, self.attempt, bridge, tag="deterministic")
        self.assertEqual(record["independent_replay"]["common"]["status"], "complete")
        self.assertEqual(record["independent_replay"]["tight"]["status"], "complete")
        self.assertLess(max(record["independent_replay"]["common"]["hold_endpoint_max_abs_difference"]), 1e-10)
        self.assertLess(abs(record["independent_replay"]["common"]["objective_difference"]), 1e-10)
        self.assertEqual(record["sampled_constraint_diagnostics"], constraints)
        self.assertEqual(record["render"]["status"], "complete")
        independent = json.loads((self.attempt / "deterministic-common" / "record.json").read_text())
        self.assertEqual(independent["sampled_constraint_diagnostics"][
            "state_bound_violation_by_coordinate"], [0.0, 0.0])
        self.assertEqual(independent["sampled_constraint_diagnostics"][
            "control_bound_violation_by_coordinate"], [0.0])
        for plot in record["render"]["plots"]:
            self.assertTrue((self.attempt / plot).is_file())
        self.assertEqual(json.loads((self.attempt / "postcheck-deterministic.json").read_text())[
            "overall_status"], "complete")

    def test_v1_reader_skips_large_embedded_stage_field_without_allocating_it(self):
        payload = "x" * (1024 * 1024 - 2) + '\\"' + "x" * (7 * 1024 * 1024)
        legacy = self.attempt / "attempt.json"
        legacy.write_text(json.dumps({"schema": "csl.closed-loop.attempt/1",
            "attempt_id": "legacy", "status": "incomplete", "controls": [[0.5]],
            "physical_states": [[0.0], [0.5]], "stages": [payload]}, separators=(",", ":")),
            encoding="utf-8")
        tracemalloc.start()
        try:
            record, receipt = read_attempt(legacy)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertNotIn("stages", record)
        self.assertEqual(record["controls"], [[0.5]])
        self.assertEqual(receipt.bytes_read, legacy.stat().st_size)
        self.assertLess(peak, len(payload) // 4)

    def test_v1_skipped_stage_json_accepts_escaped_quotes_and_rejects_malformed_values(self):
        legacy = self.attempt / "attempt.json"
        legacy.write_text('{"schema":"v1","status":"incomplete","stages":["a\\\"b",{"n":2}]}',
            encoding="utf-8")
        record, _ = read_attempt(legacy)
        self.assertEqual(record["status"], "incomplete")
        for skipped in ('["value",]', '["unterminated]', '[1 2]'):
            with self.subTest(skipped=skipped):
                legacy.write_text('{"schema":"v1","stages":' + skipped + '}', encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_attempt(legacy)

    def test_reader_rejects_trailing_root_syntax_and_invalid_skipped_utf8(self):
        legacy = self.attempt / "attempt.json"
        for raw in (b'{"status":"complete"} trailing',
                    b'{"status":"complete",}',
                    b'{"status":"complete","stages":["bad\x01control"]}',
                    b'{"status":"complete","stages":["bad\xffutf8"]}'):
            with self.subTest(raw=raw):
                legacy.write_bytes(raw)
                with self.assertRaises(ValueError):
                    read_attempt(legacy)

    def test_dense_nested_geometry_skip_records_parse_telemetry(self):
        geometry = "[" + ",".join(f"[{index / 10:.1f},{index / 20:.2f}]"
            for index in range(40_000)) + "]"
        record = self.attempt / "geometry.json"
        record.write_text('{"status":"complete","clouds":' + geometry +
            ',"summary":{"completed_holds":40}}', encoding="utf-8")
        fields, receipt = read_object_fields(record, selected={"status", "summary"},
            omitted={"clouds"})
        self.assertEqual(fields, {"status": "complete", "summary": {"completed_holds": 40}})
        self.assertEqual(receipt.bytes_read, record.stat().st_size)
        self.assertGreaterEqual(receipt.parse_seconds, 0.0)
        self.assertGreater(receipt.bytes_read, 500_000)


if __name__ == "__main__":
    unittest.main()

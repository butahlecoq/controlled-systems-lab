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
    summarize_io, write_attempt, write_stage)


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
            "native_query_capture": {"status": "request-sent"}}
        write_stage(self.attempt, 1, interrupted)
        self.assertEqual(register_orphan_stages(self.attempt), 1)
        record["stage_records"]["count"] = 2
        controls, states, _ = materialize_episode_summary(self.attempt, record)
        self.assertEqual(controls, [[0.5]])
        self.assertEqual(states, [[0.0, 1.0], [0.5, 1.0]])
        self.assertEqual([row["update_index"] for row in iter_stage_references(self.attempt)], [0, 1])

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
        reference = persist_native_capture(self.attempt, 0, capture, saved)
        stage = finalize_stage(self.attempt, 0, {"update_index": 0, "status": "complete",
            "native_query_capture": reference})
        metadata, payloads = read_native_capture_metadata(self.attempt, reference)
        self.assertEqual((payloads["request"].read_text(), payloads["response"].read_text()),
            (request, response))
        self.assertEqual(metadata["request_sha256"], "request-hash")
        self.assertEqual(metadata["bridge_response_sha256"], "response-hash")
        self.assertLess((self.attempt / reference["path"]).stat().st_size, 2048)
        self.assertEqual(sum(1 for path in self.attempt.glob("native-query-000-*")), 2)

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

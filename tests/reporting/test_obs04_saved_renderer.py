"""Verify OBS-04 HTML is derived from and preserves saved attempts."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/obs04"))
import render_saved


def fixture_record():
    spec = {
        "schema": "csl.comparison-spec/3",
        "arms": [{"configuration_id": "config-1", "strategy": "<script>reach-back</script>",
                  "instrumentation": "disabled"}],
        "repetitions": 4,
        "problem_id": "problem-1",
        "input_manifest_hash": "input-hash",
        "environment": {
            "build": {"source_revision": "commit-1", "source_tree_sha256": "tree-hash",
                      "compiler_id": "GNU", "compiler_version": "16", "build_type": "Release"},
            "runtime": {"binary_sha256": {"value": "binary-hash"},
                        "os_version": {"value": "Linux"}, "kernel": {"value": "kernel"},
                        "cpu_model": {"value": "CPU"}},
        },
    }
    attempts = []
    for index, (status, phase, warmup, duration) in enumerate([
        ("passed", "passed", True, 50),
        ("passed", "passed", False, 100),
        ("passed", "passed", False, 200),
        ("failed", "failed", False, None),
    ]):
        measurement = {
            "schema": "csl.obs04-instrumentation-comparison-event/6",
            "strategy": "<script>reach-back</script>",
            "instrumentation": "disabled",
            "repetition": index,
            "warmup": warmup,
            "status": "passed" if status == "passed" else "failed",
            "phase_status": phase,
            "outcome": "optimal" if status == "passed" else "unknown",
            "strategy_run_ns": duration,
            "end_to_end_ns": duration,
        }
        run_id = f"run-{index}"
        run = {
            "schema": "csl.run-statistics/6", "recorded_state": "unverified_recorded_data",
            "run": run_id, "problem": "problem-1",
            "configuration": {"id": "config-1", "value": {
                "strategy": {"strategy": "<script>reach-back</script>"},
                "collection": {"enabled": False},
            }},
            "final": {"kind": "synthesis", "value": {"termination": "completed"}}
            if status == "passed" else {"kind": "failed", "value": {}},
        }
        run_text = json.dumps(run, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        attempts.append({
            "arm_index": 0, "run_id": run_id,
            "run_digest": hashlib.sha256(run_text.encode()).hexdigest(),
            "repetition_index": index,
            "reported_status": "completed" if status == "passed" else "failed",
            "measurement_payload": json.dumps(measurement), "run": run_text,
        })
    spec_text = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    spec_id = hashlib.sha256(spec_text.encode()).hexdigest()
    record = {"schema": "csl.comparison-record/1", "comparison_run_id": "",
              "comparison_spec_id": spec_id, "track": "new-comparison",
              "spec": spec_text, "attempts": attempts}
    identity_material = {"attempts": attempts, "comparison_spec_id": spec_id,
                         "schema": "csl.comparison-record/1"}
    record["comparison_run_id"] = hashlib.sha256(
        json.dumps(identity_material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return record


class SavedRendererTests(unittest.TestCase):
    def test_html_summarizes_measured_passes_and_keeps_every_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            record_path = Path(temp) / "record.json"
            record_path.write_text(json.dumps(fixture_record()), encoding="utf-8")
            record = render_saved.load_record(record_path)
        page = render_saved.render_html(record)
        self.assertIn("150 ns (100–200)", page)
        self.assertIn("Warmups</th><th>Measured</th><th>Passed", page)
        self.assertIn("run-0", page)
        self.assertIn("run-3", page)
        self.assertIn("failed/failed", page)
        self.assertIn("&lt;script&gt;reach-back&lt;/script&gt;", page)
        self.assertNotIn("<script>reach-back</script>", page)

    def test_rejects_unknown_record_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps({"schema": "other", "attempts": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "comparison-record/1"):
                render_saved.load_record(path)

    def test_rejects_malformed_saved_measurement(self):
        record = fixture_record()
        record["attempts"][0]["measurement_payload"] = "not json"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "measurement_payload"):
                render_saved.load_record(path)

    def test_rejects_stale_comparison_identity(self):
        record = fixture_record()
        record["comparison_run_id"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "comparison run identity"):
                render_saved.load_record(path)

    def test_rejects_tampered_run_digest(self):
        record = fixture_record()
        record["attempts"][1]["run_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run digest"):
                render_saved.load_record(path)

    def test_rejects_reported_status_that_disagrees_with_measurement_and_run(self):
        record = fixture_record()
        record["attempts"][1]["reported_status"] = "failed"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity or status"):
                render_saved.load_record(path)


if __name__ == "__main__":
    unittest.main()

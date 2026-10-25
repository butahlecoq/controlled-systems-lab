"""Verify OBS-04 HTML is derived from and preserves saved attempts."""
import json
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
            "warmup": warmup,
            "status": status,
            "phase_status": phase,
            "outcome": "optimal" if status == "passed" else "unknown",
            "strategy_run_ns": duration,
            "end_to_end_ns": duration,
        }
        attempts.append({
            "run_id": f"run-{index}", "run_digest": f"digest-{index}",
            "repetition_index": index, "reported_status": status,
            "measurement_payload": json.dumps(measurement), "run": "{}",
        })
    return {"schema": "csl.comparison-record/1", "comparison_run_id": "run-id",
            "comparison_spec_id": "spec-id", "track": "new-comparison",
            "spec": json.dumps(spec), "attempts": attempts}


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


if __name__ == "__main__":
    unittest.main()

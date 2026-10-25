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
    strategy_id = "<script>reach-back</script>"
    config_value = {
        "collection": {"enabled": False, "mode": "summary"},
        "modules": [],
        "numerical": {"absolute_bits": "0", "relative_bits": "0"},
        "output": {"kind": "synthesis", "witness_count": "2"},
        "resources": {"total_threads": "1"},
        "selector": {"id": "selector", "version": "1", "options": []},
        "stop": {"deadline_budget_ticks": None},
        "strategy": {"strategy": strategy_id, "selector": "selector", "representation": "representation"},
        "workspace_policy": "fresh",
    }
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    config_id = "csl.config.v1.sha256:" + hashlib.sha256(
        b"CSL.RESOLVED.CONFIG\0v1\0" + canonical(config_value).encode()
    ).hexdigest()
    common_request = json.loads(json.dumps(config_value))
    common_request.pop("modules")
    common_request["collection"].pop("enabled")
    common_request["strategy"] = {"selector": "selector", "representation": "representation"}
    spec = {
        "schema": "csl.comparison-spec/3",
        "arms": [{"configuration_id": config_id, "strategy": strategy_id,
                  "instrumentation": "disabled"}],
        "repetitions": 4,
        "problem_id": "problem-1",
        "request_digest": hashlib.sha256(canonical(common_request).encode()).hexdigest(),
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
            "strategy": strategy_id,
            "instrumentation": "disabled",
            "repetition": index,
            "warmup": warmup,
            "status": "passed" if status == "passed" else "failed",
            "phase_status": phase,
            "analytic_family_checked": status == "passed",
            "complete_family_verified": status == "passed",
            "outcome": "optimal" if status == "passed" else "unknown",
            "strategy_run_ns": duration,
            "end_to_end_ns": duration,
        }
        run_id = f"run-{index}"
        run = {
            "schema": "csl.run-statistics/6", "recorded_state": "unverified_recorded_data",
            "run": run_id, "problem": "problem-1",
            "configuration": {"id": config_id, "value": config_value},
            "final": {"kind": "synthesis", "value": {"termination": "completed"}}
            if status == "passed" else {"kind": "failed", "value": {}},
        }
        run_text = canonical(run)
        attempts.append({
            "arm_index": 0, "run_id": run_id,
            "run_digest": hashlib.sha256(run_text.encode()).hexdigest(),
            "repetition_index": index,
            "reported_status": "completed" if status == "passed" else "failed",
            "measurement_payload": json.dumps(measurement), "run": run_text,
        })
    spec_text = canonical(spec)
    spec_id = hashlib.sha256(spec_text.encode()).hexdigest()
    record = {"schema": "csl.comparison-record/1", "comparison_run_id": "",
              "comparison_spec_id": spec_id, "track": "new-comparison",
              "spec": spec_text, "attempts": attempts}
    identity_material = {"attempts": attempts, "comparison_spec_id": spec_id,
                         "schema": "csl.comparison-record/1"}
    record["comparison_run_id"] = hashlib.sha256(
        canonical(identity_material).encode()
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

    def test_rejects_passed_phase_without_analytic_check(self):
        record = fixture_record()
        measurement = json.loads(record["attempts"][1]["measurement_payload"])
        measurement["analytic_family_checked"] = False
        record["attempts"][1]["measurement_payload"] = json.dumps(measurement)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "analytic-check flag"):
                render_saved.load_record(path)

    def test_output_cannot_replace_record(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            original = json.dumps(fixture_record()).encode()
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "must not replace"):
                render_saved.write_report(path, path)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

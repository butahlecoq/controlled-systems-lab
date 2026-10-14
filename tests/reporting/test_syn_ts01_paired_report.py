from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = ROOT / "reports" / "algorithm-results" / "tooling" / "syn_ts01_paired"
REPORT_DIR = ROOT / "reports" / "algorithm-results" / "syn-ts01-paired-20261014-b7f1ac0"
SPEC = importlib.util.spec_from_file_location("syn_ts01_paired_report", TOOL_DIR / "report.py")
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class PairedTs01ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads((REPORT_DIR / "records.json").read_text(encoding="utf-8"))

    def test_saved_bundle_validates_and_raw_sidecar_matches_typed_record(self) -> None:
        self.assertEqual(REPORT.validate(self.record), [])
        raw = (REPORT_DIR / "measurement-events.jsonl").read_bytes()
        stdout = (REPORT_DIR / "process-stdout.bin").read_bytes()
        events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        self.assertEqual(events, self.record["measurement"]["events"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.record["measurement"]["events_sha256"])
        self.assertEqual(stdout.replace(b"\r\n", b"\n"), raw)
        self.assertEqual((REPORT_DIR / "process-stderr.bin").read_bytes(), b"")

    def test_html_and_plot_show_bounded_inconclusive_result(self) -> None:
        html = (REPORT_DIR / "index.html").read_text(encoding="utf-8")
        svg = (REPORT_DIR / "performance.svg").read_text(encoding="utf-8")
        self.assertIn("Conclusion: inconclusive; no winner is claimed.", html)
        self.assertIn("latency limiter is unknown", html)
        self.assertIn("CTest duration is not used", html)
        self.assertIn("Seven alternating paired T-S01", svg)
        self.assertEqual(html, REPORT.render_html(self.record))
        self.assertEqual(svg, REPORT.render_svg(self.record))

    def test_request_and_measurement_tampering_are_rejected(self) -> None:
        bad_selector = json.loads(json.dumps(self.record))
        bad_selector["request"]["selector"]["seed"] = 32
        self.assertIn("selector_request", REPORT.validate(bad_selector))

        bad_event = json.loads(json.dumps(self.record))
        bad_event["measurement"]["events"][3]["timings_ns"]["end_to_end_strategy"]["value"] += 1
        self.assertIn("summary_statistics", REPORT.validate(bad_event))

        bad_status = json.loads(json.dumps(self.record))
        bad_status["measurement"]["events"][2]["status"] = "failed"
        self.assertIn("trial_result", REPORT.validate(bad_status))

    def test_manifest_covers_every_bundle_file(self) -> None:
        manifest = json.loads((REPORT_DIR / "manifest.json").read_text(encoding="utf-8"))
        listed = manifest["files"]
        actual = {path.name for path in REPORT_DIR.iterdir() if path.is_file() and path.name != "manifest.json"}
        self.assertEqual(set(listed), actual)
        for name, expected_hash in listed.items():
            self.assertEqual(hashlib.sha256((REPORT_DIR / name).read_bytes()).hexdigest(), expected_hash, name)


if __name__ == "__main__":
    unittest.main()

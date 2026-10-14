from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = ROOT / "reports" / "algorithm-results" / "tooling" / "syn_ts01_paired"
REPORT_DIR = ROOT / "reports" / "algorithm-results" / "syn-ts01-paired-20261014-b7f1ac0"
sys.path.insert(0, str(TOOL_DIR))
SPEC = importlib.util.spec_from_file_location("syn_ts01_paired_report", TOOL_DIR / "report.py")
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
import regenerate_bundle


class PairedTs01ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads((REPORT_DIR / "records.json").read_text(encoding="utf-8"))

    def test_saved_bundle_validates_and_raw_sidecar_matches_typed_record(self) -> None:
        self.assertEqual(REPORT.validate_bundle(REPORT_DIR), self.record)
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

    def test_saved_bundle_regenerates_byte_identically_without_solver(self) -> None:
        commands = json.loads((REPORT_DIR / "commands.json").read_text(encoding="utf-8"))
        self.assertTrue(commands["saved_bundle_is_complete_regeneration_source"])
        self.assertFalse(commands["regeneration_runs_solver"])
        self.assertIn("regenerate_bundle.py", commands["report_regeneration"][0])
        self.assertNotIn("<saved-run>", commands["report_regeneration"][0])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / REPORT.REPORT_ID
            regenerate_bundle.regenerate(REPORT_DIR, output)
            for name in sorted(REPORT.BUNDLE_FILES):
                self.assertEqual((REPORT_DIR / name).read_bytes(), (output / name).read_bytes(), name)

    def test_trial_csv_is_bound_to_saved_raw_and_typed_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / REPORT.REPORT_ID
            shutil.copytree(REPORT_DIR, bundle)
            csv_path = bundle / "trials.csv"
            csv_path.write_bytes(csv_path.read_bytes().replace(b"5123800", b"5123801", 1))
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["trials.csv"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "trial CSV differs"):
                REPORT.validate_bundle(bundle)

    def test_strict_json_parser_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        for payload in ('{"schema": "first", "schema": "second"}', '{"value": NaN}', '{"value": Infinity}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                REPORT.parse_json(payload)

    def test_bundle_rejects_duplicate_keys_in_records_manifest_sidecar_and_jsonl(self) -> None:
        mutations = {
            "records.json": lambda text: text.replace('"schema":', '"schema": "shadow", "schema":', 1),
            "manifest.json": lambda text: text.replace('"schema":', '"schema": "shadow", "schema":', 1),
            "environment.json": lambda text: text.replace('"schema":', '"schema": "shadow", "schema":', 1),
            "measurement-events.jsonl": lambda text: text.replace('"event":"header"', '"event":"header","event":"header"', 1),
        }
        for filename, mutate in mutations.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                bundle = Path(temp) / REPORT.REPORT_ID
                shutil.copytree(REPORT_DIR, bundle)
                path = bundle / filename
                path.write_text(mutate(path.read_text(encoding="utf-8")), encoding="utf-8")
                if filename != "manifest.json":
                    manifest_path = bundle / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["files"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                    REPORT.validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()

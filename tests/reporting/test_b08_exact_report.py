"""Behavior checks for the saved-data B08 exact report harness."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/reports/b08_exact_report.py"
spec = importlib.util.spec_from_file_location("b08_exact_report", TOOL)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def fixture_record():
    rows = []
    for index, warmup in report.expected_identities(7):
        stdout = report.EXPECTED_OUTPUT + "\n"
        rows.append({"repetition": index, "warmup": warmup, "status": "passed",
                     "duration_ns": 10 + index, "exit_code": 0, "timed_out": False,
                     "work_observed": True, "stdout_sha256": report.sha(stdout.encode()),
                     "stderr_sha256": report.sha(b""),
                     "detail": "exact checker and saved-record comparison passed",
                     "stdout": stdout, "stderr": ""})
    raw = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows).encode()
    record = {"schema": report.SCHEMA, "purpose": "measurement", "created_utc": "2026-10-16T00:00:00Z",
              "source": {"source_commit": report.SOURCE, "harness_commit": "a" * 40,
                         "source_files_sha256": report.SOURCE_FILE_HASHES,
                         "source_tree_oid": "b" * 40, "harness_tree_oid": "c" * 40,
                         "reviewed_harness_delta": sorted(report.ALLOWED)},
              "reference": {"source_id": "L04", "source_sha256": "6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f",
                            "plan_count": 625, "corner_histories_per_plan": 256,
                            "minimum_squared_exact": "112730080707/25000000", "exact_minimizers": 3},
              "repetitions": 7, "warmups": 1, "timeout_seconds": 60,
              "interval": report.INTERVAL,
              "environment": {"optimization": "CPython -O; -B disables bytecode writes"},
              "rows": rows, "summary": {"trials": 7, "median_ns": 13,
                                            "min_ns": 10, "max_ns": 16},
              "publishable": True, "raw_jsonl_sha256": report.sha(raw)}
    digest = report.sha(report.canonical(record))
    record["payload_sha256"] = digest
    record["report_id"] = "b08-exact-" + digest[:16]
    return record, raw


class B08ExactReportTests(unittest.TestCase):
    def test_real_checker_functional_smoke(self):
        result = subprocess.run([sys.executable, "-B", "-O", str(TOOL), "smoke"],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("functional smoke passed", result.stdout)

    def test_child_failure_retains_status_and_output(self):
        row = report.run_child([sys.executable, "-c", "import sys; print('bad'); print('failed', file=sys.stderr); sys.exit(7)"],
                               0, True, 10)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["exit_code"], 7)
        self.assertEqual(row["stdout"].strip(), "bad")
        self.assertEqual(row["stderr"].strip(), "failed")
        self.assertFalse(row["work_observed"])

    def test_saved_bundle_and_csv_tamper(self):
        record, raw = fixture_record()
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            bundle.mkdir()
            (bundle / "records.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            (bundle / "raw-trials.jsonl").write_bytes(raw)
            (bundle / "trials.csv").write_bytes(report.csv_bytes(record["rows"]))
            (bundle / "index.html").write_text(report.render_html(record), encoding="utf-8")
            files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}
            (bundle / "manifest.json").write_text(json.dumps({"schema": "csl.b08-report-files/1",
                "report_id": record["report_id"], "files": files}), encoding="utf-8")
            with zipfile.ZipFile(bundle.with_suffix(".zip"), "w") as archive:
                for path in bundle.iterdir():
                    archive.write(path, arcname=path.name)
            self.assertEqual(report.check(bundle), record["report_id"])
            with (bundle / "trials.csv").open("ab") as stream:
                stream.write(b"tampered\n")
            with self.assertRaisesRegex(ValueError, "CSV differs"):
                report.check(bundle)

    def test_refreshed_digest_cannot_hide_incorrect_summary(self):
        record, _ = fixture_record()
        record["summary"]["min_ns"] = 999
        digest = report.sha(report.canonical({k: v for k, v in record.items()
                                              if k not in ("payload_sha256", "report_id")}))
        record["payload_sha256"] = digest
        record["report_id"] = "b08-exact-" + digest[:16]
        with self.assertRaisesRegex(ValueError, "summary"):
            report.validate_record(record)

    def test_failed_collection_keeps_every_raw_attempt(self):
        example, _ = fixture_record()
        rows = example["rows"]
        rows[3] = {**rows[3], "status": "failed", "exit_code": 7,
                   "work_observed": False, "stdout": "bad\n", "stderr": "failed\n",
                   "stdout_sha256": report.sha(b"bad\n"),
                   "stderr_sha256": report.sha(b"failed\n"),
                   "detail": "child failed, timed out, or output differed"}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            note = base / "concurrent-work.txt"
            note.write_text("No other heavy local work was running during this test.", encoding="utf-8")
            bundle = base / "failed-run"
            args = SimpleNamespace(out=bundle, repetitions=7, timeout=60,
                                   concurrent_work=note, harness_commit="a" * 40)
            with patch.object(report, "source_identity", return_value=example["source"]), \
                    patch.object(report, "run_child", side_effect=rows):
                with self.assertRaisesRegex(ValueError, "publication rejected"):
                    report.collect(args)
            raw = (bundle / "raw-trials.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(raw), 8)
            self.assertEqual(json.loads(raw[3])["exit_code"], 7)
            self.assertEqual(json.loads((bundle / "records.json").read_text())["publishable"], False)
            self.assertTrue((bundle / "trials.csv").is_file())
            self.assertFalse((bundle / "index.html").exists())
            self.assertFalse(bundle.with_suffix(".zip").exists())


if __name__ == "__main__":
    unittest.main()

"""Saved-only checks for the frozen issue #3 accepted report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import io

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from issue3 import render_saved as native
import issue3_registered_reports as publication

BUNDLE = ROOT / "reports" / "algorithm-results" / native.REPORT_ID


class Issue3SavedReportTests(unittest.TestCase):
    def test_exact_saved_record_and_descriptive_batches(self):
        record = native.render(BUNDLE, check=True)
        self.assertEqual(record["source_commit"], native.SOURCE)
        self.assertEqual(record["harness_commit"], native.HARNESS)
        self.assertEqual((record["warmups"], record["measured_batches"],
                          record["failed_batches"]), (8, 56, 0))
        by_name = {r["fixture"]: r for r in record["summary"]}
        self.assertEqual(by_name["b08_rounded"]["median_batch_ns"], 84_898_000)
        self.assertEqual(by_name["b08_rounded"]["batch_checked_calls"], 1)
        self.assertEqual(by_name["l19"]["batch_checked_calls"], 10000)
        self.assertEqual(by_name["all_infeasible"]["result"]["rejected_plans"],
                         native.LITERALS["all_infeasible"]["rejected_plans"])
        self.assertIn("contention", record["concurrent_work_note"])
        self.assertIn("Inconclusive", record["performance_conclusion"])

    def test_tampered_raw_and_binary_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / native.REPORT_ID
            shutil.copytree(BUNDLE, target)
            raw = target / "evidence/accepted-001/accepted.stdout"
            raw.write_bytes(raw.read_bytes().replace(b'"checked_calls":10000',
                                                   b'"checked_calls":9999', 1))
            with self.assertRaisesRegex(ValueError, "accepted.*capture|raw JSONL pin"):
                native.validate_evidence(target)
            shutil.copyfile(BUNDLE / "evidence/accepted-001/accepted.stdout", raw)
            binary = target / "evidence/accepted-001/driver.exe"
            binary.write_bytes(binary.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "binary/fixture/build provenance"):
                native.validate_evidence(target)

    def test_literal_and_exact_binary64_oracles_reject_mutation(self):
        row = native.parse_rows(native.evidence(BUNDLE, "smoke.stdout"))[0]
        row["result"]["maximizers"] = [[1], [2]]
        row["checks"]["observed"]["maximizers"] = [[1], [2]]
        row["checks"]["expected"]["maximizers"] = [[1], [2]]
        with self.assertRaisesRegex(ValueError, "literal oracle"):
            native.check_result("l19", row)
        b08 = native.parse_rows(native.evidence(BUNDLE, "smoke.stdout"))[-1]
        request = json.loads(b08["input_canonical"])
        request["disturbance_vertices_binary64_hex"][2][0][0] = float.hex(-0.3)
        b08["input_canonical"] = json.dumps(request, separators=(",", ":"))
        b08["input_sha256"] = hashlib.sha256(b08["input_canonical"].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "exact binary64"):
            native.check_inputs(b08)

    def test_public_archive_contains_exact_saved_evidence(self):
        item = publication.adapt(BUNDLE)
        files = publication.publication_artifacts(BUNDLE, item)
        archive = publication.offline_zip(BUNDLE, item)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read(item.report_id + "/evidence/accepted-001/accepted.stdout"),
                             native.evidence(BUNDLE, "accepted.stdout"))
            self.assertEqual(zipped.read("index.html"), files["index.html"])
        self.assertEqual(publication.catalogue_entry(BUNDLE)["zip_sha256"],
                         hashlib.sha256(archive).hexdigest())

    def test_public_route_tracks_normalized_publisher_bytes(self):
        original = publication.adapt(BUNDLE).report_id
        publisher_lf = Path(publication.__file__).read_bytes().replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "issue3_registered_reports.py"
            copied.write_bytes(publisher_lf.replace(b"\n", b"\r\n"))
            with patch.object(publication, "__file__", str(copied)):
                self.assertEqual(publication.adapt(BUNDLE).report_id, original)
            copied.write_bytes(publisher_lf + b"# changed publication source\n")
            with patch.object(publication, "__file__", str(copied)):
                self.assertNotEqual(publication.adapt(BUNDLE).report_id, original)


if __name__ == "__main__":
    unittest.main()

"""Saved GEO-07 evidence must regenerate without native execution."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/geo07"))
sys.path.insert(0, str(ROOT / "scripts/reports"))
import render_saved as report
import stage_geo07

SOURCE = ROOT / "reports/algorithm-results/geo07-9ef0d347291774da"


class Geo07PublicationTests(unittest.TestCase):
    def test_saved_bytes_regenerate_page_figure_and_offline_zip(self):
        record = report.validate_native(SOURCE)
        self.assertEqual((record["source_commit"], record["harness_commit"]),
                         (report.SOURCE, report.HARNESS))
        report.render(SOURCE, check=True)
        page = (SOURCE / "index.html").read_text(encoding="utf-8")
        self.assertIn("37.555", page)
        self.assertIn("30.668", page)
        self.assertIn("42.760", page)
        self.assertIn("inconclusive", page)
        self.assertIn("nlohmann JSON", page)
        with zipfile.ZipFile(io.BytesIO((SOURCE / "bundle.zip").read_bytes())) as archive:
            self.assertEqual(archive.read(SOURCE.name + "/trials.jsonl"),
                             (SOURCE / "trials.jsonl").read_bytes())
            self.assertEqual(archive.read(SOURCE.name + "/index.html"),
                             (SOURCE / "index.html").read_bytes())

    def test_changed_native_raw_or_displayed_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / SOURCE.name
            shutil.copytree(SOURCE, bundle)
            with (bundle / "trials.jsonl").open("ab") as stream:
                stream.write(b'{"forged":true}\n')
            with self.assertRaises(ValueError):
                report.render(bundle, check=True)
            shutil.copyfile(SOURCE / "trials.jsonl", bundle / "trials.jsonl")
            page = (bundle / "index.html").read_text(encoding="utf-8").replace("37.555", "99.999")
            (bundle / "index.html").write_text(page, encoding="utf-8")
            with self.assertRaises(ValueError):
                report.render(bundle, check=True)

    def test_extension_stages_new_route_with_exact_source_bytes(self):
        item = stage_geo07.validate(SOURCE)
        self.assertEqual(item.source_report_id, SOURCE.name)
        catalogue = json.loads((SOURCE.parent / "geo07-publications.json").read_text(encoding="utf-8"))
        self.assertEqual(catalogue["reports"], [stage_geo07.catalogue_entry(SOURCE)])
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            old = b'<!doctype html><html lang="en"><body><ul><li>Existing report</li></ul></body></html>'
            (site / "index.html").write_bytes(old)
            (site / "existing.txt").write_bytes(b"old route stays fixed")
            rid = stage_geo07.stage(SOURCE.parent / "geo07-publications.json", site)
            self.assertEqual(rid, item.report_id)
            self.assertEqual((site / "existing.txt").read_bytes(), b"old route stays fixed")
            self.assertEqual((site / rid / "trials.jsonl").read_bytes(),
                             (SOURCE / "trials.jsonl").read_bytes())
            self.assertTrue((site / (rid + ".zip")).is_file())
            self.assertIn(rid, (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256((site / rid / "records.json").read_bytes()).hexdigest(),
                             hashlib.sha256((SOURCE / "records.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()

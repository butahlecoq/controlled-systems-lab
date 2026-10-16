"""Saved GEO-07 evidence must regenerate without native execution."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/geo07"))
sys.path.insert(0, str(ROOT / "scripts/reports"))
import render_saved as report
import stage_geo07

SOURCE = ROOT / "reports/algorithm-results/geo07-9ef0d347291774da"


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


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

    def test_extracted_offline_page_has_no_dead_local_downloads(self):
        with zipfile.ZipFile(io.BytesIO((SOURCE / "bundle.zip").read_bytes())) as archive:
            page = archive.read(SOURCE.name + "/index.html").decode("utf-8")
            links = LocalLinks()
            links.feed(page)
            self.assertTrue(links.hrefs)
            for href in links.hrefs:
                with self.subTest(href=href):
                    self.assertIn(SOURCE.name + "/" + href, archive.namelist())

    def test_public_id_binds_all_publisher_modules_with_lf_line_endings(self):
        publisher_files = ("stage_geo07.py", "geo07/render_saved.py",
                           "geo07/collect.py", "registered_reports.py")
        original_id = stage_geo07.validate(SOURCE).report_id
        with tempfile.TemporaryDirectory() as directory:
            fake_root = Path(directory)
            originals = {}
            for name in publisher_files:
                content = (ROOT / "scripts/reports" / name).read_bytes()
                originals[name] = content
                target = fake_root / "scripts/reports" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            with mock.patch.object(stage_geo07, "ROOT", fake_root):
                self.assertEqual(stage_geo07.validate(SOURCE).report_id, original_id)
                for name in publisher_files:
                    target = fake_root / "scripts/reports" / name
                    target.write_bytes(originals[name].replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                self.assertEqual(stage_geo07.validate(SOURCE).report_id, original_id)
                for name in publisher_files:
                    target = fake_root / "scripts/reports" / name
                    target.write_bytes(originals[name] + b"\n# reviewed publisher change\n")
                    with self.subTest(publisher=name):
                        self.assertNotEqual(stage_geo07.validate(SOURCE).report_id, original_id)
                    target.write_bytes(originals[name])

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

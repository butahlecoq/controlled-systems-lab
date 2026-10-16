"""The GEO-07 dependent report regenerates from saved public-port evidence."""
from __future__ import annotations

import csv
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
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_geo07_dependent as stage

BUNDLE = ROOT / "reports/algorithm-results/geo07-dependent-4dcc5a8fe36f17ed"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class DependentPublication(unittest.TestCase):
    def test_saved_native_identity_and_failed_attempts(self):
        record = stage.report.validate_native(BUNDLE)
        self.assertEqual(record["report_id"], BUNDLE.name)
        self.assertEqual(record["source_commit"], "5411e37ad456f0d5b3bf775130f149622ef5ebfa")
        self.assertEqual(record["harness_commit"], "eef1eda3d326418a392b3cc1e8f8f4b204ca7a73")
        self.assertEqual(record["reviewed_code_commit"], "eaa32fdfdcf42b3f3f3221dd3031d654fe05e576")
        self.assertEqual(hashlib.sha256((BUNDLE / "trials.stdout").read_bytes()).hexdigest(),
                         "3cc538611451add4eaef7adcbb5f225bbe668eadb8c32bd9e98de298f85fbc0c")
        self.assertEqual(len(record["rows"]), 16)
        self.assertEqual(sum(row["checked_calls"] for row in record["rows"]), 32000)
        self.assertEqual(record["summary"]["shared_cancellation"]["successes"], 7)
        self.assertEqual(record["summary"]["constrained_shared"]["successes"], 7)
        self.assertFalse(json.loads((BUNDLE / "evidence/rejected-001/collection-status.json").read_bytes())["publishable"])
        self.assertFalse(json.loads((BUNDLE / "evidence/rejected-002/collection-status.json").read_bytes())["publishable"])

    def test_rendered_values_csv_and_offline_zip_links(self):
        stage.report.render(BUNDLE, check=True)
        page = (BUNDLE / "index.html").read_text(encoding="utf-8")
        for literal in ("x = 0", "u − v = 0", "u + w = 0", "25.957", "32.201",
                        "exploratory", "inconclusive", "binary64", "rejected-001", "rejected-002"):
            self.assertIn(literal, page)
        rows = list(csv.DictReader(io.StringIO((BUNDLE / "trials.csv").read_text(encoding="utf-8"))))
        self.assertEqual(len(rows), 16)
        self.assertEqual(sum(row["warmup"] == "True" for row in rows), 2)
        self.assertEqual(sum(int(row["checked_calls"]) for row in rows), 32000)
        with zipfile.ZipFile(BUNDLE / "bundle.zip") as archive:
            self.assertEqual(archive.read(BUNDLE.name + "/trials.stdout"), (BUNDLE / "trials.stdout").read_bytes())
            for name in ("index.html", BUNDLE.name + "/index.html"):
                parser = Links()
                parser.feed(archive.read(name).decode("utf-8"))
                self.assertTrue(parser.hrefs)
                for href in parser.hrefs:
                    self.assertIn(str((Path(name).parent / href).as_posix()), archive.namelist())

    def test_native_and_rendered_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, bundle)
            for name in ("trials.stdout", "records.json", "evidence/rejected-001/manifest.json",
                         "evidence/rejected-002/trials.stdout", "index.html"):
                with self.subTest(name=name):
                    path = bundle / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"X")
                    with self.assertRaises(ValueError):
                        stage.report.render(bundle, check=True)
                    path.write_bytes(original)

    def test_catalogue_route_and_existing_site(self):
        item = stage.validate(BUNDLE)
        catalog = BUNDLE.parent / "geo07-dependent-publications.json"
        self.assertEqual(json.loads(catalog.read_bytes())["reports"], [stage.catalogue_entry(BUNDLE)])
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text('<!doctype html><html lang="en"><body><ul></ul></body></html>',
                                             encoding="utf-8")
            (site / "existing.txt").write_bytes(b"preserved")
            self.assertEqual(stage.stage(catalog, site), item.report_id)
            self.assertEqual((site / "existing.txt").read_bytes(), b"preserved")
            self.assertEqual((site / item.report_id / "trials.stdout").read_bytes(),
                             (BUNDLE / "trials.stdout").read_bytes())
            with self.assertRaises(ValueError):
                stage.stage(catalog, site)

    def test_public_identity_binds_publisher_bytes(self):
        original = stage.validate(BUNDLE).report_id
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary)
            for name in stage.PUBLISHERS:
                target = fake / "scripts/reports" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / "scripts/reports" / name).read_bytes())
            with mock.patch.object(stage, "ROOT", fake):
                self.assertEqual(stage.validate(BUNDLE).report_id, original)
                target = fake / "scripts/reports/stage_geo07_dependent.py"
                target.write_bytes(target.read_bytes() + b"\n# changed publisher\n")
                self.assertNotEqual(stage.validate(BUNDLE).report_id, original)

    def test_stage_preserves_existing_catalogue_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            stage.site.stage(BUNDLE.parent / "catalog.json", site, check=True)
            prior = next(row for row in json.loads((BUNDLE.parent / "catalog.json").read_bytes())["reports"]
                         if row["report_kind"] == "geo06-quickhull")
            page = (site / prior["report_id"] / "index.html").read_bytes()
            stage.stage(BUNDLE.parent / "geo07-dependent-publications.json", site)
            self.assertEqual((site / prior["report_id"] / "index.html").read_bytes(), page)

    def test_pages_workflow_is_main_only_and_stages_route(self):
        workflow = (ROOT / ".github/workflows/algorithm-reports.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/reports/stage_geo07_dependent.py", workflow)
        self.assertIn("reports/algorithm-results/geo07-dependent-publications.json", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)


if __name__ == "__main__":
    unittest.main()

"""Saved GEO-07 registered-port evidence must regenerate without native execution."""
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
sys.path.insert(0, str(ROOT / "scripts/reports/geo07_port"))
sys.path.insert(0, str(ROOT / "scripts/reports"))
import render_saved as report
import stage_geo07_port as stage

BUNDLE = ROOT / "reports/algorithm-results/geo07-port-4dee19cde3d50259"


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class Geo07PortPublicationTests(unittest.TestCase):
    def test_public_zip_root_and_nested_pages_have_live_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text('<!doctype html><html lang="en"><body><ul></ul></body></html>',
                                             encoding="utf-8")
            public_id = stage.stage(BUNDLE.parent / "geo07-port-publications.json", site)
            with zipfile.ZipFile(site / (public_id + ".zip")) as archive:
                for page_name in ("index.html", public_id + "/index.html"):
                    links = LocalLinks()
                    links.feed(archive.read(page_name).decode("utf-8"))
                    self.assertTrue(links.hrefs)
                    for href in links.hrefs:
                        with self.subTest(page=page_name, href=href):
                            self.assertIn(str((Path(page_name).parent / href).as_posix()), archive.namelist())

    def test_content_bound_route_preserves_existing_site_and_raw_bytes(self):
        item = stage.validate(BUNDLE)
        catalogue = json.loads((BUNDLE.parent / "geo07-port-publications.json").read_bytes())
        self.assertEqual(catalogue["reports"], [stage.catalogue_entry(BUNDLE)])
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text('<!doctype html><html lang="en"><body><ul></ul></body></html>',
                                             encoding="utf-8")
            (site / "existing-route.txt").write_bytes(b"unchanged existing route")
            self.assertEqual(stage.stage(BUNDLE.parent / "geo07-port-publications.json", site), item.report_id)
            self.assertEqual((site / "existing-route.txt").read_bytes(), b"unchanged existing route")
            self.assertEqual((site / item.report_id / "trials.jsonl").read_bytes(),
                             (BUNDLE / "trials.jsonl").read_bytes())
            self.assertIn(item.report_id, (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256((site / (item.report_id + ".zip")).read_bytes()).hexdigest(),
                             catalogue["reports"][0]["zip_sha256"])
            with self.assertRaises(ValueError):
                stage.stage(BUNDLE.parent / "geo07-port-publications.json", site)

    def test_real_catalogue_stage_keeps_existing_geo06_route_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            site_root = Path(temporary) / "site"
            stage.site.stage(BUNDLE.parent / "catalog.json", site_root, check=True)
            geo06 = next(row for row in json.loads((BUNDLE.parent / "catalog.json").read_bytes())["reports"]
                         if row["report_kind"] == "geo06-quickhull")
            old_page = (site_root / geo06["report_id"] / "index.html").read_bytes()
            stage.stage(BUNDLE.parent / "geo07-port-publications.json", site_root)
            self.assertEqual((site_root / geo06["report_id"] / "index.html").read_bytes(), old_page)

    def test_pages_workflow_stages_additive_geo07_port_route(self):
        workflow = (ROOT / ".github/workflows/algorithm-reports.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/reports/stage_geo07_port.py", workflow)
        self.assertIn("reports/algorithm-results/geo07-port-publications.json", workflow)

    def test_public_id_binds_all_byte_generating_publishers_with_lf_normalization(self):
        originals = {name: (ROOT / "scripts/reports" / name).read_bytes() for name in stage.PUBLISHERS}
        original_id = stage.validate(BUNDLE).report_id
        with tempfile.TemporaryDirectory() as temporary:
            fake_root = Path(temporary)
            for name, content in originals.items():
                target = fake_root / "scripts/reports" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            with mock.patch.object(stage, "ROOT", fake_root):
                self.assertEqual(stage.validate(BUNDLE).report_id, original_id)
                for name, content in originals.items():
                    target = fake_root / "scripts/reports" / name
                    target.write_bytes(content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                    self.assertEqual(stage.validate(BUNDLE).report_id, original_id)
                    target.write_bytes(content + b"\n# changed publisher bytes\n")
                    with self.subTest(publisher=name):
                        self.assertNotEqual(stage.validate(BUNDLE).report_id, original_id)
                    target.write_bytes(content)

    def test_changed_catalogue_fails_staging(self):
        catalogue = json.loads((BUNDLE.parent / "geo07-port-publications.json").read_bytes())
        catalogue["reports"][0]["zip_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            shutil.copytree(BUNDLE, temporary_root / BUNDLE.name)
            path = temporary_root / "geo07-port-publications.json"
            path.write_text(json.dumps(catalogue), encoding="utf-8")
            with self.assertRaises(ValueError):
                stage.stage(path, temporary_root)

    def test_pinned_native_and_separate_post_host_bytes(self):
        record = report.validate_native(BUNDLE)
        self.assertEqual(record["report_id"], "geo07-port-4dee19cde3d50259")
        self.assertEqual(record["source_commit"], "41b4b58f2ef982e75554519862afdd803e30f717")
        self.assertEqual(record["harness_commit"], "95ba77d3fb2077ec3f56c8fe68903eb18f26488a")
        self.assertEqual(hashlib.sha256((BUNDLE / "trials.jsonl").read_bytes()).hexdigest(),
                         "41649b7f4acde2c0e980b7c648358d9d217f68e3e5ec9c103f25173e7ab0d39e")
        self.assertEqual(hashlib.sha256((BUNDLE / "post-host-observation.json").read_bytes()).hexdigest(),
                         "dff519dc043fe14cd451f919315a9eee34f00a919e979fba46be809a71548c8a")
        self.assertEqual(record["environment"]["host_observation"]["build_processes"],
                         {"MSBuild": 0, "cl": 0, "cmake": 0})
        self.assertEqual((record["collection_start_utc"], record["collection_end_utc"]),
                         ("2026-10-16T14:51:36.008720+00:00", "2026-10-16T14:51:37.703130+00:00"))

    def test_generated_tables_figure_and_source_zip_use_saved_results(self):
        report.render(BUNDLE, check=True)
        page = (BUNDLE / "index.html").read_text(encoding="utf-8")
        for literal in ("2 ≤ x ≤ 12", "1 ≤ x ≤ 7", "2, 6, 8, 12", "57.405", "69.538", "83.050",
                        "exploratory", "inconclusive", "binary64", "7f31a8988d36fde6846b4fbb463b797ced9f4b93796bf06e3e9db5843a7d433e"):
            with self.subTest(literal=literal):
                self.assertIn(literal, page)
        self.assertIn("enumerated corner images 2, 6, 8, 12", page)
        self.assertIn("only 2 and 12 are extreme endpoints", page)
        self.assertIn("V-representation rows", page)
        self.assertNotIn("all four vertices", page)
        self.assertNotIn("V vertices", page)
        trials = list(csv.DictReader(io.StringIO((BUNDLE / "trials.csv").read_text(encoding="utf-8"))))
        self.assertEqual(len(trials), 24)
        self.assertEqual(sum(row["warmup"] == "True" for row in trials), 3)
        self.assertEqual(sum(int(row["checked_calls"]) for row in trials), 120000)
        self.assertIn("Seven measured verified batches", (BUNDLE / "performance.svg").read_text(encoding="utf-8"))
        with zipfile.ZipFile(BUNDLE / "bundle.zip") as archive:
            nested = BUNDLE.name + "/index.html"
            self.assertEqual(archive.read(BUNDLE.name + "/trials.jsonl"), (BUNDLE / "trials.jsonl").read_bytes())
            self.assertEqual(archive.read(nested), (BUNDLE / "index.html").read_bytes())
            for page_name in ("index.html", nested):
                links = LocalLinks()
                links.feed(archive.read(page_name).decode("utf-8"))
                self.assertTrue(links.hrefs)
                for href in links.hrefs:
                    with self.subTest(page=page_name, href=href):
                        resolved = str((Path(page_name).parent / href).as_posix())
                        self.assertIn(resolved, archive.namelist())

    def test_native_or_rendered_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, bundle)
            for name in ("trials.jsonl", "records.json", "manifest.json", "post-host-observation.json"):
                with self.subTest(name=name):
                    original = (bundle / name).read_bytes()
                    (bundle / name).write_bytes(original + b"\n")
                    with self.assertRaises(ValueError):
                        report.render(bundle, check=True)
                    (bundle / name).write_bytes(original)
            original_page = (bundle / "index.html").read_bytes()
            (bundle / "index.html").write_bytes(original_page.replace(b"57.405", b"99.999"))
            with self.assertRaises(ValueError):
                report.render(bundle, check=True)

    def test_generated_assets_are_exact_byte_deterministic(self):
        record = report.validate_native(BUNDLE)
        self.assertEqual(report.generated(record), report.generated(record))
        self.assertEqual(json.loads((BUNDLE / "report-manifest.json").read_bytes())["files"]["trials.jsonl"],
                         hashlib.sha256((BUNDLE / "trials.jsonl").read_bytes()).hexdigest())
        report.render(BUNDLE, check=True)


if __name__ == "__main__":
    unittest.main()

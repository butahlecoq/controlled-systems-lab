"""Saved GEO-07 evidence must regenerate without native execution."""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/geo07"))
sys.path.insert(0, str(ROOT / "scripts/reports"))
report = importlib.import_module("render_saved")
stage_geo07 = importlib.import_module("stage_geo07")
stage_geo07_dependent = importlib.import_module("stage_geo07_dependent")
stage_geo07_port = importlib.import_module("stage_geo07_port")

SOURCE = ROOT / "reports/algorithm-results/geo07-9ef0d347291774da"


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class Geo07PublicationTests(unittest.TestCase):
    def test_shared_publication_zip_preserves_default_and_validates_root_launcher(self):
        report_id = "sample-1"
        files = {"index.html": b"<html>nested</html>\n", "records.json": b"{}\n"}
        legacy = stage_geo07.common.publication_zip(report_id, files)
        self.assertEqual(
            hashlib.sha256(legacy).hexdigest(),
            "1c478bd3046e4837041fd18e7e90700a196464b732a2dfb8a93296ae7cc3af47",
        )
        landing = (
            b'<!doctype html><html lang="en"><body><a href="sample-1/index.html">Open report</a>'
            b"</body></html>\n"
        )
        archive_bytes = stage_geo07.common.publication_zip(
            report_id, files, root_landing_page=landing
        )
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                archive.namelist(),
                ["index.html", "sample-1/index.html", "sample-1/records.json"],
            )
            self.assertEqual(archive.read("index.html"), landing)
            self.assertEqual(archive.read("sample-1/index.html"), files["index.html"])
            self.assertEqual(archive.read("sample-1/records.json"), files["records.json"])
        for invalid in (
            b"<a href='elsewhere/index.html'>Open</a>",
            b"<a href='sample-1/index.html'>Open</a><a href='elsewhere'>Else</a>",
            b"<a href='sample-1/index.html'>Open</a><img src='remote.png'>",
            b"<html lang='en'><body><template><a href='sample-1/index.html'>Hidden</a></template></body></html>",
            b"\xff",
        ):
            with self.subTest(landing=invalid), self.assertRaises(ValueError):
                stage_geo07.common.publication_zip(report_id, files, root_landing_page=invalid)

    def test_geo07_public_zip_and_catalogue_hashes_match_prechange_outputs(self):
        baselines = (
            (
                stage_geo07,
                SOURCE,
                SOURCE.parent / "geo07-publications.json",
                "0847d3fe95df1d6481ada90bb523aee5b971afd58d1dc00415c74b579ec2083c",
                "5bad1e17414a353faa3df50e8e0f4b36829abef03946ba2609f6aea311f17e93",
            ),
            (
                stage_geo07_port,
                ROOT / "reports/algorithm-results/geo07-port-4dee19cde3d50259",
                ROOT / "reports/algorithm-results/geo07-port-publications.json",
                "63a226d6e5a5df0352e2e44ff39dcbc7aa586c1a3b82f4d10effea718cd62fcc",
                "bb49e7c54d01d573197e65c2cc876c69b65ad16e49bd4386f093924b506ae4b3",
            ),
            (
                stage_geo07_dependent,
                ROOT / "reports/algorithm-results/geo07-dependent-4dcc5a8fe36f17ed",
                ROOT / "reports/algorithm-results/geo07-dependent-publications.json",
                "c046a49dea35dc3c12f77061d92b3166f994c821f9a2f14fb494354541b8fda9",
                "6543cf41207f36cf501c67ed31213b1b1ddcc863e3c673d1819cfa70b6b05e58",
            ),
        )
        for stage, bundle, catalogue_path, zip_sha256, catalogue_sha256 in baselines:
            with self.subTest(stage=stage.__name__):
                entry = stage.catalogue_entry(bundle)
                self.assertEqual(entry["zip_sha256"], zip_sha256)
                self.assertEqual(
                    hashlib.sha256(catalogue_path.read_bytes()).hexdigest(), catalogue_sha256
                )
                saved = json.loads(catalogue_path.read_bytes())["reports"][0]
                self.assertEqual(saved, entry)

    def test_saved_bytes_regenerate_page_figure_and_offline_zip(self):
        record = report.validate_native(SOURCE)
        self.assertEqual(
            (record["source_commit"], record["harness_commit"]), (report.SOURCE, report.HARNESS)
        )
        report.render(SOURCE, check=True)
        page = (SOURCE / "index.html").read_text(encoding="utf-8")
        self.assertIn("37.555", page)
        self.assertIn("30.668", page)
        self.assertIn("42.760", page)
        self.assertIn("inconclusive", page)
        self.assertIn("nlohmann JSON", page)
        with zipfile.ZipFile(io.BytesIO((SOURCE / "bundle.zip").read_bytes())) as archive:
            self.assertEqual(
                archive.read(SOURCE.name + "/trials.jsonl"), (SOURCE / "trials.jsonl").read_bytes()
            )
            self.assertEqual(
                archive.read(SOURCE.name + "/index.html"), (SOURCE / "index.html").read_bytes()
            )

    def test_extracted_offline_page_has_no_dead_local_downloads(self):
        with zipfile.ZipFile(io.BytesIO((SOURCE / "bundle.zip").read_bytes())) as archive:
            page = archive.read(SOURCE.name + "/index.html").decode("utf-8")
            links = LocalLinks()
            links.feed(page)
            self.assertTrue(links.hrefs)
            for href in links.hrefs:
                with self.subTest(href=href):
                    self.assertIn(SOURCE.name + "/" + href, archive.namelist())

    def test_public_zip_root_and_nested_pages_have_live_local_links(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text(
                "<html><body><ul></ul></body></html>", encoding="utf-8"
            )
            rid = stage_geo07.stage(SOURCE.parent / "geo07-publications.json", site)
            with zipfile.ZipFile(site / (rid + ".zip")) as archive:
                extracted = site / "extracted"
                archive.extractall(extracted)
            nested_page = rid + "/index.html"
            for page_name in ("index.html", nested_page):
                links = LocalLinks()
                links.feed((extracted / page_name).read_text(encoding="utf-8"))
                self.assertTrue(links.hrefs)
                if page_name == "index.html":
                    self.assertIn(nested_page, links.hrefs)
                for href in links.hrefs:
                    with self.subTest(page=page_name, href=href):
                        self.assertTrue(((extracted / page_name).parent / href).is_file())

    @mock.patch.dict(stage_geo07.common._HISTORICAL_PUBLICATIONS, {}, clear=True)
    def test_unpinned_public_id_binds_all_publisher_modules_with_lf_line_endings(self):
        publisher_files = (
            "stage_geo07.py",
            "geo07/render_saved.py",
            "geo07/collect.py",
            "registered_reports.py",
        )
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
                    target.write_bytes(
                        originals[name].replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    )
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
        catalogue = json.loads(
            (SOURCE.parent / "geo07-publications.json").read_text(encoding="utf-8")
        )
        self.assertEqual(catalogue["reports"], [stage_geo07.catalogue_entry(SOURCE)])
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            old = b'<!doctype html><html lang="en"><body><ul><li>Existing report</li></ul></body></html>'
            (site / "index.html").write_bytes(old)
            (site / "existing.txt").write_bytes(b"old route stays fixed")
            rid = stage_geo07.stage(SOURCE.parent / "geo07-publications.json", site)
            self.assertEqual(rid, item.report_id)
            self.assertEqual((site / "existing.txt").read_bytes(), b"old route stays fixed")
            self.assertEqual(
                (site / rid / "trials.jsonl").read_bytes(), (SOURCE / "trials.jsonl").read_bytes()
            )
            self.assertTrue((site / (rid + ".zip")).is_file())
            self.assertIn(rid, (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(
                hashlib.sha256((site / rid / "records.json").read_bytes()).hexdigest(),
                hashlib.sha256((SOURCE / "records.json").read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()

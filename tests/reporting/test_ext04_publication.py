"""EXT-04 saved report and public route must regenerate from audited bytes."""
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
sys.path.insert(0, str(ROOT / "scripts/reports/ext04"))
sys.path.insert(0, str(ROOT / "scripts/reports"))
import render_saved as report
import stage_ext04

SOURCE = ROOT / "reports/algorithm-results/ext04-df62c7c6d295e135"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []

    def handle_starttag(self, tag, attrs):
        if tag in ("a", "img"):
            self.local.extend(value for key, value in attrs if key in ("href", "src"))


class Ext04Publication(unittest.TestCase):
    def test_audited_raw_and_literal_outcomes_regenerate(self):
        record = report.validate_native(SOURCE)
        self.assertEqual((record["source_commit"], record["harness_commit"]),
                         ("c23aaf13c1c1e5480cc22dd5bac5cd3e79562609",
                          "959755ed5f69641ae643e852c00efe718fa9eb86"))
        self.assertEqual(hashlib.sha256((SOURCE / "trials.jsonl").read_bytes()).hexdigest(),
                         "7c6c33024ffa93eb37065bf1a66df8a8f02827e0e0e039ec93a9090db1b900d8")
        self.assertEqual([(name, record["summary"][name]["median_batch_ns"])
                          for name in report.collect.EXPECTED],
                         [("partial_noisy_delayed", 254441900),
                          ("post_feedthrough", 160891000), ("no_channel", 68215900)])
        report.render(SOURCE, check=True)
        page = (SOURCE / "index.html").read_text(encoding="utf-8")
        for literal in ("2, 7", "9, 7", "post-decision feedthrough", "no implicit observation",
                        "254.442", "160.891", "68.216", "inconclusive"):
            self.assertIn(literal, page.lower())

    def test_changed_raw_or_displayed_result_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / SOURCE.name
            shutil.copytree(SOURCE, bundle)
            (bundle / "trials.jsonl").write_bytes((bundle / "trials.jsonl").read_bytes() + b'{}\n')
            with self.assertRaises(ValueError):
                report.render(bundle, check=True)
            shutil.copyfile(SOURCE / "trials.jsonl", bundle / "trials.jsonl")
            (bundle / "index.html").write_text(
                (bundle / "index.html").read_text(encoding="utf-8").replace("254.442", "999.999"),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                report.render(bundle, check=True)

    def test_source_and_public_zip_root_and_nested_links_resolve(self):
        stage_ext04.validate(SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text('<html><body><ul></ul></body></html>', encoding="utf-8")
            public_id = stage_ext04.stage(SOURCE.parent / "ext04-publications.json", site)
            for archive_bytes, nested in (((SOURCE / "bundle.zip").read_bytes(), SOURCE.name),
                                          ((site / (public_id + ".zip")).read_bytes(), public_id)):
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    entries = set(archive.namelist())
                    for page_name in ("index.html", nested + "/index.html"):
                        links = Links()
                        links.feed(archive.read(page_name).decode("utf-8"))
                        self.assertTrue(links.local)
                        parent = Path(page_name).parent
                        for href in links.local:
                            with self.subTest(page=page_name, href=href):
                                self.assertIn((parent / href).as_posix(), entries)

    def test_public_identity_binds_every_byte_generating_module(self):
        original = stage_ext04.validate(SOURCE).report_id
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory)
            originals = {}
            for name in stage_ext04.PUBLISHERS:
                content = (ROOT / "scripts/reports" / name).read_bytes()
                originals[name] = content
                path = fake / "scripts/reports" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            with mock.patch.object(stage_ext04, "ROOT", fake):
                self.assertEqual(stage_ext04.validate(SOURCE).report_id, original)
                for name, content in originals.items():
                    (fake / "scripts/reports" / name).write_bytes(
                        content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                self.assertEqual(stage_ext04.validate(SOURCE).report_id, original)
                for name, content in originals.items():
                    path = fake / "scripts/reports" / name
                    path.write_bytes(content + b"\n# changed publisher\n")
                    with self.subTest(module=name):
                        self.assertNotEqual(stage_ext04.validate(SOURCE).report_id, original)
                    path.write_bytes(content)

    def test_extension_stages_new_route_without_changing_existing_files(self):
        item = stage_ext04.validate(SOURCE)
        catalogue = json.loads((SOURCE.parent / "ext04-publications.json").read_text(encoding="utf-8"))
        self.assertEqual(catalogue["reports"], [stage_ext04.catalogue_entry(SOURCE)])
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            old = b'<html><body><ul><li>Existing report</li></ul></body></html>'
            (site / "index.html").write_bytes(old)
            (site / "existing.txt").write_bytes(b"existing route remains fixed")
            report_id = stage_ext04.stage(SOURCE.parent / "ext04-publications.json", site)
            self.assertEqual(report_id, item.report_id)
            self.assertEqual((site / "existing.txt").read_bytes(), b"existing route remains fixed")
            self.assertEqual((site / report_id / "trials.jsonl").read_bytes(),
                             (SOURCE / "trials.jsonl").read_bytes())
            self.assertIn(report_id, (site / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

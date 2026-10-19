from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/ext07"))
sys.path.insert(0, str(ROOT / "scripts/reports"))

import collect
import render_saved
import stage_ext07


class Ext07SavedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bundles = sorted((ROOT / "reports/algorithm-results").glob("ext07-hybrid-*"))
        cls.bundle = next((path for path in bundles if path.is_dir()), None)
        if cls.bundle is None:
            raise unittest.SkipTest("EXT-07 report bundle is created from a frozen measured source")

    def test_saved_report_rebuilds_and_catalogue_binds_every_file(self) -> None:
        self.assertEqual(render_saved.render(self.bundle, check=True)["report_id"], self.bundle.name)
        entry = stage_ext07.catalog_entry(self.bundle)
        self.assertEqual(entry["source_commit"], collect.read_json(self.bundle / "records.json")["source_commit"])
        self.assertEqual(entry["zip_sha256"], collect.sha((self.bundle / (self.bundle.name + ".zip")).read_bytes()))

    def test_stager_copies_only_the_validated_bundle_and_adds_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged_bundle = root / self.bundle.name
            shutil.copytree(self.bundle, staged_bundle)
            catalog = root / "ext07-publications.json"
            catalog.write_text(json.dumps({"schema": "csl.ext07-publications/1",
                                           "reports": [stage_ext07.catalog_entry(staged_bundle)]}),
                               encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>", encoding="utf-8")
            self.assertEqual(stage_ext07.stage(catalog, site), self.bundle.name)
            self.assertTrue((site / self.bundle.name / "example-2d.html").is_file())
            self.assertIn("example-2d.html", (site / "index.html").read_text(encoding="utf-8"))

    def test_report_identity_rejects_tampered_raw_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / self.bundle.name
            shutil.copytree(self.bundle, copied)
            with (copied / "measure.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{}\n")
            with self.assertRaises(ValueError):
                render_saved.validate(copied)


if __name__ == "__main__":
    unittest.main()

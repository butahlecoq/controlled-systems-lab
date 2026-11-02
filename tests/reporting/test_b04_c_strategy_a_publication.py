"""Publication-boundary tests for the corrected B04-C Strategy A report."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from scripts.reports import stage_b04_c_strategy_a as publisher


class B04CStrategyAPublicationTests(unittest.TestCase):
    def test_stage_builds_hash_bound_page_and_offline_bundle(self):
        with tempfile.TemporaryDirectory(prefix="b04-c-strategy-a-publication-") as temporary:
            root = Path(temporary)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><main><h1>Reports</h1></main></body></html>',
                encoding="utf-8")

            route = publisher.stage(publisher.SOURCE, site)

            report = site / route
            self.assertTrue((report / "index.html").is_file())
            self.assertTrue((report / "trajectory.svg").is_file())
            self.assertTrue((report / "publication-manifest.json").is_file())
            self.assertIn(f'href="{route}/index.html"', (site / "index.html").read_text())
            manifest = publisher.read_json(report / "publication-manifest.json")
            self.assertEqual(manifest["report_id"], route)
            for name, expected in manifest["published_files"].items():
                self.assertEqual(hashlib.sha256((report / name).read_bytes()).hexdigest(), expected)
            with zipfile.ZipFile(site / f"{route}.zip") as archive:
                self.assertIn(f"{route}/strategy-a-ci.json", archive.namelist())
                self.assertEqual(archive.read(f"{route}/record.json"), (report / "record.json").read_bytes())

    def test_rejects_tampered_functional_test_receipt(self):
        with tempfile.TemporaryDirectory(prefix="b04-c-strategy-a-tamper-") as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(publisher.SOURCE, source)
            ci = publisher.read_json(source / "strategy-a-ci.json")
            ci["run"]["conclusion"] = "failure"
            (source / "strategy-a-ci.json").write_bytes(publisher.json_bytes(ci))
            with self.assertRaisesRegex(ValueError, "SHA256SUMS mismatch"):
                publisher.validate_bundle(source)


if __name__ == "__main__":
    unittest.main()

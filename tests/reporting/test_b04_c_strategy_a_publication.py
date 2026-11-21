"""Publication-boundary tests for the corrected B04-C Strategy A report."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.reports import stage_b04_c_strategy_a as publisher


class B04CStrategyAPublicationTests(unittest.TestCase):
    def test_stage_builds_hash_bound_page_and_offline_bundle(self):
        with tempfile.TemporaryDirectory(prefix="b04-c-strategy-a-publication-") as temporary:
            root = Path(temporary)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><main><h1>Reports</h1></main></body></html>',
                encoding="utf-8",
            )

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
                self.assertEqual(
                    archive.read(f"{route}/record.json"), (report / "record.json").read_bytes()
                )

    def test_historical_zip_is_independent_of_platform_metadata_defaults(self):
        original_init = zipfile.ZipInfo.__init__

        def use_windows_default(info, *args, **kwargs):
            original_init(info, *args, **kwargs)
            info.create_system = 0

        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "index.html").write_text("<html><body>Reports</body></html>", encoding="utf-8")
            with patch.object(zipfile.ZipInfo, "__init__", use_windows_default):
                route = publisher.stage(publisher.SOURCE, site)
            with zipfile.ZipFile(site / f"{route}.zip") as archive:
                self.assertEqual({item.create_system for item in archive.infolist()}, {3})

    def test_rejects_changed_historical_zip_before_publishing(self):
        original_writestr = zipfile.ZipFile.writestr

        def write_with_changed_metadata(archive, *args, **kwargs):
            original_writestr(archive, *args, **kwargs)
            archive.comment = b"Different archive metadata"

        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            landing = site / "index.html"
            original_html = "<html><body>Reports</body></html>"
            landing.write_text(original_html, encoding="utf-8")
            with (
                patch.object(zipfile.ZipFile, "writestr", write_with_changed_metadata),
                self.assertRaisesRegex(ValueError, "historical.*ZIP checksum"),
            ):
                publisher.stage(publisher.SOURCE, site)
            self.assertEqual(list(site.iterdir()), [landing])
            self.assertEqual(landing.read_text(encoding="utf-8"), original_html)

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

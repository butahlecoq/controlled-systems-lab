"""APP-04 saved report: raw oracle, regeneration, ZIP and staging behavior."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
from app04 import collect, render_saved  # noqa: E402
import stage_app04  # noqa: E402


class SavedApp04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_path = ROOT / "reports/algorithm-results/app04-publications.json"
        cls.catalog = json.loads(cls.catalog_path.read_text(encoding="utf-8"))
        cls.report_id = cls.catalog["reports"][0]["report_id"]
        cls.bundle = cls.catalog_path.parent / cls.report_id

    def test_saved_bundle_and_catalog_regenerate_exactly(self) -> None:
        self.assertEqual(render_saved.render(self.bundle, check=True),
                         self.bundle.parent / (self.report_id + ".zip"))
        self.assertEqual(stage_app04.catalog_entry(self.bundle), self.catalog["reports"][0])
        record = render_saved.validate(self.bundle)
        self.assertEqual(sum(row["successes"] for row in record["measurement"]["summary"]),
                         2100)
        self.assertEqual(record["measurement"]["failures"], 0)

    def test_changed_radius_fails_literal_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "measure.csv"
            text = (self.bundle / "measure.csv").read_text(encoding="utf-8")
            self.assertIn("1.4142135623730951", text)
            raw.write_text(text.replace("1.4142135623730951", "0", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "radius"):
                collect.rows(raw, "measure")

    def test_changed_render_or_zip_fails_exact_byte_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied = root / self.report_id
            shutil.copytree(self.bundle, copied)
            archive = root / (self.report_id + ".zip")
            shutil.copyfile(self.bundle.parent / archive.name, archive)
            page = copied / "index.html"
            page.write_bytes(page.read_bytes() + b"changed\n")
            with self.assertRaisesRegex(ValueError, "rendered"):
                render_saved.render(copied, check=True)
            shutil.copyfile(self.bundle / "index.html", page)
            archive.write_bytes(archive.read_bytes() + b"changed\n")
            with self.assertRaisesRegex(ValueError, "ZIP"):
                render_saved.render(copied, check=True)

    def test_stage_copies_exact_public_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>',
                encoding="utf-8")
            self.assertEqual(stage_app04.stage(self.catalog_path, site), self.report_id)
            self.assertEqual((site / self.report_id / "index.html").read_bytes(),
                             (self.bundle / "index.html").read_bytes())
            self.assertEqual((site / (self.report_id + ".zip")).read_bytes(),
                             (self.bundle.parent / (self.report_id + ".zip")).read_bytes())
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(self.report_id + "/example-2d.html", index)


if __name__ == "__main__":
    unittest.main()

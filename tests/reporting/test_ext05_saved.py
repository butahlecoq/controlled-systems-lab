"""EXT-05 saved records regenerate and stage only their reviewed bytes."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
from ext05 import render_saved  # noqa: E402
import stage_ext05  # noqa: E402


class SavedContinuousReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ROOT / "reports/algorithm-results/ext05-publications.json"
        cls.entry = json.loads(cls.catalog.read_text(encoding="utf-8"))["reports"][0]
        cls.bundle = cls.catalog.parent / cls.entry["report_id"]

    def test_saved_numerical_report_regenerates(self) -> None:
        details = render_saved.render(self.bundle, check=True)
        self.assertEqual(details["source_commit"],
                         "6cc1740a59ca95e4a575e921cef793c2ac262e9f")
        self.assertEqual(details["index_sha256"],
                         "291c9e51e95d68bf83a91af850399825d66f7b888c05bfd351ac723a136c52ee")
        self.assertEqual(stage_ext05.catalog_entry(self.bundle), self.entry)
        record = render_saved.validate(self.bundle)
        self.assertEqual(record["analytic"]["trajectory"], [[0, 0], [1, 2], [3, 0]])
        self.assertEqual(record["measurement"]["measured_calls"], 700)
        self.assertEqual(record["measurement"]["failures"], 0)
        with zipfile.ZipFile(self.bundle / (self.bundle.name + ".zip")) as archive:
            self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED and
                                item.create_system == 3
                                for item in archive.infolist()))

    def test_changed_raw_observation_refuses_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / self.bundle.name
            shutil.copytree(self.bundle, copy)
            raw = copy / "measure.csv"
            raw.write_bytes(raw.read_bytes().replace(b"1,2,3,0,2,0,0", b"1,2,4,0,2,0,0", 1))
            with self.assertRaises(ValueError):
                render_saved.render(copy, check=True)

    def test_stage_creates_2d_route_and_offline_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text("<html><body><ul></ul></body></html>",
                                             encoding="utf-8")
            self.assertEqual(stage_ext05.stage(self.catalog, site), self.bundle.name)
            staged = site / self.bundle.name
            self.assertEqual((staged / "index.html").read_bytes(),
                             (self.bundle / "index.html").read_bytes())
            self.assertEqual((staged / (self.bundle.name + ".zip")).read_bytes(),
                             (self.bundle / (self.bundle.name + ".zip")).read_bytes())
            self.assertIn(self.bundle.name + "/example-2d.html",
                          (site / "index.html").read_text(encoding="utf-8"))

    def test_bad_site_index_leaves_no_partial_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text("<html><body></body></html>",
                                             encoding="utf-8")
            with self.assertRaises(ValueError):
                stage_ext05.stage(self.catalog, site)
            self.assertFalse((site / self.bundle.name).exists())


if __name__ == "__main__":
    unittest.main()

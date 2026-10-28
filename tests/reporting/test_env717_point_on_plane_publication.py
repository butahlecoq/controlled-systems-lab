from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_env717_point_on_plane", ROOT / "scripts/reports/stage_env717_point_on_plane.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class PointOnThePlanePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-point-on-plane"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        self.root = Path(self.temp.name)
        self.source = self.root / stage_module.SOURCE.name
        shutil.copytree(stage_module.SOURCE, self.source)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_stages_verified_position_and_velocity_geometry(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-point-on-plane-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        self.assertEqual(manifest["source_repository_commit"], stage_module.SOURCE_COMMIT)
        for name, sha in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        figure = json.loads((destination / "figure-data.json").read_text())
        self.assertEqual(figure["projection_pairs"], [[0, 1], [2, 3]])
        self.assertEqual(figure["target"]["shape"], "disk")
        self.assertGreater(len(figure["stages"][3]["states"]), 1)
        self.assertTrue(figure["trajectory"])
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        page = (destination / "index.html").read_text()
        self.assertIn("positions (x1,x2)", page)
        self.assertIn("velocities (x3,x4)", page)
        index = (self.site / "index.html").read_text()
        self.assertIn(f'href="{report_id}/index.html"', index)
        self.assertIn(f'href="{report_id}.zip"', index)

    def test_rejects_saved_figure_data_that_differs_from_source_replay(self):
        figure_path = self.source / "figure-data.json"
        figure = json.loads(figure_path.read_text())
        figure["projection_pairs"] = [[0, 1], [1, 2]]
        figure_path.write_text(json.dumps(figure, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "saved projection data differs"):
            stage_module._inputs(self.source)

    def test_rejects_report_file_symlinks_even_with_a_matching_checksum(self):
        outside = self.root / "outside-readme.md"
        outside.write_text("external content\n", encoding="utf-8")
        readme = self.source / "README.md"
        readme.unlink()
        try:
            os.symlink(outside, readme)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "regular non-symlink files"):
            stage_module._inputs(self.source)


if __name__ == "__main__":
    unittest.main()

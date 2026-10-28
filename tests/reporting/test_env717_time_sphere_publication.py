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
    "stage_env717_time_sphere", ROOT / "scripts/reports/stage_env717_time_sphere.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class TimeOptimalSpherePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-time-sphere"
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

    def test_stages_verified_nominal_reachability_geometry(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-time-sphere-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        for name, sha in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        figure = json.loads((destination / "figure-data.json").read_text())
        result = json.loads((destination / "result.json").read_text())
        capture = json.loads((destination / "capture.json").read_text())
        self.assertEqual(figure["projection_pairs"], [[0, 1]])
        self.assertEqual(figure["target"]["radius"], 1.0)
        self.assertTrue(capture["host_processor"].strip())
        self.assertTrue(result["initial_winning"])
        self.assertEqual(result["selected_horizon_steps"], 12)
        self.assertTrue(figure["trajectory"])
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/reachability.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        page = (destination / "index.html").read_text()
        self.assertIn("v=0", page)
        self.assertIn("unit-disk target", page)
        self.assertIn('href="capture.json"', page)
        self.assertIn(f'href="{report_id}/index.html"', (self.site / "index.html").read_text())

    def test_rejects_figure_data_that_differs_from_source_replay(self):
        figure_path = self.source / "figure-data.json"
        figure = json.loads(figure_path.read_text())
        figure["projection_pairs"] = [[1, 2]]
        figure_path.write_text(json.dumps(figure, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "saved projection data differs"):
            stage_module._inputs(self.source)

    def test_rejects_symlinked_bundle_leaves_with_matching_checksum(self):
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

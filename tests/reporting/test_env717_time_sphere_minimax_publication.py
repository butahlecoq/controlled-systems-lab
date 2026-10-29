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
    "stage_env717_time_sphere_minimax",
    ROOT / "scripts/reports/stage_env717_time_sphere_minimax.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class TimeOptimalSphereMinimaxPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-time-sphere-minimax/publication-tests"
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

    def test_stages_verified_adversarial_reachability_and_minimax_result(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-time-sphere-minimax-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        for name, sha in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        figure = json.loads((destination / "figure-data.json").read_text())
        result = json.loads((destination / "result.json").read_text())
        capture = json.loads((destination / "capture.json").read_text())
        self.assertEqual(figure["projection"]["x"], "position x1")
        self.assertEqual(figure["projection"]["y"], "velocity x2")
        self.assertEqual(figure["target"]["radius"], 1.0)
        self.assertEqual(result["first_guaranteed_capture_horizon_steps"], 35)
        self.assertAlmostEqual(result["minimax_capture_time_seconds"], 3.43)
        self.assertEqual(len(figure["layers"]), 36)
        self.assertEqual(capture["solver_failures"], 0)
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/reachability.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        page = (destination / "index.html").read_text()
        self.assertIn("sequential-response game", page)
        self.assertIn("not the source RL game", page)
        self.assertIn("v observes u's action", page)
        self.assertIn("trains u to minimize elapsed time while v maximizes it", page)
        self.assertIn(f'href="{report_id}/index.html"', (self.site / "index.html").read_text())

    def test_rejects_changed_bundle_bytes_before_replay(self):
        path = self.source / "figure-data.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            stage_module._inputs(self.source)

    def test_rejects_symlinked_bundle_leaf(self):
        outside = self.root / "outside-readme.md"
        outside.write_text("external content\n", encoding="utf-8")
        readme = self.source / "README.md"
        readme.unlink()
        try:
            os.symlink(outside, readme)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "regular non-symlink files"):
            stage_module._inputs(self.source)


if __name__ == "__main__":
    unittest.main()

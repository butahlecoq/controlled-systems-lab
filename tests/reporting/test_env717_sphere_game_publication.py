from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_env717_sphere_game", ROOT / "scripts/reports/stage_env717_sphere_game.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class SphereGamePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-sphere-game"
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

    def test_stages_verified_sphere_phase_plane_report(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-sphere-game-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        self.assertEqual(manifest["source_repository_commit"], stage_module.SOURCE_COMMIT)
        self.assertEqual(manifest["scenario_sha256"],
                         hashlib.sha256((destination / "scenario.json").read_bytes()).hexdigest())
        self.assertEqual(manifest["numerics"]["independent_replay_absolute_tolerance"], 1e-12)
        for name, digest in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/scenario.json", archive.namelist())
        figure = (destination / "projections.svg").read_text()
        self.assertIn("causal feedback-winning nodes at open-loop threshold", figure)
        self.assertIn("fixed-plan worst-case path", figure)
        page = (destination / "index.html").read_text()
        self.assertIn("source reward", page)
        self.assertIn("zero warmups, n=1", page)
        self.assertIn("Scenario input SHA-256", page)
        self.assertIn("Scenario input", page)
        index = (self.site / "index.html").read_text()
        for name in ("index.html", "result.json", "projections.svg"):
            self.assertIn(f'href="{report_id}/{name}"', index)
            self.assertTrue((self.site / report_id / name).is_file())
        self.assertIn(f'href="{report_id}.zip"', index)
        self.assertTrue((self.site / f"{report_id}.zip").is_file())

    def test_rejects_result_that_disagrees_with_independent_replay(self):
        result_path = self.source / "result.json"
        result = json.loads(result_path.read_text())
        result["source_reward_value"] += 1.0
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "independent environment replay failed"):
            stage_module._inputs(self.source)


if __name__ == "__main__":
    unittest.main()

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
    "stage_env717_two_particle_minimax",
    ROOT / "scripts/reports/stage_env717_two_particle_minimax.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class TwoParticleMinimaxPublicationTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "build/env717-two-particle-minimax/publication-tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.root = Path(self.temp.name)
        self.source = self.root / stage_module.SOURCE.name
        shutil.copytree(stage_module.SOURCE, self.source)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_stages_checked_game_and_both_physical_projections(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-two-particle-minimax-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        for name, sha in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        checksum_lines = (destination / "SHA256SUMS").read_text().splitlines()
        checksums = {name: sha for sha, name in
                     (line.split("  ", 1) for line in checksum_lines)}
        self.assertNotIn("SHA256SUMS", checksums)
        self.assertNotIn("publication-manifest.json", checksums)
        for name, sha in checksums.items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        figure = json.loads((destination / "figure-data.json").read_text())
        result = json.loads((destination / "result.json").read_text())
        self.assertEqual([projection["name"] for projection in figure["projections"]],
                         ["particle-1-phase-plane", "particle-2-phase-plane"])
        self.assertEqual([projection["x_label"] for projection in figure["projections"]],
                         ["x₁ position", "x₃ position"])
        self.assertEqual([projection["y_label"] for projection in figure["projections"]],
                         ["x₂ velocity", "x₄ velocity"])
        self.assertTrue(all(projection["target_projection"] for projection in figure["projections"]))
        self.assertEqual([projection["layers"][-1]["stage"] for projection in figure["projections"]],
                         [4, 4])
        self.assertEqual(result["graph_state_counts"], [1, 9, 81, 621, 3969])
        self.assertEqual(result["first_robust_capture_steps"], 4)
        self.assertAlmostEqual(result["finite_causal_minimax_terminal_gap"], 0.859899)
        self.assertEqual(len(result["minimax_trajectory"]), 5)
        self.assertIn("stronger within-stage information pattern", (destination / "index.html").read_text())
        page = (destination / "index.html").read_text()
        self.assertIn("particle 1's (x₁,x₂) phase plane", page)
        self.assertIn("particle 2's (x₃,x₄) phase plane", page)
        self.assertIn("First robust capture of |x₁−x₃| ≤ 1", page)
        self.assertIn("projected graph nodes are points, not convex hulls", page)
        svg = (destination / "projections.svg").read_text()
        self.assertGreater(svg.rfind('data-role="terminal-target"'),
                           svg.rfind('data-role="winning-intersection"'))
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        self.assertIn(f'href="{report_id}/index.html"',
                      (self.site / "index.html").read_text())

    def test_rejects_mutated_result_before_staging(self):
        result = self.source / "result.json"
        result.write_bytes(result.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            stage_module.validate_bundle(self.source)

    def test_rejects_symlinked_bundle_leaf(self):
        readme = self.source / "README.md"
        readme.unlink()
        outside = self.root / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        try:
            readme.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "regular non-symlink files"):
            stage_module.validate_bundle(self.source)


if __name__ == "__main__":
    unittest.main()

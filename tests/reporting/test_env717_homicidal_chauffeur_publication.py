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
    "stage_env717_homicidal_chauffeur",
    ROOT / "scripts/reports/stage_env717_homicidal_chauffeur.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class HomicidalChauffeurPublicationTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "build/env717-homicidal-chauffeur/publication-tests"
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

    def test_stages_verified_game_and_both_player_position_views(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-homicidal-chauffeur-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        for name, sha in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        checksums = {name: sha for sha, name in
                     (line.split("  ", 1) for line in (destination / "SHA256SUMS").read_text().splitlines())}
        self.assertEqual(set(checksums), set(stage_module.FILES))
        for name, sha in checksums.items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
        result = json.loads((destination / "result.json").read_text())
        figure = json.loads((destination / "figure-data.json").read_text())
        self.assertEqual([projection["name"] for projection in figure["projections"]],
                         ["pursuer-position-plane", "evader-position-plane"])
        self.assertEqual(result["graph_state_counts"][0], 1)
        self.assertEqual(len(result["minimax_trajectory"]), 5)
        self.assertEqual(result["first_robust_capture_steps"], 4)
        self.assertAlmostEqual(result["finite_causal_minimax_terminal_separation"],
                               7.778040783932288)
        self.assertTrue(all(layer["forward_convex_envelope"] for projection in figure["projections"]
                            for layer in projection["layers"]))
        page = (destination / "index.html").read_text()
        self.assertIn("not exact projections of the five-dimensional reachable sets", page)
        self.assertIn("do not reproduce continuous-action RL training", page)
        svg = (destination / "projections.svg").read_text()
        self.assertIn('data-role="projected-convex-envelope"', svg)
        self.assertIn('data-role="winning-intersection"', svg)
        self.assertIn('data-role="terminal-target"', svg)
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        self.assertIn(f'href="{report_id}/index.html"',
                      (self.site / "index.html").read_text())

    def test_rejects_modified_result(self):
        result = self.source / "result.json"
        result.write_bytes(result.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "report checksum mismatch"):
            stage_module.validate_bundle(self.source)

    def test_rejects_symlinked_bundle_entry(self):
        readme = self.source / "README.md"
        readme.unlink()
        outside = self.root / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        try:
            readme.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "regular files"):
            stage_module.validate_bundle(self.source)


if __name__ == "__main__":
    unittest.main()

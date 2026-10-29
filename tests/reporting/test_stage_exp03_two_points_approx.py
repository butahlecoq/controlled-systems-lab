import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_exp03_two_points_approx as stager


class StageExp03TwoPointsTests(unittest.TestCase):
    def test_stages_verified_frozen_bundle_without_rewriting_source(self):
        source = stager.SOURCE
        source_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in source.iterdir() if path.is_file()}
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "index.html").write_text(
                "<!doctype html><html><body><h1>Reports</h1><ul></ul></body></html>",
                encoding="utf-8")
            route = stager.stage(source, site)
            destination = site / route
            self.assertEqual(route, "exp03-two-points-approx-publication-v1")
            published_page = (destination / "index.html").read_text()
            self.assertIn("On narrow screens, swipe or scroll the figure horizontally", published_page)
            self.assertIn("independent coordinate ranges and position/velocity units", published_page)
            self.assertIn("@page{size:landscape", published_page)
            self.assertNotEqual((destination / "index.html").read_bytes(),
                                (source / "index.html").read_bytes())
            self.assertEqual((destination / "reachability-and-approximations.svg").read_bytes(),
                             (source / "reachability-and-approximations.svg").read_bytes())
            self.assertEqual((destination / "run.json").read_bytes(), (source / "run.json").read_bytes())
            publication_sums = {name: sha for sha, name in
                                 (line.split("  ", 1) for line in
                                  (destination / "SHA256SUMS").read_text().splitlines())}
            self.assertEqual(publication_sums["index.html"],
                             hashlib.sha256((destination / "index.html").read_bytes()).hexdigest())
            manifest = json.loads((destination / "publication-manifest.json").read_text())
            self.assertEqual(manifest["schema"], "csl.exp03-two-points-approx-publication/1")
            self.assertEqual(manifest["published_files"]["run.json"],
                             hashlib.sha256((source / "run.json").read_bytes()).hexdigest())
            landing = (site / "index.html").read_text()
            self.assertIn(route + "/index.html", landing)
            self.assertIn(route + "/reachability-and-approximations.svg", landing)
        self.assertEqual(source_hashes,
                         {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source.iterdir() if path.is_file()})

    def test_rejects_corrupted_frozen_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / stager.SOURCE.name
            copied.mkdir()
            for path in stager.SOURCE.iterdir():
                if path.is_file():
                    (copied / path.name).write_bytes(path.read_bytes())
            (copied / "run.json").write_bytes((copied / "run.json").read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                stager.read_bundle(copied)


if __name__ == "__main__":
    unittest.main()

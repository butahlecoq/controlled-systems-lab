from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_env717_max_coordinate", ROOT / "scripts/reports/stage_env717_max_coordinate.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class MaxCoordinateGamePublicationTests(unittest.TestCase):
    def test_stages_verified_phase_plane_report_and_offline_archive(self):
        temp_root = ROOT / "build/env717-max-coordinate"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            root = Path(temp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8")
            report_id = stage_module.stage(stage_module.SOURCE, site)
            self.assertRegex(report_id, r"^env717-max-coordinate-[0-9a-f]{20}$")
            destination = site / report_id
            manifest = json.loads((destination / "publication-manifest.json").read_text())
            self.assertEqual(manifest["report_id"], report_id)
            for name, digest in manifest["published_files"].items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
            with zipfile.ZipFile(site / f"{report_id}.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            figure = (destination / "projections.svg").read_text()
            self.assertIn("causal feedback-winning nodes at open-loop threshold", figure)
            self.assertIn("fixed-plan worst-case path", figure)
            self.assertIn(f"{report_id}/index.html", (site / "index.html").read_text())

    def test_rejects_rehashed_result_that_fails_independent_game_replay(self):
        temp_root = ROOT / "build/env717-max-coordinate"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            source = Path(temp) / "tampered"
            import shutil
            shutil.copytree(stage_module.SOURCE, source)
            result_path = source / "result.json"
            result = json.loads(result_path.read_text())
            result["objective_value"] += 1
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
            (source / "SHA256SUMS").write_text("".join(
                f"{hashlib.sha256((source / name).read_bytes()).hexdigest()}  {name}\n"
                for name in names), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "independent environment replay failed"):
                stage_module._inputs(source)


if __name__ == "__main__":
    unittest.main()

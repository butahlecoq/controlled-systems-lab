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
    "stage_env717_unequal_game", ROOT / "scripts/reports/stage_env717_unequal_game.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class UnequalGamePublicationTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "build/env717-unequal-game-make/tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            dir=temp_root)
        self.root = Path(self.temp.name)
        self.source = self.root / stage_module.SOURCE.name
        shutil.copytree(stage_module.SOURCE, self.source)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_stages_verified_content_addressed_report_and_offline_archive(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-unequal-game-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        self.assertEqual(manifest["source_repository_commit"], stage_module.SOURCE_COMMIT)
        self.assertEqual(manifest["source_commit"],
                         json.loads((self.source / "result.json").read_text())["source_commit"])
        for name, digest in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertEqual(archive.testzip(), None)
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertNotIn(f"{report_id}/projections.png", archive.namelist())
            self.assertIn(f"{report_id}/publication-manifest.json", archive.namelist())
        self.assertIn(f"{report_id}/index.html", (self.site / "index.html").read_text())
        published_svg = (destination / "projections.svg").read_text()
        self.assertIn("terminal target", published_svg)
        self.assertIn("Position x", published_svg)
        self.assertIn("Time (s)", published_svg)
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage_module.stage(self.source, self.site)

    def test_rejects_tampered_result_even_if_report_checksum_is_updated(self):
        result_path = self.source / "result.json"
        result = json.loads(result_path.read_text())
        result["objective_value"] += 1.0
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "independent environment replay failed"):
            stage_module.stage(self.source, self.site)

    def test_rejects_rehashed_figure_and_page_that_disagree_with_verified_result(self):
        for name, expected_error in (("figure-data.json", "saved figure data differs"),
                                     ("projections.svg", "saved SVG differs"),
                                     ("index.html", "saved report page differs")):
            with self.subTest(name=name):
                source = self.root / ("mutated-" + name)
                shutil.copytree(self.source, source)
                target = source / name
                original = target.read_bytes()
                if name == "figure-data.json":
                    data = json.loads(original)
                    data["trajectory"][0] += 1
                    target.write_text(json.dumps(data, indent=2) + "\n")
                else:
                    target.write_bytes(original.replace(b"UnequalGame", b"Fake points", 1))
                checksum_names = [item for item in stage_module.FILES
                                  if item != "SHA256SUMS"]
                (source / "SHA256SUMS").write_text("".join(
                    f"{hashlib.sha256((source / item).read_bytes()).hexdigest()}  {item}\n"
                    for item in checksum_names), encoding="ascii")
                with self.assertRaisesRegex(ValueError, expected_error):
                    stage_module.stage(source, self.site)


if __name__ == "__main__":
    unittest.main()

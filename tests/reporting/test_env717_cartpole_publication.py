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
    "stage_env717_cartpole", ROOT / "scripts/reports/stage_env717_cartpole.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class CartPolePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-cartpole/publication-tests"
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

    def test_stages_source_qualified_finite_control_report(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertRegex(report_id, r"^env717-cartpole-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        self.assertEqual(manifest["source_repository_commit"], stage_module.SOURCE_COMMIT)
        for name, digest in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
        figure = json.loads((destination / "figure-data.json").read_text())
        self.assertEqual(figure["projection_panels"], [[0, 1], [2, 3]])
        self.assertEqual(len(figure["layers"]), 14)
        self.assertEqual(len(figure["selected_plan_states"]), 15)
        result = json.loads((destination / "result.json").read_text())
        self.assertEqual(result["performance"]["measured_repetitions"], 9)
        self.assertEqual(len(result["performance"]["raw_elapsed_ns"]), 9)
        self.assertEqual(result["objective_value"], 14)
        self.assertEqual(len(result["maximizing_plan_indices"]), 13136)
        report_generation = json.loads((destination / "report-generation.json").read_text())
        self.assertEqual(report_generation["measured_runs"], 5)
        self.assertEqual(len(report_generation["raw_elapsed_ns"]), 5)
        profile = json.loads((destination / "profile.json").read_text())
        self.assertEqual(len(profile["runs"]), 2)
        self.assertTrue(profile["diagnostic_only"])
        page = (destination / "index.html").read_text()
        self.assertIn("not a learned policy", page)
        self.assertIn("not the original 500-step task", page)
        self.assertIn("Cart position–velocity plane", page)
        self.assertIn("Pole angle–angular velocity plane", page)
        self.assertIn("Full report collection median", page)
        self.assertIn("GNU gprof", page)
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/profile.json", archive.namelist())
        self.assertIn(f'href="{report_id}/index.html"', (self.site / "index.html").read_text())

    def test_rejects_modified_plan_even_after_checksum_rewrite(self):
        result_path = self.source / "result.json"
        result = json.loads(result_path.read_text())
        result["plans"][-1]["reward"] += 1
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "source-bound report validation failed"):
            stage_module.inputs(self.source)

    def test_rejects_forged_profile_even_after_checksum_rewrite(self):
        path = self.source / "profile.json"
        profile = json.loads(path.read_text())
        profile["runs"][0]["advance_state_self_percent"] = 1000.0
        path.write_text(json.dumps(profile, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "source-bound report validation failed"):
            stage_module.inputs(self.source)


if __name__ == "__main__":
    unittest.main()

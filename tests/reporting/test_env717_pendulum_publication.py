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
    "stage_env717_pendulum", ROOT / "scripts/reports/stage_env717_pendulum.py")
publication = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publication)


class PendulumPublicationTests(unittest.TestCase):
    def test_stages_replayed_finite_action_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / publication.SOURCE.name
            shutil.copytree(publication.SOURCE, source)
            site = base / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><html><ul></ul></html>", encoding="utf-8")

            route_id = publication.stage(source, site)

            self.assertRegex(route_id, r"^env717-pendulum-[0-9a-f]{20}$")
            report = site / route_id
            manifest = json.loads((report / "publication-manifest.json").read_text())
            self.assertEqual(manifest["report_id"], route_id)
            self.assertEqual(manifest["source_repository_commit"], publication.SOURCE_COMMIT)
            for name, expected in manifest["published_files"].items():
                self.assertEqual(hashlib.sha256((report / name).read_bytes()).hexdigest(), expected)
            result = json.loads((report / "result.json").read_text())
            self.assertEqual(result["search"]["complete_plan_count"], 5**10)
            self.assertEqual(len(result["finite_catalogue_optimum"]["trajectory"]), 11)
            self.assertEqual(result["runtime_measurement"]["measured_repetitions"], 7)
            self.assertIn("only over this catalogue and horizon", (report / "index.html").read_text())
            with zipfile.ZipFile(site / f"{route_id}.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(f"{route_id}/phase-plane.svg", archive.namelist())
                self.assertIn(f"{route_id}/publication-manifest.json", archive.namelist())
            self.assertIn(f"{route_id}/index.html", (site / "index.html").read_text())

    def test_rejects_bundle_with_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / publication.SOURCE.name
            shutil.copytree(publication.SOURCE, source)
            (source / "result.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication.verified_bundle(source)


if __name__ == "__main__":
    unittest.main()

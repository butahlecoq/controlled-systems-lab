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
    "stage_env717_earth_orbit", ROOT / "scripts/reports/stage_env717_earth_orbit.py")
publication = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publication)


class EarthOrbitalMotionPublicationTests(unittest.TestCase):
    def test_stages_independently_replayed_finite_catalog_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / publication.SOURCE.name
            shutil.copytree(publication.SOURCE, source)
            site = base / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html><ul></ul></html>", encoding="utf-8")

            route_id = publication.stage(source, site)

            self.assertRegex(route_id, r"^env717-earth-orbit-[0-9a-f]{20}$")
            report = site / route_id
            manifest = json.loads((report / "publication-manifest.json").read_text())
            self.assertEqual(manifest["report_id"], route_id)
            self.assertEqual(manifest["source_repository_commit"], publication.UPSTREAM_SOURCE_COMMIT)
            for name, expected in manifest["published_files"].items():
                self.assertEqual(hashlib.sha256((report / name).read_bytes()).hexdigest(), expected)
            result = json.loads((report / "result.json").read_text())
            self.assertEqual(result["search"]["evaluated_plan_count"], 729)
            self.assertTrue(result["search"]["all_plan_scores_independently_replayed"])
            self.assertIn("not an optimum over continuous controls", (report / "index.html").read_text())
            self.assertIn("Target orbit", (report / "orbit-phase-plane.svg").read_text())
            with zipfile.ZipFile(site / f"{route_id}.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(f"{route_id}/orbit-phase-plane.svg", archive.namelist())
                self.assertIn(f"{route_id}/publication-manifest.json", archive.namelist())
            self.assertIn(f"{route_id}/index.html", (site / "index.html").read_text())

    def test_rejects_modified_report_bundle_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(publication.SOURCE, source)
            with (source / "result.json").open("a", encoding="utf-8") as stream:
                stream.write("modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication.verified_bundle(source)


if __name__ == "__main__":
    unittest.main()

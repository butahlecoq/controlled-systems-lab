from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reports import stage_env717_earth_orbit as publication  # noqa: E402 - direct test entry point


class EarthOrbitalMotionPublicationTests(unittest.TestCase):
    def test_stages_independently_replayed_finite_catalog_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / publication.SOURCE.name
            shutil.copytree(publication.SOURCE, source)
            site = base / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html><ul></ul></html>", encoding="utf-8"
            )

            route_id = publication.stage(source, site)
            self.assertEqual(route_id, "env717-earth-orbit-d89c89a7460a98d8297b")
            self.assertEqual(
                hashlib.sha256((site / f"{route_id}.zip").read_bytes()).hexdigest(),
                "54222e7c40271d5e32c2531bc0113ee086db4124d4c95592420c312127a1336c",
            )

            self.assertRegex(route_id, r"^env717-earth-orbit-[0-9a-f]{20}$")
            report = site / route_id
            manifest = json.loads((report / "publication-manifest.json").read_text())
            self.assertEqual(manifest["report_id"], route_id)
            self.assertEqual(
                manifest["source_repository_commit"], publication.UPSTREAM_SOURCE_COMMIT
            )
            for name, expected in manifest["published_files"].items():
                self.assertEqual(hashlib.sha256((report / name).read_bytes()).hexdigest(), expected)
            result = json.loads((report / "result.json").read_text())
            self.assertEqual(result["search"]["evaluated_plan_count"], 729)
            self.assertTrue(result["search"]["all_plan_scores_independently_replayed"])
            self.assertIn(
                "not an optimum over continuous controls", (report / "index.html").read_text()
            )
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

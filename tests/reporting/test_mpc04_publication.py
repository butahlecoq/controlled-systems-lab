import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import landing
import stage_mpc04_max_coordinate as publication


class Mpc04PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mpc04-publication-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            '<!doctype html><html><body><h1>Reports</h1><ul></ul></body></html>',
            encoding="utf-8")

    def test_stages_replay_verified_immutable_route_and_archive(self):
        route = publication.stage(publication.SOURCE, self.site)
        self.assertEqual(landing.family_for(route), "mpc04-max-coordinate-replanning")
        report_dir = self.site / route
        manifest = json.loads((report_dir / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], route)
        self.assertEqual(manifest["verification"]["status"], "passed")
        self.assertEqual(len(manifest["source_bundle_sha256"]), 10)
        for name, expected in manifest["published_files"].items():
            self.assertEqual(publication.digest((report_dir / name).read_bytes()), expected, name)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'{route}/index.html', page)
        self.assertIn(f'{route}/trajectory.svg', page)
        with zipfile.ZipFile(self.site / f"{route}.zip") as archive:
            self.assertIn(f"{route}/publication-manifest.json", archive.namelist())
            self.assertEqual(archive.read(f"{route}/index.html"), (report_dir / "index.html").read_bytes())

    def test_source_tampering_fails_before_any_route_is_written(self):
        source = self.root / "tampered-source"
        shutil.copytree(publication.SOURCE, source)
        result_path = source / "result.json"
        result_path.write_bytes(result_path.read_bytes() + b" ")
        original_page = (self.site / "index.html").read_bytes()
        with self.assertRaisesRegex(ValueError, "outer checksum mismatch: result.json"):
            publication.stage(source, self.site)
        self.assertEqual(list(self.site.iterdir()), [self.site / "index.html"])
        self.assertEqual((self.site / "index.html").read_bytes(), original_page)

    def test_captured_source_fingerprint_mismatch_is_rejected(self):
        capture = json.loads((publication.SOURCE / "capture.json").read_text())
        fingerprints = dict(capture["source"]["source_sha256"])
        fingerprints["native_driver"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source fingerprint differs: native_driver"):
            publication.verify_source_fingerprints(
                capture["source"]["report_code_commit"], fingerprints)

    def test_immutable_route_collision_is_rejected(self):
        route = publication.stage(publication.SOURCE, self.site)
        with self.assertRaisesRegex(ValueError, "immutable route already exists"):
            publication.stage(publication.SOURCE, self.site)
        self.assertTrue((self.site / route / "publication-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()

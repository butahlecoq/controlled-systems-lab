from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_env717", ROOT / "scripts/reports/stage_env717.py")
stage_env717 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_env717)
LANDING_SPEC = importlib.util.spec_from_file_location(
    "report_landing", ROOT / "scripts/reports/landing.py")
landing = importlib.util.module_from_spec(LANDING_SPEC)
assert LANDING_SPEC.loader is not None
LANDING_SPEC.loader.exec_module(landing)


class EnvironmentPublicationTests(unittest.TestCase):
    def test_stages_content_addressed_report_and_offline_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "env717-simple-control-pilot-v1"
            shutil.copytree(stage_env717.SOURCE, source)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><ul></ul></html>', encoding="utf-8")

            report_id = stage_env717.stage(source, site)
            route = site / report_id
            self.assertTrue(report_id.startswith("env717-simple-control-"))
            self.assertTrue((route / "index.html").is_file())
            self.assertTrue((route / "projection.png").is_file())
            self.assertTrue((route / "projection.svg").is_file())
            self.assertEqual(json.loads((route / "publication-manifest.json").read_text())[
                "source_report_id"], source.name)
            manifest = json.loads((route / "publication-manifest.json").read_text())
            self.assertEqual(manifest["stager_sha256"], hashlib.sha256(
                Path(stage_env717.__file__).read_bytes()).hexdigest())
            self.assertEqual(set(manifest["published_files"]),
                             {path.name for path in route.iterdir()} - {"publication-manifest.json"})
            for name, digest in manifest["published_files"].items():
                self.assertEqual(digest, hashlib.sha256((route / name).read_bytes()).hexdigest())
            checksums = {}
            for line in (route / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                checksums[name] = digest
            self.assertNotIn("publication-manifest.json", checksums)
            for name, digest in checksums.items():
                self.assertEqual(digest, hashlib.sha256((route / name).read_bytes()).hexdigest())
            with zipfile.ZipFile(site / (report_id + ".zip")) as archive:
                self.assertIn(f"{report_id}/index.html", archive.namelist())
                self.assertIn(f"{report_id}/projection.png", archive.namelist())
            self.assertIn(f'href="{report_id}/index.html"',
                          (site / "index.html").read_text(encoding="utf-8"))
            landing.build(site)
            rendered = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("SimpleControlProblem finite-action pilot", rendered)
            self.assertIn(f'href="{report_id}/projection.svg"', rendered)
            self.assertIn(manifest["source_commit"], rendered)

    def test_rejects_tampered_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "env717-simple-control-pilot-v1"
            shutil.copytree(stage_env717.SOURCE, source)
            with (source / "result.json").open("a", encoding="utf-8") as stream:
                stream.write(" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                stage_env717._inputs(source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
SPEC = importlib.util.spec_from_file_location(
    "stage_env717", ROOT / "scripts/reports/stage_env717.py"
)
if SPEC is None or SPEC.loader is None:
    raise ImportError("cannot load the environment publication test dependency")
stage_env717 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage_env717)
landing = importlib.import_module("landing")


class EnvironmentPublicationTests(unittest.TestCase):
    def test_stages_content_addressed_report_and_offline_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "env717-simple-control-pilot-v1"
            shutil.copytree(stage_env717.SOURCE, source)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><ul></ul></html>', encoding="utf-8"
            )

            report_id = stage_env717.stage(source, site)
            self.assertEqual(report_id, "env717-simple-control-65a4341b28e95682f6de")
            self.assertEqual(
                hashlib.sha256((site / f"{report_id}.zip").read_bytes()).hexdigest(),
                "b36170e17ebb6a59c6428e04abd98a17d8bb748afd8181a21f47845cfd0773f2",
            )
            route = site / report_id
            self.assertTrue(report_id.startswith("env717-simple-control-"))
            self.assertTrue((route / "index.html").is_file())
            self.assertTrue((route / "projection.png").is_file())
            self.assertTrue((route / "projection.svg").is_file())
            self.assertEqual(
                json.loads((route / "publication-manifest.json").read_text())["source_report_id"],
                source.name,
            )
            manifest = json.loads((route / "publication-manifest.json").read_text())
            self.assertEqual(
                manifest["stager_sha256"],
                "01930def86ef2031523323fb77e29fc51f5553c7ff11a75cf907da812e3251ad",
            )
            self.assertEqual(
                set(manifest["published_files"]),
                {path.name for path in route.iterdir()} - {"publication-manifest.json"},
            )
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
            self.assertIn(
                f'href="{report_id}/index.html"', (site / "index.html").read_text(encoding="utf-8")
            )
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

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
    "stage_mpc06_tube", ROOT / "scripts/reports/stage_mpc06_tube.py")
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class Mpc06TubePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mpc06-publication-")
        self.root = Path(self.temp.name)
        self.source = self.root / stage_module.SOURCE.name
        shutil.copytree(stage_module.SOURCE, self.source)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<!doctype html><html><body><main>archive</main></body></html>", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_stages_replayed_immutable_tube_report(self):
        route = stage_module.stage(self.source, self.site)
        self.assertRegex(route, r"^mpc06-tube-[0-9a-f]{20}$")
        destination = self.site / route
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], route)
        for name, expected in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), expected)
        sums = {}
        for line in (destination / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split("  ", 1)
            sums[name] = expected
        self.assertEqual(sums, {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                                for name in stage_module.FILES if name != "SHA256SUMS"})
        page = (self.site / "index.html").read_text()
        self.assertIn(f'href="{route}/index.html"', page)
        self.assertIn(f'href="{route}.zip"', page)
        self.assertIn("no objective, minimax cost", page)
        report = (destination / "index.html").read_text()
        self.assertIn("Exact feasibility evidence", report)
        self.assertIn("One descriptive timing observation", report)
        self.assertIn("range unavailable for a single run", report)
        self.assertIn("cmake --build build/mpc06", report)
        with zipfile.ZipFile(self.site / f"{route}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{route}/projection.svg", archive.namelist())
            self.assertIn(f"{route}/scenario.json", archive.namelist())

    def test_rejects_changed_saved_figure(self):
        path = self.source / "projection.svg"
        path.write_text(path.read_text() + "<!-- changed -->", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            stage_module.inputs(self.source)


if __name__ == "__main__":
    unittest.main()

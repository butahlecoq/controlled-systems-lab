from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reports import stage_env717_dubins_car as stage_module  # noqa: E402 - direct test entry point

ROOT = Path(__file__).resolve().parents[2]


class DubinsCarPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = ROOT / "build/env717-dubins-car"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        self.root = Path(self.temp.name)
        self.source = self.root / stage_module.SOURCE.name
        shutil.copytree(stage_module.SOURCE, self.source)
        self.site = self.root / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_stagers_load_outside_the_repository(self):
        check_imports = """\
import importlib
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
names = ["stage_env717" + suffix for suffix in sys.argv[2:]]
for name in names:
    spec = importlib.util.spec_from_file_location(f"file_{name}", root / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.stage)
sys.path.insert(0, str(root))
for name in names:
    assert callable(importlib.import_module(name).stage)
"""
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                check_imports,
                str(ROOT / "scripts/reports"),
                "",
                "_dubins_car",
                "_earth_orbit",
                "_max_coordinate",
                "_pendulum_terminal",
                "_point_on_plane",
                "_two_points",
                "_unequal_game",
                "_vanderpol",
                "_pendulum",
                "_sphere_game",
                "_time_sphere",
                "_time_sphere_minimax",
                "_two_particle_minimax",
                "_unlimited_bolza",
            ],
            cwd=self.site,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_archive_drift_leaves_the_site_unchanged(self):
        landing = self.site / "index.html"
        original = landing.read_bytes()
        with (
            patch.object(stage_module, "escape", side_effect=lambda value: "changed-" + value),
            self.assertRaisesRegex(
                ValueError, "historical environment report archive hash differs"
            ),
        ):
            stage_module.stage(self.source, self.site)
        self.assertEqual(list(self.site.iterdir()), [landing])
        self.assertEqual(landing.read_bytes(), original)

    def test_different_valid_source_uses_current_publisher_hashes(self):
        ledger = self.source / "SHA256SUMS"
        checksums = ledger.read_text(encoding="ascii").splitlines()
        ledger.write_text("\n".join(reversed(checksums)) + "\n", encoding="ascii")
        route = stage_module.stage(self.source, self.site)
        self.assertNotEqual(route, "env717-dubins-car-eb4d25d6244afc5de2f2")
        manifest = json.loads((self.site / route / "publication-manifest.json").read_text())
        stager = ROOT / "scripts/reports/stage_env717_dubins_car.py"
        shared = ROOT / "scripts/reports/environment_report_publication.py"
        self.assertEqual(manifest["stager_sha256"], hashlib.sha256(stager.read_bytes()).hexdigest())
        self.assertEqual(
            manifest["publication_helper_sha256"], hashlib.sha256(shared.read_bytes()).hexdigest()
        )

    def test_stages_verified_finite_control_trajectory(self):
        report_id = stage_module.stage(self.source, self.site)
        self.assertEqual(report_id, "env717-dubins-car-eb4d25d6244afc5de2f2")
        self.assertEqual(
            hashlib.sha256((self.site / f"{report_id}.zip").read_bytes()).hexdigest(),
            "d5a809ed13623630749c26ce357161d9c5449572e254c58592dfd6341fde6914",
        )
        self.assertRegex(report_id, r"^env717-dubins-car-[0-9a-f]{20}$")
        destination = self.site / report_id
        manifest = json.loads((destination / "publication-manifest.json").read_text())
        self.assertEqual(manifest["report_id"], report_id)
        self.assertEqual(manifest["source_repository_commit"], stage_module.SOURCE_COMMIT)
        for name, digest in manifest["published_files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
        figure = json.loads((destination / "figure-data.json").read_text())
        self.assertEqual([len(cloud) for cloud in figure["stage_clouds"]], [5, 25, 125])
        self.assertEqual(len(figure["trajectory"]), 64)
        self.assertTrue((destination / "projections.svg").read_text().startswith("<svg"))
        self.assertIn("not a continuous-action optimum", (destination / "index.html").read_text())
        with zipfile.ZipFile(self.site / f"{report_id}.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(f"{report_id}/projections.svg", archive.namelist())
            self.assertIn(f"{report_id}/figure-data.json", archive.namelist())
        landing = (self.site / "index.html").read_text()
        self.assertIn(f'href="{report_id}/index.html"', landing)
        self.assertIn(f'href="{report_id}.zip"', landing)

    def test_rejects_a_changed_plan_even_when_checksums_are_rewritten(self):
        result_path = self.source / "result.json"
        result = json.loads(result_path.read_text())
        result["plans"][-1]["terminal_loss"] += 1.0
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
                for name in names
            ),
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "independent finite-plan replay rejected result"):
            stage_module._inputs(self.source)

    def test_rejects_a_truncated_terminal_state_even_when_checksums_are_rewritten(self):
        result_path = self.source / "result.json"
        result = json.loads(result_path.read_text())
        result["plans"][0]["terminal_state"] = []
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
                for name in names
            ),
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "independent finite-plan replay rejected result"):
            stage_module._inputs(self.source)

    def test_rejects_report_file_symlinks_even_with_matching_checksums(self):
        outside = self.root / "outside-readme.md"
        outside.write_text("outside bundle\n", encoding="utf-8")
        readme = self.source / "README.md"
        readme.unlink()
        try:
            os.symlink(outside, readme)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        names = [name for name in stage_module.FILES if name != "SHA256SUMS"]
        (self.source / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n"
                for name in names
            ),
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "regular non-symlink files"):
            stage_module._inputs(self.source)


if __name__ == "__main__":
    unittest.main()

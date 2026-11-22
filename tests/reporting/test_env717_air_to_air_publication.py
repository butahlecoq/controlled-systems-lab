"""Verify the archived report packaging from both supported CLI entry points."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-air-to-air-pilot-v1"
ROUTE = "env717-air-to-air-32985fda3c8312da3566"
ARCHIVE = "05426bb96a74d6d1c681afe58a9f7cc09e2bb5fa26b075dc1906e1794db77b16"


class ArchivedEnvironmentPublicationTests(unittest.TestCase):
    def test_both_entry_points_preserve_the_published_route_and_zip(self) -> None:
        commands = (
            [str(ROOT / "scripts/reports/stage_env717_air_to_air.py")],
            ["-m", "scripts.reports.stage_env717_air_to_air"],
        )
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                site = Path(directory)
                index = site / "index.html"
                index.write_text("<ul></ul>", encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, *command, "--source", str(SOURCE), "--site", str(site)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.strip(), ROUTE)
                self.assertEqual(
                    hashlib.sha256((site / f"{ROUTE}.zip").read_bytes()).hexdigest(), ARCHIVE
                )
                self.assertIn(f'href="{ROUTE}/index.html"', index.read_text(encoding="utf-8"))

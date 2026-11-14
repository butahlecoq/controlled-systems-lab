"""Validate the additive, source-only initial closed-loop publication."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_closed_loop_initial_baselines as publisher  # noqa: E402


class ClosedLoopInitialBaselinesPublicationTests(unittest.TestCase):
    def test_stage_preserves_manifested_bytes_and_archive(self) -> None:
        source = ROOT / "reports/closed-loop-initial-baselines-v1"
        manifest = json.loads((source / "publication-manifest.json").read_text())
        self.assertEqual(manifest["archive"]["capture_manifest_mapped_members"], 1179)
        self.assertEqual(manifest["archive"]["zip_non_directory_members"], 1182)
        self.assertEqual(len(manifest["archive"]["additional_members"]), 3)
        archive_path = ROOT / "reports/closed-loop-initial-baselines-v1.zip"
        with ZipFile(archive_path) as frozen:
            members = [name for name in frozen.namelist() if not name.endswith("/")]
            self.assertEqual(len(members), manifest["archive"]["zip_non_directory_members"])
            self.assertTrue(set(manifest["archive"]["additional_members"]).issubset(members))
            self.assertIsNone(frozen.testzip())

        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            publisher.stage(source, site)
            route = site / "closed-loop-initial-baselines-v1"
            for relative, metadata in manifest["files"].items():
                with self.subTest(asset=relative):
                    staged = route / relative
                    self.assertEqual(staged.stat().st_size, metadata["bytes"])
                    self.assertEqual(
                        hashlib.sha256(staged.read_bytes()).hexdigest(), metadata["sha256"]
                    )
            staged_archive = site / "closed-loop-initial-baselines-v1.zip"
            self.assertEqual(
                hashlib.sha256(staged_archive.read_bytes()).hexdigest(),
                manifest["archive"]["sha256"],
            )

"""Exercise REVIEW-05 capture admission and package a previously saved archive."""

import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.reports import stage_review05_family_query as saved_report

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "benchmarks/reporting/review05"


class Review05CaptureToolTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "linux", "The capture tools use Linux wait4")
    def test_capture_and_profiler_reject_ineligible_inputs_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            cache = bundle / "CMakeCache.txt"
            cache.write_text("CMAKE_BUILD_TYPE:STRING=Debug\n")
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "run_family_query.py"),
                    "--driver",
                    str(bundle / "never-executed"),
                    "--output",
                    str(bundle / "capture"),
                    "--build-cache",
                    str(cache),
                    "--repetitions",
                    "4",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertIn("at least five measured repetitions", run.stderr)
            self.assertFalse((bundle / "capture").exists())
            profile = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "profile_family_query.py"),
                    "--driver",
                    str(sys.executable),
                    "--bundle",
                    str(bundle),
                    "--build-cache",
                    str(cache),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(profile.returncode, 2, profile.stderr)
            self.assertIn("profile needs a Release cache", profile.stderr)
            self.assertFalse((bundle / "limiter-profile").exists())

    def test_packager_retains_every_saved_member_and_indexes_only_reading_assets(self):
        capture = saved_report.QUERY_SOURCE
        archive_bytes = (capture / "offline.zip").read_bytes()
        member_manifest = (capture / "archive-members.sha256").read_bytes()
        saved_report.checked_zip(archive_bytes, member_manifest)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            result = root / "repacked"
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                archive.extractall(original)
                expected_digests = {
                    name: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in archive.namelist()
                }
            packaged = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "package_family_query.py"),
                    str(original),
                    str(result),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(packaged.returncode, 0, packaged.stderr)
            with zipfile.ZipFile(result / "offline.zip") as repacked:
                self.assertIsNone(repacked.testzip())
                self.assertCountEqual(repacked.namelist(), expected_digests.keys())
                for name, expected in expected_digests.items():
                    self.assertEqual(
                        hashlib.sha256(repacked.read(name)).hexdigest(), expected, name
                    )

            self.assertEqual((result / "archive-members.sha256").read_bytes(), member_manifest)
            self.assertEqual(
                (result / "summary.json").read_bytes(), (original / "summary.json").read_bytes()
            )
            self.assertIn('href="offline.zip"', (result / "index.html").read_text())
            output_manifest = {
                name: digest
                for digest, name in (
                    line.split("  ", 1) for line in (result / "SHA256SUMS").read_text().splitlines()
                )
            }
            actual = {
                path.relative_to(result).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in result.rglob("*")
                if path.is_file() and path != result / "SHA256SUMS"
            }
            self.assertEqual(output_manifest, actual)
            published = {
                path.relative_to(capture).as_posix()
                for path in capture.rglob("*")
                if path.is_file() and path != capture / "SHA256SUMS"
            }
            self.assertEqual(set(actual), published)

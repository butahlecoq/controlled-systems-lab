"""Public boundary and optional private-source checks for the A10 criterion trace."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check_l13_a10_saved_criterion.py")
PRIVATE_ROOT = None


def run_check(*args):
    return subprocess.run([sys.executable, "-B", "-O", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


class PublicBoundaryTests(unittest.TestCase):
    def test_literal_state_distinguishes_printed_and_archived_expressions(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            from check_l13_a10_saved_criterion import criterion_values
        finally:
            sys.path.pop(0)
        values = criterion_values((60.0, 4.0, 23.75, 2.0))
        self.assertEqual(values["l13_eq16"], math.sqrt(20.0625))
        self.assertEqual(values["a08_report"], math.sqrt(20.75))
        self.assertEqual(values["a09_candidate"], math.sqrt(21.0625))

    def test_missing_private_archive_is_explicit(self):
        result = run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("--archive-root", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_changed_a08_is_rejected_before_mat_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Публикации/Минимакс/Adaptive_Samara/Minmaxclosedloop.m"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not registered A08")
            result = run_check("--archive-root", root)
            self.assertEqual(source.read_bytes(), b"not registered A08")
        self.assertEqual(result.returncode, 2)
        self.assertIn("A08", result.stderr)
        self.assertIn("SHA-256", result.stderr)
        self.assertEqual(result.stdout, "")


class PrivateSavedWorkspaceTests(unittest.TestCase):
    def test_a10_saved_j_selects_a08_reporting_expression(self):
        if PRIVATE_ROOT is None:
            self.skipTest("registered private A08-A10 originals not supplied; saved-run trace NOT run")
        result = run_check("--archive-root", PRIVATE_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["variant"], "a10-saved-mat-criterion-trace-v1")
        self.assertEqual(set(report["source_sha256"]), {"A08", "A09", "A10"})
        self.assertEqual(report["saved_open_loop_controls"], [0.75, 1.0, -1.0, 0.25])
        self.assertEqual(report["saved_adaptive_controls"], [0.75, 0.75, -0.5, -0.5])
        self.assertEqual(report["open_loop_terminal"], [
            60.50153367245107, 18.08439396961137,
            23.72609163625532, 3.9803245521003423])
        self.assertEqual(report["adaptive_terminal"], [
            60.0, 14.589974321147963, 24.0, 3.2502993802977542])
        self.assertEqual(report["adaptive_trajectory_end"], report["adaptive_terminal"])
        self.assertAlmostEqual(report["saved_j"], 20.224269632967587, delta=1e-12)
        self.assertAlmostEqual(report["open_loop_a08_report"], 20.224269632967587, delta=1e-12)
        self.assertAlmostEqual(report["open_loop_a09_candidate"], 20.232894413366783, delta=1e-12)
        self.assertAlmostEqual(report["open_loop_l13_eq16"], 18.526058690517537, delta=1e-12)
        self.assertAlmostEqual(report["adaptive_a08_report"], 16.28551543110981, delta=1e-12)
        self.assertAlmostEqual(report["adaptive_a09_candidate"], 16.28551543110981, delta=1e-12)
        self.assertAlmostEqual(report["adaptive_l13_eq16"], 14.94763515588071, delta=1e-12)
        self.assertEqual(report["publication_row_match"], False)
        self.assertNotIn(str(Path(PRIVATE_ROOT).resolve()), result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path)
    arguments = parser.parse_args()
    PRIVATE_ROOT = arguments.archive_root or (
        Path(os.environ["CSL_PRIVATE_ARCHIVE_ROOT"])
        if "CSL_PRIVATE_ARCHIVE_ROOT" in os.environ else None)
    unittest.main(argv=[sys.argv[0]])

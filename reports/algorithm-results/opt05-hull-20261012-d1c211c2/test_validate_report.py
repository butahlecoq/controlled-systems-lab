#!/usr/bin/env python3
"""Corruption checks for the saved OPT-05 report validator."""
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPORT = Path(__file__).resolve().parent


class ValidatorRejectsCorruptCsvTests(unittest.TestCase):
    def run_with_corruption(self, relative: str, column: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="opt05-validator-") as temp_dir:
            copy = Path(temp_dir) / REPORT.name
            shutil.copytree(REPORT, copy)
            for path in (copy / relative, copy / "evidence/accepted-002" / relative):
                with path.open(newline="", encoding="utf-8") as stream:
                    reader = csv.DictReader(stream)
                    fieldnames = reader.fieldnames
                    rows = list(reader)
                self.assertTrue(rows)
                rows[0][column] = str(int(rows[0][column]) + 1)
                with path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
            return subprocess.run(
                [sys.executable, str(copy / "validate_report.py")],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_rejects_trial_value_changed_in_both_csv_copies(self) -> None:
        result = self.run_with_corruption("trials.csv", "elapsed_ns")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("trials.csv", result.stderr)

    def test_rejects_summary_value_changed_in_both_csv_copies(self) -> None:
        result = self.run_with_corruption("summary.csv", "median_ns")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("summary.csv", result.stderr)


if __name__ == "__main__":
    unittest.main()

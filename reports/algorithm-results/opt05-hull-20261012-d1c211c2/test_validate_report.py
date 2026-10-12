#!/usr/bin/env python3
"""Corruption checks for the saved OPT-05 report validator."""
from __future__ import annotations

import csv
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPORT = Path(__file__).resolve().parent


class ValidatorRejectsCorruptCsvTests(unittest.TestCase):
    def run_with_corruption(self, relative: str, column: str, optimized: bool = False) -> subprocess.CompletedProcess[str]:
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
            before = {name: (copy / name).read_bytes() for name in ("manifest.sha256", "bundle.zip", "bundle.zip.sha256")}
            result = subprocess.run(
                [sys.executable, *(["-O"] if optimized else []), str(copy / "validate_report.py")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(before, {name: (copy / name).read_bytes() for name in before})
            return result

    def test_rejects_trial_value_changed_in_both_csv_copies(self) -> None:
        result = self.run_with_corruption("trials.csv", "elapsed_ns")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("trials.csv", result.stderr)

    def test_rejects_summary_value_changed_in_both_csv_copies(self) -> None:
        result = self.run_with_corruption("summary.csv", "median_ns")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("summary.csv", result.stderr)

    def test_optimized_python_rejects_corrupt_trial(self) -> None:
        result = self.run_with_corruption("trials.csv", "elapsed_ns", optimized=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("trials.csv", result.stderr)

    def test_rejects_corrupt_saved_zip_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opt05-validator-") as temp_dir:
            copy = Path(temp_dir) / REPORT.name
            shutil.copytree(REPORT, copy)
            archive = copy / "bundle.zip"
            archive.write_bytes(archive.read_bytes() + b"corruption")
            before = {name: (copy / name).read_bytes() for name in ("manifest.sha256", "bundle.zip", "bundle.zip.sha256")}
            result = subprocess.run([sys.executable, str(copy / "validate_report.py")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("bundle.zip", result.stderr)
            self.assertEqual(before, {name: (copy / name).read_bytes() for name in before})

    def test_rejects_corrupt_zip_member_with_refreshed_sidecar(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opt05-validator-") as temp_dir:
            copy = Path(temp_dir) / REPORT.name
            shutil.copytree(REPORT, copy)
            archive = copy / "bundle.zip"
            with zipfile.ZipFile(archive) as source:
                members = [(info, source.read(info.filename)) for info in source.infolist()]
            with zipfile.ZipFile(archive, "w") as changed:
                for info, data in members:
                    changed.writestr(info, data + b"corruption" if info.filename.endswith("/README.md") else data)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            (copy / "bundle.zip.sha256").write_bytes(f"{digest}  bundle.zip\n".encode("ascii"))
            before = {name: (copy / name).read_bytes() for name in ("manifest.sha256", "bundle.zip", "bundle.zip.sha256")}
            result = subprocess.run([sys.executable, str(copy / "validate_report.py")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("bundle.zip bytes differ", result.stderr)
            self.assertEqual(before, {name: (copy / name).read_bytes() for name in before})


if __name__ == "__main__":
    unittest.main()

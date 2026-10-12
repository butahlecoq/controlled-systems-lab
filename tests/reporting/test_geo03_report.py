from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "algorithm-results"
VALIDATOR_PATH = ROOT / "reports" / "algorithm-results" / "tooling" / "geo03" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("geo03_validate_report", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class Geo03ReportCsvProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = sorted(path for path in REPORTS.glob("geo03-*") if path.is_dir())
        if len(cls.sources) != 1:
            raise AssertionError(f"expected one committed GEO-03 report fixture, found {len(cls.sources)}")
        cls.source = cls.sources[0]

    def copy_report(self, temp: str) -> Path:
        report = Path(temp) / self.source.name
        shutil.copytree(self.source, report)
        shutil.copy2(self.source.with_name(self.source.name + ".source.zip"), report.parent / f"{self.source.name}.source.zip")
        return report

    @staticmethod
    def refresh_manifest_for(report: Path, changed_name: str) -> None:
        manifest_path = report / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][changed_name] = hashlib.sha256((report / changed_name).read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        assert manifest["files"][changed_name] == hashlib.sha256((report / changed_name).read_bytes()).hexdigest()

    def test_saved_report_and_csv_projections_validate(self) -> None:
        VALIDATOR.validate(self.source)

    def test_modified_trial_csv_is_rejected_after_manifest_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.copy_report(temp)
            path = report / "trials.csv"
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            self.assertIsNotNone(fields)
            rows[0]["run_ns"] = str(int(rows[0]["run_ns"]) + 1)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            self.refresh_manifest_for(report, "trials.csv")
            with self.assertRaisesRegex(AssertionError, "trials CSV does not exactly project"):
                VALIDATOR.validate(report)

    def test_modified_summary_csv_is_rejected_after_manifest_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.copy_report(temp)
            path = report / "summary.csv"
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            self.assertIsNotNone(fields)
            rows[0]["run_ns_median_ns"] = str(int(rows[0]["run_ns_median_ns"]) + 1)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            self.refresh_manifest_for(report, "summary.csv")
            with self.assertRaisesRegex(AssertionError, "summary CSV does not exactly project"):
                VALIDATOR.validate(report)


if __name__ == "__main__":
    unittest.main()

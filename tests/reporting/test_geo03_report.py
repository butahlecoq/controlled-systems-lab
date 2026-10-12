from __future__ import annotations

import csv
import argparse
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "algorithm-results"
VALIDATOR_PATH = ROOT / "reports" / "algorithm-results" / "tooling" / "geo03" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("geo03_validate_report", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
BUILDER_PATH = ROOT / "reports" / "algorithm-results" / "tooling" / "geo03" / "build_report.py"
BUILDER_SPEC = importlib.util.spec_from_file_location("geo03_build_report", BUILDER_PATH)
assert BUILDER_SPEC is not None and BUILDER_SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(BUILDER)


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
        shutil.copy2(self.source.with_suffix(".zip"), report.parent / f"{self.source.name}.zip")
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

    def test_saved_report_audits_archival_lineage_without_equivalence_claim(self) -> None:
        wrapper = json.loads((self.source / "records.json").read_text(encoding="utf-8"))
        payload = wrapper["payload"]
        audit = payload["lineage_audit"]
        self.assertEqual(audit["status"], "source-level review; executable equivalence not established")
        self.assertEqual(audit["contract_reference"], "docs/contracts/polyhedral-conversion.md#lineage-audit-a17-and-a18")
        self.assertEqual(audit["sources"], {
            "A17": {
                "path": "Scientific Research/GeoCalcLib-master/vertexEnumeration.m",
                "sha256": "d0f4ef259c0e33a48c0b2f56480e4a1c68df42a1783baf6e8110af8078e5fd19",
                "finding": "thin wrapper delegates to external libgeocalc; its algorithm and guarantees are not established by the archived wrapper",
            },
            "A18": {
                "path": "Конференция/ICIE 2018/VertexEnumeration.m",
                "sha256": "0d70893bd42066ed311b6ab36aa203e9fdf8856863cc23d9b5e254e45a87bee6",
                "finding": "homogenization, rank completion, randomized initial basis, inverse-based ray updates, and epsilon-policy division; not the Qhull polar-facet algorithm",
            },
        })
        self.assertNotIn("A17/A18 lineage not audited", payload["scope_limitations"])
        html = (self.source / "index.html").read_text(encoding="utf-8")
        self.assertIn("A17/A18 source-level lineage", html)
        self.assertIn("Executable equivalence is not established", html)
        VALIDATOR.validate(self.source)

    def test_resealed_false_lineage_claim_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.copy_report(temp)
            wrapper_path = report / "records.json"
            wrapper = json.loads(wrapper_path.read_text(encoding="utf-8"))
            wrapper["payload"]["lineage_audit"]["status"] = "executable equivalence established"
            payload_digest = hashlib.sha256(VALIDATOR.canonical(wrapper["payload"])).hexdigest()
            wrapper["payload_sha256"] = payload_digest
            report_id = f"geo03-{wrapper['payload']['created_utc'][:10].replace('-', '')}-{payload_digest[:12]}"
            wrapper["report_id"] = report_id
            wrapper_path.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

            manifest_path = report / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["report_id"] = report_id
            manifest["files"]["records.json"] = hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with zipfile.ZipFile(report.parent / f"{report_id}.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(report.iterdir()):
                    archive.write(path, path.name)

            with self.assertRaisesRegex(AssertionError, "A17/A18 source lineage audit"):
                VALIDATOR.validate(report)

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

    def test_zip_manifest_must_equal_adjacent_manifest_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.copy_report(temp)
            archive_path = report.parent / f"{report.name}.zip"
            with zipfile.ZipFile(archive_path) as original:
                members = [(info, original.read(info.filename)) for info in original.infolist()]
            with zipfile.ZipFile(archive_path, "w") as changed:
                for info, data in members:
                    changed.writestr(info, data + b"\n" if info.filename == "manifest.json" else data)
            with self.assertRaisesRegex(AssertionError, "ZIP manifest differs"):
                VALIDATOR.validate(report)

    def test_saved_package_rebuild_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.copy_report(temp)
            first_archive = BUILDER.package_artifacts(report, report.name)
            first = first_archive.read_bytes()
            second_archive = BUILDER.package_artifacts(report, report.name)
            self.assertEqual(first, second_archive.read_bytes())
            VALIDATOR.validate(report)


class Geo03FailedCollectionTests(unittest.TestCase):
    @staticmethod
    def driver_csv_with_change(field: str, value: str) -> tuple[str, int]:
        source = next(path for path in REPORTS.glob("geo03-*") if path.is_dir())
        with (source / "raw-driver-output.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            rows = list(reader)
        assert fields is not None
        rows[0][field] = value
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue(), len(rows)

    def test_nonzero_process_preserves_available_output_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "failed"
            args = argparse.Namespace(exe=Path("driver.exe"), repetitions=7, warmups=1,
                                      out=out, cmake_version="test")
            with patch.object(BUILDER, "load_snapshot", return_value={"sample": "test"}), \
                 patch.object(BUILDER, "run_text", return_value=(9, "partial,csv\n", "native failure\n")):
                with self.assertRaisesRegex(SystemExit, "executable failed"):
                    BUILDER.collect(args)
            self.assertEqual((out / "raw-driver-output.csv").read_text(), "partial,csv\n")
            self.assertEqual((out / "process-stderr.txt").read_text(), "native failure\n")
            status = json.loads((out / "collection-status.json").read_text())
            self.assertEqual(status["process_return_code"], 9)
            self.assertEqual(status["state"], "failed")
            self.assertFalse((out / "records.json").exists())

    def test_failed_oracle_preserves_all_emitted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "failed"
            args = argparse.Namespace(exe=Path("driver.exe"), repetitions=7, warmups=1,
                                      out=out, cmake_version="test")
            raw, count = self.driver_csv_with_change("oracle_passed", "false")
            with patch.object(BUILDER, "load_snapshot", return_value={"sample": "test"}), \
                 patch.object(BUILDER, "run_text", return_value=(0, raw, "oracle detail\n")):
                with self.assertRaises(SystemExit):
                    BUILDER.collect(args)
            self.assertEqual((out / "raw-driver-output.csv").read_text(), raw)
            self.assertEqual((out / "process-stderr.txt").read_text(), "oracle detail\n")
            status = json.loads((out / "collection-status.json").read_text())
            self.assertEqual(status["parsed_rows"], count)
            self.assertEqual(status["expected_rows"], count)
            self.assertEqual(status["state"], "failed")
            self.assertIn("oracle", status["reason"])

    def test_malformed_csv_preserves_raw_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "failed"
            args = argparse.Namespace(exe=Path("driver.exe"), repetitions=5, warmups=1,
                                      out=out, cmake_version="test")
            raw = "not,a,driver,header\n" + "malformed,row\n" * 40
            with patch.object(BUILDER, "load_snapshot", return_value={"sample": "test"}), \
                 patch.object(BUILDER, "run_text", return_value=(0, raw, "parse detail\n")):
                with self.assertRaises(SystemExit):
                    BUILDER.collect(args)
            self.assertEqual((out / "raw-driver-output.csv").read_text(), raw)
            self.assertEqual((out / "process-stderr.txt").read_text(), "parse detail\n")
            status = json.loads((out / "collection-status.json").read_text())
            self.assertEqual(status["state"], "failed")
            self.assertIn("malformed", status["reason"])

    def test_bad_numeric_row_preserves_raw_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "failed"
            args = argparse.Namespace(exe=Path("driver.exe"), repetitions=7, warmups=1,
                                      out=out, cmake_version="test")
            raw, count = self.driver_csv_with_change("run_ns", "not-an-integer")
            with patch.object(BUILDER, "load_snapshot", return_value={"sample": "test"}), \
                 patch.object(BUILDER, "run_text", return_value=(0, raw, "numeric detail\n")):
                with self.assertRaises(SystemExit):
                    BUILDER.collect(args)
            self.assertEqual((out / "raw-driver-output.csv").read_text(), raw)
            status = json.loads((out / "collection-status.json").read_text())
            self.assertEqual(status["parsed_rows"], count)
            self.assertIn("numeric", status["reason"])

    def test_failed_roster_preserves_raw_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "failed"
            args = argparse.Namespace(exe=Path("driver.exe"), repetitions=7, warmups=1,
                                      out=out, cmake_version="test")
            raw, count = self.driver_csv_with_change("fixture", "unexpected-fixture")
            with patch.object(BUILDER, "load_snapshot", return_value={"sample": "test"}), \
                 patch.object(BUILDER, "run_text", return_value=(0, raw, "roster detail\n")):
                with self.assertRaises(SystemExit):
                    BUILDER.collect(args)
            self.assertEqual((out / "raw-driver-output.csv").read_text(), raw)
            status = json.loads((out / "collection-status.json").read_text())
            self.assertEqual(status["parsed_rows"], count)
            self.assertIn("roster", status["reason"])


if __name__ == "__main__":
    unittest.main()

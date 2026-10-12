from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
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


if __name__ == "__main__":
    unittest.main()

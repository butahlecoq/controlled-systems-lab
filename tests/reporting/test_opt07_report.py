"""Synthetic-only saved-data tests; these are never benchmark observations."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "reports/algorithm-results/tooling/opt07"))
import build_bundle as report  # noqa: E402
from oracle import FIXTURES  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
import opt07_registered_reports as publisher  # noqa: E402
site_spec = importlib.util.spec_from_file_location(
    "opt07_report_site", Path(__file__).resolve().parents[2] /
    "scripts/reports/site.py")
report_site = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(report_site)


CERTIFICATES = {
    "signed-score": ([0, 1, 2, 3],
                     [(5, [(2, 0.125), (3, 0.875)]),
                      (4, [(0, 0.375), (2, 0.625)])]),
    "zero-width-duplicate": ([1, 3],
                             [(0, [(3, 1.0)]),
                              (2, [(1, 0.5), (3, 0.5)])]),
    "late-outside": ([0, 3],
                     [(2, [(0, 0.75), (3, 0.25)]),
                      (1, [(0, 0.5), (3, 0.5)])]),
}


def synthetic_call(case_id: str, round_id: int, ordinal: int) -> dict:
    fixture = FIXTURES[case_id]
    retained, certificates = CERTIFICATES[case_id]
    removed = [{"point": point, "program_problem": f"opt07-{case_id}",
                "program": f"hull-membership-{point}",
                "terms": [[index, weight] for index, weight in terms]}
               for point, terms in certificates]
    removed_ids = {point for point, _ in certificates}
    return {"kind": "call", "purpose": "measurement", "case_id": case_id,
            "problem": f"opt07-{case_id}", "round": round_id,
            "warmup": round_id == 0, "ordinal": ordinal,
            "points": fixture["points"], "verified": True, "status": "complete",
            "retained": retained, "removed": removed, "order": fixture["order"],
            "ordered_candidates": len(fixture["points"]),
            "zero_width_coordinates": fixture["zero_width"],
            "identity_fallback": False, "lp_calls": len(fixture["points"]),
            "attempts": [[point, "feasible" if point in removed_ids else "infeasible"]
                         for point in fixture["order"]],
            "support": fixture["support"]}


def synthetic_collection(directory: Path) -> None:
    rows = []
    for case_index, case_id in enumerate(FIXTURES):
        for round_id in range(8):
            rows.extend(synthetic_call(case_id, round_id, ordinal)
                        for ordinal in range(100))
            rows.append({"kind": "batch", "purpose": "measurement",
                         "case_id": case_id, "round": round_id,
                         "warmup": round_id == 0, "calls": 100,
                         "verified_calls": 100,
                         "elapsed_ns": 1000 + case_index * 1000 + round_id * 10})
    (directory / "raw-stdout.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8", newline="\n")
    (directory / "raw-stderr.txt").write_bytes(b"")
    log = b"Clean Release /O2 /D NDEBUG /std:c++20 at $SOURCE_ROOT\n"
    (directory / "release-build-log-sanitized.txt").write_bytes(log)
    (directory / "functional-validation.json").write_text(
        json.dumps({"purpose": "measurement", "fixtures": 3,
                    "batches": 24, "calls": 2400}), encoding="utf-8")
    commit = "a" * 40
    collection = {"source_commit": commit,
                  "description": {"source_commit": commit,
                                  "configuration": "Release",
                                  "batch_calls": 100, "repetitions": 7},
                  "algorithm": {"method": "csl.hull.ordered-membership",
                                "version": "1.0.0"},
                  "backend": {"method": "csl.lp.highs",
                              "adapter_version": "1.0.0+highs.1.11.0",
                              "configured_threads": 1},
                  "process_exit_code": 0,
                  "protocol": {"warmup_batches_per_fixture": 1,
                               "measured_batches_per_fixture": 7,
                               "calls_per_batch": 100},
                  "build_log_sha256": "b" * 64,
                  "sanitized_build_log_sha256": hashlib.sha256(log).hexdigest(),
                  "executable_sha256": "c" * 64,
                  "fixture_sha256": "d" * 64,
                  "cmake_cache_sha256": "e" * 64,
                  "generated_release_project_sha256": "f" * 64,
                  "source_sha256": {"synthetic.cpp": "a" * 64},
                  "release_project": {"LanguageStandard": "stdcpp20",
                                      "Optimization": "MaxSpeed",
                                      "PreprocessorDefinitions": "NDEBUG"},
                  "environment": {"os": "synthetic test host",
                                  "machine": "synthetic machine",
                                  "logical_processors": 1,
                                  "concurrent_work_note": "synthetic test only"}}
    (directory / "collection.json").write_text(json.dumps(collection),
                                                  encoding="utf-8")


class SavedReportTests(unittest.TestCase):
    def test_build_check_and_literal_batch_median_from_synthetic_raw(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "synthetic-collection"
            collection.mkdir()
            synthetic_collection(collection)
            bundle = report.build(collection, root)
            checked = report.check(bundle)
            self.assertEqual(checked["summary"][0]["median_batch_ns"], 1040)
            self.assertEqual(checked["summary"][0]["measured_calls"], 700)
            self.assertEqual(checked["validation"]["calls"], 2400)
            self.assertEqual((bundle / "raw-stdout.jsonl").read_bytes(),
                             (collection / "raw-stdout.jsonl").read_bytes())
            self.assertIn("All batch outcomes", (bundle / "index.html").read_text())
            self.assertIn("complete", (bundle / "index.html").read_text())

    def test_corrupt_raw_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary)
            synthetic_collection(collection)
            raw = collection / "raw-stdout.jsonl"
            lines = raw.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])
            first["removed"][0]["terms"][0][1] = 0.12500000000000003
            lines[0] = json.dumps(first)
            raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "reconstruct|sum exactly"):
                report.report_record(collection)

    def test_rehashed_html_cannot_override_saved_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "synthetic-collection"
            collection.mkdir()
            synthetic_collection(collection)
            bundle = report.build(collection, root)
            page = bundle / "index.html"
            page.write_text(page.read_text(encoding="utf-8").replace(
                "median of seven", "median of nine"), encoding="utf-8")
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["index.html"] = report.digest(page.read_bytes())
            manifest_path.write_bytes(report.json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, "saved projection differs"):
                report.check(bundle)

    def test_schema3_adapter_stages_synthetic_bundle_only_in_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "synthetic-collection"
            collection.mkdir()
            synthetic_collection(collection)
            bundle = report.build(collection, root)
            item = publisher.adapt(bundle)
            row = {"report_id": item.report_id, "report_kind": item.kind,
                   "payload_schema": item.payload_schema,
                   "payload_sha256": item.payload_sha256,
                   "source_commit": item.source_commit,
                   "measured_scope": item.measured_scope,
                   "evidence_limits": item.evidence_limits,
                   "native_payload_sha256": item.native_payload_sha256,
                   "source_report_id": item.source_report_id,
                   "zip_sha256": report.digest(publisher.offline_zip(bundle, item))}
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"schema": "csl.algorithm-report-catalog/3",
                                           "artifact_ref": "main", "reports": [row]}),
                               encoding="utf-8")
            with patch.object(report_site, "legacy_pins", return_value={}):
                staged = report_site.stage(catalog, root / "staged", check=False)
            self.assertTrue((staged / item.report_id / "publication-manifest.json").is_file())
            self.assertIn("synthetic test host", (staged / item.report_id /
                                                   "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

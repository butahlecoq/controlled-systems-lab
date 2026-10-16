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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
import opt07_registered_reports as publisher  # noqa: E402
report = publisher.source
SOURCE_PATHS = report.SOURCE_PATHS
fixture_sha256 = report.fixture_sha256
FIXTURES = report.FIXTURES
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
    return {"kind": "call", "purpose": "test", "case_id": case_id,
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
            rows.append({"kind": "batch", "purpose": "test",
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
        json.dumps({"purpose": "test", "fixtures": 3,
                    "batches": 24, "calls": 2400}), encoding="utf-8")
    commit = "a" * 40
    collection = {"purpose": "test", "source_commit": commit,
                  "description": {"kind": "describe", "source_commit": commit,
                                  "harness_sha256": "b" * 64,
                                  "configuration": "Release",
                                  "cxx_standard": 202002, "ndebug": True,
                                  "batch_calls": 100, "repetitions": 7},
                  "algorithm": {"method": "csl.hull.ordered-membership",
                                "version": "1.0.0"},
                  "backend": {"method": "csl.lp.highs",
                              "adapter_version": "1.0.0+highs.1.11.0",
                              "configured_threads": 1},
                  "process_exit_code": 0,
                  "raw_stdout_sha256": hashlib.sha256(
                      (directory / "raw-stdout.jsonl").read_bytes()).hexdigest(),
                  "raw_stderr_sha256": hashlib.sha256(
                      (directory / "raw-stderr.txt").read_bytes()).hexdigest(),
                  "protocol": {"warmup_batches_per_fixture": 1,
                               "measured_batches_per_fixture": 7,
                               "calls_per_batch": 100},
                  "build_log_sha256": "b" * 64,
                  "sanitized_build_log_sha256": hashlib.sha256(log).hexdigest(),
                  "executable_sha256": "c" * 64,
                  "fixture_sha256": fixture_sha256(),
                  "cmake_cache_sha256": "e" * 64,
                  "generated_release_project_sha256": "f" * 64,
                  "source_sha256": {path: ("b" if path.endswith(
                      "ordered_hull_driver.cpp") else "a") * 64
                                    for path in SOURCE_PATHS},
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
            with self.assertRaisesRegex(ValueError, "test-only"):
                report.build(collection, root)
            bundle = report.build(collection, root, allow_test=True)
            with self.assertRaisesRegex(ValueError, "test-only"):
                report.check(bundle)
            checked = report.check(bundle, allow_test=True)
            self.assertEqual(checked["summary"][0]["median_batch_ns"], 1040)
            self.assertEqual(checked["summary"][0]["nonwarmup_calls"], 700)
            self.assertEqual(checked["validation"]["calls"], 2400)
            self.assertEqual((bundle / "raw-stdout.jsonl").read_bytes(),
                             (collection / "raw-stdout.jsonl").read_bytes())
            self.assertIn("TEST / synthetic", (bundle / "index.html").read_text())
            self.assertNotIn("Measured batches", (bundle / "index.html").read_text())
            self.assertNotIn("Seven measured", (bundle / "latency.svg").read_text())
            self.assertEqual(checked["purpose"], "test")
            self.assertIn("synthetic test data", checked["performance_interpretation"])
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
            metadata = json.loads((collection / "collection.json").read_text())
            metadata["raw_stdout_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
            (collection / "collection.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "reconstruct|sum exactly"):
                report.report_record(collection, allow_test=True)

    def test_rehashed_html_cannot_override_saved_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "synthetic-collection"
            collection.mkdir()
            synthetic_collection(collection)
            bundle = report.build(collection, root, allow_test=True)
            page = bundle / "index.html"
            page.write_text(page.read_text(encoding="utf-8").replace(
                "median of seven", "median of nine"), encoding="utf-8")
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["index.html"] = report.digest(page.read_bytes())
            manifest_path.write_bytes(report.json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, "saved projection differs"):
                report.check(bundle, allow_test=True)

    def test_schema3_adapter_rejects_synthetic_bundle_even_with_site_test_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "synthetic-collection"
            collection.mkdir()
            synthetic_collection(collection)
            bundle = report.build(collection, root, allow_test=True)
            with self.assertRaisesRegex(ValueError, "test-only"):
                publisher.adapt(bundle)
            row = {"report_id": "opt07-" + "b" * 64,
                   "report_kind": publisher.KIND,
                   "source_report_id": bundle.name}
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"schema": "csl.algorithm-report-catalog/3",
                                           "artifact_ref": "main", "reports": [row]}),
                               encoding="utf-8")
            with patch.object(report_site, "legacy_pins", return_value={}):
                with self.assertRaisesRegex(ValueError, "test-only"):
                    report_site.stage(catalog, root / "staged", check=False,
                                      allow_test=True)

    def test_changed_valid_batch_rejected_by_collection_time_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary)
            synthetic_collection(collection)
            raw = collection / "raw-stdout.jsonl"
            lines = raw.read_text(encoding="utf-8").splitlines()
            batch = json.loads(lines[100])
            batch["elapsed_ns"] += 1
            lines[100] = json.dumps(batch)
            raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw stdout hash"):
                report.report_record(collection, allow_test=True)

    def test_changed_stderr_rejected_by_collection_time_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary)
            synthetic_collection(collection)
            (collection / "raw-stderr.txt").write_bytes(b"new diagnostic\n")
            with self.assertRaisesRegex(ValueError, "raw stderr hash"):
                report.report_record(collection, allow_test=True)

    def test_fixture_source_and_description_provenance_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary)
            synthetic_collection(collection)
            path = collection / "collection.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            mutations = (
                (lambda data: data["source_sha256"].update({"synthetic.cpp": "a" * 64}),
                 "source file inventory"),
                (lambda data: data.update({"fixture_sha256": "d" * 64}),
                 "fixture digest"),
                (lambda data: data["description"].update({"harness_sha256": "e" * 64}),
                 "harness digest"),
                (lambda data: data["description"].update({"ndebug": False}),
                 "source-bound"),
                (lambda data: data["description"].update({"batch_calls": 1}),
                 "source-bound"),
            )
            for mutate, message in mutations:
                with self.subTest(message=message):
                    data = json.loads(json.dumps(original))
                    mutate(data)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        report.report_record(collection, allow_test=True)


if __name__ == "__main__":
    unittest.main()

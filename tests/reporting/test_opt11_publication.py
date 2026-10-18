"""Exercise OPT-11 native bundle publication through the schema-3 site path."""
import hashlib
import importlib.util
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
SITE_PATH = ROOT / "scripts" / "reports" / "site.py"
SITE_SPEC = importlib.util.spec_from_file_location("csl_opt11_test_report_site", SITE_PATH)
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)


class Opt11PublicationTests(unittest.TestCase):
    def make_collection(self, directory: Path) -> Path:
        builder = report_site.opt11.source
        oracle = builder.FIXTURES
        rows = []
        for fixture_id, points in oracle.items():
            for round_id in range(1):
                warmup = False
                recursive_first = (round_id + list(oracle).index(fixture_id)) % 2 == 1
                methods = ("recursive", "baseline") if recursive_first else ("baseline", "recursive")
                for method in methods:
                    call = {
                        "kind": "call", "purpose": "test", "fixture": fixture_id,
                        "round": round_id, "warmup": warmup, "method": method,
                        "problem": f"opt11-{fixture_id}",
                        "elapsed_ns": 1000 + round_id * 10 + (method == "recursive"),
                        "points": points, "status": "complete", "retained": list(range(len(points))),
                        "support": [max(x * d[0] + y * d[1] for x, y in points)
                                    for d in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1))],
                        "removed": [], "lp_calls": 0, "attempts": [], "recursive": None,
                    }
                    if method == "recursive":
                        call["recursive"] = {"leaf_nodes": 1, "merge_nodes": 0,
                                             "leaf_lp_calls": 0, "merge_lp_calls": 0,
                                             "peak_merge_points": 0, "concurrent_child_subtrees": 0,
                                             "parallel_overhead_microseconds": 0}
                    rows.append(call)
                rows.append({"kind": "pair", "purpose": "test", "fixture": fixture_id,
                             "round": round_id, "warmup": warmup,
                             "recursive_first": recursive_first})
        raw = ("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n").encode()
        collection = directory / "collection"
        collection.mkdir()
        raw_path = collection / "raw-stdout.jsonl"
        raw_path.write_bytes(raw)
        stderr = b""
        compiler_path = "$PROGRAM_FILES_X86/MSVC/cl.exe"
        build_log = ("\n".join(
            f'"{compiler_path}" /O2 /std:c++20 /D NDEBUG "${{SOURCE_ROOT}}/{source}"'
            for source in builder.TIMING_TRANSLATION_UNITS) + "\n").encode()
        compiler_source = (f'set(CMAKE_CXX_COMPILER "{compiler_path}")\n'
                           'set(CMAKE_CXX_COMPILER_ID "test")\n'
                           'set(CMAKE_CXX_COMPILER_VERSION "test")\n').encode()
        (collection / "raw-stderr.txt").write_bytes(stderr)
        (collection / "release-build-log-sanitized.txt").write_bytes(build_log)
        (collection / "compiler-identification.cmake").write_bytes(compiler_source)
        validation = builder.validate_stream(raw_path, "test")
        (collection / "functional-validation.json").write_text(
            json.dumps(validation, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                         for name in builder.SOURCE_PATHS}
        commit = "a" * 40
        harness_hash = source_hashes["reports/algorithm-results/tooling/opt11/recursive_hull_driver.cpp"]
        description = {"kind": "describe", "source_commit": commit,
                       "harness_sha256": harness_hash, "configuration": "Release",
                       "ndebug": True, "cxx_standard": 202002,
                       "warmups_per_fixture": 1, "measured_pairs_per_fixture": 6,
                       "backend": {"method": "csl.lp.highs", "version": "1.0.0+highs.1.11.0"}}
        metadata = {
            "purpose": "test", "source_commit": commit,
            "source_sha256": source_hashes, "fixture_sha256": builder.fixture_digest(),
            "harness_sha256": harness_hash,
            "algorithm": {"baseline": {"method": "csl.hull.lp-membership", "version": "1.0.0"},
                          "recursive": {"method": "csl.hull.recursive-split-merge", "version": "1.0.0"}},
            "backend": {"method": "csl.lp.highs", "version": "1.0.0+highs.1.11.0",
                        "adapter_version": "1.0.0", "native_version": "1.11.0",
                        "configured_threads": 1, "presolve": "off", "parallel": "off",
                        "observed_native_threads": None},
            "environment": {"os": "test", "machine": "test", "logical_processors": 1,
                            "python": "test", "concurrent_work_note": "isolated publisher test",
                            "observed_native_threads": None,
                            "machine_load": {
                                "before": {"utc": "2026-10-18T00:00:00Z", "os": "test",
                                           "logical_processors": 1, "python": "3.12", "cpu": "test",
                                           "load_percent": [0], "ram_bytes": 1024},
                                "after": {"utc": "2026-10-18T00:00:01Z", "os": "test",
                                          "logical_processors": 1, "python": "3.12", "cpu": "test",
                                          "load_percent": [0], "ram_bytes": 1024},
                                "process_cpu_deltas": {"available": True,
                                    "unit": "process CPU seconds over collection interval",
                                    "values": {"python": 0.0},
                                    "scope": "matching observed processes only; test fixture"}}},
            "release_project": {"generator": "test", "configuration": "Release",
                                "language_standard": "stdcpp20", "optimization": "MaxSpeed",
                                "preprocessor_definitions": "NDEBUG", "compiler_id": "test",
                                "compiler_version": "test", "compiler_path_sanitized": compiler_path,
                                "ndebug": True},
            "protocol": {"warmups_per_fixture": 0, "measured_pairs_per_fixture": 1,
                         "unavailable": []},
            "description": description, "executable_sha256": "b" * 64,
            "process_outcome": "completed", "process_exit_code": 0,
            "raw_stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "sanitized_build_log_sha256": hashlib.sha256(build_log).hexdigest(),
            "compiler_identification_sha256": hashlib.sha256(compiler_source).hexdigest(),
            "compiler_identification_source_sha256": "d" * 64,
            "validation": validation,
        }
        (collection / "collection.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return collection

    def build_native_bundle(self, root: Path) -> Path:
        builder = report_site.opt11.source
        collection = self.make_collection(root)
        out_root = root / "algorithm-results"
        out_root.mkdir()
        return builder.build(collection, out_root, allow_test=True)

    def test_saved_collection_rejects_compiler_path_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            collection = self.make_collection(Path(temp))
            metadata_path = collection / "collection.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["release_project"]["compiler_path_sanitized"] = "$PROGRAM_FILES_X86/Other/cl.exe"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from retained CMake compiler source"):
                report_site.opt11.source.read_collection(collection, allow_test=True)

    def test_saved_collection_rejects_compile_log_using_different_compiler(self):
        with tempfile.TemporaryDirectory() as temp:
            collection = self.make_collection(Path(temp))
            log_path = collection / "release-build-log-sanitized.txt"
            log = log_path.read_bytes().replace(b"$PROGRAM_FILES_X86/MSVC/cl.exe",
                                                b"$PROGRAM_FILES_X86/Other/cl.exe", 1)
            log_path.write_bytes(log)
            metadata_path = collection / "collection.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["sanitized_build_log_sha256"] = hashlib.sha256(log).hexdigest()
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sanitized compiler path is not present"):
                report_site.opt11.source.read_collection(collection, allow_test=True)

    def test_saved_collection_rejects_malformed_machine_load_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            collection = self.make_collection(Path(temp))
            metadata_path = collection / "collection.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["environment"]["machine_load"]["process_cpu_deltas"] = []
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "process CPU delta summary is malformed"):
                report_site.opt11.source.read_collection(collection, allow_test=True)

    def test_saved_collection_rejects_snapshots_without_load_data_or_unavailable_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            collection = self.make_collection(Path(temp))
            metadata_path = collection / "collection.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["environment"]["machine_load"]["before"] = {
                "utc": "2026-10-18T00:00:00Z", "os": "test",
                "logical_processors": 1, "python": "3.12"}
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "counters are absent"):
                report_site.opt11.source.read_collection(collection, allow_test=True)

    def test_exact_oracle_rejects_wrong_certificate_identity(self):
        oracle = importlib.import_module("csl_opt11_report_tooling.oracle")
        call = {"fixture": "signed-grid", "method": "baseline", "problem": "opt11-signed-grid",
                "points": oracle.FIXTURES["signed-grid"],
                "retained": [index for index in range(33) if index != 8],
                "removed": [{"point": 8, "program_problem": "opt11-signed-grid",
                             "program": "hull-membership-8", "terms": [[0, 1.0]]}]}
        oracle.exact_certificate(call)
        call["removed"][0]["program_problem"] = "opt11-other-cloud"
        with self.assertRaisesRegex(ValueError, "program problem identity"):
            oracle.exact_certificate(call)
        call["removed"][0]["program_problem"] = "opt11-signed-grid"
        call["removed"][0]["program"] = "hull-membership-9"
        with self.assertRaisesRegex(ValueError, "program identity"):
            oracle.exact_certificate(call)

    def test_native_bundle_stages_and_emits_repository_fallback_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = self.build_native_bundle(root)
            with self.assertRaisesRegex(ValueError, "explicit test gate"):
                report_site.opt11.adapt(bundle)
            publication = report_site.opt11.adapt(bundle, allow_test=True)
            self.assertEqual("opt11-recursive-hull", publication.kind)
            self.assertTrue(publication.report_id.startswith("opt11-"))
            self.assertEqual("3 alternating baseline/recursive pairs across 3 fixed clouds; "
                             "3 pairs complete; performance interpretation inconclusive",
                             publication.measured_scope)

            public_zip = report_site.opt11.offline_zip(bundle, publication, allow_test=True)
            production = ROOT / "reports" / "algorithm-results"
            legacy_catalogue = json.loads((production / "catalog.json").read_text(encoding="utf-8"))
            pinned_ids = set(json.loads((production / "legacy-publications.json").read_text(
                encoding="utf-8"))["reports"])
            legacy_rows = [row for row in legacy_catalogue["reports"]
                           if row.get("source_report_id") in pinned_ids]
            self.assertEqual(2, len(legacy_rows))
            shutil.copyfile(production / "legacy-publications.json", bundle.parent / "legacy-publications.json")
            for row in legacy_rows:
                source_id = row["source_report_id"]
                shutil.copytree(production / source_id, bundle.parent / source_id)
                shutil.copyfile(production / (source_id + ".source.zip"),
                                bundle.parent / (source_id + ".source.zip"))
                shutil.copyfile(production / (source_id + ".zip"),
                                bundle.parent / (source_id + ".zip"))
                shutil.copyfile(production / (row["report_id"] + ".zip"),
                                bundle.parent / (row["report_id"] + ".zip"))
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main",
                         "reports": legacy_rows + [{
                "report_id": publication.report_id, "source_report_id": publication.source_report_id,
                "report_kind": publication.kind, "source_commit": publication.source_commit,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "payload_schema": publication.payload_schema,
                "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "zip_sha256": hashlib.sha256(public_zip).hexdigest(),
            }]}
            (bundle.parent / (publication.report_id + ".zip")).write_bytes(public_zip)
            catalog_path = bundle.parent / "catalog.json"
            catalog_path.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
            (bundle.parent / "index.html").write_text(report_site.catalogue_index(catalogue), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicit test gate"):
                report_site.stage(catalog_path, root / "production-site", check=True)
            staged = report_site.stage(catalog_path, root / "site", check=True, allow_test=True)
            index = (staged / "index.html").read_text(encoding="utf-8")
            self.assertIn("https://github.com/butahlecoq/controlled-systems-lab/tree/main/reports/algorithm-results/"
                          + publication.source_report_id, index)
            self.assertIn("https://github.com/butahlecoq/controlled-systems-lab/blob/main/reports/algorithm-results/"
                          + publication.report_id + ".zip", index)
            envelope = json.loads((staged / publication.report_id / "report-envelope.json").read_text())
            self.assertEqual(publication.source_commit, envelope["source_commit"])
            self.assertEqual(publication.payload_schema, envelope["payload_schema"])
            self.assertEqual(publication.report_id, envelope["report_id"])
            self.assertEqual(publication.payload_sha256, envelope["payload_sha256"])
            self.assertEqual(publication.native_payload_sha256, envelope["native_payload_sha256"])
            self.assertEqual("test", envelope["payload"]["purpose"])

            catalogue["reports"][-1]["payload_sha256"] = "0" * 64
            catalog_path.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
            (bundle.parent / "index.html").write_text(report_site.catalogue_index(catalogue),
                                                        encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "registered catalogue provenance mismatch"):
                report_site.stage(catalog_path, root / "bad-digest-site", check=True, allow_test=True)
            catalogue["reports"][-1]["payload_sha256"] = publication.payload_sha256
            catalogue["reports"][-1]["report_id"] = "opt11-" + "0" * 64
            catalog_path.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
            (bundle.parent / "index.html").write_text(report_site.catalogue_index(catalogue),
                                                        encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "registered catalogue kind differs from bundle"):
                report_site.stage(catalog_path, root / "bad-id-site", check=True, allow_test=True)

    def test_tampered_native_source_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = self.build_native_bundle(Path(temp))
            source_zip = bundle.parent / (bundle.name + ".source.zip")
            source_zip.write_bytes(source_zip.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "offline ZIP mismatch"):
                report_site.opt11.adapt(bundle, allow_test=True)

    def test_tampered_native_report_id_or_payload_digest_is_rejected(self):
        for field, value in (("report_id", "opt11-" + "0" * 16),
                             ("payload_sha256", "0" * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                bundle = self.build_native_bundle(Path(temp))
                builder = report_site.opt11.source
                record_path = bundle / "records.json"
                record = json.loads(record_path.read_text(encoding="utf-8"))
                record[field] = value
                record_path.write_bytes(builder.json_bytes(record))
                manifest_path = bundle / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["files"]["records.json"] = builder.digest(record_path.read_bytes())
                manifest_path.write_bytes(builder.json_bytes(manifest))
                (bundle.parent / (bundle.name + ".source.zip")).write_bytes(builder.zip_bytes(bundle))
                with self.assertRaisesRegex(ValueError, "typed report differs from retained raw bytes"):
                    report_site.opt11.adapt(bundle, allow_test=True)


if __name__ == "__main__":
    unittest.main()

"""SYN-01 schema-3 adapter boundary tests over saved synthetic analytic records."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLING = ROOT / "reports" / "algorithm-results" / "tooling" / "syn01"
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
sys.path.insert(0, str(TOOLING))

import report
import publication_map
import syn01_registered_reports as adapter
import registered_reports

COLLECT_SPEC = importlib.util.spec_from_file_location("csl_syn01_test_collect", TOOLING / "collect.py")
collect = importlib.util.module_from_spec(COLLECT_SPEC)
COLLECT_SPEC.loader.exec_module(collect)

SITE_SPEC = importlib.util.spec_from_file_location("csl_syn01_test_site", ROOT / "scripts" / "reports" / "site.py")
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)

SOURCE = "a" * 40
HARNESS = "b" * 40
PROVIDER_IDS = {name: {"id": "csl." + name, "version": "1.0.0"} for name in (
    "projection", "affine_sum", "conversion", "lp_backend", "hull_reducer")}
PROVENANCE = {"algorithm_module": {"id": "csl.reachability.nominal-forward", "version": "0.1.0"},
              "providers": PROVIDER_IDS,
              "dependency_edges": {"affine_sum": ["hull_reducer", "lp_backend", "conversion"],
                                   "conversion": ["lp_backend"]},
              "runtime_settings": report.RUNTIME_SETTINGS,
              "native_thread_observation": {"status": "unavailable", "observed_threads": None,
                  "reason": "The driver has no supported runtime API to observe effective native worker threads."},
              "build_configuration": {"configuration": "Release", "generator": "Visual Studio 17 2022",
                  "generator_platform": "x64", "cxx_standard": "c++20", "compiler_id": "MSVC",
                  "compiler_version": "19.44.35215.0", "compiler_executable": "cl.exe", "cmake_version": "3.31.6",
                  "cmake_release_flags": "/O2 /Ob2 /DNDEBUG",
                  "target_release_properties": {"LanguageStandard": "stdcpp20", "Optimization": "MaxSpeed"},
                  "effective_release_flags": ["/std:c++20", "/O2", "/Ob2", "/DNDEBUG", "/W4", "/WX", "/permissive-"],
                  "evidence_sha256": {"CMakeCache.txt": "a" * 64, "build_configuration_file": "b" * 64,
                                       "release_build_log": "c" * 64}}}


def make_event(scenario, repetition):
    return {"schema": report.EVENT_SCHEMA, "scenario": scenario, "repetition": repetition,
            "warmup": repetition == 0, "status": "passed", "outcome": "forward_tube",
            "expected_marginals": report.EXPECTED[scenario], "observed_marginals": report.EXPECTED[scenario],
            "oracle_passed": True, "setup_ns": 100 + repetition, "solve_ns": 200 + repetition,
            "setup_state": "available", "solve_state": "available",
            "oracle_ns": 20, "oracle_state": "available", "execute_ns": 400 + repetition,
            "execute_state": "available", "provider_identities": PROVIDER_IDS,
            "execution_settings": report.RUNTIME_SETTINGS,
            "provider_operation_counts": {"csl.geometry.affine-sum": 4,
                                           "csl.geometry.polyhedral-projection": 2},
            "provider_operation_timing_ns": None, "detail": ""}


class Syn01PublicationTests(unittest.TestCase):
    def make_bundle(self, root):
        root.mkdir(parents=True, exist_ok=True)
        trials = [make_event(name, repetition) for repetition in range(8) for name in report.SCENARIOS]
        record = report.make_record(trials, source_commit=SOURCE, harness_commit=HARNESS,
                                    environment={"os": "fixture", "processor": "fixture"},
                                    provenance={**PROVENANCE, "configuration": "Release", "compiler_id": "fixture"})
        record["report_id"] = "syn01-nominal-20261013-aaaaaaaa-" + "c" * 12
        bundle = root / record["report_id"]
        bundle.mkdir()
        contents = {
            "README.md": b"fixture",
            "records.json": collect.canonical(record) + b"\n",
            "raw-events.jsonl": b"".join(collect.canonical(row) + b"\n" for row in trials),
            "trials.csv": collect.trials_csv(trials),
            "summary.csv": collect.summary_csv(record),
            "scenarios.json": collect.canonical({"fixture_catalog": record["fixture_catalog"],
                                                  "scenario_hashes": record["scenario_hashes"]}) + b"\n",
            "environment.json": collect.canonical(record["environment"]) + b"\n",
            "build-provenance.json": collect.canonical(record["provenance"]) + b"\n",
            "configure-log.txt": b"Release configure fixture\n",
            "build-log.txt": b"Release build fixture\n",
            "driver-stderr.txt": b"",
            "measurement-command.txt": b"fixture command\n",
            "profile-evidence.txt": b"No source profile; limiter and capacity remain unknown.\n",
            "index.html": report.render_html(record).encode("utf-8"),
            "latency.svg": report.render_svg(record).encode("utf-8"),
        }
        contents["publication-map.json"] = collect.canonical(publication_map.project(record)) + b"\n"
        for name, content in contents.items():
            (bundle / name).write_bytes(content)
        manifest = {"schema": "csl.syn01-report-manifest/1", "report_id": record["report_id"],
                    "source_commit": SOURCE, "harness_commit": HARNESS,
                    "files": {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}}
        (bundle / "manifest.json").write_bytes(collect.canonical(manifest) + b"\n")
        return bundle

    def test_valid_bundle_projects_schema3_envelope_and_deterministic_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory) / "reports")
            item = adapter.adapt(bundle)
            self.assertEqual("syn01-nominal-forward", item.kind)
            self.assertEqual(bundle.name, item.source_report_id)
            files = adapter.publication_artifacts(bundle, item)
            self.assertIn("latency.svg", files)
            self.assertIn("report-envelope.json", files)
            self.assertIn("publication-manifest.json", files)
            self.assertTrue(registered_reports.validate_publication_manifest(
                _write_publication(Path(directory), item, files), {"report_id": item.report_id,
                    "report_kind": item.kind, "payload_schema": item.payload_schema,
                    "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
                    "source_commit": SOURCE, "measured_scope": item.measured_scope,
                    "evidence_limits": item.evidence_limits, "source_report_id": item.source_report_id}))
            report_site.OfflineHTML(set(item.files) | {"report-envelope.json", "publication-manifest.json"}).feed(
                adapter.render_page(bundle, item))
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main", "reports": [{
                "report_id": item.report_id, "report_kind": item.kind, "source_report_id": item.source_report_id,
                "measured_scope": item.measured_scope, "evidence_limits": item.evidence_limits,
                "source_commit": item.source_commit}]}
            index = report_site.catalogue_index(catalogue)
            self.assertIn(item.report_id + "/index.html", index)
            self.assertEqual(adapter.offline_zip(bundle, item), adapter.offline_zip(bundle, item))

    def test_corrupted_file_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory) / "reports")
            (bundle / "latency.svg").write_text("<svg/>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                adapter.adapt(bundle)

    def test_raw_record_mismatch_is_rejected_even_with_updated_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory) / "reports")
            (bundle / "raw-events.jsonl").write_text("{}\n", encoding="utf-8")
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["raw-events.jsonl"] = hashlib.sha256((bundle / "raw-events.jsonl").read_bytes()).hexdigest()
            manifest_path.write_bytes(collect.canonical(manifest) + b"\n")
            with self.assertRaisesRegex(ValueError, "raw event stream"):
                adapter.adapt(bundle)


def _write_publication(root, item, files):
    target = root / "publication"
    target.mkdir()
    for name, content in files.items():
        (target / name).write_bytes(content)
    return target


if __name__ == "__main__":
    unittest.main()

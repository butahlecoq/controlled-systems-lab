"""SYN-02 registered Pages adapter boundary tests."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
sys.path.insert(0, str(ROOT / "reports" / "algorithm-results" / "tooling" / "syn02"))
import registered_reports
import report_data
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

publication_map = _load_module("csl_syn02_test_publication_map", ROOT / "reports/algorithm-results/tooling/syn02/publication_map.py")
sys.modules["publication_map"] = publication_map
collect = _load_module("csl_syn02_test_collect", ROOT / "reports/algorithm-results/tooling/syn02/collect.py")
SITE_SPEC = importlib.util.spec_from_file_location("csl_syn02_test_site", ROOT / "scripts" / "reports" / "site.py")
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)
import syn02_registered_reports as syn02

SOURCE = "c234a1a04b2f90e34776a2bfa349a91a1d30257d"
HARNESS = "985c5e88916383e2e98464744ee685fd71b6cd4e"
TRIAL_FIELDS = ["scenario", "repetition", "status", "validation_errors", "outcome", "termination", "relation",
                "optimization_present", "optimum_present", "provider", "primal_value", "lower_bound", "upper_bound",
                "prepare_ns", "solve_ns", "oracle_ns", "execute_ns", "solver_observations"]


def make_event(name, repetition, attempt):
    spec = collect.SCENARIOS[name]
    failure = name == "shifted-residual-degenerate"
    diagnostics = ("phase.qp.model_status=7\noptimality.withheld=original-space checks unavailable or failing\ncheck.stationarity.violation=1\n"
                   if failure else "native.primal_infeasibility=0\nnative.dual_infeasibility=0\n" if spec["provider"] == "csl.lp.highs"
                   else "check.rows.violation=0\ncheck.variables.violation=0\ncheck.stationarity.violation=0\n")
    observations = ({"phase.qp.model_status": 7, "optimality.withheld": "original-space checks unavailable or failing",
                     "check.stationarity.violation": 1} if failure else
                    {"native.primal_infeasibility": 0, "native.dual_infeasibility": 0} if spec["provider"] == "csl.lp.highs" else
                    {"check.rows.violation": 0, "check.variables.violation": 0, "check.stationarity.violation": 0})
    warmup = repetition == 0
    return {"schema": "csl.syn02-terminal-trial/1", "scenario": name, "repetition": repetition, "warmup": warmup,
            "status": "passed", "expected_outcome": spec["outcome"], "expected_termination": spec["termination"],
            "expected_provider": spec["provider"], "outcome": spec["outcome"], "termination": spec["termination"],
            "relation": not failure, "optimization_present": True, "optimum_present": True,
            "provider": spec["provider"], "relation_support": "unestablished", "optimum_support": "unestablished",
            "raw_diagnostics": diagnostics, "solver_observations": observations,
            "primal_value": 0.5 if failure else spec["value"], "lower_bound": None, "upper_bound": None,
            "inequalities": [[1, 0], [-1, 0], [0, 1], [0, -1]], "upper_bounds": [1, 0, 1, 0],
            "equalities": [] if failure else [[1, 0]], "equality_values": [] if failure else [0],
            "prepare_ns": 100 + repetition, "solve_ns": 200 + repetition, "oracle_ns": 10,
            "execute_ns": 350 + repetition, "attempt_index": attempt, "source_commit": SOURCE,
            "harness_commit": HARNESS,
            "scenario_hash": collect.sha(collect.canonical({"scenario": spec, "terminal_slice": collect.UNIT_BOX})),
            "trial_id": f"{SOURCE[:8]}-{HARNESS[:8]}-{name}-{repetition}",
            "validation_errors": []}


def _csv_value(value):
    return json.dumps(value, separators=(",", ":")) if isinstance(value, list) else value


class Syn02PublicationTests(unittest.TestCase):
    def make_bundle(self, root):
        root.mkdir(parents=True, exist_ok=True)
        source_id = "syn02-terminal-20261013-c234a1a0-1755dd198e03"
        bundle = root / source_id
        bundle.mkdir()
        rows = []
        for round_index in range(8):
            names = list(collect.SCENARIOS)
            if round_index % 2:
                names.reverse()
            rows.extend(make_event(name, round_index, len(rows) + 1) for name in names)
        summary = collect.summarize(rows)
        record = {"schema": "csl.syn02-terminal-report/1", "report_id": source_id, "source_commit": SOURCE,
                  "harness_commit": HARNESS, "scenario_catalog": collect.SCENARIOS,
                  "terminal_slice": collect.UNIT_BOX,
                  "scenario_hashes": {name: collect.sha(collect.canonical({"scenario": spec, "terminal_slice": collect.UNIT_BOX}))
                                      for name, spec in collect.SCENARIOS.items()},
                  "measurement": {"kind": "descriptive_single_adapter", "scope": "Terminal optimizer on resolved objectives and a supplied terminal H-slice; not system simulation or complete control synthesis",
                                  "repetitions": 7, "warmups_per_scenario": 1, "driver_exit_code": 0},
                  "attempt_counts": {"measured": 35, "matched_expected": 35, "failed": 0, "non_success": 7, "missing": 0},
                  "summary": summary, "evidence_limits": ["binary64 literal fixture checks, not exact or validated arithmetic",
                      "relation samples do not certify full set equality", "global optimum and relation support remain Unestablished",
                      "shifted residual case returns undetermined with numerical_failure and no constructed relation",
                      "tiny analytic fixtures only; no comparator, speedup, application-scale, throughput, or scalability claim",
                      "limiter unknown because no call-stack profile evidence was collected"],
                  "profile_summary": "Separate process CPU/RSS counter sampling is incomplete; limiter unknown. WPR CPU stack capture unavailable.",
                  "environment": {"os": "Windows test fixture", "processor": "fixture"},
                  "provenance": {"schema": "csl.syn02-build-provenance/1", "source_commit": SOURCE,
                                 "harness_commit": HARNESS, "compiler": "MSVC test fixture"}}
        payload_bytes = (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        (bundle / "records.json").write_bytes(payload_bytes)
        (bundle / "raw-events.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        (bundle / "trials.csv").write_bytes(collect.trials_csv_bytes(rows))
        (bundle / "summary.csv").write_bytes(collect.summary_csv_bytes(summary))
        (bundle / "latency.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><title>Latency</title><path d="M0 0L10 10"/></svg>', encoding="utf-8")
        (bundle / "index.html").write_text("<!doctype html><html><body>SYN-02 saved report</body></html>", encoding="utf-8")
        (bundle / "environment.json").write_text(json.dumps(record["environment"], sort_keys=True) + "\n", encoding="utf-8")
        (bundle / "build-provenance.json").write_text(json.dumps(record["provenance"], sort_keys=True) + "\n", encoding="utf-8")
        (bundle / "profile-evidence.json").write_text(json.dumps({"status": "process_counter_sampling_incomplete"}, sort_keys=True) + "\n", encoding="utf-8")
        content = {"README.md": b"fixture", "build-log.txt": b"Release build fixture", "collect.py": b"collector fixture",
                   "configure-log.txt": b"configure fixture", "etw-profile-attempt.txt": b"unavailable",
                   "measurement-command.txt": b"fixture command", "profile-note.txt": b"limiter unknown",
                   "profile-raw.jsonl": b"profile fixture\n", "publication_map.py": b"publication mapping fixture",
                   "render_saved.py": b"renderer fixture",
                   "terminal_driver.cpp": b"driver fixture", "test_report.py": b"test fixture"}
        for name, data in content.items():
            (bundle / name).write_bytes(data)
        (bundle / "publication-map.json").write_text(json.dumps(publication_map.project(record), ensure_ascii=False,
                                                                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
        source_names = (set(publication_map.STAGED_SOURCE_FILES) - {"manifest.json"}) | {"index.html"}
        manifest = {"schema": "csl.syn02-report-manifest/1", "report_id": source_id,
                    "source_commit": SOURCE, "harness_commit": HARNESS,
                    "files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(source_names)}}
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return bundle

    def test_valid_bundle_stages_registered_page_envelope_manifest_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "reports"
            bundle = self.make_bundle(root)
            shutil.copyfile(ROOT / "reports" / "algorithm-results" / "legacy-publications.json", root / "legacy-publications.json")
            item = syn02.adapt(bundle)
            self.assertEqual("syn02-terminal-minimizers", item.kind)
            self.assertEqual(bundle.name, item.source_report_id)
            source_root = ROOT / "reports" / "algorithm-results"
            original_catalogue = json.loads((source_root / "catalog.json").read_text(encoding="utf-8"))
            pins = json.loads((source_root / "legacy-publications.json").read_text(encoding="utf-8"))["reports"]
            retained = []
            for row in original_catalogue["reports"]:
                source_id = row.get("source_report_id")
                if source_id not in pins:
                    continue
                shutil.copytree(source_root / source_id, root / source_id)
                for suffix in (".source.zip", ".zip"):
                    shutil.copyfile(source_root / (source_id + suffix), root / (source_id + suffix))
                retained.append(row)
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main", "reports": [*retained, {
                "report_id": item.report_id, "report_kind": item.kind, "source_report_id": item.source_report_id,
                "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
                "source_commit": item.source_commit, "measured_scope": item.measured_scope,
                "evidence_limits": item.evidence_limits, "payload_schema": item.payload_schema,
                "zip_sha256": hashlib.sha256(syn02.offline_zip(bundle, item)).hexdigest()}]}
            local_catalogue_files = {path for row in catalogue["reports"] for path in
                (row["report_id"] + "/index.html", row["report_id"] + "/records.json",
                 row["report_id"] + "/trials.csv", row["report_id"] + ".zip")}
            report_site.OfflineHTML(local_catalogue_files).feed(report_site.catalogue_index(catalogue))
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalogue), encoding="utf-8")
            output = root / "staged"
            report_site.stage(catalog_path, output, check=False)
            self.assertTrue((output / item.report_id / "report-envelope.json").is_file())
            self.assertTrue((output / item.report_id / "publication-manifest.json").is_file())
            self.assertEqual(syn02.offline_zip(bundle, item), (output / (item.report_id + ".zip")).read_bytes())
            expected = {key: catalogue["reports"][-1][key] for key in ("report_id", "report_kind", "payload_schema", "payload_sha256",
                        "native_payload_sha256", "source_commit", "measured_scope", "evidence_limits", "source_report_id")}
            self.assertTrue(syn02.validate_publication_manifest(output / item.report_id, expected))

    def test_generated_latency_svg_passes_pages_safety_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
            report_data.validate_svg(collect.svg(record["summary"]).encode("utf-8"))

    def _rehash_native_manifest(self, bundle):
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"] = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(manifest["files"])}
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
        (bundle / "publication-map.json").write_text(json.dumps(publication_map.project(record), ensure_ascii=False,
                                                                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
        manifest["files"]["publication-map.json"] = hashlib.sha256((bundle / "publication-map.json").read_bytes()).hexdigest()
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def test_rejects_native_hash_and_unlisted_inventory_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self.make_bundle(root / "hash")
            (bundle / "latency.svg").write_text("<svg/>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                syn02.adapt(bundle)
            bundle2 = self.make_bundle(root / "inventory")
            (bundle2 / "unlisted.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inventory"):
                syn02.adapt(bundle2)

    def test_rejects_raw_csv_and_summary_mismatch_even_after_native_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            csv_path = bundle / "trials.csv"
            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertIn("shifted-residual-degenerate,1,passed", csv_text)
            csv_path.write_text(csv_text.replace("shifted-residual-degenerate,1,passed", "shifted-residual-degenerate,1,forged", 1), encoding="utf-8")
            self._rehash_native_manifest(bundle)
            with self.assertRaisesRegex(ValueError, "CSV"):
                syn02.adapt(bundle)

    def test_rejects_semantically_equivalent_noncanonical_trial_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            path = bundle / "trials.csv"
            original = path.read_bytes()
            noncanonical = original.replace(b"\n", b"\r\n")
            self.assertNotEqual(original, noncanonical)
            path.write_bytes(noncanonical)
            self._rehash_native_manifest(bundle)
            with self.assertRaisesRegex(ValueError, "CSV"):
                syn02.adapt(bundle)

    def test_rejects_duplicate_keys_in_raw_event_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            path = bundle / "raw-events.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            lines[0] = lines[0][:-1] + ', "scenario": "linear-face"}'
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._rehash_native_manifest(bundle)
            with self.assertRaisesRegex(ValueError, "duplicate JSON key.*scenario"):
                syn02.adapt(bundle)

    def test_rejects_missing_summary_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            (bundle / "summary.csv").unlink()
            with self.assertRaisesRegex(ValueError, "inventory|summary"):
                syn02.adapt(bundle)

    def test_rejects_summary_csv_mismatch_even_after_native_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            path = bundle / "summary.csv"
            contents = path.read_text(encoding="utf-8")
            path.write_text(contents.replace("linear-face", "forged-face", 1), encoding="utf-8")
            self._rehash_native_manifest(bundle)
            with self.assertRaisesRegex(ValueError, "summary.csv"):
                syn02.adapt(bundle)

    def test_accepts_completed_profile_with_explicit_unknown_limiter(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            record_path = bundle / "records.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["profile_summary"] = "Separate process CPU/RSS counter sampling completed; no call-stack attribution. WPR CPU stack capture unavailable; limiting source function remains unknown."
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (bundle / "publication-map.json").write_text(json.dumps(publication_map.project(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rehash_native_manifest(bundle)
            self.assertEqual(bundle.name, syn02.adapt(bundle).source_report_id)
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory))
            record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
            record["summary"][0]["failed"] += 1
            (bundle / "records.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rehash_native_manifest(bundle)
            with self.assertRaisesRegex(ValueError, "summary"):
                syn02.adapt(bundle)

    def test_rejects_unsafe_svg_and_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory) / "svg")
            (bundle / "latency.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', encoding="utf-8")
            self._rehash_native_manifest(bundle)
            with self.assertRaises(ValueError):
                syn02.adapt(bundle)
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.make_bundle(Path(directory) / "identity")
            record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
            record["report_id"] = "../unsafe"
            (bundle / "records.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity"):
                syn02.adapt(bundle)


if __name__ == "__main__":
    unittest.main()

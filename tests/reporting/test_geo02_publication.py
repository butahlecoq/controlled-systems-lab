"""GEO-02 publication boundary regression tests."""
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
import geo02_registered_reports as geo02
SITE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reports" / "site.py"
SITE_SPEC = importlib.util.spec_from_file_location("csl_geo02_test_site", SITE_PATH)
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "geo02"))
import collect
RENDER_PATH = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "geo02" / "render.py"
RENDER_SPEC = importlib.util.spec_from_file_location("csl_geo02_test_renderer", RENDER_PATH)
geo02_renderer = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(geo02_renderer)


def fixture_record():
    record = collect.fixture_payload("20261013T120000Z")
    record["algorithm"].update(source_commit="a" * 40, harness_commit="b" * 40)
    record["evidence"].update(limiter_profile="not collected; no OS limiter/CPU sampling available",
                               unavailable_counters=["per-trial CPU time", "internal LP timings"])
    for trial in record["trials"]:
        case = collect.SCENARIOS[trial["scenario"]]
        trial["input_sha256"] = collect.sha(collect.canonical(case["inputs"]))
    return collect.finalize(record, "20261013T120000Z")


class Geo02PublicationTests(unittest.TestCase):
    def make_bundle(self, root):
        record = fixture_record()
        record["collection"].update(process_return_code=0, aborted_or_timed_out=False, parse_error=None)
        bundle = root / record["report_id"]
        bundle.mkdir()
        (bundle / "records.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (bundle / "scenarios.json").write_text(json.dumps(record["expected"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (bundle / "raw-events.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in record["trials"]), encoding="utf-8")
        with (bundle / "raw-driver-output.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=collect.FIELDS)
            writer.writeheader()
            for trial in record["trials"]:
                writer.writerow({key: json.dumps(trial[key], separators=(",", ":")) if key in ("output_points", "support_values") else str(trial[key]).lower() if isinstance(trial[key], bool) else trial[key] for key in collect.FIELDS})
        with (bundle / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            fields = ["scenario", "phase", "unit", "median", "min", "max", "range", "successful_trials", "trials_excluded_from_summary"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for scenario, summary in record["summary"].items():
                for phase, values in summary["phases"].items():
                    writer.writerow({"scenario": scenario, "phase": phase, **values})
        status = {key: record["collection"][key] for key in ("state", "expected_trials", "actual_trials", "failures", "warmups_per_scenario", "warmup_results", "warmup_failures", "warmup_parse_error", "process_return_code", "aborted_or_timed_out", "parse_error")}
        (bundle / "collection-status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        (bundle / "profile-evidence.txt").write_text("OS limiter profiling not collected.\n", encoding="utf-8")
        for name in ("build-provenance.txt", "measurement-command.txt", "environment.json", "process-stderr.txt", "concurrent-work.txt"):
            (bundle / name).write_text("synthetic deterministic fixture\n", encoding="utf-8")
        (bundle / "index.html").write_text(geo02_renderer.render_html(record), encoding="utf-8")
        (bundle / "timings.svg").write_text(geo02_renderer.render_svg(record), encoding="utf-8")
        files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(bundle.iterdir())}
        manifest = {"schema": "csl.geo02-bundle/1", "report_id": record["report_id"], "files": files}
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(root / (bundle.name + ".zip"), "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.iterdir()):
                archive.writestr(path.name, path.read_bytes())
        return bundle

    def test_payload_adapter_requires_explicit_limited_claims_and_unapplied_reduction(self):
        record = fixture_record()
        item = geo02.adapt_payload(record)
        self.assertEqual(item.kind, "geo02-affine-sum")
        self.assertEqual(item.payload_schema, geo02.SCHEMA)
        self.assertIn("Full candidate cloud retained", item.evidence_limits)
        broken = copy.deepcopy(record)
        broken["evidence"]["limitations"][-1] = "candidate deletion applied"
        broken = collect.finalize(broken, "20261013T120000Z")
        with self.assertRaisesRegex(ValueError, "reduction"):
            geo02.adapt_payload(broken)

    def test_source_identity_is_digest_bound(self):
        record = fixture_record()
        record["report_id"] = "geo02-20261013T120000Z-000000000000"
        with self.assertRaises(ValueError):
            geo02.adapt_payload(record)

    def test_trial_timing_and_oracle_status_are_checked(self):
        record = fixture_record()
        # Total trial time also covers timer gaps and per-trial harness overhead.
        record["trials"][0]["total_ns"] += 1
        record["summary"] = collect.summarize(record["trials"])
        record = collect.finalize(record, "20261013T120000Z")
        self.assertEqual(geo02.adapt_payload(record).kind, "geo02-affine-sum")

        record["trials"][0]["total_ns"] = 5
        record["summary"] = collect.summarize(record["trials"])
        record = collect.finalize(record, "20261013T120000Z")
        with self.assertRaises(ValueError):
            geo02.adapt_payload(record)

    def test_complete_collection_metadata_must_match_successful_trials(self):
        for key, value in (("expected_trials", 27), ("process_return_code", 2),
                           ("aborted_or_timed_out", True), ("parse_error", "truncated CSV")):
            with self.subTest(key=key):
                record = fixture_record()
                record["collection"][key] = value
                record = collect.finalize(record, "20261013T120000Z")
                with self.assertRaises(ValueError):
                    geo02.adapt_payload(record)

    def test_failed_warmup_blocks_complete_publication(self):
        record = fixture_record()
        record["collection"]["warmup_results"][0]["oracle_passed"] = False
        record = collect.finalize(record, "20261013T120000Z")
        with self.assertRaisesRegex(ValueError, "invalid GEO-02 report payload"):
            geo02.adapt_payload(record)

    def test_complete_bundle_round_trips_through_offline_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = self.make_bundle(Path(temp))
            item = geo02.adapt(bundle)
            self.assertEqual(item.kind, "geo02-affine-sum")
            self.assertEqual(item, geo02.adapt(bundle))
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main", "reports": [{
                "report_id": item.report_id, "report_kind": item.kind, "source_report_id": item.source_report_id,
                "payload_sha256": item.payload_sha256, "source_commit": item.source_commit,
                "measured_scope": item.measured_scope, "evidence_limits": item.evidence_limits,
                "payload_schema": item.payload_schema, "zip_sha256": hashlib.sha256(geo02.offline_zip(bundle, item)).hexdigest()}]}
            index = report_site.catalogue_index(catalogue)
            self.assertIn(item.report_id + "/raw-driver-output.csv", index)
            self.assertIn(item.report_id + ".zip", index)
            artifacts = geo02.publication_artifacts(bundle, item)
            report_site.OfflineHTML(set(artifacts)).feed(artifacts["index.html"].decode("utf-8"))
            output = Path(temp) / "published"
            output.mkdir()
            for name, content in artifacts.items():
                (output / name).write_bytes(content)
            expected = {"report_id": item.report_id, "report_kind": item.kind,
                        "payload_schema": item.payload_schema, "payload_sha256": item.payload_sha256,
                        "source_commit": item.source_commit, "measured_scope": item.measured_scope,
                        "evidence_limits": item.evidence_limits, "native_payload_sha256": item.native_payload_sha256,
                        "source_report_id": item.source_report_id}
            self.assertTrue(geo02.validate_publication_manifest(output, expected))
            self.assertEqual(geo02.offline_zip(bundle, item), geo02.offline_zip(bundle, item))


if __name__ == "__main__":
    unittest.main()

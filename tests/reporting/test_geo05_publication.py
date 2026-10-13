"""Publication boundary tests for the GEO-05 native measurement record."""
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
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
import geo05_registered_reports as geo05
SITE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reports" / "site.py"
SITE_SPEC = importlib.util.spec_from_file_location("csl_geo05_report_site", SITE_PATH)
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)


SCENARIOS = ("singular_a", "unreachable_equality_target", "integrator_predecessor", "v_projection_preserves_ray")
PHASES = ("preparation_ns", "workspace_ns", "run_ns", "verification_ns", "end_to_end_ns")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def reseal(saved):
    unsigned = {key: value for key, value in saved.items() if key not in ("report_id", "payload_sha256")}
    digest = hashlib.sha256(canonical(unsigned)).hexdigest()
    saved["payload_sha256"] = digest
    saved["report_id"] = "geo05-" + digest[:16]


def record(purpose="measurement", failed=False, missing=False, failure_context=False, raw_stdout=""):
    trials = []
    for repetition in range(7):
        for scenario in geo05._scenario_order(repetition):
            status = "failed" if failed and scenario == "integrator_predecessor" and repetition == 0 else "passed"
            trials.append({
                "purpose": "measurement", "scenario": scenario, "repetition": repetition, "status": status,
                "oracle_scope": "numeric_literal_samples", "oracle_passed": status == "passed",
                "work_observed": True, "max_rows": None if scenario == "v_projection_preserves_ray" else 128,
                "input_rows": geo05.ORACLES[scenario]["input_rows"],
                "output_rows": geo05.ORACLES[scenario]["output_rows"] if status == "passed" else None,
                "expected_fm_peak_rows": geo05.ORACLES[scenario].get("expected_fm_peak_rows"),
                "result_kind": geo05.ORACLES[scenario]["result_kind"] if status == "passed" else None,
                "result_encoding": ("h_contradiction_row" if scenario == "unreachable_equality_target" else ("v_generators" if scenario == "v_projection_preserves_ray" else "h_rows")) if status == "passed" else None,
                "input_sha256": hashlib.sha256(canonical(geo05.ORACLES[scenario]["inputs"])).hexdigest(),
                "scenario_sha256": hashlib.sha256(canonical(geo05.ORACLES[scenario])).hexdigest(),
                "detail": "<script>alert(1)</script>",
                "durations_ns": {phase: None if phase == "workspace_ns" and scenario != "v_projection_preserves_ray" else 10 for phase in PHASES},
            })
            if failure_context:
                trials[-1]["predecessor_failure"] = (
                    {"phase": "run", "code": "unsupported"}
                    if status == "failed" and scenario == "integrator_predecessor" else None)
                trials[-1]["end_to_end_scope"] = "through_verification_and_fixture_teardown"
    if missing:
        trials.pop()
    warmups = [{"scenario": scenario, "repetition": 0, "purpose": "warmup", "status": "passed",
                "oracle_scope": "numeric_literal_samples", "oracle_passed": True, "work_observed": True,
                "max_rows": None if scenario == "v_projection_preserves_ray" else 128,
                "input_rows": geo05.ORACLES[scenario]["input_rows"],
                "output_rows": geo05.ORACLES[scenario]["output_rows"],
                "expected_fm_peak_rows": geo05.ORACLES[scenario].get("expected_fm_peak_rows"),
                "result_kind": geo05.ORACLES[scenario]["result_kind"],
                "result_encoding": "h_contradiction_row" if scenario == "unreachable_equality_target" else ("v_generators" if scenario == "v_projection_preserves_ray" else "h_rows"),
                "input_sha256": hashlib.sha256(canonical(geo05.ORACLES[scenario]["inputs"])).hexdigest(),
                "scenario_sha256": hashlib.sha256(canonical(geo05.ORACLES[scenario])).hexdigest(),
                "durations_ns": {phase: None if phase == "workspace_ns" and scenario != "v_projection_preserves_ray" else 10 for phase in PHASES}}
               for scenario in SCENARIOS]
    if failure_context:
        for row in warmups:
            row["end_to_end_scope"] = "through_verification_and_fixture_teardown"
    counts = {name: 0 for name in ("passed", "failed", "unsupported", "cancelled", "missing")}
    counts["passed"] = len(trials) + len(warmups) - (1 if failed else 0)
    counts["failed"] = 1 if failed else 0
    counts["missing"] = 28 - len(trials)
    invalid = failed or missing
    phases = {}
    for phase in PHASES:
        values = [row["durations_ns"][phase] for row in trials if row["status"] == "passed"
                  and row["oracle_passed"] is True and type(row["durations_ns"].get(phase)) is int]
        phases[phase] = {"median_ns": None if invalid or not values else 10,
                         "min_ns": None if invalid or not values else 10,
                         "max_ns": None if invalid or not values else 10,
                         "successful_trials": len(values), "unavailable_trials": len(trials) - len(values),
                         "trials_excluded": len(values) if invalid else 0}
    def stats(group):
        values_by_phase = {}
        for phase in PHASES:
            values = [row["durations_ns"].get(phase) for row in group if row["status"] == "passed"
                      and row["oracle_passed"] is True and type(row["durations_ns"].get(phase)) is int]
            values_by_phase[phase] = {"median_ns": None if invalid or not values else 10,
                "min_ns": None if invalid or not values else 10, "max_ns": None if invalid or not values else 10,
                "successful_trials": len(values), "unavailable_trials": len(group) - len(values),
                "trials_excluded": len(values) if invalid else 0}
        return values_by_phase
    process_exit_code = 0
    algorithm = {"id": "GEO-05", "source_commit": "a" * 40, "harness_commit": "b" * 40,
                 "raw_stdout_sha256": hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest(),
                 "raw_stderr_sha256": hashlib.sha256(b"").hexdigest()}
    if process_exit_code:
        algorithm["process_exit_code"] = process_exit_code
    unsigned = {
        "schema": "csl.geo05-numerical-report/1", "purpose": purpose,
        "algorithm": algorithm,
        "catalog": {"version": "geo05-analytic-v1", "scenarios": list(SCENARIOS), "oracles": geo05.ORACLES},
        "collection": {"measured_repetitions": 7, "warmups_per_scenario": 1,
                       "expected_trials": 28, "expected_warmup_trials": 4, "actual_warmup_trials": 4,
                       "counts": counts, "valid_success_summary": not invalid,
                       "process_return_code": process_exit_code, "parse_errors": 0, "timed_out": False, "phases": phases,
                       "by_scenario": {scenario: {"attempts": sum(row["scenario"] == scenario for row in trials),
                                                   "phases": stats([row for row in trials if row["scenario"] == scenario])}
                                       for scenario in SCENARIOS}},
        "trials": trials, "warmup_trials": warmups,
        "evidence_limits": ["numeric sample checks only", "H relation support Unestablished",
                            "no exact set equality or validated arithmetic claim"],
    }
    digest = hashlib.sha256(canonical(unsigned)).hexdigest()
    return {**unsigned, "payload_sha256": digest, "report_id": "geo05-" + digest[:16]}


def create_bundle(root, saved):
    bundle = root / saved["report_id"]
    bundle.mkdir()
    (bundle / "records.json").write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    (bundle / "provenance.json").write_text(json.dumps({key: value for key, value in saved["algorithm"].items()
                                                            if key != "id"}) + "\n", encoding="utf-8")
    (bundle / "command.json").write_text('["driver", "--measure", "--repetitions", "7", "--warmups", "1"]\n', encoding="utf-8")
    (bundle / "parse-errors.json").write_text("[]\n", encoding="utf-8")
    (bundle / "stderr.txt").write_text("", encoding="utf-8")
    (bundle / "stdout.jsonl").write_text("", encoding="utf-8")
    rows = [*saved["warmup_trials"], *saved["trials"]]
    with (bundle / "trials.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    modern_fields = any("predecessor_failure" in row for row in rows)
    fields = (("purpose", "scenario", "repetition", "status", "detail", "predecessor_failure",
               "oracle_passed", "work_observed", "end_to_end_scope", "max_rows", "input_rows",
               "output_rows", "result_kind", "result_encoding", "input_sha256", "scenario_sha256",
               "expected_fm_peak_rows", *PHASES) if modern_fields else
              ("purpose", "scenario", "repetition", "status", "detail", "oracle_passed", "work_observed",
               "max_rows", "input_rows", "output_rows", "result_kind", "result_encoding", "input_sha256",
               "scenario_sha256", "expected_fm_peak_rows", *PHASES))
    with (bundle / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {**row, **row["durations_ns"]}
            if "predecessor_failure" in fields and flat.get("predecessor_failure") is not None:
                flat["predecessor_failure"] = json.dumps(flat["predecessor_failure"], sort_keys=True, allow_nan=False)
            elif "predecessor_failure" in fields:
                flat["predecessor_failure"] = ""
            writer.writerow(flat)
    (bundle / "index.html").write_text("<!doctype html><html lang=\"en\"><body>untrusted source HTML</body></html>", encoding="utf-8")
    inventory = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in bundle.iterdir() if path.is_file()}
    manifest = {"schema": "csl.geo05-report-files/1", "files": inventory}
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(root / (bundle.name + ".zip"), "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(bundle.iterdir()):
            archive.write(path, arcname=path.name)
    return bundle


def reseal_source_bundle(bundle):
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in bundle.iterdir() if path.is_file() and path.name != "manifest.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rewrite_source_zip(bundle)


def rewrite_source_zip(bundle):
    with zipfile.ZipFile(bundle.parent / (bundle.name + ".zip"), "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(bundle.iterdir()):
            archive.write(path, arcname=path.name)


class Geo05PublicationTests(unittest.TestCase):
    def test_duplicate_keys_in_native_record_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), record())
            source = (bundle / "records.json").read_text(encoding="utf-8")
            source = source.replace('"schema":', '"schema":"shadow", "schema":', 1)
            (bundle / "records.json").write_text(source, encoding="utf-8")
            reseal_source_bundle(bundle)
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                geo05.adapt(bundle)

    def test_duplicate_keys_in_each_trial_jsonl_object_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), record())
            lines = (bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()
            lines = [line.replace('"scenario":', '"scenario":"shadow", "scenario":', 1) for line in lines]
            (bundle / "trials.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            reseal_source_bundle(bundle)
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                geo05.adapt(bundle)

    def test_duplicate_keys_are_rejected_in_every_json_sidecar(self):
        duplicate_payloads = {
            "records.json": lambda text: text.replace('"schema":', '"schema":"shadow", "schema":', 1),
            "manifest.json": lambda text: text.replace('"schema":', '"schema":"shadow", "schema":', 1),
            "provenance.json": lambda text: text.replace('"source_commit":', '"source_commit":"shadow", "source_commit":', 1),
            "command.json": lambda _text: '{"duplicate": 1, "duplicate": 2}',
            "parse-errors.json": lambda _text: '[{"duplicate": 1, "duplicate": 2}]',
        }
        for filename, mutate in duplicate_payloads.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                bundle = create_bundle(Path(temp), record())
                path = bundle / filename
                if filename == "manifest.json":
                    reseal_source_bundle(bundle)
                path.write_text(mutate(path.read_text(encoding="utf-8")), encoding="utf-8")
                if filename == "manifest.json":
                    rewrite_source_zip(bundle)
                else:
                    reseal_source_bundle(bundle)
                with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                    geo05.adapt(bundle)

    def test_surplus_trials_csv_field_is_rejected_after_bundle_reseal(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), record())
            csv_path = bundle / "trials.csv"
            lines = csv_path.read_text(encoding="utf-8").splitlines()
            lines[1] += ",unregistered-extra-value"
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            reseal_source_bundle(bundle)
            with self.assertRaisesRegex(ValueError, "trials.csv"):
                geo05.adapt(bundle)

    def test_measurement_adapter_preserves_attempts_and_identity(self):
        saved = record(failed=True)
        publication = geo05.adapt_payload(saved)
        self.assertEqual(publication.kind, "geo05-projection-predecessor")
        self.assertEqual(publication.source_report_id, saved["report_id"])
        self.assertEqual(publication.payload_schema, "csl.geo05-numerical-report/1")
        self.assertIn('"failed": 1', publication.evidence_limits)
        self.assertIn("no exact set equality", publication.evidence_limits)

    def test_failure_context_csv_shape_is_accepted_and_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), record(failed=True, failure_context=True))
            publication = geo05.adapt(bundle)
            self.assertEqual(publication.source_report_id, bundle.name)
            with (bundle / "trials.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            failed = next(row for row in rows if row["scenario"] == "integrator_predecessor" and row["status"] == "failed")
            self.assertEqual(json.loads(failed["predecessor_failure"]), {"code": "unsupported", "phase": "run"})

    def test_failure_context_csv_must_match_saved_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), record(failed=True, failure_context=True))
            csv_path = bundle / "trials.csv"
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            failure_column = rows[0].index("predecessor_failure")
            failed_row = next(row for row in rows[1:] if row[3] == "failed")
            failed_row[failure_column] = '{"phase":"different"}'
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            reseal_source_bundle(bundle)
            with self.assertRaisesRegex(ValueError, "trials.csv differs"):
                geo05.adapt(bundle)

    def test_raw_process_text_accepts_windows_newline_translation(self):
        with tempfile.TemporaryDirectory() as temp:
            saved = record(raw_stdout='{"event":"capture"}\n')
            bundle = create_bundle(Path(temp), saved)
            (bundle / "stdout.jsonl").write_bytes(b'{"event":"capture"}\r\n')
            reseal_source_bundle(bundle)
            self.assertEqual(geo05.adapt(bundle).source_report_id, bundle.name)

    def test_current_end_to_end_scope_is_required_to_match_the_registered_contract(self):
        saved = record(failure_context=True)
        saved["trials"][0]["end_to_end_scope"] = "execution-only"
        reseal(saved)
        with self.assertRaisesRegex(ValueError, "end-to-end scope"):
            geo05.adapt_payload(saved)

    def test_test_and_smoke_records_cannot_enter_publication(self):
        for purpose in ("test", "smoke"):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                geo05.adapt_payload(record(purpose=purpose))

    def test_missing_attempts_remain_reportable_but_inconclusive(self):
        saved = record(missing=True)
        publication = geo05.adapt_payload(saved)
        self.assertIn('"missing": 1', publication.evidence_limits)
        self.assertIn("INCOMPLETE / INCONCLUSIVE", publication.evidence_limits)
        self.assertIn('"median_ns": null', json.dumps(saved["collection"]["phases"]))
        with tempfile.TemporaryDirectory() as temp:
            bundle = create_bundle(Path(temp), saved)
            page = geo05.render_page(bundle, geo05.adapt(bundle))
            summary = page.split("<h2>Phase summaries (ns)</h2>", 1)[1].split("<h2>Native evidence limits</h2>", 1)[0]
            self.assertIn("INCOMPLETE / INCONCLUSIVE", page)
            self.assertNotIn("<td>10</td>", summary)

    def test_payload_digest_tampering_is_rejected(self):
        saved = copy.deepcopy(record())
        saved["trials"][0]["durations_ns"]["run_ns"] = 999
        with self.assertRaisesRegex(ValueError, "digest"):
            geo05.adapt_payload(saved)

    def test_bundle_adapter_verifies_inventory_and_renders_escaped_saved_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            saved = record(failed=True)
            bundle = create_bundle(root, saved)

            publication = geo05.adapt(bundle)
            artifacts = geo05.publication_artifacts(bundle, publication)
            page = artifacts["index.html"].decode("utf-8")
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
            self.assertNotIn("untrusted source HTML", page)
            self.assertIn("failed", page)
            self.assertEqual(publication.report_id, geo05.adapt(bundle).report_id)

            (bundle / "stderr.txt").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                geo05.adapt(bundle)

    def test_site_stages_geo05_through_registered_envelope(self):
        source = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "reports"
            shutil.copytree(source, root)
            saved = record()
            bundle = create_bundle(root, saved)
            publication = geo05.adapt(bundle)
            archive = geo05.offline_zip(bundle, publication)
            (root / (publication.report_id + ".zip")).write_bytes(archive)
            catalogue = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
            catalogue["reports"].append({"report_id": publication.report_id, "report_kind": publication.kind,
                "source_report_id": publication.source_report_id, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
                "zip_sha256": hashlib.sha256(archive).hexdigest()})
            (root / "catalog.json").write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
            (root / "index.html").write_text(report_site.catalogue_index(catalogue), encoding="utf-8")
            staged = report_site.stage(root / "catalog.json", Path(temp) / "stage", check=True)
            page = (staged / publication.report_id / "index.html").read_text(encoding="utf-8")
            envelope = json.loads((staged / publication.report_id / "report-envelope.json").read_text(encoding="utf-8"))
            self.assertIn("GEO-05 measurement report", page)
            self.assertEqual(envelope["payload_schema"], "csl.geo05-numerical-report/1")
            self.assertIn("trials.csv", page)


if __name__ == "__main__":
    unittest.main()

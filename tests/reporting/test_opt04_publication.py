"""Synthetic saved evidence exercises the publisher; this is not a measurement."""
import copy
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "reports/algorithm-results/tooling/opt04"
sys.path.insert(0, str(ROOT / "scripts/reports"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native_tests = load("opt04_fixture_tools", TOOLS / "test_report_tools.py")
collector = load("opt04_fixture_collector", TOOLS / "collect.py")
renderer = native_tests.render
report_site = load("opt04_test_site", ROOT / "scripts/reports/site.py")


def make_records():
    # Test-only expansion of the native tool's one-fixture record to its five
    # analytic inputs. Durations and provenance here are synthetic literals.
    record = native_tests.fixture_records()
    record["report_id"] = "opt04-20261013T000000Z-123456789abc"
    record["purpose"] = "test"
    record["evidence_limits"] = ["Synthetic test evidence; never publish this fixture."]
    record["catalog"]["fixtures"] = []
    record["warmup_trials"] = []
    record["trials"] = []
    record["measurement"]["execution_order"] = []
    record["measurement"]["timing_boundaries"] = {
        "setup": "program publication, registration, selection, preparation and fresh workspace creation",
        "public_run": "BoundWorkspace.run",
        "verification": "independent expected outcome, candidate, equality residual and nonnegativity checks",
        "end_to_end": "fixture construction through independent verification; excludes process startup and serialization"}
    raw = []
    base = native_tests.fixture_records()["trials"][0]
    for name, fixture in collector.FIXTURES.items():
        record["catalog"]["fixtures"].append({"id": name, **copy.deepcopy(fixture),
            **collector.fixture_fingerprints(fixture), "expected_reference_status": fixture["expected_status"],
            "absolute_tolerance": 1e-8, "relative_tolerance": 0.0})

    def event(name, side, repetition, warmup):
        fixture = collector.FIXTURES[name]
        row = copy.deepcopy(base)
        primal = fixture["expected_phase_one_primal"]
        original_rows_max_violation = max(
            abs(sum(coefficient * value for coefficient, value in zip(matrix_row, primal)) - target)
            for matrix_row, target in zip(fixture["matrix"], fixture["rhs"]))
        row.update({"fixture": name, "side": side, "repetition": repetition, "warmup": warmup,
            "pair_id": f"{name}-warmup-0" if warmup else f"{name}-{repetition}", "sequence": len(raw),
            "expected_status": fixture["expected_status"], "observed_status": fixture["expected_status"],
            "input": {"matrix": fixture["matrix"], "rhs": fixture["rhs"], "row_relation": "equality",
                "variable_lower_bound": 0.0, "variable_upper_bound": None,
                "objective_coefficients": [0.0] * fixture["columns"], "objective_constant": 0.0}})
        row["result"].update({"outcome": fixture["expected_status"],
            "primal": primal, "auxiliary": fixture["expected_auxiliary"]})
        row["original_rows_max_violation"] = original_rows_max_violation
        row["auxiliary_value"] = fixture["expected_auxiliary"]
        if side == "highs-reference":
            for key in ("original_rows_max_violation", "nonnegative_max_violation", "objective_value", "auxiliary_residual", "auxiliary_value"):
                row[key] = None
            for key in ("auxiliary", "pivots", "degenerate_pivots", "factorizations"):
                row["result"][key] = None
            row["oracle_checks"] = [{"name": name, "passed": True} for name in
                ("expected_status", "independent_feasible_witness", "original_equalities",
                 "nonnegative_variables", "zero_original_objective")]
        raw.append(row)

    for name in collector.FIXTURES:
        for side in collector.SIDES:
            event(name, side, 0, True)
    for repetition in range(7):
        names = list(collector.FIXTURES)
        if repetition % 2:
            names.reverse()
        schedule = []
        for name in names:
            index = list(collector.FIXTURES).index(name)
            sides = collector.SIDES if (repetition + index) % 2 == 0 else reversed(collector.SIDES)
            for side in sides:
                event(name, side, repetition, False)
                schedule.append({"fixture": name, "side": side, "order_index": len(schedule)})
        record["measurement"]["execution_order"].append({"repetition": repetition, "sequence": schedule})
    driver = copy.deepcopy(raw)
    warmups, trials, errors, missing = collector.normalize_and_pair(raw)
    assert errors == [] and missing == 0
    record["warmup_trials"], record["trials"] = warmups, trials
    record["summary"] = collector.summarize(trials, warmups, True, 0)
    return record, driver


def make_bundle(root):
    record, driver = make_records()
    bundle = root / record["report_id"]
    bundle.mkdir(parents=True)
    (bundle / "records.json").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (bundle / "stdout.jsonl").write_text("".join(json.dumps(row) + "\n" for row in
        [*record["warmup_trials"], *record["trials"]]), encoding="utf-8")
    (bundle / "driver-stdout.txt").write_text("".join(json.dumps(row) + "\n" for row in driver), encoding="utf-8")
    (bundle / "stderr.txt").write_bytes(b"synthetic test stderr\n")
    (bundle / "release-build.txt").write_bytes(b"test Release build\n")
    renderer.render_report(record, bundle)
    return bundle


class Opt04PublicationTests(unittest.TestCase):
    def adapter(self):
        try:
            import opt04_registered_reports
        except ImportError:
            self.fail("OPT-04 registered adapter is missing")
        return opt04_registered_reports

    def test_synthetic_infeasible_phase_one_warmup_records_recomputed_row_violation(self):
        record, _ = make_records()
        row = next(row for row in record["warmup_trials"]
                   if row["fixture"] == "contradictory_rows" and row["side"] == "phase-one-bland")
        fixture = next(fixture for fixture in record["catalog"]["fixtures"]
                       if fixture["id"] == "contradictory_rows")
        primal = row["result"]["primal"]
        expected = max(abs(sum(a * x for a, x in zip(matrix_row, primal)) - target)
                       for matrix_row, target in zip(fixture["matrix"], fixture["rhs"]))
        self.assertEqual(1.0, expected)
        self.assertEqual(expected, row["original_rows_max_violation"])
        self.assertGreater(expected, fixture["absolute_tolerance"])

    def test_saved_bundle_stages_typed_page_and_complete_native_evidence(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = make_bundle(root)
            item = adapter.adapt(bundle, allow_test=True)
            self.assertEqual("opt04-phase-one", item.kind)
            self.assertEqual("opt04-20261013T000000Z-123456789abc", item.source_report_id)
            self.assertRegex(item.report_id, r"^opt04-20261013T000000Z-[0-9a-f]{64}$")
            artifacts = adapter.publication_artifacts(bundle, item)
            envelope = json.loads(artifacts["report-envelope.json"])
            self.assertEqual("csl.opt04-phase-one-report/2", envelope["payload_schema"])
            self.assertEqual("Unestablished", envelope["payload"]["claims"]["feasibility_numerics"])
            self.assertEqual(70, len(envelope["payload"]["trials"]))
            self.assertEqual(10, len(envelope["payload"]["warmup_trials"]))
            for path in bundle.iterdir():
                self.assertEqual(path.read_bytes(), artifacts["source-evidence/" + path.name])
            self.assertNotEqual((bundle / "index.html").read_bytes(), artifacts["index.html"])
            self.assertIn(b"contradictory_rows", artifacts["index.html"])
            report_site.OfflineHTML(set(artifacts)).feed(artifacts["index.html"].decode())
            archive = adapter.offline_zip(bundle, item)
            self.assertEqual(archive, adapter.offline_zip(bundle, item))
            with zipfile.ZipFile(io.BytesIO(archive)) as saved:
                self.assertEqual(artifacts["source-evidence/bundle.zip"], saved.read(item.report_id + "/source-evidence/bundle.zip"))

    def test_catalogue_check_stages_only_matching_integrated_projection(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = make_bundle(root)
            item = adapter.adapt(bundle, allow_test=True)
            source = ROOT / "reports/algorithm-results"
            shutil.copyfile(source / "legacy-publications.json", root / "legacy-publications.json")
            pins = json.loads((source / "legacy-publications.json").read_text())["reports"]
            original = json.loads((source / "catalog.json").read_text())
            rows = []
            for row in original["reports"]:
                if row.get("source_report_id") in pins:
                    source_id = row["source_report_id"]
                    shutil.copytree(source / source_id, root / source_id)
                    for suffix in (".zip", ".source.zip"):
                        shutil.copyfile(source / (source_id + suffix), root / (source_id + suffix))
                    rows.append(row)
            projection = {"report_id": item.report_id, "report_kind": item.kind,
                "source_report_id": item.source_report_id, "payload_schema": item.payload_schema,
                "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
                "source_commit": item.source_commit, "measured_scope": item.measured_scope,
                "evidence_limits": item.evidence_limits,
                "zip_sha256": hashlib.sha256(adapter.offline_zip(bundle, item)).hexdigest()}
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main",
                "reports": [*rows, projection]}
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalogue))
            index = report_site.catalogue_index(catalogue)
            report_site.OfflineHTML({row["report_id"] + suffix for row in catalogue["reports"]
                for suffix in ("/index.html", "/records.json", "/stdout.jsonl", "/trials.csv", ".zip")}).feed(index)
            (root / "index.html").write_text(index, encoding="utf-8")
            output = root / "stage"
            with self.assertRaisesRegex(ValueError, "admission|test-only"):
                report_site.stage(catalog_path, output, check=True)
            self.assertFalse(output.exists())
            cli_output = root / "cli-stage"
            command = [sys.executable, str(ROOT / "scripts/reports/site.py"), "--catalog", str(catalog_path),
                "--out", str(cli_output), "--check"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("test-only", result.stderr)
            self.assertFalse(cli_output.exists())
            result = subprocess.run([*command, "--allow-test"], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertIn("unrecognized arguments", result.stderr)
            self.assertFalse(cli_output.exists())
            report_site.stage(catalog_path, output, check=True, allow_test=True)
            self.assertEqual("csl.algorithm-report-envelope/1", json.loads(
                (output / item.report_id / "report-envelope.json").read_text())["schema"])
            self.assertEqual((bundle / "index.html").read_bytes(),
                (output / item.report_id / "source-evidence/index.html").read_bytes())
            self.assertEqual(adapter.offline_zip(bundle, item), (output / (item.report_id + ".zip")).read_bytes())
            self.assertTrue(report_site.validate_publication_manifest(output / item.report_id, projection))
            for field, bad in (("native_payload_sha256", "0" * 64), ("payload_schema", "unknown"),
                               ("measured_scope", "speedup proved"), ("source_report_id", "../outside")):
                with self.subTest(field=field):
                    changed = copy.deepcopy(catalogue)
                    changed["reports"][-1][field] = bad
                    catalog_path.write_text(json.dumps(changed))
                    rejected = root / ("rejected-" + field)
                    with self.assertRaises(ValueError):
                        report_site.stage(catalog_path, rejected, check=False, allow_test=True)
                    self.assertFalse(rejected.exists())

    def test_production_adapter_rejects_synthetic_and_unreviewed_bundles(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            for purpose in ("test", "measurement", None):
                with self.subTest(purpose=purpose):
                    bundle = make_bundle(Path(directory) / str(purpose))
                    record = json.loads((bundle / "records.json").read_text())
                    if purpose is None:
                        del record["purpose"]
                    else:
                        record["purpose"] = purpose
                    (bundle / "records.json").write_text(json.dumps(record))
                    (bundle / "stderr.txt").write_bytes(b"relabelled and changed test evidence\n")
                    renderer.render_report(record, bundle)
                    with self.assertRaisesRegex(ValueError, "admission|test-only"):
                        adapter.adapt(bundle)

    def test_reviewed_admission_binds_every_native_file_and_cannot_admit_test_purpose(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            bundle = make_bundle(Path(directory))
            record = json.loads((bundle / "records.json").read_text())
            del record["purpose"]
            (bundle / "records.json").write_text(json.dumps(record))
            renderer.render_report(record, bundle)
            original = {path.name: path.read_bytes() for path in bundle.iterdir()}
            source_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in original.items()}
            inventory_digest = hashlib.sha256(json.dumps(source_hashes, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            # Only this test's Python harness simulates a trusted reviewer pin;
            # the production registry remains empty and no authenticity is claimed.
            with patch.dict(adapter.REVIEWED_NATIVE_BUNDLES, {bundle.name: inventory_digest}):
                self.assertEqual(bundle.name, adapter.adapt(bundle).source_report_id)
                with self.assertRaisesRegex(ValueError, "purpose: test"):
                    adapter.adapt(bundle, allow_test=True)
                for name in ("records.json", "stdout.jsonl", "driver-stdout.txt", "stderr.txt",
                        "release-build.txt", "index.html", "performance.svg", "manifest.sha256",
                        "bundle.zip", "bundle.zip.sha256"):
                    with self.subTest(name=name):
                        path = bundle / name
                        content = original[name]
                        path.write_bytes((b"0" * 64 + content[64:]) if name == "manifest.sha256" else content + b"\n")
                        with self.assertRaisesRegex(ValueError, "admission"):
                            adapter.adapt(bundle)
                        path.write_bytes(content)
            with self.assertRaisesRegex(ValueError, "admission"):
                adapter.adapt(bundle)
            record["purpose"] = "test"
            (bundle / "records.json").write_text(json.dumps(record))
            renderer.render_report(record, bundle)
            source_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in bundle.iterdir()}
            inventory_digest = hashlib.sha256(json.dumps(source_hashes, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with patch.dict(adapter.REVIEWED_NATIVE_BUNDLES, {bundle.name: inventory_digest}):
                with self.assertRaisesRegex(ValueError, "test-only"):
                    adapter.adapt(bundle)
                self.assertEqual(bundle.name, adapter.adapt(bundle, allow_test=True).source_report_id)

    def test_rejects_corrupt_missing_extra_and_unsafe_inventory(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            for name in ("hash", "missing", "extra", "traversal"):
                with self.subTest(name=name):
                    bundle = make_bundle(Path(directory) / name)
                    if name == "hash":
                        (bundle / "stderr.txt").write_bytes(b"altered")
                    elif name == "missing":
                        (bundle / "driver-stdout.txt").unlink()
                    elif name == "extra":
                        (bundle / "extra.txt").write_bytes(b"unlisted")
                        renderer.package_report(bundle)
                    else:
                        (bundle / "manifest.sha256").write_text("0" * 64 + "  ../outside\n")
                    with self.assertRaises(ValueError):
                        adapter.adapt(bundle, allow_test=True)

    def test_rejects_rehashed_record_and_raw_output_projection_tampering(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            for name in ("stdout.jsonl", "driver-stdout.txt", "summary", "schema", "schema-fields", "identity", "provenance", "input", "invalid-json", "duplicate-json", "scope", "build-hash"):
                with self.subTest(name=name):
                    bundle = make_bundle(Path(directory) / name)
                    path = bundle / "records.json"
                    record = json.loads(path.read_text())
                    if name in ("stdout.jsonl", "driver-stdout.txt"):
                        stream = bundle / name
                        lines = stream.read_text().splitlines()
                        row = json.loads(lines[0])
                        row["durations_ns"]["setup"] = 999
                        lines[0] = json.dumps(row)
                        stream.write_text("\n".join(lines) + "\n")
                    elif name == "invalid-json":
                        path.write_text("{broken")
                    elif name == "duplicate-json":
                        path.write_text(path.read_text().rstrip()[:-1] + ', "report_id": "duplicate"}')
                    else:
                        if name == "summary":
                            record["summary"]["rows"][0]["median_ns"] = 999
                        elif name == "schema":
                            record["schema"] = "csl.opt04-phase-one-report/1"
                        elif name == "schema-fields":
                            del record["measurement"]["execution_policy"]["arithmetic"]["rounding_mode_reason"]
                        elif name == "identity":
                            record["report_id"] = "../outside"
                        elif name == "provenance":
                            record["provenance"]["source_commit"] = "not-a-commit"
                        elif name == "input":
                            record["trials"][0]["input"]["rhs"][0] = 2
                        elif name == "scope":
                            record["measurement"]["timing_boundaries"]["public_run"] = "entire application"
                        elif name == "build-hash":
                            record["provenance"]["release_build_sha256"] = "0" * 64
                        path.write_text(json.dumps(record))
                    # Regenerate producer projections wherever possible, then
                    # rehash every package entry: checksums alone must not pass.
                    if name not in ("invalid-json", "duplicate-json"):
                        renderer.render_report(record, bundle)
                    else:
                        renderer.package_report(bundle)
                    with self.assertRaises(ValueError):
                        adapter.adapt(bundle, allow_test=True)

    def test_failed_incomplete_and_aborted_evidence_is_ineligible(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            for name in ("failed", "incomplete", "aborted"):
                with self.subTest(name=name):
                    bundle = make_bundle(Path(directory) / name)
                    record = json.loads((bundle / "records.json").read_text())
                    if name == "failed":
                        row = record["trials"][0]
                        row["status"] = "failed"
                        row["oracle_match"] = False
                        row["oracle_checks"][0]["passed"] = False
                        row["error"] = "retained failure"
                    elif name == "incomplete":
                        record["trials"].pop()
                        record["measurement"]["execution_order"][-1]["sequence"].pop()
                        record["trials"][-1]["paired_outcomes"] = None
                        record["trials"][-1]["reference_status"] = None
                    else:
                        record["aborted"] = True
                    record["summary"] = collector.summarize(record["trials"], record["warmup_trials"], False,
                        1 if name == "incomplete" else 0)
                    (bundle / "records.json").write_text(json.dumps(record))
                    renderer.render_report(record, bundle)
                    with self.assertRaisesRegex(ValueError, "ineligible"):
                        adapter.adapt(bundle, allow_test=True)

    def test_public_identity_binds_all_native_files_and_normalized_publisher(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            bundle = make_bundle(Path(directory))
            item = adapter.adapt(bundle, allow_test=True)
            source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}
            identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": bundle.name,
                "source_files": source_hashes, "publisher_sha256": hashlib.sha256(
                    Path(adapter.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
            suffix = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            self.assertEqual("opt04-20261013T000000Z-" + suffix, item.report_id)
            (bundle / "stderr.txt").write_bytes(b"changed retained stderr\n")
            renderer.package_report(bundle)
            changed = adapter.adapt(bundle, allow_test=True)
            self.assertNotEqual(item.report_id, changed.report_id)
            self.assertEqual(item.payload_sha256, changed.payload_sha256)
            self.assertEqual(item.source_report_id, changed.source_report_id)

    def test_rejects_bundle_directory_identity_mismatch(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = make_bundle(root)
            renamed = root / "opt04-20261013T000001Z-123456789abc"
            bundle.rename(renamed)
            with self.assertRaisesRegex(ValueError, "identity"):
                adapter.adapt(renamed, allow_test=True)

    def test_rejects_symlink_source_evidence(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = make_bundle(root)
            (bundle / "stderr.txt").unlink()
            outside = root / "outside.txt"
            outside.write_bytes(b"outside")
            try:
                (bundle / "stderr.txt").symlink_to(outside)
            except OSError as exc:
                self.skipTest("symlink creation unavailable: " + str(exc))
            with self.assertRaisesRegex(ValueError, "symlink"):
                adapter.adapt(bundle, allow_test=True)

    def test_native_zip_and_svg_corruption_are_rejected_after_rehash(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            bundle = make_bundle(Path(directory) / "svg")
            (bundle / "performance.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')
            renderer.package_report(bundle)
            with self.assertRaisesRegex(ValueError, "performance.svg"):
                adapter.adapt(bundle, allow_test=True)
            bundle = make_bundle(Path(directory) / "zip")
            (bundle / "bundle.zip").write_bytes(b"invalid ZIP")
            digest = hashlib.sha256(b"invalid ZIP").hexdigest()
            (bundle / "bundle.zip.sha256").write_text(digest + "  bundle.zip\n")
            with self.assertRaises(ValueError):
                adapter.adapt(bundle, allow_test=True)

    def test_typed_evidence_text_is_escaped_in_public_page(self):
        adapter = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            bundle = make_bundle(Path(directory))
            record = json.loads((bundle / "records.json").read_text())
            record["evidence_limits"].append('<script>alert("test")</script>')
            (bundle / "records.json").write_text(json.dumps(record))
            renderer.render_report(record, bundle)
            page = adapter.render_page(bundle, adapter.adapt(bundle, allow_test=True))
            self.assertIn('&lt;script&gt;alert(&quot;test&quot;)&lt;/script&gt;', page)
            self.assertNotIn('<script>', page)
            report_site.OfflineHTML({"performance.svg", "records.json", "stdout.jsonl",
                "report-envelope.json", "publication-manifest.json"} | {
                "source-evidence/" + path.name for path in bundle.iterdir()}).feed(page)

    def test_admitted_opt04_validation_requires_dependency_without_skipping_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = make_bundle(Path(directory))
            code = '''
import sys
sys.path.insert(0, sys.argv[1])
import opt04_registered_reports as opt04
opt04.adapt(sys.argv[2], allow_test=True)
'''
            result = subprocess.run([sys.executable, "-S", "-c", code, str(ROOT / "scripts/reports"), str(bundle)],
                capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("OPT-04 validation requires report-only jsonschema", result.stderr)


if __name__ == "__main__":
    unittest.main()

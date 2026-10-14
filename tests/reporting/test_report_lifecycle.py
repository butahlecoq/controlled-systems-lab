"""Behavior of shared capture and immutable publication compatibility."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import zipfile
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import collector_common as lifecycle
import registered_reports as publications


class CaptureTests(unittest.TestCase):
    def test_timeout_retains_partial_stdout_and_stderr(self):
        command = [sys.executable, "-u", "-c", "import sys,time; print('partial',flush=True); print('diagnostic',file=sys.stderr,flush=True); time.sleep(10)"]
        stdout, stderr, code, timed_out = lifecycle.capture_process(command, timeout_seconds=1)
        self.assertEqual((stdout.strip(), stderr.strip(), code, timed_out), ("partial", "diagnostic", 124, True))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "capture"
            lifecycle.write_capture(out, stdout, stderr, command, code, timed_out, schema="test-capture/1")
            saved = json.loads((out / "process-capture.json").read_text())
            self.assertEqual(saved["process_return_code"], 124)
            self.assertTrue(saved["timed_out"])
            self.assertEqual(saved["stdout_file_sha256"], hashlib.sha256((out / "stdout.jsonl").read_bytes()).hexdigest())

    def test_launch_failure_is_retained(self):
        stdout, stderr, code, timed_out = lifecycle.capture_process(["csl-no-such-executable-for-test"])
        self.assertEqual((stdout, code, timed_out), ("", 127, False))
        self.assertTrue(stderr)

    def test_capture_cannot_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                lifecycle.write_capture(Path(temp), "new", "", [], 0, False, schema="test/1")
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_publication_inventory_rejects_unsafe_paths_and_unregistered_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "records.json").write_text("{}")
            (root / "manifest.json").write_text("{}")
            digest = hashlib.sha256(b"{}").hexdigest()
            publications.validate_source_inventory(root, {"records.json": digest}, {"records.json"}, label="test")
            with self.assertRaises(ValueError):
                publications.validate_source_inventory(root, {"../records.json": digest}, {"../records.json"}, label="test")
            (root / "unreviewed.py").write_text("unreviewed")
            with self.assertRaisesRegex(ValueError, "unregistered"):
                publications.validate_source_inventory(root, {"records.json": digest}, {"records.json"}, label="test")

    def test_historical_pin_requires_exact_input_and_output(self):
        source_id, pin = next(iter(publications._HISTORICAL_PUBLICATIONS.items()))
        bundle = ROOT / "reports" / "algorithm-results" / source_id
        item = publications.PublicationRecord("test", "current", "", "", "", "", source_report_id=source_id)
        self.assertEqual(publications.preserve_historical_publication(bundle, item, lambda *_: b"changed-output").report_id, "current")
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp)
            (changed / "records.json").write_text("changed source")
            archive_builder = unittest.mock.Mock(side_effect=AssertionError("changed input cannot use historical output"))
            self.assertEqual(publications.preserve_historical_publication(changed, item, archive_builder).report_id, "current")
            archive_builder.assert_not_called()

    def test_repacked_identity_source_archive_cannot_reuse_historical_route(self):
        import geo02_registered_reports
        import geo05_registered_reports
        for adapter, source_id in ((geo02_registered_reports, "geo02-20261013T061151Z-338ff7d1d63c"),
                                   (geo05_registered_reports, "geo05-4dc3c0557570a52e")):
            with self.subTest(kind=adapter.__name__), tempfile.TemporaryDirectory() as temporary:
                source = ROOT / "reports" / "algorithm-results" / source_id
                bundle = Path(temporary) / source_id
                shutil.copytree(source, bundle)
                archive_path = bundle.with_suffix(".zip")
                shutil.copyfile(source.with_suffix(".zip"), archive_path)
                publication_zip = publications._HISTORICAL_PUBLICATIONS[source_id]["report_id"] + ".zip"
                if (source.parent / publication_zip).is_file():
                    shutil.copyfile(source.parent / publication_zip, bundle.parent / publication_zip)
                historical = adapter.adapt(bundle)
                self.assertEqual(historical.report_id, publications._HISTORICAL_PUBLICATIONS[source_id]["report_id"])
                before = archive_path.read_bytes()
                # ZIP comments alter source identity without changing any admitted entry.
                with zipfile.ZipFile(archive_path, "a") as archive:
                    archive.comment = b"repacked source identity fixture"
                self.assertNotEqual(before, archive_path.read_bytes())
                current = adapter.adapt(bundle)
                self.assertEqual(current.source_report_id, historical.source_report_id)
                self.assertNotEqual(current.report_id, historical.report_id)
                self.assertEqual(current.payload_sha256, historical.payload_sha256)


class GeometryCollectionTests(unittest.TestCase):
    def test_current_geometry_harness_paths_are_admitted_explicitly(self):
        for kind, filename, driver in (("geo04", "collect.py", "polyhedral_intersection_driver.cpp"),
                                        ("geo05", "report.py", "projection_predecessor_driver.cpp")):
            tooling = ROOT / "scripts" / "reports" / kind
            with self.subTest(kind=kind), patch.object(sys, "path", [str(tooling), *sys.path]):
                spec = importlib.util.spec_from_file_location(kind + "_current_harness", tooling / filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.validate_source_tree_delta([f"scripts/reports/{kind}/{filename}",
                    f"benchmarks/reporting/{kind}/{driver}", "scripts/reports/collector_common.py"])
                with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
                    module.validate_source_tree_delta([f"scripts/reports/{kind}/unreviewed.py"])

    def test_geo04_malformed_and_timeout_keep_raw_and_reached_attempts(self):
        tooling = ROOT / "scripts" / "reports" / "geo04"
        with patch.object(sys, "path", [str(tooling), *sys.path]):
            spec = importlib.util.spec_from_file_location("geo04_capture_fixture", tooling / "collect.py")
            collector = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(collector)
        source = next((ROOT / "reports" / "algorithm-results").glob("geo04-*/raw-driver-output.csv"))
        lines = source.read_text(encoding="utf-8").splitlines()
        prefix = "\n".join(lines[:2]) + "\n"
        for name, stdout, code, timeout in (("malformed", prefix + "malformed\n", 0, False),
                                            ("timeout", prefix, 124, True)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                exe, note, profile = root / "driver.exe", root / "note", root / "profile"
                exe.write_bytes(b"test-only executable identity")
                note.write_text("test collection; no numerical work")
                profile.write_text("no profiling in this test")
                out = root / "out"
                args = ["collect.py", "--exe", str(exe), "--build-dir", str(root),
                        "--source-commit", "source", "--harness-commit", "harness",
                        "--concurrent-work", str(note), "--profile-evidence", str(profile), "--out", str(out)]
                provenance = {"fresh_build": {"command": ["fixture-build"], "stdout": "fixture", "stderr": ""}}
                with patch.object(sys, "argv", args), patch.object(collector, "build_provenance", return_value=provenance), \
                     patch.object(collector, "git", return_value=str(ROOT)), patch.object(collector, "clean_tracked"), \
                     patch.object(lifecycle, "capture_process", return_value=(stdout, "partial diagnostic", code, timeout)), \
                     patch.object(lifecycle, "machine_snapshot", return_value={}), patch.object(lifecycle, "public_load", return_value={}):
                    self.assertEqual(collector.main(), 2)
                record = json.loads((out / "records.json").read_text())
                self.assertEqual(record["algorithm"]["source_commit"], "source")
                self.assertEqual(record["collection"]["state"], "failed")
                self.assertEqual(record["collection"]["aborted_or_timed_out"], timeout)
                self.assertEqual(len(record["trials"]), 1)
                self.assertEqual(record["trials"][0]["status"], "passed")
                self.assertEqual((out / "raw-driver-output.csv").read_text(), stdout)
                self.assertEqual((out / "process-stderr.txt").read_text(), "partial diagnostic")
                self.assertEqual(json.loads((out / "process-capture.json").read_text())["process_return_code"], code)
                if name == "malformed":
                    self.assertTrue((out / "validation-error.json").is_file())


if __name__ == "__main__":
    unittest.main()

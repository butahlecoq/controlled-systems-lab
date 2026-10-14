"""Behavior of shared capture and immutable publication compatibility."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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


if __name__ == "__main__":
    unittest.main()

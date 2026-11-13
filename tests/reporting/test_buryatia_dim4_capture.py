import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (Path(__file__).resolve().parents[2] / "scripts/reports/buryatia/capture_dim4.py")
SPEC = importlib.util.spec_from_file_location("buryatia_capture_dim4", SCRIPT)
CAPTURE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CAPTURE)
CHECK_SCRIPT = (Path(__file__).resolve().parents[2] / "scripts/reports/buryatia/check_dim4.py")
CHECK_SPEC = importlib.util.spec_from_file_location("buryatia_check_dim4", CHECK_SCRIPT)
CHECK = importlib.util.module_from_spec(CHECK_SPEC)
assert CHECK_SPEC and CHECK_SPEC.loader
CHECK_SPEC.loader.exec_module(CHECK)


class BuryatiaCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for relative in CAPTURE.IMPLEMENTATION_SOURCES:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        self.build_cache = self.root / "CMakeCache.txt"
        self.build_cache.write_text("CMAKE_BUILD_TYPE:STRING=Release\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_reused_attempt_directory_is_rejected_without_changing_streams(self):
        attempt = self.root / "attempt-001"
        command = [sys.executable, "-c", "import sys; print('record'); print('trace', file=sys.stderr)"]
        CAPTURE.capture(command, self.source, self.build_cache, attempt, "test")
        stdout = (attempt / "stdout.json").read_bytes()
        stderr = (attempt / "stderr.txt").read_bytes()
        metadata = (attempt / "capture.json").read_bytes()

        with self.assertRaises(FileExistsError):
            CAPTURE.capture(command, self.source, self.build_cache, attempt, "test-retry")

        self.assertEqual((attempt / "stdout.json").read_bytes(), stdout)
        self.assertEqual((attempt / "stderr.txt").read_bytes(), stderr)
        self.assertEqual((attempt / "capture.json").read_bytes(), metadata)

    def test_stream_files_exist_before_child_starts(self):
        attempt = self.root / "attempt-precreated"
        code = (
            "from pathlib import Path; import sys; "
            "assert Path(sys.argv[1]).is_file() and Path(sys.argv[2]).is_file(); "
            "print('streams ready')"
        )
        command = [sys.executable, "-c", code,
                   str(attempt / "stdout.json"), str(attempt / "stderr.txt")]

        CAPTURE.capture(command, self.source, self.build_cache, attempt, "test-precreated")

        self.assertEqual((attempt / "stdout.json").read_text(), "streams ready\n")

    def test_nonzero_child_retains_both_streams_and_failure_metadata(self):
        attempt = self.root / "attempt-failed"
        command = [sys.executable, "-c", "import sys; print('partial-json'); print('solver failed', file=sys.stderr); sys.exit(7)"]

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            CAPTURE.capture(command, self.source, self.build_cache, attempt, "test-failure")

        self.assertEqual(raised.exception.returncode, 7)
        self.assertEqual((attempt / "stdout.json").read_text(), "partial-json\n")
        self.assertEqual((attempt / "stderr.txt").read_text(), "solver failed\n")
        receipt = json.loads((attempt / "capture.json").read_text())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["exit_code"], 7)
        self.assertTrue(receipt["stdout_sha256"])
        self.assertTrue(receipt["stderr_sha256"])

    def test_full_state_orientation_gate_marks_old_trace_and_accepts_corrected_record(self):
        root = Path(__file__).resolve().parents[2]
        record = json.loads((root / "docs/examples/buryatia-dim4-literal-affine-v1-records.json")
                            .read_text(encoding="utf-8"))
        CHECK.validate(record)
        with self.assertRaises(AssertionError):
            CHECK.validate(record, require_full_box_orientation=True)

        corrected = json.loads(json.dumps(record))
        for stage in corrected["records"][1:]:
            box = next(family for family in stage["families"] if family["family"] == "box")
            box["module_invocations"]["operation"]["inclusion_evidence"][0] = \
                CHECK.box_orientation_rows(corrected["state_dimension"])
        CHECK.validate(corrected, require_full_box_orientation=True)


if __name__ == "__main__":
    unittest.main()

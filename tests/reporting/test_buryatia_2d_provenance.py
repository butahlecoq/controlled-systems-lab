import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/buryatia/check_2d.py"
RAW = ROOT / "docs/examples/buryatia-volterra-affine-2d-records.json"
SPEC = importlib.util.spec_from_file_location("buryatia_check_2d", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CHECK)


class Buryatia2DProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = json.loads(RAW.read_text(encoding="utf-8"))

    def test_saved_raw_cli_accepts_declared_producer_after_source_update(self):
        name = "src/geometry/approximation/box_parallelotope.cpp"
        self.assertNotEqual(self.saved["native_build"]["source_sha256"][name],
                            hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
        result = subprocess.run([sys.executable, str(SCRIPT), "--raw", str(RAW)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validated 61 stages", result.stdout)

    def test_saved_raw_cli_rejects_tampered_hash_or_false_producer(self):
        # Current main can legitimately contain the same source blobs as this
        # historical capture. Use the reviewed Dim4 head, whose 2D checker and
        # parallelotope source are known to differ from the recorded producer.
        false_producer = "8a6ff5add9a18615aaecf4b877e6d0f6fa5af727"
        for field in ("hash", "revision"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                record = copy.deepcopy(self.saved)
                if field == "hash":
                    record["native_build"]["source_sha256"][CHECK.IMPLEMENTATION_SOURCES[0]] = "0" * 64
                else:
                    record["native_build"]["git_revision"] = false_producer
                path = Path(temporary) / "tampered.json"
                path.write_text(json.dumps(record), encoding="utf-8")
                result = subprocess.run([sys.executable, str(SCRIPT), "--raw", str(path)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)

    def test_historical_receipt_cannot_be_labeled_current(self):
        with self.assertRaises(AssertionError):
            CHECK.validate(copy.deepcopy(self.saved), require_current_sources=True)

    def test_executable_mode_rejects_a_historical_receipt(self):
        run = subprocess.run

        def native_or_git(command, **kwargs):
            if command[0] == "native-fixture":
                return subprocess.CompletedProcess(command, 0, json.dumps(self.saved), "")
            return run(command, **kwargs)

        with patch.object(sys, "argv", [str(SCRIPT), "--exe", "native-fixture"]), \
             patch.object(CHECK.subprocess, "run", side_effect=native_or_git), \
             patch.object(CHECK, "native_receipt", return_value=self.saved["native_build"]):
            with self.assertRaises(AssertionError):
                CHECK.main()

    def test_current_capture_requires_committed_matching_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in CHECK.IMPLEMENTATION_SOURCES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            old = "docs/examples/buryatia-volterra-affine-2d-records-superseded-v1.json"
            (root / old).parent.mkdir(parents=True, exist_ok=True)
            (root / old).write_bytes((ROOT / old).read_bytes())
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Provenance test", "-c",
                            "user.email=provenance@example.invalid", "commit", "-qm", "fixture"],
                           cwd=root, check=True)
            with patch.object(CHECK, "ROOT", root):
                record = copy.deepcopy(self.saved)
                record["native_build"] = CHECK.native_receipt(Path(sys.executable), None)
                CHECK.validate(record, require_current_sources=True)
                changed = root / CHECK.IMPLEMENTATION_SOURCES[0]
                changed.write_bytes(changed.read_bytes() + b"\n// dirty fixture\n")
                # An old receipt cannot describe changed working sources.
                with self.assertRaises(AssertionError):
                    CHECK.validate(record, require_current_sources=True)
                # Recapturing dirty hashes cannot evade the committed-source check.
                record["native_build"] = CHECK.native_receipt(Path(sys.executable), None)
                with self.assertRaises(AssertionError):
                    CHECK.validate(record, require_current_sources=True)


if __name__ == "__main__":
    unittest.main()

"""Native inventory validation for the saved BTULSHOR report bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_btulshor


class StageBtulshorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / stage_btulshor.REPORT_ID
        self.bundle.mkdir()
        self._make_bundle()

    def _make_bundle(self):
        contents = {
            "index.html": b'<!doctype html><html lang="en"><body>Saved outcomes</body></html>\n',
            "point-projections.svg": b'<svg xmlns="http://www.w3.org/2000/svg"></svg>\n',
            "raw/comparisons.json": b'{"schema":"saved-comparisons"}\n',
            "input/cloud-2d.json": b'{"points":[[0,0],[1,0],[0,1]]}\n',
            "source/include/csl/geometry/legacy_btulshor.hpp": b"// public header snapshot\n",
            "source/src/geometry/legacy_btulshor.cpp": b"// public source snapshot\n",
            "source/benchmarks/reporting/btulshor/driver.cpp": b"// public driver snapshot\n",
            "source/scripts/reports/btulshor/render.py": b"# public renderer snapshot\n",
            "source/docs/research/tools/check_btulshor_hulls.py": b"# public checker snapshot\n",
            "offline_check.py": b"print('verified')\n",
        }
        for name, data in contents.items():
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest = {
            "schema": stage_btulshor.SCHEMA,
            "capture_source_commit": "a" * 40,
            "source_sha256": stage_btulshor.ORIGINAL_SOURCE_SHA256,
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
        }
        manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        (self.bundle / stage_btulshor.MANIFEST).write_bytes(manifest_bytes)
        sums = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
        sums[stage_btulshor.MANIFEST] = hashlib.sha256(manifest_bytes).hexdigest()
        sums_bytes = "".join(f"{value}  {name}\n" for name, value in sorted(sums.items())).encode("ascii")
        (self.bundle / stage_btulshor.SUMS).write_bytes(sums_bytes)
        with zipfile.ZipFile(self.bundle / stage_btulshor.ZIP_NAME, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(contents.items()):
                archive.writestr(f"{stage_btulshor.REPORT_ID}/{name}", data)
            archive.writestr(f"{stage_btulshor.REPORT_ID}/{stage_btulshor.MANIFEST}", manifest_bytes)
            archive.writestr(f"{stage_btulshor.REPORT_ID}/{stage_btulshor.SUMS}", sums_bytes)

    def _rehash(self):
        manifest_path = self.bundle / stage_btulshor.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest["files"] = {
            path.relative_to(self.bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.bundle.rglob("*") if path.is_file() and path.name not in
            {stage_btulshor.MANIFEST, stage_btulshor.SUMS, stage_btulshor.ZIP_NAME}
        }
        manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        manifest_path.write_bytes(manifest_bytes)
        checks = {name: value for name, value in manifest["files"].items()}
        checks[stage_btulshor.MANIFEST] = hashlib.sha256(manifest_bytes).hexdigest()
        sums_bytes = "".join(f"{value}  {name}\n" for name, value in sorted(checks.items())).encode("ascii")
        (self.bundle / stage_btulshor.SUMS).write_bytes(sums_bytes)
        with zipfile.ZipFile(self.bundle / stage_btulshor.ZIP_NAME, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(set(manifest["files"]) | {stage_btulshor.MANIFEST, stage_btulshor.SUMS}):
                archive.write(self.bundle / name, f"{stage_btulshor.REPORT_ID}/{name}")

    def test_validates_saved_inventory_and_preserves_native_archive(self):
        admitted = stage_btulshor.validate(self.bundle)
        self.assertEqual(admitted["manifest"]["capture_source_commit"], "a" * 40)
        self.assertEqual(admitted["files"]["index.html"], (self.bundle / "index.html").read_bytes())
        self.assertEqual(admitted["zip_bytes"], (self.bundle / stage_btulshor.ZIP_NAME).read_bytes())
        with zipfile.ZipFile(self.bundle / stage_btulshor.ZIP_NAME) as archive:
            self.assertIsNone(archive.testzip())

    def test_manifest_hash_mismatch_and_unsafe_zip_are_refused(self):
        data_file = self.bundle / "raw/comparisons.json"
        data_file.write_bytes(data_file.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
            stage_btulshor.validate(self.bundle)

        self._make_bundle()
        with zipfile.ZipFile(self.bundle / stage_btulshor.ZIP_NAME, "a") as archive:
            archive.writestr(f"{stage_btulshor.REPORT_ID}/../escape", b"bad")
        with self.assertRaisesRegex(ValueError, "unsafe bundle path"):
            stage_btulshor.validate(self.bundle)

    def test_private_source_snapshot_is_refused_even_when_all_hashes_match(self):
        private = self.bundle / "source/original/ReachableSets.pas"
        private.parent.mkdir(parents=True)
        private.write_text("private source")
        self._rehash()
        with self.assertRaisesRegex(ValueError, "source snapshot contains a non-public"):
            stage_btulshor.validate(self.bundle)



if __name__ == "__main__":
    unittest.main()

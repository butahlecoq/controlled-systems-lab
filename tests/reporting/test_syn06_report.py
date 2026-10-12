"""Behavioral publication checks against the saved SYN-06 measurement bundle."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_syn06 as syn06

CATALOG = ROOT / "reports" / "algorithm-results" / "syn06-publications.json"
SOURCE_ID = "syn06-verifier-20261012-edf2b200"
SOURCE = CATALOG.parent / SOURCE_ID


def rehash_native(bundle: Path) -> None:
    files = {name: (bundle / name).read_bytes() for name in syn06.SOURCE_FILES}
    manifest = {"schema": "csl.syn06-source-manifest/1", "report_id": bundle.name,
                "files": {name: syn06.digest_bytes(files[name]) for name in sorted(files)}}
    (bundle / "manifest.json").write_bytes(syn06.json_bytes(manifest))
    (bundle / "bundle.zip").write_bytes(syn06.registered.publication_zip(bundle.name,
        {**files, "manifest.json": (bundle / "manifest.json").read_bytes()}))


class Syn06ReportTests(unittest.TestCase):
    def test_saved_bundle_and_public_zip_preserve_validated_evidence(self):
        expected = syn06.catalogue_entry(SOURCE)
        self.assertEqual(json.loads(CATALOG.read_text(encoding="utf-8"))["reports"], [expected])
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / "site"
            syn06.site.stage(CATALOG.parent / "catalog.json", site, check=True)
            old_paths = [path for path in site.rglob("*") if path.is_file() and path != site / "index.html"]
            old_bytes = {path.relative_to(site): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in old_paths}
            original_index = (site / "index.html").read_bytes()
            public_id = syn06.stage(CATALOG, site)
            self.assertEqual(public_id, expected["report_id"])
            self.assertNotEqual(original_index, (site / "index.html").read_bytes())
            self.assertIn(public_id + "/index.html", (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(old_bytes, {relative: hashlib.sha256((site / relative).read_bytes()).hexdigest()
                                         for relative in old_bytes})
            public = site / public_id
            self.assertEqual((public / "raw-events.jsonl").read_bytes(), (SOURCE / "raw-events.jsonl").read_bytes())
            self.assertEqual((public / "index.html").read_bytes(), (SOURCE / "index.html").read_bytes())
            with zipfile.ZipFile(site / (public_id + ".zip")) as archive:
                self.assertEqual(archive.read(public_id + "/records.json"), (public / "records.json").read_bytes())
                self.assertEqual(archive.read(public_id + "/bundle.zip"), (SOURCE / "bundle.zip").read_bytes())

    def test_rehashed_contradictory_csv_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / SOURCE_ID
            shutil.copytree(SOURCE, bundle)
            path = bundle / "trials.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                fields = reader.fieldnames
            rows[0]["elapsed_ns"] = str(int(rows[0]["elapsed_ns"]) + 1)
            path.write_bytes(syn06.csv_bytes(tuple(fields), rows))
            rehash_native(bundle)
            with self.assertRaisesRegex(ValueError, "CSV differs"):
                syn06.validate(bundle)

    def test_rehashed_active_html_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / SOURCE_ID
            shutil.copytree(SOURCE, bundle)
            page = (bundle / "index.html").read_text(encoding="utf-8")
            (bundle / "index.html").write_text(page.replace("</body>", "<script>alert(1)</script></body>"),
                                                encoding="utf-8")
            rehash_native(bundle)
            with self.assertRaisesRegex(ValueError, "offline HTML|unsupported"):
                syn06.validate(bundle)


if __name__ == "__main__":
    unittest.main()

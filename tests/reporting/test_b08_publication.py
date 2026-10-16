"""Saved B08 report publication and neighboring route behavior."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import b08_exact_registered_reports as b08
from scripts.reports import site
import stage_ext01

REPORTS = ROOT / "reports/algorithm-results"
SOURCE = REPORTS / "b08-exact-b0d0e85d4d338f56"


class B08PublicationTests(unittest.TestCase):
    def test_reviewed_bundle_binds_catalogue_and_offline_zip(self):
        item = b08.adapt(SOURCE)
        catalogue = json.loads((REPORTS / "catalog.json").read_text(encoding="utf-8"))
        entry = next(row for row in catalogue["reports"] if row["report_kind"] == b08.KIND)
        self.assertEqual(entry, b08.catalogue_entry(SOURCE))
        self.assertEqual(item.source_report_id, "b08-exact-b0d0e85d4d338f56")
        self.assertEqual(item.source_commit, "78212b21d42ec3f136f0e1c72b2b0861d306792c")
        self.assertIn("625 plans x 256 corners", item.measured_scope)
        self.assertIn("no comparator or speedup", item.evidence_limits)
        self.assertEqual((REPORTS / (item.report_id + ".zip")).read_bytes(), b08.offline_zip(SOURCE, item))
        self.assertIn("raw-trials.jsonl", b08.render_page(SOURCE, item))
        self.assertIn("report-envelope.json", b08.render_page(SOURCE, item))

    def test_changed_raw_or_source_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / SOURCE.name
            shutil.copytree(SOURCE, bundle)
            archive = root / (SOURCE.name + ".zip")
            shutil.copyfile(SOURCE.with_suffix(".zip"), archive)
            raw = bundle / "raw-trials.jsonl"
            saved = raw.read_bytes()
            raw.write_bytes(saved + b"tampered\n")
            with self.assertRaisesRegex(ValueError, "source file hash mismatch"):
                b08.adapt(bundle)
            raw.write_bytes(saved)
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "ZIP"):
                b08.adapt(bundle)

    def test_staged_b08_geo06_and_ext01_routes_are_present(self):
        catalogue = json.loads((REPORTS / "catalog.json").read_text(encoding="utf-8"))
        geo = next(row for row in catalogue["reports"] if row["report_kind"] == "geo06-quickhull")
        b08_entry = next(row for row in catalogue["reports"] if row["report_kind"] == b08.KIND)
        ext = json.loads((REPORTS / "ext01-publications.json").read_text(encoding="utf-8"))["reports"][0]
        with tempfile.TemporaryDirectory() as temporary:
            staged = site.stage(REPORTS / "catalog.json", Path(temporary) / "site", check=True)
            stage_ext01.stage(REPORTS / "ext01-publications.json", staged)
            index = (staged / "index.html").read_text(encoding="utf-8")
            for entry in (geo, b08_entry, ext):
                rid = entry["report_id"]
                self.assertIn(rid + "/index.html", index)
                self.assertTrue((staged / rid / "index.html").is_file())
                self.assertEqual(hashlib.sha256((staged / (rid + ".zip")).read_bytes()).hexdigest(),
                                 entry["zip_sha256"])
                self.assertTrue(site.validate_publication_manifest(staged / rid, entry))
            page = (staged / b08_entry["report_id"] / "index.html").read_text(encoding="utf-8")
            self.assertIn("Fresh-process durations for all B08 attempts", page)
            self.assertIn("The gray warmup is excluded from the median", page)
            self.assertIn("raw-trials.jsonl", page)


if __name__ == "__main__":
    unittest.main()

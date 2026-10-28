"""Publication and exact-record checks for the first EXP-02 3D hull cell."""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
sys.path.insert(0, str(ROOT / "benchmarks/reporting/it17_hull"))

import exp02_it17_hull3d as publication
import summarize_3d

PRIMARY = ROOT / "reports/algorithm-results/exp02-it17-hull-3d-simplex-20261028-r1"
INITIAL = ROOT / "reports/algorithm-results/exp02-it17-hull-3d-halton-cloud-20261028-r1"


class Exp02Hull3DPublicationTests(unittest.TestCase):
    def test_all_raw_attempts_have_exact_independent_hull_checks(self) -> None:
        rows = summarize_3d.read_rows(PRIMARY / "raw/raw-rows.jsonl")
        self.assertEqual(len(rows), 36)
        measured = [row for row in rows if not row["warmup"] and row["method"] != "geometric-quickhull"]
        self.assertEqual(len(measured), 25)
        self.assertTrue(all(row["independent_hull_check"] for row in measured))
        self.assertEqual(sum(row["reducer_status_complete"] is True for row in measured), 15)
        self.assertTrue(all(row["outcome"] == "unsupported_dimension"
                            for row in rows if row["method"] == "geometric-quickhull"))

    def test_bundles_and_offline_archives_match_their_checksums(self) -> None:
        self.assertEqual(len(publication.verify_bundle(PRIMARY)), 64)
        self.assertEqual(len(publication.verify_bundle(INITIAL)), 64)

    def test_stager_adds_fresh_routes_and_rejects_tampered_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            primary = temp / PRIMARY.name
            initial = temp / INITIAL.name
            shutil.copytree(PRIMARY, primary)
            shutil.copytree(INITIAL, initial)
            site = temp / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><html><ul></ul></html>", encoding="utf-8")
            self.assertEqual(publication.stage(primary, initial, site), PRIMARY.name)
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f"{PRIMARY.name}/index.html", index)
            self.assertIn(f"{INITIAL.name}/index.html", index)
            self.assertTrue((site / PRIMARY.name / f"{PRIMARY.name}.zip").is_file())
            self.assertTrue((site / INITIAL.name / f"{INITIAL.name}.zip").is_file())

            second_site = temp / "second-site"
            second_site.mkdir()
            (second_site / "index.html").write_text("<!doctype html><html><ul></ul></html>", encoding="utf-8")
            (primary / "summary.csv").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication.stage(primary, initial, second_site)


if __name__ == "__main__":
    unittest.main()

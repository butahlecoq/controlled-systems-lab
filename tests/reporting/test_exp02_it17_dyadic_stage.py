"""The repeated ITIS17 dyadic bundle stages as a safe, navigable Pages report."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
spec = importlib.util.spec_from_file_location(
    "exp02_it17_dyadic_stage", ROOT / "scripts/reports/stage_exp02_it17_dyadic.py")
stage_report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(stage_report)


class Exp02IT17DyadicStageTests(unittest.TestCase):
    def test_summarizer_suppresses_latency_for_failed_or_short_samples(self):
        source = ROOT / "reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3"
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / source.name
            shutil.copytree(source, copied)

            path = copied / "raw/n64.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            measured = [row for row in rows if not row["warmup"]]
            failed_group = measured[0]["method"]
            short_group = next(row["method"] for row in measured
                               if row["method"] != failed_group)
            next(row for row in rows if row["method"] == failed_group and not row["warmup"])["passed"] = False
            short_row = next(row for row in rows
                             if row["method"] == short_group and not row["warmup"])
            rows.remove(short_row)
            path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n"
                                      for row in rows), encoding="utf-8")

            subprocess.run([sys.executable, str(copied / "summarize.py")],
                           check=True, capture_output=True, text=True)

            with (copied / "summary.csv").open(newline="", encoding="utf-8") as stream:
                summaries = list(csv.DictReader(stream))
            failed = next(row for row in summaries
                          if row["fixture"] == "dyadic-square-n64"
                          and row["method"] == failed_group)
            short = next(row for row in summaries
                         if row["fixture"] == "dyadic-square-n64"
                         and row["method"] == short_group)
            for row, measured_count, passed_count, failed_count in (
                    (failed, "5", "4", "1"), (short, "4", "4", "0")):
                self.assertEqual(row["measured"], measured_count)
                self.assertEqual(row["passed"], passed_count)
                self.assertEqual(row["failed"], failed_count)
                self.assertEqual(row["median_ns_passed_only"], "")
                self.assertEqual(row["min_ns_passed_only"], "")
                self.assertEqual(row["max_ns_passed_only"], "")
            page = (copied / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("All 60 measured attempts passed", page)

    def test_output_status_bundle_stages_verified_hulls_and_reducer_status(self):
        report_id = "exp02-it17-a44-paper-order-20261028-r3"
        source = ROOT / "reports/algorithm-results" / report_id
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>',
                encoding="utf-8")

            self.assertEqual(stage_report.stage(source, site), report_id)
            import landing
            landing.build(site)

            page = (site / report_id / "index.html").read_text(encoding="utf-8")
            self.assertIn("output-status pilot", page)
            self.assertIn("Timing summary", page)
            self.assertIn("0/5", page)
            record = json.loads((source / "record.json").read_text(encoding="utf-8"))
            self.assertIn(record["source_commit"], page)
            self.assertTrue((site / report_id / "fixture-geometry.svg").is_file())
            raw = (site / report_id / "raw/n64.jsonl").read_text(encoding="utf-8")
            self.assertIn('"reducer_status_complete":false', raw)
            self.assertIn('"reducer_status_complete":null', raw)
            self.assertIn('"passed":true', raw)
            self.assertIn(report_id + ".zip", (site / "index.html").read_text(encoding="utf-8"))

            with ZipFile(site / (report_id + ".zip")) as archive:
                names = set(archive.namelist())
                self.assertIn(report_id + "/raw/n256.jsonl", names)
                self.assertIn(report_id + "/fixture-geometry.svg", names)
                self.assertIn(report_id + "/SHA256SUMS", names)

    def test_clean_a44_v2_bundle_stages_with_source_identity_and_figure(self):
        report_id = "exp02-it17-a44-paper-order-20261027-r2"
        source = ROOT / "reports/algorithm-results" / report_id
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>',
                encoding="utf-8")

            self.assertEqual(stage_report.stage(source, site), report_id)
            import landing
            landing.build(site)

            report_page = site / report_id / "index.html"
            page = report_page.read_text(encoding="utf-8")
            self.assertIn("A44 v2", page)
            self.assertIn("ec7d183842d8725d10276dee8b8689ee5313448e", page)
            self.assertTrue((site / report_id / "fixture-geometry.svg").is_file())
            self.assertTrue((site / report_id / "raw/n256.jsonl").is_file())
            self.assertIn(report_id + ".zip", (site / "index.html").read_text(encoding="utf-8"))

            with ZipFile(site / (report_id + ".zip")) as archive:
                names = set(archive.namelist())
                self.assertIn(report_id + "/raw/n64.jsonl", names)
                self.assertIn(report_id + "/fixture-geometry.svg", names)
                self.assertIn(report_id + "/SHA256SUMS", names)

    def test_versioned_report_and_raw_rows_stage_into_site_and_offline_zip(self):
        source = ROOT / "reports/algorithm-results" / stage_report.REPORT_ID
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>',
                encoding="utf-8")

            self.assertEqual(stage_report.stage(source, site), stage_report.REPORT_ID)
            import landing
            landing.build(site)

            report_page = site / stage_report.REPORT_ID / "index.html"
            page = report_page.read_text(encoding="utf-8")
            self.assertIn("performance verdict inconclusive", page)
            self.assertIn("60 interior points", page)
            self.assertTrue((site / stage_report.REPORT_ID / "raw/n64.jsonl").is_file())
            prior_page = site / stage_report.REPORT_ID / "prior-halton-ladder/index.html"
            self.assertTrue(prior_page.is_file())
            self.assertTrue((prior_page.parent / "halton-square-n1000.svg").is_file())
            self.assertIn("Earlier size ladder", page)
            landing_page = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(stage_report.REPORT_ID + "/index.html", landing_page)
            self.assertIn(stage_report.REPORT_ID + ".zip", landing_page)

            with ZipFile(site / (stage_report.REPORT_ID + ".zip")) as archive:
                names = set(archive.namelist())
                self.assertIn(stage_report.REPORT_ID + "/raw/n256.jsonl", names)
                self.assertIn(stage_report.REPORT_ID + "/prior-halton-ladder/index.html", names)
                self.assertIn(stage_report.REPORT_ID + "/prior-halton-ladder/halton-square-n1000.svg", names)
                self.assertIn(stage_report.REPORT_ID + "/SHA256SUMS", names)

    def test_bundle_hash_mismatch_is_rejected(self):
        source = ROOT / "reports/algorithm-results" / stage_report.REPORT_ID
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / stage_report.REPORT_ID
            import shutil
            shutil.copytree(source, copied)
            with (copied / "summary.csv").open("a", encoding="utf-8") as output:
                output.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                stage_report.validate_bundle(copied)


if __name__ == "__main__":
    unittest.main()

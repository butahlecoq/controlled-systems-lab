"""Validate the reviewed MPC-03 report staging route."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import landing
import stage_mpc03


class StageMpc03Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(ROOT / "reports/algorithm-results/mpc03-open-loop-pilot-v1", self.source)
        self.site = self.root / "site"
        examples = self.site / "examples"
        examples.mkdir(parents=True)
        (examples / "index.html").write_text(
            '<html><body><main><section id="analytic-illustrations">Analytic examples</section></main></body></html>',
            encoding="utf-8")

    def test_stage_copies_saved_report_and_adds_discoverable_gallery_card_idempotently(self):
        stage_mpc03.stage(self.source, self.site)
        stage_mpc03.stage(self.source, self.site)
        route = self.site / stage_mpc03.REPORT_ID
        self.assertEqual(json.loads((route / "record.json").read_text())['result']['finite_upper_bound'], 2.25)
        self.assertTrue((route / "index.html").is_file())
        self.assertTrue((route / "disturbance-tube.svg").is_file())
        page = (self.site / "examples/index.html").read_text()
        self.assertEqual(page.count('id="mpc03-open-loop-pilot-v1"'), 1)
        self.assertIn("../mpc03-open-loop-pilot-v1/index.html", page)

    def test_stage_rejects_a_raw_record_hash_mismatch_before_writing(self):
        (self.source / "pilot-output.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw output differs"):
            stage_mpc03.stage(self.source, self.site)
        self.assertFalse((self.site / stage_mpc03.REPORT_ID).exists())

    def test_staged_report_reaches_the_archive_and_gallery_indexes(self):
        (self.site / "index.html").write_text(
            '<!doctype html><html lang="en"><body><ul></ul>'
            '<p id="visual-examples-link"><a href="examples/index.html">Examples</a></p></body></html>',
            encoding="utf-8")
        stage_mpc03.stage(self.source, self.site)
        landing.build(self.site)
        report_index = (self.site / "index.html").read_text(encoding="utf-8")
        gallery_index = (self.site / "examples/index.html").read_text(encoding="utf-8")
        self.assertIn('href="mpc03-open-loop-pilot-v1/index.html"', report_index)
        self.assertIn('href="mpc03-open-loop-pilot-v1/record.json"', report_index)
        self.assertIn('href="../mpc03-open-loop-pilot-v1/index.html"', gallery_index)


if __name__ == "__main__":
    unittest.main()

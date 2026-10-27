"""Validate the saved B08 MIQCP report and deterministic projections."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
from mpc03.b08_report import render_html, render_svg
import stage_mpc03_b08


class Mpc03B08ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(ROOT / "reports/algorithm-results/mpc03-b08-l04-miQCP-v1", self.source)
        self.site = self.root / "site"
        examples = self.site / "examples"
        examples.mkdir(parents=True)
        (examples / "index.html").write_text(
            '<html><body><section id="analytic-illustrations">Examples</section></body></html>',
            encoding="utf-8")

    def test_saved_report_and_all_five_projected_tubes_are_record_rendered(self):
        record = json.loads((self.source / "record.json").read_text(encoding="utf-8"))
        self.assertEqual([len(stage["points"]) for stage in record["result"]["projected_tube"]],
                         [1, 4, 16, 64, 256])
        self.assertEqual(render_html(record),
                         (self.source / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(render_svg(record),
                         (self.source / "disturbance-tube.svg").read_text(encoding="utf-8"))
        svg = render_svg(record)
        self.assertIn("worst-cost terminal", svg)
        self.assertIn("projected target at stage 4", svg)
        self.assertIn("fixed plan (0.3, 0.6, 0.6, -0.6)", svg)

    def test_stage_adds_report_and_gallery_card_idempotently(self):
        stage_mpc03_b08.stage(self.source, self.site)
        stage_mpc03_b08.stage(self.source, self.site)
        route = self.site / stage_mpc03_b08.REPORT_ID
        self.assertEqual(json.loads((route / "record.json").read_text())["case_id"],
                         "b08-l04-displayed-rounded-open-loop")
        self.assertTrue((route / "index.html").is_file())
        self.assertTrue((route / "disturbance-tube.svg").is_file())
        gallery = (self.site / "examples/index.html").read_text(encoding="utf-8")
        self.assertEqual(gallery.count('id="mpc03-b08-l04-miQCP-v1"'), 1)
        self.assertIn("../mpc03-b08-l04-miQCP-v1/index.html", gallery)

    def test_stage_rejects_tampered_solver_output_before_writing(self):
        path = self.source / "solver-output.json"
        path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "solver output hash differs"):
            stage_mpc03_b08.stage(self.source, self.site)
        self.assertFalse((self.site / stage_mpc03_b08.REPORT_ID).exists())

    def test_stage_rejects_changed_geometry_before_writing(self):
        path = self.source / "disturbance-tube.svg"
        path.write_text(path.read_text(encoding="utf-8").replace("B08 L04 disturbance tube", "changed"),
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SVG differs from deterministic"):
            stage_mpc03_b08.stage(self.source, self.site)
        self.assertFalse((self.site / stage_mpc03_b08.REPORT_ID).exists())


if __name__ == "__main__":
    unittest.main()

"""Validate the reviewed MPC-03 report staging route."""
import json
from pathlib import Path
import re
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
        report = (route / "index.html").read_text()
        self.assertIn("projected onto intermediate state x1 and terminal state x2 axes", report)
        self.assertNotIn("projected onto initial state and terminal state axes", report)
        page = (self.site / "examples/index.html").read_text()
        self.assertEqual(page.count('id="mpc03-open-loop-pilot-v1"'), 1)
        self.assertIn("../mpc03-open-loop-pilot-v1/index.html", page)

    def test_stage_rejects_a_raw_record_hash_mismatch_before_writing(self):
        (self.source / "pilot-output.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw output differs"):
            stage_mpc03.stage(self.source, self.site)
        self.assertFalse((self.site / stage_mpc03.REPORT_ID).exists())

    def test_saved_projection_matches_literal_endpoints_and_simple_hull(self):
        record = json.loads((self.source / "record.json").read_text(encoding="utf-8"))
        points = stage_mpc03.result_points(record)
        self.assertEqual(points, [
            ("--", 0.875, 1.75), ("-+", 0.875, 2.0),
            ("+-", 1.125, 2.0), ("++", 1.125, 2.25),
        ])
        svg = stage_mpc03.render_svg(record)
        match = re.search(r'<path d="([ML0-9 .-]+Z)" fill="#dce9f7"', svg)
        self.assertIsNotNone(match)
        vertices = [(float(x), float(y)) for x, y in re.findall(r"[ML]([\d.]+) ([\d.]+)", match.group(1))]
        self.assertEqual(vertices, [(237.5, 295.0), (237.5, 230.0), (512.5, 165.0), (512.5, 230.0)])
        def orientation(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        turns = [orientation(vertices[i], vertices[(i + 1) % 4], vertices[(i + 2) % 4])
                 for i in range(4)]
        self.assertTrue(all(turn > 0 for turn in turns))
        self.assertIn("(++) worst", svg)
        self.assertIn("terminal safety x2 &gt;= 1.5", svg)
        self.assertEqual(stage_mpc03.render_svg(record),
                         (self.source / "disturbance-tube.svg").read_text(encoding="utf-8"))

    def test_checked_in_report_and_example_are_record_rendered(self):
        record = json.loads((self.source / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(stage_mpc03.render_html(record),
                         (self.source / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(stage_mpc03.render_svg(record),
                         (ROOT / "docs/examples/mpc03-open-loop-disturbance-tube.svg").read_text(encoding="utf-8"))

    def test_stage_rejects_displayed_values_that_do_not_match_saved_record(self):
        page = self.source / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace("2.25 incumbent", "999 incumbent"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "HTML differs from deterministic"):
            stage_mpc03.stage(self.source, self.site)
        self.assertFalse((self.site / stage_mpc03.REPORT_ID).exists())

    def test_stage_rejects_svg_geometry_that_does_not_match_saved_record(self):
        figure = self.source / "disturbance-tube.svg"
        figure.write_text(figure.read_text(encoding="utf-8").replace("M237.5 295", "M512.5 295"),
                          encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SVG differs from deterministic"):
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

"""Verify the bounded EXP-06 paired artifact and saved visual output."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "reports/algorithm-results/exp06-geometry-pilot-20261029"
PAPER_BUNDLE = ROOT / "reports/algorithm-results/exp06-it17-paper-reducers-20261029-r1"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render = load("exp06_saved_renderer_test", ROOT / "scripts/reports/exp06/render_saved.py")
paper_render = load("exp06_paper_saved_renderer_test", ROOT / "scripts/reports/exp06/render_paper_saved.py")
stage = load("exp06_stage_test", ROOT / "scripts/reports/stage_exp06.py")
source_indices = load("exp06_source_indices_test", ROOT / "scripts/reports/exp06/check_source_indices.py")


class Exp06PilotTest(unittest.TestCase):
    def test_source_index_checker_rejects_an_out_of_range_quickhull_index(self) -> None:
        self.assertEqual(source_indices.check([0, 1, 9], 9), {
            "schema": "csl.exp06-source-index-check/1",
            "status": "incorrect",
            "point_count": 9,
            "reported_count": 3,
            "invalid_positions": [2],
        })

    def test_saved_record_has_two_checked_methods_and_all_attempts(self) -> None:
        capture, wire, _spec, manifest, methods, rows = render.read_saved(BUNDLE)
        self.assertEqual(len(manifest["points"]), 9)
        self.assertEqual(len(rows), 12)
        self.assertEqual(set(methods), set(render.METHODS))
        self.assertTrue(all(row["checker"] == "verified" for row in rows))
        for attempt in wire["attempts"]:
            run = json.loads(attempt["run"])
            self.assertEqual(run["result"]["checker"]["budget"], {"max_points": 64})
            self.assertEqual(run["result"]["checker"]["source_index_check"]["status"], "verified")
        self.assertEqual(capture["checker_controls"]["omitted_corner"]["status"], "incorrect")
        self.assertEqual(capture["checker_controls"]["all_redundant_points_retained"]["status"], "verified")
        self.assertIn("inconclusive", capture["timing_comparison"])
        self.assertEqual(wire["schema"], "csl.comparison-record/1")

    def test_saved_renderer_reproduces_only_the_derived_files(self) -> None:
        rendered, report_id = render.render(BUNDLE)
        self.assertTrue(report_id.startswith("exp06-"))
        for name, data in rendered.items():
            self.assertEqual((BUNDLE / name).read_bytes(), data)

    def test_site_stager_copies_verified_report_and_links_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            (site_dir / "index.html").write_text("<!doctype html><html><body><ul></ul></body></html>")
            report_id = stage.stage(BUNDLE, site_dir)
            self.assertTrue((site_dir / report_id / "hulls.svg").is_file())
            index = (site_dir / "index.html").read_text()
            self.assertIn("2D hull illustration", index)
            self.assertIn("paired record", index)

    def test_paper_followup_record_keeps_distinct_rows_and_tie_evidence(self) -> None:
        capture, wire, _spec, _manifest, methods, rows = paper_render.read_saved(PAPER_BUNDLE)
        self.assertEqual(len(capture["method_ids"]), 6)
        self.assertIn("csl.hull.itis17.a43-certified-basis-reuse", methods)
        self.assertIn("csl.hull.itis17.a43-artificial-basis", methods)
        self.assertIn("csl.hull.itis17.a43-largest-norm-tie", methods)
        self.assertIn("csl.hull.itis17.a44-incremental-lp", methods)
        self.assertEqual(len(rows), 36)
        self.assertTrue(all(row["status"] == "completed" and row["checker"] == "verified" for row in rows))
        tie_attempts = [json.loads(item["run"])["result"]["algorithm"]["reduction"]["a43_paper_metrics"]
            for item in wire["attempts"]
            if json.loads(item["run"])["method"]["id"] == "csl.hull.itis17.a43-largest-norm-tie"]
        self.assertEqual(len(tie_attempts), 6)
        self.assertTrue(all(metric["largest_norm_tie_breaks"] > 0 for metric in tie_attempts))
        self.assertFalse(capture["harness_dirty"])

    def test_paper_followup_renderer_and_stager_verify_saved_bundle(self) -> None:
        rendered, report_id = paper_render.render(PAPER_BUNDLE)
        self.assertTrue(report_id.startswith("exp06-"))
        for name, data in rendered.items():
            self.assertEqual((PAPER_BUNDLE / name).read_bytes(), data)
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            (site_dir / "index.html").write_text("<!doctype html><html><body><ul></ul></body></html>")
            staged_id = stage.stage(PAPER_BUNDLE, site_dir, paper_render)
            self.assertEqual(staged_id, report_id)
            self.assertTrue((site_dir / report_id / "hulls.svg").is_file())
            self.assertIn("paper-derived", (site_dir / report_id / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()

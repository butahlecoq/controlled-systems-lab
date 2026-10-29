"""Verify the bounded EXP-06 paired artifact and saved visual output."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "reports/algorithm-results/exp06-geometry-pilot-20261029"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render = load("exp06_saved_renderer_test", ROOT / "scripts/reports/exp06/render_saved.py")
stage = load("exp06_stage_test", ROOT / "scripts/reports/stage_exp06.py")


class Exp06PilotTest(unittest.TestCase):
    def test_saved_record_has_two_checked_methods_and_all_attempts(self) -> None:
        capture, wire, _spec, manifest, methods, rows = render.read_saved(BUNDLE)
        self.assertEqual(len(manifest["points"]), 9)
        self.assertEqual(len(rows), 12)
        self.assertEqual(set(methods), set(render.METHODS))
        self.assertTrue(all(row["checker"] == "verified" for row in rows))
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


if __name__ == "__main__":
    unittest.main()

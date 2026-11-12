from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/source_index_figure.py"
SPEC = importlib.util.spec_from_file_location("source_index_figure", SCRIPT)
source_index_figure = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = source_index_figure
SPEC.loader.exec_module(source_index_figure)


class SourceIndexFigureTests(unittest.TestCase):
    def setUp(self):
        self.records = json.loads((ROOT / "docs/examples/source-index-geometry-2d-records.json").read_text())

    def test_saved_vertices_render_with_correct_cartesian_axes(self):
        svg = source_index_figure.render_svg(self.records)
        self.assertIn('aria-label="Affine image from records"', svg)
        self.assertIn('M456.43,301.50 L599.29,236.50 L599.29,106.50 L456.43,171.50 Z', svg)
        self.assertIn('M773.43,236.50 L916.29,236.50 L916.29,106.50 L773.43,106.50 Z', svg)
        self.assertIn('y coordinate</text>', svg)
        self.assertIn('>x coordinate</text>', svg)
        self.assertIn('Negative y coordinates appear below the horizontal zero axis.', svg)

    def test_rejects_methods_that_disagree_on_the_plotted_geometry(self):
        changed = json.loads(json.dumps(self.records))
        changed["btulshor"]["results"][0]["vertices"][0][1] += 0.01
        with self.assertRaisesRegex(ValueError, "records disagree"):
            source_index_figure.render_svg(changed)

    def test_generated_pages_match_saved_records(self):
        self.assertEqual((ROOT / "docs/examples/source-index-geometry-2d.svg").read_text(),
                         source_index_figure.render_svg(self.records))
        self.assertEqual((ROOT / "docs/examples/source-index-geometry-2d.html").read_text(),
                         source_index_figure.render_html(source_index_figure.render_svg(self.records)))


if __name__ == "__main__":
    unittest.main()

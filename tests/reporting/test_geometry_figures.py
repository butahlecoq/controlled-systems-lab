import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import geometry_figures


class GeometryFigureTests(unittest.TestCase):
    def test_saved_geometry_uses_shared_numeric_axes_and_accessible_scope(self):
        document = {
            "schema": "csl.saved-geometric-plot/1",
            "title": "Saved square and enclosing circle",
            "description": "The circle is an outer enclosure; the square vertices are saved input values.",
            "aspect": "equal",
            "axes": {"x": {"label": "x (unitless)"}, "y": {"label": "y (unitless)"}},
            "series": [
                {"kind": "polygon", "label": "saved square", "color": "#0072B2",
                 "points": [[-1, -1], [1, -1], [1, 1], [-1, 1]], "fill": True},
                {"kind": "circle", "label": "saved outer circle", "color": "#D55E00",
                 "center": [0, 0], "radius": 2},
                {"kind": "points", "label": "saved vertices", "color": "#009E73",
                 "points": [[-1, -1], [1, -1], [1, 1], [-1, 1]]},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "figure"
            receipt = geometry_figures.render(document, ROOT / "scripts/reports/styles/control-v1.json", out)
            self.assertEqual(receipt["quantitative_axis_policy"], "csl-report-quantitative-v1")
            self.assertTrue((out / "geometry.png").is_file())
            svg = ET.parse(out / "geometry.svg").getroot()
            self.assertEqual(svg.attrib["role"], "img")
            text = " ".join(svg.itertext())
            self.assertIn("Saved square and enclosing circle", text)
            self.assertIn("x (unitless); y (unitless)", text)
            self.assertIn("major gridlines", text)
            self.assertIn("outer enclosure", text)
            self.assertEqual(receipt["files"]["geometry.svg"], __import__("hashlib").sha256((out / "geometry.svg").read_bytes()).hexdigest())
            export = json.loads((out / "export.json").read_text())
            self.assertEqual(export, receipt)

    def test_missing_aspect_disclosure_is_rejected_before_writing(self):
        document = {"schema": "csl.saved-geometric-plot/1", "title": "figure",
                    "description": "description", "axes": {"x": {"label": "x"}, "y": {"label": "y"}},
                    "series": [{"kind": "points", "label": "p", "color": "#0072B2", "points": [[0, 0]]}]}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "figure"
            with self.assertRaisesRegex(ValueError, "aspect must be explicit"):
                geometry_figures.render(document, ROOT / "scripts/reports/styles/control-v1.json", out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()

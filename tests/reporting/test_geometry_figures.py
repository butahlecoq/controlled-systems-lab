import hashlib
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import geometry_figures  # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"


class GeometryFigureTests(unittest.TestCase):
    def test_saved_geometry_uses_shared_numeric_axes_and_accessible_scope(self):
        document = {
            "schema": "csl.saved-geometric-plot/1",
            "title": "Saved square and enclosing circle",
            "description": "The circle is an outer enclosure; the square vertices are saved input values.",
            "aspect": "equal",
            "axes": {"x": {"label": "x (unitless)"}, "y": {"label": "y (unitless)"}},
            "series": [
                {
                    "kind": "polygon",
                    "label": "saved square",
                    "color": "#0072B2",
                    "points": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
                    "fill": True,
                },
                {
                    "kind": "circle",
                    "label": "saved outer circle",
                    "color": "#D55E00",
                    "center": [0, 0],
                    "radius": 2,
                },
                {
                    "kind": "points",
                    "label": "saved vertices",
                    "color": "#009E73",
                    "points": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
                },
                {
                    "kind": "path",
                    "label": "saved path",
                    "color": "#CC79A7",
                    "points": [[-1, 0], [0, 1], [3, 1]],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "figure"
            receipt = geometry_figures.render(
                document, ROOT / "scripts/reports/styles/control-v1.json", out
            )
            self.assertEqual(receipt["quantitative_axis_policy"], "csl-report-quantitative-v1")
            self.assertTrue((out / "geometry.png").is_file())
            svg = ET.parse(out / "geometry.svg").getroot()
            self.assertEqual(svg.attrib["role"], "img")
            title_id, description_id = svg.attrib["aria-labelledby"].split()
            self.assertEqual(
                svg.findtext(f"{SVG}title[@id='{title_id}']"), "Saved square and enclosing circle"
            )
            description = svg.findtext(f"{SVG}desc[@id='{description_id}']", default="")
            self.assertIn("x (unitless); y (unitless)", description)
            self.assertIn("major gridlines", description)
            self.assertIn("outer enclosure", description)
            for axis_id, label in (
                ("matplotlib.axis_1", "x (unitless)"),
                ("matplotlib.axis_2", "y (unitless)"),
            ):
                [axis] = svg.findall(f".//{SVG}g[@id='{axis_id}']")
                visible_text = [element.text for element in axis.iter(f"{SVG}text")]
                self.assertIn(label, visible_text)
                self.assertGreaterEqual(
                    sum(
                        bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text or ""))
                        for text in visible_text
                    ),
                    3,
                )
                self.assertGreaterEqual(
                    sum(
                        "#8290a3" in element.get("style", "") for element in axis.iter(f"{SVG}path")
                    ),
                    2,
                )
            [plane] = svg.findall(f".//{SVG}g[@id='axes_1']")
            [trajectory] = [
                element
                for element in plane.iter(f"{SVG}path")
                if "clip-path" in element.attrib and "#cc79a7" in element.get("style", "")
            ]
            x0, y0, x1, y1, x2, y2 = [
                float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", trajectory.attrib["d"])
            ]
            # The first saved step travels one unit along each axis. The second is horizontal.
            self.assertGreater(x1, x0)
            self.assertAlmostEqual(x1 - x0, y0 - y1, places=5)
            self.assertAlmostEqual(x2 - x1, 3 * (x1 - x0), places=5)
            self.assertEqual(y2, y1)
            self.assertEqual(
                receipt["files"],
                {
                    name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                    for name in ("geometry.svg", "geometry.png")
                },
            )
            export = json.loads((out / "export.json").read_text())
            self.assertEqual(export, receipt)

    def test_missing_aspect_disclosure_is_rejected_before_writing(self):
        document = {
            "schema": "csl.saved-geometric-plot/1",
            "title": "figure",
            "description": "description",
            "axes": {"x": {"label": "x"}, "y": {"label": "y"}},
            "series": [{"kind": "points", "label": "p", "color": "#0072B2", "points": [[0, 0]]}],
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "figure"
            with self.assertRaisesRegex(ValueError, "aspect must be explicit"):
                geometry_figures.render(
                    document, ROOT / "scripts/reports/styles/control-v1.json", out
                )
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()

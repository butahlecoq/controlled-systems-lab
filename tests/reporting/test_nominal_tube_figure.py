"""Tests the published full-state nominal H-tube geometry figure."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/nominal_tube_figure.py"
SPEC = importlib.util.spec_from_file_location("nominal_tube_figure", SCRIPT)
FIGURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIGURE)

class NominalTubeFigureTests(unittest.TestCase):
    def test_saved_geometry_and_separate_nonlinear_overlay_are_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp) / "tube"
            data = FIGURE.build(FIGURE.CAPTURE, FIGURE.ATTEMPT, stem)
            self.assertEqual(len(data["stages"]), 31)
            self.assertEqual(data["time"]["transitions"], 30)
            self.assertEqual(data["objective_metadata"]["optimizer_selection"], "not_used")
            self.assertEqual(data["nonlinear_nmpc_overlay"]["physical_states"],
                             FIGURE.load(FIGURE.ATTEMPT)["physical_states"])
            self.assertEqual(data["nonlinear_nmpc_overlay"]["attempt_id"], FIGURE.load(FIGURE.ATTEMPT)["attempt_id"])
            self.assertTrue(all(data["stages"][i][key]["vertex_check"]["within_tolerance"]
                                for i in range(31) for key in ("F", "B", "I")))
            self.assertEqual(data["stages"][15]["F"]["H"]["A"],
                             FIGURE.load(FIGURE.CAPTURE / "raw-record.json")["stages"][15]["forward"]["output"]["inequalities"]["A"])
            tree = ET.parse(stem.with_suffix(".svg"))
            self.assertTrue(any(node.tag.endswith("polygon") for node in tree.iter()))
            page = stem.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("../../examples.css", page)
            self.assertIn("display check only", page)
            self.assertIn("Separate nonlinear replay", page)
            self.assertIn("Initial physical state x", page)
            self.assertIn("soft objective target", page)
            self.assertIn("distinct from the physical terminal feasible box", page)
            self.assertIn("Initial physical state x", page)
            self.assertIn("soft objective target", page)
            self.assertIn("distinct from the physical terminal feasible box", page)

    def test_figure_index_exposes_the_saved_geometry_route(self):
        index = json.loads((ROOT / "docs/examples/closed-loop/figure-index.json").read_text())
        entry = next(item for item in index["figures"] if item["id"] == "nominal-h-tube-lotka")
        for route_key in ("href", "svg_href", "plotted_data_href"):
            route = ROOT / "docs" / entry[route_key]
            self.assertTrue(route.is_file(), entry[route_key])
        self.assertEqual(entry["availability"], "ready")
        self.assertIn("full-state intersections I[0..30] before projection", entry["layer_scopes"])

if __name__ == "__main__":
    unittest.main()

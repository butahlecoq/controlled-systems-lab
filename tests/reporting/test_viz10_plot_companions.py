import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import viz10_plot_companions as renderer


class Viz10SavedPlotCompanionTests(unittest.TestCase):
    def test_fuel_figure_coordinates_match_saved_four_state_rows(self):
        b07_path = ROOT / "reports/algorithm-results/b07-owner-approved-eight-case-v1/results.jsonl"
        b09_path = ROOT / "reports/algorithm-results/b09-a08-source-reference-4818ddde/results.jsonl"

        self.assertEqual([(pair[0], pair[1]) for pair in renderer.B07_PAIRS], [(0, 1), (2, 3)])
        self.assertEqual([(pair[0], pair[1]) for pair in renderer.FUEL_PAIRS], [(0, 2), (1, 3)])

        b07 = renderer.load_jsonl(b07_path)[0]["winner_terminal_vertices_x1_x3_x2_x4"]
        self.assertEqual(renderer.project_coordinates(b07, 0, 1), [(row[0], row[1]) for row in b07])
        self.assertEqual(renderer.project_coordinates(b07, 2, 3), [(row[2], row[3]) for row in b07])

        b09 = renderer.load_jsonl(b09_path)[0]["winner_terminal_vertices_x1_x2_x3_x4"]
        self.assertEqual(renderer.project_coordinates(b09, 0, 2), [(row[0], row[2]) for row in b09])
        self.assertEqual(renderer.project_coordinates(b09, 1, 3), [(row[1], row[3]) for row in b09])

    def test_companions_replay_saved_records_with_quantitative_axes_and_provenance(self):
        with tempfile.TemporaryDirectory(prefix="viz10-render-", dir=ROOT) as temporary:
            out = Path(temporary) / "gallery"
            renderer.build(out)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "csl.viz10-gallery/1")
            self.assertEqual(manifest["quantitative_axis_policy"], "csl-report-quantitative-v1")
            self.assertEqual(len([name for name in manifest["figures"] if name.endswith(".svg")]), 15)
            self.assertEqual(len([name for name in manifest["figures"] if name.endswith(".png")]), 15)

            b07 = (out / "b07-b07-reconstruction-s0-l0-d0.svg").read_text(encoding="utf-8")
            self.assertIn("Oxidizer flow x₁ (kg/s)", b07)
            self.assertIn("Fuel flow x₃ (kg/s)", b07)
            self.assertIn("Oxidizer stock balance x₂ (kg)", b07)
            self.assertIn("Fuel stock balance x₄ (kg)", b07)
            self.assertIn("B07 four-state fuel projections", b07)

            b09 = (out / "b09-lambda-0.svg").read_text(encoding="utf-8")
            self.assertIn("Open-loop replay terminal state", b09)
            self.assertIn("Receding-horizon replay terminal state", b09)
            self.assertIn("no projected hull is recomputed", b09.lower())

            for path, expected_hash in manifest["inputs"].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected_hash, path)
            for name, expected_hash in manifest["figures"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), expected_hash, name)
            self.assertIn("../../issue6-b07-reference-a394915af10636430cdcd757d95a9d987eaa6c4c0b742bef7ba1aa04638a2cdd/index.html",
                          (out / "index.html").read_text(encoding="utf-8"))
            self.assertIn("No solver, hull query, numerical experiment or benchmark ran during rendering",
                          (out / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

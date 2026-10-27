from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/viz04"))
import render_saved


class Viz04RendererTests(unittest.TestCase):
    def test_matching_physical_units_get_equal_aspect_and_disclosed_scale(self):
        class Axis:
            def __init__(self):
                self.aspect = None

            def set_aspect(self, aspect, adjustable):
                self.aspect = (aspect, adjustable)

        value = render_saved.load(ROOT / "docs/examples/viz04-replay-comparison.json")
        coordinates = value["state_coordinates"]
        axis = Axis()
        note = render_saved.set_coordinate_aspect(axis, coordinates[0], coordinates[2])
        self.assertEqual(axis.aspect, ("equal", "box"))
        self.assertEqual(note, "Equal x/y scale because paired coordinates share units.")

        axis = Axis()
        note = render_saved.set_coordinate_aspect(axis, coordinates[0], coordinates[1])
        self.assertIsNone(axis.aspect)
        self.assertIn("Independent x/y scales", note)

    def test_figure_caption_discloses_equal_scale_and_selected_paths(self):
        page = (ROOT / "docs/examples/viz04-replay-comparison.html").read_text(encoding="utf-8")
        self.assertIn("equal x/y scaling because its paired coordinates share units", page)
        self.assertIn("not boundaries of reachable sets", page)


if __name__ == "__main__":
    unittest.main()

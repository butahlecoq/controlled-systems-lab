from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RENDERER_PATH = ROOT / "scripts/reports/viz04/render_saved.py"
SPEC = importlib.util.spec_from_file_location("viz04_render_saved", RENDERER_PATH)
render_saved = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_saved)


class Viz04RendererTests(unittest.TestCase):
    def test_renderer_accepts_legacy_v1_and_current_v2_artifacts(self):
        current_path = ROOT / "docs/examples/viz04-replay-comparison.json"
        current = json.loads(current_path.read_text(encoding="utf-8"))
        self.assertEqual(current["schema"], "csl.viz04-replay-comparison/2")
        self.assertEqual(render_saved.load(current_path)["schema"], current["schema"])

        current["schema"] = "csl.viz04-replay-comparison/1"
        for witness in current["witnesses"]:
            witness["replay"].pop("numerical_policy")
            witness["replay"].pop("integration_residual")
        with tempfile.TemporaryDirectory() as temporary:
            legacy_path = Path(temporary) / "legacy.json"
            legacy_path.write_text(json.dumps(current), encoding="utf-8")
            self.assertEqual(render_saved.load(legacy_path)["schema"], current["schema"])

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

    def test_checked_in_svg_matches_saved_artifact_renderer(self):
        artifact = ROOT / "docs/examples/viz04-replay-comparison.json"
        checked_in = ROOT / "docs/examples/viz04-replay-comparison.svg"
        with tempfile.TemporaryDirectory() as temporary:
            rendered = Path(temporary) / "replay.svg"
            render_saved.render(render_saved.load(artifact), rendered)
            self.assertEqual(rendered.read_bytes(), checked_in.read_bytes())


if __name__ == "__main__":
    unittest.main()

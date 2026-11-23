from __future__ import annotations

import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/campaign_graph_figures.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("campaign_graph_figures", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Cannot load campaign figure renderer from {SCRIPT}")
figures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = figures
SPEC.loader.exec_module(figures)
RENDERER_SCRIPT = ROOT / "scripts/reports/render_full_profile_campaign.py"
RENDERER_SPEC = importlib.util.spec_from_file_location(
    "render_full_profile_campaign", RENDERER_SCRIPT
)
if RENDERER_SPEC is None or RENDERER_SPEC.loader is None:
    raise ImportError(f"Cannot load full-profile renderer from {RENDERER_SCRIPT}")
renderer = importlib.util.module_from_spec(RENDERER_SPEC)
sys.modules[RENDERER_SPEC.name] = renderer
RENDERER_SPEC.loader.exec_module(renderer)


class PairedCampaignFigureTests(unittest.TestCase):
    def test_fuel_pair_uses_mass_and_flow_coordinates_in_one_accessible_svg(self):
        self.assertEqual(
            [plane["indices"] for plane in renderer.FUEL_PAIRED_PLANES], [[0, 1], [2, 3]]
        )
        nodes = [
            {
                "absolute_stage": stage,
                "node_id": f"n{stage}",
                "state": [1 + stage, 2 + stage, 3 + stage, 4 + stage],
                "backward_viable": stage == 0,
            }
            for stage in range(2)
        ]
        plan = [[1, 2, 3, 4], [2, 3, 4, 5]]
        replay = [[1, 2, 3, 4], [2.1, 3.1, 4.1, 5.1]]
        panels = [
            (
                plane["id"],
                figures.draw_svg(
                    plane["id"],
                    "fuel-test",
                    plane,
                    nodes,
                    plan,
                    replay,
                    final_stage=1,
                    compact=True,
                ),
            )
            for plane in renderer.FUEL_PAIRED_PLANES
        ]
        paired = figures.draw_paired_svg("Fuel transfer · exact polytope", panels)

        self.assertIn('aria-labelledby="paired-title paired-desc"', paired)
        self.assertIn("Oxidizer mass mₒₓ", paired)
        self.assertIn("Fuel mass m_f", paired)
        self.assertIn("Oxidizer flow qₒₓ", paired)
        self.assertIn("Fuel flow q_f", paired)
        self.assertIn("Selected plan", paired)
        self.assertIn("Observed replay", paired)
        ET.fromstring(paired)
        self.assertEqual(paired.count('id="title"'), 0)
        self.assertEqual(paired.count('viewBox="0 0 620 500"'), 2)

    def test_box_outer_tubes_fit_the_same_paired_projection_layout(self):
        tubes = [
            {
                "stages": [
                    {"lower": [1, 2, 3, 4], "upper": [2, 3, 4, 5]},
                    {"lower": [1.2, 2.1, 3.2, 4.1], "upper": [2.2, 3.1, 4.2, 5.1]},
                ]
            }
        ]
        plan = [[1.5, 2.5, 3.5, 4.5], [1.8, 2.8, 3.8, 4.8]]
        panels = [
            (
                plane["id"],
                renderer.draw_box_tube_svg(plane["id"], plane, tubes, plan, plan, compact=True),
            )
            for plane in renderer.FUEL_PAIRED_PLANES
        ]

        paired = figures.draw_paired_svg("Fuel transfer · box", panels)

        self.assertEqual(paired.count('viewBox="0 0 620 500"'), 2)
        self.assertIn("Outer fixed-plan trajectory enclosures", paired)
        self.assertIn("Fuel flow q_f", paired)
        ET.fromstring(paired)


if __name__ == "__main__":
    unittest.main()

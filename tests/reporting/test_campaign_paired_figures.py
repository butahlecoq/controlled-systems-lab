from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

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
SAVED_DATA_RENDERER = ROOT / "scripts/reports/render_campaign_paired_projection.py"


class PairedCampaignFigureTests(unittest.TestCase):
    def test_campaign_dashboard_distinguishes_graph_and_box_evidence(self):
        dashboard = (ROOT / "docs/examples/closed-loop/campaign-2026-11-18/index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Graph-backed representation cards use one completed native graph", dashboard)
        self.assertIn("Box cards instead show a fixed-plan outer tube", dashboard)
        self.assertNotIn("Each representation card uses one completed native graph", dashboard)

    def test_saved_data_command_recreates_graph_and_box_pairs(self):
        reports = ROOT / "docs/examples/closed-loop/campaign-2026-11-18"
        for representation in ("exact-polytope", "box"):
            figure_id = f"syn-nl-fuel-01-{representation}-paired"
            data = reports / "raw/plotted-data" / f"syn-nl-fuel-01-{representation}.json"
            expected_svg = reports / f"{figure_id}.svg"
            with self.subTest(representation=representation), TemporaryDirectory() as temporary:
                staged = Path(temporary) / "campaign"
                for folder in ("raw/plotted-data", "raw/task-contracts"):
                    (staged / folder).mkdir(parents=True)
                for source in (
                    data,
                    reports / "raw/task-contracts/syn-nl-fuel-01.json",
                    reports / f"{figure_id}.json",
                    reports / "provenance-manifest.json",
                    reports / "provenance-manifest.json.sha256",
                ):
                    relative = source.relative_to(reports)
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                staged_data = staged / data.relative_to(reports)
                subprocess.run(
                    [sys.executable, str(SAVED_DATA_RENDERER), "--data", str(staged_data)],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                output = staged / f"{figure_id}.svg"
                self.assertEqual(output.read_bytes(), expected_svg.read_bytes())
                provenance_path = staged / f"{figure_id}.json"
                provenance = json.loads(provenance_path.read_text())
                self.assertEqual(
                    hashlib.sha256(output.read_bytes()).hexdigest(), provenance["svg_sha256"]
                )
                self.assertEqual(
                    hashlib.sha256((staged / f"{figure_id}.html").read_bytes()).hexdigest(),
                    json.loads((staged / "provenance-manifest.json").read_text())["files_sha256"][
                        f"{figure_id}.html"
                    ],
                )
                html = (staged / f"{figure_id}.html").read_text()
                self.assertIn("render_campaign_paired_projection.py", html)
                self.assertIn("mₒₓ", html)
                self.assertIn("100 kg", html)
                if representation == "box":
                    self.assertIn("no finite-graph marks", html)
                    self.assertNotIn("backward-viable nodes are shown", html)
                else:
                    self.assertIn("backward-viable nodes are shown", html)
                ET.fromstring(output.read_text(encoding="utf-8"))

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

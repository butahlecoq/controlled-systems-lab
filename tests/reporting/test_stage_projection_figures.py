from __future__ import annotations

import json
from html import unescape
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.reports import stage_projection_data as data
from scripts.reports.stage_projection_figures import (
    _limits,
    _trajectory_points,
    render_batch,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/artifacts/fixtures/stage-projection-batch-v1.json"
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
IDENTITY = {
    "expected_run_id": "run-1",
    "expected_problem_id": "fuel",
    "expected_request_id": "stage-batch",
    "expected_route_id": "fuel-route",
    "expected_record_schema": "csl.run-statistics/7",
    "expected_source_sha256": "a" * 64,
}


class StageProjectionFiguresTests(unittest.TestCase):
    def load_fixture(self) -> dict:
        return data.read_stage_projection_batch(FIXTURE, **IDENTITY)

    def render(self, batch: dict, output: Path) -> list[dict]:
        input_path = output.parent / "validated-input.json"
        input_path.write_bytes(data.dumps_stage_projection_batch(batch, **IDENTITY))
        return render_batch(input_path, output, expected_identity=IDENTITY, style_path=STYLE)

    def test_saved_batch_renders_accessible_svg_png_and_offline_html(self):
        batch = self.load_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            outputs = self.render(batch, output)

            self.assertEqual(len(outputs), len(batch["requested_pairs"]))
            self.assertTrue((output / "index.html").is_file())
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn(str(output.resolve()), html)
            self.assertIn("R0 · initial", outputs[0]["description"])
            self.assertIn("R3 · final", outputs[0]["description"])
            self.assertIn("separate from set geometry", outputs[0]["description"])
            self.assertIn("@media(max-width:640px)", html)
            self.assertIn("@media print", html)
            for item in outputs:
                svg_path, png_path = output / item["svg"], output / item["png"]
                svg_root = ET.parse(svg_path).getroot()
                self.assertEqual(svg_root.get("role"), "img")
                self.assertIn("aria-labelledby", svg_root.attrib)
                self.assertTrue(png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertIn(item["description"], unescape(html))
            receipt = json.loads((output / "render-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["input_content_sha256"], batch["content_sha256"])
            self.assertEqual(receipt["quantitative_axis_policy"], "csl-report-quantitative-v1")
            self.assertEqual(receipt["output_directory"], str(output.resolve()))

    def test_unbounded_and_unavailable_outcomes_are_labelled_without_a_boundary(self):
        batch = self.load_fixture()
        unbounded = batch["records"][0]["outcome"]["components"][0]
        unbounded["kind"] = "unbounded"
        unbounded["rays"] = [[1.0, 0.0]]
        batch["records"][1]["outcome"] = {
            "status": "unavailable", "kind": "missing",
            "explanation": "stage was not supplied by this route",
        }
        batch["records"][1]["source_set_ids"] = []
        batch = data.loads_stage_projection_batch(
            data.dumps_stage_projection_batch(batch, **IDENTITY), **IDENTITY)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            self.render(batch, output)
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("unbounded", html)
            self.assertIn("missing", html)
            self.assertIn("no boundary is reconstructed", html)
            svg = next(output.glob("*.svg")).read_text(encoding="utf-8")
            self.assertIn("ray 1 direction", svg)

    def test_optional_materialization_failure_is_visible_with_projection_success(self):
        batch = self.load_fixture()
        outcome = batch["records"][0]["outcome"]
        outcome["components"] = []
        outcome["materialization_failure"] = {
            "kind": "stopped", "explanation": "converter resource limit",
            "stop_reason": "resource_limit",
        }
        batch = data.loads_stage_projection_batch(
            data.dumps_stage_projection_batch(batch, **IDENTITY), **IDENTITY)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            rendered = self.render(batch, output)
            self.assertIn("V materialization stopped", rendered[0]["description"])
            self.assertIn("converter resource limit (resource_limit)", rendered[0]["description"])
            svg_root = ET.parse(output / rendered[0]["svg"]).getroot()
            visible_text = " ".join(node.text or "" for node in svg_root.iter()
                                     if node.tag.endswith("}text"))
            self.assertIn("V MATERIALIZATION STOPPED", visible_text)
            self.assertIn("converter resource limit", visible_text)

    def test_coordinate_order_and_negative_values_are_preserved(self):
        trajectory = {"coordinate_ids": ["x0", "x2"], "points": [[-4.0, 3.0], [2.0, -1.0]]}
        self.assertEqual(_trajectory_points(trajectory, "x2", "x0"), [[3.0, -4.0], [-1.0, 2.0]])
        self.assertIsNone(_trajectory_points(trajectory, "x1", "x2"))
        low, high = _limits([-9.0, 2.0])
        self.assertLess(low, -9.0)
        self.assertGreater(high, 2.0)

    def test_negative_fuel_stock_values_remain_visible_in_the_svg(self):
        batch = self.load_fixture()
        batch["coordinates"][0].update(name="fuel stock A", unit="kg")
        batch["coordinates"][2].update(name="fuel stock B", unit="kg")
        batch = data.loads_stage_projection_batch(
            data.dumps_stage_projection_batch(batch, **IDENTITY), **IDENTITY)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            rendered = self.render(batch, output)
            svg_root = ET.parse(output / rendered[0]["svg"]).getroot()
            text = " ".join(node.text or "" for node in svg_root.iter()
                             if node.tag.endswith("}text"))
            self.assertIn("fuel stock A (kg)", text)
            self.assertIn("fuel stock B (kg)", text)
            self.assertTrue("−" in text or "-" in text, text)

    def test_each_requested_pair_gets_its_own_figure_in_requested_order(self):
        batch = self.load_fixture()
        batch["requested_pairs"].append([2, 0])
        extra = []
        for row in batch["records"]:
            copy = json.loads(json.dumps(row))
            copy["pair_index"] = 1
            for evidence in copy["outcome"].get("evidence", []):
                evidence["request_id"] = f"stage-batch/pair/1/stage/{row['stage']}"
                evidence["ideal_output_id"] = f"stage-projection/pair/1/stage/{row['stage']}"
            for component in copy["outcome"].get("components", []):
                component["component_id"] = f"stage-projection/pair/1/stage/{row['stage']}"
            extra.append(copy)
        by_stage_pair = {(row["stage"], row["pair_index"]): row
                         for row in batch["records"] + extra}
        batch["records"] = [by_stage_pair[(stage, pair)]
                            for stage in range(len(batch["stage_axis"]["points"]))
                            for pair in range(len(batch["requested_pairs"]))]
        batch = data.loads_stage_projection_batch(
            data.dumps_stage_projection_batch(batch, **IDENTITY), **IDENTITY)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            rendered = self.render(batch, output)
            self.assertEqual([item["svg"] for item in rendered], [
                "projection-01-x0-x2.svg", "projection-02-x2-x0.svg"])
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("oxidizer flow × fuel flow", html)
            self.assertIn("fuel flow × oxidizer flow", html)

    def test_renderer_rejects_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                self.render(self.load_fixture(), output)

    def test_offline_command_prints_absolute_artifact_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "command-output"
            environment = os.environ.copy()
            environment["MPLCONFIGDIR"] = str(Path(temporary) / "mpl-config")
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/reports/render_stage_projections.py"),
                "--input", str(FIXTURE), "--out", str(output),
                "--expected-run-id", IDENTITY["expected_run_id"],
                "--expected-problem-id", IDENTITY["expected_problem_id"],
                "--expected-request-id", IDENTITY["expected_request_id"],
                "--expected-route-id", IDENTITY["expected_route_id"],
                "--expected-record-schema", IDENTITY["expected_record_schema"],
                "--expected-source-sha256", IDENTITY["expected_source_sha256"],
            ], cwd=ROOT, env=environment, capture_output=True, text=True, check=True)
            self.assertIn(str((output / "index.html").resolve()), result.stdout)
            self.assertIn(str((output / "render-manifest.json").resolve()), result.stdout)
            self.assertIn(str((output / "projection-01-x0-x2.svg").resolve()), result.stdout)
            self.assertTrue((output / "projection-01-x0-x2.png").is_file())


if __name__ == "__main__":
    unittest.main()

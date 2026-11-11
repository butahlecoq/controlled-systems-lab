"""Focused checks for the source-bound layered fuel demonstration."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
from scripts.reports.fuel_reachability_layers import capture


class FuelReachabilityLayersTests(unittest.TestCase):
    def test_render_output_directory_contains_its_styles_and_local_assets(self):
        record_path = ROOT / "docs/examples/fuel-reachability-layers/plot-data.json"
        original = record_path.read_bytes()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "custom-output"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/reports/fuel_reachability_layers.py"),
                 "render", "--input", str(record_path), "--out-dir", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("<style>", page)
            self.assertIn((ROOT / "docs/examples/examples.css").read_text(encoding="utf-8"), page)
            self.assertNotIn('href="../examples.css"', page)
            self.assertIn('href="../../index.html">Learn</a>', page)
            self.assertIn('href="../index.html">Examples</a>', page)
            for name in ("plot-data.json", "fuel-reachability-layers-model.json",
                         "fuel-reachability-x1-x2.svg", "fuel-reachability-x1-x2.png",
                         "fuel-reachability-x3-x4.svg", "fuel-reachability-x3-x4.png"):
                self.assertTrue((output / name).is_file(), name)
        self.assertEqual(record_path.read_bytes(), original)

    def test_capture_optimizes_the_model_target_and_objective_matrix(self):
        model = json.loads((ROOT / "docs/examples/fuel-reachability-layers-model.json")
                           .read_text(encoding="utf-8"))
        model["target"] = [29.0, 0.0, 21.0, 0.0]
        model["terminal_objective_matrix"] = np.eye(4).tolist()

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            model_path = directory / "model.json"
            record_path = directory / "plot-data.json"
            model_path.write_text(json.dumps(model), encoding="utf-8")
            record = capture(model_path, record_path)
            self.assertTrue(record_path.is_file())

        terminal = np.asarray(record["optimal"]["terminal_state"], dtype=float)
        target = np.asarray(model["target"], dtype=float)
        objective_matrix = np.asarray(model["terminal_objective_matrix"], dtype=float)
        objective = float((terminal - target) @ objective_matrix @ (terminal - target))
        self.assertAlmostEqual(record["optimal"]["objective"], objective, places=10)
        self.assertEqual(record["model"]["target"], model["target"])
        controls = np.asarray(record["optimal"]["controls"], dtype=float)
        A = np.asarray(model["A"], dtype=float)
        B = np.asarray(model["B"], dtype=float)
        initial = np.asarray(model["initial_state"], dtype=float)
        control_map = np.column_stack([
            np.linalg.matrix_power(A, 2) @ B,
            A @ B,
            B,
        ])
        gradient = 2 * control_map.T @ objective_matrix @ (terminal - target)
        lower, upper = model["control_bounds"]
        for control, derivative in zip(controls, gradient, strict=True):
            if np.isclose(control, lower, atol=1e-8):
                self.assertGreaterEqual(derivative, -1e-8)
            elif np.isclose(control, upper, atol=1e-8):
                self.assertLessEqual(derivative, 1e-8)
            else:
                self.assertAlmostEqual(derivative, 0.0, places=8)
        state = initial
        for control in controls:
            state = A @ state + B * control
            self.assertTrue(28.0 < state[0] < 32.0)
            self.assertTrue(18.0 < state[2] < 21.0)


if __name__ == "__main__":
    unittest.main()

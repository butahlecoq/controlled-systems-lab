"""Focused checks for the source-bound layered fuel demonstration."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.reports.fuel_reachability_layers import capture


ROOT = Path(__file__).resolve().parents[2]


class FuelReachabilityLayersTests(unittest.TestCase):
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
        objective = float((terminal - target) @ (terminal - target))
        self.assertAlmostEqual(record["optimal"]["objective"], objective, places=10)
        self.assertEqual(record["model"]["target"], model["target"])


if __name__ == "__main__":
    unittest.main()

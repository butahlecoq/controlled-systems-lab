from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))

import nominal_tube_source as source
from contracts import load_task
from task_models import prediction_receipt


class NominalTubeSourceTests(unittest.TestCase):
    def test_request_preserves_original_grid_physical_coefficients_and_all_roles(self):
        task = load_task("syn-nl-lv-01")
        receipt = prediction_receipt(task)
        request = source.build_request(task)
        self.assertEqual(request["time"], {
            "unit": "day", "dt": 0.1, "intervals": 30, "final_time": 3,
            "grid": [0.1 * stage for stage in range(31)],
        })
        self.assertEqual(len(request["physical_coefficients"]), 30)
        self.assertEqual(request["physical_coefficients"], receipt["physical_coefficients"])
        self.assertEqual(request["state_coordinates"], [
            {"name": "P", "unit": "thousand individuals", "scale": 100,
             "initial": 120, "bounds": [0, 200]},
            {"name": "R", "unit": "thousand individuals", "scale": 80,
             "initial": 60, "bounds": [0, 150]},
        ])
        self.assertEqual(request["control_constraints"], [[0, 0.05]])
        self.assertEqual(request["initial_state"], [120, 60])
        self.assertEqual(request["profile"]["action_profile"], "continuous_box_all_admissible_controls")
        self.assertEqual(request["profile"]["optimizer_selection"], "not_used")
        self.assertEqual(request["source"]["plant_model_id"], "syn-nl-lv-01/ode/1")
        self.assertEqual(request["source"]["predictor_model_id"], "syn-nl-lv-01/frozen-coexistence-affine/1")

    def test_physical_terminal_bounds_are_distinct_from_complete_source_cost(self):
        task = load_task("syn-nl-lv-01")
        request = source.build_request(task)
        self.assertEqual(request["terminal_feasibility"]["bounds"], [[0, 200], [0, 150]])
        self.assertNotEqual(request["terminal_feasibility"]["bounds"],
            request["objective_metadata"]["soft_terminal_target"])
        self.assertEqual(request["objective_metadata"]["source_objective"], task["objective"])
        self.assertEqual(request["objective_metadata"]["source_objective"]["source_definition"]["running_weight"], 0.05)
        self.assertEqual(request["objective_metadata"]["source_objective"]["running_stage_range"], [0, 29])
        self.assertEqual(request["objective_metadata"]["optimizer_selection"], "not_used")

    def test_rejects_finite_or_different_task_instead_of_relabeling_profile(self):
        task = load_task("syn-nl-lv-01")
        changed = copy.deepcopy(task)
        changed["task_id"] = "syn-nl-lv-01/finite"
        with self.assertRaisesRegex(ValueError, "original Lotka task"):
            source.build_request(changed)

    def test_saved_nonlinear_nmpc_record_is_read_by_fixed_path_and_hash(self):
        record = source.read_saved_nmpc()
        self.assertEqual(record["path"], source.SAVED_NMPC.as_posix())
        self.assertEqual(record["sha256"], source.SAVED_NMPC_SHA256)
        attempt = record["record"]
        self.assertEqual(attempt["task_sha256"], source.SAVED_NMPC_TASK_SHA256)
        self.assertEqual(attempt["model_id"], "syn-nl-lv-01/ode/1")
        self.assertEqual(attempt["action_profile_id"], "syn-nl-lv-01/continuous-receding/1/continuous-control/1")
        self.assertEqual(len(attempt["controls"]), 30)
        self.assertEqual(len(attempt["physical_states"]), 31)


if __name__ == "__main__":
    unittest.main()

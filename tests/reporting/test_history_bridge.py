"""Native analytic full-cost history probe; requires the built bridge."""
import json
import os
import subprocess
import unittest


@unittest.skipUnless(os.environ.get("CSL_NATIVE_POLICY_BRIDGE"), "native bridge not built")
class HistoryBridgeTest(unittest.TestCase):
    def test_continuous_quadratic_tradeoff_uses_full_feasible_relation(self):
        request = {"mode": "continuous-history/1", "task_id": "analytic", "task_sha256": "analytic",
            "problem_id": "analytic", "request_id": "analytic", "controller_id": "analytic",
            "action_profile_id": "analytic-continuous", "absolute_update_index": 0,
            "original_horizon": 1, "dt": 1, "observed_physical_state": [0, 0],
            "predictor_stages": [{"A": [[1, 0], [0, 1]], "B": [[1, 0], [0, 1]], "c": [0, 0]}],
            "state_bounds": [None, None], "control_bounds": [[-2, 2], [-2, 2]],
            "terminal_objective": {"kind": "quadratic", "Q": [[2, 0], [0, 2]],
                                   "linear": [-2, 0], "offset": 1},
            "running_cost": {"objective_id": "analytic-cost", "stages": [
                {"stage": 0, "terms": [{"kind": "quadratic", "reference": [0, 0],
                    "scales": [1, 1], "weights": [1, 1], "coefficient": 2}]}]}}
        result = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]], input=json.dumps(request) + "\n",
                                text=True, capture_output=True, check=True)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "accepted", response)
        self.assertAlmostEqual(response["primal"][-2], 1 / 3, places=5)
        self.assertAlmostEqual(response["primal"][-1], 0, places=5)
        self.assertEqual(response["solver_receipt"]["provider"], "csl.convex.highs")
        self.assertEqual(response["history_relation"]["representation"], "polytope-h")
        self.assertAlmostEqual(response["source_cost"]["total"], 2 / 3, places=5)
        request["running_cost"]["stages"][0]["terms"][0]["coefficient"] = 0
        terminal_run = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
            input=json.dumps(request) + "\n", text=True, capture_output=True, check=True)
        terminal_only = json.loads(terminal_run.stdout)
        self.assertEqual(terminal_only["status"], "accepted", terminal_only)
        self.assertAlmostEqual(terminal_only["primal"][-2], 1, places=5)
        self.assertAlmostEqual(terminal_only["primal"][-1], 0, places=5)


if __name__ == "__main__":
    unittest.main()

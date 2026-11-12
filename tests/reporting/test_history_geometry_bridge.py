"""Real coordinator plus original-cost solver on a complete two-state history."""
import json
import os
import subprocess
import sys
import unittest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks/reporting/closed_loop"))
from history_policy import geometry_memberships
from history_norm_solver import solve


@unittest.skipUnless(os.environ.get("CSL_NATIVE_GEOMETRY_BRIDGE"), "geometry bridge not built")
class GeometryBridgeTest(unittest.TestCase):
    def test_real_family_memberships_and_original_history_objective(self):
        request = {"mode": "continuous-history/1", "history_solver": "casadi-ipopt",
            "task_id": "analytic", "task_sha256": "analytic", "problem_id": "analytic",
            "request_id": "analytic", "controller_id": "analytic", "action_profile_id": "continuous",
            "absolute_update_index": 0, "original_horizon": 1, "dt": 1,
            "observed_physical_state": [0, 0],
            "predictor_stages": [{"A": [[1, 0], [0, 1]], "B": [[1, 0], [0, 1]], "c": [0, 0]}],
            "state_bounds": [None, None], "control_bounds": [[-2, 2], [-2, 2]],
            "terminal_objective": {"kind": "quadratic", "Q": [[2, 0], [0, 2]], "linear": [-2, 0], "offset": 1},
            "running_cost": {"objective_id": "analytic-cost", "stages": [
                {"stage": 0, "terms": [{"kind": "quadratic", "reference": [0, 0],
                    "scales": [1, 1], "weights": [1, 1], "coefficient": 2}]}]},
            "geometry_max_generators": 1000}
        for family in ("polytope", "box", "zonotope", "parallelotope", "ellipsoid"):
            with self.subTest(family=family):
                request["geometry_family"] = family
                run = subprocess.run([os.environ["CSL_NATIVE_GEOMETRY_BRIDGE"]],
                    input=json.dumps(request) + "\n", capture_output=True, text=True, check=True)
                response = json.loads(run.stdout)
                self.assertEqual(response["status"], "exported", response)
                geometry = response["geometry"]
                memberships = geometry_memberships(geometry, family, 2, 1)
                self.assertTrue(any(m["providers"] for m in memberships))
                self.assertTrue(any(m["support_calls"] for m in memberships))
                carriers = [carrier for m in memberships for carrier in m["auxiliary_input_carriers"]]
                self.assertTrue(carriers)
                self.assertTrue(all(carrier["representation"] == "polytope-h" and carrier["set_id"]
                                    for carrier in carriers))
                for stage in geometry["stages"]:
                    ids = [membership["set_id"] for membership in stage["memberships"]]
                    self.assertEqual(len(set(ids)), 3)
                    self.assertTrue(all(ids))
                    for membership in stage["memberships"]:
                        h = stage[membership["role"] + "_h"]
                        for cert in membership["support_certificates"]:
                            self.assertEqual(cert["input_set"], h["set_id"])
                            A = np.asarray(h["inequalities"], dtype=float).reshape(-1, 2)
                            E = np.asarray(h["equalities"], dtype=float).reshape(-1, 2)
                            lam = np.asarray(cert["inequality_multipliers"])
                            mu = np.asarray(cert["equality_multipliers"])
                            self.assertTrue(np.all(lam >= 0))
                            residual = np.asarray(cert["direction"]) - A.T @ lam - E.T @ mu
                            check = (lam @ np.asarray(h["upper_bounds"]) + mu @ np.asarray(h["equality_values"])
                                     + np.maximum(residual * cert["carrier_lower"],
                                                  residual * cert["carrier_upper"]).sum())
                            self.assertLessEqual(check, cert["bound"] + 1e-9 * (1 + abs(check)))
                answer = solve(response["history_relation"], response["history_objective"],
                               initial=[0]*6, geometry_memberships=memberships)
                self.assertTrue(answer["success"], answer)
                z = answer["primal"]
                self.assertAlmostEqual(z[2], 1/3, places=5)
                self.assertAlmostEqual(z[3], 0, places=5)
                self.assertAlmostEqual(z[4], z[2], places=6)
                self.assertAlmostEqual(z[5], z[3], places=6)
                self.assertAlmostEqual((z[2]-1)**2 + z[3]**2 + 2*(z[4]**2+z[5]**2),
                                       answer["objective"], places=6)
                self.assertTrue(answer["geometry_validation"]["accepted"])
        request["task_id"] = "env717-earth-orbit/continuous-receding/1"
        request["geometry_family"] = "box"
        run = subprocess.run([os.environ["CSL_NATIVE_GEOMETRY_BRIDGE"]],
            input=json.dumps(request) + "\n", capture_output=True, text=True, check=True)
        response = json.loads(run.stdout)
        self.assertEqual(response["status"], "exported", response)
        rows = geometry_memberships(response["geometry"], "box", 2, 1,
                                    [{"coordinate": 0, "lower_bound": 0, "strict": True}])
        self.assertTrue(all(row["strict_source_domain"][0]["strict"] for row in rows))


    def test_four_state_singular_carriers_preserve_full_cost_for_every_family(self):
        request = {"mode": "continuous-history/1", "history_solver": "casadi-ipopt",
            "task_id": "analytic-four-state", "task_sha256": "analytic-four-state",
            "problem_id": "analytic-four-state", "request_id": "analytic-four-state",
            "controller_id": "analytic", "action_profile_id": "continuous",
            "absolute_update_index": 0, "original_horizon": 1, "dt": 1,
            "observed_physical_state": [0, 0, 0, 0],
            "predictor_stages": [{"A": np.eye(4).tolist(),
                "B": [[1, 0], [0, 1], [0, 0], [0, 0]], "c": [0, 0, 0, 0]}],
            "state_bounds": [None] * 4, "control_bounds": [[-2, 2], [-2, 2]],
            "terminal_objective": {"kind": "quadratic", "Q": (2 * np.eye(4)).tolist(),
                "linear": [-2, 0, 0, 0], "offset": 1},
            "running_cost": {"objective_id": "analytic-cost", "stages": [
                {"stage": 0, "terms": [{"kind": "quadratic", "reference": [0, 0],
                    "scales": [1, 1], "weights": [1, 1], "coefficient": 2}]}]},
            "geometry_max_generators": 1000}
        for family in ("polytope", "box", "zonotope", "parallelotope", "ellipsoid"):
            with self.subTest(family=family):
                request["geometry_family"] = family
                run = subprocess.run([os.environ["CSL_NATIVE_GEOMETRY_BRIDGE"]],
                    input=json.dumps(request) + "\n", capture_output=True, text=True, check=True)
                response = json.loads(run.stdout)
                self.assertEqual(response["status"], "exported", response)
                memberships = geometry_memberships(response["geometry"], family, 4, 1)
                self.assertEqual(len(memberships), 6)
                answer = solve(response["history_relation"], response["history_objective"],
                               initial=[0] * 10, geometry_memberships=memberships)
                self.assertTrue(answer["success"], answer)
                np.testing.assert_allclose(answer["primal"][4:8], [1 / 3, 0, 0, 0], atol=1e-5)
                np.testing.assert_allclose(answer["primal"][8:10], [1 / 3, 0], atol=1e-5)
                self.assertAlmostEqual(answer["objective"], 2 / 3, places=6)
                self.assertTrue(answer["geometry_validation"]["accepted"])


if __name__ == "__main__":
    unittest.main()

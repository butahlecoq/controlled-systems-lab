"""Native analytic full-cost history probe; requires the built bridge."""
import json
import os
import subprocess
import unittest


def analytic_request():
    return {"mode": "continuous-history/1", "history_solver": "csl.convex.highs", "task_id": "analytic", "task_sha256": "analytic",
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


@unittest.skipUnless(os.environ.get("CSL_NATIVE_POLICY_BRIDGE"), "native bridge not built")
class HistoryBridgeTest(unittest.TestCase):
    def test_primal_hint_reaches_highs_and_reports_observed_state_repair(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks/reporting/closed_loop"))
        from history_policy import initial_history
        previous = None
        for stage in range(3):
            horizon = 3 - stage
            request = {"mode": "continuous-history/1", "task_id": "warm", "task_sha256": "warm",
                "problem_id": "warm", "request_id": str(stage), "controller_id": "warm",
                "action_profile_id": "warm", "absolute_update_index": stage, "original_horizon": 3,
                "dt": 1, "observed_physical_state": [0.1*stage, -0.1*stage],
                "predictor_stages": [{"A": [[1, 0], [0, 1]], "B": [[1, 0], [0, 1]], "c": [0, 0]}]*horizon,
                "state_bounds": [None, None], "control_bounds": [[-2, 2], [-2, 2]],
                "terminal_objective": {"kind": "quadratic", "Q": [[0, 0], [0, 0]], "linear": [0, 0], "offset": 0},
                "running_cost": {"objective_id": "warm", "stages": [
                    {"stage": k, "terms": [{"kind": "quadratic", "reference": [0.2*(k+1), -0.1*(k+1)],
                        "scales": [1, 1], "weights": [1, 1], "coefficient": 1}]} for k in range(3)]}}
            initial, _ = initial_history(request, previous)
            request["initial_primal"] = initial.tolist()
            result = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]], input=json.dumps(request)+"\n",
                                    text=True, capture_output=True, check=True)
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], "solved", response)
            self.assertEqual(response["warm_start"]["initial_primal"], initial.tolist())
            raw = response["solver_receipt"]["raw_diagnostics"]
            for phase in ("feasibility", "qp"):
                self.assertIn(f"phase.{phase}.primal_start.api_status=0", raw)
                self.assertIn(f"phase.{phase}.primal_start.retained=true", raw)
                self.assertIn(f"phase.{phase}.primal_start.zero_duals=true", raw)
            self.assertIn("phase.qp.actual_start.value_valid=true", raw)
            self.assertIn("phase.qp.actual_start.basis_valid=true", raw)
            actual_rows = next(line.split("=", 1)[1] for line in raw.splitlines()
                               if line.startswith("phase.qp.actual_start.row_duals="))
            self.assertTrue(all(float(value) == 0 for value in actual_rows.split(",") if value))
            self.assertNotIn("phase.qp.retry=cold_fresh_model", raw)
            if stage:
                self.assertIn("phase.qp.primal_start.repair=feasibility-phase-solution", raw)
                self.assertIn("phase.qp.actual_start.source=feasibility-phase-repair", raw)
            else:
                self.assertIn("phase.qp.actual_start.source=submitted-primal", raw)
            self.assertEqual(len(response["primal"]), (horizon+1)*2+horizon*2)
            for k in range(horizon):
                self.assertAlmostEqual(response["primal"][(horizon+1)*2+k*2], 0.2*(stage+k+1), places=5)
                self.assertAlmostEqual(response["primal"][(horizon+1)*2+k*2+1], -0.1*(stage+k+1), places=5)
            previous = {"stage": stage, "primal": response["primal"]}


    def test_original_task_policy_queries_shift_the_last_accepted_history(self):
        import importlib.util
        import sys
        from pathlib import Path
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks/reporting/closed_loop"))
        from contracts import load_task, manifest_sha256
        from history_policy import HistoryPolicy
        for name in ("syn-nl-lv-01", "syn-nl-fuel-01", "earth-orbit"):
            if name == "earth-orbit" and not importlib.util.find_spec("casadi"):
                continue
            with self.subTest(task=name):
                task = load_task(name)
                policy = HistoryPolicy(task, manifest_sha256(task), "native-continuous-affine-history-mpc/1",
                                       task["control_domains"]["continuous"]["problem_id"])
                observed = (list(task["objective"]["source_definition"]["terminal_target"])
                            if name == "syn-nl-fuel-01" else
                            [row["initial"] for row in task["model"]["states"]])
                previous = None
                try:
                    for stage in range(task["episode"]["intervals"]-3, task["episode"]["intervals"]):
                        result = policy.query(task["task_id"], observed, stage)
                        self.assertEqual(result["status"], "accepted", result)
                        request = policy.last_query_capture["request"]
                        initial = request["initial_primal"]
                        if previous is not None:
                            states, controls = previous["states"][1:], previous["controls"][1:]
                            states[0] = observed
                            np.testing.assert_array_equal(initial, np.concatenate([*states, *controls]))
                            self.assertEqual(request["warm_start"]["source_stage"], stage-1)
                        previous = result["selected_plan"]
                        observed = list(previous["states"][1])
                        observed[0] += 1e-6
                finally:
                    policy.close()


    def test_continuous_quadratic_tradeoff_uses_full_feasible_relation(self):
        request = analytic_request()
        result = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]], input=json.dumps(request) + "\n",
                                text=True, capture_output=True, check=True)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "solved", response)
        self.assertAlmostEqual(response["primal"][-2], 1 / 3, places=5)
        self.assertAlmostEqual(response["primal"][-1], 0, places=5)
        self.assertEqual(response["solver_receipt"]["provider"], "csl.convex.highs")
        self.assertEqual(response["history_relation"]["representation"], "polytope-h")
        self.assertAlmostEqual(response["source_cost"]["total"], 2 / 3, places=5)
        request["running_cost"]["stages"][0]["terms"][0]["coefficient"] = 0
        terminal_run = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
            input=json.dumps(request) + "\n", text=True, capture_output=True, check=True)
        terminal_only = json.loads(terminal_run.stdout)
        self.assertEqual(terminal_only["status"], "solved", terminal_only)
        self.assertAlmostEqual(terminal_only["primal"][-2], 1, places=5)
        self.assertAlmostEqual(terminal_only["primal"][-1], 0, places=5)

    def test_explicit_ipopt_export_preserves_the_same_quadratic_problem(self):
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks/reporting/closed_loop"))
        from history_norm_solver import solve

        request = analytic_request()
        request["history_solver"] = "casadi-ipopt"
        completed = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
            input=json.dumps(request) + "\n", text=True, capture_output=True, check=True)
        exported = json.loads(completed.stdout)
        self.assertEqual(exported["status"], "exported", exported)
        self.assertEqual(exported["history_objective"]["residual_norms"], [])
        result = solve(exported["history_relation"], exported["history_objective"],
                       initial=[0, 0, 0, 0, 0, 0])
        self.assertTrue(result["success"], result)
        self.assertAlmostEqual(result["primal"][-2], 1 / 3, places=5)
        self.assertAlmostEqual(result["primal"][-1], 0, places=5)
        self.assertAlmostEqual(result["objective"], 2 / 3, places=5)

    def test_selected_highs_refuses_norms_without_an_ipopt_fallback(self):
        request = analytic_request()
        request["terminal_objective"] = {"kind": "norm", "map": [[1, 0], [0, 1]],
                                         "target": [1, 0], "weights": [1, 1]}
        completed = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
            input=json.dumps(request) + "\n", text=True, capture_output=True, check=True)
        response = json.loads(completed.stdout)
        self.assertEqual(response["status"], "unsupported", response)
        self.assertEqual(response["requested_solver"], "csl.convex.highs")
        self.assertNotIn("primal", response)

    def test_unknown_history_solver_is_rejected(self):
        request = analytic_request()
        request["history_solver"] = "unknown-solver"
        completed = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
            input=json.dumps(request) + "\n", text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(completed.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()

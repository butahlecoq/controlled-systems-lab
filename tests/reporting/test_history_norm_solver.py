"""Functional check of the full-history norm solver."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))


@unittest.skipUnless(importlib.util.find_spec("casadi") and importlib.util.find_spec("numpy"),
                     "CasADi and NumPy required")
class HistoryNormSolverTest(unittest.TestCase):
    def test_separate_norms_and_positive_radius_obey_complete_history_rows(self):
        from history_norm_solver import solve

        # z = [initial radius, future radius, u]. Dynamics r1 = r0 + u,
        # r0 = 1, bounds 0 <= u <= 2. Minimize |r1-3| + 2|u|.
        # The minimum is u=0, r1=1; squaring/merging norms changes it.
        relation = {"inequalities": [[0, 0, 1], [0, 0, -1]],
                    "upper_bounds": [2, 0],
                    "equalities": [[1, 0, 0], [-1, 1, -1]],
                    "equality_values": [1, 0]}
        objective = {"quadratic": {"Q": [[0, 0, 0]] * 3,
                                    "linear": [0, 0, 0], "offset": 0},
                     "residual_norms": [
                         {"map": [[0, 1, 0]], "target": [3], "weights": [1], "coefficient": 1},
                         {"map": [[0, 0, 1]], "target": [0], "weights": [1], "coefficient": 2}]}
        result = solve(relation, objective, initial=[1, 1, 0], positive_indices=[1])
        self.assertTrue(result["success"], result)
        self.assertAlmostEqual(result["primal"][0], 1, places=6)
        self.assertAlmostEqual(result["primal"][1], 1, places=5)
        self.assertAlmostEqual(result["primal"][2], 0, places=5)
        self.assertAlmostEqual(result["objective"], 2, places=5)

    def test_continuous_request_keeps_task_identity_and_remaining_horizon(self):
        from contracts import load_task, manifest_sha256
        from task_models import prediction_receipt
        from history_policy import make_request

        for name in ("syn-nl-lv-01", "syn-nl-fuel-01", "earth-orbit"):
            with self.subTest(task=name):
                task = load_task(name)
                receipt = prediction_receipt(task)
                stage = 2
                observed = [row["initial"] for row in task["model"]["states"]]
                request = make_request(task, manifest_sha256(task), receipt, observed, stage)
                self.assertEqual(request["action_profile_id"], task["control_domains"]["continuous"]["problem_id"])
                self.assertEqual(request["control_bounds"], task["control_domains"]["continuous"]["bounds"])
                self.assertEqual(request["absolute_update_index"], stage)
                self.assertEqual(request["original_horizon"], task["episode"]["intervals"])
                self.assertEqual(len(request["predictor_stages"]), task["episode"]["intervals"] - stage)
                self.assertEqual(request["observed_physical_state"], observed)
                self.assertNotIn("actions", request)

    def test_continuous_request_preserves_quadratic_terminal_source_cost(self):
        from contracts import load_task, manifest_sha256
        from task_models import objective, prediction_receipt
        from history_policy import make_request

        for name in ("syn-nl-lv-01", "syn-nl-fuel-01"):
            with self.subTest(task=name):
                task = load_task(name)
                n = task["episode"]["intervals"]
                state = [field["initial"] for field in task["model"]["states"]]
                controls = [[0.0] * len(task["model"]["controls"]) for _ in range(n)]
                source = objective(task, [state] * (n + 1), controls)["terminal"]
                spec = make_request(task, manifest_sha256(task), prediction_receipt(task), state, 0)["terminal_objective"]
                quadratic = sum(0.5 * state[i] * value * state[j]
                    for i, row in enumerate(spec["Q"]) for j, value in enumerate(row))
                compiled = quadratic + sum(a * b for a, b in zip(spec["linear"], state)) + spec["offset"]
                self.assertAlmostEqual(compiled, source, places=9)

    def test_history_manifest_has_one_continuous_geometry_free_route_per_task(self):
        from capabilities import HISTORY_MANIFEST, build_history_manifest, validate_manifest
        from contracts import load_task

        manifest = build_history_manifest()
        self.assertEqual(validate_manifest(manifest_path=HISTORY_MANIFEST), manifest)
        graphs = manifest["graphs"]
        self.assertEqual(len(graphs), 3)
        for name in ("syn-nl-lv-01", "syn-nl-fuel-01", "earth-orbit"):
            task = load_task(name)
            graph = next(row for row in graphs if row["task_id"] == task["task_id"])
            self.assertEqual(graph["action_profile_id"], task["control_domains"]["continuous"]["problem_id"])
            self.assertEqual(graph["objective_id"], task["objective"]["objective_id"])
            self.assertIn(task["source"]["path"], {row["path"] for row in graph["source_files"]})
            self.assertEqual(graph["role_bindings"]["representation"], "not_used")
            self.assertEqual(graph["controller"]["policy_factory"], "history_policy:create_policy")

    def test_policy_refuses_a_task_hash_that_does_not_match_the_source_task(self):
        from contracts import load_task
        from history_policy import create_policy
        task = load_task("earth-orbit")
        with self.assertRaisesRegex(ValueError, "task hash"):
            create_policy(task, task_sha256="wrong", controller_id="history",
                          action_profile_id=task["control_domains"]["continuous"]["problem_id"])

    def test_runner_resolves_continuous_history_profile_before_bridge_preflight(self):
        import json
        import tempfile
        from pathlib import Path
        from run_closed_loop import run_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_task("syn-nl-lv-01", root, root / "missing-bridge",
                              controller_id="native-continuous-affine-history-mpc/1")
            self.assertEqual(result["status"], "refused")
            reason = json.loads((Path(result["attempt"]) / "resolution-refusal.json").read_text())["reason"]
            self.assertIn("common execution bridge does not exist", reason)

    def test_history_verification_rejects_wrong_rows_and_cost(self):
        import numpy as np
        from contracts import load_task
        from history_validation import validate
        from task_models import objective

        task = load_task("earth-orbit")
        initial = np.array([7000.0, 0.0, 0.0, 0.001])
        control = np.array([0.1, -0.1])
        predictor = [{"A": np.eye(4).tolist(), "B": np.zeros((4, 2)).tolist(), "c": [0] * 4}]
        primal = np.r_[initial, initial, control]
        relation = {"inequalities": [[0] * 8 + [1, 0]], "upper_bounds": [0.2],
                    "equalities": [], "equality_values": []}
        source = objective(task, [initial, initial], [control], absolute_stage_offset=19)
        check = lambda z, cost: validate(task, 19, initial, predictor, relation, z, cost)
        self.assertTrue(check(primal, source["total"])["accepted"])
        bad = primal.copy(); bad[4] += 2
        self.assertFalse(check(bad, source["total"])["accepted"])
        bad = primal.copy(); bad[8] = 0.3
        self.assertFalse(check(bad, source["total"])["accepted"])
        self.assertFalse(check(primal, source["total"] + 1)["accepted"])


if __name__ == "__main__":
    unittest.main()

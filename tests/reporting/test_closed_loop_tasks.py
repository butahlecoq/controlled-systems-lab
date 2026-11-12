"""Contract and local-model checks for the three single-player task adapters."""

import sys
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))

class ClosedLoopTaskContracts(unittest.TestCase):
    @unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                             ('numpy', 'scipy', 'casadi', 'do_mpc')),
                         'qualified MPC11 numerical dependencies are unavailable')
    def test_source_bound_model_objective_and_prediction_contracts(self):
        from check_contracts import main
        self.assertEqual(main(), 0)

    @unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                             ("numpy", "scipy", "casadi", "do_mpc")),
                         "qualified numerical dependencies are unavailable")
    def test_source_objective_for_remaining_horizon_keeps_absolute_stages(self):
        import numpy as np
        from contracts import load_task
        from task_models import objective

        for name in ("syn-nl-lv-01", "syn-nl-fuel-01", "earth-orbit"):
            with self.subTest(task=name):
                task = load_task(name)
                n = task["episode"]["intervals"]
                nx = len(task["model"]["states"])
                nu = len(task["model"]["controls"])
                states = np.ones((n + 1, nx))
                controls = np.full((n, nu), 0.2)
                stage = n - 2
                full = objective(task, states, controls)
                prefix_zero = controls.copy()
                prefix_zero[stage:] = 0
                prefix_cost = objective(task, states, prefix_zero)
                tail = objective(task, states[stage:], controls[stage:], absolute_stage_offset=stage)
                zero_tail = objective(task, states[stage:], np.zeros_like(controls[stage:]), absolute_stage_offset=stage)
                self.assertAlmostEqual(tail["running"] - zero_tail["running"], full["running"] - prefix_cost["running"], places=10)
                self.assertAlmostEqual(tail["terminal"], full["terminal"], places=10)
        orbit = load_task("earth-orbit")
        last = objective(orbit, np.ones((2, 4)), np.array([[0.2, 0.3]]), absolute_stage_offset=19)
        self.assertEqual(last["running"], 0.0)

    def test_bounded_candidates_keep_the_full_remaining_horizon_and_source_indices(self):
        from native_graph_policy import _candidate_action_histories

        result = _candidate_action_histories(action_count=3, horizon=30, budget=512)
        candidates = result["candidates"]
        self.assertEqual(result["policy_id"], "constant-and-single-switch-full-horizon/1")
        self.assertEqual(len(candidates), 177)
        self.assertEqual(result["search_coverage"], "incomplete")
        self.assertEqual(result["full_action_history_count"], str(3 ** 30))
        self.assertTrue(all(len(row) == 30 for row in candidates))
        self.assertTrue(all(0 <= action < 3 for row in candidates for action in row))
        self.assertEqual(len({tuple(row) for row in candidates}), len(candidates))

    def test_small_full_plan_product_is_exhaustive_and_budget_shortfall_is_explicit(self):
        from native_graph_policy import _candidate_action_histories

        exhaustive = _candidate_action_histories(action_count=2, horizon=2, budget=4)
        self.assertEqual(exhaustive["search_coverage"], "complete")
        self.assertEqual(exhaustive["candidates"], [[0, 0], [0, 1], [1, 0], [1, 1]])
        refused = _candidate_action_histories(action_count=3, horizon=5, budget=2)
        self.assertEqual(refused["search_coverage"], "unsupported-budget-below-action-count")
        self.assertEqual(refused["candidates"], [])

    def test_large_single_switch_space_is_not_materialized_when_constants_fill_budget(self):
        from native_graph_policy import _candidate_action_histories

        result = _candidate_action_histories(action_count=100, horizon=1000, budget=100)
        self.assertEqual(len(result["candidates"]), 100)
        self.assertEqual(result["candidate_budget"], 100)
        self.assertEqual(result["constant_history_count"], 100)
        self.assertEqual(result["available_single_switch_history_count"], 999 * 100 * 99)
        self.assertEqual(result["selected_single_switch_history_count"], 0)
        self.assertTrue(all(len(row) == 1000 for row in result["candidates"]))

        thinned = _candidate_action_histories(action_count=3, horizon=1000, budget=5)
        self.assertEqual(thinned["selected_single_switch_history_count"], 2)
        self.assertEqual(thinned["candidates"][:3], [[0] * 1000, [1] * 1000, [2] * 1000])
        self.assertEqual(thinned["candidates"][3], [0] + [1] * 999)
        self.assertEqual(thinned["candidates"][4], [2] * 999 + [1])


if __name__ == "__main__":
    unittest.main()

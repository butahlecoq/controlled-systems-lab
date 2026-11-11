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


if __name__ == "__main__":
    unittest.main()

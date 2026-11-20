"""Behavior at the native strategy feedback action and initialization boundaries."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))


class NativeStrategyHistoryTest(unittest.TestCase):
    def test_first_actuation_uses_the_literal_physical_bounds(self):
        from native_strategy_history import actuation_error

        self.assertEqual(actuation_error([0.5, -0.5], [[-0.5, 0.5], [-0.5, 0.5]]), 0)
        self.assertGreater(actuation_error([0.5, -0.50000000000002], [[-0.5, 0.5], [-0.5, 0.5]]), 0)

    def test_seed_for_a_rank_deficient_factor_is_a_real_bounded_witness(self):
        from native_strategy_history import feasible_membership_factors

        membership = {
            "kind": "zonotope",
            "indices": [0, 1],
            "factor_count": 3,
            "center": [0, 0],
            "factor": [[1, 1, 0], [0, 0, 0]],
        }
        [factors] = feasible_membership_factors([membership], [1.8, 0], {}, 2)
        self.assertAlmostEqual(factors[0] + factors[1], 1.8)
        self.assertTrue(all(-1 <= value <= 1 for value in factors))
        with self.assertRaisesRegex(ValueError, "membership"):
            feasible_membership_factors([membership], [1.8, 0.2], {}, 2)

"""Independent literal behavior checks for the issue #5 finite-game reference."""
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_finite_policy_classes import Game, compare, l13_policy_gap_game, remaining_fixed


class FinitePolicyClassTests(unittest.TestCase):
    def test_fixed_plan_and_replanning_values_are_distinct_objects(self):
        result = compare(l13_policy_gap_game())
        self.assertEqual(result.fixed_plan_values, {
            (0, -1): 4, (0, 1): 4, (1, -1): 2, (1, 1): 10,
        })
        self.assertEqual(result.fixed_value, 2)
        self.assertEqual(result.replanning_first_actions[(0, (0, 0))], (1,))
        self.assertEqual(result.replanning_worst, 2)
        self.assertEqual(result.causal_value, 1)

    def test_replanning_uses_observed_next_state_and_retains_ties(self):
        result = compare(l13_policy_gap_game())
        self.assertEqual(result.replanning_first_actions[(1, (0, 1))], (-1, 1))
        self.assertEqual(result.replanning_first_actions[(1, (1, 0))], (-1,))
        self.assertEqual(result.replanning_first_actions[(1, (2, -1))], (-1,))
        self.assertEqual(result.replanning_history_costs, {(-1, 0): 2, (0, 0): 1, (1, 0): 2})

    def test_executed_replanning_can_strictly_improve_on_initial_fixed_plan(self):
        # Any fixed suffix has worst |w0+u1|=2; observing w0 permits
        # u1=-w0 and terminal cost zero on both complete histories.
        game = Game((0,), ((0,), (-1, 1)), ((-1, 1), (0,)),
                    lambda stage, state, action, disturbance:
                        (state[0] + action + disturbance,),
                    lambda stage, state: True,
                    lambda state: Fraction(abs(state[0])))
        result = compare(game)
        self.assertEqual(result.fixed_plan_values, {(0, -1): 2, (0, 1): 2})
        self.assertEqual(result.fixed_value, 2)
        self.assertEqual(result.replanning_first_actions[(1, (-1,))], (1,))
        self.assertEqual(result.replanning_first_actions[(1, (1,))], (-1,))
        self.assertEqual(result.replanning_history_costs, {(-1, 0): 0, (1, 0): 0})
        self.assertEqual(result.replanning_worst,
                         max(result.replanning_history_costs.values()))
        self.assertEqual(result.replanning_worst, 0)
        self.assertEqual(result.causal_value, 0)

    def test_causal_continuation_has_interior_worst_cost(self):
        result = compare(l13_policy_gap_game())
        self.assertEqual(result.causal_first_actions[(0, (0, 0))], (0,))
        self.assertEqual(result.causal_first_actions[(1, (-1, 1))], (1,))
        self.assertEqual(result.causal_first_actions[(1, (0, 0))], (-1, 1))
        self.assertEqual(result.causal_first_actions[(1, (1, -1))], (-1,))
        self.assertEqual(result.causal_history_costs, {(-1, 0): 0, (0, 0): 1, (1, 0): 0})

    def test_current_disturbance_cannot_choose_a_different_first_action(self):
        game = Game((0,), ((-1, 1),), ((-1, 1),),
                    lambda stage, state, action, disturbance: (action + disturbance,),
                    lambda stage, state: True,
                    lambda state: Fraction(abs(state[0])))
        result = compare(game)
        # Seeing the current disturbance before acting would give zero instead.
        self.assertEqual(result.fixed_plan_values, {(-1,): 2, (1,): 2})
        self.assertEqual(result.causal_value, 2)
        self.assertEqual(result.causal_first_actions[(0, (0,))], (-1, 1))

    def test_whole_successor_safety_rejects_clipping_trap(self):
        game = Game((0,), ((0,),), ((-1, 1),),
                    lambda stage, state, action, disturbance: (disturbance,),
                    lambda stage, state: stage == 0 or state == (0,),
                    lambda state: Fraction(0))
        value, plans = remaining_fixed(game, 0, (0,))
        self.assertIsNone(value)
        self.assertEqual(plans, ())

    def test_nominal_case_has_equal_policy_class_values(self):
        game = Game((0,), ((0, 1), (-1, 1)), ((0,), (0,)),
                    lambda stage, state, action, disturbance: (state[0] + action,),
                    lambda stage, state: True,
                    lambda state: Fraction(state[0] * state[0]))
        result = compare(game)
        self.assertEqual((result.fixed_value, result.replanning_worst, result.causal_value),
                         (0, 0, 0))


if __name__ == "__main__":
    unittest.main()

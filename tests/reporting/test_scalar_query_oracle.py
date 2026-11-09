import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("scalar_query_oracle", Path(__file__).resolve().parents[2] / "benchmarks/reporting/review05/scalar_query_oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class ScalarQueryOracleTests(unittest.TestCase):
    def test_zero_optimum_and_non_singleton_constant_family(self):
        for t in (2, 4, 8):
            self.assertTrue(oracle.verify_history([[0]]*(t+1), [[0]]*t, 0, t, 1))
            self.assertTrue(oracle.verify_history([[k/2] for k in range(t+1)], [[.5]]*t, 0, t, 0))

    def test_rejects_feasible_nonoptimal_and_wrong_objective(self):
        with self.assertRaisesRegex(ValueError, "not optimal"):
            oracle.verify_history([[0],[1],[2]], [[1],[1]], 2, 2, 1)
        with self.assertRaisesRegex(ValueError, "reported objective"):
            oracle.verify_history([[0],[1],[2]], [[1],[1]], 2, 2, 0)

    def test_rejects_invalid_initial_state_and_actuator_bounds(self):
        for coefficient in (0, 1):
            for states, controls in (([[1], [1], [1]], [[0], [0]]),
                                     ([[0], [2], [2]], [[2], [0]])):
                with self.assertRaises(ValueError):
                    oracle.verify_history(states, controls, 0, 2, coefficient)

    def test_rejects_broken_recurrence_and_nonfinite_input(self):
        for states in ([[0],[0],[1]], [[0],[float("nan")],[0]]):
            with self.assertRaises(ValueError):
                oracle.verify_history(states, [[0],[0]], 0, 2, 0)


if __name__ == "__main__":
    unittest.main()

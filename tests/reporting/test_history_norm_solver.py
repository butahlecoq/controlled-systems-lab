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


if __name__ == "__main__":
    unittest.main()

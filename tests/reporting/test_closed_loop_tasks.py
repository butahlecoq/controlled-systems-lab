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


if __name__ == "__main__":
    unittest.main()

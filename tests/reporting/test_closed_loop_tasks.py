"""Contract and local-model checks for the three single-player task adapters."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))

from check_contracts import main


class ClosedLoopTaskContracts(unittest.TestCase):
    def test_source_bound_model_objective_and_prediction_contracts(self):
        self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()

"""Public exact-reference checks; no archive, solver or checkout mutation."""
from pathlib import Path
import subprocess
import sys
import unittest


class TemporalLiftTests(unittest.TestCase):
    def test_optimized_cli_runs_all_literal_checks(self):
        result = subprocess.run(
            [sys.executable, "-B", "-O", str(Path(__file__).with_name("check_temporal_lift.py"))],
            text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "PASS temporal_affine_ltv_states",
            "PASS temporal_inverse_recovery",
            "PASS temporal_first_step_and_stage_bounds",
            "PASS temporal_rate_scaling",
            "PASS temporal_homogeneous_slice",
            "PASS temporal_uncoupled_counterexample",
            "PASS temporal_terminal_memory_fibre",
            "PASS temporal_marginal_coverage",
            "PASS temporal_four_state_embedding",
            "9 exact literal checks passed; report proofs are unavailable in this checkout; "
            "continuum claims are not verified.",
        ])

    def test_wrong_arithmetic_is_rejected_under_optimization(self):
        code = """import check_temporal_lift as c
from unittest.mock import patch
wrong = c.observations()
wrong['temporal_inverse_recovery'] = ((0, 0, 0), (0, 0, 0))
with patch.object(c, 'observations', return_value=wrong):
    c.check_temporal_lift()
"""
        result = subprocess.run([sys.executable, "-B", "-O", "-c", code],
                                cwd=Path(__file__).parent, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ValueError: temporal_inverse_recovery:", result.stderr)


if __name__ == "__main__":
    unittest.main()

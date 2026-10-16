"""Literal regression for the inferred scalar-input R29 reference."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "docs/research/tools/check_r29_reference.py"
SCENARIO = ROOT / "benchmarks/scenarios/r29-corrected-scalar-reference.json"


class R29ReferenceTest(unittest.TestCase):
    def test_terminal_matches_hand_derived_nilpotent_anchors(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(CHECKER), "--scenario", str(SCENARIO)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["terminal_center_exact"], ["1150", "0", "430", "0"])
        self.assertEqual(result["generator_count_by_stage"], list(range(4, 21)))
        self.assertEqual(result["terminal_factor_ids"],
                         ["x0.0", "x0.1", "x0.2", "x0.3"] +
                         [f"u.{stage}" for stage in range(16)])
        self.assertEqual(result["terminal_generator_columns_exact"][0],
                         ["20", "-2080", "0", "0"])
        self.assertEqual(result["terminal_generator_columns_exact"][2],
                         ["0", "0", "10", "-1040"])
        self.assertEqual(result["terminal_generator_columns_exact"][4],
                         ["4", "-390", "2", "-195"])
        self.assertEqual(result["terminal_generator_columns_exact"][-1],
                         ["4", "0", "2", "0"])
        self.assertEqual(result["terminal_coordinate_intervals_exact"],
                         [["1066", "1234"], ["-5700", "5700"],
                          ["388", "472"], ["-2900", "2900"]])
        self.assertEqual(result["closed_form_verified_stages"], 17)
        self.assertEqual(result["historical_run_reproduced"], False)


if __name__ == "__main__":
    unittest.main()

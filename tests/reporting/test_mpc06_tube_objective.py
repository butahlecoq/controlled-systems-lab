from __future__ import annotations

from fractions import Fraction as Q
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports/mpc06"))
import build_tube_objective
import check_tube_objective
from tube_objective import SCENARIO_PATH, simulate


class Mpc06TubeObjectiveTests(unittest.TestCase):
    def test_nonzero_nominal_input_is_in_surrogate_cost(self):
        scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        scenario["nominal_plan"]["controls"] = ["1/8", "0", "0"]
        disturbances = (Q(0), Q(0), Q(0))

        result = simulate(scenario, disturbances)

        self.assertEqual(Q(result["nominal_surrogate_cost"]), Q(9, 64))

    def test_analyze_and_independently_check_saved_report(self):
        analyzed = build_tube_objective.analyze()
        saved_result = json.loads(build_tube_objective.OUTPUT.joinpath("result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_result, analyzed)
        expected = check_tube_objective.check()
        saved = json.loads(check_tube_objective.OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(saved, expected)
        self.assertEqual(expected["status"], "verified")
        self.assertEqual(expected["checked"]["exact_continuous_box_worst_cost"], "3/8")


if __name__ == "__main__":
    unittest.main()

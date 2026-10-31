from fractions import Fraction
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def fraction(value: object) -> Fraction:
    return Fraction(str(value))


def cost(control: tuple[Fraction, Fraction]) -> Fraction:
    return (control[0] - Fraction(1, 2)) ** 2 + control[1] ** 2


class Mpc02FourTrackIndependentOracleTests(unittest.TestCase):
    expected = {
        "mpc02-unconstrained-2d-v1": ((Fraction(1, 2), Fraction(0)), Fraction(0)),
        "mpc02-stage-box-2d-v1": ((Fraction(1, 2), Fraction(0)), Fraction(0)),
        "mpc02-slew-2d-v1": ((Fraction(3, 8), Fraction(1, 8)), Fraction(1, 32)),
        "mpc02-l1-budget-2d-v1": ((Fraction(1, 4), Fraction(0)), Fraction(1, 16)),
    }

    def load(self, filename: str) -> dict:
        return json.loads((ROOT / "examples" / "scenarios" / filename).read_text())

    def test_each_authored_track_matches_independent_rational_oracle(self) -> None:
        files = {
            "mpc02-unconstrained-2d-v1": "mpc02-unconstrained-2d.json",
            "mpc02-stage-box-2d-v1": "mpc02-stage-box-2d.json",
            "mpc02-slew-2d-v1": "mpc02-slew-2d.json",
            "mpc02-l1-budget-2d-v1": "mpc02-l1-budget-2d.json",
        }
        for scenario_id, filename in files.items():
            with self.subTest(scenario_id=scenario_id):
                scenario = self.load(filename)
                self.assertEqual(scenario["id"], scenario_id)
                self.assertEqual(scenario["initial_state"], [0, 0])
                self.assertEqual(scenario["horizon"], 2)
                stages = scenario["model"]["stages"]
                self.assertEqual(stages[0]["A"], [[1, 0], [0, 1]])
                self.assertEqual(stages[1]["A"], [[1, 0], [0, 1]])
                self.assertEqual(stages[0]["B"], [[1], [0]])
                self.assertEqual(stages[1]["B"], [[0], [1]])
                objective_spec = scenario["objective"]
                self.assertEqual(objective_spec["Q"], [[2, 0], [0, 2]])
                self.assertEqual(objective_spec["linear"], [-1, 0])
                self.assertEqual(fraction(objective_spec["offset"]), Fraction(1, 4))

                control, objective = self.expected[scenario_id]
                self.assertEqual(cost(control), objective)
                if scenario["controls"]["kind"] == "box":
                    lower = fraction(scenario["controls"]["lower"][0])
                    upper = fraction(scenario["controls"]["upper"][0])
                    self.assertTrue(all(lower <= value <= upper for value in control))

                if scenario_id == "mpc02-slew-2d-v1":
                    self.assertEqual(abs(control[1] - control[0]), Fraction(1, 4))
                elif scenario_id == "mpc02-l1-budget-2d-v1":
                    self.assertEqual(abs(control[0]) + abs(control[1]), Fraction(1, 4))
                else:
                    self.assertNotIn("temporal", scenario)

    def test_budget_rows_are_exactly_the_two_dimensional_l1_ball(self) -> None:
        scenario = self.load("mpc02-l1-budget-2d.json")
        rows = scenario["temporal"]["rows"]
        bounds = scenario["temporal"]["bounds"]
        self.assertEqual(rows, [
            [0, 0, 0, 0, 0, 0, 1, 1],
            [0, 0, 0, 0, 0, 0, -1, -1],
            [0, 0, 0, 0, 0, 0, 1, -1],
            [0, 0, 0, 0, 0, 0, -1, 1],
        ])
        self.assertEqual(
            [(row["lower"], fraction(row["upper"])) for row in bounds],
            [(None, Fraction(1, 4))] * 4,
        )


if __name__ == "__main__":
    unittest.main()

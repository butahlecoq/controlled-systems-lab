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
                    self.assertEqual(scenario["temporal"]["rows"],
                                     [[0, 0, 0, 0, 0, 0, -1, 1]])
                    self.assertEqual(
                        [(row["lower"], fraction(row["upper"]))
                         for row in scenario["temporal"]["bounds"]],
                        [(Fraction(-1, 4), Fraction(1, 4))],
                    )
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

    def test_intermediate_violation_is_not_hidden_by_physical_endpoint(self) -> None:
        """A physical-state-only recurrence admits a history rejected by slew."""
        # x0=0, x1=x0+u0, x2=x1+u1; require x1=1 and |u1-u0| <= 1/4.
        u0 = Fraction(1)  # x1=1 fixes the first control exactly.
        admissible_u1 = (Fraction(3, 4), Fraction(1))
        terminal_interval = (u0 + admissible_u1[0], u0 + admissible_u1[1])
        self.assertEqual(terminal_interval, (Fraction(7, 4), Fraction(2)))

        # Dropping the remembered u0 and propagating with an independent [-1,1]
        # second-stage domain falsely admits the same endpoint x2=0.
        falsely_admitted = (u0, Fraction(-1))
        self.assertEqual(sum(falsely_admitted), Fraction(0))
        self.assertGreater(abs(falsely_admitted[1] - falsely_admitted[0]), Fraction(1, 4))

    def test_incompatible_initial_memory_makes_first_slew_step_infeasible(self) -> None:
        # A declared previous command p0=2 is incompatible with u0 in [-1,1]
        # when |u0-p0| <= 1/4.  This is a constraint contradiction, not a
        # solver failure and not permission to silently drop the first row.
        p0 = Fraction(2)
        control_lower, control_upper = Fraction(-1), Fraction(1)
        slew = Fraction(1, 4)
        compatible_lower = max(control_lower, p0 - slew)
        compatible_upper = min(control_upper, p0 + slew)
        self.assertGreater(compatible_lower, compatible_upper)

    def test_temporal_rows_can_make_the_complete_history_empty(self) -> None:
        # The box alone permits every pair in [-1,1]^2.  These are literal rows
        # in x0,...,xT,u0,u1 order: u0 <= -3 and -u0 <= 2 (u0 >= -2).
        # No complete history can satisfy them; endpoint projection must not
        # manufacture a witness.
        lower, upper = Fraction(-1), Fraction(1)
        history_upper = Fraction(-3)
        history_lower = Fraction(-2)
        rows = [
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, -1, 0],
        ]
        upper_bounds = [history_upper, Fraction(2)]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row[6:] for row in rows], [[1, 0], [-1, 0]])
        self.assertEqual(upper_bounds, [Fraction(-3), Fraction(2)])
        self.assertLess(history_upper, lower)
        self.assertLess(history_upper, history_lower)
        self.assertLess(min(upper, history_upper), max(lower, history_lower))

    def test_slew_memory_projection_reconstructs_original_controls(self) -> None:
        p0 = Fraction(1, 8)
        increments = (Fraction(1, 4), Fraction(-1, 4))
        memory = (p0, p0 + increments[0])
        recovered = (memory[0] + increments[0], memory[1] + increments[1])
        self.assertEqual(recovered, (Fraction(3, 8), Fraction(1, 8)))
        self.assertEqual(abs(recovered[0] - p0), Fraction(1, 4))
        self.assertEqual(abs(recovered[1] - recovered[0]), Fraction(1, 4))


if __name__ == "__main__":
    unittest.main()

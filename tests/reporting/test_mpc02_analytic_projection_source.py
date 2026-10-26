from fractions import Fraction
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def rational_vector(values: list[str]) -> tuple[Fraction, ...]:
    return tuple(Fraction(value) for value in values)


class Mpc02AnalyticProjectionSourceTests(unittest.TestCase):
    def test_projection_source_matches_authored_slew_scenario(self) -> None:
        source = json.loads((ROOT / "docs/examples/mpc02-slew-analytic-source.json").read_text())
        scenario = json.loads((ROOT / "examples/scenarios/mpc02-slew-2d.json").read_text())

        self.assertEqual(source["scenario_id"], scenario["id"])
        self.assertEqual(source["model"]["horizon"], scenario["horizon"])
        self.assertEqual(rational_vector(source["model"]["initial_state"]),
                         tuple(Fraction(value) for value in scenario["initial_state"]))
        self.assertEqual(rational_vector(source["model"]["control_bounds"]),
                         (Fraction(scenario["controls"]["lower"][0]),
                          Fraction(scenario["controls"]["upper"][0])))
        self.assertEqual(source["model"]["slew_bound"], "|u1-u0|<=1/4")
        self.assertEqual(scenario["temporal"]["rows"], [[0, 0, 0, 0, 0, 0, -1, 1]])
        self.assertEqual(scenario["temporal"]["bounds"],
                         [{"lower": -0.25, "upper": 0.25}])
        self.assertEqual([stage["A"] for stage in scenario["model"]["stages"]],
                         [[[1, 0], [0, 1]], [[1, 0], [0, 1]]])
        self.assertEqual([stage["B"] for stage in scenario["model"]["stages"]],
                         [[[1], [0]], [[0], [1]]])
        objective = scenario["objective"]
        self.assertEqual(objective["Q"], [[2, 0], [0, 2]])
        self.assertEqual(objective["linear"], [-1, 0])
        self.assertEqual(objective["offset"], 0.25)
        self.assertEqual(rational_vector(source["model"]["terminal_target"]),
                         (Fraction(1, 2), Fraction(0)))

        projection = source["projection"]
        self.assertEqual(rational_vector(projection["stage_box_optimum_control_rational"]),
                         (Fraction(1, 2), Fraction(0)))
        controls = [rational_vector(vertex)
                    for vertex in projection["control_vertices_rational"]]
        expected = ((-1, -1), (Fraction(-3, 4), -1), (1, Fraction(3, 4)),
                    (1, 1), (Fraction(3, 4), 1), (-1, Fraction(-3, 4)))
        self.assertEqual(controls, list(expected))
        for first, second in controls:
            self.assertLessEqual(abs(first), 1)
            self.assertLessEqual(abs(second), 1)
            self.assertLessEqual(abs(second - first), Fraction(1, 4))
        self.assertEqual([rational_vector(vertex)
                          for vertex in projection["terminal_state_vertices_rational"]], controls)

        optimum = rational_vector(projection["slew_optimum_control_rational"])
        target = rational_vector(source["model"]["terminal_target"])
        self.assertEqual(optimum, (Fraction(3, 8), Fraction(1, 8)))
        self.assertEqual(sum((value - target[index]) ** 2
                             for index, value in enumerate(optimum)), Fraction(1, 32))
        self.assertEqual(rational_vector(projection["slew_optimum_terminal_state_rational"]),
                         optimum)
        self.assertEqual(Fraction(projection["slew_optimum_cost_rational"]), Fraction(1, 32))


if __name__ == "__main__":
    unittest.main()

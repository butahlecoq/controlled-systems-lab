import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ext04_affine_synthesis_report", ROOT / "scripts/reports/ext04/affine_synthesis_report.py")
report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report)


def result_fixture():
    gain, offset = 1.0, 0.0
    rows = []
    for x1, x2, error in report.expected_initials():
        observation = x1 + error
        action = gain * observation + offset
        terminal = [x1 + x2 - action, x2]
        rows.append({"initial": [x1, x2], "measurement_error": error,
            "observation": observation, "action": action, "terminal": terminal,
            "action_margins": [1.101 - action, 1.101 + action],
            "terminal_margins": [0.16 - terminal[0], 0.051 - terminal[1],
                0.16 + terminal[0], 0.051 + terminal[1]]})
    return {"policy_gain": gain, "policy_offset": offset, "generators": rows,
        "assurance": "numerical", "coverage": "all_joint_uncertainty",
        "feasibility": "within_tolerance", "solver_outcome": "optimal"}


class AffineSynthesisReportTests(unittest.TestCase):
    def test_literal_two_state_policy_replay_covers_all_joint_vertices(self):
        value = result_fixture()
        report.check_result(value)
        image = report.svg(value)
        self.assertIn("x₁", image)
        self.assertIn("x₂", image)
        self.assertEqual(image.count("marker-end=\"url(#arrow)\""), 9)

    def test_report_checker_rejects_an_incorrect_terminal_vertex(self):
        value = result_fixture()
        value["generators"][0]["terminal"][0] += 0.01
        with self.assertRaisesRegex(ValueError, "independent plant calculation"):
            report.check_result(value)


if __name__ == "__main__":
    unittest.main()

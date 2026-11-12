"""Physical plane and box projection checks for saved feedback figures."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
from plot_feedback_history import PLANES, axis_bounds


class FeedbackHistoryPlotTest(unittest.TestCase):
    def test_full_state_box_then_fuel_physical_planes(self):
        member = {"inequalities": [[1, 0, 0, 0], [-1, 0, 0, 0], [0, 1, 0, 0],
                    [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, -1, 0],
                    [0, 0, 0, 1], [0, 0, 0, -1]],
                  "upper_bounds": [10, 0, 20, 0, 3, 0, 4, 0],
                  "equalities": [], "equality_values": []}
        lower, upper = axis_bounds(member, 4)
        self.assertEqual(lower, [0, 0, 0, 0])
        self.assertEqual(upper, [10, 20, 3, 4])
        self.assertEqual(PLANES["syn-nl-fuel-01"], [(2, 0), (3, 1)])

    def test_rejects_non_axis_h_instead_of_drawing_false_box(self):
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            axis_bounds({"inequalities": [[1, 1]], "upper_bounds": [1],
                         "equalities": [], "equality_values": []}, 2)


if __name__ == "__main__":
    unittest.main()

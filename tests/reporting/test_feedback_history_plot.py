"""Physical plane and box projection checks for saved feedback figures."""
import sys
import unittest
import importlib.util
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
from plot_feedback_history import PLANES, axis_bounds


class FeedbackHistoryPlotTest(unittest.TestCase):
    def test_zonotope_projection_preserves_correlation_and_physical_coordinate_order(self):
        from plot_feedback_history import project_member
        member = {"kind": "zonotope", "center": [10, 20, 30, 40],
                  "factor_count": 2, "factor": [[1, 1], [0, 0], [1, -1], [0, 0]]}
        projected = project_member(member, 4, 2, 0)
        self.assertEqual({tuple(row) for row in projected["points"]},
                         {(28, 10), (30, 8), (32, 10), (30, 12)})

    def test_ellipsoid_projection_uses_its_factor_and_support(self):
        from plot_feedback_history import project_member
        member = {"kind": "ellipsoid", "center": [0, 0, 0, 0],
                  "factor_count": 2, "factor": [[1, 1], [0, 0], [1, -1], [0, 0]]}
        points = np.asarray(project_member(member, 4, 2, 0)["points"])
        np.testing.assert_allclose(np.linalg.norm(points, axis=1), np.sqrt(2), atol=1e-12)
        for direction in ([1, 0], [0, 1], [1, 1]):
            actual = np.max(points @ direction)
            expected = np.sqrt(2) * np.linalg.norm(direction)
            self.assertLessEqual(actual, expected + 1e-12)
            self.assertLess(expected - actual, 0.002)

    def test_rotated_polytope_is_not_replaced_by_its_axis_box(self):
        from plot_feedback_history import project_member
        member = {"kind": "h", "inequalities": [[1, 1], [1, -1], [-1, 1], [-1, -1]],
                  "upper_bounds": [1, 1, 1, 1], "equalities": [], "equality_values": []}
        points = project_member(member, 2, 0, 1)["points"]
        self.assertEqual({tuple(row) for row in points}, {(1, 0), (0, 1), (-1, 0), (0, -1)})
        with self.assertRaisesRegex(ValueError, "bounded"):
            project_member(dict(member, inequalities=[[1, 0], [0, 1]], upper_bounds=[1, 1]), 2, 0, 1)

    def test_zero_factor_projection_remains_a_point(self):
        from plot_feedback_history import project_member
        member = {"kind": "ellipsoid", "center": [10, 20, 30, 40],
                  "factor_count": 0, "factor": [[], [], [], []]}
        self.assertEqual(project_member(member, 4, 2, 0)["points"], [[30, 10]])

    @unittest.skipUnless(importlib.util.find_spec("scipy"), "SciPy required for non-axis full-state H projection")
    def test_full_state_equalities_remain_in_force_during_projection(self):
        from plot_feedback_history import project_member
        member = {"kind": "h", "inequalities": [[1, 0, 0, 0], [-1, 0, 0, 0],
                  [0, 1, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0]],
                  "upper_bounds": [1, 1, 1, 1, 1],
                  "equalities": [[-1, -1, 1, 0], [0, 0, 0, 1]], "equality_values": [0, 0]}
        points = project_member(member, 4, 0, 1)["points"]
        self.assertEqual({tuple(np.round(p, 8)) for p in points},
                         {(-1, -1), (1, -1), (1, 0), (0, 1), (-1, 1)})

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

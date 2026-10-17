"""Behavior checks for the L04 printed terminal-row rounding audit."""

from fractions import Fraction
import unittest

from docs.research.tools.check_b08_reported_rounding import audit, squared_norm_box


class B08ReportedRoundingTest(unittest.TestCase):
    def test_box_bounds_include_zero_and_use_farthest_endpoints(self):
        self.assertEqual(squared_norm_box((Fraction(1, 4), Fraction(3)),
                                          (Fraction(0), Fraction(0)), Fraction(1, 2)),
                         (Fraction(25, 4), Fraction(205, 16)))

    def test_source_rows_have_literal_exact_dispositions(self):
        result = audit()
        self.assertEqual(result["nonlinear_text"]["norm_squared_box"],
                         ["269620017/1000000", "269658203/1000000"])
        self.assertEqual(result["nonlinear_text"]["cost_box_disjoint"], True)
        self.assertEqual(result["nonlinear_table"]["cost_box_disjoint"], True)
        self.assertEqual(result["linear_table"]["cost_box_disjoint"], False)
        self.assertEqual(result["linear_table"]["corners_in_coordinate_box"], 0)
        self.assertEqual(result["linear_table"]["nearest_corner_max_coordinate_gap"], "3/80")
        self.assertEqual(result["linear_table"]["worst_corner_squared"],
                         "112730080707/25000000")
        self.assertEqual(result["linear_table"]["worst_cost_box_disjoint"], True)
        self.assertEqual(result["linear_table"]["corner_count"], 256)


if __name__ == "__main__":
    unittest.main()

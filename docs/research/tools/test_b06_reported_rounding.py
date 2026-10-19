"""Behavior checks for the exact L09 B06 terminal-cost center audit."""

from fractions import Fraction
import unittest

from docs.research.tools.check_b06_reported_rounding import audit, squared_criterion


class B06ReportedRoundingTest(unittest.TestCase):
    def test_criterion_uses_all_five_printed_terms(self):
        self.assertEqual(squared_criterion(tuple(map(Fraction, ("30", "6.0345", "20", "4.4731")))),
                         Fraction(16378084179, 200000000))

    def test_more_precise_nonlinear_state_explains_reported_cost(self):
        result = audit()
        self.assertFalse(result["nonlinear_table_center"]["center_rounds_to_reported_criterion"])
        self.assertTrue(result["nonlinear_text_center"]["center_rounds_to_reported_criterion"])
        self.assertEqual(result["nonlinear_text_center"]["criterion_squared_at_center"],
                         "16378084179/200000000")

    def test_linear_table_center_rounds_to_reported_worst_case(self):
        result = audit()
        self.assertTrue(result["linear_table_center"]["center_rounds_to_reported_criterion"])
        self.assertEqual(result["linear_table_center"]["criterion_squared_at_center"],
                         "4088109/40000")


if __name__ == "__main__":
    unittest.main()

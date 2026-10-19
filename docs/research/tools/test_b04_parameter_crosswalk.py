"""Literal exact-rational checks of the B04 parameter crosswalk."""

import unittest

from docs.research.tools.check_b04_parameter_crosswalk import audit


class B04ParameterCrosswalkTest(unittest.TestCase):
    def test_published_law_and_archived_kernel_remain_distinct(self):
        result = audit()
        self.assertEqual(result["printed_nonlinear_initial"],
                         ["3862615640/3169317", "928513375/2112878"])
        self.assertEqual(result["displayed_linear_initial"], ["152113/125", "438787/1000"])
        self.assertFalse(result["printed_nonlinear_initial_matches_displayed"])
        self.assertEqual(result["linear_initial_from_equation_1_4"], ["90136/75", "11218/25"])
        self.assertFalse(result["equation_1_4_matches_displayed_linear_initial"])
        self.assertEqual(result["printed_nonlinear_reference_input_slope"],
                         ["1014/55", "-2439/220"])
        self.assertEqual(result["displayed_linear_B_flow_rows"], ["17", "-12"])
        self.assertFalse(result["printed_slope_matches_displayed_B"])
        self.assertEqual(result["kernel_nonlinear_initial"],
                         ["3867462560/3169317", "464839250/1056439"])
        self.assertEqual(result["kernel_initial_minus_saved"],
                         ["-653611/316931700000000000", "27721/66027437500000000"])
        self.assertEqual(result["kernel_nonlinear_reference_input_slope"],
                         ["1104/55", "-576/55"])
        self.assertEqual(result["A01_B_flow_rows"], ["1104/55", "-576/55"])
        self.assertTrue(result["kernel_slope_matches_A01_B"])


if __name__ == "__main__":
    unittest.main()

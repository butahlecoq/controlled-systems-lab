"""Literal exact-rational checks of the B04 model-variant diagnosis."""

import unittest

from docs.research.tools.check_b04_model_variants import audit


class B04ModelVariantTest(unittest.TestCase):
    def setUp(self):
        self.result = audit()

    def test_printed_model_is_excluded_by_its_own_stock_plane(self):
        plane = self.result["variants"]["printed-l11"]["plane"]
        self.assertEqual(plane["weights"], [12, 17])
        self.assertEqual(plane["flow_plane_required"], "22062227/1000")
        self.assertEqual(plane["stock_plane_required"], "-21227/10")
        self.assertEqual(plane["flow_residual"], "-427/1000")
        self.assertEqual(plane["stock_residual"], "1716499/1000")
        self.assertEqual(plane["flow_rounding_radius"], "29/20")
        self.assertEqual(plane["stock_rounding_radius"], "29/2000")
        self.assertTrue(plane["flow_compatible"])
        self.assertFalse(plane["stock_compatible"])
        self.assertFalse(plane["compatible"])

    def test_saved_variant_contains_the_published_point(self):
        plane = self.result["variants"]["saved-a39-a01-a40"]["plane"]
        self.assertEqual(plane["weights"], [12, 23])
        self.assertEqual(plane["flow_residual"], "-65554305551/125000000000")
        self.assertEqual(plane["stock_residual"], "-14444449/1250000000")
        self.assertEqual(plane["flow_rounding_radius"], "7/4")
        self.assertEqual(plane["stock_rounding_radius"], "7/400")
        self.assertTrue(plane["flow_compatible"])
        self.assertTrue(plane["stock_compatible"])
        self.assertTrue(plane["compatible"])

    def test_only_the_saved_variant_is_compatible_with_the_published_row(self):
        compatibility = self.result["compatibility"]
        self.assertEqual(compatibility["published_row_compatible_variants"], ["saved-a39-a01-a40"])
        self.assertEqual(compatibility["published_row_incompatible_variants"], ["printed-l11"])

    def test_printed_criterion_evaluates_to_the_reported_objective(self):
        criterion = self.result["criterion"]
        self.assertEqual(criterion["reported_objective"], "30899/1000")
        self.assertEqual(criterion["criterion_squared_at_published_point"], "477371121/500000")
        self.assertTrue(criterion["reported_objective_inside_rounding"])

    def test_saved_initial_state_follows_the_scaled_nonlinear_law(self):
        table = self.result["law_versus_initial_state"]
        self.assertTrue(table["scaled-c2-c3"]["saved-a39-a01-a40"]["matches_state_within_1e-6"])
        self.assertFalse(table["scaled-c2-c3"]["saved-a39-a01-a40"]["matches_state_exactly"])
        self.assertFalse(table["printed-c2-c3"]["saved-a39-a01-a40"]["matches_state_within_1e-6"])

    def test_printed_initial_state_follows_neither_law(self):
        table = self.result["law_versus_initial_state"]
        self.assertFalse(table["printed-c2-c3"]["printed-l11"]["matches_state_within_1e-6"])
        self.assertFalse(table["scaled-c2-c3"]["printed-l11"]["matches_state_within_1e-6"])
        self.assertEqual(table["printed-c2-c3"]["printed-l11"]["oxidizer_flow_difference"],
                         "-732638179/396164625")
        self.assertEqual(table["scaled-c2-c3"]["printed-l11"]["fuel_flow_difference"],
                         "-1287550507/1056439000")

    def test_mixture_identities(self):
        mixture = self.result["mixture"]
        self.assertTrue(mixture["nominal_ratio_identity_1200_over_450"])
        self.assertEqual(mixture["nominal_mixture_ratio"], "8/3")
        self.assertEqual(mixture["initial_mixture_perturbation"], "8/75")
        self.assertEqual(mixture["initial_perturbation_relative_to_K"], "1/25")
        self.assertEqual(mixture["throttle_sensitivity_c1"], "8/75")
        self.assertEqual(mixture["reachable_mixture_band_for_u_in_unit_interval"], ["0/1", "16/75"])
        self.assertEqual(mixture["phase_box_upper_face_excess_over_K"], "1/6")
        self.assertEqual(mixture["phase_box_lower_face_excess_over_K"], "-2/13")
        self.assertTrue(mixture["phase_box_binds_above_reachable_band"])

    def test_only_the_saved_input_matrix_matches_the_printed_throttle_sensitivity(self):
        mixture = self.result["mixture"]
        self.assertEqual(mixture["mixture_sensitivity_per_variant"]["printed-l11"], "49/450")
        self.assertEqual(mixture["mixture_sensitivity_per_variant"]["saved-a39-a01-a40"], "8/75")
        self.assertFalse(mixture["mixture_sensitivity_matches_c1_per_variant"]["printed-l11"])
        self.assertTrue(mixture["mixture_sensitivity_matches_c1_per_variant"]["saved-a39-a01-a40"])


if __name__ == "__main__":
    unittest.main()

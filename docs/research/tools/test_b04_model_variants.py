"""Literal exact-rational checks of the B04 model-variant diagnosis."""

import json
import unittest
from fractions import Fraction
from pathlib import Path

from docs.research.tools.check_b04_model_variants import ROOT, audit


RECORD = ROOT / "docs/research/evidence/b04-model-variants.json"


def as_float(text):
    """Read a stored rational string as a float."""
    return float(Fraction(text))


class B04ModelVariantTest(unittest.TestCase):
    def setUp(self):
        self.result = audit()

    def test_model_structure_is_read_from_the_manifest(self):
        structure = self.result["model_structure"]
        self.assertEqual(structure["horizon"], 16)
        self.assertEqual(structure["step_seconds"], "25/4")
        self.assertEqual(structure["total_seconds"], "100/1")
        self.assertEqual(structure["stock_coupling"], "-25/4")

    def test_published_rounding_radii_follow_the_printed_decimals(self):
        rounding = self.result["published_rounding"]
        self.assertEqual(rounding["printed_decimals"], [1, 3, 1, 3])
        self.assertEqual(rounding["flow_radius"], "1/20")
        self.assertEqual(rounding["stock_radius"], "1/2000")

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

    def test_verdicts_are_robust_to_initial_flow_rounding(self):
        printed = self.result["variants"]["printed-l11"]["plane"]
        saved = self.result["variants"]["saved-a39-a01-a40"]["plane"]
        # The printed exclusion survives any plausible initial-flow error: it
        # would take more than one kilogram per second to overturn it.
        self.assertLess(as_float(printed["stock_verdict_margin_per_initial_fuel_flow_error"]), -1.0)
        # The saved inclusion tolerates an initial-flow error of order 1e-6.
        self.assertGreater(as_float(saved["stock_verdict_margin_per_initial_fuel_flow_error"]), 0.0)
        self.assertLess(as_float(saved["stock_verdict_margin_per_initial_fuel_flow_error"]), 1e-4)

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
        self.assertEqual(table["printed-c2-c3"]["printed-l11"]["fuel_flow_difference"],
                         "-704988007/1056439000")
        self.assertEqual(table["scaled-c2-c3"]["printed-l11"]["oxidizer_flow_difference"],
                         "-1338503179/396164625")
        self.assertEqual(table["scaled-c2-c3"]["printed-l11"]["fuel_flow_difference"],
                         "-1287550507/1056439000")

    def test_only_the_scaled_law_slope_equals_an_input_matrix(self):
        slopes = self.result["law_input_slope"]
        self.assertEqual(slopes["printed-c2-c3"]["reference_input_slope_at_d_zero"],
                         ["1014/55", "-2439/220"])
        self.assertEqual(slopes["scaled-c2-c3"]["reference_input_slope_at_d_zero"],
                         ["1104/55", "-576/55"])
        self.assertFalse(slopes["printed-c2-c3"]["matches_input_matrix_per_variant"]["printed-l11"])
        self.assertFalse(slopes["printed-c2-c3"]["matches_input_matrix_per_variant"]["saved-a39-a01-a40"])
        self.assertFalse(slopes["scaled-c2-c3"]["matches_input_matrix_per_variant"]["printed-l11"])
        self.assertTrue(slopes["scaled-c2-c3"]["matches_input_matrix_per_variant"]["saved-a39-a01-a40"])

    def test_mixture_identities(self):
        mixture = self.result["mixture"]
        self.assertTrue(mixture["nominal_ratio_identity_1200_over_450"])
        self.assertEqual(mixture["nominal_mixture_ratio"], "8/3")
        self.assertEqual(mixture["initial_mixture_perturbation"], "8/75")
        self.assertEqual(mixture["initial_perturbation_relative_to_K"], "1/25")
        self.assertEqual(mixture["throttle_sensitivity_c1"], "8/75")
        self.assertEqual(mixture["reachable_mixture_band_accumulated_action_in_unit_interval"],
                         ["0/1", "16/75"])
        self.assertEqual(mixture["reachable_mixture_band_per_step_control_in_unit_interval"],
                         ["-8/5", "136/75"])
        self.assertEqual(mixture["phase_box_upper_face_excess_over_K"], "1/6")
        self.assertEqual(mixture["phase_box_lower_face_excess_over_K"], "-2/13")

    def test_only_the_saved_input_matrix_matches_the_printed_throttle_sensitivity(self):
        mixture = self.result["mixture"]
        self.assertEqual(mixture["mixture_sensitivity_per_variant"]["printed-l11"], "49/450")
        self.assertEqual(mixture["mixture_sensitivity_per_variant"]["saved-a39-a01-a40"], "8/75")
        self.assertFalse(mixture["mixture_sensitivity_matches_c1_per_variant"]["printed-l11"])
        self.assertTrue(mixture["mixture_sensitivity_matches_c1_per_variant"]["saved-a39-a01-a40"])

    def test_initial_mixture_ratios_are_208_over_75_up_to_rounding(self):
        ratios = {key: value["initial_mixture_ratio"]
                  for key, value in self.result["variants"].items()}
        self.assertEqual(ratios["printed-l11"]["target_K_plus_dK"], "208/75")
        self.assertEqual(ratios["saved-a39-a01-a40"]["target_K_plus_dK"], "208/75")
        # The printed flows carry three decimals, so their ratio misses the
        # target by about 3.2e-6; the saved flows carry fourteen digits.
        self.assertLess(abs(as_float(ratios["printed-l11"]["difference"])), 1e-5)
        self.assertGreater(as_float(ratios["printed-l11"]["difference"]), 0.0)
        self.assertLess(abs(as_float(ratios["saved-a39-a01-a40"]["difference"])), 1e-13)

    def test_linear_phase_box_binds_through_the_x1_faces(self):
        box = self.result["linear_phase_box"]["saved-a39-a01-a40"]
        self.assertTrue(box["x1_control_range_exceeds_box"])
        self.assertTrue(box["x3_inside_box_along_tie_line"])
        self.assertEqual(box["binding_flow_box_faces"], ["x1"])
        self.assertEqual(box["tie_line_at_box_x1_ends"]["1176/1"]["x3"],
                         "1331440554305551/2875000000000")
        self.assertEqual(box["tie_line_at_box_x1_ends"]["1224/1"]["x3"],
                         "1259440554305551/2875000000000")

    def test_stored_record_matches_the_recomputed_record(self):
        stored = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(stored, self.result)

    def test_record_declares_its_limitations(self):
        limitations = self.result["limitations"]
        self.assertTrue(any("No optimizer" in item for item in limitations))
        self.assertTrue(any("provisional owner recollection" in item for item in limitations))
        self.assertIn("scope", self.result)
        self.assertTrue(self.result["sources"])


if __name__ == "__main__":
    unittest.main()

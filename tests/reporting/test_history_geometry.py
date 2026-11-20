"""Actual solver membership and independent factor-witness checks."""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks/reporting/closed_loop"))
from history_geometry import parse, verify
from history_norm_solver import solve


class GeometryMembershipTests(unittest.TestCase):
    def test_all_membership_forms_constrain_the_original_objective(self):
        relation = {"inequalities": [], "upper_bounds": [], "equalities": [], "equality_values": []}
        objective = {"quadratic": {"Q": [[2, 0], [0, 2]], "linear": [-2, 0], "offset": 1},
                     "residual_norms": []}
        memberships = [
            {"kind": "h", "indices": [0, 1], "inequalities": [[1, 0]], "upper_bounds": [0.5],
             "equalities": [], "equality_values": []},
            {"kind": "zonotope", "indices": [0, 1], "center": [0, 0],
             "factor_count": 1, "factor": [[0.5], [0]]},
            {"kind": "ellipsoid", "indices": [0, 1], "center": [0, 0],
             "factor_count": 2, "factor": [[0.5, 0], [0, 0.5]]},
        ]
        for membership in memberships:
            with self.subTest(kind=membership["kind"]):
                answer = solve(relation, objective, initial=[0, 0], geometry_memberships=[membership])
                self.assertTrue(answer["success"], answer)
                self.assertAlmostEqual(answer["primal"][0], 0.5, places=5)
                self.assertAlmostEqual(answer["primal"][1], 0, places=5)
                self.assertAlmostEqual(answer["objective"], 0.25, places=5)
                self.assertTrue(answer["geometry_validation"]["accepted"])

    def test_rejects_forged_and_degenerate_factor_witnesses(self):
        membership = {"kind": "zonotope", "indices": [0, 1], "center": [0, 0],
                      "factor_count": 1, "factor": [[1], [0]]}
        entries = parse([membership], 2)
        self.assertFalse(verify(entries, [2, 0], [[2]])["accepted"])
        self.assertFalse(verify(entries, [0.5, 0], [[0.1]])["accepted"])
        point = {"kind": "ellipsoid", "indices": [0, 1], "center": [1, 2],
                 "factor_count": 0, "factor": [[], []]}
        self.assertTrue(verify(parse([point], 2), [1, 2], [[]])["accepted"])
        self.assertFalse(verify(parse([point], 2), [1, 2.1], [[]])["accepted"])

    def test_zero_column_ellipsoid_constrains_to_single_point(self):
        relation = {"inequalities": [], "upper_bounds": [], "equalities": [], "equality_values": []}
        objective = {"quadratic": {"Q": [[2, 0], [0, 2]], "linear": [0, 0], "offset": 0},
                     "residual_norms": []}
        point = {"kind": "ellipsoid", "indices": [0, 1], "center": [1, 2],
                 "factor_count": 0, "factor": [[], []]}
        answer = solve(relation, objective, initial=[1, 2], geometry_memberships=[point])
        self.assertTrue(answer["success"], answer)
        self.assertAlmostEqual(answer["primal"][0], 1)
        self.assertAlmostEqual(answer["primal"][1], 2)
        self.assertEqual(answer["geometry_factors"], [[]])

    def test_fixed_axis_ellipsoid_retains_exact_witness_without_repeated_equalities(self):
        relation = {"inequalities": [], "upper_bounds": [], "equalities": [[1, 0]],
                    "equality_values": [1]}
        objective = {"quadratic": {"Q": [[0, 0], [0, 2]], "linear": [0, -2], "offset": 1},
                     "residual_norms": []}
        point = {"kind": "ellipsoid", "indices": [0], "center": [1],
                 "factor_count": 1, "factor": [[0]]}
        small = {**point, "center": [1 + 2**-45], "factor": [[2**-44]]}
        answer = solve(relation, objective, initial=[1, 0], positive_indices=[0],
                       geometry_memberships=[point, small, small])
        self.assertTrue(answer["success"], answer)
        self.assertEqual(answer["warm_start"]["fixed_geometry_witnesses"], [0, 1, 2])
        self.assertEqual(answer["geometry_factors"], [[0.0], [-0.5], [-0.5]])
        self.assertAlmostEqual(answer["primal"][1], 1.0)
        self.assertTrue(answer["geometry_validation"]["accepted"])

        outside = {**small, "factor": [[2**-46]]}
        impossible = solve(relation, objective, initial=[1, 0], positive_indices=[0],
                           geometry_memberships=[outside])
        self.assertNotIn("fixed_geometry_witnesses", impossible["warm_start"])

    def test_physical_scaling_preserves_original_history_and_witnesses(self):
        relation = {"inequalities": [], "upper_bounds": [], "equalities": [[1, 0]],
                    "equality_values": [7000]}
        objective = {"quadratic": {"Q": [[0, 0], [0, 2]], "linear": [0, -2], "offset": 1},
                     "residual_norms": []}
        memberships = [
            {"kind": "zonotope", "indices": [0], "center": [7000],
             "factor_count": 1, "factor": [[0]]},
            {"kind": "zonotope", "indices": [1], "center": [0],
             "factor_count": 1, "factor": [[0.5]]},
        ]
        result = solve(relation, objective, initial=[7000, 0.25], positive_indices=[0, 1],
                       geometry_memberships=memberships, physical_scales=[1000, 0.01])
        self.assertTrue(result["success"], result)
        self.assertEqual(result["warm_start"]["provider_initial_primal"], [7000, 0.25])
        self.assertEqual(result["warm_start"]["fixed_geometry_witnesses"], [0])
        self.assertEqual(result["numerical_profile"], "physical-scaling")
        self.assertAlmostEqual(result["primal"][0], 7000)
        self.assertAlmostEqual(result["primal"][1], 0.5, places=5)
        self.assertAlmostEqual(result["objective"], 0.25, places=5)
        self.assertTrue(verify(parse(memberships, 2), result["primal"],
                               result["geometry_factors"])["accepted"])

    def test_lifted_membership_uses_the_mandatory_original_rows_as_witness(self):
        relation = {"set_id": "original", "representation": "polytope-h",
                    "inequalities": [[0, 1]], "upper_bounds": [0.5],
                    "equalities": [[1, 0]], "equality_values": [0]}
        objective = {"quadratic": {"Q": [[2, 0], [0, 2]], "linear": [0, -2], "offset": 1},
                     "residual_norms": []}
        prefix = {"kind": "lifted-h", "indices": [0], "history_set_id": "original",
                  "row_selection": {"kind": "prefix", "inequalities": [], "equalities": [[0, 1]]}}
        full = {**prefix, "row_selection": {"kind": "full"}}
        entries = parse([prefix, full], 2, relation=relation)
        checked = verify(entries, [0, 0.75], [[], []])
        self.assertTrue(checked["checks"][0]["passed"])
        self.assertFalse(checked["checks"][1]["passed"])
        with self.assertRaisesRegex(ValueError, "mandatory"):
            parse([{**full, "history_set_id": "different"}], 2, relation=relation)
        wrong = {**prefix, "row_selection": {**prefix["row_selection"], "equalities": [[0, 2]]}}
        with self.assertRaisesRegex(ValueError, "row range"):
            parse([wrong], 2, relation=relation)
        answer = solve(relation, objective, initial=[0, 0], geometry_memberships=[prefix, full])
        self.assertTrue(answer["success"], answer)
        self.assertAlmostEqual(answer["primal"][1], 0.5, places=5)
        self.assertEqual(answer["geometry_factors"], [[], []])

    def test_lifted_route_rejects_omitted_and_future_prefix_rows(self):
        from history_policy import LIFTED_POLYTOPE_IMPLEMENTATION, geometry_memberships
        request = {"state_bounds": [None], "control_bounds": [[-1, 1]]}
        stages = []
        for k in range(2):
            members = []
            for role in ("forward", "backward", "intersection"):
                rows = ({"kind": "prefix", "inequalities": [[0, 2]] if k else [],
                         "equalities": [[0, k + 1]]} if role == "forward" else {"kind": "full"})
                members.append({"role": role, "indices": [k], "kind": "lifted-h",
                    "relation": "equivalent", "assurance": "validated", "row_selection": rows})
            stages.append({"stage": k, "coordinates": [0], "memberships": members})
        export = {"status": "complete", "family": "polytope",
                  "scope": "forward_relevant_from_observation",
                  "polytope_history": "lifted_whole_history",
                  "implementation": LIFTED_POLYTOPE_IMPLEMENTATION, "stages": stages}
        self.assertEqual(len(geometry_memberships(export, "polytope", 1, 1, lifted_request=request)), 6)
        selection = stages[0]["memberships"][0]["row_selection"]
        for bad in ([], [[0, 2]]):
            selection["equalities"] = bad
            with self.assertRaisesRegex(ValueError, "projection claim"):
                geometry_memberships(export, "polytope", 1, 1, lifted_request=request)

    def test_source_acceptance_independently_checks_geometry_witness(self):
        from history_validation import validate
        task = {"episode": {"intervals": 1},
                "model": {"states": [{"bounds": None}, {"bounds": None}],
                          "controls": [{}], "case_id": "fixture"},
                "control_domains": {"continuous": {"bounds": [[-1, 1]]}}}
        predictor = [{"A": [[1, 0], [0, 1]], "B": [[0], [0]], "c": [0, 0]}]
        relation = {"inequalities": [], "upper_bounds": [], "equalities": [], "equality_values": []}
        membership = {"kind": "zonotope", "indices": [2, 3], "center": [0, 0],
                      "factor_count": 1, "factor": [[1], [0]]}
        with mock.patch("history_validation.objective", return_value={"total": 0}):
            result = validate(task, 0, [0.5, 0], predictor, relation, [0.5, 0, 0.5, 0, 0], 0,
                              geometry_memberships=[membership], geometry_factors=[[0.5]])
            self.assertTrue(result["accepted"], result)
            bad = validate(task, 0, [0.5, 0], predictor, relation, [0.5, 0, 0.5, 0, 0], 0,
                           geometry_memberships=[membership], geometry_factors=[[0.1]])
            self.assertFalse(bad["accepted"])
            self.assertFalse(bad["checks"]["geometry"]["passed"])
            with self.assertRaises(ValueError):
                validate(task, 0, [0.5, 0], predictor, relation, [0.5, 0, 0.5, 0, 0], 0,
                         geometry_memberships=[membership])

    def test_geometry_export_requires_all_stage_roles_and_requested_family(self):
        from history_policy import geometry_memberships
        def row(k, role):
            return {"kind": "h", "indices": [2*k, 2*k+1], "role": role,
                    "relation": "outer", "inequalities": [], "upper_bounds": [],
                    "equalities": [], "equality_values": []}
        stages = [{"stage": k, "coordinates": [0, 1],
                   "memberships": [row(k, role) for role in ("forward", "backward", "intersection")]}
                  for k in range(2)]
        export = {"family": "box", "scope": "forward_relevant_from_observation",
                  "status": "complete", "stages": stages}
        self.assertEqual(len(geometry_memberships(export, "box", 2, 1)), 6)
        stages[1]["memberships"].pop()
        with self.assertRaisesRegex(ValueError, "forward, backward and intersection"):
            geometry_memberships(export, "box", 2, 1)

    def test_rejects_invalid_membership_input(self):
        with self.assertRaises(ValueError):
            parse([{"kind": "h", "indices": [0, 0], "inequalities": [], "upper_bounds": [],
                    "equalities": [], "equality_values": []}], 2)


if __name__ == "__main__":
    unittest.main()

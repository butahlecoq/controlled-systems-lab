"""Behavior at the native strategy feedback action and initialization boundaries."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))


class NativeStrategyHistoryTest(unittest.TestCase):
    def test_first_actuation_uses_the_literal_physical_bounds(self):
        from native_strategy_history import actuation_error

        self.assertEqual(actuation_error([0.5, -0.5], [[-0.5, 0.5], [-0.5, 0.5]]), 0)
        self.assertGreater(actuation_error([0.5, -0.50000000000002], [[-0.5, 0.5], [-0.5, 0.5]]), 0)

    def test_seed_for_a_rank_deficient_factor_is_a_real_bounded_witness(self):
        from native_strategy_history import feasible_membership_factors

        membership = {
            "kind": "zonotope",
            "indices": [0, 1],
            "factor_count": 3,
            "center": [0, 0],
            "factor": [[1, 1, 0], [0, 0, 0]],
        }
        [factors] = feasible_membership_factors([membership], [1.8, 0], {}, 2)
        self.assertAlmostEqual(factors[0] + factors[1], 1.8)
        self.assertTrue(all(-1 <= value <= 1 for value in factors))
        with self.assertRaisesRegex(ValueError, "membership"):
            feasible_membership_factors([membership], [1.8, 0.2], {}, 2)

    def test_native_axis_witness_and_h_source_binding_are_checked(self):
        from native_strategy_history import verify_native_geometry_receipt

        member = {
            "kind": "h",
            "role": "forward",
            "set_id": "selected",
            "relation": "outer",
            "indices": [0, 1],
            "inequalities": [[1, 0], [-1, 0]],
            "upper_bounds": [1, 1],
            "equalities": [[0, 1]],
            "equality_values": [2],
        }
        geometry = {
            "family": "box",
            "stages": [
                {
                    "stage": 0,
                    "memberships": [member],
                    "forward_h": {"set_id": "source"},
                }
            ],
        }
        binding = {
            "stage": 0,
            "role": "forward",
            "selected": "selected",
            "reference": "source",
            "relation": "outer",
        }
        receipt = {"geometry_bindings": [binding], "geometry_factors": [[0.5, 0.0]]}
        self.assertTrue(verify_native_geometry_receipt(geometry, [0.5, 2], receipt)["passed"])
        wrong_factor = dict(receipt, geometry_factors=[[0.9, 0.0]])
        self.assertFalse(verify_native_geometry_receipt(geometry, [0.5, 2], wrong_factor)["passed"])
        wrong_source = dict(receipt, geometry_bindings=[dict(binding, reference="another")])
        with self.assertRaisesRegex(ValueError, "source"):
            verify_native_geometry_receipt(geometry, [0.5, 2], wrong_source)

        member["parallelotope_frame"] = [[1, 0], [0, 1]]
        geometry["family"] = "parallelotope"
        receipt["geometry_factors"] = [[0.5, 2.0]]
        self.assertTrue(verify_native_geometry_receipt(geometry, [0.5, 2], receipt)["passed"])
        receipt["geometry_factors"] = [[0.5, 3.0]]
        self.assertFalse(verify_native_geometry_receipt(geometry, [0.5, 2], receipt)["passed"])

    def test_nonaxis_parallelotope_frame_membership_is_verified(self):
        import math

        from native_strategy_history import verify_native_geometry_receipt

        r = math.sqrt(0.5)
        frame = [[r, -r], [r, r]]
        member = {
            "kind": "h",
            "role": "forward",
            "set_id": "selected",
            "relation": "outer",
            "indices": [0, 1],
            # The producer exports the frame columns as H rows.
            "inequalities": [[r, r], [-r, -r], [-r, r], [r, -r]],
            "upper_bounds": [0.5, 0.5, 0.5, 0.5],
            "equalities": [],
            "equality_values": [],
            "parallelotope_frame": frame,
            "parallelotope_frame_lower": [-0.5, -0.5],
            "parallelotope_frame_upper": [0.5, 0.5],
        }
        geometry = {
            "family": "parallelotope",
            "stages": [
                {
                    "stage": 0,
                    "memberships": [member],
                    "forward_h": {"set_id": "source"},
                }
            ],
        }
        binding = {
            "stage": 0,
            "role": "forward",
            "selected": "selected",
            "reference": "source",
            "relation": "outer",
        }
        # x = frame * factor with factor (0.25, -0.1).
        state = [r * (0.25 + 0.1), r * (0.25 - 0.1)]
        receipt = {"geometry_bindings": [binding], "geometry_factors": [[0.25, -0.1]]}
        self.assertTrue(verify_native_geometry_receipt(geometry, state, receipt)["passed"])

        beyond_bounds = dict(receipt, geometry_factors=[[0.6, -0.1]])
        self.assertFalse(verify_native_geometry_receipt(geometry, state, beyond_bounds)["passed"])

        wrong_state = dict(receipt, geometry_factors=[[0.25, -0.35]])
        self.assertFalse(
            verify_native_geometry_receipt(geometry, [0.9, 0.0], wrong_state)["passed"]
        )

        sheared = dict(member, parallelotope_frame=[[1.0, 1.0], [0.0, 1.0]])
        sheared_geometry = {
            "family": "parallelotope",
            "stages": [
                {
                    "stage": 0,
                    "memberships": [sheared],
                    "forward_h": {"set_id": "source"},
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            verify_native_geometry_receipt(sheared_geometry, state, receipt)

        legacy = {
            key: value for key, value in member.items() if not key.startswith("parallelotope_frame")
        }
        legacy["parallelotope_frame"] = [[1, 0], [0, 1]]
        legacy["inequalities"] = [[1, 0], [-1, 0], [0, 1], [0, -1]]
        legacy["upper_bounds"] = [0.5, 0.5, 0.5, 0.5]
        legacy_geometry = {
            "family": "parallelotope",
            "stages": [{"stage": 0, "memberships": [legacy], "forward_h": {"set_id": "source"}}],
        }
        legacy_receipt = {"geometry_bindings": [binding], "geometry_factors": [[0.25, 0.4]]}
        self.assertTrue(
            verify_native_geometry_receipt(legacy_geometry, [0.25, 0.4], legacy_receipt)["passed"]
        )

    def test_factor_feasibility_lp_is_recorded_even_if_it_stops(self):
        from native_strategy_history import feasible_membership_factors

        member = {
            "kind": "zonotope",
            "indices": [0],
            "factor_count": 3,
            "center": [0],
            "factor": [[1, 1, 2]],
        }
        calls = []
        [factor] = feasible_membership_factors([member], [3.6], {}, 1, lp_calls=calls)
        self.assertAlmostEqual(factor[0] + factor[1] + 2 * factor[2], 3.6)
        self.assertEqual(calls, ["history.start-membership-feasibility"])
        calls.clear()
        with self.assertRaisesRegex(ValueError, "feasibility"):
            feasible_membership_factors([member], [5], {}, 1, lp_calls=calls)
        self.assertEqual(calls, ["history.start-membership-feasibility"])

    def test_native_receipt_requires_requested_program_and_boolean_readback(self):
        import json

        from native_strategy_history import solve_strategy

        request = {
            "task_id": "test",
            "task_sha256": "test-hash",
            "action_profile_id": "continuous",
            "controller_id": "controller",
            "request_id": "original",
            "control_bounds": [[-1, 1]],
        }
        task = {"model": {"case_id": "test"}}
        exported = {"history_relation": {}, "history_objective": {}, "geometry": {}}
        receipt = {
            "provider": "csl.nlp.casadi-ipopt.history-cost",
            "strategy": "A",
            "strategy_module": "csl.synthesis.reach-back",
            "program_id": "original",
            "supplied_readback": True,
        }
        response = dict(
            request, **exported, status="solved", policy_id="controller", solver_receipt=receipt
        )
        for status in ("solved", "failed"):
            for changes in ({"program_id": "unrelated"}, {"supplied_readback": "false"}):
                with self.subTest(status=status, changes=changes):
                    rejected = dict(
                        response,
                        status=status,
                        solver_receipt=dict(receipt, **changes),
                    )
                    serialized = json.dumps(rejected)
                    with self.assertRaisesRegex(ValueError, "requested route"):
                        solve_strategy(
                            task,
                            request,
                            exported,
                            [],
                            "A",
                            [0],
                            [],
                            lambda _raw, serialized=serialized: serialized,
                            lambda _attempts: None,
                        )

        failed = dict(response, status="failed")
        del failed["solver_receipt"]
        candidate, checks, attempts = solve_strategy(
            task,
            request,
            exported,
            [],
            "A",
            [0],
            [],
            lambda _raw: json.dumps(failed),
            lambda _attempts: None,
        )
        self.assertIsNone(candidate)
        self.assertIsNone(checks)
        self.assertTrue(attempts)
        for attempt in attempts:
            self.assertEqual(attempt["outcome"], "failed")
            self.assertNotIn("actual_provider", attempt)

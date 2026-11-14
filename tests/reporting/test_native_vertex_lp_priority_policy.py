"""Exercise real bridge priority selection on changing membership LP domains."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from native_graph_probe import bind_task_hash, request
from native_graph_policy import NativeGraphPolicy

POLICY = "structural-column-index/v1"
TRIANGLE = [[-1.0, -1.0], [1.0, -1.0], [0.0, 1.0]]
SQUARE = [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]


def fixture(actions: list[list[float]], *, policy: str | None = POLICY,
            hull: str = "csl.hull.lp-membership", lp: str = "phase-one-priority-tie") -> dict:
    query = request(middle_bound=[[-2.0, 2.0], [-2.0, 2.0]],
                    controller="native-priority-policy-test", hull_provider=hull,
                    vertex_lp_provider=lp)
    query["original_horizon"] = 1
    query["predictor_stages"] = [{"A": [[1.0, 0.0], [0.0, 1.0]],
                                    "B": [[1.0, 0.0], [0.0, 1.0]], "c": [0.0, 0.0]}]
    query["actions"] = actions
    query["state_bounds"] = [[-2.0, 2.0], [-2.0, 2.0]]
    query["stage_state_bounds"] = [[[0.0, 0.0], [0.0, 0.0]], query["state_bounds"]]
    query["running_cost"]["stages"] = [{"stage": 0, "terms": []}]
    if policy is not None:
        query["vertex_lp_priority_policy"] = policy
    bind_task_hash(query)
    return query


def assumptions(response: dict) -> list[str]:
    return [item for call in response["geometry_invocations"]
            for item in call["evidence_assumptions"]]


def factory_options(query: dict) -> dict:
    names = ("reachable_set_method", "hull_provider", "vertex_lp_provider",
             "conversion_provider", "checker_budget", "control_optimizer", "limits",
             "vertex_lp_priority_policy")
    return {key: query[key] for key in names if key in query}


class PriorityPolicyWrapperBoundaryTests(unittest.TestCase):
    def test_declared_policy_is_forwarded_and_absence_is_preserved(self):
        for explicit in (True, False):
            policy = NativeGraphPolicy.__new__(NativeGraphPolicy)
            policy.use_backward_graph = True
            policy.factory_options = factory_options(fixture(SQUARE, policy=POLICY if explicit else None))
            options = policy._geometry_options()
            self.assertEqual("vertex_lp_priority_policy" in options, explicit)
            if explicit:
                self.assertEqual(options["vertex_lp_priority_policy"], POLICY)

    def test_malformed_unknown_and_inactive_wrapper_policy_is_not_dropped(self):
        cases = [fixture(SQUARE, policy="unknown/v1"), fixture(SQUARE, lp="phase-one-bland")]
        malformed = fixture(SQUARE)
        malformed["vertex_lp_priority_policy"] = None
        cases.append(malformed)
        source = fixture(SQUARE)
        source["reachable_set_method"]["id"] += ".source-index"
        source["vertex_lp_provider"] = "not_used"
        cases.append(source)
        for query in cases:
            for active in (True, False):
                with self.subTest(query=query, active=active):
                    policy = NativeGraphPolicy.__new__(NativeGraphPolicy)
                    policy.factory_options = factory_options(query)
                    policy.use_backward_graph = active
                    with self.assertRaisesRegex(ValueError, "vertex_lp_priority_policy"):
                        policy._geometry_options()


@unittest.skipUnless(os.environ.get("CSL_NATIVE_POLICY_BRIDGE"),
                     "Configured native CTest supplies the built bridge")
class NativeVertexLpPriorityPolicyTests(unittest.TestCase):
    def run_query(self, query: dict) -> dict:
        result = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
                                input=json.dumps(query) + "\n", text=True,
                                capture_output=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def test_real_policy_wrapper_forwards_priority_and_binds_both_native_receipts(self):
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                query = fixture(SQUARE, policy=POLICY if explicit else None)
                task = {"task_id": query["task_id"],
                        "control_domains": {"finite": {"problem_id": query["action_profile_id"], "actions": SQUARE}},
                        "model": {"model_id": query["source_model_id"],
                                  "states": [{"bounds": bound} for bound in query["state_bounds"]]},
                        "episode": {"intervals": 1, "dt": 1.0},
                        "objective": {"objective_id": query["running_cost"]["objective_id"]}}
                receipt = {"model_id": query["predictor_model_id"],
                           "coefficient_assurance": query["predictor_assurance"],
                           "physical_coefficients": query["predictor_stages"]}
                # Supply an authored one-stage identity plant to the source adapters;
                # preparation, option forwarding, process exchange and receipts are real.
                with patch("native_graph_policy.prediction_receipt", return_value=receipt), \
                        patch("native_graph_policy._source_cost", return_value=query["running_cost"]), \
                        patch("native_graph_policy._terminal_objective", return_value=query["terminal_objective"]):
                    policy = NativeGraphPolicy(task, query["task_sha256"],
                        "native-exact-polytope-backward-graph/1", query["action_profile_id"], factory_options(query))
                try:
                    response = policy.query(task["task_id"], [0.0, 0.0], 0)
                    self.assertEqual(response["status"], "accepted", response)
                    sent = response["query_receipt"]["request"]
                    for selection in (sent, response["geometry_selection"],
                                      response["graph_receipt"]["geometry_selection"]):
                        self.assertEqual("vertex_lp_priority_policy" in selection, explicit)
                        if explicit:
                            self.assertEqual(selection["vertex_lp_priority_policy"], POLICY)
                    evidence = assumptions(response)
                    if explicit:
                        self.assertTrue(any("actual_provider=phase-one-priority-tie@1;" in item and
                                            "status=completed;" in item for item in evidence), evidence)
                    else:
                        self.assertTrue(any("Priority count must match" in item for item in evidence), evidence)
                finally:
                    policy.close()

    def test_nonfive_membership_domains_execute_the_selected_priority_provider(self):
        observed_columns = set()
        for points in (TRIANGLE, SQUARE):
            with self.subTest(points=points):
                response = self.run_query(fixture(points))
                self.assertEqual(response["status"], "accepted", response)
                for selection in (response["geometry_selection"],
                                  response["graph_receipt"]["geometry_selection"]):
                    self.assertEqual(selection["vertex_lp_priority_policy"], POLICY)
                evidence = assumptions(response)
                reducers = [item for item in evidence if item.startswith("HullReducerPort invocation:")]
                self.assertTrue(reducers)
                self.assertTrue(all("status=complete;" in item for item in reducers), reducers)
                retained = ",".join(str(index) for index in range(len(points)))
                self.assertTrue(any(item.endswith("retained_original_ids=" + retained)
                                    for item in reducers), reducers)
                calls = [item for item in evidence if item.startswith("vertex LP invocation record:")]
                self.assertTrue(calls)
                self.assertTrue(all("status=completed;" in item and
                                    "actual_provider=phase-one-priority-tie@1;" in item
                                    for item in calls), calls)
                # Each authored point is extreme and retained. membership_program
                # allocates one structural variable for every other retained point.
                observed_columns.add(len(points) - 1)
        self.assertEqual(observed_columns, {2, 3})

    def test_absent_policy_preserves_legacy_five_priority_refusal(self):
        response = self.run_query(fixture(TRIANGLE, policy=None))
        self.assertEqual(response["status"], "accepted", response)
        self.assertNotIn("vertex_lp_priority_policy", response["geometry_selection"])
        evidence = assumptions(response)
        self.assertTrue(any("Priority count must match the structural variable count" in item
                            and "status=rejected;" in item for item in evidence), evidence)
        self.assertTrue(any("all generated candidates retained because the complete HullReducerPort reduction failed"
                            in item for item in evidence), evidence)

    def test_absent_policy_keeps_bland_provider_identity(self):
        response = self.run_query(fixture(SQUARE, policy=None, lp="phase-one-bland"))
        self.assertEqual(response["status"], "accepted", response)
        self.assertNotIn("vertex_lp_priority_policy", response["geometry_selection"])
        self.assertTrue(any("actual_provider=phase-one-bland@1;" in item and "status=completed;" in item
                            for item in assumptions(response)))

    def test_policy_preserves_workspace_bound_basis_diagnostics(self):
        response = self.run_query(fixture(SQUARE, hull="csl.hull.phase-one-basis-bulk"))
        self.assertEqual(response["status"], "accepted", response)
        evidence = assumptions(response)
        basis = [item for item in evidence if item.startswith("HullReducerPort basis_reuse:")]
        self.assertTrue(basis)
        self.assertTrue(any(re.search(r"basis_solves=[1-9][0-9]*;", item) and
                            "fell_back_to_lp_baseline=false" in item for item in basis), basis)
        self.assertTrue(any(item.startswith("HullReducerPort child LPPort invocation:") and
                            "actual_provider=phase-one-priority-tie@1;" in item and "status=completed" in item
                            for item in evidence), evidence)

    def test_unknown_malformed_and_inactive_policies_refuse_before_geometry(self):
        cases = [fixture(SQUARE, policy="unknown/v1"), fixture(SQUARE, lp="phase-one-bland")]
        malformed = fixture(SQUARE)
        malformed["vertex_lp_priority_policy"] = []
        cases.append(malformed)
        source_index = fixture(SQUARE)
        source_index["reachable_set_method"]["id"] += ".source-index"
        source_index["vertex_lp_provider"] = "not_used"
        cases.append(source_index)
        inactive = fixture(SQUARE)
        del inactive["search_policy"]
        cases.append(inactive)
        for query in cases:
            with self.subTest(policy=query.get("vertex_lp_priority_policy"), lp=query["vertex_lp_provider"]):
                response = self.run_query(query)
                self.assertEqual(response["status"], "rejected", response)
                self.assertIn("vertex_lp_priority_policy", response["reason"])
                self.assertEqual(response["vertex_lp_priority_policy"], query["vertex_lp_priority_policy"])
                self.assertEqual(response["invocations"], [])
                self.assertNotIn("geometry_invocations", response)


if __name__ == "__main__":
    unittest.main()

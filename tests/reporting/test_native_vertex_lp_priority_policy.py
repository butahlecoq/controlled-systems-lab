"""Exercise real bridge priority selection on changing membership LP domains."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from native_graph_probe import bind_task_hash, request

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


@unittest.skipUnless(os.environ.get("CSL_NATIVE_POLICY_BRIDGE"),
                     "Configured native CTest supplies the built bridge")
class NativeVertexLpPriorityPolicyTests(unittest.TestCase):
    def run_query(self, query: dict) -> dict:
        result = subprocess.run([os.environ["CSL_NATIVE_POLICY_BRIDGE"]],
                                input=json.dumps(query) + "\n", text=True,
                                capture_output=True, check=True, timeout=20)
        return json.loads(result.stdout)

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

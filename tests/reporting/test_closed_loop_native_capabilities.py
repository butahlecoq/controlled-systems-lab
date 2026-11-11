from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import capabilities
import run_closed_loop


class NativeCapabilityTests(unittest.TestCase):
    def test_native_profiles_bind_all_tasks_to_finite_action_domains(self):
        manifest = capabilities.build_native_manifest()
        self.assertEqual(len(manifest["graphs"]), 30)
        self.assertEqual(manifest["registration_status"], "provisional-pending-native-source-freeze")
        expected_profiles = set(capabilities.NATIVE_PROFILES)
        by_task: dict[str, set[str]] = {}
        for graph in manifest["graphs"]:
            by_task.setdefault(graph["task_id"], set()).add(graph["controller"]["id"])
            task_name = "earth-orbit" if graph["task_id"].startswith("env717-earth-orbit/") else graph["task_id"].split("/")[0]
            self.assertEqual(graph["action_profile_id"],
                capabilities.load_task(task_name)["control_domains"]["finite"]["problem_id"])
            self.assertEqual(graph["controller"]["policy_factory"], "native_graph_policy:create_policy")
            self.assertTrue(graph["source_files"])
            self.assertEqual(graph["source_files"], sorted(graph["source_files"], key=lambda item: item["path"]))
        self.assertEqual(len(by_task), 3)
        self.assertTrue(all(profiles == expected_profiles for profiles in by_task.values()))

    def test_fixed_plan_profiles_do_not_claim_geometry_or_lp_calls(self):
        graph = next(row for row in capabilities.build_native_manifest()["graphs"]
            if row["controller"]["id"] == "native-box-fixed-plan-mpc/1")
        roles = graph["role_bindings"]
        self.assertEqual(roles["reachable_set_method"], "not_used")
        self.assertEqual(roles["hull_provider"], "not_used")
        self.assertEqual(roles["vertex_lp"], "not_used")
        self.assertEqual(roles["converter"], "not_used")
        self.assertEqual(roles["representation"], {"name": "box",
            "module_id": "csl::reachability::finite_plan_box", "status": "selected"})
        self.assertEqual(graph["controller"]["control_semantics"], "fixed-plan-mpc")
        self.assertEqual(roles["control_optimizer"], {"module_id": "csl::optimization::finite_action_nominal_profile",
            "provider": "public-function", "operation": "box-plan-select",
            "profile_id": "native-box-fixed-plan-mpc/1"})
        self.assertEqual(graph["controller"]["factory_options"]["build_backend_profile"],
            {"build_type": "Release", "CSL_ENABLE_HIGHS": True, "CSL_ENABLE_QHULL": True})

    def test_graph_profiles_separate_vertex_lp_from_control_solver_roles(self):
        graph = next(row for row in capabilities.build_native_manifest()["graphs"]
            if row["controller"]["id"] == "native-exact-polytope-backward-graph/1")
        roles = graph["role_bindings"]
        self.assertEqual(roles["vertex_lp"]["id"], "phase-one-bland")
        self.assertEqual(roles["control_optimizer"]["id"],
            "csl.optimization.finite-action-stage-layered-graph")
        source_paths = {source["path"] for source in graph["source_files"]}
        self.assertIn("src/geometry/hull_reducer.cpp", source_paths)
        self.assertIn("src/optimization/phase_one/simplex.cpp", source_paths)
        self.assertEqual(roles["bellman_solver"], "integrated in selected graph optimizer")
        self.assertEqual(roles["terminal_solver"], "direct authored objective evaluation")

    def test_generic_policy_prepare_forwards_manifest_factory_options(self):
        graph = {"task_sha256": "task-hash", "action_profile_id": "finite/1",
            "graph_id": "graph/1", "controller": {"id": "native-profile/1",
                "policy_factory": "module:create_policy", "factory_options": {"chosen": "source-bound"}}}
        class Policy:
            preparation_receipt = {"status": "ready"}
        with tempfile.TemporaryDirectory() as raw:
            bridge = Path(raw) / "bridge"
            bridge.write_bytes(b"bridge")
            with mock.patch.object(run_closed_loop, "validate_resolved_graph"), \
                 mock.patch.object(run_closed_loop, "manifest_sha256", return_value="task-hash"), \
                 mock.patch.object(run_closed_loop, "load_policy_adapter") as load_factory:
                factory = mock.Mock(return_value=Policy())
                load_factory.return_value = factory
                policy, receipt = run_closed_loop.prepare_graph({}, graph, bridge)
        factory.assert_called_once_with({}, task_sha256="task-hash", controller_id="native-profile/1",
            action_profile_id="finite/1", factory_options={"chosen": "source-bound"})
        self.assertEqual(policy.preparation_receipt, {"status": "ready"})
        self.assertFalse(receipt["nlp_solve_performed"])
        self.assertEqual(receipt["execution_binary_sha256"], hashlib.sha256(b"bridge").hexdigest())

    def test_missing_native_executable_is_a_preparation_failure_not_unsupported(self):
        graph = next(row for row in capabilities.build_native_manifest()["graphs"]
            if row["task_id"].startswith("syn-nl-lv-01/")
            and row["controller"]["id"] == "native-exact-polytope-backward-graph/1")
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            attempt = folder / "attempt"
            attempt.mkdir()
            bridge = folder / "plant-bridge"
            bridge.write_bytes(b"plant bridge")
            graph_path = folder / "graph.json"
            graph_path.write_text(json.dumps(graph))
            with mock.patch.dict("os.environ", {"CSL_NATIVE_POLICY_BRIDGE": ""}):
                result = run_closed_loop.worker("syn-nl-lv-01", attempt, bridge,
                    graph_path=graph_path)
            receipt = json.loads((attempt / "attempt.json").read_text())
        self.assertEqual(result, 2)
        self.assertEqual(receipt["status"], "preparation_failed")
        self.assertEqual(receipt["mathematical_support_status"], "not_evaluated")
        self.assertIn("CSL_NATIVE_POLICY_BRIDGE", receipt["preparation_failure"]["reason"])

    def test_provider_unavailability_is_a_distinct_non_mathematical_policy_outcome(self):
        query = {"task_sha256": "task-hash", "action_profile_id": "finite/1",
            "status": "unavailable", "policy_id": "native/1", "invocations": [],
            "reason": "selected provider registration unavailable"}
        self.assertEqual(run_closed_loop.validate_policy_response({}, "task-hash", "finite/1", query), query)

    def test_role_trace_keeps_actual_invocations_and_declared_roles(self):
        graph = {"role_bindings": {"control_optimizer": {"id": "optimizer"},
                "reachable_set_method": {"id": "reach"}},
            "operation_roles": {"controller.solve": "control_optimizer", "affine-image": "reachable_set_method"}}
        query = {"invocations": [{"operation": "controller.solve", "module_id": "optimizer",
                "profile_id": "profile", "provider": "native"}],
            "geometry_invocations": [{"operation": "affine-image", "actual_method_id": "reach",
                "output_id": "out"}]}
        rows = run_closed_loop.trace_call_roles(query, graph)
        self.assertEqual([row["role"] for row in rows], ["control_optimizer", "reachable_set_method"])
        self.assertEqual(rows[1]["output_id"], "out")
        self.assertEqual(rows[1]["selected_role_binding"], {"id": "reach"})

    def test_role_trace_labels_nested_reducer_and_lp_evidence(self):
        graph = {"role_bindings": {"hull_provider": {"id": "hull"},
                "vertex_lp": {"id": "lp"}, "geometry_checker": "not_used"}}
        query = {"geometry_invocations": [{"operation": "minkowski-sum",
            "evidence_assumptions": ["HullReducerPort invocation: provider=hull; status=complete",
                "HullReducerPort child LPPort invocation: requested_provider=lp; actual_provider=lp; status=completed"]}]}
        rows = run_closed_loop.trace_call_roles(query, graph)
        self.assertEqual([row["role"] for row in rows], ["reachable_set_method", "hull_provider", "vertex_lp"])
        self.assertEqual(rows[1]["selected_role_binding"], {"id": "hull"})
        self.assertIn("actual_provider=lp", rows[2]["evidence"])

    def test_selected_manifest_digest_is_not_the_historical_pilot_sidecar(self):
        manifest = capabilities.validate_manifest(manifest_path=capabilities.NATIVE_MANIFEST)
        digest = capabilities.manifest_digest(manifest)
        self.assertEqual(digest, capabilities.NATIVE_SIDECAR.read_text().split()[0])
        self.assertNotEqual(digest, capabilities.SIDECAR.read_text().split()[0])

    def test_native_resolution_selects_manifest_seal_and_finite_profile(self):
        task = capabilities.load_task("syn-nl-lv-01")
        action_profile_id = task["control_domains"]["finite"]["problem_id"]
        manifest, graph = capabilities.resolve_graph(task, action_profile_id,
            "native-box-fixed-plan-mpc/1", manifest_path=capabilities.NATIVE_MANIFEST)
        self.assertEqual(graph["action_profile_id"], action_profile_id)
        self.assertEqual(graph["controller"]["id"], "native-box-fixed-plan-mpc/1")
        self.assertEqual(capabilities.manifest_digest(manifest),
            capabilities.NATIVE_SIDECAR.read_text().split()[0])
        with self.assertRaises(ValueError):
            capabilities.resolve_graph(task, task["control_domains"]["continuous"]["problem_id"],
                "native-box-fixed-plan-mpc/1", manifest_path=capabilities.NATIVE_MANIFEST)


if __name__ == "__main__":
    unittest.main()

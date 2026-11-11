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
        self.assertEqual(manifest["registration_status"], "source-frozen")
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
            "status": "selected-in-nominal-profile"})
        self.assertEqual(graph["controller"]["control_semantics"], "fixed-plan-mpc")
        self.assertEqual(roles["control_optimizer"], {"module_id": "csl::optimization::finite_action_nominal_profile",
            "provider": "public-function", "operation": "box-plan-select",
            "profile_id": "native-box-fixed-plan-mpc/1"})
        self.assertEqual(graph["controller"]["factory_options"]["build_backend_profile"],
            {"build_type": "Release", "CSL_ENABLE_HIGHS": True, "CSL_ENABLE_QHULL": True})
        source_paths = {source["path"] for source in graph["source_files"]}
        self.assertIn("src/optimization/finite_action_plans.hpp", source_paths)
        self.assertIn("src/optimization/finite_action_box_minimax.cpp", source_paths)
        self.assertNotIn("src/reachability/finite_plan_box.cpp", source_paths)
        self.assertEqual(graph["candidate_search_policy"], "constant-and-single-switch-full-horizon/1")
        self.assertEqual(graph["controller"]["limit_usage"]["max_plans"], "used_as_candidate_history_budget")
        self.assertEqual(graph["controller"]["limit_usage"]["max_graph_nodes"], "not_used_by_fixed_plan_search")

    def test_graph_profiles_separate_vertex_lp_from_control_solver_roles(self):
        graph = next(row for row in capabilities.build_native_manifest()["graphs"]
            if row["controller"]["id"] == "native-exact-polytope-backward-graph/1")
        roles = graph["role_bindings"]
        self.assertEqual(roles["vertex_lp"]["id"], "phase-one-bland")
        self.assertEqual(roles["control_optimizer"]["id"],
            "csl.optimization.finite-action-stage-layered-graph")
        self.assertEqual(graph["controller"]["factory_options"]["limits"]["max_beam_width"], 8)
        self.assertEqual(graph["controller"]["factory_options"]["limits"]["max_graph_nodes"], 512)
        self.assertEqual(graph["controller"]["limit_usage"]["max_graph_nodes"], "used")
        self.assertEqual(graph["controller"]["limit_usage"]["max_plans"], "not_used_by_graph_search")
        source_paths = {source["path"] for source in graph["source_files"]}
        self.assertIn("src/geometry/hull_reducer.cpp", source_paths)
        self.assertIn("src/optimization/phase_one/simplex.cpp", source_paths)
        self.assertIn("src/geometry/polyhedral/intersection.cpp", source_paths)
        self.assertIn("src/geometry/polyhedral/projection.cpp", source_paths)
        self.assertIn("include/csl/reachability/nominal_predecessor.hpp", source_paths)
        self.assertEqual(roles["bellman_solver"], "integrated in selected graph optimizer")
        self.assertEqual(roles["terminal_solver"], "direct authored objective evaluation")

    def test_graph_representation_adapters_and_shared_admission_header_are_sealed(self):
        manifest = capabilities.build_native_manifest()
        adapters = {"box": "box", "zonotope": "zonotope", "parallelotope": "parallelotope",
            "ellipsoid": "ellipsoid"}
        for representation, stem in adapters.items():
            row = next(item for item in manifest["graphs"] if
                item["controller"]["id"] == f"native-{representation}-mpc/1")
            source_paths = {item["path"] for item in row["source_files"]}
            self.assertIn(f"include/csl/reachability/finite_plan_{stem}.hpp", source_paths)
            self.assertIn(f"src/reachability/finite_plan_{stem}.cpp", source_paths)
            self.assertIn("src/reachability/fixed_plan_admission.hpp", source_paths)

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
        for status in ("unavailable", "incompatible"):
            with self.subTest(status=status):
                query = {"task_sha256": "task-hash", "action_profile_id": "finite/1",
                    "status": status, "policy_id": "native/1", "invocations": [],
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

    def test_manifest_graph_ids_are_an_exact_unique_source_defined_set(self):
        valid = capabilities.validate_manifest(manifest_path=capabilities.NATIVE_MANIFEST)
        self.assertEqual(len(valid["graphs"]), 30)

        mutations = {
            "duplicate": (lambda rows: rows.__setitem__(1, json.loads(json.dumps(rows[0]))),
                "graph IDs are not unique"),
            "missing": (lambda rows: rows.pop(), "graph IDs differ from source definitions"),
            "foreign": (lambda rows: rows[0].__setitem__("graph_id", "closed-loop/foreign/1"),
                "graph IDs differ from source definitions"),
        }
        for label, (mutate, message) in mutations.items():
            with self.subTest(manifest_mutation=label), tempfile.TemporaryDirectory() as raw:
                manifest = json.loads(json.dumps(valid))
                mutate(manifest["graphs"])
                seal = Path(raw) / "native.sha256"
                seal.write_text(capabilities.canonical_sha256(manifest) + "  native.json\n")
                with mock.patch.object(capabilities, "NATIVE_SIDECAR", seal):
                    with self.assertRaisesRegex(ValueError, message):
                        capabilities.validate_manifest(manifest, capabilities.NATIVE_MANIFEST)

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


    def test_native_bridge_failures_persist_request_and_raw_response(self):
        task = capabilities.load_task("earth-orbit")
        graph = next(row for row in capabilities.build_native_manifest()["graphs"]
            if row["task_id"] == task["task_id"] and row["controller"]["id"] == "native-box-mpc/1")
        profile = graph["controller"]["id"]
        base = {"task_id": task["task_id"], "task_sha256": graph["task_sha256"],
            "action_profile_id": graph["action_profile_id"], "policy_id": profile,
            "status": "unsupported", "control": None, "invocations": [],
            "reason": "stubbed native policy outcome",
            "build_backend_profile": {"build_type": "Release", "CSL_ENABLE_HIGHS": True,
                "CSL_ENABLE_QHULL": True}}
        cases = {
            "bad-id": (base | {"task_id": "wrong-task", "status": "accepted", "control": [0, 0]},
                None, "controller_protocol_or_execution_failure"),
            "missing-backend": ({k: v for k, v in base.items() if k != "build_backend_profile"}, None, None),
            "malformed": (None, "{malformed native response\n", "controller_protocol_or_execution_failure"),
            "unsupported": (base, None, None),
            "nonfinite-partial": (base | {"partial_diagnostic": float("nan")}, None,
                "controller_protocol_or_execution_failure"),
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); execution_bridge = root / "execution-bridge"
            execution_bridge.write_bytes(b"unused execution bridge")
            for label, (response, raw_line, expected_category) in cases.items():
                with self.subTest(response_case=label):
                    if raw_line is None:
                        raw_line = json.dumps(response, separators=(",", ":")) + "\n"
                    executable = root / f"native-{label}"
                    source = "#!/usr/bin/env python3\nimport sys\nsys.stdin.readline()\nsys.stdout.write(" + repr(raw_line) + ")\nsys.stdout.flush()\n"
                    executable.write_text(source, encoding="utf-8"); executable.chmod(0o755)
                    attempt = root / f"attempt-{label}"; attempt.mkdir()
                    graph_path = root / f"graph-{label}.json"; graph_path.write_text(json.dumps(graph))
                    with mock.patch.dict("os.environ", {"CSL_NATIVE_POLICY_BRIDGE": str(executable)}):
                        result = run_closed_loop.worker("earth-orbit", attempt, execution_bridge,
                            graph_path=graph_path)
                    self.assertEqual(result, 2)
                    record = json.loads((attempt / "attempt.json").read_text())
                    stage = json.loads((attempt / "stage-000.json").read_text())
                    self.assertEqual((record["status"], record["completed_holds"]), ("incomplete", 0))
                    capture = stage["native_query_capture"]
                    self.assertTrue(capture["bridge_request_sent"])
                    request = json.loads(capture["request_json"])
                    self.assertEqual(capture["bridge_request_raw"], capture["request_json"] + "\n")
                    self.assertEqual(capture["request_sha256"],
                        hashlib.sha256(capture["bridge_request_raw"].encode("utf-8")).hexdigest())
                    self.assertEqual(request["task_sha256"], graph["task_sha256"])
                    self.assertEqual(request["action_profile_id"], graph["action_profile_id"])
                    self.assertEqual(capture["bridge_response_raw"], raw_line)
                    self.assertEqual(capture["bridge_response_sha256"], hashlib.sha256(raw_line.encode()).hexdigest())
                    if expected_category:
                        self.assertEqual(stage["failure_category"], expected_category)
                        self.assertEqual(stage["mathematical_support_status"], "not_evaluated")
                        self.assertEqual(record["mathematical_support_status"], "not_evaluated")
                    if label == "malformed":
                        self.assertEqual(capture["response_parse_status"], "malformed_json")
                    if label == "unsupported":
                        self.assertEqual(stage["controller_status"], "unsupported")
                        self.assertEqual(stage["mathematical_support_status"], "not_established")
                        self.assertEqual(stage["controller_reason"], "stubbed native policy outcome")
                    if label == "missing-backend":
                        self.assertEqual(stage["controller_status"], "failed")
                        self.assertEqual(stage["mathematical_support_status"], "not_evaluated")
                        self.assertEqual(record["mathematical_support_status"], "not_evaluated")
                        self.assertIn("omitted its compiled backend profile", stage["controller_reason"])
                    if label == "bad-id":
                        self.assertIn("source task identity", stage["controller_failure"]["reason"])
                        self.assertEqual(capture["parsed_response"]["task_id"], "wrong-task")
                    if label == "nonfinite-partial":
                        self.assertEqual(stage["mathematical_support_status"], "not_evaluated")
                        self.assertEqual(capture["parsed_response"]["partial_diagnostic"],
                            {"nonfinite_float": "nan"})


if __name__ == "__main__":
    unittest.main()

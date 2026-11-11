"""Executable analytic check for the native finite-action backward graph."""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import subprocess
from pathlib import Path


def request(*, middle_bound: list[list[float]], controller: str,
            reachable_method: str = "csl.geometry.affine-sum",
            hull_provider: str = "csl.hull.lp-membership",
            vertex_lp_provider: str | None = "phase-one-bland") -> dict:
    stages = [{"A": [[1.0, 0.0], [0.0, 1.0]], "B": [[1.0], [0.0]], "c": [0.0, 0.0]} for _ in range(2)]
    bounds = [[[0.0, 0.0], [0.0, 0.0]], middle_bound, [[0.0, 2.0], [0.0, 0.0]]]
    return {
        "schema": "csl.closed-loop.native-policy-query/1", "task_id": "analytic-2d-graph",
        "task_sha256": "", "source_model_id": "analytic-2d/1", "controller_id": controller,
        "action_profile_id": "analytic-actions/1", "problem_id": "analytic-problem", "request_id": controller,
        "absolute_update_index": 0, "observed_physical_state": [0.0, 0.0], "original_horizon": 2, "dt": 1.0,
        "predictor_model_id": "analytic-affine/1", "predictor_assurance": "exact analytic affine map",
        "predictor_stages": stages, "actions": [[0.0], [1.0]], "state_bounds": [[0.0, 2.0], [0.0, 0.0]],
        "stage_state_bounds": bounds,
        "terminal_objective": {"kind": "quadratic", "Q": [[2.0, 0.0], [0.0, 2.0]], "linear": [0.0, 0.0], "offset": 0.0},
        "running_cost": {"objective_id": "analytic-running/1", "stages": [
            {"stage": i, "terms": [{"kind": "quadratic", "reference": [0.0], "scales": [1.0],
             "weights": [1.0], "coefficient": 1.0}]} for i in range(2)]},
        "representation_index": 0, "representation_name": "exact_polytope",
        "reachable_set_method": {"id": reachable_method, "version": "1.0.0"},
        "hull_provider": {"id": hull_provider, "version": "1.0.0"},
        "vertex_lp_provider": ({"id": vertex_lp_provider, "version": "1"}
            if vertex_lp_provider is not None else "not_used"),
        "conversion_provider": "not_used",
        "checker_budget": {"max_points": 64, "wall_ms": 5000},
        "control_optimizer": {"id": "csl.optimization.finite-action-stage-layered-graph", "version": "1.0.0"},
        "search_policy": "stage-layered-backward-viability",
        "limits": {"max_beam_width": 4, "max_graph_nodes": 32,
            "max_plans": 32, "max_points_per_stage": 128,
            "max_score_evaluations": 128, "max_generators_per_stage": 64},
    }


def bind_task_hash(query: dict) -> None:
    task_contract = {
        "schema": "csl.closed-loop.analytic-source-task/1",
        "task_id": query["task_id"],
        "source_model_id": query["source_model_id"],
        "predictor_model_id": query["predictor_model_id"],
        "predictor_stages": query["predictor_stages"],
        "action_profile_id": query["action_profile_id"],
        "actions": query["actions"],
        "original_horizon": query["original_horizon"],
        "dt": query["dt"],
        "state_bounds": query["state_bounds"],
        "stage_state_bounds": query["stage_state_bounds"],
        "terminal_objective": query["terminal_objective"],
        "running_cost": query["running_cost"],
    }
    query["task_sha256"] = hashlib.sha256(json.dumps(task_contract, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def execute(bridge: Path, query: dict) -> dict:
    bind_task_hash(query)
    result = subprocess.run([str(bridge)], input=json.dumps(query) + "\n", text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def enumerate_paths(query: dict) -> list[dict]:
    rows = []
    for actions in itertools.product(range(len(query["actions"])), repeat=2):
        states = [[0.0, 0.0]]
        running = 0.0
        for action_index in actions:
            u = query["actions"][action_index][0]
            running += 0.5 * u * u  # coefficient / original N = 1/2
            states.append([states[-1][0] + u, states[-1][1]])
        terminal = states[-1][0] ** 2 + states[-1][1] ** 2
        safe = all(all(lo <= x <= hi for x, (lo, hi) in zip(state, bounds))
                   for state, bounds in zip(states, query["stage_state_bounds"]))
        rows.append({"action_indices": list(actions), "states": states, "feasible": safe,
                     "running_cost": running, "terminal_cost": terminal, "total_cost": running + terminal})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bridge = args.bridge.resolve(strict=True)
    viable_request = request(middle_bound=[[1.0, 1.0], [0.0, 0.0]], controller="analytic-viability")
    viable_response = execute(bridge, viable_request)
    paths = enumerate_paths(viable_request)
    unconstrained_best = min(paths, key=lambda row: row["total_cost"])
    feasible_best = min((row for row in paths if row["feasible"]), key=lambda row: row["total_cost"])
    assert unconstrained_best["action_indices"] == [0, 0]
    assert feasible_best["action_indices"] == [1, 0]
    assert viable_response["status"] == "accepted"
    assert viable_response["control"] == [1.0]
    assert viable_response["selected_plan"]["controls"] == [[1.0], [0.0]]
    assert abs(viable_response["selected_plan"]["total_objective"] - feasible_best["total_cost"]) < 1e-12

    continuous_only_request = request(middle_bound=[[0.5, 0.5], [0.0, 0.0]],
                                      controller="analytic-continuous-only-refusal")
    continuous_only_response = execute(bridge, continuous_only_request)
    # The continuous hull [0,1] contains u=0.5 for the target x'=0.5, but that
    # value is absent from the authored catalogue {0,1}; the graph must reject.
    continuous_membership = 0.0 + 0.5 == 0.5 and 0.0 <= 0.5 <= 1.0
    discrete_witness = any(0.0 + action[0] == 0.5 for action in continuous_only_request["actions"])
    assert continuous_membership and not discrete_witness
    assert continuous_only_response["status"] == "unsupported"
    assert "control" not in continuous_only_response

    center_request = request(middle_bound=[[-1.0, 1.0], [0.0, 0.0]], controller="analytic-center-lineage")
    center_request["actions"] = [[-1.0], [0.0], [1.0]]
    center_request["stage_state_bounds"] = [[[0.0, 0.0], [0.0, 0.0]],
        [[-1.0, 1.0], [0.0, 0.0]], [[-1.0, 1.0], [0.0, 0.0]]]
    center_response = execute(bridge, center_request)
    center_paths = enumerate_paths(center_request)
    center_best = min((row for row in center_paths if row["feasible"]), key=lambda row: row["total_cost"])
    stage_one_nodes = [node for node in center_response["graph_receipt"]["nodes"]
        if node["absolute_stage"] == 1]
    center_node = next(node for node in stage_one_nodes if node["action_index"] == 1)
    assert center_response["status"] == "accepted" and center_response["control"] == [0.0]
    assert len(stage_one_nodes) == 3 and center_node["state"] == [0.0, 0.0]
    assert center_best["action_indices"] == [1, 1] and center_best["total_cost"] == 0.0

    provider_profiles = [
        ("lp-membership", "csl.geometry.affine-sum", "csl.hull.lp-membership", "1.0.0", "phase-one-bland"),
        ("lp-membership-phase-one-priority-tie", "csl.geometry.affine-sum", "csl.hull.lp-membership", "1.0.0", "phase-one-priority-tie"),
        ("lp-membership-highs", "csl.geometry.affine-sum", "csl.hull.lp-membership", "1.0.0", "csl.lp.highs"),
        ("basis-reuse", "csl.geometry.affine-sum", "csl.hull.phase-one-basis-bulk", "1.0.0", "phase-one-bland"),
        ("ordered-membership", "csl.geometry.affine-sum", "csl.hull.ordered-membership", "1.0.0", "phase-one-bland"),
        ("itis17-a43", "csl.geometry.affine-sum", "csl.hull.itis17.a43-certified-basis-reuse", "1.0.0", "phase-one-bland"),
        ("itis17-a43-paper-order", "csl.geometry.affine-sum", "csl.hull.itis17.a43-artificial-basis", "1.0.0", "phase-one-bland"),
        ("itis17-a43-largest-norm", "csl.geometry.affine-sum", "csl.hull.itis17.a43-largest-norm-tie", "1.0.0", "phase-one-bland"),
        ("itis17-a44", "csl.geometry.affine-sum", "csl.hull.itis17.a44-incremental-lp", "2.0.0", "phase-one-bland"),
        ("itis17-a44-paper-farthest", "csl.geometry.affine-sum", "csl.hull.itis17.a44-paper-farthest-incremental-lp", "1.0.0", "phase-one-bland"),
        ("grouped-membership", "csl.geometry.affine-sum", "csl.hull.grouped-membership", "1.0.0", "phase-one-bland"),
        ("recursive-split-merge", "csl.geometry.affine-sum", "csl.hull.recursive-split-merge", "1.0.0", "phase-one-bland"),
        ("source-quickhull", "csl.geometry.affine-sum.source-index", "csl.hull.source.quickhull-2d", "1.0.0", None),
        ("source-btulshor", "csl.geometry.affine-sum.source-index", "csl.hull.source.btulshor-kpabep", "1.0.0", None),
    ]
    provider_trials = {}
    for label, reachable_method, hull_method, hull_version, lp_method in provider_profiles:
        trial_request = request(middle_bound=[[1.0, 1.0], [0.0, 0.0]],
            controller=f"analytic-provider-{label}", reachable_method=reachable_method,
            hull_provider=hull_method, vertex_lp_provider=lp_method)
        # Each envelope sum now contains a real 2D square, an interior point,
        # and a duplicate coordinate (six actions, five distinct points). This
        # drives reducer/checker calls instead of singleton clouds only.
        trial_request["predictor_stages"] = [
            {"A": [[1.0, 0.0], [0.0, 1.0]], "B": [[1.0, 0.0], [0.0, 1.0]], "c": [0.0, 0.0]}
            for _ in range(2)]
        trial_request["actions"] = [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0],
            [0.0, 0.0], [0.0, 0.0]]
        trial_request["limits"]["max_beam_width"] = 16
        trial_request["limits"]["max_graph_nodes"] = 128
        trial_request["state_bounds"] = [[-2.0, 2.0], [-2.0, 2.0]]
        trial_request["stage_state_bounds"] = [[[0.0, 0.0], [0.0, 0.0]],
            [[-1.0, 1.0], [-1.0, 1.0]], [[0.0, 0.0], [0.0, 0.0]]]
        for stage in trial_request["running_cost"]["stages"]:
            term = stage["terms"][0]
            term["reference"] = [0.0, 0.0]
            term["scales"] = [1.0, 1.0]
            term["weights"] = [1.0, 1.0]
        trial_request["hull_provider"]["version"] = hull_version
        if lp_method == "csl.lp.highs":
            trial_request["vertex_lp_provider"]["version"] = "1.1.0+highs.1.11.0"
        trial_response = execute(bridge, trial_request)
        calls = trial_response.get("geometry_invocations", [])
        assert trial_response.get("geometry_selection", {}).get("reachable_set_method", {}).get("id") == reachable_method
        assert trial_response.get("geometry_selection", {}).get("terminal_optimizer_provider") == "not_used"
        if trial_response["status"] == "accepted":
            assert calls and all(call["outcome"] == "completed" for call in calls)
            assert len(calls) % 2 == 0
            assert all(call["input_ids"] and call["ideal_output_id"] for call in calls)
            if reachable_method.endswith("source-index"):
                assert all(any("source-index generated ordered cloud: digest=" in item and "; rows=" in item
                    for item in call["evidence_assumptions"]) for call in calls)
                assert all(any("checker invocation:" in item and "status=verified" in item
                    for item in call["evidence_assumptions"]) for call in calls)
                non_singleton_clouds = [item for call in calls for item in call["evidence_assumptions"]
                    if item.startswith("source-index generated ordered cloud:") and "points=6;" in item]
                assert non_singleton_clouds, f"{label} did not retain the five-action cloud manifest"
            else:
                assert all(any("selected hull reducer:" in item for item in call["evidence_assumptions"])
                    for call in calls)
                reducer_calls = [item for call in calls for item in call["evidence_assumptions"]
                    if item.startswith("HullReducerPort invocation:")]
                assert reducer_calls
                if lp_method == "phase-one-priority-tie":
                    assert all(any(status in item for status in ("status=complete", "status=incomplete"))
                        for item in reducer_calls)
                    assert any("status=incomplete" in item for item in reducer_calls), \
                        "priority-tie Phase-I fixture unexpectedly hid its incompatible/incomplete query path"
                    assert all(any("all generated candidates retained because the complete HullReducerPort reduction failed" in item
                        for item in call["evidence_assumptions"]) for call in calls if any(
                            "status=incomplete" in item for item in call["evidence_assumptions"]))
                else:
                    assert all("status=complete" in item for item in reducer_calls)
                lp_records = [item for call in calls for item in call["evidence_assumptions"]
                    if item.startswith("HullReducerPort child LPPort invocation:") or
                       item.startswith("vertex LP invocation record:")]
                assert lp_records and all("requested_provider=" in item and "actual_provider=" in item
                    for item in lp_records), f"{label} omitted actual LP-port invocation identities"
                assert any("status=completed" in item for item in lp_records), \
                    f"{label} reported LP work without a completed LP-port result"
                if lp_method == "csl.lp.highs":
                    assert any("actual_provider=csl.lp.highs@1.1.0+highs.1.11.0" in item and
                        "status=completed" in item for item in lp_records), \
                        "HiGHS selection did not produce an actual completed HiGHS LP invocation"
                elif lp_method == "phase-one-priority-tie":
                    assert any("actual_provider=phase-one-priority-tie@1" in item and
                        "status=completed" in item for item in lp_records), \
                        "priority-tie Phase-I selection did not produce a completed query on this cloud"
                if hull_method not in {"csl.hull.phase-one-basis-bulk",
                        "csl.hull.itis17.a43-certified-basis-reuse"}:
                    actual_lp_calls = sum(int(item.split("lp_calls=", 1)[1].split(";", 1)[0])
                        for item in reducer_calls if "lp_calls=" in item)
                    assert actual_lp_calls > 0, f"{label} did not perform an LP-backed hull reduction"
                else:
                    assert any("basis_solves=" in item and int(item.split("basis_solves=",1)[1].split(";",1)[0]) > 0
                        for call in calls for item in call["evidence_assumptions"]), \
                        f"{label} did not perform basis reuse"
        else:
            # Algorithm/checker refusal is retained verbatim with the exact source cloud when generated.
            assert calls, trial_response
            failed = [call for call in calls if call["outcome"] != "completed"]
            assert failed and all(call["diagnostics"] for call in failed)
        provider_trials[label] = {"request": trial_request, "response": trial_response,
            "geometry_invocation_count": len(calls),
            "completed_operation_count": sum(call["outcome"] == "completed" for call in calls),
            "failed_operation_count": sum(call["outcome"] != "completed" for call in calls),
            "reducer_statuses": sorted({item.split("status=",1)[1].split(";",1)[0]
                for call in calls for item in call["evidence_assumptions"]
                if item.startswith("HullReducerPort invocation:")}),
            "conservative_retention": any("all generated candidates retained because the complete HullReducerPort reduction failed"
                in item for call in calls for item in call["evidence_assumptions"])}

    capacity_failure_request = copy.deepcopy(provider_trials["source-quickhull"]["request"])
    capacity_failure_request["controller_id"] = "analytic-provider-checker-capacity-refusal"
    capacity_failure_request["request_id"] = "analytic-provider-checker-capacity-refusal"
    capacity_failure_request["checker_budget"]["max_points"] = 1
    capacity_failure_response = execute(bridge, capacity_failure_request)
    capacity_failure_calls = capacity_failure_response.get("geometry_invocations", [])
    assert capacity_failure_response["status"] == "unsupported"
    assert capacity_failure_response["geometry_selection"]["reachable_set_method"]["id"] == \
        "csl.geometry.affine-sum.source-index"
    assert len(capacity_failure_calls) == 2
    assert capacity_failure_calls[0]["outcome"] == "completed"
    assert capacity_failure_calls[1]["outcome"] == "unsupported"
    assert "capacity" in capacity_failure_calls[1]["diagnostics"]
    assert "manifest was not materialized" in capacity_failure_calls[1]["diagnostics"]

    fixed_plan_mpc_trials = {}
    for representation_index, representation_name in enumerate(
            ("exact-polytope", "box", "zonotope", "parallelotope", "ellipsoid")):
        mpc_request = request(middle_bound=[[1.0, 1.0], [0.0, 0.0]],
            controller=f"analytic-fixed-plan-mpc-{representation_name}")
        del mpc_request["search_policy"]
        mpc_request["state_bounds"] = [[-2.0, 3.0], [-1.0, 1.0]]
        mpc_request["stage_state_bounds"] = [
            [[-0.01, 0.01], [-0.01, 0.01]],
            [[0.99, 1.01], [-0.01, 0.01]],
            [[-0.01, 2.01], [-0.01, 0.01]],
        ]
        mpc_request["representation_index"] = representation_index
        mpc_request["representation_name"] = representation_name
        mpc_response = execute(bridge, mpc_request)
        assert mpc_response["status"] == "accepted", mpc_response
        assert mpc_response["control"] == [1.0]
        assert mpc_response["policy_id"].endswith("/receding-fixed-plan-mpc/1")
        assert mpc_response["selector"]["search_coverage"] in {"complete", "incomplete"}
        assert mpc_response["selected_plan"]["controls"] == [[1.0], [0.0]]
        assert len(mpc_response["invocations"]) == 1
        assert mpc_response["invocations"][0]["module_id"] == \
            "csl::optimization::finite_action_nominal_profile"
        fixed_plan_mpc_trials[representation_name] = {"request": mpc_request,
            "response": mpc_response,
            "interpretation": "selected-profile fixed-plan MPC; no backward reachable-set synthesis"}

    record = {"schema": "csl.closed-loop.analytic-backward-graph-probe/1",
        "bridge": str(bridge), "viability_case": {"request": viable_request, "response": viable_response,
            "independent_histories": paths, "unconstrained_best": unconstrained_best,
            "best_feasible_history": feasible_best,
            "backward_viability_changed_first_action": True},
        "continuous_only_witness_case": {"request": continuous_only_request,
            "response": continuous_only_response, "continuous_parent_to_target_witness": continuous_membership,
            "authored_discrete_edge_witness": discrete_witness,
            "result": "rejected without fabricating a finite action"},
        "center_lineage_case": {"request": center_request, "response": center_response,
            "independent_histories": center_paths, "best_feasible_history": center_best,
            "interior_stage_node_retained": center_node,
            "interpretation": "the state produced by the authored center action is interior to the two endpoint states but remains a distinct witnessed node; the graph does not hull-deduplicate or splice its lineage"},
        "geometry_provider_trials": provider_trials,
        "fixed_plan_mpc_trials": fixed_plan_mpc_trials,
        "checker_capacity_refusal": {"request": capacity_failure_request,
            "response": capacity_failure_response,
            "failure_semantics": "the independently selected checker rejects before an oversized generated cloud is materialized; the refusal and actual source-index provider invocation remain recorded, and no cloud digest is claimed"},
        "optimizer_selection": {"control_selector": {
                "requested_method": viable_request["control_optimizer"],
                "actual_method": "csl.optimization.finite-action-stage-layered-graph@1.0.0",
                "provider": "public-function",
                "operation": "stage-layered backward Bellman selection"},
            "terminal_optimizer_provider": "not_used",
            "terminal_value_method": "direct evaluation of the authored terminal objective",
            "independent_of_geometry_provider": True}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"viability_selected_action": viable_response["control"],
        "independent_best_feasible": feasible_best["action_indices"],
        "unconstrained_best": unconstrained_best["action_indices"],
        "continuous_only_status": continuous_only_response["status"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()

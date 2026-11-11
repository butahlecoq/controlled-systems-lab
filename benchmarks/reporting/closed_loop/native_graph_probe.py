"""Executable analytic check for the native finite-action backward graph."""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from pathlib import Path


def request(*, middle_bound: list[list[float]], controller: str) -> dict:
    stages = [{"A": [[1.0, 0.0], [0.0, 1.0]], "B": [[1.0], [0.0]], "c": [0.0, 0.0]} for _ in range(2)]
    bounds = [[[0.0, 0.0], [0.0, 0.0]], middle_bound, [[0.0, 2.0], [0.0, 0.0]]]
    return {
        "schema": "csl.closed-loop.native-policy-query/1", "task_id": "analytic-2d-graph",
        "task_sha256": "a" * 64, "source_model_id": "analytic-2d/1", "controller_id": controller,
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
        "search_policy": "stage-layered-backward-viability",
        "limits": {"max_beam_width": 4, "max_graph_nodes": 32},
    }


def execute(bridge: Path, query: dict) -> dict:
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
            "interpretation": "the state produced by the authored center action is interior to the two endpoint states but remains a distinct witnessed node; the graph does not hull-deduplicate or splice its lineage"}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"viability_selected_action": viable_response["control"],
        "independent_best_feasible": feasible_best["action_indices"],
        "unconstrained_best": unconstrained_best["action_indices"],
        "continuous_only_status": continuous_only_response["status"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()

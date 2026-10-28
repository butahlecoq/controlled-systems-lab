#!/usr/bin/env python3
"""Independently check the finite causal minimax report fixtures."""

from __future__ import annotations

import json
import importlib.util
from fractions import Fraction
from functools import lru_cache
from itertools import product
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    completed = subprocess.run([sys.argv[1], "--smoke"], check=True,
                               capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["schema"] == "csl.mpc05-causal-tree-pilot/1"
    module_path = Path(__file__).with_name("reference.py")
    spec = importlib.util.spec_from_file_location("mpc05_reference", module_path)
    reference = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(reference)
    figure = reference.verify_result(result)
    geometry_source = figure["reachability_geometry_source"]
    assert geometry_source["backward_layer_counts"] == [1, 3, 9, 23]
    assert geometry_source["forward_backward_intersection_counts"] == [1, 3, 9, 23]
    assert figure["players"][0]["x_coordinate"] == "x1"
    assert figure["players"][0]["y_coordinate"] == "x2"
    assert figure["players"][1]["x_coordinate"] == "x3"
    assert figure["players"][1]["y_coordinate"] == "x4"
    with tempfile.TemporaryDirectory(prefix="mpc05-render-") as temporary:
        result_path = Path(temporary) / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        output = Path(temporary) / "rendered"
        reference.render(result_path, output)
        assert (output / "projections.svg").is_file()
        page = (output / "index.html").read_text(encoding="utf-8")
        assert "(x1,x2)" in page and "(x3,x4)" in page
        assert "forward/backward intersections" in page

    strict = result["strict_gap"]
    assert strict["fixed_plan_value"] == 2.0
    assert strict["bellman_value"] == 1.0
    assert strict["causal_policy_value"] == 1.0
    assert strict["tree"]["status"] == "optimal"
    assert strict["tree"]["global_bound"] == 1.0
    assert strict["tree"]["replayed_worst_cost"] == 1.0
    assert strict["tree"]["decision_occurrences"] == 7
    assert strict["tree"]["leaf_occurrences"] == 12

    merged = result["merged_state"]["tree"]
    assert merged["status"] == "optimal"
    assert merged["nonanticipativity_equalities"] == 2
    assert merged["leaf_occurrences"] == 4
    assert merged["objective"] == merged["replayed_worst_cost"] == 0.0

    lookahead = result["current_disturbance_lookahead"]
    assert lookahead["bellman_feasible"] is False
    assert lookahead["tree"]["status"] == "infeasible"

    two_points = result["two_points"]
    assert two_points["source_commit"] == "f4d76c60f4003f50954174e96eafd8e514bd5441"
    assert two_points["source_blob"] == "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"
    assert two_points["coordinates"] == "(x1,x2,x3,x4)=(position_1,velocity_1,position_2,velocity_2)"
    assert two_points["layer_state_counts"] == [1, 9, 81, 345]
    assert two_points["causal_tree"]["status"] == "optimal"
    assert two_points["causal_tree"]["decision_occurrences"] == 91
    assert two_points["causal_tree"]["leaf_occurrences"] == 729

    actions = (-1, 0, 1)
    disturbances = (-1, 0, 1)
    scale = 2000

    def step(state: tuple[int, ...], action: int, disturbance: int) -> tuple[int, ...]:
        p1, v1, p2, v2 = state
        assert v1 % 100 == 0 and v2 % 10 == 0
        return (p1 + v1 // 100 + 450 * action, 5000 * action,
                p2 + v2 // 10 + 9 * disturbance, v2 + 200 * disturbance)

    layers = [[(9000, 0, 0, 0)]]
    for _ in range(3):
        layers.append(sorted({step(state, action, disturbance)
                              for state in layers[-1]
                              for action in actions
                              for disturbance in disturbances}))
    assert two_points["layer_states_lattice_scale_2000"] == [
        [list(state) for state in layer] for layer in layers]

    def terminal_cost(state: tuple[int, ...]) -> Fraction:
        return Fraction((state[0] - state[2]) ** 2, scale ** 2)

    fixed_values = []
    for plan in product(actions, repeat=3):
        history_costs = []
        for disturbance_history in product(disturbances, repeat=3):
            state = layers[0][0]
            for action, disturbance in zip(plan, disturbance_history):
                state = step(state, action, disturbance)
            history_costs.append(terminal_cost(state))
        fixed_values.append(max(history_costs))
    fixed_value = min(fixed_values)

    @lru_cache(None)
    def causal_value(stage: int, state: tuple[int, ...]) -> Fraction:
        if stage == 3:
            return terminal_cost(state)
        return min(max(causal_value(stage + 1, step(state, action, disturbance))
                       for disturbance in disturbances) for action in actions)

    causal_value_exact = causal_value(0, layers[0][0])
    assert fixed_value == causal_value_exact == Fraction(58_323_769, 4_000_000)
    assert abs(two_points["open_loop_fixed_plan_value"] - float(fixed_value)) < 1e-12
    assert abs(two_points["causal_bellman_value"] - float(causal_value_exact)) < 1e-12
    assert abs(two_points["causal_tree"]["objective"] - float(causal_value_exact)) < 1e-8
    assert abs(two_points["causal_tree"]["global_bound"] - float(causal_value_exact)) < 1e-8
    assert abs(two_points["causal_tree"]["replayed_worst_cost"] - float(causal_value_exact)) < 1e-8

    saved_policy = two_points["causal_tree"]["policy"]
    assert [len(row) for row in saved_policy] == [1, 9, 81]

    @lru_cache(None)
    def saved_policy_value(stage: int, state: tuple[int, ...]) -> Fraction:
        if stage == 3:
            return terminal_cost(state)
        state_id = layers[stage].index(state)
        action = actions[saved_policy[stage][state_id]]
        return max(saved_policy_value(stage + 1, step(state, action, disturbance))
                   for disturbance in disturbances)

    assert saved_policy_value(0, layers[0][0]) == causal_value_exact
    print("MPC-05 finite causal fixtures independently checked")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_smoke.py REPORT_EXECUTABLE")
    main()

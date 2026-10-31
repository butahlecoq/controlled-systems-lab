#!/usr/bin/env python3
"""Independent exact finite-game and box-inclusion checks for EXP-824."""
from __future__ import annotations

from fractions import Fraction
from functools import reduce
from itertools import product
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mpc05"))
import reference as two_points_reference

SCALE = two_points_reference.SCALE
ACTION_CODES = two_points_reference.ACTION_CODES
DISTURBANCES = two_points_reference.DISTURBANCES


def close(left: float, right: float, tol: float = 2e-10) -> bool:
    return abs(left - right) <= tol * max(1.0, abs(left), abs(right))


def main(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != "csl.issue824-two-points-box-minimax/2":
        raise ValueError("unexpected EXP-824 report schema")
    if result.get("environment") != "TwoPointsOnParallelLines":
        raise ValueError("report must identify the source environment")
    layers, _, _, exact_value = two_points_reference.reference()
    box = result["box_method"]
    selected_indices = box["selected_action_indices"]
    if len(selected_indices) != 3 or any(index not in range(3) for index in selected_indices):
        raise ValueError("selected fixed plan is not a three-stage finite action plan")
    controls = [ACTION_CODES[index] for index in selected_indices]
    if box["selected_controls"] != [2.5 * action for action in controls]:
        raise ValueError("selected control values do not match the finite catalogue indices")
    if len(box["stages"]) != 4 or len(box["all_plan_scores"]) != 27:
        raise ValueError("stage trace or exhaustive control-plan score table is incomplete")

    exact_stages: list[set[tuple[int, ...]]] = [{layers[0][0]}]
    for stage, action in enumerate(controls):
        next_layer = {two_points_reference.step(state, action, disturbance)
                      for state in exact_stages[-1] for disturbance in DISTURBANCES}
        exact_stages.append(next_layer)
    for stage, states in enumerate(exact_stages):
        bounds = box["stages"][stage]
        lower, upper = bounds["lower"], bounds["upper"]
        if len(lower) != 4 or len(upper) != 4:
            raise ValueError("each stage box must preserve the full four-state coordinates")
        for state in states:
            point = [coordinate / SCALE for coordinate in state]
            if any(lower[j] > point[j] or upper[j] < point[j] for j in range(4)):
                raise ValueError(f"stage {stage} box misses an exact finite-game state")

    zonotope = result["zonotope_method"]
    if zonotope.get("relation") != "outer" or len(zonotope.get("stages", [])) != 4:
        raise ValueError("zonotope trace must identify an outer relation at every stage")
    generator_limit = zonotope.get("max_generators_per_stage")
    if not isinstance(generator_limit, int) or generator_limit < 0:
        raise ValueError("zonotope generator budget is missing or invalid")
    for stage, states in enumerate(exact_stages):
        current = zonotope["stages"][stage]
        center = current["center"]
        matrix = current["generators"]
        factors = current["factors"]
        if (len(center) != 4 or matrix.get("rows") != 4 or
                matrix.get("cols") != len(factors) or
                len(matrix.get("values", [])) != 4 * len(factors)):
            raise ValueError(f"stage {stage} zonotope dimensions are inconsistent")
        if len(factors) > generator_limit:
            raise ValueError(f"stage {stage} exceeds its declared generator budget")
        exact_center = [Fraction.from_float(value) for value in center]
        exact_generators = [Fraction.from_float(value) for value in matrix["values"]]
        for state in states:
            for coordinate in range(4):
                radius = sum((abs(exact_generators[coordinate * len(factors) + column])
                              for column in range(len(factors))), Fraction(0))
                lower = exact_center[coordinate] - radius
                upper = exact_center[coordinate] + radius
                point = Fraction(state[coordinate], SCALE)
                if point < lower or point > upper:
                    raise ValueError(
                        f"stage {stage} zonotope coordinate bounds miss an exact state coordinate")

    disturbance_indices = box["worst_disturbance_indices"]
    disturbance_values = box["worst_disturbances"]
    if len(disturbance_indices) != 3 or len(disturbance_values) != 3:
        raise ValueError("worst-case witness does not include every disturbance stage")
    if any(index not in range(3) for index in disturbance_indices):
        raise ValueError("worst-case disturbance index is outside the declared catalogue")
    expected_disturbances = [DISTURBANCES[index] for index in disturbance_indices]
    if disturbance_values != [[float(value)] for value in expected_disturbances]:
        raise ValueError("witness disturbance values differ from its catalogue indices")
    state = (9000, 0, 0, 0)
    path = [state]
    for action, disturbance in zip(controls, expected_disturbances):
        state = two_points_reference.step(state, action, disturbance)
        path.append(state)
    expected_path = [[coordinate / SCALE for coordinate in item] for item in path]
    if len(box["worst_case_path"]) != 4 or any(len(row) != 4 for row in box["worst_case_path"]) or any(
            not close(actual, expected)
            for actual_row, expected_row in zip(box["worst_case_path"], expected_path)
            for actual, expected in zip(actual_row, expected_row)):
        raise ValueError("stored state path does not replay the selected controls and disturbances")
    replay_value = Fraction((state[0] - state[2]) ** 2, SCALE**2)
    if not close(box["full_catalogue_replay_value"], float(replay_value)):
        raise ValueError("stored replay cost differs from the exact terminal objective")
    true_selected_worst = Fraction(-1)
    for history in product(DISTURBANCES, repeat=3):
        terminal = reduce(lambda current, pair: two_points_reference.step(current, pair[0], pair[1]),
                          zip(controls, history), (9000, 0, 0, 0))
        true_selected_worst = max(true_selected_worst,
                                  Fraction((terminal[0] - terminal[2]) ** 2, SCALE**2))
    if replay_value != true_selected_worst:
        raise ValueError("stored witness is not worst case for the selected fixed plan")

    exact = result["exact_reference"]
    if not close(exact["finite_minimax_value"], float(exact_value)):
        raise ValueError("exact C++ baseline differs from independent rational finite minimax")
    optimal = [ACTION_CODES[index] for index in exact["selected_action_indices"]]
    exact_worst = Fraction(-1)
    exact_path: list[tuple[int, ...]] = []
    for history in product(DISTURBANCES, repeat=3):
        state = (9000, 0, 0, 0)
        path = [state]
        for action, disturbance in zip(optimal, history):
            state = two_points_reference.step(state, action, disturbance)
            path.append(state)
        score = Fraction((state[0] - state[2]) ** 2, SCALE**2)
        if score > exact_worst:
            exact_worst, exact_path = score, path
    if exact_worst != exact_value:
        raise ValueError("selected exact baseline plan does not attain the independent optimum")
    scored_plans = {tuple(row["action_indices"]): row["terminal_box_maximum"]
                    for row in box["all_plan_scores"]}
    expected_plans = set(product(range(3), repeat=3))
    if set(scored_plans) != expected_plans:
        raise ValueError("box score table duplicates or omits action plans")
    best_box = min(scored_plans.values())
    if (not close(best_box, box["terminal_box_maximum"]) or
            not close(scored_plans[tuple(selected_indices)], box["terminal_box_maximum"])):
        raise ValueError("selected terminal box score is not minimal over the recorded plans")
    if box["terminal_box_maximum"] + 1e-10 < box["full_catalogue_replay_value"]:
        raise ValueError("terminal box score is below its replayed feasible-plan cost")
    if float(replay_value) + 1e-10 < float(exact_value):
        raise ValueError("selected feasible plan cannot improve on the exhaustive exact optimum")

    return {
        "schema": "csl.issue824-two-points-box-check/2",
        "status": "verified",
        "scope": "stored binary64 discrete model coefficients and the declared finite catalogs",
        "independent_source": "scripts/reports/mpc05/reference.py exact integer transitions and rational objective",
        "exact_finite_minimax_value": float(exact_value),
        "selected_plan_replay_value": float(replay_value),
        "selected_plan_action_codes": controls,
        "selected_plan_disturbance_codes": expected_disturbances,
        "selected_plan_state_path": expected_path,
        "exact_reference_state_path": [[v / SCALE for v in item] for item in exact_path],
        "stage_state_counts": [len(states) for states in exact_stages],
        "stage_box_inclusion": "every exact finite-catalog state checked at every stage",
        "stage_zonotope_coordinate_bounds":
            "every exact finite-catalog state coordinate checked against exact dyadic center +/- sum(abs(generators)); not a full zonotope membership proof",
        "objective_bound_status": "diagnostic numerical maximum on outer boxes; not a validated bound",
    }


if __name__ == "__main__":
    try:
        checked = main(Path(sys.argv[1]))
        print(json.dumps(checked, indent=2, sort_keys=True))
    except (IndexError, KeyError, ValueError, TypeError) as error:
        raise SystemExit(f"EXP-824 check failed: {error}") from error

#!/usr/bin/env python3
"""Rebuild the finite-game reachable nodes and exact 2D convex-hull inputs."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


SCALE = 2_000
CONTROLS = (-1, 0, 1)
DISTURBANCES = (-1, 0, 1)
INITIAL = (9_000, 0, 0, 0)
PROJECTIONS = ((0, 1), (2, 3))
LABELS = (("position 1", "velocity 1"), ("position 2", "velocity 2"))


def advance(state: tuple[int, int, int, int], control: int, disturbance: int):
    p1, v1, p2, v2 = state
    if v1 % 100 or v2 % 10:
        raise ValueError("source recurrence left the exact integer lattice")
    return (
        p1 + v1 // 100 + 450 * control,
        5_000 * control,
        p2 + v2 // 10 + 9 * disturbance,
        v2 + 200 * disturbance,
    )


def stored_layer(layer):
    states = set()
    for state in layer:
        scaled = tuple(round(coordinate * SCALE) for coordinate in state)
        if any(scaled[i] / SCALE != state[i] for i in range(4)):
            raise ValueError("saved state is not on the exact source lattice")
        states.add(scaled)
    return states


def cross(origin, left, right):
    return ((left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0]))


def convex_hull(points):
    ordered = sorted(set(points))
    if len(ordered) <= 1:
        return ordered
    lower = []
    for point in ordered:
        while len(lower) > 1 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(ordered):
        while len(upper) > 1 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def in_convex_hull(point, hull):
    if len(hull) == 1:
        return point == hull[0]
    if len(hull) == 2:
        return (cross(hull[0], hull[1], point) == 0
                and min(hull[0][0], hull[1][0]) <= point[0] <= max(hull[0][0], hull[1][0])
                and min(hull[0][1], hull[1][1]) <= point[1] <= max(hull[0][1], hull[1][1]))
    return all(cross(hull[i], hull[(i + 1) % len(hull)], point) >= 0
               for i in range(len(hull)))


def projected_zonotope(stage, coordinates):
    center = INITIAL
    for _ in range(stage):
        center = advance(center, 0, 0)
    center_2d = tuple(center[i] for i in coordinates)
    columns = []
    for impulse_stage in range(stage):
        for kind in ("control", "disturbance"):
            state = (0, 0, 0, 0)
            for step in range(stage):
                state = advance(
                    state,
                    int(kind == "control" and step == impulse_stage),
                    int(kind == "disturbance" and step == impulse_stage),
                )
            columns.append(tuple(state[i] for i in coordinates))
    corners = {
        tuple(center_2d[coordinate] + sum(
            signs[column] * columns[column][coordinate]
            for column in range(len(columns))) for coordinate in range(2))
        for signs in itertools.product((-1, 1), repeat=len(columns))
    } if columns else {center_2d}
    return center_2d, columns, corners


def component_outcomes(stage, component):
    outcomes = []
    for sequence in itertools.product(CONTROLS, repeat=stage):
        state = INITIAL
        for code in sequence:
            state = advance(state, code if component == "control" else 0,
                            code if component == "disturbance" else 0)
        outcomes.append({"codes": list(sequence), "terminal_state_scaled": list(state)})
    return outcomes


def finite_minimax(control_outcomes, disturbance_outcomes, scale):
    scored = []
    for control in control_outcomes:
        control_position = control["terminal_state_scaled"][0]
        worst = max((control_position - disturbance["terminal_state_scaled"][2]) ** 2
                    for disturbance in disturbance_outcomes)
        scored.append((worst, control["codes"]))
    value = min(value for value, _ in scored)
    minimizing_codes = [list(codes) for score, codes in scored if score == value]
    selected_control = minimizing_codes[0]
    control_position = next(item["terminal_state_scaled"][0] for item in control_outcomes
                            if item["codes"] == selected_control)
    worst_disturbances = [item for item in disturbance_outcomes
                          if (control_position - item["terminal_state_scaled"][2]) ** 2 == value]
    selected_disturbance = worst_disturbances[0]["codes"]
    path = [list(INITIAL)]
    state = INITIAL
    for control, disturbance in zip(selected_control, selected_disturbance):
        state = advance(state, control, disturbance)
        path.append(list(state))
    return {
        "objective": "minimum over open-loop controls of worst terminal squared position gap",
        "information_pattern": "exists full control sequence, for all full disturbance sequences",
        "value_numerator": value,
        "value_denominator": scale * scale,
        "value": value / (scale * scale),
        "minimizing_control_sequences_codes": minimizing_codes,
        "achievable_policy_witness": {
            "control_sequence_codes": selected_control,
            "control_sequence": [2.5 * code for code in selected_control],
            "worst_disturbance_sequences_codes": [item["codes"] for item in worst_disturbances],
            "selected_worst_disturbance_sequence_codes": selected_disturbance,
            "selected_worst_disturbance_sequence": [float(code) for code in selected_disturbance],
            "state_path_scaled": path,
            "terminal_gap_numerator": path[-1][0] - path[-1][2],
            "terminal_gap_denominator": scale,
            "objective_value_numerator": value,
            "objective_value_denominator": scale * scale,
            "meaning": "realizable open-loop control with its worst finite-catalogue disturbance response",
        },
        "enumerated_control_sequences": len(control_outcomes),
        "enumerated_disturbance_sequences": len(disturbance_outcomes),
        "arithmetic": "exact integer arithmetic on scale-2000 states",
    }


def build_reference(figure_path: Path, result_path: Path):
    figure_bytes = figure_path.read_bytes()
    figure = json.loads(figure_bytes)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    stored_layers = [stored_layer(layer) for layer in figure["forward_layers"]]
    if stored_layers[0] != {INITIAL}:
        raise ValueError("saved initial layer differs from the pinned case")

    layers = [{INITIAL}]
    for stage in range(len(stored_layers) - 1):
        next_states = {
            advance(state, control, disturbance)
            for state in layers[stage]
            for control in CONTROLS
            for disturbance in DISTURBANCES
        }
        if next_states != stored_layers[stage + 1]:
            raise ValueError(f"saved forward layer {stage + 1} differs from exact replay")
        layers.append(next_states)

    control_outcomes = component_outcomes(len(layers) - 1, "control")
    disturbance_outcomes = component_outcomes(len(layers) - 1, "disturbance")
    minimax = finite_minimax(control_outcomes, disturbance_outcomes, SCALE)
    if float(minimax["value"]) != result["objective_value"]:
        raise ValueError("independent finite minimax replay differs from the saved objective")

    document = {
        "schema": "csl.exp03-two-points-reference/1",
        "case_id": "env717-two-points-three-stage-finite-game",
        "environment_report": "env717-two-points-feedback-v1",
        "upstream_repository_commit": result["source_repository_commit"],
        "upstream_source_blob": result["source_file_blob"],
        "source_commit": result["source_commit"],
        "finite_game": {
            "horizon_steps": len(layers) - 1,
            "source_step_seconds": 0.1,
            "control_codes": list(CONTROLS),
            "disturbance_codes": list(DISTURBANCES),
            "state_scale": SCALE,
            "state_order": ["position_1", "velocity_1", "position_2", "velocity_2"],
            "set_meaning": (
                "the exact finite-game nodes are replayed on a scale-2000 integer lattice; "
                "coordinates are converted to binary64 while constructing the native 4D V input "
                "before the 2D projection query, and method comparison uses the convex hull of "
                "the stored binary64 projected nodes; discrete nodes and exact rational "
                "coordinates remain separately available"
            ),
            "control_terminal_outcomes": control_outcomes,
            "disturbance_terminal_outcomes": disturbance_outcomes,
            "finite_minimax_reference": minimax,
        },
        "projection_pairs": [list(pair) for pair in PROJECTIONS],
        "projection_labels": [list(labels) for labels in LABELS],
        "source_figure_data_sha256": hashlib.sha256(figure_bytes).hexdigest(),
        "layers": [
            {
                "stage": stage,
                "time_seconds": stage / 10,
                "finite_state_count": len(states),
                "finite_states_scaled": [list(state) for state in sorted(states)],
                "projected_unique_point_counts": [
                    len({tuple(state[i] for i in pair) for state in states})
                    for pair in PROJECTIONS
                ],
                "projected_vertices": [
                    [
                        [coordinate / SCALE for coordinate in projected]
                        for projected in sorted(
                            {tuple(state[i] for i in pair) for state in states}
                        )
                    ]
                    for pair in PROJECTIONS
                ],
                "projected_vertices_scaled": [
                    [
                        list(projected)
                        for projected in sorted(
                            {tuple(state[i] for i in pair) for state in states}
                        )
                    ]
                    for pair in PROJECTIONS
                ],
                "projected_zonotopes_scaled": [
                    {
                        "center": list(center),
                        "generator_columns": [list(column) for column in columns],
                        "corner_count": len(corners),
                        "corners": [list(point) for point in sorted(corners)],
                        "equals_projected_convex_hull": (
                            all(point in {tuple(state[i] for i in pair) for state in states}
                                for point in corners)
                            and all(in_convex_hull(
                                point,
                                convex_hull(corners),
                            ) for point in {
                                tuple(state[i] for i in pair) for state in states
                            })
                        ),
                    }
                    for pair in PROJECTIONS
                    for center, columns, corners in [projected_zonotope(stage, pair)]
                ],
            }
            for stage, states in enumerate(layers)
        ],
    }
    for layer in document["layers"]:
        for projection in layer["projected_zonotopes_scaled"]:
            if not projection["equals_projected_convex_hull"]:
                raise ValueError(
                    f"stage {layer['stage']} projected finite-state hull is not the derived zonotope"
                )
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure-data", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_reference(args.figure_data, args.result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": document["schema"],
        "case_id": document["case_id"],
        "source_figure_data_sha256": document["source_figure_data_sha256"],
        "layers": [
            {
                "stage": layer["stage"],
                "finite_state_count": layer["finite_state_count"],
                "projected_unique_point_counts": layer["projected_unique_point_counts"],
            }
            for layer in document["layers"]
        ],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()

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

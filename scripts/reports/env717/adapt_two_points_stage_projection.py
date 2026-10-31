#!/usr/bin/env python3
"""Adapt the saved TwoPoints feedback figure data to the shared stage batch.

This is deliberately a saved-data adapter.  It does not rerun the game, infer
continuous predecessor sets, or turn finite winning nodes into a continuous
boundary.  The per-control-prefix forward hulls and the finite
winning/intersection nodes remain
separate geometry components in the common offline renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAIRS = [[0, 1], [2, 3]]
COORDINATES = [
    {"id": "x0", "name": "position_1", "unit": "state units"},
    {"id": "x1", "name": "velocity_1", "unit": "state units / s"},
    {"id": "x2", "name": "position_2", "unit": "state units"},
    {"id": "x3", "name": "velocity_2", "unit": "state units / s"},
]


def _hull(points: list[list[float]]) -> list[list[float]]:
    """Return a deterministic 2-D convex hull of saved forward vertices."""
    unique = sorted({(float(point[0]), float(point[1])) for point in points})
    if len(unique) <= 2:
        return [[x, y] for x, y in unique]

    def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return [[x, y] for x, y in lower[:-1] + upper[:-1]]


def _kind(points: list[list[float]]) -> tuple[str, list[list[float]]]:
    hull = _hull(points)
    if len(hull) == 1:
        return "point", hull
    if len(hull) == 2:
        return "segment", hull
    return "polygon", hull


def _point_components(prefix: str, points: list[list[float]], pair: list[int], role: str) -> list[dict]:
    result = []
    for index, state in enumerate(points):
        result.append({
            "component_id": f"{prefix}/state/{index}",
            "kind": "point",
            "role": role,
            "interpretation": "conv_vertices_plus_cone_rays",
            "vertices": [[float(state[pair[0]]), float(state[pair[1]])]],
            "rays": [],
        })
    return result


def build_batch(source_path: Path) -> tuple[dict, dict[str, str]]:
    raw = source_path.read_bytes()
    source = json.loads(raw)
    required = {"forward_layers", "forward_groups", "feedback_backward_layers",
                "feedback_trajectory", "trajectory"}
    missing = required.difference(source)
    if missing:
        raise ValueError(f"saved TwoPoints figure data is missing {sorted(missing)}")
    if len(source["forward_layers"]) != len(source["feedback_backward_layers"]):
        raise ValueError("forward and backward layers must have the same stage count")
    if len(source["forward_layers"]) != len(source["forward_groups"]):
        raise ValueError("forward layers and control-prefix groups must have the same stage count")
    source_hash = hashlib.sha256(raw).hexdigest()
    run_id = "env717-two-points-feedback-v1"
    request_id = "env717-two-points-feedback-stage-projection"
    problem_id = "env717-two-points-parallel-lines"
    route_id = "env717.two_points.feedback.saved-stage-projection"
    records = []
    for stage, (forward, groups, backward) in enumerate(
        zip(source["forward_layers"], source["forward_groups"],
            source["feedback_backward_layers"])
    ):
        forward_states = {tuple(float(value) for value in state) for state in forward}
        grouped_states = set()
        for group in groups:
            if len(group.get("control_prefix", [])) != stage:
                raise ValueError(f"control-prefix length does not match stage R{stage}")
            grouped_states.update(tuple(float(value) for value in state)
                                  for state in group.get("vertices", []))
        if grouped_states != forward_states:
            raise ValueError(f"control-prefix groups do not reconstruct forward layer R{stage}")
        backward_states = {tuple(float(value) for value in state) for state in backward}
        intersection = sorted(forward_states & backward_states)
        for pair_index, pair in enumerate(PAIRS):
            components = []
            for group_index, group in enumerate(groups):
                group_states = group["vertices"]
                forward_points = [[state[pair[0]], state[pair[1]]] for state in group_states]
                kind, vertices = _kind(forward_points)
                components.append({
                    "component_id": f"forward/pair/{pair_index}/stage/{stage}/prefix/{group_index}",
                    "branch_id": "control-prefix/" + "/".join(
                        f"{float(value):g}" for value in group["control_prefix"]
                    ) if group["control_prefix"] else "control-prefix/initial",
                    "kind": kind,
                    "role": "forward",
                    "interpretation": "conv_vertices_plus_cone_rays",
                    "vertices": vertices,
                    "rays": [],
                })
            components.extend(_point_components(
                f"backward/pair/{pair_index}/stage/{stage}", sorted(backward_states), pair,
                "backward_winning"))
            components.extend(_point_components(
                f"intersection/pair/{pair_index}/stage/{stage}", intersection, pair, "intersection"))
            set_ids = [f"env717-two-points-forward-R{stage}",
                       f"env717-two-points-backward-R{stage}",
                       f"env717-two-points-intersection-R{stage}"]
            records.append({
                "stage": stage,
                "physical_time": stage / 10.0,
                "pair_index": pair_index,
                "source_assurance": "numerical",
                "source_set_ids": set_ids,
                "outcome": {
                    "status": "success",
                    "relation": "equivalent",
                    "assurance": "numerical",
                    "provider": {"id": "csl.env717.saved-stage-adapter", "version": "1.0.0"},
                    "evidence": [{
                        "request_id": f"{request_id}/pair/{pair_index}/stage/{stage}",
                        "ideal_output_id": f"projection/pair/{pair_index}/stage/{stage}",
                        "scope": "set_relation",
                        "input_set_ids": set_ids,
                        "support": {"kind": "saved-source-record", "reference": "figure-data.json"},
                        "assumptions": [
                            "forward vertices are the saved finite-action disturbance-reachable polytope vertices",
                            "backward and intersection components are finite graph nodes, not continuous boundaries",
                            "the common renderer consumes saved data only",
                        ],
                    }],
                    "components": components,
                },
            })

    trajectories = []
    for name, trajectory in (("open-loop minimax", source["trajectory"]),
                             ("causal finite-feedback", source["feedback_trajectory"])):
        for pair in PAIRS:
            trajectories.append({
                "kind": "trajectory",
                "source_run_id": run_id,
                "coordinate_ids": [f"x{pair[0]}", f"x{pair[1]}"],
                "points": [[float(state[pair[0]]), float(state[pair[1]])] for state in trajectory],
                "evidence": f"{name} from saved source-bound figure data; separate from set geometry",
            })

    batch = {
        "schema": "csl.stage-projection-batch/1",
        "provenance": {"run_id": run_id, "record_schema": "csl.env717-two-points-figure-data/1",
                        "source_sha256": source_hash},
        "problem_id": problem_id,
        "request_id": request_id,
        "route_id": route_id,
        "coordinates": COORDINATES,
        "requested_pairs": PAIRS,
        "stage_axis": {"kind": "physical_time", "points": [i / 10.0 for i in range(len(records) // len(PAIRS))],
                        "unit": "s"},
        "relation": "equivalent",
        "assurance": "numerical",
        "records": records,
        "trajectory_series": trajectories,
    }
    identity = {"expected_run_id": run_id, "expected_problem_id": problem_id,
                "expected_request_id": request_id, "expected_route_id": route_id,
                "expected_record_schema": "csl.env717-two-points-figure-data/1",
                "expected_source_sha256": source_hash}
    return batch, identity


def main() -> None:
    from scripts.reports.stage_projection_data import dumps_stage_projection_batch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    batch, identity = build_batch(args.source.resolve(strict=True))
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(dumps_stage_projection_batch(batch, **identity))
    print(args.output.resolve())


if __name__ == "__main__":
    main()

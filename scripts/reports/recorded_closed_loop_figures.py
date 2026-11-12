"""Render source-bound closed-loop stage geometry without rerunning a solver."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from figure_style import STYLE_ID, configure_numeric_axis
from mathematical_notation import matrix_html


SCHEMA = "csl.closed-loop.figure-index/1"
SOURCE_COMMIT = "64560a03b2d4a04a56a94c86b3abf193bb63f54f"
@dataclass(frozen=True)
class Plane:
    case_id: str
    figure_id: str
    title: str
    task_id: str
    raw_indices: tuple[int, int]
    names: tuple[str, str]
    units: tuple[str, str]
    time_unit: str
    dt: float
    target: tuple[float, float] | None = None
    transform_description: str = "Physical state coordinates; no scaling applied."

    def project(self, state: list[float] | tuple[float, ...]) -> tuple[float, float]:
        if max(self.raw_indices) >= len(state):
            raise ValueError(f"state dimension does not support {self.figure_id} plane")
        return float(state[self.raw_indices[0]]), float(state[self.raw_indices[1]])


def replay_for_output_stage(replay: list[dict[str, Any]], output_stage: int, dt: float) -> list[dict[str, Any]]:
    """Show state 0 at the initial instant and state k with replay interval k-1 to k."""
    if output_stage < 0 or dt <= 0.0:
        return []
    tolerance = max(1.0, abs(output_stage * dt)) * 1e-10
    if output_stage == 0:
        return [row for row in replay if abs(float(row["time"])) <= tolerance]
    lower, upper = (output_stage - 1) * dt, output_stage * dt
    return [row for row in replay
            if lower - tolerance <= float(row["time"]) <= upper + tolerance]


def rows_for_output_stage(rows: list[dict[str, Any]], output_stage: int) -> list[dict[str, Any]]:
    return [row for row in rows if int(row.get("absolute_stage", -1)) == output_stage]


def output_stage_values(stage_count: int) -> range:
    """A capture with N updates has output states 0 through N, inclusive."""
    return range(max(0, stage_count) + 1)


def normalized_time(time: float, end_time: float) -> float:
    if end_time <= 0.0:
        return 0.0
    return min(1.0, max(0.0, float(time) / end_time))


def timeline_end(runs: list[dict[str, Any]]) -> float:
    times = [
        float(row["time"])
        for run in runs
        for series_name in ("clouds", "nodes", "planned_prediction", "plant_replay")
        for row in run.get(series_name, [])
        if "time" in row
    ]
    return max(times, default=0.0)


PLANES = {
    "syn-nl-lv-01": Plane(
        "syn-nl-lv-01", "lotka-populations", "Lotka population plane",
        "syn-nl-lv-01/continuous-receding/1", (0, 1),
        ("Prey population P", "Predator population R"),
        ("thousand individuals", "thousand individuals"), "day", 0.1,
        (100.0, 80.0),
    ),
    "earth-orbit": Plane(
        "earth-orbit", "earth-orbit", "Earth orbit phase plane",
        "env717-earth-orbit/continuous-receding/1", (0, 3),
        ("Radius r", "Angular rate ω"), ("km", "rad/s"), "s", 100.0,
        (6900.0, math.sqrt(6.67448478e-20 * 5.9726e24 / 6900.0**3)),
        "Raw physical state order [r, v, theta, omega]; no scaling applied.",
    ),
    "syn-nl-fuel-01": Plane(
        "syn-nl-fuel-01", "fuel-state", "Fuel control state planes",
        "syn-nl-fuel-01/continuous-receding/1", (2, 0),
        ("Oxidizer flow qₒₓ", "Oxidizer mass mₒₓ"), ("kg/s", "kg"), "s", 0.5,
        (1.5, 75.0),
        "Raw order [m_ox, m_f, q_ox, q_f]; requested oxidizer indices [2, 0] and fuel indices [3, 1]; raw scale [100, 30, 3, 1] is not reapplied to physical data.",
    ),
}

FUEL_FUEL_PLANE = Plane(
    "syn-nl-fuel-01", "fuel-fuel-flow", "Fuel flow and mass plane",
    "syn-nl-fuel-01/continuous-receding/1", (3, 1),
    ("Fuel flow q_f", "Fuel mass m_f"), ("kg/s", "kg"), "s", 0.5,
    (0.45, 23.0),
    "Raw order [m_ox, m_f, q_ox, q_f]; requested fuel indices [3, 1]; raw scale [100, 30, 3, 1] is not reapplied to physical data.",
)

FUEL_PLANES = (
    {"id": "oxidizer-flow-mass", "raw_indices": [2, 0], "names": ["q_ox", "m_ox"], "units": ["kg/s", "kg"]},
    {"id": "fuel-flow-mass", "raw_indices": [3, 1], "names": ["q_f", "m_f"], "units": ["kg/s", "kg"]},
)

ATTEMPTS = {
    "syn-nl-lv-01": (
        "syn-nl-lv-01-20261111T202218Z-4011d21f",
        "syn-nl-lv-01-20261111T202541Z-4f0b01f8",
        "syn-nl-lv-01-20261111T203317Z-ddc8d8e0",
        "syn-nl-lv-01-20261111T204110Z-af9710e5",
        "syn-nl-lv-01-20261111T204901Z-06fc9393",
    ),
    "earth-orbit": (
        "earth-orbit-20261111T194241Z-3c53f195",
        "earth-orbit-20261111T201301Z-8f6b272d",
        "earth-orbit-20261111T210302Z-56088e74",
        "earth-orbit-20261111T210944Z-89f7c607",
    ),
    "syn-nl-fuel-01": (
        "syn-nl-fuel-01-20261111T194953Z-681474d9",
        "syn-nl-fuel-01-20261111T201447Z-6c594012",
    ),
}

CONTROLLER_LABELS = {
    "native-exact-polytope-backward-graph/1": "Exact polytope graph policy",
    "native-box-mpc/1": "Box representation MPC",
    "native-zonotope-mpc/1": "Zonotope representation MPC",
    "native-parallelotope-mpc/1": "Parallelotope representation MPC",
    "native-ellipsoid-mpc/1": "Ellipsoid representation MPC",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON record {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _convex_hull(points: list[tuple[float, float]]) -> list[list[float]]:
    ordered = sorted(set((float(x), float(y)) for x, y in points))
    if len(ordered) <= 2:
        return [[x, y] for x, y in ordered]
    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return [[x, y] for x, y in lower[:-1] + upper[:-1]]


def _zonotope_polygon(center: list[float], generator_vectors: list[list[float]], indices: tuple[int, int]) -> list[list[float]]:
    segments: list[tuple[float, float]] = []
    for vector in generator_vectors:
        dx, dy = float(vector[indices[0]]), float(vector[indices[1]])
        if dy < 0.0 or (dy == 0.0 and dx < 0.0):
            dx, dy = -dx, -dy
        if math.hypot(dx, dy) > 0.0:
            segments.append((math.atan2(dy, dx), dx, dy))
    segments.sort()
    cx, cy = float(center[indices[0]]), float(center[indices[1]])
    start = (cx - sum(x for _, x, _ in segments), cy - sum(y for _, _, y in segments))
    points = [start]
    current = start
    for _, dx, dy in segments:
        current = (current[0] + 2.0 * dx, current[1] + 2.0 * dy)
        points.append(current)
    for _, dx, dy in segments:
        current = (current[0] - 2.0 * dx, current[1] - 2.0 * dy)
        points.append(current)
    return [[x, y] for x, y in points]


def project_shape(shape: dict[str, Any], indices: tuple[int, int]) -> list[list[float]] | None:
    """Project the serialized shape itself; never infer geometry from node flags."""
    kind = shape.get("representation")
    if kind == "box":
        lower, upper = shape.get("lower"), shape.get("upper")
        if not isinstance(lower, list) or not isinstance(upper, list):
            return None
        x0, x1 = float(lower[indices[0]]), float(upper[indices[0]])
        y0, y1 = float(lower[indices[1]]), float(upper[indices[1]])
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    if kind == "ellipsoid":
        center, radii = shape.get("center"), shape.get("radii")
        if not isinstance(center, list) or not isinstance(radii, list):
            return None
        return [[float(center[indices[0]]), float(center[indices[1]])],
                [float(radii[indices[0]]), float(radii[indices[1]])]]
    if kind == "zonotope":
        center, generators = shape.get("center"), shape.get("generators")
        if not isinstance(center, list) or not isinstance(generators, list):
            return None
        if len(generators) != len(center) or any(not isinstance(row, list) for row in generators):
            return None
        if generators and any(len(row) != len(generators[0]) for row in generators):
            return None
        # Serialized zonotope generators are a state-dimension by generator-count
        # matrix. Convert once at the boundary to explicit full-state vectors.
        return _zonotope_polygon(center, [list(column) for column in zip(*generators)], indices)
    if kind == "parallelotope":
        frame, lower, upper = shape.get("frame"), shape.get("lower"), shape.get("upper")
        if not isinstance(frame, list) or not isinstance(lower, list) or not isinstance(upper, list):
            return None
        matrix = frame
        dimension = len(lower)
        if len(matrix) != dimension or any(not isinstance(row, list) or len(row) != dimension for row in matrix):
            return None
        middle = [(float(a) + float(b)) / 2.0 for a, b in zip(lower, upper)]
        center = [sum(float(matrix[i][j]) * middle[j] for j in range(dimension)) for i in range(dimension)]
        generator_vectors = [[float(matrix[i][j]) * (float(upper[j]) - float(lower[j])) / 2.0
                              for i in range(dimension)] for j in range(dimension)]
        return _zonotope_polygon(center, generator_vectors, indices)
    return None


def _collect_run(plane: Plane, attempt_id: str, capture_root: Path) -> dict[str, Any]:
    case = plane.case_id
    attempt_dir = capture_root / case / "attempts" / attempt_id
    manifest = _read_json(attempt_dir / "run-manifest.json")
    resolution = _read_json(attempt_dir / "resolution-receipt.json")
    postcheck = _read_json(attempt_dir / "postcheck-initial.json")
    if manifest.get("attempt_id") != attempt_id or manifest.get("source_commit") != SOURCE_COMMIT:
        raise ValueError(f"source or attempt identity mismatch for {attempt_id}")
    task_sha = manifest.get("task_sha256")
    if resolution.get("task_id") != plane.task_id or resolution.get("task_sha256") != task_sha:
        raise ValueError(f"task identity mismatch for {attempt_id}")
    if postcheck.get("original_attempt_id") != attempt_id or postcheck.get("task_sha256") != task_sha:
        raise ValueError(f"postcheck identity mismatch for {attempt_id}")
    if postcheck.get("overall_status") != "complete":
        raise ValueError(f"incomplete attempt {attempt_id} cannot be rendered as a completed record")
    if manifest.get("resource_profile_id") != "worker-wall-1800-cpu-1800/1":
        raise ValueError(f"unexpected resource profile for {attempt_id}")

    raw_files: list[dict[str, str]] = []
    stages: list[dict[str, Any]] = []
    stage_paths = sorted(attempt_dir.glob("stage-*.json"))
    if not stage_paths:
        raise ValueError(f"no saved stage records for {attempt_id}")
    for path in stage_paths:
        digest = _sha256(path)
        stage = _read_json(path)
        if stage.get("original_task_sha256") != task_sha:
            raise ValueError(f"stage task identity mismatch in {path}")
        stage_address = int(stage.get("update_index", -1))
        if stage_address != len(stages):
            raise ValueError(f"nonsequential saved updates in {attempt_id}")
        raw_files.append({"path": path.name, "sha256": digest})
        stage["_source_file_sha256"] = digest
        stage["_source_filename"] = path.name
        stages.append(stage)

    first = stages[0]
    if first.get("status") != "applied-and-observed":
        raise ValueError(f"initial stage was not applied and observed for {attempt_id}")
    controller_id = resolution.get("selected_controller_id")
    predicted = first.get("predicted_sets", [])
    node_layers = [layer for layer in predicted if layer.get("role") == "retained-stage-layered-singleton-nodes"]
    cloud_layers = [layer for layer in predicted if layer.get("role") == "complete-authored-action-parent-clouds"]
    nodes = node_layers[0].get("nodes", []) if node_layers else []
    clouds = cloud_layers[0].get("clouds", []) if cloud_layers else []

    shape_rows: list[dict[str, Any]] = []
    if clouds:
        for index, cloud in enumerate(clouds):
            shape = cloud.get("selected_outer_shape")
            polygon = project_shape(shape, plane.raw_indices) if isinstance(shape, dict) else None
            shape_rows.append({
                "update_index": 0,
                "absolute_stage": int(cloud.get("output_stage", cloud.get("stage", -1))),
                "time": float(cloud.get("output_time", cloud.get("parent_time", 0.0))),
                "parent_stage": int(cloud.get("parent_stage", -1)),
                "parent_node_id": cloud.get("parent_node_id"),
                "parent_state": cloud.get("parent_state"),
                "role": "complete-authored-action-parent-cloud",
                "relation": cloud.get("relation"),
                "assurance": cloud.get("assurance"),
                "representation": cloud.get("representation"),
                "shape": shape,
                "projected_geometry": polygon,
                "child_witnesses": [
                    {"action_index": child.get("action_index"),
                     "state": child.get("child_state"),
                     "membership_method": child.get("membership_method"),
                     "accepted_by_selected_shape_numerical_membership": child.get("accepted_by_selected_shape_numerical_membership")}
                    for child in cloud.get("action_child_witnesses", [])
                ],
                "source_pointer": f"stage-000.json#/predicted_sets/{predicted.index(cloud_layers[0])}/clouds/{index}",
                "source_file": first["_source_filename"],
                "source_file_sha256": first["_source_file_sha256"],
            })
    node_rows = []
    for node in nodes:
        state = node.get("state")
        if not isinstance(state, list):
            continue
        node_rows.append({
            "update_index": 0,
            "absolute_stage": int(node.get("absolute_stage", -1)),
            "time": int(node.get("absolute_stage", -1)) * plane.dt,
            "node_id": node.get("node_id"),
            "parent_node_id": node.get("parent_node_id"),
            "state": state,
            "backward_membership_witness": node.get("predecessor_contains_parent"),
            "stage_intersection_membership_witness": node.get("stage_set_intersection_nonempty"),
            "backward_viable": node.get("backward_viable"),
            "source_pointer": "stage-000.json#/predicted_sets/0/nodes",
            "source_file": first["_source_filename"],
            "source_file_sha256": first["_source_file_sha256"],
        })

    predicted_plan = first.get("selected_plan", {})
    plan_states = predicted_plan.get("states", [])
    planned = [{"absolute_stage": i, "time": i * plane.dt, "state": state,
                "point": list(plane.project(state)),
                "source_pointer": f"stage-000.json#/selected_plan/states/{i}",
                "source_file": first["_source_filename"],
                "source_file_sha256": first["_source_file_sha256"]}
               for i, state in enumerate(plan_states) if isinstance(state, list)]
    replay: list[dict[str, Any]] = []
    for stage in stages:
        execution = stage.get("execution", {})
        states, local_times = execution.get("physical_states", []), execution.get("times", [])
        if execution.get("status") != "complete" or len(states) != len(local_times):
            continue
        for index, (state, local_time) in enumerate(zip(states, local_times)):
            if replay and index == 0:
                continue
            replay.append({
                "update_index": int(stage["update_index"]),
                "absolute_stage": int(stage["update_index"]),
                "time": float(local_time),
                "state": state,
                "point": list(plane.project(state)),
                "source_pointer": f"{stage['_source_filename']}#/execution/physical_states/{index}",
                "source_file": stage["_source_filename"],
                "source_file_sha256": stage["_source_file_sha256"],
            })

    observed = first.get("observed_physical")
    if not isinstance(observed, list) or not replay:
        raise ValueError(f"initial state or completed plant replay missing for {attempt_id}")
    all_target = first.get("selected_plan", {}).get("states", [])
    result = {
        "attempt_id": attempt_id,
        "case_id": case,
        "task_id": plane.task_id,
        "task_sha256": task_sha,
        "source_commit": SOURCE_COMMIT,
        "source_hashes": manifest.get("source_hashes", {}),
        "profile_id": manifest.get("resource_profile_id"),
        "graph_fingerprint": manifest.get("graph_fingerprint"),
        "postcheck_status": postcheck.get("overall_status"),
        "controller_id": controller_id,
        "controller_label": CONTROLLER_LABELS.get(controller_id, controller_id),
        "representation": first.get("selected_representation"),
        "policy_semantics": first.get("policy_semantics"),
        "selector": first.get("selector"),
        "scope": "retained graph / complete authored finite-action parent clouds only; model prediction, not all-admissible-control reachability",
        "relation": "outer finite-authored-action parent clouds where a materialized selected outer shape is saved",
        "assurance": "numerical membership and producer-declared outer relation; not independently certified",
        "initial_state": observed,
        "initial_point": list(plane.project(observed)),
        "nodes": node_rows,
        "clouds": shape_rows,
        "planned_prediction": planned,
        "plant_replay": replay,
        "stage_count": len(stages),
        "target": list(plane.target) if plane.target else None,
        "target_semantics": "soft objective target; not a hard terminal set",
        "missing_layers": [
            "all-admissible-control forward reachable sets",
            "materialized predecessor/backward sets",
            "materialized full-state stage intersections",
        ],
        "raw_record": {
            "attempt_id": attempt_id,
            "capture_relative_path": f"{case}/attempts/{attempt_id}",
            "manifest_sha256": _sha256(attempt_dir / "run-manifest.json"),
            "resolution_sha256": _sha256(attempt_dir / "resolution-receipt.json"),
            "postcheck_sha256": _sha256(attempt_dir / "postcheck-initial.json"),
            "stage_files": raw_files,
        },
    }
    if case == "syn-nl-fuel-01":
        result["coordinate_maps"] = {
            "raw_state_order": ["m_ox", "m_f", "q_ox", "q_f"],
            "raw_scales": [100.0, 30.0, 3.0, 1.0],
            "scale_applied_to_recorded_physical_values": False,
            "requested_planes": list(FUEL_PLANES),
            "raw_initial_state": observed,
            "expected_initial_points": [[2.0, 100.0], [0.6, 30.0]],
        }
    if len(all_target) > 0:
        result["planned_final_state"] = all_target[-1]
    return result


def _ellipse_patch(center: list[float], radii: list[float], *, color: str, alpha: float, linestyle: str):
    from matplotlib.patches import Ellipse

    return Ellipse((center[0], center[1]), width=2.0 * radii[0], height=2.0 * radii[1],
                   facecolor=color, edgecolor=color, alpha=alpha, linewidth=0.55,
                   linestyle=linestyle)


def _plot_run(axis, run: dict[str, Any], plane: Plane, cmap, end_time: float,
              focused_stage: int | None = None) -> None:
    import numpy as np
    from matplotlib.patches import Polygon

    all_stages = focused_stage is None
    linestyle = "--" if run["controller_id"] == "native-exact-polytope-backward-graph/1" else "-"
    clouds = run["clouds"] if all_stages else rows_for_output_stage(run["clouds"], focused_stage)
    for item in clouds:
        geometry = item.get("projected_geometry")
        if not geometry:
            continue
        color = cmap(normalized_time(item["time"], end_time))
        kind = item.get("representation")
        if kind == "ellipsoid" and len(geometry) == 2:
            axis.add_patch(_ellipse_patch(geometry[0], geometry[1], color=color,
                                          alpha=0.055 if all_stages else 0.18, linestyle=linestyle))
        elif len(geometry) >= 3:
            axis.add_patch(Polygon(geometry, closed=True, facecolor=color,
                                   edgecolor=color, alpha=0.025 if all_stages else 0.12,
                                   linewidth=0.45, linestyle=linestyle))
    nodes = run["nodes"] if all_stages else rows_for_output_stage(run["nodes"], focused_stage)
    if nodes:
        values = np.asarray([plane.project(row["state"]) for row in nodes], dtype=float)
        times = np.asarray([row["time"] for row in nodes], dtype=float)
        axis.scatter(values[:, 0], values[:, 1], c=times, cmap=cmap, vmin=0.0,
                     vmax=max(end_time, 1e-12), s=3.0, alpha=0.35,
                     label="Retained graph node states", zorder=2)
    line = (run["plant_replay"] if all_stages else
            replay_for_output_stage(run["plant_replay"], focused_stage, plane.dt))
    if line:
        coords = np.asarray([x["point"] for x in line], dtype=float)
        times = np.asarray([x["time"] for x in line], dtype=float)
        axis.plot(coords[:, 0], coords[:, 1], color="#1c2430", linewidth=1.1,
                  linestyle=linestyle, alpha=.82, zorder=4,
                  label="Actual plant replay")
        axis.scatter(coords[:, 0], coords[:, 1], c=times, cmap=cmap,
                     vmin=0.0, vmax=max(end_time, 1e-12),
                     s=6, alpha=.88, edgecolors="none", zorder=5)
    plan = run["planned_prediction"]
    if plan:
        if not all_stages:
            plan = rows_for_output_stage(plan, focused_stage)
        if plan:
            coords = np.asarray([x["point"] for x in plan], dtype=float)
            times = np.asarray([x["time"] for x in plan], dtype=float)
            axis.plot(coords[:, 0], coords[:, 1], color="#090c10", linewidth=1.1,
                      linestyle=":", zorder=6,
                      label="Initial model prediction")
            axis.scatter(coords[:, 0], coords[:, 1], c=times, cmap=cmap,
                         vmin=0.0, vmax=max(end_time, 1e-12),
                         s=7, alpha=.9, edgecolors="none", zorder=7)


def render_figure(entry: dict[str, Any], plane: Plane, output_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    runs = entry["runs"]
    bounds = _plot_bounds(entry, plane)
    panel_count = len(runs)
    cols = min(3, panel_count)
    rows = math.ceil(panel_count / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(6.0 * cols, 4.8 * rows), squeeze=False)
    cmap = plt.get_cmap("viridis")
    end_time = timeline_end(runs)
    for index, run in enumerate(runs):
        axis = axes[index // cols][index % cols]
        _plot_run(axis, run, plane, cmap, end_time)
        x0, y0 = run["initial_point"]
        axis.scatter([x0], [y0], marker="*", s=90, color="#f3b61f", edgecolor="#31270d",
                     linewidth=.65, zorder=8, label="Initial state")
        if run["target"]:
            axis.scatter([run["target"][0]], [run["target"][1]], marker="X", s=65,
                         facecolor="#d64d3b", edgecolor="white", linewidth=.6,
                         zorder=8, label="Soft objective target")
        axis.set_title(run["controller_label"], fontsize=10)
        axis.set_xlabel(f"{plane.names[0]} ({plane.units[0]})")
        axis.set_ylabel(f"{plane.names[1]} ({plane.units[1]})")
        configure_numeric_axis(axis)
        axis.set_xlim(bounds["x"])
        axis.set_ylim(bounds["y"])
    for index in range(panel_count, rows * cols):
        axes[index // cols][index % cols].set_visible(False)
    handles, labels = [], []
    for row in axes:
        for axis in row:
            axis_handles, axis_labels = axis.get_legend_handles_labels()
            for handle, label in zip(axis_handles, axis_labels):
                if label not in labels:
                    labels.append(label)
                    handles.append(handle)
    if handles:
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .94),
                   ncol=min(5, len(labels)), frameon=False, fontsize=8)
    scalar = ScalarMappable(norm=Normalize(0.0, max(1e-12, end_time)), cmap=cmap)
    colorbar_axis = fig.add_axes([.28, .10, .44, .025])
    colorbar = fig.colorbar(scalar, cax=colorbar_axis, orientation="horizontal")
    colorbar.set_label(f"Recorded physical time ({plane.time_unit}); all stage layers share this scale")
    fig.suptitle(f"{plane.title}: recorded closed-loop views", y=.99, fontsize=14)
    fig.subplots_adjust(left=.09, right=.98, top=.85, bottom=.24, hspace=.30, wspace=.27)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{entry['id']}.png", dpi=170, bbox_inches="tight")
    svg_path = output_dir / f"{entry['id']}.svg"
    fig.savefig(svg_path, bbox_inches="tight")
    # Matplotlib emits path commands with trailing spaces; trim them without
    # changing SVG geometry so repository whitespace checks stay useful.
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    plt.close(fig)


def _html_page(entry: dict[str, Any], plane: Plane) -> str:
    ident = html.escape(entry["id"])
    title = html.escape(plane.title)
    missing = "".join(f"<li>{html.escape(item)}</li>" for item in entry["missing_layers"])
    coverage_gaps = "".join(
        f'<li><code>{html.escape(row["controller_id"])}</code>: {html.escape(row["reason"])}</li>'
        for row in entry.get("comparison_coverage_gaps", [])
    )
    shape_gaps = "".join(
        f'<li><code>{html.escape(row["controller_id"])}</code>: {html.escape(row["reason"])}</li>'
        for row in entry.get("shape_coverage_gaps", [])
    )
    raw_links = "".join(
        f'<li><code>{html.escape(run["attempt_id"])}</code> '
        f'capture locator <code>{html.escape(run["raw_record"]["capture_relative_path"])}</code>, '
        f'raw manifest SHA-256 <code>{html.escape(run["raw_record"]["manifest_sha256"])}</code>, '
        f'task <code>{html.escape(run["task_sha256"])}</code></li>' for run in entry["runs"]
    )
    data_url = f"{ident}.plotted-data.json"
    x_label, y_label = (html.escape(v) for v in plane.names)
    x_unit, y_unit = (html.escape(v) for v in plane.units)
    transform = entry["coordinate_transform"]
    permutation = matrix_html(transform["permutation_matrix"], "Projection matrix P")
    scales = transform.get("raw_scales")
    scale_view = ("<p>Raw scale vector in state order: "
                  + matrix_html([[scale] for scale in scales], "Raw scale vector")
                  + ". Recorded values are already physical, so the scales are not reapplied.</p>") if scales else "<p>Recorded values are physical coordinates.</p>"
    timeline_end_value = timeline_end(entry["runs"])
    stage_count = max(run["stage_count"] for run in entry["runs"])
    stage_options = "".join(
        f'<option value="{stage}">Output state stage {stage}; replay {stage - 1}→{stage}</option>'
        for stage in output_stage_values(stage_count) if stage > 0
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Recorded closed-loop figures</title>
<link rel="stylesheet" href="../../examples.css">
<style>
body{{max-width:1100px;margin:2rem auto;padding:0 1rem;font-family:system-ui,sans-serif;line-height:1.5}}
.figure-actions{{display:flex;gap:.7rem;align-items:center;flex-wrap:wrap;margin:1rem 0}}
.figure-frame{{overflow:auto;border:1px solid #667085;border-radius:.6rem;padding:.5rem}}
.figure-frame img,.figure-frame svg{{display:block;width:100%;height:auto}}
.time-key{{height:.7rem;margin:.5rem 0;background:linear-gradient(90deg,#440154,#3b528b,#21918c,#5ec962,#fde725)}}
.note{{border-left:4px solid #d6a500;padding:.6rem 1rem;background:rgba(214,165,0,.08)}}
code{{overflow-wrap:anywhere}} .data-links a{{margin-right:1rem}}
@media(max-width:600px){{body{{margin:1rem auto}}}}
@media print{{.figure-actions{{display:none}}.figure-frame{{overflow:visible}}body{{max-width:none}}}}
</style></head><body>
<main><p><a href="../figure-index.json">All recorded closed-loop figures</a></p>
<h1>{title}</h1>
<p>Stage-coloured projections from saved records. Solid traces show executed plant replay. Dotted traces show the initial model prediction. Shaded shapes show serialized finite authored-action parent clouds, projected from their stored shape parameters.</p>
<div class="figure-actions"><label for="stage-focus">Output state focus</label><select id="stage-focus" aria-label="Output state focus"><option value="all">All stages</option><option value="0">Output state stage 0 (initial)</option>{stage_options}</select>
<a href="{ident}.svg">Standalone SVG</a><a href="{ident}.png">PNG</a><a href="{data_url}">Exact plotted-data JSON</a></div>
<p class="note"><strong>Evidence scope.</strong> Retained graph and finite authored-action model predictions are numerical and policy-conditioned. These plots do not show all-admissible-control reachability. A point or a membership flag is a witness, not a materialized region. The marked terminal objective target is soft, not a hard target set.</p>
<div class="figure-frame"><svg id="stage-svg" viewBox="0 0 1000 620" role="img" aria-label="Interactive {title} stage view"></svg></div>
<div><small>Shared physical-time color scale: 0 to {timeline_end_value:g} {html.escape(plane.time_unit)}</small><div class="time-key" role="img" aria-label="Shared time color scale from early purple to late yellow"></div></div>
<p class="data-links"><a href="{ident}.svg">Open the all-stage SVG export</a> · <a href="{ident}.png">Open the all-stage PNG export</a> · <a href="{data_url}">Exact plotted-data JSON</a></p>
<h2>Unavailable geometric layers</h2><ul>{missing}</ul>
<h2>Incomplete comparison tracks</h2><ul>{coverage_gaps or '<li>All five intended controller tracks have a completed matched record in this capture.</li>'}</ul>
<h2>Tracks without materialized parent-cloud shapes</h2><ul>{shape_gaps or '<li>Each completed track saved its outer parent-cloud shape parameters.</li>'}</ul>
<h2>Saved source records</h2><ul>{raw_links}</ul>
<p>The immutable raw capture archive is external to this Pages bundle. The locators and per-file SHA-256 values above identify its records; a public raw archive link is not available in this capture.</p>
<h2>Rebuild the figures</h2><pre><code>python scripts/reports/recorded_closed_loop_figures.py --capture-root "$CSL_CLOSED_LOOP_CAPTURE_ROOT" --output docs/examples/closed-loop</code></pre>
<p>Source commit <code>{SOURCE_COMMIT}</code>. Coordinate axes are {x_label} ({x_unit}) and {y_label} ({y_unit}). Figures use style <code>{STYLE_ID}</code>.</p>
<section class="math-input"><p>Projection matrix P maps raw state coordinates to the displayed axes: {permutation}</p>{scale_view}<p>Exact coordinate-transform metadata is available in the plotted-data JSON.</p></section>
<script>
const focus=document.querySelector('#stage-focus'),svg=document.querySelector('#stage-svg');
const NS='http://www.w3.org/2000/svg';
const make=(tag,attrs={{}},text='')=>{{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text)e.textContent=text;return e}};
const stops=['#440154','#3b528b','#21918c','#5ec962','#fde725'];
const color=(time,end)=>{{const t=Math.min(1,Math.max(0,time/Math.max(end,1e-12)))*4,i=Math.min(3,Math.floor(t)),f=t-i;const rgb=c=>[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)];const a=rgb(stops[i]),b=rgb(stops[i+1]);return `rgb(${{a.map((v,j)=>Math.round(v+(b[j]-v)*f)).join(',')}})`}};
const replayForOutputStage=(rows,k,dt)=>{{const eps=Math.max(1,Math.abs(k*dt))*1e-10;if(k===0)return rows.filter(p=>Math.abs(p.time)<=eps);const lo=(k-1)*dt,hi=k*dt;return rows.filter(p=>p.time>=lo-eps&&p.time<=hi+eps)}};
function draw(d,selected){{
 const runs=d.runs, b=d.plot_bounds, left=95,right=950,top=45,bottom=535;
 const x=v=>left+(v-b.x[0])/(b.x[1]-b.x[0])*(right-left), y=v=>bottom-(v-b.y[0])/(b.y[1]-b.y[0])*(bottom-top);
 svg.replaceChildren();
 svg.append(make('rect',{{x:0,y:0,width:1000,height:620,fill:'transparent'}}));
 svg.append(make('line',{{x1:left,y1:bottom,x2:right,y2:bottom,stroke:'#53606f'}}));
 svg.append(make('line',{{x1:left,y1:top,x2:left,y2:bottom,stroke:'#53606f'}}));
 for(let i=0;i<=5;i++){{const xv=b.x[0]+(b.x[1]-b.x[0])*i/5, yv=b.y[0]+(b.y[1]-b.y[0])*i/5;
  svg.append(make('line',{{x1:x(xv),y1:top,x2:x(xv),y2:bottom,stroke:'#aab2bd','stroke-opacity':.28}}));
  svg.append(make('text',{{x:x(xv),y:bottom+20,'text-anchor':'middle','font-size':12,fill:'currentColor'}},Number(xv.toPrecision(5)).toString()));
  svg.append(make('line',{{x1:left,y1:y(yv),x2:right,y2:y(yv),stroke:'#aab2bd','stroke-opacity':.28}}));
  svg.append(make('text',{{x:left-9,y:y(yv)+4,'text-anchor':'end','font-size':12,fill:'currentColor'}},Number(yv.toPrecision(5)).toString()));
 }}
 for(let ri=0;ri<runs.length;ri++){{const run=runs[ri], lineColor=['#1769aa','#c04424','#18864b','#8156a8','#bc7b12'][ri%5];
  for(const c of run.clouds||[]){{if(selected!=='all'&&c.absolute_stage!==Number(selected))continue;const g=c.projected_geometry;if(!g)continue;const col=color(c.time,d.timeline_end);
   if(c.representation==='ellipsoid'&&g.length===2)svg.append(make('ellipse',{{cx:x(g[0][0]),cy:y(g[0][1]),rx:Math.abs(x(g[0][0]+g[1][0])-x(g[0][0])),ry:Math.abs(y(g[0][1]+g[1][1])-y(g[0][1])),fill:col,'fill-opacity':selected==='all'?.08:.2,stroke:col,'stroke-width':1}}));
   else if(g.length>2)svg.append(make('polygon',{{points:g.map(p=>`${{x(p[0])}},${{y(p[1])}}`).join(' '),fill:col,'fill-opacity':selected==='all'?.035:.16,stroke:col,'stroke-width':.6}}));
  }}
  const graph=(run.nodes||[]).filter(n=>selected==='all'||n.absolute_stage===Number(selected));
  for(const n of graph){{const p=n.state,ix=d.coordinate_transform.raw_indices;svg.append(make('circle',{{cx:x(p[ix[0]]),cy:y(p[ix[1]]),r:2.3,fill:color(n.time,d.timeline_end),'fill-opacity':.65}}));}}
  const replay=selected==='all'?(run.plant_replay||[]):replayForOutputStage(run.plant_replay||[],Number(selected),d.time_step);
  if(replay.length){{svg.append(make('polyline',{{points:replay.map(p=>`${{x(p.point[0])}},${{y(p.point[1])}}`).join(' '),fill:'none',stroke:lineColor,'stroke-width':2.3}}));for(const p of replay)svg.append(make('circle',{{cx:x(p.point[0]),cy:y(p.point[1]),r:3.1,fill:color(p.time,d.timeline_end),stroke:lineColor,'stroke-width':.7}}));}}
  const plan=(run.planned_prediction||[]).filter(p=>selected==='all'||p.absolute_stage===Number(selected));
  if(plan.length){{svg.append(make('polyline',{{points:plan.map(p=>`${{x(p.point[0])}},${{y(p.point[1])}}`).join(' '),fill:'none',stroke:'#111820','stroke-width':1.5,'stroke-dasharray':'5 4'}}));for(const p of plan)svg.append(make('circle',{{cx:x(p.point[0]),cy:y(p.point[1]),r:2.6,fill:color(p.time,d.timeline_end)}}));}}
  if(selected==='all'||selected==='0'){{const p=run.initial_point;svg.append(make('path',{{d:`M ${{x(p[0])-7}} ${{y(p[1])}} L ${{x(p[0])+7}} ${{y(p[1])}} M ${{x(p[0])}} ${{y(p[1])-7}} L ${{x(p[0])}} ${{y(p[1])+7}}`,stroke:'#e1a900','stroke-width':3}}));}}
  if(run.target)svg.append(make('path',{{d:`M ${{x(run.target[0])-6}} ${{y(run.target[1])-6}} L ${{x(run.target[0])+6}} ${{y(run.target[1])+6}} M ${{x(run.target[0])-6}} ${{y(run.target[1])+6}} L ${{x(run.target[0])+6}} ${{y(run.target[1])-6}}`,stroke:'#c02f31','stroke-width':2.5}}));
  svg.append(make('rect',{{x:left+5,y:top+5+ri*18,width:Math.min(280,run.controller_label.length*7.4+12),height:16,rx:2,fill:'white','fill-opacity':.86}}));
  svg.append(make('text',{{x:left+10,y:top+17+ri*18,fill:lineColor,'font-size':12}},run.controller_label));
 }}
 svg.append(make('text',{{x:(left+right)/2,y:590,'text-anchor':'middle','font-size':14,fill:'currentColor'}},`${{d.coordinate_transform.names[0]}} (${{d.coordinate_transform.units[0]}})`));
 const yl=make('text',{{x:22,y:(top+bottom)/2,'text-anchor':'middle','font-size':14,fill:'currentColor',transform:`rotate(-90 22 ${{(top+bottom)/2}})`}},`${{d.coordinate_transform.names[1]}} (${{d.coordinate_transform.units[1]}})`);svg.append(yl);
}}
fetch('{data_url}').then(r=>r.json()).then(d=>{{draw(d,'all');focus.addEventListener('change',()=>draw(d,focus.value));}});
</script></main></body></html>'''


def _figure_entry(plane: Plane, capture_root: Path) -> dict[str, Any]:
    case = plane.case_id
    runs = [_collect_run(plane, attempt, capture_root) for attempt in ATTEMPTS[case]]
    expected_hashes = {run["task_sha256"] for run in runs}
    if len(expected_hashes) != 1:
        raise ValueError(f"cannot compare different task hashes for {case}")
    runs.sort(key=lambda run: (run["representation"] if run["representation"] is not None else -1,
                               run["controller_id"]))
    seen_controllers = {run["controller_id"] for run in runs}
    comparison_controllers = (
        "native-exact-polytope-backward-graph/1",
        "native-box-mpc/1",
        "native-zonotope-mpc/1",
        "native-parallelotope-mpc/1",
        "native-ellipsoid-mpc/1",
    )
    coverage_gaps = [{
        "controller_id": controller,
        "outcome": "no complete matched record in the selected source capture",
        "reason": "No geometry or trajectory is inferred from an absent or incomplete attempt.",
    } for controller in comparison_controllers if controller not in seen_controllers]
    shape_gaps = [{
        "attempt_id": run["attempt_id"],
        "controller_id": run["controller_id"],
        "reason": "The saved response has retained graph points but no materialized parent-cloud shape geometry.",
    } for run in runs if not run["clouds"]]
    return {
        "id": plane.figure_id,
        "availability": "ready",
        "href": f"examples/closed-loop/figures/{plane.figure_id}.html",
        "plotted_data_href": f"examples/closed-loop/figures/{plane.figure_id}.plotted-data.json",
        "svg_href": f"examples/closed-loop/figures/{plane.figure_id}.svg",
        "png_href": f"examples/closed-loop/figures/{plane.figure_id}.png",
        "title": plane.title,
        "task_id": plane.task_id,
        "task_sha256": next(iter(expected_hashes)),
        "stage_count": max(run["stage_count"] for run in runs),
        "time_step": plane.dt,
        "timeline_end": timeline_end(runs),
        "source_commit": SOURCE_COMMIT,
        "profile_id": "worker-wall-1800-cpu-1800/1",
        "reproduction_command": "python scripts/reports/recorded_closed_loop_figures.py --capture-root \"$CSL_CLOSED_LOOP_CAPTURE_ROOT\" --output docs/examples/closed-loop",
        "coordinate_transform": {
            "raw_indices": list(plane.raw_indices),
            "names": list(plane.names),
            "units": list(plane.units),
            "description": plane.transform_description,
            "permutation_matrix": [
                [1.0 if column == index else 0.0 for column in range(len(plane.raw_indices) if plane.case_id == "syn-nl-lv-01" else 4)]
                for index in plane.raw_indices
            ] if plane.case_id != "syn-nl-lv-01" else [[1.0, 0.0], [0.0, 1.0]],
            "raw_scales": [100.0, 30.0, 3.0, 1.0] if plane.case_id == "syn-nl-fuel-01" else None,
            "source_values_are_physical": True,
            "scale_applied_to_source_values": False,
        },
        "layer_scopes": [
            "initial physical state",
            "retained stage-layered graph singleton nodes",
            "serialized complete authored-action parent clouds when present",
            "initial model-predicted plan",
            "executed physical plant replay",
            "soft objective target when defined",
        ],
        "missing_layers": [
            "complete all-stage forward-set geometry over the full reachable parent set",
            "all-admissible-control forward reachable sets",
            "materialized backward/predecessor sets",
            "materialized full-state intersections",
        ],
        "raw_record_refs": [{
            "attempt_id": run["attempt_id"],
            "capture_relative_path": run["raw_record"]["capture_relative_path"],
            "manifest_sha256": run["raw_record"]["manifest_sha256"],
            "stage_count": len(run["raw_record"]["stage_files"]),
            "raw_stage_hashes": run["raw_record"]["stage_files"],
        } for run in runs],
        "runs": runs,
        "comparison_coverage_gaps": coverage_gaps,
        "shape_coverage_gaps": shape_gaps,
    }


def _plot_bounds(entry: dict[str, Any], plane: Plane) -> dict[str, list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for run in entry["runs"]:
        for row in run["clouds"]:
            geometry = row.get("projected_geometry") or []
            if row.get("representation") == "ellipsoid" and len(geometry) == 2:
                center, radii = geometry
                xs.extend([center[0] - radii[0], center[0] + radii[0]])
                ys.extend([center[1] - radii[1], center[1] + radii[1]])
            else:
                xs.extend(float(point[0]) for point in geometry if isinstance(point, list) and len(point) == 2)
                ys.extend(float(point[1]) for point in geometry if isinstance(point, list) and len(point) == 2)
        for series in (run["nodes"], run["planned_prediction"], run["plant_replay"]):
            for row in series:
                point = row.get("point") or plane.project(row["state"])
                xs.append(float(point[0]))
                ys.append(float(point[1]))
        if run.get("target"):
            xs.append(float(run["target"][0]))
            ys.append(float(run["target"][1]))
    if not xs or not ys:
        raise ValueError(f"no finite plotted coordinates for {entry['id']}")
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    xpad = max((xmax - xmin) * .04, abs(xmin) * 1e-6, 1e-9)
    ypad = max((ymax - ymin) * .04, abs(ymin) * 1e-6, 1e-9)
    return {"x": [xmin - xpad, xmax + xpad], "y": [ymin - ypad, ymax + ypad]}


def build(capture_root: Path, destination: Path | None = None) -> dict[str, Any]:
    """Build figures and a read-only FigureIndex from completed saved records."""
    output = destination or (Path(__file__).resolve().parents[2] / "docs/examples/closed-loop")
    figure_dir = output / "figures"
    entries = [_figure_entry(plane, capture_root) for plane in [*PLANES.values(), FUEL_FUEL_PLANE]]
    index = {"schema": SCHEMA, "style_id": STYLE_ID, "figures": []}
    for entry in entries:
        plane = next(p for p in [*PLANES.values(), FUEL_FUEL_PLANE] if p.figure_id == entry["id"])
        entry_for_plot = dict(entry)
        render_figure(entry_for_plot, plane, figure_dir)
        data = {
            "schema": "csl.closed-loop.plotted-data/1",
            "figure_id": entry["id"],
            "case_id": entry["runs"][0]["case_id"],
            "task_id": entry["task_id"],
            "task_sha256": entry["task_sha256"],
            "source_commit": entry["source_commit"],
            "coordinate_transform": entry["coordinate_transform"],
            "comparison_coverage_gaps": entry["comparison_coverage_gaps"],
            "shape_coverage_gaps": entry["shape_coverage_gaps"],
            "runs": entry["runs"],
            "reproduction_command": "python scripts/reports/recorded_closed_loop_figures.py --capture-root \"$CSL_CLOSED_LOOP_CAPTURE_ROOT\" --output docs/examples/closed-loop",
            "stage_count": max(run["stage_count"] for run in entry["runs"]),
            "time_step": plane.dt,
            "timeline_end": timeline_end(entry["runs"]),
            "plot_bounds": _plot_bounds(entry, plane),
        }
        (figure_dir / f"{entry['id']}.plotted-data.json").write_text(
            json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        (figure_dir / f"{entry['id']}.html").write_text(_html_page(entry, plane), encoding="utf-8")
        index["figures"].append({key: entry[key] for key in (
            "id", "availability", "href", "plotted_data_href", "svg_href", "png_href",
            "title", "task_id", "task_sha256", "source_commit", "profile_id",
            "stage_count", "time_step", "timeline_end",
            "coordinate_transform", "layer_scopes", "missing_layers", "comparison_coverage_gaps",
            "shape_coverage_gaps", "raw_record_refs", "reproduction_command")})
    output.mkdir(parents=True, exist_ok=True)
    index_path = output / "figure-index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path,
                        default=Path(os.environ["CSL_CLOSED_LOOP_CAPTURE_ROOT"])
                        if os.environ.get("CSL_CLOSED_LOOP_CAPTURE_ROOT") else None)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "docs/examples/closed-loop")
    args = parser.parse_args()
    if args.capture_root is None:
        parser.error("provide --capture-root or set CSL_CLOSED_LOOP_CAPTURE_ROOT")
    index = build(args.capture_root, args.output)
    print(f"wrote {len(index['figures'])} recorded figure entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

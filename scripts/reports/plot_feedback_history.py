#!/usr/bin/env python3
"""Project every saved full-state feedback set from one observed-state query."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import math
import itertools
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from contracts import load_task, manifest_sha256
from figure_style import (STYLE_ID, configure_numeric_axis, STAGE_PALETTE as PALETTE,
                          STAGE_BACKGROUND as BACKGROUND, STAGE_FOREGROUND as FOREGROUND)

PLANES = {"syn-nl-lv-01": [(0, 1)], "earth-orbit": [(0, 3)],
          "syn-nl-fuel-01": [(2, 0), (3, 1)]}


def axis_bounds(member, dimension):
    lower = [float("-inf")] * dimension
    upper = [float("inf")] * dimension
    for rows, bounds, equality in ((member["inequalities"], member["upper_bounds"], False),
                                   (member["equalities"], member["equality_values"], True)):
        if len(rows) != len(bounds):
            raise ValueError("box row count differs from bounds")
        for row, bound in zip(rows, bounds):
            active = [i for i, value in enumerate(row) if value != 0]
            if len(row) != dimension or len(active) != 1:
                raise ValueError("box membership is not axis-aligned in full state space")
            i = active[0]
            value = bound / row[i]
            if row[i] > 0 or equality:
                upper[i] = min(upper[i], value)
            if row[i] < 0 or equality:
                lower[i] = max(lower[i], value)
    import math
    if any(not math.isfinite(v) for v in lower + upper) or any(a > b for a,b in zip(lower, upper)):
        raise ValueError("box does not have finite ordered bounds")
    return lower, upper


def convex_boundary(points):
    points = sorted(set(map(tuple, points)))
    if len(points) < 3:
        return points
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    halves = []
    for ordered in (points, reversed(points)):
        half = []
        for point in ordered:
            while len(half) > 1 and cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return halves[0] + halves[1]


def h_polygon(member):
    A = np.asarray(member["inequalities"], dtype=float).reshape(-1, 2)
    b = np.asarray(member["upper_bounds"], dtype=float)
    E = np.asarray(member["equalities"], dtype=float).reshape(-1, 2)
    e = np.asarray(member["equality_values"], dtype=float)
    if len(A) != len(b) or len(E) != len(e) or not all(np.isfinite(v).all() for v in (A, b, E, e)):
        raise ValueError("invalid finite H rows")
    rank = np.linalg.matrix_rank(E) if len(E) else 0
    if rank == 0:
        angles = sorted(math.atan2(row[1], row[0]) for row in A if np.any(row))
        if not angles or max(y-x for x, y in zip(angles, angles[1:]+[angles[0]+2*math.pi])) >= math.pi:
            raise ValueError("bounded H polygon required")
    elif rank == 1:
        normal = next(row for row in E if np.any(row))
        slopes = A @ np.array([-normal[1], normal[0]])
        if not (np.any(slopes > 0) and np.any(slopes < 0)):
            raise ValueError("bounded H segment required")
    rows = np.concatenate((A, E))
    rhs = np.concatenate((b, e))
    points = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        pair = rows[[i, j]]
        if np.linalg.det(pair) == 0:
            continue
        point = np.linalg.solve(pair, rhs[[i, j]])
        if (np.isfinite(point).all() and np.all(A @ point <= b + 1e-9*(1+np.abs(b)))
                and np.all(np.abs(E @ point-e) <= 1e-9*(1+np.abs(e)))):
            points.append(point)
    if not points:
        raise ValueError("no finite vertices of the bounded H set")
    return convex_boundary(points)


def project_h(member, dimension, first, second):
    from scipy.optimize import linprog
    A = np.asarray(member["inequalities"], dtype=float).reshape(-1, dimension)
    E = np.asarray(member["equalities"], dtype=float).reshape(-1, dimension)
    b = np.asarray(member["upper_bounds"], dtype=float)
    e = np.asarray(member["equality_values"], dtype=float)
    if len(A) != len(b) or len(E) != len(e) or not all(np.isfinite(v).all() for v in (A, b, E, e)):
        raise ValueError("invalid finite full-state H rows")
    def support(direction):
        objective = np.zeros(dimension)
        objective[[first, second]] = -np.asarray(direction)
        objective /= max(np.max(np.abs(objective)), 1e-300)
        result = linprog(objective, A_ub=A if len(A) else None, b_ub=b if len(A) else None,
                         A_eq=E if len(E) else None, b_eq=e if len(E) else None,
                         bounds=[(None, None)]*dimension, method="highs")
        if not result.success:
            raise ValueError("bounded feasible H projection required: " + result.message)
        return result.x[[first, second]]
    points = np.asarray([support(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))])
    origin = np.min(points, axis=0)
    scales = np.ptp(points, axis=0)
    scales[scales == 0] = 1
    normalized = [tuple(p) for p in (points-origin)/scales]
    for _ in range(128):
        hull = convex_boundary(normalized)
        if len(hull) == 2:
            edge = np.asarray(hull[1])-hull[0]
            normal = np.array([edge[1], -edge[0]]) / np.linalg.norm(edge)
            extra = []
            for direction in (normal, -normal):
                point = (support(direction/scales)-origin)/scales
                if abs(normal @ (point-hull[0])) > 1e-8:
                    extra.append(tuple(point))
            if extra:
                normalized.extend(extra)
                continue
        if len(hull) < 3:
            return {"points": (np.asarray(hull)*scales+origin).tolist(),
                    "method": "numerical full-state LP projection", "normalized_support_tolerance": 1e-8}
        additions = []
        for a, b0 in zip(hull, hull[1:]+hull[:1]):
            edge = np.asarray(b0)-a
            direction = np.array([edge[1], -edge[0]])
            direction /= np.linalg.norm(direction)
            point = (support(direction/scales)-origin)/scales
            if direction @ (point-a) > 1e-8:
                additions.append(tuple(point))
        if not additions:
            return {"points": (np.asarray(hull)*scales+origin).tolist(),
                    "method": "numerical full-state LP projection", "normalized_support_tolerance": 1e-8}
        normalized.extend(additions)
        if len(normalized) > 2048:
            break
    raise ValueError("H projection rendering quota exhausted")


def project_member(member, dimension, first, second):
    if first == second or not 0 <= first < dimension or not 0 <= second < dimension:
        raise ValueError("distinct physical projection coordinates required")
    kind = member["kind"]
    if kind == "h":
        try:
            lower, upper = axis_bounds(member, dimension)
        except ValueError:
            if dimension == 2:
                points = np.asarray(h_polygon(member))[:, [first, second]].tolist()
                return {"points": points, "method": "numerical 2D H boundary intersections"}
            return project_h(member, dimension, first, second)
        return {"points": [[lower[first], lower[second]], [upper[first], lower[second]],
                            [upper[first], upper[second]], [lower[first], upper[second]]],
                "method": "full-state axis H projection"}
    if kind not in {"zonotope", "ellipsoid"}:
        raise ValueError("unknown saved set representation")
    center = np.asarray(member["center"], dtype=float)
    factor = np.asarray(member["factor"], dtype=float)
    if (center.shape != (dimension,) or factor.shape != (dimension, member["factor_count"])
            or not np.isfinite(center).all() or not np.isfinite(factor).all()):
        raise ValueError("invalid full-state center or factor")
    center, factor = center[[first, second]], factor[[first, second]]
    if not factor.size:
        return {"points": [center.tolist()], "method": "zero-factor point projection"}
    if kind == "zonotope":
        generators = []
        for g in factor.T:
            if not np.any(g):
                continue
            if g[1] < 0 or (g[1] == 0 and g[0] < 0):
                g = -g
            generators.append(g)
        generators.sort(key=lambda g: math.atan2(g[1], g[0]))
        current = center-sum(generators, np.zeros(2))
        points = [current.tolist()]
        for sign in (1, -1):
            for g in generators:
                current = current + sign*2*g
                points.append(current.tolist())
        return {"points": points, "method": "projected generator boundary"}
    left, singular, _ = np.linalg.svd(factor, full_matrices=True)
    radii = np.zeros(2)
    radii[:len(singular)] = singular
    angles = np.linspace(0, 2*math.pi, 129)
    points = center[:, None] + (left*radii) @ np.array([np.cos(angles), np.sin(angles)])
    return {"points": points.T.tolist(), "method": "projected ellipsoid factor",
            "rendering_segments": 128}


def render(task_name, response, attempt_path, destination, capture_source, renderer_source):
    if destination.exists() or destination.is_symlink():
        raise ValueError("output directory must be new")
    task = load_task(task_name)
    raw = response.read_bytes()
    data = json.loads(raw)
    attempt_bytes = attempt_path.read_bytes()
    attempt = json.loads(attempt_bytes)
    if (attempt.get("status") != "complete" or attempt.get("completed_holds") != task["episode"]["intervals"]
            or attempt.get("task_id") != task["task_id"] or attempt.get("task_sha256") != manifest_sha256(task)):
        raise ValueError("complete matching observed trajectory required")
    stage0 = json.loads((attempt_path.parent / "stage-000.json").read_text())
    reference = stage0["native_query_capture"]
    metadata_bytes = (attempt_path.parent / reference["path"]).read_bytes()
    if hashlib.sha256(metadata_bytes).hexdigest() != reference["sha256"]:
        raise ValueError("saved stage capture metadata differs")
    metadata = json.loads(metadata_bytes)
    if hashlib.sha256(raw).hexdigest() != metadata["response"]["sha256"]:
        raise ValueError("response differs from the saved first query")
    geometry = data["geometry"]
    n = len(task["model"]["states"])
    horizon = data["coordinates"]["horizon"]
    family = geometry["family"]
    if (geometry["status"] != "complete" or family not in {"polytope", "box", "zonotope", "parallelotope", "ellipsoid"}
            or len(geometry["stages"]) != horizon + 1):
        raise ValueError("complete all-stage selected-family geometry required")
    protocol = "cold at each query; known warm-start protocol gap"
    initialization_sources = []
    first_request_bytes = (attempt_path.parent / metadata["request"]["path"]).read_bytes()
    if hashlib.sha256(first_request_bytes).hexdigest() != metadata["request"]["sha256"]:
        raise ValueError("first query request differs")
    first_request = json.loads(first_request_bytes)
    if "warm_start" in first_request:
        stage1 = json.loads((attempt_path.parent / "stage-001.json").read_bytes())
        next_ref = stage1["native_query_capture"]
        next_metadata_bytes = (attempt_path.parent / next_ref["path"]).read_bytes()
        if hashlib.sha256(next_metadata_bytes).hexdigest() != next_ref["sha256"]:
            raise ValueError("next query metadata differs")
        next_metadata = json.loads(next_metadata_bytes)
        next_request_bytes = (attempt_path.parent / next_metadata["request"]["path"]).read_bytes()
        if hashlib.sha256(next_request_bytes).hexdigest() != next_metadata["request"]["sha256"]:
            raise ValueError("next query request differs")
        next_request = json.loads(next_request_bytes)
        if (first_request["warm_start"]["policy"] != "initial-zero-control-rollout"
                or next_request["warm_start"]["policy"] != "shift-prior-primal-drop-applied-stage-no-terminal-repeat"
                or next_request["warm_start"]["dual_policy"] != "zero-every-solve"):
            raise ValueError("unexpected recorded initialization protocol")
        protocol = "initial observed-state rollout; subsequent shifted history primal and zero supplied duals"
        initialization_sources = [metadata["request"], next_metadata["request"]]
    protocol_label = ("Shifted primal; supplied zero duals; composite SDK build."
                      if initialization_sources else "Cold starts; composite SDK build.")
    all_sets = []
    for k, stage in enumerate(geometry["stages"]):
        if stage["stage"] != k or stage["coordinates"] != list(range(n)) or "intersection_h" not in stage:
            raise ValueError("missing full-state intersection, stage or state coordinates")
        members = {member["role"]: member for member in stage["memberships"]}
        if set(members) != {"forward", "backward", "intersection"}:
            raise ValueError("missing F/B/I membership")
        all_sets.append(members)
    trajectory = attempt["physical_states"]
    if len(trajectory) != horizon + 1 or any(len(state) != n for state in trajectory):
        raise ValueError("observed trajectory dimensions differ")
    target = task["objective"]["source_definition"]["terminal_target"]
    bounds = [row.get("bounds") for row in task["model"]["states"]]
    destination.mkdir(parents=True)
    output = []
    projection_records = []
    cmap = LinearSegmentedColormap.from_list("csl-omarchy-stages", [PALETTE[1], PALETTE[0], PALETTE[2]])
    norm = Normalize(0, max(horizon, 1))
    roles = (("forward", "-", "Forward F"), ("backward", "--", "Forward-relevant backward B"),
             ("intersection", ":", "Intersection I"))
    for first, second in PLANES[task_name]:
        projected = []
        for k, stage in enumerate(all_sets):
            row = {role: project_member(member, n, first, second) for role, member in stage.items()}
            projected.append(row)
            projection_records.append({"stage": k, "raw_state_indices": [first, second], "sets": row})
        bounded_terminal_plane = bounds[first] is not None and bounds[second] is not None
        for variant in ("screen", "print"):
            dark = variant == "screen"
            background = BACKGROUND if dark else "white"
            foreground = FOREGROUND if dark else "#202124"
            fig, axis = plt.subplots(figsize=(7.2, 8.8))
            fig.subplots_adjust(left=0.14, right=0.83, top=0.89, bottom=0.33)
            fig.patch.set_facecolor(background)
            axis.set_facecolor(background)
            for role, linestyle, _ in roles:
                for k, stage in enumerate(projected):
                    points = np.asarray(stage[role]["points"])
                    if len(points) == 1:
                        axis.scatter(points[:, 0], points[:, 1], s=4, color=[cmap(norm(k))])
                    else:
                        closed = np.concatenate((points, points[:1])) if len(points) > 2 else points
                        axis.plot(closed[:, 0], closed[:, 1], color=cmap(norm(k)), linestyle=linestyle,
                                  linewidth=0.85, alpha=0.72 if dark else 0.9)
            if bounded_terminal_plane:
                lo1, hi1 = bounds[first]
                lo2, hi2 = bounds[second]
                axis.add_patch(Rectangle((lo1, lo2), hi1-lo1, hi2-lo2, fill=False,
                    edgecolor=PALETTE[3] if dark else "#9e3157", linestyle="-.", linewidth=1.3))
            axis.plot([x[first] for x in trajectory], [x[second] for x in trajectory],
                      color=foreground, linewidth=2.1, zorder=6)
            axis.scatter([trajectory[0][first]], [trajectory[0][second]], marker="o",
                         s=46, c=[PALETTE[4] if dark else "#25683a"], edgecolors=foreground, zorder=7)
            axis.scatter([target[first]], [target[second]], marker="*", s=120,
                         c=[PALETTE[2] if dark else "#935500"], edgecolors=foreground, zorder=8)
            axis.autoscale_view()
            first_state, second_state = task["model"]["states"][first], task["model"]["states"][second]
            axis.set_xlabel(f"{first_state['name']} ({first_state['unit']})", color=foreground)
            axis.set_ylabel(f"{second_state['name']} ({second_state['unit']})", color=foreground)
            axis.set_title(f"All {family} F/B/I stages and observed trajectory", color=foreground)
            axis.tick_params(colors=foreground)
            for spine in axis.spines.values():
                spine.set_color(foreground)
            configure_numeric_axis(axis)
            handles = [Line2D([0], [0], color=foreground, linestyle=style, label=label) for _,style,label in roles]
            handles += [Line2D([0], [0], color=foreground, linewidth=2, label="Observed nonlinear plant"),
                Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE[4] if dark else "#25683a",
                       markeredgecolor=foreground, label="Initial state"),
                Line2D([0], [0], marker="*", color="none", markerfacecolor=PALETTE[2] if dark else "#935500",
                       markeredgecolor=foreground, markersize=10, label="Soft terminal reference")]
            if bounded_terminal_plane:
                handles.append(Line2D([0], [0], color=PALETTE[3] if dark else "#9e3157",
                                      linestyle="-.", label="Terminal state bounds"))
            legend = axis.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.25),
                                 ncol=2, fontsize=9, frameon=False)
            for text in legend.get_texts():
                text.set_color(foreground)
            colorbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axis, label="Local predicted stage")
            colorbar.ax.yaxis.label.set_color(foreground)
            colorbar.ax.tick_params(colors=foreground)
            fig.suptitle(f"{task_name} · first observed query, stages 0–{horizon}", color=foreground, y=0.97)
            terminal_note = ("" if bounded_terminal_plane else
                             "\nNo bounded terminal region is specified in this plane.")
            fig.text(0.5, 0.035, "Outer affine-predictor sets; observed nonlinear plant.\n" + protocol_label + terminal_note,
                     ha="center", color=foreground, fontsize=8)
            path = destination / f"all-stages-{first}-{second}-{variant}.png"
            fig.savefig(path, dpi=150, facecolor=background)
            vector = path.with_suffix(".svg")
            fig.savefig(vector, facecolor=background)
            vector.write_text("".join(line.rstrip() + chr(10) for line in vector.read_text().splitlines()))
            plt.close(fig)
            for rendered in (path, vector):
                output.append({"path": rendered.name, "sha256": hashlib.sha256(rendered.read_bytes()).hexdigest(),
                               "raw_state_indices": [first, second], "variant": variant})
    receipt = {"schema": "csl.feedback-history-stage-figure/1", "task_id": task["task_id"],
        "input_response_sha256": hashlib.sha256(raw).hexdigest(),
        "input_attempt_sha256": hashlib.sha256(attempt_bytes).hexdigest(), "capture_source_commit": capture_source,
        "renderer_source_commit": renderer_source,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "query_scope": "first observed-state query; all predicted stages, not all replans",
        "trajectory_scope": "observed nonlinear plant across full episode",
        "terminal_feasibility": "finite projected physical bounds shown when present; no bounded region invented for an unbounded source domain",
        "terminal_reference": "soft objective reference, not a terminal constraint",
        "full_state_before_projection": True, "family": family, "stages": horizon+1,
        "projections": projection_records,
        "projection_scope": "Numerical rendering of saved full-state sets; ellipsoid tessellation and LP projection tolerances are rendering details, not new algorithmic enclosure guarantees.",
        "quantitative_style": STYLE_ID, "palette": "shared Omarchy stage palette",
        "execution_protocol": protocol, "initialization_sources": initialization_sources,
        "build_scope": "composite current compiled sources and f4 installed SDK",
        "figures": output}
    (destination / "render-receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=PLANES, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--capture-source", required=True)
    parser.add_argument("--renderer-source", required=True)
    args = parser.parse_args()
    render(args.task, args.response, args.attempt, args.output, args.capture_source, args.renderer_source)


if __name__ == "__main__":
    main()

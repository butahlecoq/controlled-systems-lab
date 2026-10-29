#!/usr/bin/env python3
"""Add terminal-stage approximation outlines to the published two-plane SVG."""

from __future__ import annotations

import argparse
import html
import itertools
import json
import math
from pathlib import Path


COLORS = {
    "exact-polytope-quickhull": "#f4f1e8",
    "axis-box": "#f6c85f",
    "rotated-parallelotope": "#ef8354",
    "directional-ellipsoid": "#ef476f",
    "zonotope-axis-cover": "#06d6a0",
}
LABELS = {
    "exact-polytope-quickhull": "Binary64 projected hull",
    "axis-box": "Axis box",
    "rotated-parallelotope": "Rotated parallelotope",
    "directional-ellipsoid": "Directional ellipsoid",
    "zonotope-axis-cover": "Reduced zonotope cover",
}


def hull(points):
    points = sorted(set(tuple(map(float, point)) for point in points))
    if len(points) <= 1:
        return points

    def turn(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    lower = []
    for point in points:
        while len(lower) > 1 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) > 1 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def h_vertices(shape):
    rows, bounds = shape["inequality_rows"], shape["inequality_bounds"]
    points = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        a, b = rows[i]
        c, d = rows[j]
        det = a * d - b * c
        if abs(det) < 1e-18:
            continue
        point = ((bounds[i] * d - b * bounds[j]) / det,
                 (a * bounds[j] - bounds[i] * c) / det)
        if all(r[0] * point[0] + r[1] * point[1] <= bound + 1e-10
               for r, bound in zip(rows, bounds)):
            points.append(point)
    return hull(points)


def zonotope_vertices(shape):
    center = shape["center"]
    rows = shape["generators"]
    count = len(rows[0])
    points = []
    for signs in itertools.product((-1, 1), repeat=count):
        points.append(tuple(center[row] + sum(signs[k] * rows[row][k]
                            for k in range(count)) for row in range(2)))
    return hull(points)


def ellipse_outline(shape):
    center = shape["center"]
    matrix = shape["orientation"]
    radii = shape["radii"]
    a, b = matrix[0]
    c, d = matrix[1]
    det = a * d - b * c
    points = []
    for index in range(128):
        theta = 2 * math.pi * index / 128
        y0, y1 = radii[0] * math.cos(theta), radii[1] * math.sin(theta)
        points.append((center[0] + (d * y0 - b * y1) / det,
                       center[1] + (-c * y0 + a * y1) / det))
    return points


def vertices(shape):
    kind = shape["kind"]
    if kind == "v_polytope":
        return hull(shape["vertices"])
    if kind == "h_polytope":
        return h_vertices(shape)
    if kind == "zonotope":
        return zonotope_vertices(shape)
    if kind == "directional_ellipsoid":
        return ellipse_outline(shape)
    raise ValueError(f"Unknown recorded shape kind {kind}")


def projection_bounds(reference, projection):
    indices = reference["projection_pairs"][projection]
    scale = reference["finite_game"]["state_scale"]
    states = [state for layer in reference["layers"] for state in layer["finite_states_scaled"]]
    xs = [state[indices[0]] / scale for state in states]
    ys = [state[indices[1]] / scale for state in states]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xpad = max((xmax - xmin) * 0.08, 0.1)
    ypad = max((ymax - ymin) * 0.08, 0.1)
    return xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad


def map_point(point, projection, bounds):
    x, y = point
    x0 = 75 if projection == 0 else 665
    xmin, xmax, ymin, ymax = bounds
    return x0 + (x - xmin) * 520 / (xmax - xmin), 525 - (y - ymin) * 390 / (ymax - ymin)


def path(points, projection, bounds):
    mapped = [map_point(point, projection, bounds) for point in points]
    if not mapped:
        return ""
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in mapped) + " Z"


def build_svg(source: str, run: dict, reference: dict, source_figure: dict) -> str:
    paths = []
    for projection_index, projection in enumerate(run["projections"]):
        panel_paths = []
        indices = reference["projection_pairs"][projection_index]
        fixed_winning = hull([(state[indices[0]], state[indices[1]])
                              for state in source_figure["robust_backward_layers"][-1]])
        feedback_winning = hull([(state[indices[0]], state[indices[1]])
                                 for state in source_figure["feedback_backward_layers"][-1]])
        bounds = projection_bounds(reference, projection_index)
        panel_paths.append(
            f'<path d="{path(fixed_winning, projection_index, bounds)}" fill="none" '
            'stroke="#f4a261" stroke-width="2.1" stroke-dasharray="4 3" '
            'stroke-linejoin="round" opacity="0.95"/>'
        )
        panel_paths.append(
            f'<path d="{path(feedback_winning, projection_index, bounds)}" fill="none" '
            'stroke="#c77dff" stroke-width="2.1" stroke-dasharray="2 3" '
            'stroke-linejoin="round" opacity="0.95"/>'
        )
        for method in projection["methods"]:
            method_id = method["method"]
            points = vertices(method["result"]["shape"])
            panel_paths.append(
                f'<path d="{path(points, projection_index, bounds)}" fill="none" '
                f'stroke="{COLORS[method_id]}" stroke-width="2.4" '
                f'stroke-dasharray="{ "8 4" if method_id != "exact-polytope-quickhull" else "none"}" '
                f'stroke-linejoin="round" opacity="0.95"/>'
            )
        panel_x = 75 if projection_index == 0 else 665
        paths.append(
            f'<svg x="{panel_x}" y="135" width="520" height="390" '
            f'viewBox="{panel_x} 135 520 390" preserveAspectRatio="none" overflow="hidden">'
            + "".join(panel_paths) + "</svg>"
        )
    legend = []
    positions = [75, 315, 535, 790, 1020]
    for (method_id, label), x in zip(LABELS.items(), positions):
        dash = "" if method_id == "exact-polytope-quickhull" else ' stroke-dasharray="8 4"'
        legend.append(
            f'<line x1="{x}" y1="711" x2="{x + 28}" y2="711" '
            f'stroke="{COLORS[method_id]}" stroke-width="3"{dash}/>'
            f'<text x="{x + 36}" y="716" fill="#d2dce1" font-family="sans-serif" '
            f'font-size="12">{html.escape(label)}</text>'
        )
    legend.extend([
        '<line x1="75" y1="740" x2="103" y2="740" stroke="#f4a261" stroke-width="3" stroke-dasharray="4 3"/>'
        '<text x="111" y="745" fill="#d2dce1" font-family="sans-serif" font-size="12">Stage-3 minimax-threshold target-node hull</text>',
        '<line x1="535" y1="740" x2="563" y2="740" stroke="#c77dff" stroke-width="3" stroke-dasharray="2 3"/>'
        '<text x="571" y="745" fill="#d2dce1" font-family="sans-serif" font-size="12">Stage-3 feedback winning-node hull</text>',
    ])
    svg = source.replace('viewBox="0 0 1260 700"', 'viewBox="0 0 1260 770"')
    svg = svg.replace(
        "Two points on parallel lines: forward reachability and robust backward sets",
        "TwoPoints reachability, backward-winning intersections, and projected approximations",
    )
    svg = svg.replace(
        "Forward reachable polytopes for each finite control prefix, robust backward winning nodes, their intersections, and one minimax trajectory, shown in both point phase planes.",
        "Forward reachable polytopes by control prefix; legacy robust-backward and finite-feedback winning nodes are marked, with both trajectories and terminal projected hull approximations in the two phase planes.",
    )
    svg = svg.replace("exact scale-2000 state graph",
                      "exact scale-2000 integer replay; binary64 geometry")
    svg = svg.replace("Fixed-plan forward ∩ backward vertices",
                      "Legacy threshold-winning nodes ∩ forward graph")
    svg = svg.replace("</svg>", "\n".join(paths + legend) + "</svg>")
    return svg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-svg", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--source-figure-data", type=Path, required=True)
    parser.add_argument("--output-svg", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    source_figure = json.loads(args.source_figure_data.read_text(encoding="utf-8"))
    source = args.source_svg.read_text(encoding="utf-8")
    args.output_svg.parent.mkdir(parents=True, exist_ok=True)
    args.output_svg.write_text(build_svg(source, run, reference, source_figure), encoding="utf-8")


if __name__ == "__main__":
    main()

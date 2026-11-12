#!/usr/bin/env python3
"""Render the source-bound analytic action-cloud query for four set routes."""

import itertools
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = ROOT / "attempts"
NAMES = ("box", "zonotope", "parallelotope", "ellipsoid")


def convex_hull(points):
    points = sorted(set(map(tuple, points)))
    if len(points) <= 1:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def cloud_for(name):
    response = json.loads((ATTEMPTS / f"native-multiaction-parent-cloud-{name}-20261111-f84" / "response.json").read_text())
    if response["status"] != "accepted":
        raise RuntimeError(f"{name} route did not accept: {response['status']}")
    receipt = response["graph_receipt"]
    cloud = next(item for item in receipt["action_cloud_envelopes"]
                 if item["parent_stage"] == 0 and item["parent_node_id"] == 0)
    return response, cloud


def draw_shape(ax, shape):
    kind = shape["representation"]
    if kind == "box":
        lo, hi = shape["lower"], shape["upper"]
        ax.add_patch(Rectangle((lo[0], lo[1]), hi[0] - lo[0], hi[1] - lo[1],
                               facecolor="#8ecae6", edgecolor="#126782", alpha=0.35, lw=2))
    elif kind == "parallelotope":
        frame = shape["frame"]
        corners = []
        for y0, y1 in itertools.product((shape["lower"][0], shape["upper"][0]),
                                         (shape["lower"][1], shape["upper"][1])):
            corners.append([sum(frame[i][j] * (y0, y1)[j] for j in range(2)) for i in range(2)])
        ax.add_patch(Polygon(convex_hull(corners), closed=True, facecolor="#8ecae6",
                             edgecolor="#126782", alpha=0.35, lw=2))
    elif kind == "ellipsoid":
        ax.add_patch(Ellipse(shape["center"], 2 * shape["radii"][0], 2 * shape["radii"][1],
                             facecolor="#8ecae6", edgecolor="#126782", alpha=0.35, lw=2))
    elif kind == "zonotope":
        center, generators = shape["center"], shape["generators"]
        columns = list(zip(*generators))
        corners = []
        for signs in itertools.product((-1, 1), repeat=len(columns)):
            corners.append([center[row] + sum(sign * columns[j][row] for j, sign in enumerate(signs))
                            for row in range(2)])
        ax.add_patch(Polygon(convex_hull(corners), closed=True, facecolor="#8ecae6",
                             edgecolor="#126782", alpha=0.35, lw=2))
    else:
        raise ValueError(f"unknown shape {kind}")


def main():
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    selected_control = None
    selected_states = None
    for ax, name in zip(axes.flat, NAMES):
        response, cloud = cloud_for(name)
        draw_shape(ax, cloud["selected_outer_shape"])
        children = [witness["child_state"] for witness in cloud["action_child_witnesses"]]
        ax.scatter([point[0] for point in children], [point[1] for point in children],
                   color="#d1495b", edgecolor="white", linewidth=0.7, s=38, zorder=3,
                   label="authored action children")
        selected = response["selected_plan"]
        states = selected["states"]
        ax.plot([state[0] for state in states], [state[1] for state in states],
                color="#22223b", marker="o", linestyle="--", lw=1.7, ms=4,
                label="selected MPC trajectory")
        selected_index = response["selected_edges"][0]["action_index"]
        selected_child = next(w["child_state"] for w in cloud["action_child_witnesses"]
                              if w["action_index"] == selected_index)
        ax.scatter([selected_child[0]], [selected_child[1]], marker="*", s=190,
                   color="#ffb703", edgecolor="#6b4f00", linewidth=0.8, zorder=4,
                   label="first selected action")
        selected_control = selected["controls"][0]
        selected_states = states
        ax.set_title(f"{name.title()} · {len(children)} authored children · stage 0→1")
        ax.set_xlabel("state 1")
        ax.set_ylabel("state 2")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.22)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle("Whole authored-action clouds and selected finite-action MPC path\n"
                 f"Selected first control: {selected_control}; states: {selected_states}", fontsize=13)
    out = Path(__file__).parent
    fig.savefig(out / "analytic-action-clouds.svg")
    fig.savefig(out / "analytic-action-clouds.png", dpi=170)
    (out / "analytic-action-clouds.html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Analytic action-cloud geometry</title><main>"
        "<h1>Whole authored-action clouds</h1>"
        "<p>Source-bound analytic two-state task, stages 0–2. Each panel shows the actual selected numerical set shape, "
        "all five recomputed authored action children, and the retained-graph MPC path. The set is a numerical outer "
        "approximation; this illustration does not claim global optimality.</p>"
        "<img src='analytic-action-clouds.svg' alt='Four selected set shapes with action children and MPC trajectory'>"
        "</main></html>\n")
    plt.close(fig)


if __name__ == "__main__":
    main()

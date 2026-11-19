"""Render the fixture geometry, actual feedback history and paired deployment totals."""

import argparse
import json
from fractions import Fraction as Q
from pathlib import Path

import exact_regions as geometry
import matplotlib.pyplot as plt
from crossover_reference import polygon_rows
from explicit_double_integrator import intersect
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def draw_set(ax, poly, **style):
    pts = list(poly)
    if len(pts) > 2:
        ax.fill(*zip(*(pts + [pts[0]]), strict=True), **style)
    elif pts:
        ax.plot(
            *zip(*pts, strict=True),
            color=style.get("edgecolor"),
            linewidth=2,
            marker="o" if len(pts) == 1 else None,
        )


def draw(ref, workload, raw_path, summary, dest):
    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": "mpc-crossover-1084"}
    )
    colors = ["#453781", "#33638d", "#21918c", "#5ec962"]
    horizons = {stage["remaining"]: stage for stage in ref["horizons"]}
    with raw_path.open() as stream:
        deployment = next(
            r
            for line in stream
            if (r := json.loads(line)).get("type") == "deployment"
            and r["controller"] == "explicit"
            and r["repetition"] == 0
        )
    episode = deployment["data"]["episodes"][0]
    x0 = workload["deployment_states"][0]
    if episode["steps"][0]["observed"] != x0 or episode["status"] != "completed":
        raise ValueError("illustrated rollout is missing")
    path = [s["observed"] for s in episode["steps"]]
    p, v = path[-1]
    path.append([p + v, v + episode["steps"][-1]["action"]])
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.5, 5.2), layout="constrained")
    current = [tuple(map(Q, x0))]
    for k, color in enumerate(colors):
        stage = 3 - k
        backward = (
            geometry.vertices([*geometry.X, *geometry.target()])
            if stage == 0
            else [tuple(map(Q, p)) for p in horizons[stage]["feasible_polygon"]]
        )
        intersection = intersect(current, polygon_rows(backward))
        draw_set(ax, backward, edgecolor=color, facecolor="none", linestyle="--", linewidth=1)
        draw_set(ax, current, edgecolor=color, facecolor=color, alpha=0.17, linewidth=1.7)
        draw_set(ax, intersection, edgecolor=color, facecolor="none", hatch="///", linewidth=1)
        if k < 3:
            endpoints = [(p + v, v + u) for p, v in current for u in (-1, 1)]
            current = geometry.hull(intersect(geometry.hull(endpoints), geometry.X))
    ax.plot(*zip(*path, strict=True), "o-", color="#181818", lw=2, ms=4)
    for k, (p, v) in enumerate(path):
        ax.annotate(str(k), (p, v), xytext=(4, 6), textcoords="offset points")
    ax.set_title("Forward and backward feasible sets")
    ax.legend(
        handles=[
            Patch(facecolor="#8bbcb1", label="Forward from the initial point"),
            Line2D([], [], color="#42797e", ls="--", label="Backward to terminal target"),
            Patch(
                facecolor="white", edgecolor="#42797e", hatch="///", label="Same-stage intersection"
            ),
            Line2D([], [], color="#181818", marker="o", label="Optimal trajectory (stage 0–3)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.23),
        ncol=2,
        fontsize=8,
    )
    cells = horizons[3]["cells"]
    polygons = [[tuple(map(lambda v: float(Q(v)), p)) for p in c["vertices"]] for c in cells]
    values = []
    for poly, c in zip(polygons, cells, strict=True):
        a, b, d = map(lambda v: float(Q(v)), c["controls"][0])
        p, v = map(lambda z: sum(z) / len(z), zip(*poly, strict=True))
        values.append(a * p + b * v + d)
    coll = PolyCollection(
        polygons, edgecolors="#5d686d", linewidths=0.9, cmap="coolwarm", clim=(-1, 1)
    )
    coll.set_array(values)
    bx.add_collection(coll)
    samples = [
        q["state"] for q in workload["queries"] if q["remaining"] == 3 and q["expected"] is not None
    ]
    bx.scatter(
        *zip(*samples, strict=True), s=8, color="#1f2224", label="Checked feasible states", zorder=3
    )
    misses = [
        q["state"] for q in workload["queries"] if q["remaining"] == 3 and q["expected"] is None
    ]
    bx.scatter(
        *zip(*misses, strict=True),
        s=48,
        marker="x",
        color="#782d14",
        linewidths=2,
        label="Checked infeasible states",
        zorder=4,
    )
    bx.plot(
        *zip(*path, strict=True),
        "o-",
        color="#111111",
        markerfacecolor="white",
        lw=2,
        ms=4,
        label="Shrinking-horizon trajectory",
        zorder=5,
    )
    bx.legend(loc="upper center", bbox_to_anchor=(0.5, -0.53), fontsize=8, ncol=2)
    bx.set_title("First control for three remaining steps")
    fig.colorbar(
        coll, ax=bx, orientation="horizontal", shrink=0.85, label="Acceleration at region centroid"
    )
    for panel in (ax, bx):
        panel.set(
            xlim=(-3.15, 3.15),
            ylim=(-2.15, 2.15),
            aspect="equal",
            xlabel="Position",
            ylabel="Velocity",
        )
        panel.grid(alpha=0.15)
    bx.set_xlim(-3.15, max(p for p, _ in misses) + 0.3)
    fig.savefig(dest / "feedback-geometry.svg", metadata={"Date": None})
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.6, 4.3), layout="constrained")
    for method, color in (("explicit", "#23756d"), ("online", "#965129")):
        rows = summary["sizes"]
        counts = [r["count"] for r in rows]
        values = [r[method]["total_ns"] for r in rows]
        ax.fill_between(
            counts,
            [v["min"] / 1e6 for v in values],
            [v["max"] / 1e6 for v in values],
            color=color,
            alpha=0.16,
        )
        ax.plot(
            counts,
            [v["median"] / 1e6 for v in values],
            "o-",
            color=color,
            label=method.capitalize() + " MPC",
        )
    ax.set(
        xscale="log",
        yscale="log",
        xlabel="Trajectories per deployment",
        ylabel="Total elapsed time (ms)",
        title="Controller setup and closed-loop decisions",
    )
    ax.set_xticks(counts, labels=list(map(str, counts)))
    ax.legend()
    ax.grid(alpha=0.18)
    fig.savefig(dest / "deployment-time.svg", metadata={"Date": None})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "workload", "raw", "summary", "destination"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    draw(
        json.loads(args.reference.read_text()),
        json.loads(args.workload.read_text()),
        args.raw,
        json.loads(args.summary.read_text()),
        args.destination,
    )

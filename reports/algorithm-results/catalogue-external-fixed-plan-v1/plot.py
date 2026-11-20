"""Plot the two queue coordinates relative to the corresponding nominal stage."""
import json
from itertools import product
from pathlib import Path

from matplotlib import rcParams
import matplotlib.pyplot as plt
import numpy as np


def hull(points):
    points = sorted({tuple(point) for point in points})

    def chain(points):
        result = []
        for x in points:
            while len(result) >= 2:
                p, q = result[-2:]
                if (q[0] - p[0]) * (x[1] - p[1]) > (q[1] - p[1]) * (x[0] - p[0]):
                    break
                result.pop()
            result.append(x)
        return result

    if len(points) <= 1:
        return points
    return chain(points)[:-1] + chain(reversed(points))[:-1]


def corners(lower, upper):
    return np.asarray(list(product(*zip(lower, upper, strict=True))))


def outline(family, stage, result):
    if family == "polytope":
        return hull([point[:2] for point in stage["points"]])
    if family == "box":
        return hull(corners(stage["lower"][:2], stage["upper"][:2]))
    if family == "parallelotope":
        frame = np.asarray(result["frame"]["row_major"]).reshape(3, 3)
        return hull((corners(stage["lower"], stage["upper"]) @ frame.T)[:, :2])
    center = np.asarray(stage["center"][:2])
    if family == "ellipsoid":
        angles = np.linspace(0, 2 * np.pi, 257)
        return center + np.column_stack((np.cos(angles), np.sin(angles))) * stage["radii"][:2]
    record = stage["generators"]
    generators = np.asarray(record["row_major"]).reshape(3, record["columns"])[:2]
    polygon = [center]
    for coefficient in generators.T:
        polygon = hull([vertex + coefficient * sign for vertex in polygon for sign in (-1, 1)])
    return polygon


def render(records):
    case = next(row for row in records if row["model_id"] == "catalogue-2026/model-1/1")
    colors = {
        "ellipsoid": ("Ellipsoid", "#b96cc2"),
        "box": ("Box", "#c28019"),
        "parallelotope": ("Parallelotope", "#325eed"),
        "zonotope": ("Zonotope", "#12836a"),
        "polytope": ("Enumerated convex hull", "#22252d"),
    }
    reference = case["outcomes"]["polytope"]["stages"]
    step_scale = np.asarray([1.0, 0.1])
    fig, axes = plt.subplots(1, 3, figsize=(10.4, 4.3), sharex=True, sharey=True)
    for k, ax in enumerate(axes):
        nominal = np.asarray(reference[k]["points"][0][:2])
        for family, (label, color) in colors.items():
            result = case["outcomes"][family]
            polygon = np.asarray(outline(family, result["stages"][k], result)) - nominal
            polygon /= step_scale
            closed = np.vstack((polygon, polygon[0]))
            ax.plot(*closed.T, lw=1.5, color=color, label=label,
                    linestyle="--" if family in {"box", "zonotope"} else "-",
                    marker="o" if k == 0 and family == "polytope" else None)
        ax.set_title(f"Stage {k}")
        ax.set_aspect("equal")
        ax.set_xlabel("Queue 1 deviation / 1")
        ax.axhline(0, color="#b8bdca", lw=0.6)
        ax.axvline(0, color="#b8bdca", lw=0.6)
    axes[0].set_ylabel("Queue 2 deviation / 0.1")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("IP/SDN queues under one fixed plan")
    fig.subplots_adjust(left=.09, bottom=.19, right=.98, top=.84, wspace=.11)
    rcParams["svg.hashsalt"] = "csl-catalogue-external-fixed-plan-v1"
    fig.savefig("queue-outer-projections.svg", metadata={"Date": None})
    fig.savefig("queue-outer-projections.png", dpi=180)


if __name__ == "__main__":
    render(list(map(json.loads, Path("records.jsonl").read_text().splitlines())))

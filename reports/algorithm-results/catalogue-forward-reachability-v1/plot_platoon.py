"""Plot corner images from exact dynamics on the final car’s invariant block."""

from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from check_support import load_records

ROOT = Path(__file__).parent
MODEL = "catalogue-2026/model-26/1"


def hull(points):
    def chain(points):
        result = []
        for point in points:
            while len(result) > 1:
                a, b = result[-2:]
                cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
                    point[0] - a[0]
                )
                if cross > 0:
                    break
                result.pop()
            result.append(point)
        return result

    ordered = sorted(set(points))
    if len(ordered) <= 1:
        return ordered
    return chain(ordered)[:-1] + chain(reversed(ordered))[:-1]


def platoon_corners():
    records = load_records()[MODEL]
    rows = (27, 28, 29)
    control = 9
    A, B = records["A"], records["B"]
    assert all(not value for (i, j), value in A.items() if i in rows and j not in rows)
    assert all(not value for (i, j), value in B.items() if i in rows and j != control)
    x0 = [records["x0"][i, 0] for i in rows]
    w = records.get("nominal_w", {})
    drift = [
        sum(records["G"][i, j] * value for (j, _), value in w.items()) for i in rows
    ]
    for stage in range(4):
        corners = []
        for inputs in product((-1, 1), repeat=stage):
            state = x0
            for command in inputs:
                state = [
                    drift[k]
                    + B[i, control] * command
                    + sum(A[i, j] * value for j, value in zip(rows, state, strict=True))
                    for k, i in enumerate(rows)
                ]
            corners.append(tuple(map(float, state[:2])))
        yield corners


def draw():
    fig, (physical, relative) = plt.subplots(
        1, 2, figsize=(10.6, 4.6), layout="constrained"
    )
    fig.suptitle("Ten-car platoon · projected forward reachable sets", weight="bold")
    palette = ("#222735", "#227e83", "#8052ac", "#c85128")
    physical.set_title("Physical coordinates", loc="left")
    physical.set_xlabel("Car 10 position (m)")
    physical.set_ylabel("Car 10 velocity (m/s)")
    relative.set_title("Relative to each stage centre", loc="left")
    relative.set_xlabel("Position deviation (m)")
    relative.set_ylabel("Velocity deviation (m/s)")
    for axis in (physical, relative):
        axis.grid(alpha=0.2)
    for k, (color, corners) in enumerate(zip(palette, platoon_corners(), strict=True)):
        points = hull(corners)
        xs, ys = zip(*points, strict=True)
        centre_x, centre_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        for axis, x0, y0 in ((physical, 0.0, 0.0), (relative, centre_x, centre_y)):
            x = [value - x0 for value in (*xs, xs[0])]
            y = [value - y0 for value in (*ys, ys[0])]
            if len(points) > 2:
                axis.fill(x, y, color=color, alpha=0.21, lw=0)
            axis.plot(
                x,
                y,
                color=color,
                lw=2,
                marker="o" if len(points) == 1 else None,
                label="Initial state" if k == 0 else f"Stage {k}",
            )
    physical.legend(frameon=False, loc="upper left", ncols=2)
    fig.savefig(ROOT / "platoon-forward.svg", metadata={"Date": None})
    fig.savefig(ROOT / "platoon-forward.png", dpi=150, metadata={"Creation Time": None})


if __name__ == "__main__":
    matplotlib.rcParams["svg.hashsalt"] = "csl-catalogue-forward-v1"
    draw()

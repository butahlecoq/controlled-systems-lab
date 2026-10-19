"""Audit terminal polygon geometry in a hash-identified private MATLAB FIG.

Requires SciPy only when reading the private FIG. The geometry calculations use
exact rationals for the binary64 coordinates saved in that file. This does not
certify the historical generator or nonlinear reachable sets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path


FIGURE_SHA256 = "95b9d6a500361a832e6067163e2262fb0e04e2b17f88b83a1af13293c4c728c5"
COMPANION_SHA256 = {
    "5a6aeb8a43bf1af1a40c60e34072ce3df3e01cdac1ce4119e76e52cbe83eaf43",
    "3c6ab1c8511ca5959d723d600f3d7ab969786f5dd4fc4179480f01ee9ed05d38",
}
Point = tuple[Fraction, Fraction]


def convex_hull(points: list[Point]) -> list[Point]:
    ordered = sorted(set(points))
    if len(ordered) < 3:
        raise ValueError("polygon needs at least three distinct points")

    def turn(a: Point, b: Point, c: Point) -> Fraction:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    lower: list[Point] = []
    upper: list[Point] = []
    for point in ordered:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        raise ValueError("polygon is collinear")
    return hull


def area(hull: list[Point]) -> Fraction:
    return sum(
        (p[0] * hull[(i + 1) % len(hull)][1]
         - p[1] * hull[(i + 1) % len(hull)][0]
         for i, p in enumerate(hull)),
        Fraction(),
    ) / 2


def violations(inner: list[Point], outer: list[Point]) -> int:
    """Count inner vertices outside a counterclockwise convex outer hull."""
    return sum(
        any(
            (outer[(i + 1) % len(outer)][0] - outer[i][0])
            * (point[1] - outer[i][1])
            - (outer[(i + 1) % len(outer)][1] - outer[i][1])
            * (point[0] - outer[i][0]) < 0
            for i in range(len(outer))
        )
        for point in inner
    )


def saved_patches(path: Path, allowed_hashes: set[str]) -> list[list[Point]]:
    if hashlib.sha256(path.read_bytes()).hexdigest() not in allowed_hashes:
        raise ValueError("private FIG SHA-256 mismatch")
    import numpy as np
    from scipy.io import loadmat

    root = loadmat(path, squeeze_me=True, struct_as_record=False)["hgS_070000"]
    patches: list[list[Point]] = []

    def visit(value: object) -> None:
        nodes = value.flat if isinstance(value, np.ndarray) else (
            value if isinstance(value, (list, tuple)) else (value,)
        )
        for node in nodes:
            if not hasattr(node, "_fieldnames"):
                continue
            if getattr(node, "type", None) == "patch":
                properties = getattr(node, "properties", None)
                if properties is not None and hasattr(properties, "Vertices"):
                    vertices = np.asarray(properties.Vertices)
                    if vertices.ndim == 2 and vertices.shape[0] >= 2:
                        if vertices.shape[1] != 3 or not np.all(np.isfinite(vertices)) or np.any(vertices[:, 2] != 0):
                            raise ValueError("unexpected saved patch geometry")
                        patches.append([
                            (Fraction.from_float(float(x)), Fraction.from_float(float(y)))
                            for x, y in vertices[:, :2]
                        ])
            visit(getattr(node, "children", ()))

    visit(root)
    return patches


def audit(path: Path, companion: Path) -> dict:
    patches = saved_patches(path, {FIGURE_SHA256})
    companion_patches = saved_patches(companion, COMPANION_SHA256)
    if len(patches) != 240:
        raise ValueError("expected two 60-stage patch pairs")
    if len(companion_patches) != 120 or companion_patches != patches[:120]:
        raise ValueError("companion FIG does not match the first 60-stage pair")
    for stage in range(60):
        first_nonlinear = patches[2 * stage]
        second_nonlinear = patches[120 + 2 * stage]
        second_linear = patches[121 + 2 * stage]
        if first_nonlinear != second_nonlinear:
            raise ValueError("nonlinear plotted vertices differ between stage groups")
        if len(first_nonlinear) != 2 * (stage + 1) or len(second_linear) != 2 * (stage + 1):
            raise ValueError("unexpected stagewise plotted vertex count")
    indices = {
        "nonlinear_plot_first": 118,
        "linear_16": 119,
        "nonlinear_plot_second": 238,
        "linear_120": 239,
    }
    hulls = {name: convex_hull(patches[index]) for name, index in indices.items()}
    if hulls["nonlinear_plot_first"] != hulls["nonlinear_plot_second"]:
        raise ValueError("saved nonlinear terminal polygon differs between groups")
    expected_counts = {"nonlinear_plot_first": 120, "linear_16": 16, "linear_120": 120}
    if {name: len(hulls[name]) for name in expected_counts} != expected_counts:
        raise ValueError("unexpected terminal polygon vertex counts")
    with localcontext() as context:
        context.prec = 40
        areas = {
            name: str(Decimal(area(hulls[name]).numerator) / Decimal(area(hulls[name]).denominator))
            for name in expected_counts
        }
    return {
        "schema": "l05-saved-figure-audit-v1",
        "figure_sha256": FIGURE_SHA256,
        "companion_figure_sha256": hashlib.sha256(companion.read_bytes()).hexdigest(),
        "patch_count": len(patches),
        "paired_stages": 60,
        "nonlinear_plots_match_at_every_stage": True,
        "terminal_patches_zero_based": indices,
        "vertex_counts": expected_counts,
        "areas_of_stored_binary64_hulls": areas,
        "hull_vertex_violations": {
            "linear_16_outside_linear_120": violations(hulls["linear_16"], hulls["linear_120"]),
            "linear_120_outside_linear_16": violations(hulls["linear_120"], hulls["linear_16"]),
            "linear_120_outside_nonlinear_plot": violations(hulls["linear_120"], hulls["nonlinear_plot_first"]),
            "nonlinear_plot_outside_linear_120": violations(hulls["nonlinear_plot_first"], hulls["linear_120"]),
        },
        "scope": "exact for saved binary64 plotted convex polygons; no all-history nonlinear enclosure claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure", type=Path, required=True, help="private Buryatia 4.fig")
    parser.add_argument("--companion", type=Path, required=True, help="private Buryatia 1.fig")
    parser.add_argument("--output", type=Path, help="write derived summary JSON, never source vertices")
    args = parser.parse_args()
    if args.output and args.output.resolve() in {args.figure.resolve(), args.companion.resolve()}:
        parser.error("output must not overwrite a private FIG source")
    result = audit(args.figure, args.companion)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(serialized.encode("utf-8"))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()

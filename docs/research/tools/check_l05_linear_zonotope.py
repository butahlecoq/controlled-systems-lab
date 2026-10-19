"""Compare a source-bound linear control zonotope with saved L05 plot vertices.

The control zonotope is built from propagated generators, independently of the
archive's vertex-branching and pruning functions. This is a floating-point
source-association check, not a certified historical or nonlinear enclosure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .check_l05_saved_figures import (
    FIGURE_SHA256,
    convex_hull,
    saved_patches,
    violations,
)


SOURCE_SHA256 = "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"
MATCH_TOLERANCE = 1e-12
Vector = tuple[float, float]
Matrix = tuple[Vector, Vector]


def matvec(matrix: Matrix, vector: Vector) -> Vector:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1],
    )


def zonotope_vertices(center: Vector, generators: list[Vector]) -> list[Vector]:
    """Return the 2D zonotope boundary by traversing its sorted edge vectors."""
    oriented = [
        generator if generator[1] > 0 or (generator[1] == 0 and generator[0] >= 0)
        else (-generator[0], -generator[1])
        for generator in generators
    ]
    oriented.sort(key=lambda vector: math.atan2(vector[1], vector[0]))
    x = center[0] - sum(vector[0] for vector in oriented)
    y = center[1] - sum(vector[1] for vector in oriented)
    vertices: list[Vector] = []
    for sign, sequence in ((1, oriented), (-1, oriented)):
        for vector in sequence:
            vertices.append((x, y))
            x += sign * 2 * vector[0]
            y += sign * 2 * vector[1]
    return vertices


def candidate_stages() -> list[list[Vector]]:
    """Reconstruct the hash-gated Volterra candidate's frozen linear maps."""
    a, c, e = 0.9, 0.8, 0.85
    b, d = a / 300, c / 400
    step = (2 * math.pi / math.sqrt(a * c)) / 60
    reference: Vector = (410, 300)
    center: Vector = (1, 2)
    generators: list[Vector] = []
    stages: list[list[Vector]] = []
    for _ in range(60):
        x, y = reference
        reference = (
            x + step * (a * x - b * x * y),
            y + step * (-c * y + d * x * y),
        )
        matrix: Matrix = (
            (1 + step * a - step * b * reference[1], -step * b * reference[0]),
            (step * d * reference[1], 1 - step * c + step * d * reference[0]),
        )
        center = matvec(matrix, center)
        generators = [matvec(matrix, generator) for generator in generators]
        generators.append((step * e * 0.3, 0.0))
        stages.append(zonotope_vertices(center, generators))
    return stages


def vertex_set_distance(first: list[Vector], second: list[Vector]) -> float:
    """Symmetric nearest-vertex distance; no polygon Hausdorff claim."""
    return max(
        max(min(math.dist(point, other) for other in second) for point in first),
        max(min(math.dist(point, other) for other in first) for point in second),
    )


def audit(source: Path, figure: Path) -> dict:
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("candidate source SHA-256 mismatch")
    patches = saved_patches(figure, {FIGURE_SHA256})
    if len(patches) != 240:
        raise ValueError("expected two 60-stage patch pairs")
    if patches[1] != patches[121]:
        raise ValueError("first-stage linear segments differ between groups")
    stages = candidate_stages()
    errors: list[float] = []
    modified_outside_general: list[int] = []
    general_outside_nonlinear: list[int] = []
    modified_outside_nonlinear: list[int] = []
    nonlinear_outside_general: list[int] = []
    for index, vertices in enumerate(stages):
        saved_general = patches[121 + 2 * index]
        saved_floats = [(float(x), float(y)) for x, y in saved_general]
        if len(vertices) != 2 * (index + 1) or len(saved_floats) != len(vertices):
            raise ValueError(f"unexpected linear vertex count at stage {index + 1}")
        error = vertex_set_distance(vertices, saved_floats)
        if not math.isfinite(error) or error > MATCH_TOLERANCE:
            raise ValueError(f"candidate linear plot mismatch at stage {index + 1}: {error}")
        errors.append(error)
        if index == 0:
            continue  # The first-stage saved plots are segments, not polygons.
        modified = convex_hull(patches[1 + 2 * index])
        general = convex_hull(saved_general)
        nonlinear = convex_hull(patches[2 * index])
        stage = index + 1
        if violations(modified, general):
            modified_outside_general.append(stage)
        if violations(general, nonlinear):
            general_outside_nonlinear.append(stage)
        if violations(modified, nonlinear):
            modified_outside_nonlinear.append(stage)
        if violations(nonlinear, general):
            nonlinear_outside_general.append(stage)
    return {
        "schema": "l05-linear-zonotope-audit-v1",
        "candidate_source_sha256": SOURCE_SHA256,
        "figure_sha256": FIGURE_SHA256,
        "stages": len(stages),
        "vertex_set_distance_kind": "symmetric nearest vertex Euclidean distance in plotted coordinates",
        "maximum_vertex_set_distance": max(errors),
        "matching_tolerance": MATCH_TOLERANCE,
        "stage_range_for_polygon_inclusion": [2, 60],
        "first_stage_linear_segments_match": True,
        "modified_outside_general_stages": modified_outside_general,
        "general_outside_nonlinear_plot_stages": general_outside_nonlinear,
        "modified_outside_nonlinear_plot_stages": modified_outside_nonlinear,
        "nonlinear_plot_outside_general_stages": nonlinear_outside_general,
        "scope": "candidate linear map and saved binary64 plotted hulls only; no historical-generator or all-history nonlinear-enclosure claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="private Volterra.m candidate")
    parser.add_argument("--figure", type=Path, required=True, help="private Buryatia 4.fig")
    parser.add_argument("--output", type=Path, help="write derived JSON, never source vertices")
    args = parser.parse_args()
    if args.output and args.output.resolve() in {args.source.resolve(), args.figure.resolve()}:
        parser.error("output must not overwrite a private source")
    result = audit(args.source, args.figure)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(serialized.encode("utf-8"))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()

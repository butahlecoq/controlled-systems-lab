"""Reconstruct a hash-identified 4D candidate and compare saved L05 projections.

Requires NumPy and SciPy for the private FIG and floating convex-hull audit.
The output contains aggregate derived values, never source vertex coordinates.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
from pathlib import Path


SOURCE_SHA256 = "f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a"
FIGURES = {
    "123": ("ddaf5dad21ed9c15383bbf4567ab8a947e451c9c125aa521db787f7692a2b49e", (0, 1, 2)),
    "234": ("0c89b1e178d3153413cb57a94daa33b31eaf0f03ec3a80120d41db8f54efc9d5", (1, 2, 3)),
    "124": ("cab103d50af80ea7ee7d0d4ab0c8c93a60140e232d4327f0f93ab22e7d23e64b", (0, 1, 3)),
}
MATCH_TOLERANCE = 1e-12


def source_hash(path: Path, expected: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError("private source SHA-256 mismatch")
    return digest


def candidate_endpoints():
    """Enumerate the source's 4^7 control-corner histories, plus 14 generators."""
    import numpy as np

    a, b, c = 0.15, -0.8, 0.25
    controls = np.array([[-1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [1.0, -1.0]])
    reference = np.array([1.0, 1.0, 1.0, 1.0])
    linear = np.array([[1.0, -1.0, 1.0, 1.0]])
    nonlinear = linear.copy()
    generators = []
    for _ in range(7):
        r1, r2, r3, r4 = reference
        sine1 = math.sin(math.radians(r1))
        cosine1 = math.cos(math.radians(r1))
        sine2 = math.sin(math.radians(r2))
        cosine2 = math.cos(math.radians(r2))
        matrix = np.array([
            [1.0, cosine2, 0.0, 0.0],
            [a, 1.0, 0.0, 0.0],
            [0.0, b, 1.0, 0.0],
            [0.0, 0.0, c, 1.0],
        ])
        input_matrix = np.array([
            [1.0 + 0.5 * cosine1, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ])
        next_linear = []
        next_nonlinear = []
        for control in controls:
            next_linear.append(linear @ matrix.T + control @ input_matrix.T)
            nonlinear_step = nonlinear @ matrix.T + control @ input_matrix.T
            nonlinear_step[:, 0] += sine1 * nonlinear[:, 0] * control[0]
            next_nonlinear.append(nonlinear_step)
        linear = np.vstack(next_linear)
        nonlinear = np.vstack(next_nonlinear)
        generators = [matrix @ generator for generator in generators]
        generators.extend((input_matrix[:, 0], input_matrix[:, 1]))
        reference = np.array([
            r1 + 0.5 * sine2 + (1.0 + 0.5 * cosine1) * 0.5,
            r2 + a * r1,
            r3 + b * r2,
            r4 + c * r3 + 0.5,
        ])
    return linear, nonlinear, generators


def generator_volume(generators) -> tuple[float, float, int]:
    """4D volume of sum [-g,g] = 16 times the sum of 4-minor magnitudes."""
    import numpy as np

    determinants = [
        abs(float(np.linalg.det(np.column_stack(columns))))
        for columns in itertools.combinations(generators, 4)
    ]
    return 16.0 * math.fsum(determinants), min(determinants), len(determinants)


def saved_3d_patches(path: Path, expected_hash: str):
    source_hash(path, expected_hash)
    import numpy as np
    from scipy.io import loadmat

    saved = loadmat(path, squeeze_me=True, struct_as_record=False)
    patches = []
    strings = set()

    def visit(value) -> None:
        if isinstance(value, str):
            if value.strip():
                strings.add(value.strip())
        elif isinstance(value, np.ndarray):
            for item in value.flat:
                visit(item)
        elif hasattr(value, "_fieldnames"):
            if getattr(value, "type", None) == "patch":
                vertices = np.asarray(getattr(value.properties, "Vertices", None))
                if vertices.ndim == 2 and len(vertices) >= 2:
                    if vertices.shape[1] != 3 or not np.all(np.isfinite(vertices)):
                        raise ValueError("unexpected saved 3D patch geometry")
                    patches.append(vertices)
            for field in value._fieldnames:
                if field != "Vertices":
                    visit(getattr(value, field))
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(saved["hgS_070000"])
    if len(patches) != 2:
        raise ValueError("expected two plotted 3D patches")
    releases = sorted({match.group(1) for text in strings
                       for match in re.finditer(r"MATLAB\\(R\d{4}[ab])", text)})
    return patches, strings, saved["__header__"].decode("ascii"), releases


def vertex_set_distance(first, second) -> float:
    from scipy.spatial import cKDTree

    return max(
        float(cKDTree(second).query(first)[0].max()),
        float(cKDTree(first).query(second)[0].max()),
    )


def audit(source: Path, figures: dict[str, Path]) -> dict:
    source_hash(source, SOURCE_SHA256)
    import numpy as np
    from scipy.spatial import ConvexHull, cKDTree

    linear, nonlinear, generators = candidate_endpoints()
    if linear.shape != (16384, 4) or nonlinear.shape != (16384, 4) or len(generators) != 14:
        raise ValueError("unexpected candidate enumeration size")
    linear_hull = ConvexHull(linear)
    nonlinear_hull = ConvexHull(nonlinear)
    volume_from_generators, minimum_minor, minor_count = generator_volume(generators)
    theoretical_vertices = 2 * sum(math.comb(13, k) for k in range(4))
    if len(linear_hull.vertices) != theoretical_vertices or minor_count != 1001:
        raise ValueError("unexpected linear zonotope combinatorics")
    if abs(linear_hull.volume - volume_from_generators) > 1e-7:
        raise ValueError("independent linear volume calculations disagree")
    if (round(linear_hull.volume, 2), len(nonlinear_hull.vertices), round(nonlinear_hull.volume, 2)) != (
        40808.17, 436, 47795.76,
    ):
        raise ValueError("candidate 4D rows do not match reported precision")

    projections = {}
    for key, (expected_hash, axes) in FIGURES.items():
        patches, strings, header, releases = saved_3d_patches(figures[key], expected_hash)
        labels = [f"x_{index + 1}" for index in axes]
        if not set(labels).issubset(strings):
            raise ValueError(f"saved {key} axis labels differ")
        saved_linear, saved_nonlinear = patches
        linear_projection = linear[:, axes]
        nonlinear_projection = nonlinear[:, axes]
        projected_hull = ConvexHull(nonlinear_projection)
        projected_vertices = nonlinear_projection[projected_hull.vertices]
        error = vertex_set_distance(saved_nonlinear, projected_vertices)
        linear_endpoint_error = float(cKDTree(linear_projection).query(saved_linear)[0].max())
        if len(saved_nonlinear) != len(projected_vertices) or error > MATCH_TOLERANCE:
            raise ValueError(f"saved {key} nonlinear plot mismatch")
        if linear_endpoint_error > MATCH_TOLERANCE:
            raise ValueError(f"saved {key} linear-associated vertices are not candidate endpoints")
        projections[key] = {
            "figure_sha256": expected_hash,
            "axes_one_based": [index + 1 for index in axes],
            "saved_nonlinear_vertices": len(saved_nonlinear),
            "candidate_nonlinear_projected_hull_vertices": len(projected_vertices),
            "nonlinear_vertex_set_distance": error,
            "saved_linear_associated_vertices": len(saved_linear),
            "linear_associated_to_candidate_endpoint_max_distance": linear_endpoint_error,
            "mat_file_header": header,
            "embedded_matlabroot_releases": releases,
        }

    return {
        "schema": "l05-dim4-candidate-audit-v1",
        "candidate_source_sha256": SOURCE_SHA256,
        "transitions": 7,
        "independent_controls_per_transition": 2,
        "endpoint_histories": len(linear),
        "linear": {
            "generators": len(generators),
            "theoretical_maximum_vertices": theoretical_vertices,
            "computed_hull_vertices": len(linear_hull.vertices),
            "computed_hull_volume": float(linear_hull.volume),
            "independent_generator_determinant_volume": volume_from_generators,
            "generator_4_minors": minor_count,
            "minimum_absolute_generator_4_minor": minimum_minor,
            "reported_row_at_printed_precision": {"vertices": 756, "volume": 40808.17},
        },
        "nonlinear_corner_history_hull": {
            "vertices": len(nonlinear_hull.vertices),
            "volume": float(nonlinear_hull.volume),
            "reported_row_at_printed_precision": {"vertices": 436, "volume": 47795.76},
        },
        "saved_3d_projections": projections,
        "current_candidate_script_third_projection_one_based": [1, 3, 4],
        "saved_third_projection_one_based": [1, 2, 4],
        "modified_4d_row_reproduced": False,
        "scope": "candidate full corner-history hulls and saved projections; no versioned historical generator, modified 4D row, physical coordinate map, or validated arithmetic claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="private Dim4.m candidate")
    parser.add_argument("--figure-123", type=Path, required=True, help="private 2.1.fig")
    parser.add_argument("--figure-234", type=Path, required=True, help="private 2.2.fig")
    parser.add_argument("--figure-124", type=Path, required=True, help="private 2.3.fig")
    parser.add_argument("--output", type=Path, help="write aggregate derived JSON")
    args = parser.parse_args()
    figures = {"123": args.figure_123, "234": args.figure_234, "124": args.figure_124}
    if args.output and args.output.resolve() in {args.source.resolve(), *(p.resolve() for p in figures.values())}:
        parser.error("output must not overwrite a private source")
    serialized = json.dumps(audit(args.source, figures), indent=2) + "\n"
    if args.output:
        args.output.write_bytes(serialized.encode("utf-8"))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()

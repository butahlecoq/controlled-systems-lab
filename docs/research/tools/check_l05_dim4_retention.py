"""Source-bound floating replay of the active L05 four-state hull filter.

The private MATLAB originals are read only and SHA-256 gated. The saved record
contains counts and distances, not private vertices or a historical run claim.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .check_l05_dim4_candidate import FIGURES, SOURCE_SHA256, saved_3d_patches, source_hash


CONVSM_SHA256 = "e178858e42d5f6174d032d9415b9b7412b2e32ca9aa1b9bfbed7b202db65eaa6"
SIMPLEX_SHA256 = "6f87f2c674519352f6801df60fe498a33ac091b79a5a6cbe76f0dcf4a20f6229"
CONTROLS = ((-1.0, -1.0), (1.0, 1.0), (-1.0, 1.0), (1.0, -1.0))


def simplex_hull_mod(points, column: int):
    """Translate the archived pivot/filter operations, including column order."""
    import numpy as np

    coordinates = points.T.copy()
    dimension, count = coordinates.shape
    sign = np.where(coordinates[:, column] >= 0.0, 1.0, -1.0)
    signed = coordinates * sign[:, None]
    tableau_source = np.vstack((signed, np.ones(count), signed.sum(axis=0) + 1.0))
    tableau = tableau_source.copy()
    basis_matrix = np.eye(dimension + 2)
    basis = np.full(dimension + 1, -1, dtype=int)
    epsilon = 1e-6
    pivots = 0

    while True:
        other = np.arange(count) != column
        if np.all(tableau[-1, other] <= epsilon):
            if abs(tableau[-1, column]) > epsilon:
                return points, pivots, True, 0

            basis_columns = basis[basis >= 0]
            preceding_basis = basis_columns[basis_columns >= column]
            candidates = tableau[:dimension + 1, :].copy()
            candidates[:, basis_columns] = np.nan
            deleted = np.flatnonzero(np.sum(np.abs(candidates), axis=0) < 1.0 + epsilon)
            discard = set(deleted) | set(preceding_basis)
            remaining = [index for index in range(count) if index not in discard]
            reordered = points[np.r_[preceding_basis, remaining]]
            return reordered, pivots, False, len(preceding_basis)

        objective = tableau[-1, :].copy()
        objective[column] = np.nan
        entering = int(np.nanargmax(objective))
        divisor = tableau[:dimension + 1, entering].copy()
        divisor[divisor < epsilon] = np.nan
        ratios = tableau[:dimension + 1, column] / divisor
        leaving = int(np.nanargmin(ratios))
        basis_matrix[:, leaving] = tableau_source[:, entering]
        tableau = np.linalg.solve(basis_matrix, tableau_source)
        basis[leaving] = entering
        pivots += 1
        if pivots > 10000:
            raise RuntimeError("archived simplex translation did not terminate")


def convsm_mod(points):
    """Replay the archived column traversal and return retained points/pivots."""
    column = 0
    pivots = 0
    while column < len(points):
        previous_size = len(points)
        points, step_pivots, vertex, promoted = simplex_hull_mod(points, column)
        pivots += step_pivots
        if not vertex and promoted == 0 and len(points) >= previous_size:
            raise RuntimeError("archived filter made no column progress")
        column += 1 if vertex else promoted
    return points, pivots


def candidate_stages():
    """Expand parent-major and four-corner-minor, as active Dim4.m does."""
    import numpy as np

    controls = np.asarray(CONTROLS)
    reference = np.array([1.0, 1.0, 1.0, 1.0])
    retained = np.array([[1.0, -1.0, 1.0, 1.0]])
    full = retained.copy()
    for stage in range(1, 8):
        r1, r2, r3, r4 = reference
        sine1 = math.sin(math.radians(r1))
        cosine1 = math.cos(math.radians(r1))
        sine2 = math.sin(math.radians(r2))
        cosine2 = math.cos(math.radians(r2))
        matrix = np.array([
            [1.0, cosine2, 0.0, 0.0],
            [0.15, 1.0, 0.0, 0.0],
            [0.0, -0.8, 1.0, 0.0],
            [0.0, 0.0, 0.25, 1.0],
        ])
        input_matrix = np.array([
            [1.0 + 0.5 * cosine1, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ])
        control_images = controls @ input_matrix.T
        generated = np.vstack([row @ matrix.T + control_images for row in retained])
        full = np.vstack([row @ matrix.T + control_images for row in full])
        retained, pivots = convsm_mod(generated)
        yield stage, len(generated), retained, full, pivots
        reference = np.array([
            r1 + 0.5 * sine2 + (1.0 + 0.5 * cosine1) * 0.5,
            r2 + 0.15 * r1,
            r3 - 0.8 * r2,
            r4 + 0.25 * r3 + 0.5,
        ])


def audit(source: Path, filter_source: Path, simplex_source: Path, figures: dict[str, Path]):
    import numpy as np
    from scipy.spatial import ConvexHull, cKDTree

    source_hash(source, SOURCE_SHA256)
    source_hash(filter_source, CONVSM_SHA256)
    source_hash(simplex_source, SIMPLEX_SHA256)
    stages = []
    for stage, generated, retained, full, pivots in candidate_stages():
        record = {
            "transition": stage,
            "generated_columns": generated,
            "retained_columns": len(retained),
            "complete_corner_histories": len(full),
            "simplex_pivots": pivots,
        }
        if stage >= 2:
            hull = ConvexHull(full)
            vertices = full[hull.vertices]
            distance = max(
                float(cKDTree(vertices).query(retained)[0].max()),
                float(cKDTree(retained).query(vertices)[0].max()),
            )
            record.update({"full_hull_vertices": len(vertices), "retained_to_full_hull_vertex_distance": distance})
            if len(retained) != len(vertices) or distance > 1e-9:
                raise ValueError(f"active filter differs from complete hull at stage {stage}")
        stages.append(record)

    projected = {}
    for key, (expected, axes) in FIGURES.items():
        patches, _, _, _ = saved_3d_patches(figures[key], expected)
        saved_linear = patches[0]
        full_projection = full[:, axes]
        full_hull = ConvexHull(full_projection)
        saved_hull = ConvexHull(saved_linear)
        full_vertices = full_projection[full_hull.vertices]
        saved_to_candidate = float(cKDTree(full_projection).query(saved_linear)[0].max())
        candidate_to_saved = float(cKDTree(saved_linear).query(full_vertices)[0].max())
        if saved_to_candidate > 1e-12:
            raise ValueError(f"saved {key} linear patch is not a candidate endpoint subset")
        projected[key] = {
            "figure_sha256": expected,
            "axes_one_based": [axis + 1 for axis in axes],
            "saved_linear_patch_vertices": len(saved_linear),
            "saved_linear_patch_hull_volume": float(saved_hull.volume),
            "active_full_projected_hull_vertices": len(full_hull.vertices),
            "active_full_projected_hull_volume": float(full_hull.volume),
            "saved_to_candidate_endpoint_max_distance": saved_to_candidate,
            "active_full_hull_to_saved_vertex_max_distance": candidate_to_saved,
        }

    return {
        "schema": "l05-dim4-retention-audit-v1",
        "source_sha256": SOURCE_SHA256,
        "convsm_sha256": CONVSM_SHA256,
        "simplex_sha256": SIMPLEX_SHA256,
        "arithmetic": "NumPy binary64 translation of active archived column order; not a MATLAB execution or validated arithmetic",
        "stages": stages,
        "terminal_active_hull_volume": float(ConvexHull(retained).volume),
        "printed_general_row": {"vertices": 756, "volume": 40808.17},
        "printed_modified_row": {"vertices": 153, "volume": 34764.47},
        "saved_linear_projections": projected,
        "modified_4d_row_reproduced": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--convsm", type=Path, required=True)
    parser.add_argument("--simplex", type=Path, required=True)
    for key in FIGURES:
        parser.add_argument(f"--figure-{key}", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    figures = {key: getattr(args, f"figure_{key}") for key in FIGURES}
    inputs = [args.source, args.convsm, args.simplex, *figures.values()]
    if args.output and args.output.resolve() in {path.resolve() for path in inputs}:
        parser.error("output must not overwrite a private source")
    result = audit(args.source, args.convsm, args.simplex, figures)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(serialized.encode("utf-8"))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()

"""Explore the commented four-state Approx_mod path with source-ordered floats.

This is a private-source audit, not a historical MATLAB execution or validated
nonlinear enclosure. The private source is read only and hash gated.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path

from .check_l05_dim4_candidate import (
    FIGURES, SOURCE_SHA256, candidate_endpoints, saved_3d_patches, source_hash,
)
from .check_l05_dim4_retention import (
    CONVSM_SHA256, CONTROLS, SIMPLEX_SHA256, candidate_stages, convsm_mod,
)


APPROX_SHA256 = "7ca79821f39fde91b0eba8681c1b8775713441a1a1ff04159d963a52416b1c5a"


def hyp_info(points, column: int, threshold: float, epsilon: float):
    """Translate the private HypInfo pivot and retained/deleted classification."""
    import numpy as np

    dimension, count = points.shape
    sign = np.where(points[:, column] >= 0.0, 1.0, -1.0)
    signed = points * sign[:, None]
    source = np.vstack((signed, np.ones(count), signed.sum(axis=0) + 1.0))
    tableau = source.copy()
    basis_matrix = np.eye(dimension + 2)
    basis = np.full(dimension + 1, -1, dtype=int)
    classification = np.zeros(count, dtype=int)
    pivots = 0

    while True:
        other = np.arange(count) != column
        if np.all(tableau[-1, other] <= epsilon) or tableau[-1, column] ** 2 < threshold:
            if abs(tableau[-1, column]) ** 2 < threshold:
                basis_columns = basis[basis >= 0]
                classification[basis_columns] = 1
                objective = tableau[-1, :].copy()
                objective[basis_columns] = np.nan
                delete = objective ** 2 < threshold
                delete[objective <= epsilon] = False
                classification[delete] = -1
            else:
                classification[column] = 1
            return classification, pivots

        objective = tableau[-1, :].copy()
        objective[column] = np.nan
        entering = int(np.nanargmax(objective))
        divisor = tableau[:dimension + 1, entering].copy()
        divisor[divisor < epsilon] = np.nan
        leaving = int(np.nanargmin(tableau[:dimension + 1, column] / divisor))
        basis_matrix[:, leaving] = source[:, entering]
        tableau = np.linalg.solve(basis_matrix, source)
        basis[leaving] = entering
        pivots += 1
        if pivots > 10000:
            raise RuntimeError("HypInfo pivot loop did not terminate")


def approx_mod(points, threshold: float, scale: float = 10.0, epsilon: float = 1e-9):
    """Translate private Approx_mod normalization, ranking and deletion loops."""
    import numpy as np

    original = points.T.copy()
    center = 0.5 * (original.max(axis=1) + original.min(axis=1))
    span = original.max(axis=1) - original.min(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized = 2.0 * scale * (original - center[:, None]) / span[:, None]
    nan_rows, nan_columns = np.where(np.isnan(normalized))
    normalized[nan_rows, nan_columns] = scale * np.sign(original[nan_rows, nan_columns])
    normalized_span = normalized.max(axis=1) - normalized.min(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = np.max(np.abs((normalized - center[:, None]) / normalized_span[:, None]), axis=0)
    order = np.argsort(-distance, kind="stable")
    normalized = normalized[:, order]
    original = original[:, order]
    table = np.vstack([hyp_info(normalized, column, threshold, epsilon)[0]
                       for column in range(original.shape[1])])
    deletion_rounds = 0
    while True:
        table_without_ones = table.copy()
        table_without_ones[table_without_ones == 1] = 0
        scores = table.sum(axis=0) + table_without_ones.sum(axis=1)
        selected = int(np.argmin(scores))
        if scores[selected] >= 0:
            break
        delete = table[selected, :] < 0
        hold = table[selected, :] > 0
        if not np.any(delete):
            raise RuntimeError("Approx_mod selected a row without deletions")
        table[:, hold] = np.abs(table[:, hold])
        table = table[~delete, :][:, ~delete]
        original = original[:, ~delete]
        deletion_rounds += 1
    return original.T, deletion_rounds


def stagewise_linear(threshold: float):
    """Apply the source's commented reduction after each active hull filter."""
    import numpy as np

    controls = np.asarray(CONTROLS)
    reference = np.array([1.0, 1.0, 1.0, 1.0])
    retained = np.array([[1.0, -1.0, 1.0, 1.0]])
    for stage in range(1, 8):
        r1, r2, r3, r4 = reference
        sine2 = math.sin(math.radians(r2))
        cosine1 = math.cos(math.radians(r1))
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
        images = controls @ input_matrix.T
        generated = np.vstack([row @ matrix.T + images for row in retained])
        hull, hull_pivots = convsm_mod(generated)
        retained, deletion_rounds = approx_mod(hull, threshold)
        yield stage, len(generated), len(hull), retained, hull_pivots, deletion_rounds
        reference = np.array([
            r1 + 0.5 * sine2 + (1.0 + 0.5 * cosine1) * 0.5,
            r2 + 0.15 * r1,
            r3 - 0.8 * r2,
            r4 + 0.25 * r3 + 0.5,
        ])


def audit(source: Path, convsm: Path, simplex: Path, approx: Path, figures: dict[str, Path]):
    import numpy as np
    import scipy
    from scipy.spatial import ConvexHull, cKDTree

    for path, digest in ((source, SOURCE_SHA256), (convsm, CONVSM_SHA256),
                         (simplex, SIMPLEX_SHA256), (approx, APPROX_SHA256)):
        source_hash(path, digest)
    stages = []
    for stage, generated, hull_size, retained, hull_pivots, deletion_rounds in stagewise_linear(0.001):
        stages.append({
            "transition": stage,
            "generated_columns": generated,
            "pre_reduction_hull_columns": hull_size,
            "post_reduction_columns": len(retained),
            "hull_pivots": hull_pivots,
            "deletion_rounds": deletion_rounds,
        })
    terminal_hull = ConvexHull(retained)
    complete_linear, _, _ = candidate_endpoints()
    endpoint_distance = float(cKDTree(complete_linear).query(retained)[0].max())
    if endpoint_distance > 1e-9:
        raise ValueError("reduced points are not candidate corner-history endpoints")
    terminal_only, terminal_only_rounds = approx_mod(list(candidate_stages())[-1][2], 0.001)
    terminal_only_hull = ConvexHull(terminal_only)
    projections = {}
    for key, (digest, axes) in FIGURES.items():
        patches, _, _, _ = saved_3d_patches(figures[key], digest)
        saved_linear = patches[0]
        candidate_projection = retained[:, axes]
        candidate_hull = ConvexHull(candidate_projection)
        candidate_vertices = candidate_projection[candidate_hull.vertices]
        projections[key] = {
            "figure_sha256": digest,
            "axes_one_based": [axis + 1 for axis in axes],
            "saved_vertices": len(saved_linear),
            "candidate_projected_vertices": len(candidate_vertices),
            "saved_to_candidate_vertex_max_distance": float(cKDTree(candidate_vertices).query(saved_linear)[0].max()),
            "candidate_to_saved_vertex_max_distance": float(cKDTree(saved_linear).query(candidate_vertices)[0].max()),
        }
    return {
        "schema": "l05-dim4-approx-audit-v1",
        "source_sha256": SOURCE_SHA256,
        "convsm_sha256": CONVSM_SHA256,
        "simplex_sha256": SIMPLEX_SHA256,
        "approx_sha256": APPROX_SHA256,
        "commented_threshold": 0.001,
        "arithmetic": "NumPy binary64 translation of commented stagewise path; no MATLAB execution or validated arithmetic",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "stages": stages,
        "terminal_vertices": len(terminal_hull.vertices),
        "terminal_volume": float(terminal_hull.volume),
        "terminal_reduced_to_complete_endpoint_max_distance": endpoint_distance,
        "terminal_only_reduction": {
            "vertices": len(terminal_only_hull.vertices),
            "volume": float(terminal_only_hull.volume),
            "deletion_rounds": terminal_only_rounds,
        },
        "printed_modified_row": {"vertices": 153, "volume": 34764.47},
        "saved_linear_projections": projections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--convsm", type=Path, required=True)
    parser.add_argument("--simplex", type=Path, required=True)
    parser.add_argument("--approx", type=Path, required=True)
    for key in FIGURES:
        parser.add_argument(f"--figure-{key}", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    figures = {key: getattr(args, f"figure_{key}") for key in FIGURES}
    inputs = [args.source, args.convsm, args.simplex, args.approx, *figures.values()]
    if args.output and args.output.resolve() in {path.resolve() for path in inputs}:
        parser.error("output must not overwrite a private source")
    serialized = json.dumps(audit(args.source, args.convsm, args.simplex, args.approx, figures), indent=2) + "\n"
    if args.output:
        args.output.write_bytes(serialized.encode("utf-8"))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()

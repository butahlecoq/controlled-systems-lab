"""Compare both printed L05 T0 groupings with saved linear stage plots.

The private FIG is read only. Saved binary64 patch coordinates are parsed and
their convex hulls use the exact arithmetic shared with the existing L05
figure checks. Reconstructed zonotope vertices are compared in floating point
with a stated tolerance; this does not identify the article's executed driver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

from .check_l05_linear_zonotope import (
    MATCH_TOLERANCE,
    SOURCE_SHA256,
    candidate_stages,
    vertex_set_distance,
)
from .check_l05_saved_figures import (
    FIGURE_SHA256,
    convex_hull,
    saved_patches,
    violations,
)


def grouping_summary() -> dict:
    """Return exact public formula data, without requiring private figures."""
    # a*c = (9/10)(4/5) = 18/25. The formulas use T=60.
    a_times_c = Fraction(9, 10) * Fraction(4, 5)
    ratio = 1 / a_times_c
    return {
        "parameters": {"a": "9/10", "c": "4/5", "T": 60, "a_times_c": "18/25"},
        "candidate": {
            "formula": "2*pi/(T*sqrt(a*c))",
            "simplified": "pi/(18*sqrt(2))",
        },
        "alternative": {
            "formula": "(2*pi/T)*sqrt(a*c)",
            "simplified": "pi*sqrt(2)/50",
        },
        "candidate_over_alternative": f"{ratio.numerator}/{ratio.denominator}",
        "alternative_over_candidate": f"{a_times_c.numerator}/{a_times_c.denominator}",
    }


def _fraction_hull(vertices: list[tuple[float, float]]) -> list[tuple[Fraction, Fraction]]:
    return convex_hull([
        (Fraction.from_float(x), Fraction.from_float(y)) for x, y in vertices
    ])


def audit(source: Path, figure: Path) -> dict:
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("candidate source SHA-256 mismatch")
    patches = saved_patches(figure, {FIGURE_SHA256})
    if len(patches) != 240:
        raise ValueError("expected two 60-stage patch pairs")

    a, c, horizon = 0.9, 0.8, 60
    candidate_step = 2 * math.pi / (horizon * math.sqrt(a * c))
    alternative_step = (2 * math.pi / horizon) * math.sqrt(a * c)
    candidate = candidate_stages(candidate_step)
    alternative = candidate_stages(alternative_step)
    stages: list[dict] = []

    for index, (candidate_vertices, alternative_vertices) in enumerate(zip(candidate, alternative)):
        saved_exact = patches[121 + 2 * index]
        saved = [(float(x), float(y)) for x, y in saved_exact]
        if len(saved) != 2 * (index + 1):
            raise ValueError(f"unexpected saved general-linear vertex count at stage {index + 1}")
        candidate_distance = vertex_set_distance(candidate_vertices, saved)
        alternative_distance = vertex_set_distance(alternative_vertices, saved)
        row = {
            "stage": index + 1,
            "saved_vertex_count": len(saved),
            "candidate_vertex_set_distance": candidate_distance,
            "candidate_matches_tolerance": candidate_distance <= MATCH_TOLERANCE,
            "alternative_vertex_set_distance": alternative_distance,
            "alternative_matches_tolerance": alternative_distance <= MATCH_TOLERANCE,
        }
        if index > 0:
            saved_hull = convex_hull(saved_exact)
            candidate_hull = _fraction_hull(candidate_vertices)
            alternative_hull = _fraction_hull(alternative_vertices)
            row.update({
                "exact_saved_vertices_outside_candidate_hull": violations(saved_hull, candidate_hull),
                "exact_candidate_vertices_outside_saved_hull": violations(candidate_hull, saved_hull),
                "exact_saved_vertices_outside_alternative_hull": violations(saved_hull, alternative_hull),
                "exact_alternative_vertices_outside_saved_hull": violations(alternative_hull, saved_hull),
            })
        stages.append(row)

    candidate_distances = [row["candidate_vertex_set_distance"] for row in stages]
    alternative_distances = [row["alternative_vertex_set_distance"] for row in stages]
    return {
        "schema": "l05-t0-grouping-audit-v1",
        "candidate_source_sha256": SOURCE_SHA256,
        "figure_sha256": FIGURE_SHA256,
        "grouping_formula_audit": grouping_summary(),
        "stages": len(stages),
        "compared_saved_patch": "second-group general-linear patch, zero-based index 121 + 2*stage_index",
        "vertex_set_distance_kind": "symmetric nearest-vertex Euclidean distance in plotted coordinates",
        "matching_tolerance": MATCH_TOLERANCE,
        "candidate_maximum_vertex_set_distance": max(candidate_distances),
        "candidate_matching_stages": sum(row["candidate_matches_tolerance"] for row in stages),
        "alternative_maximum_vertex_set_distance": max(alternative_distances),
        "alternative_matching_stages": sum(row["alternative_matches_tolerance"] for row in stages),
        "exact_saved_binary64_hull_checks": "dyadic-rational orientation and containment; stage 1 is a segment and is excluded",
        "per_stage": stages,
        "limits": [
            "The grouping that generated these saved stage polygons is identified within the stated floating-point vertex-set tolerance.",
            "The alternative printed grouping is tested with the same candidate affine-control zonotope construction and does not match if its stage distances exceed tolerance.",
            "The factor 25/18 is the exact ratio of the two T0 expressions, not a claim that propagated polygon coordinates scale uniformly by that factor.",
            "The article's own Table 1 driver and the printed T0 used for its run are not identified.",
            "Saved plotted binary64 vertices and this candidate reconstruction do not certify the historical generator or nonlinear enclosure.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="private Volterra.m candidate")
    parser.add_argument("--figure", type=Path, help="private Buryatia 4.fig")
    parser.add_argument("--output", type=Path, help="write derived JSON, never source vertices")
    parser.add_argument("--verify-record", type=Path, help="recompute and compare a prior JSON record")
    args = parser.parse_args()
    if (args.source is None) != (args.figure is None):
        parser.error("--source and --figure must be supplied together")
    if args.source is None:
        parser.error("--source and --figure are required")
    result = audit(args.source, args.figure)
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output and args.output.resolve() in {args.source.resolve(), args.figure.resolve()}:
        parser.error("output must not overwrite a private source")
    if args.verify_record:
        if args.verify_record.read_text(encoding="utf-8") != serialized:
            raise SystemExit("stored L05 T0 grouping record differs from recomputed private-file audit")
    if args.output:
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    elif not args.verify_record:
        print(serialized, end="")


if __name__ == "__main__":
    main()

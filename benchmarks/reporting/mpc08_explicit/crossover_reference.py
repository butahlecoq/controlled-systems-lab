"""Exact control laws for the strictly convex, three-step MPC crossover fixture."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import combinations
from pathlib import Path

import exact_regions as geometry
from explicit_double_integrator import BOX, intersect

# Affine forms use coordinates (p, v, 1). The rows describe G u <= E (p, v, 1).
Form = tuple[Q, Q, Q]
EFFORT = Q(1, 4)


@dataclass(frozen=True)
class Bound:
    coefficients: tuple[Q, ...]
    rhs: Form


def condense(n: int):
    """Eliminate the states in p'=p+v, v'=v+u. Cost is |x_N|² + ¼ sum u²."""
    endpoint = [(n - 1 - i, 1) for i in range(n)]
    # Divide the whole gradient by two. The scaled multipliers have the same sign.
    hessian = [
        [Q(a * b + 1) + EFFORT * (i == j) for j, (b, _) in enumerate(endpoint)]
        for i, (a, _) in enumerate(endpoint)
    ]
    gradient = [(Q(a), Q(a * n + 1), Q(0)) for a, _ in endpoint]
    bounds = []
    for i in range(n):
        for sign in (1, -1):
            g = tuple(Q(sign * (i == j)) for j in range(n))
            bounds.append(Bound(g, (Q(0), Q(0), Q(1))))
    for k in range(1, n + 1):
        state_rows = geometry.X if k < n else [*geometry.X, *geometry.target()]
        for a, b, c in state_rows:
            g = tuple(a * (k - 1 - j) + b if j < k else Q(0) for j in range(n))
            bounds.append(Bound(g, (-a, -k * a - b, c)))
    return hessian, gradient, bounds


def solve(matrix, rhs):
    """Solve three rational right-hand sides together. Singular active bases are skipped."""
    a = [list(row) + list(form) for row, form in zip(matrix, rhs, strict=True)]
    for col in range(len(a)):
        pivot = next((r for r in range(col, len(a)) if a[r][col]), None)
        if pivot is None:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for r, row in enumerate(a):
            if r != col and row[col]:
                a[r] = [v - row[col] * w for v, w in zip(row, a[col], strict=True)]
    return [tuple(row[-3:]) for row in a]


def polygon_rows(polygon):
    """Outward-facing facet normals for a counterclockwise convex polygon."""
    rows = []
    for (p, v), (q, w) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        a, b = w - v, p - q
        rows.append((a, b, a * p + b * v))
    return rows


def regions(n: int):
    hessian, gradient, bounds = condense(n)
    cells = {}
    active_candidates = [i for i, row in enumerate(bounds) if any(row.coefficients)]
    for count in range(n + 1):
        for active in combinations(active_candidates, count):
            binding = [bounds[i] for i in active]
            matrix = [hessian[j] + [r.coefficients[j] for r in binding] for j in range(n)]
            matrix += [list(r.coefficients) + [Q(0)] * count for r in binding]
            rhs = [tuple(-v for v in g) for g in gradient] + [r.rhs for r in binding]
            result = solve(matrix, rhs)
            if result is None:
                continue
            controls, duals = result[:n], result[n:]
            inequalities = [(-a, -b, c) for a, b, c in duals]
            for row in bounds:
                margin = [
                    row.rhs[k]
                    - sum(
                        g * control[k]
                        for g, control in zip(row.coefficients, controls, strict=True)
                    )
                    for k in range(3)
                ]
                inequalities.append((-margin[0], -margin[1], margin[2]))
            polygon = tuple(geometry.hull(intersect(BOX, inequalities)))
            if geometry.area(polygon) == 0:
                continue
            if polygon in cells and controls != cells[polygon]:
                raise ValueError(f"inconsistent optimal histories on one cell for horizon {n}")
            cells[polygon] = controls
    return cells


def checked_reference():
    domain = geometry.vertices([*geometry.X, *geometry.target()])
    records = []
    for n in range(1, 4):
        # Independent elimination of each scalar control yields the feasible domain.
        domain = geometry.vertices(geometry.predecessor(polygon_rows(domain)))
        cells = regions(n)
        covered = sum(geometry.area(p) for p in cells)
        if covered != geometry.area(domain):
            raise ValueError(
                f"horizon {n}: cell area {covered}, feasible area {geometry.area(domain)}"
            )
        for polygon in cells:
            if not geometry.contained(polygon, polygon_rows(domain)):
                raise ValueError("cell leaves backward feasible domain")
        for left, right in combinations(cells, 2):
            shared = intersect(list(left), polygon_rows(right))
            if geometry.area(shared):
                raise ValueError("overlapping cell interiors")
            for p, v in shared:
                for a, b in zip(cells[left], cells[right], strict=True):
                    if (a[0] - b[0]) * p + (a[1] - b[1]) * v + a[2] - b[2]:
                        raise ValueError("optimal control laws disagree on a shared boundary")
        records.append(
            {
                "remaining": n,
                "feasible_polygon": domain,
                "feasible_area": covered,
                "cells": [{"vertices": poly, "controls": laws} for poly, laws in cells.items()],
            }
        )
    return {
        "schema": "csl.mpc-crossover-reference/1",
        "A": [[1, 1], [0, 1]],
        "B": [0, 1],
        "step": 1,
        "control_bounds": [-1, 1],
        "state_halfspaces": geometry.X,
        "terminal_halfspaces": geometry.target(),
        "terminal_weight": [[1, 0], [0, 1]],
        "control_weight": EFFORT,
        "affine_coordinates": ["position", "velocity", "one"],
        "horizons": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reference = checked_reference()
    args.output.write_text(
        json.dumps(reference, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
    for record in reference["horizons"]:
        print(
            f"N={record['remaining']} cells={len(record['cells'])} feasible area={record['feasible_area']}"
        )

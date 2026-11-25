"""Exact small-cloud audit of a retained subset of binary64 points.

Input JSON is ``{"points": [[...], ...], "retained_indices": [0, ...]}``.
Coordinates are interpreted as their exact binary64 values. The checker uses
only the standard library and makes no calls to numerical solvers.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import sys
from typing import Sequence


DEFAULT_BUDGET = 50_000


def _solve(matrix: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction] | None:
    """Solve a square exact system, returning None when singular."""
    n = len(rhs)
    aug = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for col in range(n):
        pivot = next((r for r in range(col, n) if aug[r][col]), None)
        if pivot is None:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [x / scale for x in aug[col]]
        for r in range(n):
            if r != col and aug[r][col]:
                factor = aug[r][col]
                aug[r] = [x - factor * y for x, y in zip(aug[r], aug[col])]
    return [aug[r][-1] for r in range(n)]


def _certificate(target: tuple[Fraction, ...], candidates: Sequence[tuple[int, tuple[Fraction, ...]]],
                 budget: list[int], limit: int) -> tuple[list[tuple[int, Fraction]] | None, bool]:
    """Return a convex certificate and whether the complete search was done."""
    d = len(target)
    for size in range(1, min(d + 1, len(candidates)) + 1):
        for support in itertools.combinations(candidates, size):
            if budget[0] >= limit:
                return None, False
            budget[0] += 1
            # The first equation is sum(lambda)=1; remaining equations reconstruct x.
            rows = [[Fraction(1) for _ in support]]
            rows.extend([[point[k] for _, point in support] for k in range(d)])
            rhs = [Fraction(1), *target]
            # A support can have fewer than d+1 points; choose every row subset
            # of matching size, then verify all equations after solving.
            for selected in itertools.combinations(range(d + 1), size):
                solution = _solve([[rows[r][c] for c in range(size)] for r in selected],
                                  [rhs[r] for r in selected])
                if solution is None or any(w < 0 for w in solution):
                    continue
                if all(sum(rows[r][c] * solution[c] for c in range(size)) == rhs[r]
                       for r in range(d + 1)):
                    return [(support[i][0], solution[i]) for i in range(size)], True
    return None, True


def _q(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("coordinates must be JSON numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("coordinates must be finite")
    return Fraction.from_float(number)


def _wire_certificate(certificate: list[tuple[int, Fraction]] | None):
    if certificate is None:
        return None
    return [{"index": index, "weight": str(weight)} for index, weight in certificate]


def check_hull(points, retained_indices, *, max_basis_tests: int = DEFAULT_BUDGET) -> dict:
    """Check hull equality exactly, plus retained-point redundancy separately.

    A ``rejected`` result means a complete exact search found an input point
    outside the retained hull. Invalid/unsupported/budget-limited requests are
    ``inconclusive``. Hull-equal redundant points remain ``verified``.
    """
    base = {"status": "inconclusive", "hull_equal": None, "irredundancy": None,
            "extra_indices": [], "reason": "", "basis_tests": 0,
            "certificates": {}, "redundancy_certificates": {}}
    try:
        if not isinstance(max_basis_tests, int) or isinstance(max_basis_tests, bool) or max_basis_tests < 0:
            raise ValueError("max_basis_tests must be a nonnegative integer")
        if not isinstance(points, (list, tuple)) or not isinstance(retained_indices, (list, tuple)):
            raise ValueError("points and retained_indices must be arrays")
        if len(points) > 12:
            raise ValueError("point count exceeds supported maximum 12")
        if not points:
            if retained_indices:
                raise ValueError("nonempty retained_indices for empty points")
            base.update(status="verified", hull_equal=True, irredundancy=True, reason="both hulls are empty")
            return base
        if any(not isinstance(point, (list, tuple)) for point in points):
            raise ValueError("each point must be an array")
        dims = {len(p) for p in points}
        if len(dims) != 1:
            raise ValueError("point dimensions must agree")
        d = next(iter(dims))
        if not 1 <= d <= 4:
            raise ValueError("dimension must be between 1 and 4")
        qpoints = [tuple(_q(v) for v in point) for point in points]
        if not isinstance(retained_indices, (list, tuple)):
            raise ValueError("retained_indices must be an array")
        if any(not isinstance(i, int) or isinstance(i, bool) for i in retained_indices):
            raise ValueError("retained indices must be integers")
        if len(set(retained_indices)) != len(retained_indices):
            raise ValueError("retained indices must be unique")
        if any(i < 0 or i >= len(points) for i in retained_indices):
            raise ValueError("retained index out of bounds")
    except (TypeError, ValueError, OverflowError) as exc:
        base["reason"] = str(exc)
        return base

    budget = [0]
    retained = [(i, qpoints[i]) for i in retained_indices]
    certs = {}
    complete = True
    for i, target in enumerate(qpoints):
        cert, done = _certificate(target, retained, budget, max_basis_tests)
        if cert is None:
            if not done:
                complete = False
                break
            base.update(status="rejected", hull_equal=False, reason=f"input point {i} is outside retained hull",
                        basis_tests=budget[0])
            return base
        certs[str(i)] = _wire_certificate(cert)
    base["basis_tests"] = budget[0]
    if not complete:
        base["reason"] = "basis-test budget exhausted during hull equality search"
        return base

    redundant = []
    redundancy_certs = {}
    # Redundancy has its own completeness flag: it does not invalidate hull equality.
    redundancy_complete = True
    for i in retained_indices:
        others = [(j, qpoints[j]) for j in retained_indices if j != i]
        cert, done = _certificate(qpoints[i], others, budget, max_basis_tests)
        if not done:
            redundancy_complete = False
            break
        if cert is not None:
            redundant.append(i)
            redundancy_certs[str(i)] = _wire_certificate(cert)
    base["basis_tests"] = budget[0]
    base["hull_equal"] = True
    base["certificates"] = certs
    base["extra_indices"] = redundant
    base["redundancy_certificates"] = redundancy_certs
    base["irredundancy"] = (not redundant) if redundancy_complete else None
    base["status"] = "verified"
    base["reason"] = ("hulls equal; redundancy search complete" if redundancy_complete else
                      "hulls equal; redundancy search hit basis-test budget")
    return base


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON file with points and retained_indices; stdin if omitted")
    parser.add_argument("--max-basis-tests", type=int, default=DEFAULT_BUDGET)
    args = parser.parse_args(argv)
    try:
        data = json.loads(Path(args.input).read_text() if args.input else sys.stdin.read())
        result = check_hull(data["points"], data["retained_indices"], max_basis_tests=args.max_basis_tests)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = {"status": "inconclusive", "hull_equal": None, "irredundancy": None,
                  "extra_indices": [], "reason": f"invalid input JSON: {exc}", "basis_tests": 0,
                  "certificates": {}, "redundancy_certificates": {}}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

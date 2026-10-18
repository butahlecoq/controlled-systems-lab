"""Fixed OPT-11 fixtures and exact dyadic hull/certificate oracle."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json

FIXTURES = {
    "signed-grid": [[[-4., -4.], [-4., 0.], [-4., 4.], [0., -4.], [0., 4.],
                     [4., -4.], [4., 0.], [4., 4.]][(i * 3) % 8]
                    for i in range(33)],
    "duplicate-collinear": [[(-16. if i % 3 == 0 else (0. if i % 3 == 1 else 16.)),
                             (-32. if i % 3 == 0 else (0. if i % 3 == 1 else 32.))]
                            for i in range(33)],
    "rank-one-offset": [[(-8. if i % 3 == 0 else (0. if i % 3 == 1 else 8.)),
                         (-22. if i % 3 == 0 else (2. if i % 3 == 1 else 26.))]
                        for i in range(33)],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fixture_digest() -> str:
    encoded = json.dumps(FIXTURES, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def q(value: float) -> Fraction:
    return Fraction.from_float(float(value))


def point_key(point: list[float] | tuple[float, ...]) -> tuple[Fraction, ...]:
    return tuple(q(v) for v in point)


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points):
    ordered = sorted(set(point_key(point) for point in points))
    if len(ordered) <= 1:
        return ordered
    lower = []
    for p in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    result = lower[:-1] + upper[:-1]
    return result if result else [ordered[0]]


def inside_hull(p, hull) -> bool:
    if len(hull) == 1:
        return p == hull[0]
    if len(hull) == 2:
        return cross(hull[0], hull[1], p) == 0 and all(
            min(a, b) <= x <= max(a, b) for x, a, b in zip(p, hull[0], hull[1]))
    return all(cross(hull[i], hull[(i + 1) % len(hull)], p) >= 0 for i in range(len(hull)))


def exact_certificate(call: dict) -> None:
    points = call["points"]
    retained = call["retained"]
    removed = call["removed"]
    n = len(points)
    require(all(type(i) is int and 0 <= i < n for i in retained), "retained ID outside fixture")
    require(len(set(retained)) == len(retained), "duplicate retained ID")
    cert_by_id = {}
    for cert in removed:
        target = cert.get("point")
        require(type(target) is int and 0 <= target < n and target not in cert_by_id,
                "duplicate or invalid removed ID")
        terms = cert.get("terms")
        require(isinstance(terms, list) and terms, "empty deletion certificate")
        weights = []
        reconstructed = [Fraction(0) for _ in points[target]]
        for term in terms:
            require(isinstance(term, list) and len(term) == 2, "malformed certificate term")
            source, raw_weight = term
            require(type(source) is int and 0 <= source < n and
                    isinstance(raw_weight, (float, int)), "invalid certificate source/weight")
            weight = q(raw_weight)
            require(weight >= 0, "negative exact dyadic certificate weight")
            weights.append(weight)
            for axis, coordinate in enumerate(points[source]):
                reconstructed[axis] += weight * q(coordinate)
        require(sum(weights, Fraction(0)) == 1, "certificate weights do not sum exactly to one")
        require(tuple(reconstructed) == point_key(points[target]), "certificate does not reconstruct exact dyadic point")
        cert_by_id[target] = terms
    require(set(retained).isdisjoint(cert_by_id) and set(retained) | set(cert_by_id) == set(range(n)),
            "retained and removed IDs do not partition fixture")

    def expand(point_id, stack=()):
        require(point_id not in stack, "cyclic deletion certificate")
        if point_id in retained:
            return {point_id: Fraction(1)}
        require(point_id in cert_by_id, "certificate references neither retained nor removed ID")
        expanded = {}
        for source, weight in cert_by_id[point_id]:
            for leaf, leaf_weight in expand(source, stack + (point_id,)).items():
                expanded[leaf] = expanded.get(leaf, Fraction(0)) + q(weight) * leaf_weight
        return expanded

    final_hull = convex_hull([points[i] for i in retained])
    expected_hull = convex_hull(points)
    require(set(expected_hull).issubset(set(point_key(points[i]) for i in retained)),
            "literal extreme vertex missing from retained output")
    require(all(inside_hull(point_key(points[i]), expected_hull) for i in retained),
            "retained point lies outside literal input hull")
    for target in cert_by_id:
        expansion = expand(target)
        require(sum(expansion.values(), Fraction(0)) == 1, "expanded certificate weights do not sum to one")
        value = [sum((weight * q(points[i][axis]) for i, weight in expansion.items()), Fraction(0))
                 for axis in range(len(points[target]))]
        require(tuple(value) == point_key(points[target]), "expanded certificate fails exact final-hull check")
    require(all(inside_hull(point_key(p), final_hull) for p in points),
            "retained coordinates do not contain every input point")

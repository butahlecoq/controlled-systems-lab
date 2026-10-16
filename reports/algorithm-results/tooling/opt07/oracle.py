"""Independent literal and exact-dyadic checks for the OPT-07 harness records."""
from __future__ import annotations

from fractions import Fraction
import math


FIXTURES = {
    "signed-score": {
        "points": [[-1.0, -1.0], [1.0, 1.0], [-1.0, 1.0],
                   [1.0, -1.0], [-1.0, 0.25], [0.75, -0.75]],
        "order": [0, 1, 2, 3, 5, 4], "zero_width": 0,
        "directions": [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0],
                       [0.0, -1.0], [1.0, 1.0]],
        "support": [1.0, 1.0, 1.0, 1.0, 2.0], "vertices": 4,
    },
    "zero-width-duplicate": {
        "points": [[-2.0, 3.0], [2.0, 3.0], [0.0, 3.0], [-2.0, 3.0]],
        "order": [0, 1, 3, 2], "zero_width": 1,
        "directions": [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]],
        "support": [2.0, 2.0, 3.0, -3.0], "vertices": 2,
    },
    "late-outside": {
        "points": [[0.0], [0.5], [0.25], [1.0]],
        "order": [0, 3, 2, 1], "zero_width": 0,
        "directions": [[1.0], [-1.0]],
        "support": [1.0, 0.0], "vertices": 2,
    },
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def exact_number(value: object) -> Fraction:
    require(type(value) in (float, int), "non-numeric coordinate or weight")
    value = float(value)
    require(math.isfinite(value), "nonfinite coordinate or weight")
    return Fraction.from_float(value)


def validate_call(row: dict) -> None:
    require(row.get("kind") == "call", "not a call row")
    case_id = row.get("case_id")
    require(case_id in FIXTURES, "unknown fixture")
    fixture = FIXTURES[case_id]
    points = row.get("points")
    require(points == fixture["points"], "fixture coordinates changed")
    require(row.get("problem") == f"opt07-{case_id}", "problem identity changed")
    count = len(points)
    require(row.get("status") == "complete" and row.get("verified") is True,
            "run was not verified complete")
    require(row.get("order") == fixture["order"], "ordered candidate IDs changed")
    require(row.get("ordered_candidates") == count, "ordered candidate count changed")
    require(row.get("zero_width_coordinates") == fixture["zero_width"],
            "zero-width count changed")
    require(row.get("identity_fallback") is False, "unexpected order fallback")

    retained = row.get("retained")
    require(isinstance(retained, list) and len(retained) == fixture["vertices"] and
            all(type(point) is int and 0 <= point < count for point in retained) and
            len(set(retained)) == len(retained), "invalid retained IDs")
    removed = row.get("removed")
    require(isinstance(removed, list), "missing removals")
    removed_ids = [item.get("point") for item in removed]
    require(all(type(point) is int and 0 <= point < count for point in removed_ids) and
            len(set(removed_ids)) == len(removed_ids) and
            set(retained).isdisjoint(removed_ids) and
            set(retained) | set(removed_ids) == set(range(count)),
            "retained/removal partition invalid")

    for position, certificate in enumerate(removed):
        candidate = certificate["point"]
        require(certificate.get("program_problem") == row["problem"],
                "membership problem identity changed")
        require(certificate.get("program") == f"hull-membership-{candidate}",
                "membership program lost original ID")
        terms = certificate.get("terms")
        require(isinstance(terms, list) and terms, "missing certificate terms")
        permitted = set(retained) | set(removed_ids[position + 1:])
        total = Fraction(0)
        reconstructed = [Fraction(0) for _ in points[candidate]]
        for term in terms:
            require(isinstance(term, list) and len(term) == 2, "malformed certificate term")
            point, weight_value = term
            require(type(point) is int and point in permitted, "certificate uses removed or invalid support")
            weight = exact_number(weight_value)
            require(weight >= 0, "negative certificate weight")
            total += weight
            for coordinate in range(len(reconstructed)):
                reconstructed[coordinate] += weight * exact_number(points[point][coordinate])
        require(total == 1, "certificate weights do not sum exactly to one")
        require(reconstructed == [exact_number(x) for x in points[candidate]],
                "certificate does not exactly reconstruct point")

    attempts = row.get("attempts")
    require(isinstance(attempts, list) and len(attempts) == count and
            [attempt[0] for attempt in attempts] == fixture["order"] and
            row.get("lp_calls") == count, "LP attempt/order count changed")
    for candidate, outcome in attempts:
        require(outcome == ("feasible" if candidate in removed_ids else "infeasible"),
                "membership outcome contradicts removal")

    actual_support = []
    for direction in fixture["directions"]:
        actual_support.append(max(sum(x * y for x, y in zip(points[point], direction))
                                  for point in retained))
    require(actual_support == fixture["support"] and row.get("support") == actual_support,
            "literal hull support changed")

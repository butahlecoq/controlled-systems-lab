"""Exact rational audit of the rounded linear B08 data printed in L04.

The article's unrounded arrays, nonlinear plant, and historical generator are
not available. This checks the finite, unconstrained transcription only.
"""

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
import json
from pathlib import Path


def q(value):
    return Fraction(value)


ZERO = q("0")
X0 = tuple(map(q, ("1182.074", "119560", "459.832", "45260")))
TARGET = tuple(map(q, ("1200", "0", "450", "0")))
B = (q("20.073"), ZERO, q("-10.473"), ZERO)
ACTIONS = tuple(map(q, ("0.6", "0.3", "0", "-0.3", "-0.6")))
REPORTED_PLAN = tuple(map(q, ("0.6", "0.6", "-0.3", "0")))
REPORTED_COST = q("67.12")
EXPECTED_SQUARED = Fraction(112730080707, 25000000)
EXPECTED_MINIMIZERS = (
    tuple(map(q, ("0.6", "0.6", "-0.3", "0"))),
    tuple(map(q, ("0.6", "0.3", "0.3", "-0.3"))),
    tuple(map(q, ("0.3", "0.6", "0.6", "-0.6"))),
)


def step(state, action=ZERO, disturbance=(ZERO, ZERO)):
    """Apply the displayed A, B and E to a four-coordinate state."""
    x1, x2, x3, x4 = state
    w1, w2 = disturbance
    return (x1 + B[0] * action + w1,
            x2 - 25 * x1,
            x3 + B[2] * action - w2,
            x4 - 25 * x3)


def corner_offsets():
    for signs in product((-1, 1), repeat=8):
        offset = (ZERO,) * 4
        for t in range(4):
            disturbance = (q("0.1") * (1 + t) * signs[2 * t],
                           q("0.1") * (1 + 3 * t) * signs[2 * t + 1])
            offset = step(offset, disturbance=disturbance)
        yield signs, offset


def squared_norm(state):
    return sum((coordinate - target) ** 2
               for coordinate, target in zip(state, TARGET))


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def decimal_sqrt(value):
    with localcontext() as ctx:
        ctx.prec = 35
        return str((Decimal(value.numerator) / Decimal(value.denominator)).sqrt())


def audit():
    offsets = tuple(corner_offsets())
    if len(offsets) != 256:
        raise RuntimeError("B08 disturbance corner count changed")
    scores = {}
    for plan in product(ACTIONS, repeat=4):
        center = X0
        for action in plan:
            center = step(center, action)
        scores[plan] = max(squared_norm(tuple(c + d for c, d in zip(center, offset)))
                           for _, offset in offsets)

    if len(scores) != 625:
        raise RuntimeError("B08 plan count changed")
    optimum = min(scores.values())
    minimizers = [plan for plan, score in scores.items() if score == optimum]
    if optimum != EXPECTED_SQUARED or tuple(minimizers) != EXPECTED_MINIMIZERS:
        raise RuntimeError("B08 exact displayed-data reference changed")
    reported = scores[REPORTED_PLAN]
    center = X0
    for action in REPORTED_PLAN:
        center = step(center, action)
    worst_signs, worst_offset = next(
        (signs, offset) for signs, offset in offsets
        if squared_norm(tuple(c + d for c, d in zip(center, offset))) == reported
    )
    worst_terminal = tuple(c + d for c, d in zip(center, worst_offset))
    return {
        "scope": "exact rational enumeration of L04 displayed rounded linear data",
        "source_id": "L04",
        "source_sha256": "6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f",
        "plan_count": len(scores),
        "disturbance_corner_count_per_plan": len(offsets),
        "objective": "Euclidean terminal norm; exact values below are squared norms",
        "minimum_squared_exact": rational(optimum),
        "minimum_norm_decimal": decimal_sqrt(optimum),
        "exact_minimizers": [[str(action) for action in plan] for plan in minimizers],
        "reported_plan": [str(action) for action in REPORTED_PLAN],
        "reported_plan_squared_exact": rational(reported),
        "reported_plan_norm_decimal": decimal_sqrt(reported),
        "reported_plan_worst_corner_signs": list(worst_signs),
        "reported_plan_worst_terminal_exact": [rational(value) for value in worst_terminal],
        "reported_norm": "67.12",
        "reported_plan_is_exact_minimizer": reported == optimum,
        "reported_norm_squared_exact": rational(REPORTED_COST ** 2),
        "displayed_model_matches_reported_norm": optimum == REPORTED_COST ** 2,
        "limitations": [
            "Printed decimals are treated as exact rationals; original unrounded arrays are unavailable.",
            "Only the displayed four-step unconstrained linear minimax model is checked.",
            "No nonlinear trajectory, historical timing, or complete publication generator is reproduced."
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-record", type=Path,
                        help="compare the computed result with a saved JSON record")
    args = parser.parse_args()
    result = audit()
    if args.verify_record:
        saved = json.loads(args.verify_record.read_text(encoding="utf-8"))
        if result != saved:
            raise RuntimeError("B08 exact record differs from computed result")
        print("B08 exact displayed-data record verified")
    else:
        print(json.dumps(result, indent=2))

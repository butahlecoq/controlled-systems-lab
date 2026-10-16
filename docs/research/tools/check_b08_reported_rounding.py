"""Exact rounding-box checks for L04's printed B08 terminal rows.

This evaluates the printed Euclidean criterion and printed affine model. It
does not identify the unpublished numerical arrays or nonlinear trajectory.
"""

import argparse
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path


SOURCE_ID = "L04"
SOURCE_BYTES = 390884
SOURCE_SHA256 = "6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f"
TARGET = tuple(map(Fraction, ("1200", "0", "450", "0")))
INITIAL = tuple(map(Fraction, ("1182.074", "119560", "459.832", "45260")))
CONTROL = tuple(map(Fraction, ("0.6", "0.6", "-0.3", "0")))
INPUT = tuple(map(Fraction, ("20.073", "0", "-10.473", "0")))
ROWS = {
    "nonlinear_text": (("1200.139", "-2.294", "450.406", "-16.254"),
                       "0.0005", "14.048", "0.0005"),
    "nonlinear_table": (("1200.14", "-2.29", "450.41", "-16.25"),
                        "0.005", "14.05", "0.005"),
    "linear_table": (("1201.14", "-27.29", "452.61", "-61.25"),
                     "0.005", "67.12", "0.005"),
}


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def squared_norm_box(center, target, half_width):
    """Exact extrema of squared Euclidean distance on a uniform axis box."""
    distances = [abs(x - y) for x, y in zip(center, target)]
    lower = sum(max(Fraction(0), distance - half_width) ** 2
                for distance in distances)
    upper = sum((distance + half_width) ** 2 for distance in distances)
    return lower, upper


def step(state, action, disturbance):
    x1, x2, x3, x4 = state
    w1, w2 = disturbance
    return (x1 + INPUT[0] * action + w1,
            x2 - 25 * x1,
            x3 + INPUT[2] * action - w2,
            x4 - 25 * x3)


def published_plan_corners():
    for signs in product((-1, 1), repeat=8):
        state = INITIAL
        for stage, action in enumerate(CONTROL):
            disturbance = (Fraction(stage + 1, 10) * signs[2 * stage],
                           Fraction(1 + 3 * stage, 10) * signs[2 * stage + 1])
            state = step(state, action, disturbance)
        yield state


def audit():
    result = {
        "source_id": SOURCE_ID,
        "source_sha256": SOURCE_SHA256,
        "source_bytes": SOURCE_BYTES,
        "scope": "L04 printed terminal rows, nearest-decimal rounding boxes and printed linear model",
        "criterion": "L04 p.7 Eq.(15) and p.12: Euclidean distance to (1200,0,450,0)",
        "rows": "L04 physical PDF p.13 text and Table 2",
    }
    for name, (coordinates, half, cost, cost_half) in ROWS.items():
        center = tuple(map(Fraction, coordinates))
        radius = Fraction(half)
        norm_lower, norm_upper = squared_norm_box(center, TARGET, radius)
        reported = Fraction(cost)
        reported_half = Fraction(cost_half)
        cost_lower, cost_upper = (reported - reported_half) ** 2, (reported + reported_half) ** 2
        result[name] = {
            "coordinates": list(coordinates),
            "coordinate_half_width": half,
            "reported_cost": cost,
            "cost_half_width": cost_half,
            "norm_squared_box": [rational(norm_lower), rational(norm_upper)],
            "cost_squared_box": [rational(cost_lower), rational(cost_upper)],
            "cost_box_disjoint": norm_lower > cost_upper or norm_upper < cost_lower,
        }
    corners = tuple(published_plan_corners())
    linear = result["linear_table"]
    printed = tuple(map(Fraction, linear["coordinates"]))
    radius = Fraction(linear["coordinate_half_width"])
    corner_squared = [sum((x - y) ** 2 for x, y in zip(point, TARGET)) for point in corners]
    worst = max(corner_squared)
    nearest = min(max(abs(x - y) for x, y in zip(point, printed)) for point in corners)
    reported = Fraction(linear["reported_cost"])
    reported_half = Fraction(linear["cost_half_width"])
    linear.update({
        "corner_count": len(corners),
        "corners_in_coordinate_box": sum(all(abs(x - y) <= radius
                                              for x, y in zip(point, printed)) for point in corners),
        "nearest_corner_max_coordinate_gap": rational(nearest),
        "worst_corner_squared": rational(worst),
        "worst_cost_box_disjoint": worst > (reported + reported_half) ** 2 or
                                   worst < (reported - reported_half) ** 2,
    })
    return result


def verify_source(path):
    raw = path.read_bytes()
    if len(raw) != SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("L04 PDF bytes/hash differ from registered source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", type=Path, help="optional private L04 original hash check")
    parser.add_argument("--verify-record", type=Path, help="compare with committed exact result")
    args = parser.parse_args()
    if args.source_pdf:
        verify_source(args.source_pdf)
    observed = audit()
    if args.verify_record:
        expected = json.loads(args.verify_record.read_text(encoding="utf-8"))
        if observed != expected:
            raise ValueError("B08 rounding record differs from exact replay")
        print("B08 printed terminal-row rounding audit verified")
    else:
        print(json.dumps(observed, indent=2, ensure_ascii=False))

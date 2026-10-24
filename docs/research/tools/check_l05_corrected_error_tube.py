#!/usr/bin/env python3
"""Outward-rounded error tube for an explicitly assumed L05 corrected track."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from fractions import Fraction
from math import isqrt
import json

PRECISION = 80


def atan_reciprocal_interval(denominator, terms=120):
    """Bound atan(1/q) between consecutive exact alternating-series sums."""
    x = Fraction(1, denominator)
    term = x
    partial = Fraction(0)
    sums = []
    for index in range(terms + 1):
        partial += term if index % 2 == 0 else -term
        sums.append(partial)
        term *= x * x * Fraction(2 * index + 1, 2 * index + 3)
    return min(sums[-2:]), max(sums[-2:])


def fraction_decimal(value, mode):
    return rounded(lambda: Decimal(value.numerator) / Decimal(value.denominator), mode)


def pi_interval():
    # Machin's identity and alternating arctan series give a rational enclosure.
    atan5 = atan_reciprocal_interval(5)
    atan239 = atan_reciprocal_interval(239)
    lower = 16 * atan5[0] - 4 * atan239[1]
    upper = 16 * atan5[1] - 4 * atan239[0]
    return fraction_decimal(lower, ROUND_FLOOR), fraction_decimal(upper, ROUND_CEILING)


def rounded(operation, mode):
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = mode
        return operation()


def point(value):
    number = Decimal(value)
    return number, number


def add(left, right):
    return (rounded(lambda: left[0] + right[0], ROUND_FLOOR),
            rounded(lambda: left[1] + right[1], ROUND_CEILING))


def negate(value):
    return value[1].copy_negate(), value[0].copy_negate()


def subtract(left, right):
    return add(left, negate(right))


def multiply(left, right):
    products = [rounded(lambda: a * b, ROUND_FLOOR)
                for a in left for b in right]
    upper = [rounded(lambda: a * b, ROUND_CEILING)
             for a in left for b in right]
    return min(products), max(upper)


def divide_positive(numerator, denominator):
    reciprocal = (rounded(lambda: Decimal(1) / denominator[1], ROUND_FLOOR),
                  rounded(lambda: Decimal(1) / denominator[0], ROUND_CEILING))
    return multiply(numerator, reciprocal)


def square_root(value):
    def bounds(number):
        rational = Fraction(number)
        scaled_floor = rational.numerator * 10 ** (2 * PRECISION) // rational.denominator
        root = isqrt(scaled_floor)
        return (Decimal(f"{root}e-{PRECISION}"),
                Decimal(f"{root + 1}e-{PRECISION}"))
    return bounds(value[0])[0], bounds(value[1])[1]


def show(interval):
    return [str(interval[0]), str(interval[1])]


def run():
    a, b, c, d, gain = map(point, ("0.9", "0.003", "0.8", "0.002", "0.85"))
    pi = pi_interval()
    t0 = divide_positive(
        divide_positive(multiply(point("2"), pi), square_root(multiply(a, c))),
        point("60"))
    reference = (point("410"), point("300"))
    deviation = (point("1"), point("2"))
    error = (point("0"), point("0"))
    control = (Decimal("-0.3"), Decimal("0.3"))
    samples = {}
    stage_enclosures = []

    for stage in range(60):
        x1, x2 = reference
        q1, q2 = deviation
        f1 = subtract(multiply(a, x1), multiply(b, multiply(x1, x2)))
        f2 = add(negate(multiply(c, x2)), multiply(d, multiply(x1, x2)))
        next_reference = (add(x1, multiply(t0, f1)),
                          add(x2, multiply(t0, f2)))

        a11 = add(point("1"), multiply(t0, subtract(a, multiply(b, x2))))
        a12 = negate(multiply(t0, multiply(b, x1)))
        a21 = multiply(t0, multiply(d, x2))
        a22 = add(point("1"), multiply(t0, add(negate(c), multiply(d, x1))))
        bu = multiply(multiply(t0, gain), control)
        next_deviation = (
            add(add(multiply(a11, q1), multiply(a12, q2)), bu),
            add(multiply(a21, q1), multiply(a22, q2)))

        # Exact nonlinear remainder relative to the affine tangent at reference.
        bilinear = multiply(t0, multiply(q1, q2))
        remainder = (negate(multiply(b, bilinear)), multiply(d, bilinear))
        next_error = (
            add(add(multiply(a11, error[0]), multiply(a12, error[1])), remainder[0]),
            add(add(multiply(a21, error[0]), multiply(a22, error[1])), remainder[1]))

        reference, deviation, error = next_reference, next_deviation, next_error
        stage_enclosures.append({
            "stage": stage + 1,
            "reference": [show(value) for value in reference],
            "deviation": [show(value) for value in deviation],
            "physical_state": [show(add(x, q)) for x, q in zip(reference, deviation)],
            "linearization_error": [show(value) for value in error],
        })
        if stage + 1 in (1, 5, 10, 20, 40, 60):
            samples[str(stage + 1)] = {
                "reference": [show(value) for value in reference],
                "deviation": [show(value) for value in deviation],
                "linearization_error": [show(value) for value in error],
            }

    max_abs = [max(bound.copy_abs() for bound in coordinate) for coordinate in error]
    norm_squared = add(multiply((max_abs[0], max_abs[0]),
                                (max_abs[0], max_abs[0])),
                       multiply((max_abs[1], max_abs[1]),
                                (max_abs[1], max_abs[1])))
    norm_bound = square_root(norm_squared)[1]
    result = {
        "schema": "csl.l05-corrected-track-error-tube/1",
        "track": "owner-authorized corrected comparison; not historical L05 reproduction",
        "source_references": {
            "paper": {
                "path": "papers/papers_for_professor/1063.pdf",
                "sha256": "9327fdc6d4a24258d458d8c80bc5c983ef63b2245eeadce99475e8e66c6942bf",
                "pages": "PDF pp. 8-9 (printed pp. 59-60)",
            },
            "candidate_step_grouping": {
                "path": "papers/Siberia/Volterra.m",
                "sha256": "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1",
                "scope": "candidate source only; does not identify the Table 1 driver",
            },
        },
        "assumptions": {
            "model": "printed discrete Lotka-Volterra recurrence; T0=(2*pi/sqrt(a*c))/60",
            "coordinates": "physical state = zero-control reference + deviation",
            "reference_initial": ["410", "300"],
            "deviation_initial": ["1", "2"],
            "control_interval_each_stage": ["-0.3", "0.3"],
            "horizon": 60,
            "constraints": "none; L05 Example 1 supplies no common state-constraint set",
            "pairing": "same control sequence for nonlinear deviation and affine surrogate",
        },
        "arithmetic": {
            "decimal_precision_digits": PRECISION,
            "rounding": "directed floor/ceiling for every interval arithmetic operation",
            "pi_interval": show(pi),
            "t0_interval": show(t0),
            "assurance_scope": "outward enclosure for the stated recurrence and assumptions",
        },
        "linearization_error_coordinate_bounds_at_stage_60": [show(value) for value in error],
        "euclidean_hausdorff_upper_bound": str(norm_bound),
        "stage_enclosures": stage_enclosures,
        "stage_samples": samples,
        "interpretation": "For every shared 60-control sequence, the paired physical trajectories differ by at most the reported Euclidean bound. The same pairing gives both directed set-distance bounds between the two reachable sets.",
        "limits": [
            "The initial deviation interpretation and T0 grouping are explicit assumptions, not a recovered paper coordinate transform or Table 1 run identity.",
            "The bound is conservative interval arithmetic and is not a measured distance or a claim about the paper's historical nonlinear plot.",
            "No stage constraints, discretization discrepancy, or external implementation error is included; the model itself is the printed discrete recurrence.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    run()

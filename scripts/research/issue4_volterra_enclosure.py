"""Validated box propagation for the hash-identified L05 companion candidate.

This is a fresh transcription of the recurrence, not a copy of private MATLAB.
All interval endpoints are integers in units of 10^-15. Every multiplication
rounds out, including construction of the step-size and reference matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


SCALE = 10**15
SOURCE_SHA256 = "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"


def floor_fraction(x: Fraction) -> int:
    return x.numerator // x.denominator


def ceil_fraction(x: Fraction) -> int:
    return -floor_fraction(-x)


@dataclass(frozen=True)
class Box:
    lo: int
    hi: int

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise ValueError("reversed interval")

    @staticmethod
    def rational(value: Fraction) -> Box:
        return Box(floor_fraction(value * SCALE), ceil_fraction(value * SCALE))

    def __add__(self, other: Box) -> Box:
        return Box(self.lo + other.lo, self.hi + other.hi)

    def __neg__(self) -> Box:
        return Box(-self.hi, -self.lo)

    def __sub__(self, other: Box) -> Box:
        return self + -other

    def __mul__(self, other: Box) -> Box:
        products = (
            self.lo * other.lo,
            self.lo * other.hi,
            self.hi * other.lo,
            self.hi * other.hi,
        )
        return Box(min(products) // SCALE, -((-max(products)) // SCALE))

    def strings(self) -> list[str]:
        return [fixed(self.lo), fixed(self.hi)]


def fixed(value: int) -> str:
    sign = "-" if value < 0 else ""
    digits = str(abs(value)).zfill(16)
    return f"{sign}{digits[:-15]}.{digits[-15:]}"


def arctan_bounds(inverse: int, terms: int = 24) -> tuple[Fraction, Fraction]:
    def partial(count: int) -> Fraction:
        return sum(
            (Fraction(-1 if k % 2 else 1, (2 * k + 1) * inverse ** (2 * k + 1))
             for k in range(count)),
            Fraction(),
        )

    adjacent = (partial(terms), partial(terms + 1))
    return min(adjacent), max(adjacent)


def step_box() -> Box:
    a5_lo, a5_hi = arctan_bounds(5)
    a239_lo, a239_hi = arctan_bounds(239)
    pi_lo = 16 * a5_lo - 4 * a239_hi
    pi_hi = 16 * a5_hi - 4 * a239_lo
    root_lo_i = math.isqrt(2 * SCALE * SCALE)
    root_hi_i = root_lo_i + 1
    # pi/(18 sqrt(2)); all denominator endpoints are strictly positive.
    return Box(
        floor_fraction(pi_lo * SCALE * SCALE / (18 * root_hi_i)),
        ceil_fraction(pi_hi * SCALE * SCALE / (18 * root_lo_i)),
    )


def run() -> dict:
    q = lambda n, d=1: Box.rational(Fraction(n, d))
    a, b, c, d, input_gain = q(9, 10), q(3, 1000), q(4, 5), q(1, 500), q(17, 20)
    step = step_box()
    control = Box(-3 * SCALE // 10, 3 * SCALE // 10)
    reference = [q(410), q(300)]
    linear = [q(1), q(2)]
    nonlinear = [q(1), q(2)]
    error = [q(0), q(0)]
    rows = []
    for stage in range(1, 61):
        r1, r2 = reference
        reference = [
            r1 + step * (a * r1 - b * r1 * r2),
            r2 + step * (-c * r2 + d * r1 * r2),
        ]
        r1, r2 = reference  # candidate matrix reads the next reference sample
        matrix = [
            [q(1) + step * (a - b * r2), -(step * b * r1)],
            [step * d * r2, q(1) + step * (-c + d * r1)],
        ]
        drive = step * input_gain * control

        def affine(state: list[Box]) -> list[Box]:
            return [
                matrix[0][0] * state[0] + matrix[0][1] * state[1] + drive,
                matrix[1][0] * state[0] + matrix[1][1] * state[1],
            ]

        product = nonlinear[0] * nonlinear[1]
        nonlinear_next = affine(nonlinear)
        nonlinear = [nonlinear_next[0] - step * b * product,
                     nonlinear_next[1] + step * d * product]
        linear = affine(linear)
        # The identical control cancels algebraically in this recurrence.
        error = [matrix[0][0] * error[0] + matrix[0][1] * error[1] - step * b * product,
                 matrix[1][0] * error[0] + matrix[1][1] * error[1] + step * d * product]
        rows.append({
            "stage": stage,
            "reference": [x.strings() for x in reference],
            "linear": [x.strings() for x in linear],
            "nonlinear": [x.strings() for x in nonlinear],
            "same_control_error": [x.strings() for x in error],
        })
    radius = max(abs(v) for coordinate in error for v in (coordinate.lo, coordinate.hi))
    return {
        "schema": "issue4-volterra-enclosure-v1",
        "candidate_source_sha256": SOURCE_SHA256,
        "candidate_source_status": "private companion candidate; not a Table 1 generator identification",
        "arithmetic": "integer outward intervals at scale 10^-15; Machin alternating series and integer sqrt bracket",
        "step_size": step.strings(),
        "control_each_stage": control.strings(),
        "initial_linear_and_nonlinear": ["1", "2"],
        "reference_initial": ["410", "300"],
        "error_linf_upper": fixed(radius),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="optional private candidate for hash verification")
    args = parser.parse_args()
    if args.source and hashlib.sha256(args.source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise SystemExit("candidate source SHA-256 mismatch")
    record = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

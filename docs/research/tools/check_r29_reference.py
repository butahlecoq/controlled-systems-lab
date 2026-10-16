"""Exact-rational R29 corrected scalar-input reachability reference.

This checks an explicitly inferred input interpretation, not the historical
program, numerical timing, or an optimal control family.
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO = ROOT / "benchmarks/scenarios/r29-corrected-scalar-reference.json"


def rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("R29 coefficients must be exact integer or rational strings")
    return Fraction(value)


def show(value):
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def public_digest(raw):
    return hashlib.sha256(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def matvec(matrix, vector):
    return tuple(sum((row[j] * vector[j] for j in range(len(vector))), Fraction(0))
                 for row in matrix)


def add(left, right):
    return tuple(a + b for a, b in zip(left, right))


def scale(factor, vector):
    return tuple(factor * value for value in vector)


def reference(scenario_path):
    raw = scenario_path.read_bytes()
    scenario = json.loads(raw)
    if (scenario["schema_version"] != 1 or
            scenario["status"] != "editorial_reference_not_historical_run" or
            scenario["inferred_interpretation"]["authority"] !=
            "editorial_mathematical_inference_not_recovered_run_input"):
        raise ValueError("R29 provenance must identify the editorial interpretation")
    printed = scenario["printed"]
    dimension = printed["state_dimension"]
    horizon = printed["horizon"]
    if dimension != 4 or horizon != 16 or printed["control_dimension"] != 1:
        raise ValueError("R29 printed dimensions or horizon changed")
    matrix = tuple(tuple(map(rational, row)) for row in printed["A"])
    b = tuple(map(rational, printed["B"]))
    x0 = tuple(map(rational, printed["initial_center"]))
    diagonal = tuple(map(rational, printed["initial_generator_diagonal"]))
    lower, upper = map(rational, printed["scalar_bound"])
    control_center = rational(scenario["inferred_interpretation"]["control_center"])
    control_generator = rational(scenario["inferred_interpretation"]["control_generator"])
    if (len(matrix) != dimension or any(len(row) != dimension for row in matrix) or
            len(b) != dimension or len(x0) != dimension or len(diagonal) != dimension or
            (lower, upper, control_center, control_generator) !=
            (Fraction(-1), Fraction(1), Fraction(0), Fraction(1))):
        raise ValueError("R29 printed shape or inferred scalar interval changed")
    identity = tuple(tuple(Fraction(i == j) for j in range(dimension))
                     for i in range(dimension))
    n = tuple(tuple(matrix[i][j] - identity[i][j] for j in range(dimension))
              for i in range(dimension))
    for j in range(dimension):
        unit = tuple(Fraction(i == j) for i in range(dimension))
        if matvec(n, matvec(n, unit)) != (Fraction(0),) * dimension:
            raise ValueError("R29 closed-form oracle requires (A-I)^2=0")

    def power_on(vector, exponent):
        return add(vector, scale(exponent, matvec(n, vector)))

    initial_columns = [tuple(diagonal[j] if i == j else Fraction(0)
                             for i in range(dimension)) for j in range(dimension)]
    center = x0
    columns = initial_columns.copy()
    factor_ids = [f"x0.{j}" for j in range(dimension)]
    counts = []
    for stage in range(horizon + 1):
        expected_center = power_on(x0, stage)
        expected_columns = [power_on(column, stage) for column in initial_columns]
        expected_columns.extend(power_on(scale(control_generator, b), stage - 1 - k)
                                for k in range(stage))
        if center != expected_center or columns != expected_columns or len(factor_ids) != dimension + stage:
            raise RuntimeError(f"R29 recurrence disagrees with independent closed form at stage {stage}")
        counts.append(len(columns))
        if stage < horizon:
            center = add(matvec(matrix, center), scale(control_center, b))
            columns = [matvec(matrix, column) for column in columns]
            columns.append(scale(control_generator, b))
            factor_ids.append(f"u.{stage}")

    coordinate_intervals = []
    for i in range(dimension):
        radius = sum((abs(column[i]) for column in columns), Fraction(0))
        coordinate_intervals.append([show(center[i] - radius), show(center[i] + radius)])

    return {
        "scenario_id": scenario["id"],
        "status": scenario["status"],
        "public_digest_convention": "utf8-lf",
        "scenario_sha256": public_digest(raw),
        "checker_sha256": public_digest(Path(__file__).read_bytes()),
        "source_id": scenario["sources"]["paper_id"],
        "source_sha256": scenario["sources"]["paper_sha256"],
        "editable_source_id": scenario["sources"]["editable_source_id"],
        "editable_source_sha256": scenario["sources"]["editable_source_sha256"],
        "arithmetic": "exact rational (Python Fraction); no floating conversion",
        "horizon": horizon,
        "closed_form_verified_stages": horizon + 1,
        "generator_count_by_stage": counts,
        "terminal_center_exact": list(map(show, center)),
        "terminal_factor_ids": factor_ids,
        "terminal_generator_columns_exact": [list(map(show, column)) for column in columns],
        "terminal_coordinate_intervals_exact": coordinate_intervals,
        "historical_run_reproduced": False,
        "limitations": [
            "Scalar P(t)=Z(0,[1]) and independent temporal factor IDs are an editorial interpretation of the printed scalar bound, not recovered executable input.",
            "This is unreduced nominal reachable-set propagation from a set-valued initial condition, not an optimal family or historical timing result.",
            "Exact rational reference arithmetic does not validate the separate binary64 generator adapter or any numerical enclosure."
        ]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--verify-record", type=Path)
    args = parser.parse_args()
    result = reference(args.scenario)
    if args.verify_record:
        if result != json.loads(args.verify_record.read_text(encoding="utf-8")):
            raise RuntimeError("R29 saved exact reference differs from computed result")
        print("R29 corrected scalar reference verified")
    else:
        print(json.dumps(result, indent=2))

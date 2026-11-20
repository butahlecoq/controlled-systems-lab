"""Check SDK generator output against exact adjoint propagation of stored inputs."""

import csv
import json
import math
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent
HORIZON = 3
DIRECTION_COUNT = 32
RELATIVE_TOLERANCE = Fraction(1, 10**12)


def dyadic(value):
    return Fraction.from_float(float(value))


def load_records():
    records = defaultdict(lambda: defaultdict(dict))
    with (ROOT / "models.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (int(row["row"]), int(row["column"]))
            values = records[row["model"]][row["kind"]]
            if key in values:
                raise ValueError(f"duplicate matrix entry: {row}")
            values[key] = dyadic(row["value"])
    return records


def projected_support(records, stage, i, j, dx, dy):
    """Apply the transposed A recursion, without forming or reading any generators."""
    y = {i: dx, j: dy}
    external = records.get("nominal_w", {})
    options = {
        row: sum(
            records["G"].get((row, col), 0) * value
            for ((col, _), value) in external.items()
        )
        for row, _ in records["x0"]
    }
    A = [(row, col, v) for (row, col), v in records["A"].items() if v]
    B = [(row, col, v) for (row, col), v in records["B"].items() if v]
    support = 0
    magnitude = 0
    for _ in range(stage):
        coeffs = defaultdict(Fraction)
        for row, col, value in B:
            if y.get(row):
                coeffs[col] += value * y[row]
        radius = sum(map(abs, coeffs.values()))
        translation = [value * options[row] for row, value in y.items()]
        support += radius + sum(translation)
        magnitude += radius + sum(map(abs, translation))
        before = defaultdict(Fraction)
        for row, col, value in A:
            if y.get(row):
                before[col] += value * y[row]
        y = before
    initial = [value * records["x0"][row, 0] for row, value in y.items()]
    return support + sum(initial), max(1, magnitude + sum(map(abs, initial)))


def directions(n, model):
    for i in range(n):
        for sign in (1.0, -1.0):
            yield i, (i + 1) % n, sign, 0.0
    i = 27 if model == "catalogue-2026/model-26/1" else 0
    for k in range(DIRECTION_COUNT):
        angle = 2 * math.pi * k / DIRECTION_COUNT
        yield i, i + 1, math.cos(angle), math.sin(angle)


def check(path):
    models = load_records()
    saved = defaultdict(list)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            saved[row["model"], int(row["stage"])].append(row)
    expected_keys = {(model, stage) for model in models for stage in range(HORIZON + 1)}
    if len(models) != 35 or set(saved) != expected_keys:
        raise ValueError("model or stage coverage mismatch")
    residual = Fraction(0)
    normalized = Fraction(0)
    count = 0
    for (model, stage), rows in saved.items():
        records = models[model]
        for row, direction in zip(
            rows, directions(len(records["x0"]), model), strict=True
        ):
            i, j, dx, dy = direction
            if (
                (int(row["i"]), int(row["j"])) != (i, j)
                or not math.isclose(float(row["dx"]), dx, abs_tol=2e-15)
                or not math.isclose(float(row["dy"]), dy, abs_tol=2e-15)
            ):
                raise ValueError(f"unexpected direction at {model} stage {stage}")
            a, b = dyadic(row["dx"]), dyadic(row["dy"])
            reference, scale = projected_support(records, stage, i, j, a, b)
            support = dyadic(row["support"])
            error = abs(reference - support)
            witness_error = abs(
                a * dyadic(row["witness_x"]) + b * dyadic(row["witness_y"]) - support
            )
            if max(error, witness_error) > RELATIVE_TOLERANCE * scale:
                raise ValueError(f"support or witness outside tolerance: {row}")
            residual = max(residual, error)
            normalized = max(normalized, error / scale)
            count += 1
    return {
        "models": len(models),
        "model_stages": len(saved),
        "support_checks": count,
        "nominal_external_models": sum(
            bool(record.get("nominal_w")) for record in models.values()
        ),
        "max_absolute_support_error": float(residual),
        "max_scaled_support_error": float(normalized),
        "scaled_tolerance": float(RELATIVE_TOLERANCE),
    }


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1])), indent=2))

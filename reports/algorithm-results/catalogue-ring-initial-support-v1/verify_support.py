"""Certify the archived fixed-initial-state query with a zero-control witness."""

import argparse
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile

REVISION = "e9c95871b7ec8ff31b16104919e6c93d79e1419f"
ARCHIVE_SHA256 = "b393255e8c91049363a8e718e2063e04fc2f31c0f56e69e4e587a99a5926c92a"
ARCHIVE = "catalogue-feasible-history-evidence.zip"


def exact_json(payload):
    return json.loads(payload, parse_float=lambda value: Fraction(float(value)))


def matrix(data):
    rows, cols = data["rows"], data["cols"]
    values = data["values"]
    if len(values) != rows * cols:
        raise ValueError("invalid matrix shape")
    return [values[i * cols : (i + 1) * cols] for i in range(rows)]


def dot(left, right):
    return sum(x * y for x, y in zip(left, right, strict=True))


def bound(value, limits):
    lower, upper = limits
    if (lower is not None and value < lower) or (upper is not None and upper < value):
        raise ValueError(f"witness violates bound {limits}")


def certify(record):
    profile = record["full_history"]
    model = record["model_id"]
    if model != "catalogue-2026/model-30/1":
        raise ValueError(f"unexpected model {model}")
    (sample,) = [row for row in profile["samples"] if row["status"] == "undetermined"]
    if sample["stage"] != 0 or sample["direction"] != [-1, -1]:
        raise ValueError("expected fixed initial-state support in direction (-1, -1)")
    constraints = record["constraints"]
    if set(constraints) != {"state", "control", "positive_part", "stage", "terminal"}:
        raise ValueError("unexpected constraint schema")
    if constraints["stage"] or constraints["terminal"]:
        raise ValueError("this certificate expects no additional stage or terminal rows")
    a, b, g = (matrix(record[k]) for k in ("A", "B", "G"))
    state = record["initial"]
    states = [state]
    control_count = len(b[0])
    commands = [0] * control_count
    for control_bounds, budgets, disturbance in zip(
        constraints["control"],
        constraints["positive_part"],
        record["external"],
        strict=True,
    ):
        for value, limits in zip(commands, control_bounds, strict=True):
            bound(value, limits)
        for budget in budgets:
            if set(budget) != {"indices", "upper"}:
                raise ValueError("unexpected positive-part bound schema")
            total = sum(max(0, commands[i]) for i in budget["indices"])
            bound(total, (None, budget["upper"]))
        state = [
            dot(ax, state) + dot(bu, commands) + dot(gw, disturbance) + offset
            for ax, bu, gw, offset in zip(a, b, g, record["offset"], strict=True)
        ]
        states.append(state)
    for state, state_bounds in zip(states, constraints["state"], strict=True):
        for value, limits in zip(state, state_bounds, strict=True):
            bound(value, limits)
    direction = [-1, -1]
    support = dot(direction, [states[0][i] for i in record["plane"]])
    return {
        "model_id": model,
        "stage": 0,
        "projection_zero_based": record["plane"],
        "direction": direction,
        "native_status": sample["status"],
        "certificate_status": "exact-optimal",
        "support": str(support),
        "support_decimal": float(support),
        "witness_controls": [commands for _ in states[1:]],
        "witness_states": [list(map(str, row)) for row in states],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path(__file__).with_name(ARCHIVE))
    args = parser.parse_args()

    archive = args.archive.read_bytes()
    archive_sha = hashlib.sha256(archive).hexdigest()
    if archive_sha != ARCHIVE_SHA256:
        raise SystemExit(f"Unexpected input archive SHA-256: {archive_sha}")
    with ZipFile(io.BytesIO(archive)) as handle:
        raw = handle.read("raw/30.json")
        certificate = certify(exact_json(raw))
        audit = exact_json(handle.read("independent-audit.json"))
    (reference,) = [
        row for row in audit["30"]["full_history"]["samples"] if row["native"] == "undetermined"
    ]
    if certificate["support_decimal"] != float(reference["reference_support"]):
        raise ValueError("rounded exact support differs from archived condensed reference")
    print(
        json.dumps(
            {
                "revision": REVISION,
                "archive_sha256": archive_sha,
                "record_sha256": hashlib.sha256(raw).hexdigest(),
                **certificate,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Validate OPT-11 raw JSONL, complete paired trials, exact certificates and literal hulls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .oracle import FIXTURES, convex_hull, exact_certificate, q, require
else:
    from oracle import FIXTURES, convex_hull, exact_certificate, q, require

METHODS = {"baseline", "recursive"}


def validate_stream(path: Path, purpose: str) -> dict:
    require(purpose in {"smoke", "measurement", "test"}, "unknown purpose")
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL line {line_no}") from error
    calls, pairs, positions = {}, {}, {}
    for ordinal, row in enumerate(rows):
        require(row.get("purpose") == purpose, "mixed or incorrect purpose")
        fixture, round_id = row.get("fixture"), row.get("round")
        require(fixture in FIXTURES and type(round_id) is int, "unknown fixture or invalid round")
        key = fixture, round_id
        if row.get("kind") == "call":
            method = row.get("method")
            require(method in METHODS and key + (method,) not in calls, "duplicate or unknown method call")
            require(row.get("points") == FIXTURES[fixture], "fixture bytes differ from literal catalogue")
            require(row.get("problem") == f"opt11-{fixture}", "point cloud problem identity mismatch")
            require(type(row.get("elapsed_ns")) is int and row["elapsed_ns"] >= 0, "invalid call duration")
            require(row.get("status") in {"complete", "incomplete", "diagnostics"}, "unknown outcome status")
            if row["status"] != "diagnostics":
                exact_certificate(row)
                directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1))
                retained_points = [row["points"][i] for i in row["retained"]]
                expected_support = [max(sum(q(p[k]) * d[k] for k in range(2)) for p in row["points"])
                                    for d in directions]
                actual_support = [max(sum(q(p[k]) * d[k] for k in range(2)) for p in retained_points)
                                  for d in directions]
                require(actual_support == expected_support and
                        [q(value) for value in row.get("support", [])] == expected_support,
                        "literal support values differ from exact full input")
                require(len(row.get("attempts", [])) == row.get("lp_calls"),
                        "per-call LP attempt outcomes are incomplete")
            if method == "recursive" and row["status"] != "diagnostics":
                metrics = row.get("recursive")
                require(isinstance(metrics, dict), "recursive metrics absent")
                require(metrics["leaf_lp_calls"] + metrics["merge_lp_calls"] == row["lp_calls"],
                        "recursive LP metrics do not add to total calls")
            calls[key + (method,)] = row
            positions[key + (method,)] = ordinal
        elif row.get("kind") == "pair":
            require(key not in pairs, "duplicate pair row")
            expected_warmup = round_id == 0 and purpose != "test"
            require(type(row.get("warmup")) is bool and
                    row["warmup"] == expected_warmup, "warmup identity mismatch")
            pairs[key] = row
        else:
            require(row.get("kind") == "describe", "unknown raw row type")
    rounds = 1 if purpose in {"smoke", "test"} else 7
    expected_keys = {(fixture, r) for fixture in FIXTURES for r in range(rounds)}
    require(set(pairs) == expected_keys, "missing or extra paired fixture rounds")
    require(set(calls) == {(f, r, method) for f, r in expected_keys for method in METHODS},
            "missing or extra method calls")
    for key, pair in pairs.items():
        baseline = calls[key + ("baseline",)]
        recursive = calls[key + ("recursive",)]
        actual_recursive_first = positions[key + ("recursive",)] < positions[key + ("baseline",)]
        require(pair.get("recursive_first") is actual_recursive_first and
                baseline["warmup"] == pair["warmup"] == recursive["warmup"], "pair ordering mismatch")
        if baseline["status"] != "diagnostics" and recursive["status"] != "diagnostics":
            bhull = convex_hull([FIXTURES[key[0]][i] for i in baseline["retained"]])
            rhull = convex_hull([FIXTURES[key[0]][i] for i in recursive["retained"]])
            require(bhull == rhull, "baseline and recursive exact hull vertices differ")
    return {"purpose": purpose, "fixtures": len(FIXTURES), "pairs": len(pairs),
            "calls": len(calls), "exact_certificates": sum(len(c["removed"]) for c in calls.values()),
            "noncomplete_calls": sum(row.get("status") != "complete" for row in calls.values()),
            "paired_matrix_complete": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--purpose", choices=("smoke", "measurement", "test"), required=True)
    args = parser.parse_args()
    print(json.dumps(validate_stream(args.path, args.purpose), sort_keys=True))


if __name__ == "__main__":
    main()

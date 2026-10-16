"""Check every raw OPT-07 call and the complete batch protocol without a solver."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from oracle import FIXTURES, require, validate_call


def validate_stream(path: Path, purpose: str) -> dict:
    require(purpose in ("smoke", "measurement"), "unknown purpose")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL line {number}") from error
    expected_calls = 1 if purpose == "smoke" else 100
    expected_rounds = 1 if purpose == "smoke" else 8
    groups = {}
    batches = {}
    for row in rows:
        require(row.get("purpose") == purpose, "mixed or wrong run purpose")
        case_id = row.get("case_id")
        round_id = row.get("round")
        warmup = row.get("warmup")
        require(case_id in FIXTURES and type(round_id) is int and
                0 <= round_id < expected_rounds and type(warmup) is bool and
                warmup == (round_id == 0), "invalid batch identity")
        key = (case_id, round_id)
        kind = row.get("kind")
        if kind == "call":
            validate_call(row)
            groups.setdefault(key, []).append(row)
        elif kind == "batch":
            require(key not in batches, "duplicate batch row")
            require(type(row.get("calls")) is int and row["calls"] == expected_calls and
                    row.get("verified_calls") == expected_calls and
                    type(row.get("elapsed_ns")) is int and row["elapsed_ns"] >= 0,
                    "invalid batch count or elapsed time")
            batches[key] = row
        else:
            raise ValueError("unknown raw row kind")
    expected = {(case_id, round_id)
                for case_id in FIXTURES for round_id in range(expected_rounds)}
    require(set(groups) == expected and set(batches) == expected,
            "missing or extra fixture batch")
    for key, calls in groups.items():
        require(len(calls) == expected_calls and
                sorted(row.get("ordinal") for row in calls) == list(range(expected_calls)),
                "missing, duplicate or extra call in batch")
    return {"purpose": purpose, "fixtures": len(FIXTURES),
            "batches": len(batches), "calls": sum(map(len, groups.values()))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--purpose", choices=("smoke", "measurement"), required=True)
    args = parser.parse_args()
    print(json.dumps(validate_stream(args.path, args.purpose), sort_keys=True))


if __name__ == "__main__":
    main()

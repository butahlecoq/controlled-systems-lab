"""Capture paired B09 calls in alternating objective order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def capture(executable: Path, rounds: int) -> list[dict]:
    rows = []
    order = 0
    for round_index in range(1, rounds + 1):
        for lambda_value in (0, 1):
            result = subprocess.run([str(executable), "--lambda", str(lambda_value), "--measure", "1"],
                                    check=True, capture_output=True, text=True)
            pair = [json.loads(line) for line in result.stdout.splitlines()]
            if len(pair) != 2 or [row["batch"] for row in pair] != [0, 1]:
                raise ValueError("driver must emit one warmup and one measured row")
            for row, phase in zip(pair, ("excluded_warmup", "measured")):
                row["phase"] = phase
                row["alternation_round"] = round_index
                row["capture_order"] = order
                order += 1
                rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        raise ValueError("rounds must be positive")
    rows = capture(args.executable.resolve(), args.rounds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

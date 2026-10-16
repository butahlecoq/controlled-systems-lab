"""Bounded public-API GEO-07 functional check; never a measured report."""
from __future__ import annotations

import json
import subprocess
import sys

SOURCE = "db7906cb33ca40da55e31b9bf6b21cf7ffcc1ee4"
EXPECTED = {
    "box_image": {"status": "passed", "center": [7.0], "generators": [2.0, 3.0],
                  "factor_ids": ["horizontal", "vertical"],
                  "physical_witnesses": [2, 7, 12, 8], "outside_points": [1, 13]},
    "shared_cancellation": {"status": "passed", "center": [0.0], "generators": [0.0],
                            "factor_ids": ["history.0"],
                            "physical_witnesses": [0, 0, 0], "outside_points": [-1, 1]},
    "constrained_sum": {"status": "passed", "center": [0.0, 0.0],
                        "generators": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
                        "factor_ids": ["u", "v", "w"],
                        "equalities": [1.0, -1.0, 0.0, 1.0, 0.0, 1.0],
                        "physical_witnesses": [[0, 0], [0, 0]],
                        "outside_points": [[0, 1], [0, -1]]},
}


def parse_lines(data: bytes) -> list[dict]:
    if not data.endswith(b"\n"):
        raise ValueError("unterminated driver event")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    return [json.loads(line, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(
        ValueError("nonfinite JSON number"))) for line in data.splitlines()]


def validate(rows: list[dict], *, repetitions: int, warmups: int, batch: int) -> None:
    if repetitions < 1 or warmups not in (0, 1) or batch < 1:
        raise ValueError("invalid collection profile")
    names = list(EXPECTED)
    order = [(name, 0, True) for name in names] if warmups else []
    order += [(name, round_number, False)
              for round_number in range(repetitions)
              for name in (names if round_number % 2 == 0 else names[::-1])]
    if len(rows) != len(order):
        raise ValueError("missing or extra GEO-07 event")
    for row, (name, round_number, warmup) in zip(rows, order):
        if (row.get("schema") != "csl.geo07-generator-trial/1" or
                row.get("fixture") != name or row.get("round") != round_number or
                row.get("warmup") is not warmup or row.get("batch") != batch or
                row.get("checked_calls") != batch or row.get("status") != "passed" or
                row.get("error") is not None or
                json.dumps(row.get("result"), sort_keys=True) != json.dumps(EXPECTED[name], sort_keys=True) or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 0):
            raise ValueError("GEO-07 trial envelope, oracle result, or work count differs")


def main(executable: str) -> None:
    described = subprocess.run([executable, "--describe"], capture_output=True, check=True)
    if described.stderr:
        raise ValueError("driver describe wrote stderr")
    description = parse_lines(described.stdout)
    if (len(description) != 1 or description[0].get("source_commit") != SOURCE or
            description[0].get("module") != "CSL::geometry_generators" or
            description[0].get("fixtures") != list(EXPECTED)):
        raise ValueError("driver source identity or fixture catalogue differs")
    completed = subprocess.run([executable, "--smoke"], capture_output=True, check=True)
    if completed.stderr:
        raise ValueError("driver smoke wrote stderr")
    validate(parse_lines(completed.stdout), repetitions=1, warmups=0, batch=1)


if __name__ == "__main__":
    main(sys.argv[1])

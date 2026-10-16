"""Bounded public registered-port check; never a timed report."""
from __future__ import annotations

import subprocess
import sys

from collect import DESCRIPTION_SCHEMA, EXPECTED, SOURCE, TRIAL_SCHEMA, admit_description, json_bytes, parse_raw


def validate(raw: bytes) -> None:
    rows = parse_raw(raw)
    if len(rows) != len(EXPECTED):
        raise ValueError("missing or extra port smoke event")
    for row, name in zip(rows, EXPECTED):
        if (row.get("schema") != TRIAL_SCHEMA or row.get("fixture") != name or
                row.get("round") != 0 or row.get("warmup") is not False or
                row.get("batch") != 1 or row.get("checked_calls") != 1 or
                row.get("status") != "passed" or row.get("error") is not None or
                json_bytes(row.get("result")) != json_bytes(EXPECTED[name]) or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 0):
            raise ValueError("port smoke oracle, event, or work count differs")


def main(executable: str) -> None:
    described = subprocess.run([executable, "--describe"], capture_output=True, check=True)
    if described.stderr:
        raise ValueError("driver describe wrote stderr")
    admit_description(described.stdout)
    description = parse_raw(described.stdout)
    if (len(description) != 1 or description[0].get("schema") != DESCRIPTION_SCHEMA or
            description[0].get("source_commit") != SOURCE or
            description[0].get("module") != "CSL::generator_adapter" or
            description[0].get("fixtures") != list(EXPECTED)):
        raise ValueError("port source identity or fixture catalogue differs")
    completed = subprocess.run([executable, "--smoke"], capture_output=True, check=True)
    if completed.stderr:
        raise ValueError("driver smoke wrote stderr")
    validate(completed.stdout)


if __name__ == "__main__":
    main(sys.argv[1])

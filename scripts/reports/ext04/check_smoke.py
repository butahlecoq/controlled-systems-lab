"""Bounded public replay smoke: one checked call per fixture, never a report."""
from __future__ import annotations

import subprocess
import sys

from collect import admit_description, parse_raw, EXPECTED, TRIAL_SCHEMA, json_bytes


def main(executable: str) -> None:
    described = subprocess.run([executable, "--describe"], capture_output=True, check=True)
    if described.stderr:
        raise ValueError("driver description wrote stderr")
    admit_description(described.stdout)
    completed = subprocess.run([executable, "--smoke"], capture_output=True, check=True)
    if completed.stderr:
        raise ValueError("driver smoke wrote stderr")
    rows = parse_raw(completed.stdout)
    if len(rows) != len(EXPECTED):
        raise ValueError("smoke fixture count differs")
    for row, (name, literal) in zip(rows, EXPECTED.items()):
        if (row.get("schema") != TRIAL_SCHEMA or row.get("fixture") != name or
                row.get("round") != 0 or row.get("warmup") is not False or
                row.get("batch") != 1 or row.get("checked_calls") != 1 or
                row.get("status") != "passed" or row.get("error") is not None or
                json_bytes(row.get("result")) != json_bytes(literal) or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] <= 0):
            raise ValueError("smoke literal replay result differs")


if __name__ == "__main__":
    main(sys.argv[1])

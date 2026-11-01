from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    executable = Path(sys.argv[1])
    completed = subprocess.run([str(executable), "--smoke"], check=True,
                               capture_output=True, text=True)
    if completed.stderr:
        raise ValueError("report smoke wrote unexpected stderr")
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    if len(rows) != 1:
        raise ValueError("expected one smoke record")
    row = rows[0]
    expected_branches = [
        {"catalogue_index": 0, "discrete_value": -1, "objective": 0,
         "complete_family_verified": True},
        {"catalogue_index": 1, "discrete_value": 0, "objective": 0,
         "complete_family_verified": True},
        {"catalogue_index": 2, "discrete_value": 1, "objective": 0,
         "complete_family_verified": True},
    ]
    if (row.get("schema") != "csl.ext02-portfolio-trial/1" or
        row.get("trial") != 0 or row.get("warmup") is not False or
        row.get("horizon") != 1 or row.get("catalogue_size") != 3 or
        row.get("history_count") != 3 or row.get("status") != "complete" or
        row.get("optimum") != 0 or row.get("branches") != expected_branches or
        type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] <= 0 or
        type(row.get("retained_relation_rows")) is not int or
        row["retained_relation_rows"] <= 0 or
        type(row.get("retained_relation_scalars")) is not int or
        row["retained_relation_scalars"] <= 0 or
        row.get("retained_numeric_bytes") != row["retained_relation_scalars"] * 8):
        raise ValueError("EXT-02 smoke record differs from the analytic oracle")


if __name__ == "__main__":
    main()

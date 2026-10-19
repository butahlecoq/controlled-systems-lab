"""Check the bounded APP-04 native report smoke path."""
from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys


def main(executable: Path) -> None:
    result = subprocess.run([str(executable), "smoke"], capture_output=True,
                            text=True, check=True)
    if result.stderr:
        raise ValueError("APP-04 smoke driver wrote stderr")
    rows = list(csv.DictReader(result.stdout.splitlines()))
    if len(rows) != 3 or [row["case"] for row in rows] != [
        "square-axis", "square-diagonal", "horizontal-segment"
    ]:
        raise ValueError("APP-04 smoke case inventory differs")
    for row in rows:
        if (row["phase"], row["calls"], row["status"], row["verified"],
            row["basis"]) != ("smoke", "1", "enclosed", "true", "v_ellipsoid"):
            raise ValueError("APP-04 smoke row lacks a verified enclosure")
        if int(row["elapsed_ns"]) <= 0:
            raise ValueError("APP-04 smoke duration must be positive")
    if float(rows[2]["radius_y"]) != 0:
        raise ValueError("Degenerate segment lost its zero radius")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

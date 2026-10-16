"""Literal public-port driver smoke check; no performance evidence."""
from __future__ import annotations

import subprocess
import sys

from collect import EXPECTED, admit_description, admit_rows


def main(executable: str) -> None:
    described = subprocess.run([executable, "--describe"], capture_output=True, timeout=30)
    if described.returncode or described.stderr:
        raise ValueError("driver description failed")
    admit_description(described.stdout)
    observed = subprocess.run([executable, "--smoke"], capture_output=True, timeout=30)
    if observed.returncode or observed.stderr:
        raise ValueError("driver smoke failed")
    rows, _ = admit_rows(observed.stdout, repetitions=1, batch=1, smoke=True)
    if [row["fixture"] for row in rows] != list(EXPECTED):
        raise ValueError("smoke fixture order differs")


if __name__ == "__main__":
    main(sys.argv[1])

#!/usr/bin/env python3
"""Validate and summarize the saved preliminary ITIS17 hull pilot rows."""

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    expected = 12 + 3 * 4 * 7
    if len(rows) != expected or any(row["passed"] is not True for row in rows):
        raise SystemExit(f"expected {expected} successful rows, got {len(rows)}")
    warmups = [row for row in rows if row["warmup"]]
    measured = [row for row in rows if not row["warmup"]]
    if len(warmups) != 12 or len(measured) != 84:
        raise SystemExit("unexpected warmup or measurement count")
    groups = defaultdict(list)
    for row in measured:
        groups[(row["fixture"], row["method"])].append(row["elapsed_ns"])
    if len(groups) != 12 or any(len(values) != 7 for values in groups.values()):
        raise SystemExit("expected seven measured repetitions per fixture and method")
    target.mkdir(parents=True, exist_ok=True)
    with (target / "raw-rows.jsonl").open("w") as output:
        for row in rows:
            output.write(json.dumps(row, sort_keys=True) + "\n")
    with (target / "summary.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("fixture", "method", "repetitions", "median_ns", "min_ns", "max_ns"))
        for (fixture, method), values in sorted(groups.items()):
            writer.writerow((fixture, method, len(values), int(statistics.median(values)), min(values), max(values)))
    print(f"validated {len(rows)} rows: {len(warmups)} warmups, {len(measured)} measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

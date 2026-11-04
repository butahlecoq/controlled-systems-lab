"""Validate and summarize EXT-07 capability-profile measurements."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
from collections import defaultdict

EXPECTED = {
    (1, 1, 1, 2, 1, 1),
    (2, 2, 1, 2, 1, 1),
    (4, 4, 1, 2, 1, 1),
    (8, 8, 1, 2, 1, 1),
    (1, 1, 2, 2, 2, 1),
    (1, 1, 4, 2, 2, 1),
    (1, 1, 8, 2, 2, 1),
    (1, 1, 4, 4, 4, 1),
    (1, 1, 4, 8, 8, 1),
    (1, 1, 8, 2, 4, 256),
}
PROFILE = ("state_dimension", "control_dimension", "horizon", "mode_count",
           "edge_count", "path_count")


def collect(raw: Path, output: Path) -> list[dict]:
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = tuple(row[field] for field in PROFILE)
        if row.get("calls") != 1000 or row.get("repetition") not in range(7):
            raise ValueError("Unexpected call count or repetition index")
        if row.get("family") not in {"single-chain", "parallel-branching"}:
            raise ValueError("Unexpected fixture family")
        groups[key].append(row)

    if set(groups) != EXPECTED or any(len(group) != 7 for group in groups.values()):
        raise ValueError("Raw rows do not contain the complete ten-profile, seven-repeat matrix")
    for group in groups.values():
        if {row["repetition"] for row in group} != set(range(7)):
            raise ValueError("A profile has missing or duplicate repetitions")
        if any(row["batch_ns"] <= 0 for row in group):
            raise ValueError("A measured batch must have positive elapsed time")

    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for key in sorted(groups):
        group = groups[key]
        durations = [row["batch_ns"] for row in group]
        profile = dict(zip(PROFILE, key))
        median_ns = statistics.median(durations)
        summary.append({
            **profile,
            "path_cap": group[0]["path_cap"],
            "family": group[0]["family"],
            "repetitions": len(group),
            "calls_per_batch": group[0]["calls"],
            "median_batch_ns": median_ns,
            "min_batch_ns": min(durations),
            "max_batch_ns": max(durations),
            "median_ns_per_call": median_ns / group[0]["calls"],
        })

    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for record in collect(args.raw, args.out):
        print(json.dumps(record, sort_keys=True))

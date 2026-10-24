#!/usr/bin/env python3
"""Validate and summarize the exploratory ITIS17 hull workload ladder."""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


METHODS = (
    "geometric-quickhull",
    "lp-membership-baseline",
    "basis-reuse-related-to-A43",
    "ordered-membership-related-to-A44",
    "A43-certificate-safe-basis-adaptation",
    "A44-incremental-LP-paper-adaptation",
)
SIZES = (250, 1000, 5000)


def read_rows(paths):
    rows = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    return rows


def key(row):
    return row["fixture"], row["method"], row["warmup"], row["round"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    raw_paths = sorted(args.raw_dir.glob("raw-*.jsonl"))
    if not raw_paths:
        raise SystemExit("no raw-*.jsonl files found")
    all_rows = read_rows(raw_paths)
    unique = {}
    duplicates = []
    for row in all_rows:
        if row["method"] not in METHODS:
            raise SystemExit(f"unexpected method: {row['method']}")
        if row["fixture"] not in {f"halton-square-n{size}" for size in SIZES}:
            raise SystemExit(f"unexpected fixture: {row['fixture']}")
        k = key(row)
        if k in unique:
            duplicates.append(k)
            continue
        unique[k] = row

    expected = {
        (f"halton-square-n{size}", method, warmup, round_number)
        for size in SIZES
        for method in METHODS
        for warmup, round_number in [(True, 0), *[(False, n) for n in range(1, 8)]]
    }
    if set(unique) != expected:
        missing = sorted(expected - set(unique))
        extra = sorted(set(unique) - expected)
        raise SystemExit(f"coverage mismatch: {len(missing)} missing, {len(extra)} extra")
    hashes = defaultdict(set)
    for row in unique.values():
        hashes[row["fixture"]].add(row["input_sha256"])
        if row["input_points"] not in SIZES:
            raise SystemExit("input point count does not match workload ladder")
    if any(len(values) != 1 for values in hashes.values()):
        raise SystemExit("input hash changed within a fixture")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(unique.values(), key=lambda r: (r["input_points"], r["warmup"], r["round"], r["method"]))
    with (args.output_dir / "validated-rows.jsonl").open("w", encoding="utf-8") as stream:
        for row in ordered:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    summaries = []
    for size in SIZES:
        fixture = f"halton-square-n{size}"
        for method in METHODS:
            trials = [unique[(fixture, method, False, n)] for n in range(1, 8)]
            passed = [r for r in trials if r["passed"]]
            times = [r["elapsed_ns"] / 1e6 for r in passed]
            summaries.append({
                "input_points": size,
                "method": method,
                "valid_trials": len(passed),
                "trials": len(trials),
                "median_valid_ms": statistics.median(times) if times else "",
                "min_valid_ms": min(times) if times else "",
                "max_valid_ms": max(times) if times else "",
                "failed_trials": sum(not r["passed"] for r in trials),
                "median_attempt_ms_all_trials": statistics.median(
                    [r["elapsed_ns"] / 1e6 for r in trials]),
                "median_retained": statistics.median([r["retained"] for r in trials]),
                "median_removed": statistics.median([r["removed"] for r in trials]),
            })
    with (args.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    (args.output_dir / "coverage.json").write_text(json.dumps({
        "expected_rows": len(expected),
        "raw_rows": len(all_rows),
        "unique_rows": len(unique),
        "duplicate_keys_preserved_by_first_observation": len(duplicates),
        "fixture_sha256": {fixture: next(iter(values)) for fixture, values in sorted(hashes.items())},
        "source_commits": sorted({r["source_commit"] for r in unique.values()}),
        "all_warmups_present": True,
        "all_seven_repetitions_present": True,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

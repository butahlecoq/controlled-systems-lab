#!/usr/bin/env python3
"""Validate and summarize the raw repeated ITIS17 dyadic pilot."""
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
EXPECTED_METHODS = {
    "geometric-quickhull",
    "lp-membership-baseline",
    "basis-reuse-related-to-A43",
    "ordered-membership-related-to-A44",
    "A43-certificate-safe-basis-adaptation",
    "A44-incremental-LP-paper-adaptation",
}
rows = []
for size in (64, 256):
    source = RAW / f"n{size}.jsonl"
    parsed = [json.loads(line) for line in source.read_text().splitlines() if line]
    if len(parsed) != 36:
        raise SystemExit(f"{source}: expected 36 rows, found {len(parsed)}")
    fixture = f"dyadic-square-n{size}"
    methods = {row["method"] for row in parsed}
    if methods != EXPECTED_METHODS:
        raise SystemExit(f"{source}: method set mismatch: {methods ^ EXPECTED_METHODS}")
    for method in EXPECTED_METHODS:
        attempts = [row for row in parsed if row["method"] == method]
        if sum(bool(row["warmup"]) for row in attempts) != 1:
            raise SystemExit(f"{source}: {method} must have one warmup")
        measured = [row for row in attempts if not row["warmup"]]
        if {row["round"] for row in measured} != set(range(1, 6)):
            raise SystemExit(f"{source}: {method} must have measured rounds 1..5")
        if any(row["fixture"] != fixture or row["input_points"] != size for row in attempts):
            raise SystemExit(f"{source}: unexpected fixture data for {method}")
    rows.extend(parsed)

with (ROOT / "validated-rows.jsonl").open("w") as out:
    for row in rows:
        out.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

summary = []
for size in (64, 256):
    for method in sorted(EXPECTED_METHODS):
        measured = [r for r in rows if r["fixture"] == f"dyadic-square-n{size}" and
                    r["method"] == method and not r["warmup"]]
        passed = [r for r in measured if r["passed"]]
        times = [r["elapsed_ns"] / 1_000_000 for r in passed]
        summary.append({
            "fixture": f"dyadic-square-n{size}", "method": method,
            "measured_attempts": len(measured), "passed": len(passed),
            "failed": len(measured) - len(passed),
            "retained_counts": ";".join(str(r["retained"]) for r in measured),
            "median_ms_of_passes": f"{statistics.median(times):.6f}" if times else "",
            "min_ms_of_passes": f"{min(times):.6f}" if times else "",
            "max_ms_of_passes": f"{max(times):.6f}" if times else "",
            "failed_elapsed_ms_diagnostic_only": ";".join(
                f"{r['elapsed_ns'] / 1_000_000:.6f}" for r in measured if not r["passed"]),
        })
with (ROOT / "summary.csv").open("w", newline="") as out:
    writer = csv.DictWriter(out, fieldnames=summary[0].keys())
    writer.writeheader()
    writer.writerows(summary)
print(f"validated {len(rows)} raw rows; wrote summary.csv and validated-rows.jsonl")

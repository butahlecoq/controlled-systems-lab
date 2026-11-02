#!/usr/bin/env python3
"""Summarize gprof flat profiles without treating them as performance timings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROW = re.compile(r"^\s*([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)\s+(.*)$")
PROFILE = re.compile(r"gprof-flat-t(02|04|08)-(reach-back|strategy-b)\.txt$")
SAMPLE_INTERVAL_SECONDS = 0.01


def summarize(path: Path) -> dict[str, object]:
    match = PROFILE.fullmatch(path.name)
    if not match:
        raise ValueError(f"unexpected profile filename: {path.name}")
    rows: list[tuple[float, float, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = ROW.match(line)
        if row:
            rows.append((float(row.group(1)), float(row.group(3)), row.group(4).strip()))
    if not rows:
        raise ValueError(f"profile has no flat-profile rows: {path}")
    sampled_seconds = sum(seconds for _, seconds, _ in rows)
    max_share = max(share for share, _, _ in rows)
    leaders = [line for share, _, line in rows if share == max_share]
    return {
        "horizon": int(match.group(1)),
        "strategy": match.group(2),
        "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
        "sampled_cpu_seconds": round(sampled_seconds, 2),
        "sampled_ticks": round(sampled_seconds / SAMPLE_INTERVAL_SECONDS),
        "largest_function_share_percent": max_share,
        "leading_rows": leaders,
        "function_rows_with_samples": sum(seconds > 0 for _, seconds, _ in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    profiles = sorted(args.profiles.glob("gprof-flat-t*-*.txt"))
    if len(profiles) != 6:
        parser.error(f"expected six horizon/strategy profiles, found {len(profiles)}")
    rows = [summarize(path) for path in profiles]
    if any(row["largest_function_share_percent"] >= 15 for row in rows):
        parser.error("a profile exceeds the report's 15% investigation threshold")
    payload = {
        "schema": "csl.review05.source-profile-matrix-summary/1",
        "claim": "flat gprof samples are source-attribution diagnostics, not performance timings",
        "profiles": rows,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"profiles": len(rows), "max_share_percent": max(
        row["largest_function_share_percent"] for row in rows), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

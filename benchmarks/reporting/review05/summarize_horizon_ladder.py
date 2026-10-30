#!/usr/bin/env python3
"""Summarize REVIEW-05 HORIZON-01 raw attempts without winner claims."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    attempts = [json.loads(line) for line in (bundle / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    checks = {row["attempt_id"]: row for row in (
        json.loads(line) for line in (bundle / "checks.jsonl").read_text(encoding="utf-8").splitlines() if line
    )}
    summaries = []
    for horizon in (2, 4, 8):
        rows = [row for row in attempts if row.get("horizon") == horizon and not row.get("warmup")]
        paired_times: dict[int, dict[str, int]] = defaultdict(dict)
        completed_times: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            result = row.get("result") or {}
            if row.get("process_status") == "completed" and isinstance(result.get("strategy_run_ns"), int):
                completed_times[row["strategy"]].append(result["strategy_run_ns"])
            check = checks.get(row.get("attempt_id"), {})
            if row.get("process_status") == "completed" and check.get("status") == "verified":
                if isinstance(result.get("strategy_run_ns"), int) and result["strategy_run_ns"] >= 0:
                    paired_times[row["repetition"]][row["strategy"]] = result["strategy_run_ns"]
        paired_repetitions = {
            repetition: values for repetition, values in paired_times.items()
            if set(values) == {"csl.synthesis.reach-back", "csl.synthesis.strategy-b"}
        }
        by_strategy: dict[str, list[int]] = defaultdict(list)
        for values in paired_repetitions.values():
            for strategy, duration in values.items():
                by_strategy[strategy].append(duration)
        strategy_stats = {}
        for strategy in sorted(set(by_strategy) | set(completed_times)):
            values = by_strategy.get(strategy, [])
            completed = completed_times.get(strategy, [])
            strategy_stats[strategy] = {
                "verified_rows_within_measured_pairs": len(values),
                "median_strategy_run_ns_within_verified_pairs": statistics.median(values) if values else None,
                "completed_timing_rows_including_inconclusive": len(completed),
                "median_completed_run_ns_including_inconclusive": statistics.median(completed) if completed else None,
                "min_completed_run_ns_including_inconclusive": min(completed) if completed else None,
                "max_completed_run_ns_including_inconclusive": max(completed) if completed else None,
            }
        summaries.append({
            "horizon": horizon,
            "measured_attempts": len(rows),
            "verified_attempts": sum(
                row.get("process_status") == "completed" and checks.get(row.get("attempt_id"), {}).get("status") == "verified"
                for row in rows
            ),
            "verified_paired_repetitions": len(paired_repetitions),
            "process_statuses": {
                status: sum(row.get("process_status") == status for row in rows)
                for status in sorted({str(row.get("process_status")) for row in rows})
            },
            "strategies": strategy_stats,
        })
    output = {
        "schema": "csl.review05.horizon-summary/1",
        "claim": "descriptive timings for one synthetic scalar-integrator fixture; no winner, speedup, family-completeness, or scalability claim",
        "timed_region": "SynthesisWorkspace::run, steady_clock nanoseconds",
        "horizons": summaries,
    }
    (bundle / "summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

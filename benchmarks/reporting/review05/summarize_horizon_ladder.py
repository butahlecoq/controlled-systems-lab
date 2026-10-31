#!/usr/bin/env python3
"""Summarize REVIEW-05 HORIZON-01 raw attempts without winner claims."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
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
        backend_thread_counts: dict[str, list[int]] = defaultdict(list)
        backend_thread_unavailable: dict[str, int] = defaultdict(int)
        for row in rows:
            result = row.get("result") or {}
            if row.get("process_status") == "completed" and isinstance(result.get("strategy_run_ns"), int):
                completed_times[row["strategy"]].append(result["strategy_run_ns"])
                observed_threads = result.get("observed_backend_threads")
                if isinstance(observed_threads, int):
                    backend_thread_counts[row["strategy"]].append(observed_threads)
                else:
                    backend_thread_unavailable[row["strategy"]] += 1
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
            shapes: set[tuple[int, int, int, int]] = set()
            for row in rows:
                if row.get("strategy") != strategy or row.get("process_status") != "completed":
                    continue
                result = row.get("result") or {}
                if checks.get(row.get("attempt_id"), {}).get("status") != "verified":
                    continue
                relation = result.get("candidate_relation")
                if not isinstance(relation, dict):
                    continue
                inequalities = relation.get("inequalities", [])
                equalities = relation.get("equalities", [])
                nonzeros = sum(value != 0 for matrix in (inequalities, equalities)
                               for relation_row in matrix for value in relation_row)
                shapes.add((relation["dimension"], len(inequalities), len(equalities), nonzeros))
            strategy_stats[strategy] = {
                "verified_rows_within_measured_pairs": len(values),
                "median_strategy_run_ns_within_verified_pairs": statistics.median(values) if values else None,
                "min_strategy_run_ns_within_verified_pairs": min(values) if values else None,
                "max_strategy_run_ns_within_verified_pairs": max(values) if values else None,
                "completed_timing_rows_including_inconclusive": len(completed),
                "median_completed_run_ns_including_inconclusive": statistics.median(completed) if completed else None,
                "min_completed_run_ns_including_inconclusive": min(completed) if completed else None,
                "max_completed_run_ns_including_inconclusive": max(completed) if completed else None,
                "verified_representation_shapes": [
                    {"joint_coordinates": dimension, "inequality_rows": inequalities,
                     "equality_rows": equalities, "nonzero_h_coefficients": nonzeros}
                    for dimension, inequalities, equalities, nonzeros in sorted(shapes)
                ],
                "observed_backend_thread_counts": {
                    str(threads): count for threads, count in sorted(Counter(backend_thread_counts.get(strategy, [])).items())
                },
                "observed_backend_thread_unavailable_rows": backend_thread_unavailable.get(strategy, 0),
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
        "claim": "matched descriptive timings for a scalar-integrator horizon and candidate-relation growth pilot; the independent analytic checker verifies the emitted relation equals the unique optimum history for these fixtures only; no general completeness, winner, speedup, or complexity claim",
        "timed_region": "SynthesisWorkspace::run, steady_clock nanoseconds",
        "horizons": summaries,
    }
    (bundle / "summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

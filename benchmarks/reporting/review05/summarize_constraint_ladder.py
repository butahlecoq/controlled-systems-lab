#!/usr/bin/env python3
"""Summarize checked matched CONSTRAINT-01 runs without dropping failures."""
from __future__ import annotations
import argparse, json, statistics
from pathlib import Path

STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
CASES = (("r2", 2), ("r4", 4), ("r8", 8))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    attempts = [json.loads(line) for line in (bundle / "attempts.jsonl").read_text().splitlines() if line]
    checks = {row["attempt_id"]: row for row in
              (json.loads(line) for line in (bundle / "checks.jsonl").read_text().splitlines() if line)}
    summary = {
        "schema": "csl.review05.constraint-summary/1",
        "claim": "descriptive fixed-n, fixed-horizon measurements while authored redundant state H-row count grows; the exact fixture oracle establishes the unique zero optimum only for these three finite scenarios; no winner, speedup, general completeness, memory, phase, or complexity claim",
        "timed_region": "SynthesisWorkspace::run, steady_clock nanoseconds",
        "cases": []}
    for key, rows_per_stage in CASES:
        measured = {}
        for row in attempts:
            if row["case"] == key and not row["warmup"]:
                measured.setdefault(row["repetition"], []).append(row)
        verified_attempts = sum(checks[row["attempt_id"]]["status"] == "verified"
                                for rows in measured.values() for row in rows)
        paired = {strategy: [] for strategy in STRATEGIES}
        shapes = {strategy: [] for strategy in STRATEGIES}
        verified_pairs = []
        for repetition, rows in sorted(measured.items()):
            by_strategy = {row["strategy"]: row for row in rows}
            if set(by_strategy) != set(STRATEGIES):
                continue
            if any(checks[by_strategy[strategy]["attempt_id"]]["status"] != "verified"
                   for strategy in STRATEGIES):
                continue
            verified_pairs.append(repetition)
            for strategy in STRATEGIES:
                row = by_strategy[strategy]
                paired[strategy].append(row["result"]["strategy_run_ns"])
                relation = row["result"]["candidate_relation"]
                shapes[strategy].append({
                    "joint_coordinates": relation["dimension"],
                    "inequality_rows": len(relation["inequalities"]),
                    "equality_rows": len(relation["equalities"]),
                    "nonzero_h_coefficients": sum(value != 0 for hrow in
                        relation["inequalities"] + relation["equalities"] for value in hrow)})
        strategies = {}
        for strategy, values in paired.items():
            structure = shapes[strategy]
            fixed_shape = structure[0] if structure and all(item == structure[0] for item in structure) else None
            strategies[strategy] = {
                "verified_measured_rows": len(values),
                "median_ns": statistics.median(values) if values else None,
                "min_ns": min(values) if values else None,
                "max_ns": max(values) if values else None,
                "representation_shape": fixed_shape}
        summary["cases"].append({
            "case": key, "state_dimension": 1, "control_dimension": 1, "horizon": 2,
            "state_rows_per_stage": rows_per_stage, "stages": 3,
            "authored_state_rows_total": rows_per_stage * 3,
            "verified_measured_attempts": verified_attempts,
            "verified_paired_repetitions": len(verified_pairs),
            "paired_repetitions": verified_pairs, "strategies": strategies})
    (bundle / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

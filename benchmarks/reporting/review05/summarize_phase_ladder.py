#!/usr/bin/env python3
"""Summarize OBS-03 high-level phase diagnostics from the horizon ladder."""
from __future__ import annotations
import argparse, json, statistics
from collections import defaultdict
from pathlib import Path

HORIZONS = (2, 4, 8)
STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
NOT_MEASURED = ["sparse assembly", "LP factorization/solve internals", "provider conversions",
                "per-stage family queries", "witness-selector queries"]

def summarize(attempts_path: Path, output_path: Path) -> dict[str, object]:
    attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {(t, r, p) for t in HORIZONS for r in range(7) for p in (0, 1)}
    observed = {(row.get("horizon"), row.get("repetition"), row.get("order_position")) for row in attempts}
    if len(attempts) != 42 or observed != expected:
        raise ValueError("phase report requires the complete 42-process horizon schedule")
    groups: dict[tuple[int, str, str], list[int]] = defaultdict(list)
    expected_operations = {
        STRATEGIES[0]: {"strategy-a/run", "strategy-a/forward", "strategy-a/feasible-preimage",
            "strategy-a/terminal-optimization", "strategy-a/terminal-preimage", "strategy-a/family-construction"},
        STRATEGIES[1]: {"strategy-b/run", "strategy-b/family-construction"},
    }
    for row in attempts:
        if row.get("process_status") != "completed" or row.get("return_code") != 0 or row.get("result") is None:
            raise ValueError(f"missing instrumented result: {row.get('attempt_id')}")
        timing = row["result"].get("phase_timing")
        if not isinstance(timing, dict) or timing.get("clock_period_numerator") != 1 or timing.get("clock_period_denominator") != 1_000_000_000:
            raise ValueError(f"missing or unexpected steady-clock phase report: {row.get('attempt_id')}")
        spans = timing.get("spans", [])
        if {span.get("operation") for span in spans} != expected_operations[row["strategy"]]:
            raise ValueError(f"phase operation inventory mismatch: {row.get('attempt_id')}")
        if row.get("warmup"):
            continue
        for span in spans:
            value = span.get("inclusive_wall_ticks")
            if span.get("completed") and (not isinstance(value, int) or
                    not isinstance(span.get("exclusive_wall_ticks"), int)):
                raise ValueError(f"completed phase has invalid duration: {row.get('attempt_id')}")
            groups[(row["horizon"], row["strategy"], span["operation"])].append(
                value if span.get("completed") else None)
    summary = []
    for horizon in HORIZONS:
        for strategy, operations in expected_operations.items():
            for operation in sorted(operations):
                values = groups[(horizon, strategy, operation)]
                if len(values) != 6:
                    raise ValueError(f"expected six measured phase observations for T={horizon}, {operation}; got {len(values)}")
                observed_values = [value for value in values if value is not None]
                summary.append({"horizon": horizon, "strategy": strategy, "operation": operation,
                    "measured_spans": len(values), "completed_spans": len(observed_values),
                    "not_called_or_unavailable_spans": len(values) - len(observed_values),
                    "timing_scope": "instrumented OBS-03 inclusive wall ticks",
                    "inclusive_wall_ns": {"median": statistics.median(observed_values) if observed_values else None,
                        "minimum": min(observed_values) if observed_values else None,
                        "maximum": max(observed_values) if observed_values else None}})
    result = {"schema": "csl.review05.phase-summary/1",
        "claim": "instrumented strategy-phase diagnostics; not directly comparable to the uninstrumented strategy timing ladder",
        "instrumented_phases": summary, "not_measured": NOT_MEASURED,
        "relation_scope": "candidate-relaxation outputs independently checked against the pinned analytic fixtures; exact history equality is fixture-specific and does not imply general family completeness"}
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.attempts, args.output)
    print(json.dumps({"phases": len(result["instrumented_phases"]), "unmeasured": result["not_measured"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

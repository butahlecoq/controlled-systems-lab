#!/usr/bin/env python3
"""Summarize OBS-03 strategy and provider diagnostics from the horizon ladder."""
from __future__ import annotations
import argparse, json, statistics
from collections import Counter, defaultdict
from pathlib import Path

from check_horizon_ladder import check_attempt, sha256
from highs_clock_events import parse_stderr

HORIZONS = (2, 4, 8)
STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
STRATEGY_OPERATIONS = {
    STRATEGIES[0]: {"strategy-a/run", "strategy-a/forward", "strategy-a/feasible-preimage",
        "strategy-a/terminal-optimization", "strategy-a/terminal-preimage", "strategy-a/family-construction"},
    STRATEGIES[1]: {"strategy-b/run", "strategy-b/family-construction", "strategy-b/program-solve", "strategy-b/program-build"},
}
NOT_MEASURED = ["LP factorization internals", "per-stage family queries",
                "witness-selector queries"]


def expected_spans(strategy: str, horizon: int) -> Counter[tuple[str, int | None]]:
    result = Counter((operation, None) for operation in STRATEGY_OPERATIONS[strategy])
    if strategy == STRATEGIES[0]:
        for stage in range(horizon + 1):
            if stage:
                result[("geometry.affine-image", stage)] += 2
                result[("geometry.minkowski-sum", stage)] += 1
                result[("geometry.to-h", stage)] += 1
            result[("geometry.projection", stage)] += 2
    return result


def summarize(attempts_path: Path, output_path: Path) -> dict[str, object]:
    attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bundle = attempts_path.resolve().parent
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    checks = {row["attempt_id"]: row for row in
              (json.loads(line) for line in (bundle / "checks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    expected_schedule = {(t, r, p) for t in HORIZONS for r in range(7) for p in (0, 1)}
    observed_schedule = {(row.get("horizon"), row.get("repetition"), row.get("order_position")) for row in attempts}
    if len(attempts) != 42 or observed_schedule != expected_schedule:
        raise ValueError("phase report requires the complete 42-process horizon schedule")
    groups: dict[tuple[int, str, str, int | None], list[int | None]] = defaultdict(list)
    clock_capture_attempts = []
    clock_samples: dict[tuple[int, str, int, int, str], list[dict[str, object]]] = defaultdict(list)
    for row in attempts:
        if row.get("process_status") != "completed" or row.get("return_code") != 0 or row.get("result") is None:
            raise ValueError(f"missing instrumented result: {row.get('attempt_id')}")
        strategy = row["strategy"]
        if strategy not in STRATEGY_OPERATIONS:
            raise ValueError(f"unexpected strategy: {strategy}")
        timing = row["result"].get("phase_timing")
        if not isinstance(timing, dict) or timing.get("clock_period_numerator") != 1 or timing.get("clock_period_denominator") != 1_000_000_000:
            raise ValueError(f"missing or unexpected steady-clock phase report: {row.get('attempt_id')}")
        spans = timing.get("spans", [])
        actual = Counter((span.get("operation"), span.get("stage")) for span in spans)
        if actual != expected_spans(strategy, row["horizon"]):
            raise ValueError(f"phase operation/stage inventory mismatch: {row.get('attempt_id')}")
        if row.get("warmup"):
            continue
        check = checks.get(row.get("attempt_id"), {})
        if manifest.get("schedule", {}).get("highs_internal_clocks"):
            if check.get("status") != "verified":
                raise ValueError(f"HiGHS clock summaries require a verified attempt: {row.get('attempt_id')}")
            status, reasons = check_attempt(row, manifest["scenario_sha256"][str(row["horizon"])])
            if status != "verified":
                raise ValueError(f"current attempt verification failed: {reasons}")
            stderr_path = bundle / row["stderr_path"]
            if sha256(stderr_path) != row["stderr_sha256"]:
                raise ValueError("clock stderr hash mismatch")
            current_groups = parse_stderr(stderr_path.read_bytes(), enabled=True)
            if current_groups != row.get("solver_clock_groups"):
                raise ValueError("clock groups differ from retained stderr")
            clock_capture_attempts.append({"attempt_id": row["attempt_id"],
                "horizon": row["horizon"], "strategy": strategy,
                "provider_calls": len(current_groups),
                "captured_groups": sum(group["capture_status"] == "captured" for group in current_groups),
                "unavailable_groups": sum(group["capture_status"] == "unavailable" for group in current_groups)})
            for group in current_groups:
                for clock in group["clocks"]:
                    key = (row["horizon"], strategy, group["provider_call_index"],
                           clock["id"], clock["name"])
                    clock_samples[key].append({"status": clock["status"], "calls": clock["calls"],
                                               "elapsed_seconds": clock["elapsed_seconds"]})
        for span in spans:
            value = span.get("inclusive_wall_ticks")
            if span.get("completed") and not isinstance(value, int):
                raise ValueError(f"completed phase has invalid duration: {row.get('attempt_id')}")
            groups[(row["horizon"], strategy, span["operation"], span.get("stage"))].append(
                value if span.get("completed") else None)
    summary = []
    for horizon in HORIZONS:
        for strategy in STRATEGIES:
            for operation_stage, count_per_attempt in expected_spans(strategy, horizon).items():
                operation, stage = operation_stage
                values = groups[(horizon, strategy, operation, stage)]
                expected_count = 6 * count_per_attempt
                if len(values) != expected_count:
                    raise ValueError(f"expected {expected_count} measured observations for T={horizon}, {operation}, stage={stage}; got {len(values)}")
                observed_values = [value for value in values if value is not None]
                summary.append({"horizon": horizon, "strategy": strategy, "operation": operation,
                    "stage": stage, "measured_spans": len(values), "completed_spans": len(observed_values),
                    "not_called_or_unavailable_spans": len(values) - len(observed_values),
                    "timing_scope": "instrumented OBS-03 inclusive wall ticks",
                    "inclusive_wall_ns": {"median": statistics.median(observed_values) if observed_values else None,
                        "minimum": min(observed_values) if observed_values else None,
                        "maximum": max(observed_values) if observed_values else None}})
    highs_clock_summary = []
    for (horizon, strategy, call_index, clock_id, name), samples in sorted(clock_samples.items()):
        observed = [sample["elapsed_seconds"] for sample in samples if sample["status"] == "observed"]
        highs_clock_summary.append({"horizon": horizon, "strategy": strategy,
            "provider_call_index": call_index, "clock_id": clock_id, "clock_name": name,
            "verified_measured_samples": len(samples),
            "observed_samples": len(observed),
            "uncalled_samples": sum(sample["status"] == "uncalled" for sample in samples),
            "unavailable_samples": sum(sample["status"] == "unavailable" for sample in samples),
            "calls_minimum": min((sample["calls"] for sample in samples if sample["calls"] is not None), default=None),
            "calls_maximum": max((sample["calls"] for sample in samples if sample["calls"] is not None), default=None),
            "elapsed_seconds": {"median": statistics.median(observed) if observed else None,
                "minimum": min(observed) if observed else None, "maximum": max(observed) if observed else None},
            "timing_scope": "native HiGHS timer clock; clocks may overlap and are not summed"})
    result = {"schema": "csl.review05.phase-summary/2",
        "claim": "instrumented strategy and provider-call diagnostics; not directly comparable to the uninstrumented strategy timing ladder",
        "instrumented_phases": summary,
        "highs_internal_clocks": highs_clock_summary,
        "highs_clock_capture_attempts": clock_capture_attempts,
        "highs_clock_capture_enabled": manifest.get("schedule", {}).get("highs_internal_clocks") is True,
        "measured_operations": ["geometry affine-image", "geometry Minkowski-sum", "geometry to-H conversion", "geometry projection", "Strategy B joint program build", "Strategy B LP program run"],
        "not_measured": [item for item in NOT_MEASURED if item != "LP factorization internals"
                         or not any(row["observed_samples"] and row["clock_name"] == "INVERT"
                                    for row in highs_clock_summary)],
        "relation_scope": "candidate-relaxation outputs independently checked against the pinned analytic fixtures; exact history equality is fixture-specific and does not imply general family completeness"}
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.attempts, args.output)
    print(json.dumps({"phase_groups": len(result["instrumented_phases"]), "unmeasured": result["not_measured"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

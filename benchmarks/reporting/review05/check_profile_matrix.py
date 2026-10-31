#!/usr/bin/env python3
"""Summarize retained exact-profile matrix trials without dropping failures."""

from __future__ import annotations

import json
import statistics
from pathlib import Path


PROFILES = {
    "ts01_exact_integrator": ("csl.synthesis.paired-ts01-event/1", 7),
    "ts02_constant_integrator": ("csl.synthesis.paired-family-event/1", 5),
    "ts03_singular_integrator": ("csl.synthesis.paired-family-event/1", 5),
}
STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def checked(event: dict) -> bool:
    if not (event["status"] == "passed" and event["termination"] == "completed" and
            event["outcome"] == "optimal" and event["complete_family_verified"] and
            event["distinct_witnesses"] == 2 and len(event["witnesses"]) == 2):
        return False
    return all(w["verification"]["feasibility"] == "numerical_pass" and
               w["verification"]["objective"] == "numerical_pass" and
               w["verification"]["bindings"] == "numerical_pass"
               for w in event["witnesses"])


def timed_values(events: list[dict], phase: str) -> list[int]:
    return [event["timings_ns"][phase]["value"] for event in events
            if event["timings_ns"][phase]["available"]]


def summarize_profile(raw: Path, profile: str, schema: str, measured_pairs: int) -> dict:
    events = read_events(raw / f"{profile}.jsonl")
    header, trials = events[0], events[1:]
    if header.get("event") != "header" or header.get("profile") != profile or header.get("schema") != schema:
        raise ValueError(f"{profile}: header/profile/schema mismatch")
    if len(trials) != 2 * (measured_pairs + 1):
        raise ValueError(f"{profile}: expected {2 * (measured_pairs + 1)} trial rows, got {len(trials)}")
    if any(event.get("event") != "trial" for event in trials):
        raise ValueError(f"{profile}: non-trial event after header")
    measured = [event for event in trials if not event["warmup"]]
    if len(measured) != 2 * measured_pairs:
        raise ValueError(f"{profile}: measured-pair count mismatch")
    order = []
    for index in range(measured_pairs):
        pair = [event for event in measured if event["repetition"] == index + 1]
        expected = list(STRATEGIES if index % 2 == 0 else reversed(STRATEGIES))
        observed = [event["strategy"] for event in pair]
        if observed != expected:
            raise ValueError(f"{profile}: repetition {index + 1} order mismatch: {observed}")
        order.append(observed)
    results = {}
    for strategy in STRATEGIES:
        rows = [event for event in measured if event["strategy"] == strategy]
        end_to_end = timed_values(rows, "end_to_end_strategy")
        family = timed_values(rows, "family_construction")
        results[strategy] = {
            "attempts": len(rows),
            "complete_verified_outputs": sum(checked(event) for event in rows),
            "retained_statuses": [event["status"] for event in rows],
            "end_to_end_strategy_ns": {
                "median": statistics.median(end_to_end) if end_to_end else None,
                "min": min(end_to_end) if end_to_end else None,
                "max": max(end_to_end) if end_to_end else None,
            },
            "family_construction_ns": {
                "median": statistics.median(family) if family else None,
                "min": min(family) if family else None,
                "max": max(family) if family else None,
            },
        }
    process = json.loads((raw / f"{profile}.process.json").read_text(encoding="utf-8"))
    results_metadata = {
        "schema": schema,
        "measured_pairs": measured_pairs,
        "order_by_repetition": order,
        "process_exit_code": process["exit_code"],
        "timed_out": process["timed_out"],
        "elapsed_wall_seconds": process["elapsed_wall_seconds"],
        "scenario_sha256": process["scenario_sha256"],
        "executable_sha256": process["executable_sha256"],
        "host": process["host"],
        "strategies": results,
    }
    return results_metadata


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = {name: summarize_profile(args.raw, name, schema, pairs)
               for name, (schema, pairs) in PROFILES.items()}
    args.out.write_text(json.dumps({"schema": "csl.review05.profile-matrix-check/1",
                                    "profiles": results}, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"wrote {args.out}")
    for name, result in results.items():
        print(f"{name}: {result['measured_pairs']} measured pairs; "
              f"A={result['strategies'][STRATEGIES[0]]['complete_verified_outputs']}/"
              f"{result['measured_pairs']}, B={result['strategies'][STRATEGIES[1]]['complete_verified_outputs']}/"
              f"{result['measured_pairs']} complete-family and witness checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Summarize wait4 CPU and peak-RSS receipts from DIMENSION-01."""
from __future__ import annotations
import argparse, json, statistics
from collections import defaultdict
from pathlib import Path

CASES = ("n1-t2", "n1-t4", "n2-t2", "n2-t4")
STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")

def summarize(attempts_path: Path, output_path: Path) -> list[dict[str, object]]:
    attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {(case, repetition, position) for case in CASES for repetition in range(7) for position in (0, 1)}
    observed = {(row.get("case"), row.get("repetition"), row.get("order_position")) for row in attempts}
    if len(attempts) != 56 or observed != expected:
        raise ValueError("resource report requires the complete 56-process dimension schedule")
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in attempts:
        receipt = row.get("resource_receipt")
        if row.get("process_status") != "completed" or row.get("return_code") != 0:
            raise ValueError(f"process did not complete: {row.get('attempt_id')}")
        if not isinstance(receipt, dict) or receipt.get("source") != "POSIX wait4 for the isolated strategy process" or receipt.get("timed_out") is not False:
            raise ValueError(f"missing or invalid wait4 receipt: {row.get('attempt_id')}")
        for field in ("user_cpu_seconds", "system_cpu_seconds", "child_cpu_seconds", "peak_rss_kib"):
            value = receipt.get(field)
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"invalid {field}: {row.get('attempt_id')}")
        if abs(receipt["child_cpu_seconds"] - receipt["user_cpu_seconds"] - receipt["system_cpu_seconds"]) > 1e-9:
            raise ValueError(f"CPU receipt total mismatch: {row.get('attempt_id')}")
        groups[(row["case"], row["strategy"])].append(row)
    summary = []
    for case in CASES:
        for strategy in STRATEGIES:
            measured = [row for row in groups[(case, strategy)] if not row["warmup"]]
            if len(measured) != 6:
                raise ValueError(f"expected six measured attempts for {case}, {strategy}")
            metrics = {name: [row["resource_receipt"][name] for row in measured]
                       for name in ("user_cpu_seconds", "system_cpu_seconds", "child_cpu_seconds", "peak_rss_kib")}
            summary.append({"case": case, "state_dimension": measured[0]["state_dimension"],
                "control_dimension": measured[0]["state_dimension"], "horizon": measured[0]["horizon"],
                "strategy": strategy, "measured_attempts": len(measured),
                "resource_source": "POSIX wait4; whole isolated strategy process including startup and setup",
                "metrics": {name: {"median": statistics.median(values), "minimum": min(values), "maximum": max(values)}
                            for name, values in metrics.items()}})
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for row in summarize(args.attempts, args.output):
        print(json.dumps(row, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

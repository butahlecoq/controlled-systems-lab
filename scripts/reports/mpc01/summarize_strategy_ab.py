#!/usr/bin/env python3
"""Validate and summarize the paired registered T-S01 Strategy A/B run."""

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


EXPECTED = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
PHASES = (
    "preparation", "workspace_creation", "family_construction",
    "selector_preparation", "selector_workspace_creation", "witness_query",
    "original_verification", "end_to_end_strategy",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    event_bytes, stdout_bytes = args.events.read_bytes(), args.stdout.read_bytes()
    if event_bytes != stdout_bytes:
        raise ValueError("saved event sidecar does not match stdout bytes")
    rows = [json.loads(line) for line in event_bytes.decode("utf-8").splitlines() if line]
    if len(rows) != 17 or rows[0].get("event") != "header":
        raise ValueError("expected one header and sixteen trial events")
    header, trials = rows[0], rows[1:]
    if header.get("schema") != "csl.synthesis.paired-ts01-event/1":
        raise ValueError("unsupported Strategy A/B event schema")
    if header.get("scenario_sha256") != digest(args.scenario):
        raise ValueError("event header does not bind the supplied T-S01 scenario")
    if header.get("profile") != "ts01_exact_integrator" or header.get("assurance") != "numerical":
        raise ValueError("event request is not the registered T-S01 numerical profile")
    if len([row for row in trials if row["warmup"]]) != 2 or len([row for row in trials if not row["warmup"]]) != 14:
        raise ValueError("expected one excluded warmup pair and seven measured pairs")

    measured: dict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(trials):
        expected_rep = index // 2
        expected_position = index % 2
        if row.get("event") != "trial" or row.get("repetition") != expected_rep or row.get("order_position") != expected_position:
            raise ValueError("trial repetition or order is inconsistent")
        if row.get("strategy") not in EXPECTED:
            raise ValueError("unexpected strategy identity")
        if row["status"] != "passed" or row["termination"] != "completed" or row["outcome"] != "optimal":
            raise ValueError(f"Strategy A/B attempt failed: {row.get('strategy')} {row.get('error', '')}")
        if not row["complete_family_verified"] or row["distinct_witnesses"] != 2:
            raise ValueError("strategy did not provide its admitted complete T-S01 family and two witnesses")
        if row["verification_summary"]["optimality"] != "unsupported" or row["verification_summary"]["completeness"] != "unsupported":
            raise ValueError("witness verification was overclaimed")
        for witness in row["witnesses"]:
            if witness["original_objective"] != 0 or witness["recomputed_objective"] != 0:
                raise ValueError("T-S01 selected witness differs from the exact zero-cost optimum")
            checks = witness["verification"]
            if any(checks[key] != "numerical_pass" for key in ("bindings", "feasibility", "objective")):
                raise ValueError("original-problem witness verification did not pass")
        if not row["warmup"]:
            measured[row["strategy"]].append(row)

    if set(measured) != set(EXPECTED) or any(len(rows) != 7 for rows in measured.values()):
        raise ValueError("measured A/B result counts differ")
    lines = [
        "# Current-branch Strategy A/B T-S01 paired run",
        "",
        "This functional measurement uses the same exact two-stage integrator equations as `ts01-exact-v1`: `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and terminal objective `(x2-1)^2`. It is a separate registered-strategy path from the OSQP/HPIPM QP solve-phase measurements; phase timings are not directly comparable.",
        "",
        f"- Source commit: `{json.loads(args.environment.read_text())['source_commit']}`.",
        f"- Scenario SHA-256: `{digest(args.scenario)}`.",
        f"- Event/stdout SHA-256: `{digest(args.events)}`.",
        "- One excluded warmup pair and seven measured alternating A/B pairs; all 16 trials passed.",
        "- Every measured result carries the registered T-S01 complete-family profile, two distinct selected witnesses, zero original/recomputed objective, and numerical-pass original-data checks. Witness checks do not claim separate optimality or completeness proofs; the profile-specific family status is retained separately.",
        "",
        "| Strategy | Median end-to-end (ms) | Range (ms) |",
        "|---|---:|---:|",
    ]
    for strategy in EXPECTED:
        values = [row["timings_ns"]["end_to_end_strategy"]["value"] for row in measured[strategy]]
        lines.append(f"| `{strategy}` | {statistics.median(values) / 1e6:.6f} | {min(values) / 1e6:.6f}–{max(values) / 1e6:.6f} |")
    lines.extend([
        "",
        "The timing interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. No separate limiter or per-attempt resource-cap profile was collected, so these tiny-case timings support no general performance winner claim.",
        "",
    ])
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

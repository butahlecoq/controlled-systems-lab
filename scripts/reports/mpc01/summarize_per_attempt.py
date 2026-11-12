#!/usr/bin/env python3
"""Validate and summarize an MPC-01 per-attempt resource capture."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.bundle
    attempts = read_jsonl(root / "attempts.jsonl")
    records = read_jsonl(root / "comparison-records.jsonl")
    exact = read_jsonl(root / "exact-candidate-checks.jsonl")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    build = json.loads((root / "build-identity.json").read_text(encoding="utf-8"))
    profile = json.loads((root / "capture-profile.json").read_text(encoding="utf-8"))

    expected_count = summary["repetitions"] * len(summary["fixtures"]) * 4
    if len(attempts) != expected_count or len(records) != len(summary["fixtures"]):
        raise ValueError("capture does not contain the declared attempt or comparison-record count")
    if summary["completed"] != expected_count or any(row["status"] != "completed" for row in attempts):
        raise ValueError("capture contains a failed, timed-out or resource-limited attempt")
    if summary["timed_out"] or summary["resource_limited"] or summary["failed"]:
        raise ValueError("attempt summary counters disagree with completion status")
    for row in attempts:
        if row["enforced"]["memory_max_bytes"] != 8 * 1024**3 or \
                row["enforced"]["memory_swap_max_bytes"] != 0 or \
                row["enforced"]["wall_watchdog_seconds"] != 300:
            raise ValueError(f"resource contract differs for attempt {row['index']}")
        observed = row["observed"]
        events = {key: int(value) for key, value in (line.split() for line in observed["memory_events"])}
        if events.get("oom", 0) or events.get("oom_kill", 0):
            raise ValueError(f"memory OOM was recorded for attempt {row['index']}")
    expected_keys = set()
    for row in attempts:
        event = row["attempt"]
        expected_keys.add((event["case_id"], event["method"], event["start_mode"],
                           event["repetition"], event["input_sha256"]))
    record_keys = set()
    for record in records:
        if record.get("schema") != "csl.comparison-record/1" or len(record.get("attempts", [])) != 20:
            raise ValueError("comparison record failed the schema or attempt-count check")
        for item in record["attempts"]:
            payload = json.loads(item["measurement_payload"])
            event = payload["attempt"]
            if "resource_profile" not in event:
                raise ValueError("canonical record omitted a per-attempt resource receipt")
            record_keys.add((event["case_id"], event["method"], event["start_mode"],
                             event["repetition"], event["input_sha256"]))
    if record_keys != expected_keys:
        raise ValueError("canonical records do not contain exactly the captured native attempts")
    if len(exact) != summary["repetitions"] * 18:
        raise ValueError(f"expected 90 exact rational checks, found {len(exact)}")
    for row in exact:
        if row.get("schema") != "csl.mpc01-exact-candidate-check/1" or \
                row.get("feasibility") != "verified_exact_rational":
            raise ValueError("exact checker produced a non-verified candidate row")

    figure_manifest = json.loads((root / "b04-figure-manifest.json").read_text(encoding="utf-8"))
    representatives = read_jsonl(root / "representative-b04-cold-attempts.jsonl")
    if (figure_manifest.get("attempt_count") != 2 or len(representatives) != 2 or
            figure_manifest.get("attempts_sha256") != hashlib.sha256(
                (root / "representative-b04-cold-attempts.jsonl").read_bytes()).hexdigest()):
        raise ValueError("B04 representative figure manifest does not bind its saved paths")
    if not (root / "b04-repeated-projections.svg").is_file() or \
            not (root / "b04-repeated-projections.html").is_file():
        raise ValueError("B04 2D projection files are missing")

    by_arm: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    outcome_counts: Counter[tuple[str, str, str, str]] = Counter()
    for row in attempts:
        event = row["attempt"]
        by_arm[(row["fixture"], row["method"], row["start_mode"])].append(row)
        outcome_counts[(row["fixture"], row["method"], row["start_mode"],
                        event["mathematical_outcome"])] += 1

    lines = [
        "# MPC-01 per-attempt resource capture",
        "",
        f"Capture window: `{profile['started_at']}` to `{profile['finished_at']}`.",
        f"Host: {profile['host'].get('system', profile['host']['platform'])} `{profile['host'].get('kernel_release', 'kernel unavailable')}`, `{profile['host'].get('machine', 'architecture unavailable')}`, {profile['host'].get('cpu_model', 'CPU model unavailable')}, {profile['host'].get('logical_cpu_count', 'unknown')} logical CPUs.",
        f"Load average before/after: `{profile['host']['load_average_before']}` / `{profile['host']['load_average_after']}` (1, 5, 15 minutes). Hardware details recorded at `{profile['host'].get('hardware_metadata_collected_at', 'capture time')}`.",
        f"Source revision: `{build['source_revision']}` plus the source-file hashes in `build-identity.json`.",
        f"Build: {build['build_type']} with `{build['cxx_compiler_id']} {build['cxx_compiler_version']}`; executable SHA-256 `{build['binary_sha256']}`.",
        "",
        f"The run retained {len(attempts)} of {expected_count} native attempts and {len(records)} canonical comparison records. Each attempt ran sequentially in its own systemd user scope with an enforced 300-second process-tree watchdog, an 8 GiB cgroup-v2 memory cap, swap disabled, one CPU quota and one pinned logical CPU. The host has {profile['host']['physical_memory_total_bytes'] / (1024**3):.2f} GiB physical RAM, below the configured per-attempt cgroup maximum; observed use stayed small, with a largest process-tree peak of {max(r['observed']['process_tree_peak_memory_bytes'] for r in attempts):,} bytes. No attempt timed out, failed, or recorded memory OOM events.",
        "",
        f"The independent exact-rational checker verified feasibility and objective bounds for {len(exact)} native attempts classified as optimal. Native solver classifications for singular, infeasible and unbounded cases remain separate; non-optimal attempts are retained in `attempts.jsonl` and their canonical records.",
        "",
        "A separate [source-mapped gprof limiter profile](../mpc01-source-mapped-profile-20261102/README.txt) attributes sampled OSQP time to QDLDL triangular solves on its 20-repetition workload. It was instrumented with `-pg` and is excluded from these Release timings; the current measurements do not establish a general limiter outside that workload.",
        "",
        "Solve timings below are native solver phase timings, reported as descriptive medians and ranges of five repetitions per fixture/arm. Warm attempts include a same-process cold seed solve inside their attempt resource budget; the seed solve time is retained separately in each event. These rows do not establish a general solver winner or end-to-end MPC latency.",
        "",
        "| Fixture | Solver | Start mode | Completed / outcomes | Solve median (ms) | Solve range (ms) | Attempt process median (ms) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for key in sorted(by_arm):
        fixture, method, mode = key
        rows = by_arm[key]
        solve_ms = [row["attempt"]["timings_ns"]["solve"] / 1e6 for row in rows]
        wall_ms = [row["attempt_wall_time_ns"] / 1e6 for row in rows]
        outcomes = Counter(row["attempt"]["mathematical_outcome"] for row in rows)
        outcome_text = ", ".join(f"{name}: {count}" for name, count in sorted(outcomes.items()))
        lines.append(
            f"| `{fixture}` | `{method}` | `{mode}` | {len(rows)} ({outcome_text}) | "
            f"{statistics.median(solve_ms):.6f} | {min(solve_ms):.6f}–{max(solve_ms):.6f} | "
            f"{statistics.median(wall_ms):.3f} |"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `attempts.jsonl`: one resource and outcome record per attempt, including stdout/stderr hashes and cgroup counters.",
        "- `comparison-records.jsonl`: seven validated canonical records; each measurement payload binds its resource receipt.",
        "- `native-attempts.jsonl`: source rows used by the exact checker and record builder.",
        "- `exact-candidate-checks.jsonl` and `exact-check-manifest.json`: independent rational feasibility/objective checks.",
        "- `exact-checker-resource-profile.json`: separate five-second checker budget and resource accounting.",
        "- [B04 2D projection (HTML)](b04-repeated-projections.html) and [SVG](b04-repeated-projections.svg): representative saved solver paths in the `(x1,x2)` oxidizer and `(x3,x4)` fuel planes, alongside the exact reference witness.",
        "- `SHA256SUMS`: bundle integrity manifest.",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

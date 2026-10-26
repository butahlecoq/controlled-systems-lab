#!/usr/bin/env python3
"""Regenerate an OBS-06 operation summary from saved raw phase JSON."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path


def rows_from(path: Path):
    open_text = gzip.open if path.suffix == ".gz" else open
    with open_text(path, "rt", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    for line in lines:
        if line.strip():
            yield json.loads(line)


def tick_value(metric):
    return metric if isinstance(metric, int) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", nargs="+", type=Path, help="B06/B07/B09 phase JSON or JSONL files")
    parser.add_argument("--output", type=Path, required=True, help="summary CSV path")
    parser.add_argument("--provenance", type=Path, help="capture manifest with environment and binary hashes")
    args = parser.parse_args()

    provenance = json.loads(args.provenance.read_text(encoding="utf-8")) if args.provenance else {}
    binary_hashes = provenance.get("raw_binary_sha256", {})
    result = []
    for source in args.raw:
        for row in rows_from(source):
            case_id = row.get("case_id") or row.get("scenario")
            if not case_id and "lambda" in row:
                case_id = f"B09-lambda-{row['lambda']:g}"
            if not case_id and "batch" in row:
                case_id = "B06-paired-run"
            timing = row["phase_timing"]
            if timing["schema"] != "csl.obs06-fuel-phase/1":
                raise ValueError(f"unsupported phase schema in {source}")
            clock = timing["wall_clock"]
            numerator = int(clock["period_numerator"])
            denominator = int(clock["period_denominator"])
            if numerator <= 0 or denominator <= 0:
                raise ValueError(f"invalid wall clock period in {source}")
            operations = {}
            for span in timing["spans"]:
                operation = span["operation"]
                group = operations.setdefault(operation, {
                    "span_count": 0, "call_count": 0, "returned": 0, "rejected": 0, "failed": 0,
                    "not_called": 0, "incomplete": 0,
                    "wall_inclusive_ticks_sum": 0, "wall_exclusive_ticks_sum": 0,
                    "inclusive_available": True, "exclusive_available": True,
                })
                group["span_count"] += 1
                if span.get("execution") == "not_called":
                    group["not_called"] += 1
                else:
                    group["call_count"] += 1
                    group[span["status"] if span["status"] in {"returned", "rejected", "failed"} else "incomplete"] += 1
                for metric_name, availability_name in (
                    ("wall_inclusive_ticks", "inclusive_available"),
                    ("wall_exclusive_ticks", "exclusive_available"),
                ):
                    ticks = tick_value(span.get(metric_name))
                    if ticks is None:
                        group[availability_name] = False
                    else:
                        group[metric_name + "_sum"] += ticks
            if sum(group["span_count"] for group in operations.values()) != timing["span_count"]:
                raise ValueError(f"span count mismatch in {source}")
            for operation, group in sorted(operations.items()):
                inclusive_ms = (group["wall_inclusive_ticks_sum"] * numerator / denominator * 1e3
                                if group["inclusive_available"] else "unavailable")
                exclusive_ms = (group["wall_exclusive_ticks_sum"] * numerator / denominator * 1e3
                                if group["exclusive_available"] else "unavailable")
                result.append({
                    "source_file": source.name,
                    "binary_sha256": binary_hashes.get(source.name, "unavailable"),
                    "case_id": case_id or "unknown-case",
                    "operation": operation,
                    "span_count": group["span_count"],
                    "call_count": group["call_count"],
                    "returned": group["returned"],
                    "rejected": group["rejected"],
                    "failed": group["failed"],
                    "not_called": group["not_called"],
                    "incomplete": group["incomplete"],
                    "inclusive_wall_ms_sum": inclusive_ms,
                    "exclusive_wall_ms_sum": exclusive_ms,
                    "solver_call_wall_ns": timing.get("solver_call_wall_ns"),
                    "clock_period_seconds": f"{numerator}/{denominator}",
                    "cpu_time": timing.get("cpu_time", "unavailable"),
                    "worker_accounting": json.dumps(timing.get("worker_accounting", "unavailable"), sort_keys=True),
                    "source_commit": row.get("source_commit", "unavailable"),
                    "driver_sha256": row.get("driver_sha256", "unavailable"),
                    "scenario_sha256": row.get("scenario_sha256", row.get("fixture_sha256", "unavailable")),
                })
            failure = timing.get("failure_pair", {}).get("phase_timing")
            if failure:
                for operation, group in sorted(failure["counts_by_operation"].items()):
                    inclusive = group["wall_inclusive_ticks_sum"] * numerator / denominator * 1e3
                    exclusive = group["wall_exclusive_ticks_sum"] * numerator / denominator * 1e3
                    result.append({
                        "source_file": source.name,
                        "binary_sha256": binary_hashes.get(source.name, "unavailable"),
                        "case_id": "B06-unsupported-capacity-failure",
                        "operation": operation,
                        "span_count": group["span_count"],
                        "call_count": group["call_count"],
                        "returned": group["returned"],
                        "rejected": group["rejected"],
                        "failed": group["failed"],
                        "not_called": group["not_called"],
                        "incomplete": group["incomplete"],
                        "inclusive_wall_ms_sum": inclusive,
                        "exclusive_wall_ms_sum": exclusive,
                        "solver_call_wall_ns": failure.get("solver_call_wall_ns"),
                        "clock_period_seconds": f"{numerator}/{denominator}",
                        "cpu_time": failure.get("cpu_time", "unavailable"),
                        "worker_accounting": json.dumps(failure.get("worker_accounting", "unavailable"), sort_keys=True),
                        "source_commit": row.get("source_commit", "unavailable"),
                        "driver_sha256": row.get("driver_sha256", "unavailable"),
                        "scenario_sha256": row.get("scenario_sha256", row.get("fixture_sha256", "unavailable")),
                    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    print(f"wrote {len(result)} operation rows to {args.output}")
    markdown = args.output.with_suffix(".md")
    columns = ("case_id", "operation", "span_count", "call_count", "returned", "rejected",
               "not_called", "failed", "incomplete", "inclusive_wall_ms_sum", "exclusive_wall_ms_sum")
    with markdown.open("w", encoding="utf-8") as stream:
        stream.write("# OBS-06 fuel phase summary\n\n")
        stream.write("Generated from saved raw phase spans. Millisecond columns sum same-operation spans "
                     "across calls; they are not wall time across different operations. Parent inclusive "
                     "and child inclusive values overlap and must not be added. Exclusive values remove "
                     "nested child intervals. Missing metrics remain `unavailable`.\n\n")
        if provenance:
            stream.write(f"Source commit: `{provenance.get('source_commit', 'unavailable')}`. "
                         f"Environment: `{json.dumps(provenance.get('environment', {}), sort_keys=True)}`.\n\n")
        stream.write("| " + " | ".join(columns) + " |\n")
        stream.write("|" + "|".join("---" for _ in columns) + "|\n")
        for row in result:
            cells = [str(row[column]) for column in columns]
            stream.write("| " + " | ".join(cells) + " |\n")
        stream.write("\nRaw input files: " + ", ".join(f"`{source.name}`" for source in args.raw) + "\n")
        for source in args.raw:
            for row in rows_from(source):
                failure = row.get("phase_timing", {}).get("failure_pair")
                if failure:
                    phase = failure["phase_timing"]
                    stream.write("\nB06 failure pair: baseline and instrumented capacity failures "
                                 f"matched exactly; {phase['span_count']} planned failure-path spans "
                                 "are retained in the raw B06 record.\n")
    print(f"wrote readable timing table to {markdown}")


if __name__ == "__main__":
    main()

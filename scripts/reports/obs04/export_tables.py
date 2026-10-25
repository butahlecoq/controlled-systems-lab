#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
from fractions import Fraction
from typing import Any

_RENDERER_SPEC = importlib.util.spec_from_file_location(
    "obs04_saved_renderer_for_tables", Path(__file__).with_name("render_saved.py"))
render_saved = importlib.util.module_from_spec(_RENDERER_SPEC)
sys.modules[_RENDERER_SPEC.name] = render_saved
_RENDERER_SPEC.loader.exec_module(render_saved)
DESCRIPTION = "Export saved OBS-04 records as raw attempt and module timing tables."


def _availability(value: Any) -> tuple[str, Any, str]:
    if isinstance(value, dict) and value.get("state") in {"available", "unavailable"}:
        return value["state"], value.get("value"), value.get("reason", "")
    if value is None:
        return "unavailable", "", "not_recorded"
    return "available", value, ""


def _measurement_metric(measurement: dict[str, Any], name: str) -> tuple[str, Any, str]:
    value = measurement.get(name)
    if value is None:
        return "unavailable", "", "not_recorded"
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"measurement {name} must be a non-negative finite number or null")
    return "available", value, ""


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return render_saved._canonical_json(value)
    return value


def _duration_ns(span: dict[str, Any], clocks: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
    interval = span.get("interval", {})
    if interval.get("kind") != "ticks":
        return "unavailable", "", interval.get("kind", "not_recorded")
    endpoints = interval.get("value", {})
    start, end = endpoints.get("start", {}), endpoints.get("end", {})
    if start.get("state") != "available" or end.get("state") != "available":
        return "unavailable", "", "endpoint_unavailable"
    descriptor = span.get("descriptor", {})
    clock_id = descriptor.get("clock", "")
    clock = clocks.get(clock_id, {})
    numerator, denominator = clock.get("period_numerator"), clock.get("period_denominator")
    try:
        ticks = int(end["value"]) - int(start["value"])
        numerator, denominator = int(numerator), int(denominator)
    except (TypeError, ValueError):
        return "unavailable", "", "clock_period_unavailable"
    if ticks < 0 or numerator <= 0 or denominator <= 0:
        return "unavailable", "", "invalid_interval_or_clock_period"
    return "available", str(Fraction(ticks * numerator * 1_000_000_000, denominator)), ""


def _interval(span: dict[str, Any]) -> tuple[str, int, int] | None:
    interval = span.get("interval", {})
    if interval.get("kind") != "ticks":
        return None
    descriptor = span.get("descriptor", {})
    endpoints = interval.get("value", {})
    start, end = endpoints.get("start", {}), endpoints.get("end", {})
    if start.get("state") != "available" or end.get("state") != "available":
        return None
    try:
        start_value, end_value = int(start["value"]), int(end["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if end_value < start_value:
        return None
    return str(descriptor.get("clock", "")), start_value, end_value


def _exclusive_wall_ns(span: dict[str, Any], spans: list[dict[str, Any]],
                       clocks: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
    own = _interval(span)
    if own is None:
        return "unavailable", "", "interval_unavailable"
    if span.get("completion_observed") is not True:
        return "unavailable", "", "incomplete_span"
    clock_id, start, end = own
    descriptor = span.get("descriptor", {})
    own_id = str(descriptor.get("id", {}).get("value", ""))
    by_id = {str(item.get("descriptor", {}).get("id", {}).get("value", "")): item for item in spans}
    descendants = []
    for candidate in spans:
        candidate_id = str(candidate.get("descriptor", {}).get("id", {}).get("value", ""))
        if candidate_id == own_id:
            continue
        current = candidate
        seen = set()
        while True:
            current_id = str(current.get("descriptor", {}).get("id", {}).get("value", ""))
            if current_id in seen:
                return "unavailable", "", "invalid_parent_cycle"
            seen.add(current_id)
            parent = current.get("descriptor", {}).get("parent")
            if not isinstance(parent, dict):
                break
            parent_id = str(parent.get("id", {}).get("value", ""))
            if parent_id == own_id:
                if candidate.get("completion_observed") is not True:
                    return "unavailable", "", "incomplete_descendant_span"
                interval = _interval(candidate)
                if interval is None:
                    execution = candidate.get("execution", {})
                    if execution.get("kind") == "known_not_called":
                        break
                    return "unavailable", "", "descendant_interval_unavailable"
                if interval[0] != clock_id:
                    return "unavailable", "", "descendant_clock_mismatch"
                descendants.append((max(start, interval[1]), min(end, interval[2])))
                break
            current = by_id.get(parent_id)
            if current is None:
                break

    intervals = sorted((a, b) for a, b in descendants if a < b)
    covered = 0
    if intervals:
        merged_start, merged_end = intervals[0]
        for next_start, next_end in intervals[1:]:
            if next_start <= merged_end:
                merged_end = max(merged_end, next_end)
            else:
                covered += merged_end - merged_start
                merged_start, merged_end = next_start, next_end
        covered += merged_end - merged_start
    clock = clocks.get(clock_id, {})
    try:
        numerator, denominator = int(clock["period_numerator"]), int(clock["period_denominator"])
    except (KeyError, TypeError, ValueError):
        return "unavailable", "", "clock_period_unavailable"
    if numerator <= 0 or denominator <= 0:
        return "unavailable", "", "invalid_clock_period"
    ticks = end - start - covered
    return "available", str(Fraction(ticks * numerator * 1_000_000_000, denominator)), ""


def export_tables(record_path: Path, output_dir: Path) -> None:
    source = record_path.resolve(strict=True)
    target = output_dir.resolve()
    if source == target or source in target.parents:
        raise ValueError("output directory must not contain or replace the input record")
    record = render_saved.load_record(source)
    raw_bytes = source.read_bytes()
    raw_digest = hashlib.sha256(raw_bytes).hexdigest()

    attempt_fields = ["comparison_run_id", "comparison_spec_id", "track", "input_manifest_hash", "arm_index",
                      "repetition_index", "run_id", "run_digest", "reported_status", "event_status",
                      "phase_status", "outcome", "complete_family_verified", "strategy", "instrumentation",
                      "warmup", "final_result_json", "selection_evidence_json", "resource_observation_json",
                      "measurement_payload_json"]
    metric_names = ("strategy_run_ns", "strategy_run_cpu_ns", "worker_work_ns", "setup_ns", "family_construction_ns",
                    "first_witness_query_ns", "additional_witness_query_ns", "verification_ns",
                    "end_to_end_ns", "plot_export_ns", "observed_backend_scheduler_width")
    for metric in metric_names:
        attempt_fields.extend((metric, metric + "_availability", metric + "_reason"))
    attempt_fields.extend(("strategy_run_cpu_scope", "strategy_run_peak_rss_bytes",
                          "strategy_run_peak_rss_availability", "strategy_run_peak_rss_scope",
                          "strategy_run_peak_rss_reason"))
    attempt_rows = []
    span_rows = []
    grouped_spans: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    spec = record["_parsed_spec"]
    for attempt in record["_parsed_attempts"]:
        measurement, run = attempt["_measurement"], attempt["_run"]
        base = {"comparison_run_id": record["comparison_run_id"],
                "comparison_spec_id": record["comparison_spec_id"],
                "track": record["track"],
                "input_manifest_hash": spec["input_manifest_hash"],
                "arm_index": attempt["arm_index"], "repetition_index": attempt["repetition_index"],
                "run_id": attempt["run_id"], "run_digest": attempt["run_digest"],
                "reported_status": attempt["reported_status"], "event_status": measurement.get("status"),
                "phase_status": measurement.get("phase_status"), "outcome": measurement.get("outcome"),
                "complete_family_verified": measurement.get("complete_family_verified"),
                "strategy": measurement.get("strategy"), "instrumentation": measurement.get("instrumentation"),
                "warmup": str(measurement.get("warmup", "")).lower(),
                "final_result_json": render_saved._canonical_json(run.get("final")),
                "selection_evidence_json": render_saved._canonical_json(run.get("selection")),
                "resource_observation_json": render_saved._canonical_json(run.get("resources")),
                "measurement_payload_json": render_saved._canonical_json(measurement)}
        for metric in metric_names:
            state, value, reason = _measurement_metric(measurement, metric)
            if metric in {"worker_work_ns", "setup_ns", "plot_export_ns"} and metric not in measurement:
                reason = "not_in_event_schema"
            base[metric], base[metric + "_availability"], base[metric + "_reason"] = value, state, reason
        base["strategy_run_cpu_scope"] = "process" if measurement.get("strategy_run_cpu_ns") is not None else "unavailable"
        rss = measurement.get("strategy_run_peak_rss")
        if isinstance(rss, dict):
            base["strategy_run_peak_rss_bytes"] = rss.get("value_bytes", "")
            base["strategy_run_peak_rss_availability"] = rss.get("status", "unavailable")
            base["strategy_run_peak_rss_scope"] = rss.get("scope", "")
            base["strategy_run_peak_rss_reason"] = rss.get("reason") or ""
        else:
            base["strategy_run_peak_rss_bytes"] = ""
            base["strategy_run_peak_rss_availability"] = "unavailable"
            base["strategy_run_peak_rss_scope"] = "unavailable"
            base["strategy_run_peak_rss_reason"] = "not_recorded"
        attempt_rows.append(base)

        stats = run.get("statistics", {})
        clock_map = {clock.get("id"): clock for clock in stats.get("clocks", [])}
        spans = stats.get("spans", [])
        for span in spans:
            descriptor = span.get("descriptor", {})
            module = descriptor.get("module", {})
            duration_state, duration_ns, duration_reason = _duration_ns(span, clock_map)
            exclusive_state, exclusive_ns, exclusive_reason = _exclusive_wall_ns(span, spans, clock_map)
            execution = span.get("execution", {})
            iterations_state, iterations_value, iterations_reason = _availability(span.get("iterations"))
            input_state, input_size, input_reason = _availability(descriptor.get("input_size"))
            output_state, output_size, output_reason = _availability(descriptor.get("output_size"))
            row = {
                "comparison_run_id": record["comparison_run_id"], "repetition_index": attempt["repetition_index"],
                "arm_index": attempt["arm_index"],
                "run_id": attempt["run_id"], "run_digest": attempt["run_digest"],
                "reported_status": attempt["reported_status"], "strategy": measurement.get("strategy"),
                "instrumentation": measurement.get("instrumentation"),
                "execution_kind": execution.get("kind"), "warmup": str(measurement.get("warmup", "")).lower(),
                "span_id": descriptor.get("id", {}).get("value"),
                "parent_span_id": descriptor.get("parent", {}).get("id", {}).get("value"),
                "parent_kind": descriptor.get("parent", {}).get("kind"),
                "task": descriptor.get("task"), "operation": descriptor.get("operation"),
                "module": module.get("id"), "module_version": module.get("version"),
                "backend": _csv_value(descriptor.get("backend")), "program": _csv_value(descriptor.get("program")),
                "stage": _csv_value(descriptor.get("stage")), "query": _csv_value(descriptor.get("query")),
                "clock": descriptor.get("clock"), "duration_ns": duration_ns,
                "duration_availability": duration_state, "duration_reason": duration_reason,
                "exclusive_wall_ns": exclusive_ns, "exclusive_wall_availability": exclusive_state,
                "exclusive_wall_reason": exclusive_reason,
                "status": json.dumps(span.get("status"), sort_keys=True, separators=(",", ":")),
                "termination": span.get("termination", {}).get("value"),
                "iterations": iterations_value, "iterations_availability": iterations_state,
                "iterations_reason": iterations_reason,
                "input_representation": descriptor.get("input_representation"),
                "input_size": input_size, "input_size_availability": input_state, "input_size_reason": input_reason,
                "output_representation": descriptor.get("output_representation"),
                "output_size": output_size, "output_size_availability": output_state, "output_size_reason": output_reason,
                "cpu_scope": "not_exposed_per_span", "cpu_availability": "unavailable",
                "cpu_reason": "run_record_schema_has_no_per_span_cpu",
                "memory_scope": "not_exposed_per_span", "memory_availability": "unavailable",
                "memory_reason": "run_record_schema_has_no_per_span_memory",
            }
            span_rows.append(row)
            key = (str(row["arm_index"]), str(row["strategy"]), str(row["instrumentation"]), str(row["task"]),
                   str(row["operation"]), str(row["module"]), str(row["backend"]), str(row["stage"]),
                   str(row["query"]), str(row["clock"]))
            grouped_spans.setdefault(key, []).append(row)

    target.mkdir(parents=True, exist_ok=False)
    raw_path = target / "comparison-record.json"
    raw_path.write_bytes(raw_bytes)
    _write_csv(target / "attempts.csv", attempt_fields, attempt_rows)

    phase_summary_fields = ["arm_index", "strategy", "instrumentation", "metric", "unit", "measured_attempts",
                            "available_values", "unavailable_values", "median", "p95", "minimum", "maximum",
                            "tail_statistic"]
    phase_summary_rows = []
    for arm_index in range(len(spec["arms"])):
        arm = spec["arms"][arm_index]
        arm_attempts = [row for row in attempt_rows if row["arm_index"] == arm_index and row["warmup"] != "true"]
        for metric in metric_names:
            values = sorted(row[metric] for row in arm_attempts
                            if row[metric + "_availability"] == "available"
                            and isinstance(row[metric], (int, float)) and not isinstance(row[metric], bool))
            p95 = values[max(0, (95 * len(values) + 99) // 100 - 1)] if values else ""
            reasons = sorted({row[metric + "_reason"] for row in arm_attempts
                              if row[metric + "_availability"] != "available"})
            phase_summary_rows.append({
                "arm_index": arm_index, "strategy": arm["strategy"], "instrumentation": arm["instrumentation"],
                "metric": metric, "unit": "ns" if metric.endswith("_ns") else "count",
                "measured_attempts": len(arm_attempts), "available_values": len(values),
                "unavailable_values": len(arm_attempts) - len(values),
                "median": str(Fraction(sum(values), len(values))) if values else "", "p95": p95,
                "minimum": min(values) if values else "", "maximum": max(values) if values else "",
                "tail_statistic": "nearest-rank p95; unavailable reasons: " + (", ".join(reasons) if reasons else "none"),
            })
    _write_csv(target / "phase-summary.csv", phase_summary_fields, phase_summary_rows)

    span_fields = list(span_rows[0].keys()) if span_rows else [
        "comparison_run_id", "repetition_index", "arm_index", "run_id", "run_digest", "reported_status", "strategy",
        "instrumentation", "span_id", "parent_span_id", "parent_kind", "task", "operation", "module",
        "module_version", "backend", "program", "stage", "query", "clock", "duration_ns",
        "duration_availability", "duration_reason", "exclusive_wall_ns", "exclusive_wall_availability",
        "exclusive_wall_reason", "status", "termination", "execution_kind", "warmup", "iterations",
        "iterations_availability", "iterations_reason", "input_representation", "input_size",
        "input_size_availability", "input_size_reason", "output_representation", "output_size",
        "output_size_availability", "output_size_reason", "cpu_scope", "cpu_availability", "cpu_reason",
        "memory_scope", "memory_availability", "memory_reason"]
    _write_csv(target / "module-spans.csv", span_fields, span_rows)

    summary_fields = ["arm_index", "strategy", "instrumentation", "task", "operation", "module", "backend", "stage", "query",
                      "clock", "planned_spans", "observed_calls", "available_durations", "median_ns", "p95_ns",
                      "minimum_ns", "maximum_ns", "available_exclusive_durations", "median_exclusive_wall_ns", "p95_exclusive_wall_ns",
                      "tail_statistic"]
    summary_rows = []
    for key, rows in sorted(grouped_spans.items()):
        measured_rows = [row for row in rows if row["warmup"] != "true"]
        durations = sorted(Fraction(row["duration_ns"]) for row in measured_rows
                           if row["duration_availability"] == "available")
        exclusive_durations = sorted(Fraction(row["exclusive_wall_ns"]) for row in measured_rows
                                     if row["exclusive_wall_availability"] == "available")
        p95 = durations[max(0, (95 * len(durations) + 99) // 100 - 1)] if durations else ""
        observed_calls = sum(row["execution_kind"] == "observed_return" for row in measured_rows)
        summary_rows.append(dict(zip(summary_fields, [*key, len(measured_rows), observed_calls, len(durations),
            str(statistics.median(durations)) if durations else "", str(p95) if durations else "",
            min(durations) if durations else "", max(durations) if durations else "",
            len(exclusive_durations),
            str(statistics.median(exclusive_durations)) if exclusive_durations else "",
            str(exclusive_durations[max(0, (95 * len(exclusive_durations) + 99) // 100 - 1)]) if exclusive_durations else "",
            "nearest-rank p95; spans are per attempt and are not summed"])))
    _write_csv(target / "module-summary.csv", summary_fields, summary_rows)

    manifest = {
        "schema": "csl.obs05-export/1", "comparison_run_id": record["comparison_run_id"],
        "comparison_spec_id": record["comparison_spec_id"], "input_manifest_hash": spec["input_manifest_hash"],
        "track": record["track"],
        "raw_record_file": raw_path.name, "raw_record_sha256": raw_digest,
        "exports": ["attempts.csv", "phase-summary.csv", "module-spans.csv", "module-summary.csv"],
        "source": "saved comparison record only; no solver, selector, or provider calls",
        "duration": "Recorded clock ticks converted with the persisted clock period to exact rational nanoseconds.",
        "cpu_and_memory": "Run-level process CPU and peak RSS observations remain in attempts.csv with scope and availability; per-span values are explicitly unavailable when the run schema does not expose them.",
        "aggregation": "Phase and module summaries use measured attempts only and report median plus nearest-rank p95. Unavailable phases remain explicit. Span durations retain exact rational nanoseconds; every attempt remains in the raw record and CSV exports.",
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--record", type=Path, required=True, help="saved csl.comparison-record/1 JSON")
    parser.add_argument("--out-dir", type=Path, required=True, help="new directory for CSV and raw-record exports")
    args = parser.parse_args()
    try:
        export_tables(args.record, args.out_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(f"Exported saved OBS-04 tables to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

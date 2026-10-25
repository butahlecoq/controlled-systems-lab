#!/usr/bin/env python3
"""Render a comparison-record JSON file without running a solver."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
from typing import Any


def _json_value(value: Any, field: str) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{field} is not valid JSON: {error}") from error
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _run_status(run: dict[str, Any]) -> str:
    final = run.get("final")
    if not isinstance(final, dict):
        raise ValueError("recorded run final result is missing")
    kind = final.get("kind")
    value = final.get("value")
    if kind in {"synthesis", "program"} and isinstance(value, dict):
        result = value.get("result", {}) if kind == "program" else value
        termination = result.get("termination")
        return {
            "completed": "completed",
            "cancelled": "cancelled",
            "resource_limit": "resource_limited",
            "operation_rejected": "unsupported",
            "contract_rejected": "failed",
            "numerical_failure": "failed",
        }.get(termination, "invalid")
    if kind in {"unsupported", "failed"}:
        return kind
    if kind == "skipped" and isinstance(value, dict):
        reason = value.get("reason")
        if reason == "cancelled":
            return "cancelled"
        if reason in {"deadline", "task_limit", "reservation_exceeds_budget"}:
            return "resource_limited"
        if reason == "batch_failed":
            return "incomplete"
    return "invalid"


def load_record(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or set(record) != {
        "schema", "comparison_run_id", "comparison_spec_id", "spec", "attempts", "track"
    } or record.get("schema") != "csl.comparison-record/1":
        raise ValueError("record schema must be csl.comparison-record/1")
    if record.get("track") != "new-comparison":
        raise ValueError("comparison record track must be new-comparison")
    if not isinstance(record.get("attempts"), list):
        raise ValueError("record attempts must be an array")
    spec_text = record.get("spec")
    if not isinstance(spec_text, str):
        raise ValueError("record spec must be a canonical JSON string")
    spec = _json_value(spec_text, "record spec")
    if not isinstance(spec, dict) or spec.get("schema") != "csl.comparison-spec/3":
        raise ValueError("record spec must use csl.comparison-spec/3")
    if set(spec) != {"arms", "environment", "input_manifest_hash", "input_manifest_source",
                     "problem_id", "repetitions", "request_digest", "schema"}:
        raise ValueError("comparison spec fields are invalid")
    if _canonical_json(spec) != spec_text:
        raise ValueError("record spec is not canonical JSON")
    input_hash = spec.get("input_manifest_hash")
    problem_id = spec.get("problem_id")
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    if (not isinstance(input_hash, str) or not digest_pattern.fullmatch(input_hash) or
            spec.get("input_manifest_source") != "resolved-problem-canonical-bytes" or
            not isinstance(problem_id, str) or problem_id != "csl.problem.v1.sha256:" + input_hash):
        raise ValueError("comparison spec problem identity and input manifest hash disagree")
    if not isinstance(spec.get("request_digest"), str) or not digest_pattern.fullmatch(spec["request_digest"]):
        raise ValueError("comparison spec request digest is invalid")
    spec_id = hashlib.sha256(spec_text.encode("utf-8")).hexdigest()
    if record.get("comparison_spec_id") != spec_id:
        raise ValueError("comparison spec identity does not match its saved spec")
    arms = spec.get("arms")
    repetitions = spec.get("repetitions")
    if (not isinstance(arms, list) or not arms or
            not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1):
        raise ValueError("comparison spec arms or repetition count are invalid")
    if any(not isinstance(arm, dict) or set(arm) != {"configuration_id", "strategy", "instrumentation"}
           for arm in arms):
        raise ValueError("comparison spec arm fields are invalid")
    if any(not isinstance(arm["strategy"], str) or not arm["strategy"] or
           not isinstance(arm["instrumentation"], str) or arm["instrumentation"] not in {"enabled", "disabled"} or
           not isinstance(arm["configuration_id"], str) for arm in arms):
        raise ValueError("comparison spec arm values are invalid")
    if len(record["attempts"]) != len(arms) * repetitions:
        raise ValueError("comparison record does not contain every ordered attempt")
    record["_parsed_spec"] = spec
    parsed_attempts = []
    for index, attempt in enumerate(record["attempts"]):
        if not isinstance(attempt, dict) or set(attempt) != {
            "arm_index", "measurement_payload", "repetition_index", "reported_status", "run", "run_digest", "run_id"
        }:
            raise ValueError(f"attempts[{index}] must be an object")
        measurement = _json_value(attempt.get("measurement_payload"), f"attempts[{index}].measurement_payload")
        if not isinstance(measurement, dict):
            raise ValueError(f"attempts[{index}].measurement_payload must be an object")
        arm_index, repetition_index = divmod(index, repetitions)
        if attempt.get("arm_index") != arm_index or attempt.get("repetition_index") != repetition_index:
            raise ValueError(f"attempts[{index}] is out of comparison-spec order")
        run_text = attempt.get("run")
        if not isinstance(run_text, str):
            raise ValueError(f"attempts[{index}].run must be a JSON string")
        run = _json_value(run_text, f"attempts[{index}].run")
        if not isinstance(run, dict) or _canonical_json(run) != run_text:
            raise ValueError(f"attempts[{index}].run is not a canonical saved run")
        if hashlib.sha256(run_text.encode("utf-8")).hexdigest() != attempt.get("run_digest"):
            raise ValueError(f"attempts[{index}] run digest does not match the saved run")
        arm = arms[arm_index]
        config = run.get("configuration")
        config_value = config.get("value") if isinstance(config, dict) else None
        strategy_config = config_value.get("strategy") if isinstance(config_value, dict) else None
        collection_config = config_value.get("collection") if isinstance(config_value, dict) else None
        expected_status = attempt.get("reported_status")
        measurement_to_reported = {
            "passed": "completed", "failed": "failed", "unsupported": "unsupported",
            "cancelled": "cancelled", "resource_limited": "resource_limited", "incomplete": "incomplete",
        }
        event_schema = measurement.get("schema")
        if event_schema in {
                "csl.obs04-instrumentation-comparison-event/6",
                "csl.obs04-instrumentation-comparison-event/7",
                "csl.obs04-instrumentation-comparison-event/8",
                "csl.obs04-instrumentation-comparison-event/9"}:
            phase_status = measurement.get("phase_status")
            if phase_status not in {"passed", "failed"}:
                raise ValueError(f"attempts[{index}] phase status is invalid")
            if measurement.get("analytic_family_checked") is not (phase_status == "passed"):
                raise ValueError(f"attempts[{index}] analytic-check flag disagrees with phase status")
            complete_family = measurement.get("complete_family_verified")
            if not isinstance(complete_family, bool) or (phase_status == "passed" and not complete_family):
                raise ValueError(f"attempts[{index}] passed phase lacks complete-family evidence")
        expected_strategy = arm.get("strategy") if isinstance(arm, dict) else None
        expected_instrumentation = arm.get("instrumentation") if isinstance(arm, dict) else None
        if not isinstance(config_value, dict):
            raise ValueError(f"attempts[{index}] configuration value is invalid")
        semantic_config = copy.deepcopy(config_value)
        for module in semantic_config.get("modules", []):
            pin = module.get("pin", {})
            if pin.get("state") == "unavailable":
                pin["detail"] = ""
        config_material = b"CSL.RESOLVED.CONFIG\0v1\0" + _canonical_json(semantic_config).encode("utf-8")
        expected_config_id = "csl.config.v1.sha256:" + hashlib.sha256(config_material).hexdigest()
        common_request = copy.deepcopy(config_value)
        common_request.pop("modules", None)
        common_request.get("collection", {}).pop("enabled", None)
        if isinstance(common_request.get("strategy"), dict):
            strategy = common_request["strategy"]
            common_request["strategy"] = {
                "selector": strategy.get("selector"),
                "representation": strategy.get("representation"),
            }
        request_digest = hashlib.sha256(_canonical_json(common_request).encode("utf-8")).hexdigest()
        if (run.get("schema") not in {"csl.run-statistics/5", "csl.run-statistics/6"} or
                run.get("recorded_state") != "unverified_recorded_data" or
                run.get("run") != attempt.get("run_id") or run.get("problem") != spec.get("problem_id") or
                not isinstance(config, dict) or config.get("id") != arm.get("configuration_id") or
                config.get("id") != expected_config_id or request_digest != spec.get("request_digest") or
                not isinstance(strategy_config, dict) or strategy_config.get("strategy") != expected_strategy or
                not isinstance(collection_config, dict) or collection_config.get("enabled") != (expected_instrumentation == "enabled") or
                _run_status(run) != expected_status or
                attempt.get("reported_status") not in set(measurement_to_reported.values()) or
                measurement_to_reported.get(measurement.get("status")) != expected_status or
                event_schema not in {f"csl.obs04-instrumentation-comparison-event/{n}" for n in range(2, 10)} or
                measurement.get("strategy") != expected_strategy or
                measurement.get("instrumentation") != expected_instrumentation or
                measurement.get("repetition") != repetition_index or
                measurement.get("warmup") != (repetition_index == 0)):
            raise ValueError(f"attempts[{index}] identity or status does not match the saved spec and run")
        if event_schema in {"csl.obs04-instrumentation-comparison-event/8",
                            "csl.obs04-instrumentation-comparison-event/9"}:
            for field in ("strategy_run_cpu_ns", "observed_backend_scheduler_width"):
                if field not in measurement:
                    raise ValueError(f"attempts[{index}] {field} is required by event schema /8")
                value = measurement.get(field)
                if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                    raise ValueError(f"attempts[{index}] {field} must be a non-negative integer or null")
            width = measurement["observed_backend_scheduler_width"]
            if width == 0:
                raise ValueError(f"attempts[{index}] observed_backend_scheduler_width must be positive or null")
        if event_schema == "csl.obs04-instrumentation-comparison-event/9":
            rss = measurement.get("strategy_run_peak_rss")
            if not isinstance(rss, dict):
                raise ValueError(f"attempts[{index}] strategy_run_peak_rss must be an object")
            if (rss.get("metric") != "process_peak_rss_bytes" or
                    rss.get("scope") != "process_vm_hwm_reset_before_and_read_after_strategy_run"):
                raise ValueError(f"attempts[{index}] strategy_run_peak_rss metric or scope is invalid")
            rss_status, value, reason = rss.get("status"), rss.get("value_bytes"), rss.get("reason")
            if rss_status not in {"available", "unavailable", "not_measured"}:
                raise ValueError(f"attempts[{index}] strategy_run_peak_rss status is invalid")
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"attempts[{index}] strategy_run_peak_rss value_bytes must be a non-negative integer or null")
            if rss_status == "available":
                if value is None or reason is not None:
                    raise ValueError(f"attempts[{index}] available strategy_run_peak_rss needs a value and null reason")
            elif value is not None or not isinstance(reason, str) or not reason:
                raise ValueError(f"attempts[{index}] unavailable strategy_run_peak_rss needs null value and a reason")
        parsed_attempts.append({**attempt, "_measurement": measurement, "_run": run})
    identity_material = {
        "attempts": record["attempts"],
        "comparison_spec_id": spec_id,
        "schema": "csl.comparison-record/1",
    }
    run_id = hashlib.sha256(_canonical_json(identity_material).encode("utf-8")).hexdigest()
    if record.get("comparison_run_id") != run_id:
        raise ValueError("comparison run identity does not match its ordered attempts")
    record["_parsed_attempts"] = parsed_attempts
    return record


def _cell(value: Any) -> str:
    if value is None:
        value = "—"
    elif isinstance(value, bool):
        value = str(value).lower()
    return html.escape(str(value), quote=True)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_cell(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(record: dict[str, Any]) -> str:
    spec = record["_parsed_spec"]
    attempts = record["_parsed_attempts"]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    statuses: dict[str, int] = {}
    for attempt in attempts:
        measurement = attempt["_measurement"]
        key = (str(measurement.get("strategy", "unknown")), str(measurement.get("instrumentation", "unknown")))
        groups.setdefault(key, []).append(attempt)
        status = str(attempt.get("reported_status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1

    summary_rows: list[list[Any]] = []
    metric_names = ("strategy_run_ns", "strategy_run_cpu_ns", "family_construction_ns", "first_witness_query_ns",
                    "additional_witness_query_ns", "verification_ns", "end_to_end_ns")
    for (strategy, instrumentation), group in sorted(groups.items()):
        measured = [a for a in group if not a["_measurement"].get("warmup", False)]
        passed = [a for a in measured if a["_measurement"].get("status") == "passed"
                  and a["_measurement"].get("phase_status") == "passed"]
        metric_summary = []
        for metric in metric_names:
            values = [a["_measurement"].get(metric) for a in passed]
            values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if values:
                median = int(statistics.median(values))
                metric_summary.append(f"{metric.removesuffix('_ns')}: {median} ns ({min(values)}–{max(values)})")
            else:
                metric_summary.append(f"{metric.removesuffix('_ns')}: unavailable")
        summary_rows.append([strategy, instrumentation, len(group) - len(measured), len(measured),
                             len(passed), "; ".join(metric_summary)])

    attempt_rows = []
    for attempt in attempts:
        m = attempt["_measurement"]
        attempt_rows.append([
            attempt.get("repetition_index"),
            attempt.get("run_id"),
            m.get("strategy"),
            m.get("instrumentation"),
            str(m.get("status", attempt.get("reported_status", "unknown"))) + "/" + str(m.get("phase_status", "—")),
            m.get("outcome"),
            m.get("strategy_run_ns"),
            m.get("strategy_run_cpu_ns"),
            m.get("observed_backend_scheduler_width"),
            _format_peak_rss(m.get("strategy_run_peak_rss")),
            m.get("end_to_end_ns"),
            attempt.get("run_digest"),
        ])

    environment = spec.get("environment", {})
    build = environment.get("build", {})
    runtime = environment.get("runtime", {})
    environment_rows = [
        ["Source revision", build.get("source_revision")],
        ["Source tree hash", build.get("source_tree_sha256")],
        ["Binary SHA-256", runtime.get("binary_sha256", {}).get("value")],
        ["Compiler", f"{build.get('compiler_id', 'unknown')} {build.get('compiler_version', 'unknown')}"],
        ["Build", build.get("build_type")],
        ["Operating system", runtime.get("os_version", {}).get("value")],
        ["Kernel", runtime.get("kernel", {}).get("value")],
        ["CPU", runtime.get("cpu_model", {}).get("value")],
        ["Input manifest", spec.get("input_manifest_hash")],
        ["Track", record.get("track")],
    ]
    status_text = ", ".join(f"{status}: {count}" for status, count in sorted(statuses.items())) or "none"
    problem = spec.get("problem_id", "unknown")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OBS-04 comparison record</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#202124}}
h1,h2{{line-height:1.2}} code{{overflow-wrap:anywhere}} table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}
th,td{{border:1px solid #bbb;padding:.45rem .6rem;text-align:left;vertical-align:top}} th{{background:#eef2f6}}
td{{overflow-wrap:anywhere}} .note{{border-left:4px solid #5478a4;padding:.5rem 1rem;background:#f4f7fa}}
</style></head><body>
<h1>OBS-04 comparison record</h1>
<p>Saved record only; rendering does not run a solver or alter the source evidence.</p>
<p><strong>Comparison run:</strong> <code>{_cell(record.get('comparison_run_id'))}</code><br>
<strong>Specification:</strong> <code>{_cell(record.get('comparison_spec_id'))}</code><br>
<strong>Problem:</strong> <code>{_cell(problem)}</code></p>
<h2>Environment and input identity</h2>{_table(["Field", "Recorded value"], environment_rows)}
<h2>Attempt summary</h2><p>{_cell(status_text)}</p>
{_table(["Strategy", "Instrumentation", "Warmups", "Measured", "Passed", "Passing-attempt phase medians/ranges"], summary_rows)}
<h2>All retained attempts</h2>
<p>Warmups, failed phases, and other non-passing outcomes remain listed. Timing summaries use measured attempts whose solver and post-run phase statuses both passed.</p>
{_table(["Repetition", "Run ID", "Strategy", "Instrumentation", "Status / phase", "Outcome", "Strategy wall (ns)", "Process CPU (ns)", "Backend scheduler width", "Process peak RSS", "End to end (ns)", "Run digest"], attempt_rows)}
<p class="note">Process CPU covers the whole process during the strategy call. Backend scheduler width is the maximum width reported by adapters; it is not a count of busy threads.</p>
<p class="note">Process peak RSS is the process VmHWM value after resetting its high-water mark immediately before the strategy call. It includes the driver and all process threads; unsupported platforms report an unavailable status. This is an observation, not a memory limit.</p>
<p class="note">A timing summary describes only the saved attempts. It is not a method winner claim; consult the saved evidence and limiter profile before making performance claims.</p>
</body></html>"""


def _format_peak_rss(value: Any) -> str:
    if not isinstance(value, dict):
        return "—"
    status = value.get("status", "unknown")
    amount = value.get("value_bytes")
    reason = value.get("reason")
    if amount is not None:
        return f"{status}: {amount} bytes"
    return f"{status}: {reason or 'no value'}"


def write_report(record_path: Path, output_path: Path) -> None:
    source = record_path.resolve(strict=True)
    target = output_path.resolve()
    if source == target or (target.exists() and source.samefile(target)):
        raise ValueError("HTML output must not replace the saved comparison record")
    record = load_record(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(record), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="saved csl.comparison-record/1 JSON file")
    parser.add_argument("--out", type=Path, required=True, help="HTML output path")
    args = parser.parse_args()
    try:
        write_report(args.record, args.out)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(f"Rendered saved comparison record to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

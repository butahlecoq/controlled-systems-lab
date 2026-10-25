#!/usr/bin/env python3
"""Render a comparison-record JSON file without running a solver."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import statistics
from typing import Any


def _json_value(value: Any, field: str) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{field} is not valid JSON: {error}") from error
    return value


def load_record(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema") != "csl.comparison-record/1":
        raise ValueError("record schema must be csl.comparison-record/1")
    if not isinstance(record.get("attempts"), list):
        raise ValueError("record attempts must be an array")
    spec = _json_value(record.get("spec"), "record spec")
    if not isinstance(spec, dict) or spec.get("schema") != "csl.comparison-spec/3":
        raise ValueError("record spec must use csl.comparison-spec/3")
    record["_parsed_spec"] = spec
    parsed_attempts = []
    for index, attempt in enumerate(record["attempts"]):
        if not isinstance(attempt, dict):
            raise ValueError(f"attempts[{index}] must be an object")
        measurement = _json_value(attempt.get("measurement_payload"), f"attempts[{index}].measurement_payload")
        if not isinstance(measurement, dict):
            raise ValueError(f"attempts[{index}].measurement_payload must be an object")
        parsed_attempts.append({**attempt, "_measurement": measurement})
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
    metric_names = ("strategy_run_ns", "family_construction_ns", "first_witness_query_ns",
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
{_table(["Repetition", "Run ID", "Strategy", "Instrumentation", "Status / phase", "Outcome", "Strategy run (ns)", "End to end (ns)", "Run digest"], attempt_rows)}
<p class="note">A timing summary describes only the saved attempts. It is not a method winner claim; consult the saved evidence and limiter profile before making performance claims.</p>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="saved csl.comparison-record/1 JSON file")
    parser.add_argument("--out", type=Path, required=True, help="HTML output path")
    args = parser.parse_args()
    try:
        record = load_record(args.record)
        document = render_html(record)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"Rendered {len(record['_parsed_attempts'])} saved attempts to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

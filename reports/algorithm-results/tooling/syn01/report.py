"""Saved-record validation, summary calculation, and standalone SYN-01 rendering."""
from __future__ import annotations

import html
import hashlib
import json
import math
import statistics

SCHEMA = "csl.syn01-nominal-forward-report/1"
EVENT_SCHEMA = "csl.syn01-nominal-forward-trial/1"
SCENARIOS = ("integrator", "ltv")
EXPECTED = {
    "integrator": [[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]],
    "ltv": [[1.0, 1.0], [3.0, 4.0], [-5.0, -4.0]],
}
SCENARIO_SPECS = {
    "integrator": {"x0": 0, "controls": [[0, 1], [0, 1]], "stages": ["x_next=x+u", "x_next=x+u"],
                   "state_constraints": [[0, 0], [0, 1], [0, 2]]},
    "ltv": {"x0": 1, "controls": [[0, 1], [0, 1]],
            "stages": ["x_next=2*x+u+1", "x_next=-x+2*u-2"],
            "state_constraints": [[0, 2], [3, 4], [-5, -4]]},
}
PHASES = ("setup_ns", "solve_ns", "oracle_ns", "execute_ns")
LIMITS = [
    "Complete 1-D H-row bounds over returned binary64 data; not an exact real-arithmetic certificate.",
    "Reachability relation assurance remains Unestablished; provider outputs are numerical.",
    "Two tiny analytic scalar fixtures only; no comparator, no speedup, no application-scale or scalability claim.",
    "No source-level profile was collected; the performance limiter and capacity remain unknown.",
    "Per-provider operation timings are unavailable; operation counts are derived from returned operation lineage.",
]


def _timing(values):
    if len(values) != 7:
        return {"median_ns": None, "min_ns": None, "max_ns": None,
                "range_ns": None, "successful_trials": len(values), "unavailable_trials": 7-len(values)}
    return {"median_ns": statistics.median(values), "min_ns": min(values), "max_ns": max(values),
            "range_ns": max(values)-min(values), "successful_trials": 7, "unavailable_trials": 0}


def summarize(trials):
    rows = []
    for scenario in SCENARIOS:
        measured = [row for row in trials if row.get("scenario") == scenario and not row.get("warmup")]
        all_successful = len(measured) == 7 and all(row.get("status") == "passed" and row.get("oracle_passed") is True for row in measured)
        phases = {}
        for phase in PHASES:
            values = [row.get(phase) for row in measured if type(row.get(phase)) is int and row[phase] >= 0] if all_successful else []
            phases[phase] = _timing(values)
        rows.append({"scenario": scenario, "attempts": len(measured),
                     "passed": sum(row.get("status") == "passed" and row.get("oracle_passed") is True for row in measured),
                     "failed": sum(row.get("status") != "passed" or row.get("oracle_passed") is not True for row in measured),
                     "phases": phases})
    return rows


def make_record(trials, *, source_commit, harness_commit, environment, provenance):
    rows = [dict(row) for row in trials]
    scenario_hashes = {name: hashlib.sha256(json.dumps(SCENARIO_SPECS[name], sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest() for name in SCENARIOS}
    expected_matrix = {(scenario, repetition) for scenario in SCENARIOS for repetition in range(8)}
    actual_matrix = {(row.get("scenario"), row.get("repetition")) for row in rows}
    failures = sum(row.get("status") != "passed" or row.get("oracle_passed") is not True for row in rows)
    state = "complete" if actual_matrix == expected_matrix and len(rows) == 16 and failures == 0 else "failed"
    return {
        "schema": SCHEMA,
        "report_id": "pending",
        "source_commit": source_commit,
        "harness_commit": harness_commit,
        "fixture_catalog": {name: {"input": SCENARIO_SPECS[name], "expected_marginals": EXPECTED[name]}
                            for name in SCENARIOS},
        "scenario_hashes": scenario_hashes,
        "environment": environment,
        "provenance": provenance,
        "measurement": {
            "kind": "descriptive_single_adapter",
            "scope": "Two-step discrete nominal-forward reachability on two authored scalar analytic fixtures",
            "warmups_per_fixture": 1,
            "measured_repetitions_per_fixture": 7,
            "fixture_order": "alternating forward/reverse by repetition",
            "requested_workers": 1,
            "configured_native_threads": 1,
            "operation_timing": "unavailable; the public provider seam exposes no per-operation timer",
            "timing_scopes": {
                "setup_ns": "fresh problem construction/resolution and provider registration/selection/preparation",
                "solve_ns": "nominal_forward() call only",
                "oracle_ns": "immediate returned-outcome consumption plus complete 1-D H-row bound verification",
                "execute_ns": "setup through independent H-row verification; excludes process startup/build/serialization/rendering",
            },
        },
        "support": "Unestablished",
        "evidence_limits": list(LIMITS),
        "trials": rows,
        "summary": summarize(rows),
        "collection": {"state": state, "counts": {"measured": sum(not row.get("warmup", False) for row in rows),
                                                       "warmups": sum(row.get("warmup", False) for row in rows),
                                                       "failures": failures,
                                                       "missing_or_duplicate": max(0, 16-len(set(actual_matrix)))},
                       "fixture_order": "alternating forward/reverse by repetition"},
    }


def validate_record(record):
    errors = []
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return ["unsupported_schema"]
    expected_catalog = {name: {"input": SCENARIO_SPECS[name], "expected_marginals": EXPECTED[name]}
                        for name in SCENARIOS}
    if record.get("fixture_catalog") != expected_catalog:
        errors.append("fixture_catalog_mismatch")
    expected_hashes = {name: hashlib.sha256(json.dumps(SCENARIO_SPECS[name], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest() for name in SCENARIOS}
    if record.get("scenario_hashes") != expected_hashes:
        errors.append("scenario_hashes_mismatch")
    for field in ("source_commit", "harness_commit"):
        value = record.get(field)
        if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            errors.append("invalid_" + field)
    trials = record.get("trials")
    if not isinstance(trials, list):
        return errors + ["trials_not_array"]
    seen = set()
    for row in trials:
        if not isinstance(row, dict) or row.get("schema") != EVENT_SCHEMA:
            errors.append("invalid_event_schema")
            continue
        scenario, repetition = row.get("scenario"), row.get("repetition")
        if scenario not in EXPECTED or type(repetition) is not int or repetition not in range(8):
            errors.append("invalid_trial_identity")
            continue
        key = (scenario, repetition)
        if key in seen:
            errors.append("duplicate_trial")
        seen.add(key)
        if row.get("warmup") is not (repetition == 0):
            errors.append("invalid_warmup_identity")
        if row.get("expected_marginals") != EXPECTED[scenario]:
            errors.append("literal_fixture_oracle_mismatch")
        if row.get("status") == "passed" and row.get("oracle_passed") is True:
            if row.get("outcome") != "forward_tube" or row.get("observed_marginals") != EXPECTED[scenario]:
                errors.append("literal_marginal_mismatch")
        for phase in PHASES:
            value = row.get(phase)
            if type(value) is not int or value < 0:
                errors.append("invalid_timing_" + phase)
        if all(type(row.get(phase)) is int and row[phase] >= 0 for phase in PHASES) and row["execute_ns"] < sum(row[phase] for phase in PHASES[:3]):
            errors.append("nested_timing_exceeds_end_to_end")
        counts = row.get("provider_operation_counts")
        if not isinstance(counts, dict) or any(type(value) is not int or value < 0 for value in counts.values()):
            errors.append("invalid_provider_operation_counts")
        if row.get("provider_operation_timing_ns") is not None:
            errors.append("unsupported_provider_operation_timing_claim")
    if len(trials) != 16 or seen != {(scenario, repetition) for scenario in SCENARIOS for repetition in range(8)}:
        errors.append("incomplete_trial_matrix")
    if record.get("summary") != summarize(trials):
        errors.append("summary_differs_from_trials")
    expected_failures = sum(row.get("status") != "passed" or row.get("oracle_passed") is not True for row in trials if isinstance(row, dict))
    collection = record.get("collection", {})
    if collection.get("counts") != {"measured": 14, "warmups": 2, "failures": expected_failures,
                                     "missing_or_duplicate": max(0, 16-len(seen))}:
        errors.append("collection_counts_mismatch")
    if collection.get("state") != ("complete" if not errors and expected_failures == 0 else "failed"):
        errors.append("collection_state_mismatch")
    return errors


def render_svg(record):
    errors = validate_record(record)
    if errors:
        raise ValueError("invalid SYN-01 report record: " + ", ".join(errors))
    values = [row["phases"]["execute_ns"]["median_ns"] for row in record["summary"]]
    maximum = max((value for value in values if value is not None), default=1)
    parts = []
    for index, (scenario, value) in enumerate(zip(SCENARIOS, values)):
        y = 30 + index * 46
        width = 0 if value is None else max(1, round(520 * value / maximum))
        label = "unavailable" if value is None else f"{value:g} ns"
        parts.append(f'<text x="8" y="{y+15}">{html.escape(scenario)}</text>'
                     f'<rect x="170" y="{y}" width="{width}" height="22" fill="#3572a5"/>'
                     f'<text x="{180+width}" y="{y+15}">{html.escape(label)}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 130" role="img" aria-label="End-to-end time by fixture">' + "".join(parts) + "</svg>"


def render_html(record):
    errors = validate_record(record)
    if errors:
        raise ValueError("invalid SYN-01 report record: " + ", ".join(errors))
    phase_headers = "".join(f"<th>{html.escape(phase)}</th>" for phase in PHASES)
    trial_rows = []
    for row in record["trials"]:
        trial_rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            row.get("scenario"), row.get("repetition"), "warmup" if row.get("warmup") else "measured",
            row.get("status"), row.get("outcome"), row.get("oracle_passed"), row.get("observed_marginals"),
            *(row.get(phase) for phase in PHASES), row.get("detail", ""))) + "</tr>")
    summary = []
    for row in record["summary"]:
        stats = [row["phases"][phase] for phase in PHASES]
        summary.append("<tr><th>" + html.escape(row["scenario"]) + "</th>" +
                       f"<td>{row['attempts']}</td><td>{row['passed']}</td><td>{row['failed']}</td>" +
                       "".join("<td>" + (f"{s['median_ns']} (range {s['min_ns']}–{s['max_ns']}) ns" if s["median_ns"] is not None else "unavailable") + "</td>" for s in stats) + "</tr>")
    limits = "".join("<li>" + html.escape(item) + "</li>" for item in record["evidence_limits"])
    report_id = html.escape(str(record.get("report_id")))
    state = html.escape(record["collection"]["state"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SYN-01 nominal forward report {report_id}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #b8c3cc;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#edf2f6}}.scroll{{overflow-x:auto}}code,td{{overflow-wrap:anywhere}}</style></head><body>
<h1>SYN-01 nominal forward reachability report</h1><p>Collection state: <strong>{state}</strong>. Report ID <code>{report_id}</code>.</p>
<p>Measured source <code>{html.escape(record['source_commit'])}</code>; report harness <code>{html.escape(record['harness_commit'])}</code>.</p>
<p>One registered provider stack; descriptive timings only, no speedup or comparison claim. Reachability support: <strong>Unestablished</strong>.</p>
<h2>Evidence limits</h2><ul>{limits}</ul><h2>Median end-to-end timing by fixture</h2>{render_svg(record)}
<div class="scroll"><table><thead><tr><th>Fixture</th><th>Measured trials</th><th>Passed</th><th>Failed</th>{phase_headers}</tr></thead><tbody>{''.join(summary)}</tbody></table></div>
<h2>Raw trial observations</h2><div class="scroll"><table><thead><tr><th>Fixture</th><th>Repetition</th><th>Kind</th><th>Status</th><th>Outcome</th><th>Oracle</th><th>Returned marginals</th>{phase_headers}<th>Detail</th></tr></thead><tbody>{''.join(trial_rows)}</tbody></table></div>
</body></html>'''

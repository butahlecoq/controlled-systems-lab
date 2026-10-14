"""Saved-record validation, summary calculation, and standalone SYN-01 rendering."""
from __future__ import annotations

import html
import hashlib
import json
import math
import statistics
import copy

SCHEMA = "csl.syn01-nominal-forward-report/2"
EVENT_SCHEMA = "csl.syn01-nominal-forward-trial/2"
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
PHASE_STATES = ("available", "partial", "not_reached")
TIMING_SCOPES = {
    "setup_ns": "fresh problem construction/resolution and provider registration/selection/preparation",
    "solve_ns": "nominal_forward() call only",
    "oracle_ns": "immediate returned-outcome consumption plus complete 1-D H-row bound verification",
    "execute_ns": "driver entry through verified result; includes numerical-policy, execution-context, and effective-settings construction; excludes process startup/build/serialization/collector validation/rendering",
}
RUNTIME_SETTINGS = {
    "numerical_policy": {"absolute_tolerance": 1e-8, "relative_tolerance": 1e-8},
    "highs": {"solver": "simplex", "presolve": "off", "parallel": "off", "threads": 1,
              "random_seed": 0, "allow_unbounded_or_infeasible": False, "log_to_console": True,
              "output_flag": True, "small_matrix_value": 1e-12, "large_matrix_value": "kHighsInf",
              "infinite_bound": "kHighsInf", "infinite_cost": "kHighsInf",
              "primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8,
              "simplex_iteration_limit": None, "time_limit": "kHighsInf (no deadline)"},
    "qhull": {"options": "qhull Qx", "max_ambient_dimension": None, "max_input_rows": None},
    "projection": {"output": "h", "max_rows": None},
    "affine_sum": {"max_candidates": None},
    "hull_reducer": {"default_registration": True},
}
LIMITS = [
    "Complete 1-D H-row bounds over returned binary64 data; not an exact real-arithmetic certificate.",
    "Reachability relation assurance remains Unestablished; provider outputs are numerical.",
    "Two tiny analytic scalar fixtures only; no comparator, no speedup, no application-scale or scalability claim.",
    "No source-level profile was collected; the performance limiter and capacity remain unknown.",
    "Per-provider operation timings are unavailable; operation counts are derived from returned operation lineage.",
]


def _timing(values, partial_trials, not_reached_trials):
    attempts = 7
    return {"median_ns": statistics.median(values) if values else None,
            "min_ns": min(values) if values else None,
            "max_ns": max(values) if values else None,
            "range_ns": max(values)-min(values) if values else None,
            "available_trials": len(values), "partial_trials": partial_trials,
            "not_reached_trials": not_reached_trials,
            "unavailable_trials": attempts-len(values),
            "coverage": "complete" if len(values) == attempts else "incomplete"}


def summarize(trials):
    rows = []
    for scenario in SCENARIOS:
        measured = [row for row in trials if row.get("scenario") == scenario and not row.get("warmup")]
        phases = {}
        for phase in PHASES:
            state_name = phase.removesuffix("_ns") + "_state"
            values = [row.get(phase) for row in measured if row.get(state_name) == "available"
                      and type(row.get(phase)) is int and row[phase] >= 0]
            phases[phase] = _timing(values,
                sum(row.get(state_name) == "partial" for row in measured),
                sum(row.get(state_name) == "not_reached" for row in measured))
        rows.append({"scenario": scenario, "attempts": len(measured),
                     "passed": sum(row.get("status") == "passed" and row.get("oracle_passed") is True for row in measured),
                     "failed": sum(row.get("status") != "passed" or row.get("oracle_passed") is not True for row in measured),
                     "phases": phases})
    return rows


def make_record(trials, *, source_commit, harness_commit, environment, provenance):
    rows = [copy.deepcopy(row) for row in trials]
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
        "provenance": copy.deepcopy(provenance),
        "measurement": {
            "kind": "descriptive_single_adapter",
            "scope": "Two-step discrete nominal-forward reachability on two authored scalar analytic fixtures",
            "warmups_per_fixture": 1,
            "measured_repetitions_per_fixture": 7,
            "fixture_order": "alternating forward/reverse by repetition",
            "requested_workers": 1,
            "configured_native_threads": 1,
            "operation_timing": "unavailable; the public provider seam exposes no per-operation timer",
            "timing_scopes": dict(TIMING_SCOPES),
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
    provenance = record.get("provenance")
    expected_providers = {"projection", "affine_sum", "conversion", "lp_backend", "hull_reducer"}
    if (not isinstance(provenance, dict) or
            provenance.get("algorithm_module") != {"id": "csl.reachability.nominal-forward",
                "version": "0.1.0"} or
            not isinstance(provenance.get("providers"), dict) or
            set(provenance["providers"]) != expected_providers or
            any(not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"] or
                not isinstance(value.get("version"), str) or not value["version"]
                for value in provenance["providers"].values()) or
            provenance.get("dependency_edges") != {"affine_sum": ["hull_reducer", "lp_backend", "conversion"],
                                                     "conversion": ["lp_backend"]}):
        errors.append("provider_provenance_incomplete")
    if not isinstance(provenance, dict) or provenance.get("runtime_settings") != RUNTIME_SETTINGS:
        errors.append("effective_settings_incomplete")
    thread_observation = provenance.get("native_thread_observation") if isinstance(provenance, dict) else None
    if (not isinstance(thread_observation, dict) or
            thread_observation.get("status") != "unavailable" or
            thread_observation.get("observed_threads") is not None or
            thread_observation.get("reason") !=
            "The driver has no supported runtime API to observe effective native worker threads."):
        errors.append("native_thread_observation_must_be_unavailable")
    measurement = record.get("measurement")
    if (not isinstance(measurement, dict) or measurement.get("requested_workers") != 1 or
            measurement.get("configured_native_threads") != 1):
        errors.append("thread_configuration_must_be_one")
    if not isinstance(measurement, dict) or measurement.get("timing_scopes") != TIMING_SCOPES:
        errors.append("timing_scope_metadata_mismatch")
    build = provenance.get("build_configuration") if isinstance(provenance, dict) else None
    required_build_fields = {"configuration", "generator", "generator_platform", "cxx_standard",
        "compiler_id", "compiler_version", "compiler_executable", "cmake_version",
        "cmake_release_flags", "target_release_properties", "effective_release_flags", "evidence_sha256"}
    if (not isinstance(build, dict) or not required_build_fields <= set(build) or
            build.get("configuration") != "Release" or build.get("cxx_standard") != "c++20" or
            not all(isinstance(build.get(field), str) and build[field] for field in
                    ("generator", "compiler_id", "compiler_version", "compiler_executable", "cmake_version", "cmake_release_flags")) or
            not isinstance(build.get("target_release_properties"), dict) or
            not isinstance(build.get("effective_release_flags"), list) or
            not all(isinstance(flag, str) and flag for flag in build["effective_release_flags"]) or
            not isinstance(build.get("evidence_sha256"), dict) or
            set(build["evidence_sha256"]) != {"CMakeCache.txt", "build_configuration_file", "release_build_log"} or
            not all(isinstance(digest, str) and len(digest) == 64 and
                    all(char in "0123456789abcdef" for char in digest)
                    for digest in build["evidence_sha256"].values())):
        errors.append("release_build_provenance_incomplete")
    elif build["compiler_id"] == "MSVC":
        if not {"/std:c++20", "/O2", "/DNDEBUG", "/W4", "/WX", "/permissive-"} <= set(build["effective_release_flags"]):
            errors.append("effective_msvc_release_flags_incomplete")
        if (build["target_release_properties"].get("LanguageStandard") != "stdcpp20" or
                build["target_release_properties"].get("Optimization") != "MaxSpeed"):
            errors.append("effective_msvc_release_properties_incomplete")
    elif not any(flag in ("-std=c++20", "-std=gnu++20") for flag in build["effective_release_flags"]):
        errors.append("effective_cxx20_release_flag_missing")
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
            state = row.get(phase.removesuffix("_ns") + "_state")
            if state not in PHASE_STATES or (state == "not_reached" and value is not None) or (
                    state in ("available", "partial") and (type(value) is not int or value < 0)):
                errors.append("invalid_timing_" + phase)
        setup_state, solve_state, oracle_state, execute_state = (
            row.get("setup_state"), row.get("solve_state"), row.get("oracle_state"), row.get("execute_state"))
        if setup_state not in ("available", "partial"):
            errors.append("invalid_phase_order_setup")
        if ((setup_state == "available" and solve_state == "not_reached") or
                (setup_state == "partial" and solve_state != "not_reached")):
            errors.append("invalid_phase_order_solve")
        if ((solve_state == "available" and oracle_state == "not_reached") or
                (solve_state != "available" and oracle_state != "not_reached")):
            errors.append("invalid_phase_order_oracle")
        if execute_state != "available":
            errors.append("invalid_phase_order_execute")
        passed = row.get("status") == "passed"
        if row.get("status") not in ("passed", "failed") or row.get("oracle_passed") is not passed:
            errors.append("trial_outcome_status_mismatch")
        if passed and (any(row.get(phase.removesuffix("_ns") + "_state") != "available" or
                            type(row.get(phase)) is not int or row[phase] < 0 for phase in PHASES)):
            errors.append("passed_trial_phase_incomplete")
        if all(row.get(phase.removesuffix("_ns") + "_state") == "available" and
               type(row.get(phase)) is int and row[phase] >= 0 for phase in PHASES[:3]) and \
                row.get("execute_state") == "available" and type(row.get("execute_ns")) is int and \
                row["execute_ns"] < sum(row[phase] for phase in PHASES[:3]):
            errors.append("nested_timing_exceeds_end_to_end")
        counts = row.get("provider_operation_counts")
        if not isinstance(counts, dict) or any(type(value) is not int or value < 0 for value in counts.values()):
            errors.append("invalid_provider_operation_counts")
        if row.get("provider_operation_timing_ns") is not None:
            errors.append("unsupported_provider_operation_timing_claim")
        provider_ids = row.get("provider_identities")
        if provider_ids and provider_ids != (provenance.get("providers") if isinstance(provenance, dict) else None):
            errors.append("trial_provider_identity_mismatch")
        if passed and (not provider_ids or provider_ids != (provenance.get("providers") if isinstance(provenance, dict) else None)):
            errors.append("passed_trial_provider_stack_missing")
        if row.get("execution_settings") != RUNTIME_SETTINGS:
            errors.append("trial_effective_settings_mismatch")
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
        coverage = record["summary"][index]["phases"]["execute_ns"]["coverage"]
        label = "unavailable" if value is None else f"{value:g} ns ({coverage})"
        parts.append(f'<text x="8" y="{y+15}">{html.escape(scenario)}</text>'
                     f'<rect x="170" y="{y}" width="{width}" height="22" fill="#3572a5"/>'
                     f'<text x="{180+width}" y="{y+15}">{html.escape(label)}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 130" role="img" aria-label="Execute interval from driver entry through verified result by fixture">' + "".join(parts) + "</svg>"


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
            *(f"{row.get(phase)} ({row.get(phase.removesuffix('_ns') + '_state')})" for phase in PHASES),
            row.get("detail", ""))) + "</tr>")
    summary = []
    for row in record["summary"]:
        stats = [row["phases"][phase] for phase in PHASES]
        summary.append("<tr><th>" + html.escape(row["scenario"]) + "</th>" +
                       f"<td>{row['attempts']}</td><td>{row['passed']}</td><td>{row['failed']}</td>" +
                       "".join("<td>" + (f"{s['median_ns']} (range {s['min_ns']}–{s['max_ns']}) ns; "
                           f"{s['available_trials']}/7 available, {s['partial_trials']} partial, "
                           f"{s['not_reached_trials']} not reached; {s['coverage']} coverage"
                           if s["median_ns"] is not None else
                           f"unavailable; {s['partial_trials']} partial, {s['not_reached_trials']} not reached") + "</td>" for s in stats) + "</tr>")
    limits = "".join("<li>" + html.escape(item) + "</li>" for item in record["evidence_limits"])
    report_id = html.escape(str(record.get("report_id")))
    state = html.escape(record["collection"]["state"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SYN-01 nominal forward report {report_id}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #b8c3cc;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#edf2f6}}.scroll{{overflow-x:auto}}code,td{{overflow-wrap:anywhere}}</style></head><body>
<h1>SYN-01 nominal forward reachability report</h1><p>Collection state: <strong>{state}</strong>. Report ID <code>{report_id}</code>.</p>
<p>Measured source <code>{html.escape(record['source_commit'])}</code>; report harness <code>{html.escape(record['harness_commit'])}</code>.</p>
<h2>Implementation and selected provider stack</h2><p>Algorithm module: <code>{html.escape(record['provenance']['algorithm_module']['id'])}</code> version <code>{html.escape(record['provenance']['algorithm_module']['version'])}</code>.</p>
<ul>{''.join('<li>'+html.escape(name)+': <code>'+html.escape(item['id'])+'</code> version <code>'+html.escape(item['version'])+'</code></li>' for name,item in sorted(record['provenance']['providers'].items()))}</ul>
<p>Nested dependencies: {html.escape(json.dumps(record['provenance']['dependency_edges'], sort_keys=True))}</p>
<h2>Effective runtime settings</h2><pre>{html.escape(json.dumps(record['provenance']['runtime_settings'], sort_keys=True, indent=2))}</pre>
<p>Requested workers: {record['measurement']['requested_workers']}; configured native threads: {record['measurement']['configured_native_threads']}; observed effective native threads: unavailable. {html.escape(record['provenance']['native_thread_observation']['reason'])}</p>
<p>Provider operation counts represent direct stage-provider lineage and exclude nested LP/hull operations; per-provider operation durations are unavailable.</p>
<h2>Compiler and Release build evidence</h2><pre>{html.escape(json.dumps(record['provenance']['build_configuration'], sort_keys=True, indent=2))}</pre>
<p>One registered provider stack; descriptive timings only, no speedup or comparison claim. Reachability support: <strong>Unestablished</strong>.</p>
<h2>Evidence limits</h2><ul>{limits}</ul><h2>Median execute interval (driver entry through verified result)</h2><p>The interval includes numerical-policy, execution-context, and effective-settings construction before the setup phase begins.</p>{render_svg(record)}
<div class="scroll"><table><thead><tr><th>Fixture</th><th>Measured trials</th><th>Passed</th><th>Failed</th>{phase_headers}</tr></thead><tbody>{''.join(summary)}</tbody></table></div>
<h2>Raw trial observations</h2><div class="scroll"><table><thead><tr><th>Fixture</th><th>Repetition</th><th>Kind</th><th>Status</th><th>Outcome</th><th>Oracle</th><th>Returned marginals</th>{phase_headers}<th>Detail</th></tr></thead><tbody>{''.join(trial_rows)}</tbody></table></div>
</body></html>'''

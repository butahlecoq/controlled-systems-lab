"""Validate and render the paired registered-synthesis T-S01 report."""
from __future__ import annotations

import html
import csv
import hashlib
import io
import json
import statistics
from pathlib import Path

SCHEMA = "csl.syn-ts01-paired-comparison-report/1"
EVENT_SCHEMA = "csl.synthesis.paired-ts01-event/1"
SOURCE_COMMIT = "b7f1ac0a9800326c825b6d8e35a8f23656496682"
SOURCE_FILE_SHA256 = "eeaa8ddadceb3d30b219486b81375f977b108369f999cb39a05e0fb3a2067c3c"
SCENARIO_SHA256 = "f9f067beb75288884c79133d2c81e4578f9de445f03eca7f6b697c5486681c04"
REPORT_ID = "syn-ts01-paired-20261014-b7f1ac0"
STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
PHASES = (
    "end_to_end_strategy",
    "preparation",
    "workspace_creation",
    "family_construction",
    "selector_preparation",
    "selector_workspace_creation",
    "witness_query",
    "original_verification",
)
EXPECTED_SELECTOR = {
    "count": 2,
    "distinctness_tolerance": 0,
    "seed": 31,
    "directions": [[1, -1], [-1, 1]],
}
EXPECTED_SCENARIO = {
    "schema": "csl.scenario/1",
    "id": "two-stage-integrator",
    "horizon": 2,
    "model": {"kind": "linear_discrete", "A": [[1]], "B": [[1]]},
    "initial_state": [0],
    "controls": {"kind": "box", "lower": [0], "upper": [1]},
    "objective": {"kind": "quadratic", "Q": [[2]], "linear": [-2], "offset": 1},
}
BUNDLE_FILES = frozenset({
    "README.md", "build-provenance.json", "commands.json", "environment.json", "index.html",
    "limiter-profile.json", "manifest.json", "measurement-events.jsonl", "performance.svg",
    "process-run.json", "process-stderr.bin", "process-stdout.bin", "records.json", "scenario.json",
    "trials.csv", "validation.json",
})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def trials_csv_bytes(record):
    fields = ["repetition", "warmup", "order_position", "strategy", "status", *PHASES]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for event in record["measurement"]["events"][1:]:
        row = {key: event[key] for key in fields if key in event}
        for phase in PHASES:
            row[phase] = event["timings_ns"][phase]["value"]
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def bundle_manifest_bytes(record, files):
    manifest = {
        "schema": "csl.paired-ts01-bundle-manifest/1",
        "report_id": record["report_id"],
        "files": {name: sha256_bytes(files[name]) for name in sorted(BUNDLE_FILES - {"manifest.json"})},
    }
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def validate_bundle(bundle):
    """Validate all saved inputs and derived projections in one immutable bundle."""
    bundle = Path(bundle)
    if not bundle.is_dir() or bundle.is_symlink():
        raise ValueError("paired T-S01 source bundle must be a regular directory")
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    if any(path.is_symlink() for path in bundle.rglob("*")) or actual != BUNDLE_FILES:
        raise ValueError("paired T-S01 bundle inventory differs")
    record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    errors = validate(record)
    if errors:
        raise ValueError("invalid paired T-S01 record: " + ", ".join(errors))
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.paired-ts01-bundle-manifest/1" or manifest.get("report_id") != record["report_id"]:
        raise ValueError("paired T-S01 manifest identity differs")
    if set(manifest.get("files", {})) != BUNDLE_FILES - {"manifest.json"}:
        raise ValueError("paired T-S01 manifest inventory differs")
    for name, expected in manifest["files"].items():
        if sha256_bytes((bundle / name).read_bytes()) != expected:
            raise ValueError("paired T-S01 bundle hash mismatch: " + name)
    if bundle.name != record["report_id"] or record["report_id"] != REPORT_ID:
        raise ValueError("paired T-S01 source identity differs")
    for name, expected in (
        ("environment.json", record["environment"]),
        ("build-provenance.json", record["build"]),
        ("process-run.json", record["process"]),
        ("limiter-profile.json", record["measurement"]["limiter_profile"]),
    ):
        if json.loads((bundle / name).read_text(encoding="utf-8")) != expected:
            raise ValueError("paired T-S01 sidecar differs from typed record: " + name)
    if json.loads((bundle / "scenario.json").read_text(encoding="utf-8")) != record["scenario"]["value"]:
        raise ValueError("paired T-S01 scenario sidecar differs")
    if (bundle / "performance.svg").read_text(encoding="utf-8") != render_svg(record):
        raise ValueError("paired T-S01 SVG differs from typed record")
    if (bundle / "index.html").read_text(encoding="utf-8") != render_html(record):
        raise ValueError("paired T-S01 HTML differs from typed record")

    raw_events = (bundle / "measurement-events.jsonl").read_bytes()
    try:
        events = [json.loads(line) for line in raw_events.decode("utf-8", errors="strict").splitlines() if line]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("paired T-S01 raw event stream is malformed") from error
    if events != record["measurement"]["events"] or sha256_bytes(raw_events) != record["measurement"]["events_sha256"]:
        raise ValueError("paired T-S01 raw events differ from typed record")
    stdout = (bundle / "process-stdout.bin").read_bytes()
    stderr = (bundle / "process-stderr.bin").read_bytes()
    if (stdout.replace(b"\r\n", b"\n") != raw_events
            or sha256_bytes(stdout) != record["measurement"]["stdout_sha256"]
            or sha256_bytes(stderr) != record["measurement"]["stderr_sha256"]):
        raise ValueError("paired T-S01 retained process streams differ from report hashes")
    if (bundle / "trials.csv").read_bytes() != trials_csv_bytes(record):
        raise ValueError("paired T-S01 trial CSV differs from typed/raw events")
    return record


def timing_summary(events):
    output = {}
    for strategy in STRATEGIES:
        group = [e for e in events if e.get("event") == "trial" and not e.get("warmup") and e.get("strategy") == strategy]
        by_phase = {}
        for phase in PHASES:
            values = [e["timings_ns"][phase]["value"] for e in group if e["timings_ns"][phase].get("available") is True]
            by_phase[phase] = {
                "observations_ns": values,
                "median_ns": statistics.median(values) if values else None,
                "min_ns": min(values) if values else None,
                "max_ns": max(values) if values else None,
                "range_ns": max(values) - min(values) if values else None,
            }
        output[strategy] = {"measured_count": len(group), **by_phase}
    return output


def validate(record):
    errors = []
    if record.get("schema") != SCHEMA: errors.append("schema")
    if record.get("report_id") != REPORT_ID: errors.append("report_id")
    source = record.get("source", {})
    if source.get("harness_commit") != SOURCE_COMMIT or source.get("measurement_source_file_sha256") != SOURCE_FILE_SHA256:
        errors.append("source_identity")
    scenario = record.get("scenario", {})
    if scenario.get("sha256") != SCENARIO_SHA256 or scenario.get("value") != EXPECTED_SCENARIO or sha256_bytes(canonical(scenario.get("value"))) != scenario.get("canonical_sha256"):
        errors.append("scenario_hash")
    request = record.get("request", {})
    if request.get("profile") != "ts01_exact_integrator" or request.get("target") != "exact_optimal_relation" or request.get("representation") != "csl.polyhedron.h" or request.get("assurance") != "numerical" or request.get("absolute_tolerance") != 1e-8 or request.get("relative_tolerance") != 1e-8 or request.get("materialization_limit") is not None:
        errors.append("family_request")
    if request.get("selector") != EXPECTED_SELECTOR or request.get("selector_source") != {"commit": SOURCE_COMMIT, "file_sha256": SOURCE_FILE_SHA256}:
        errors.append("selector_request")

    measurement = record.get("measurement", {})
    events = measurement.get("events", [])
    header = events[0] if events else {}
    trials = events[1:] if events else []
    if not isinstance(events, list) or len(events) != 17 or header.get("schema") != EVENT_SCHEMA or header.get("event") != "header":
        errors.append("event_header_or_count")
    if header.get("problem") != request.get("problem_identity") or header.get("scenario_sha256") != SCENARIO_SHA256:
        errors.append("event_scenario_identity")
    if header.get("resource_policy") != {"total_threads": 1, "outer_workers": 1, "threads_per_worker": 1, "memory_bytes": None}:
        errors.append("resource_policy")
    if header.get("order_policy") != "One excluded A-then-B warmup pair; seven measured pairs alternate A/B then B/A. Both members of every pair share this immutable resolved problem and provider registries.":
        errors.append("order_policy")
    if len(trials) != 16 or any(t.get("schema") != EVENT_SCHEMA or t.get("event") != "trial" for t in trials):
        errors.append("trial_inventory")
    expected_order = []
    for repetition in range(8):
        ordered = STRATEGIES if repetition in (0, 1, 3, 5, 7) else tuple(reversed(STRATEGIES))
        expected_order.extend((repetition, repetition == 0, position, strategy) for position, strategy in enumerate(ordered))
    observed_order = [(t.get("repetition"), t.get("warmup"), t.get("order_position"), t.get("strategy")) for t in trials]
    if observed_order != expected_order:
        errors.append("alternation")
    if any(t.get("status") != "passed" or t.get("termination") != "completed" or t.get("outcome") != "optimal" or t.get("complete_family_verified") is not True or t.get("assurance") != "numerical" or t.get("distinct_witnesses") != 2 or t.get("error") for t in trials):
        errors.append("trial_result")
    for trial in trials:
        identity = trial.get("family_identity") or {}
        family_request = identity.get("request") or {}
        if identity.get("problem") != request.get("problem_identity") or identity.get("strategy") != trial.get("strategy"):
            errors.append("family_identity")
            break
        if family_request.get("profile") != request.get("profile") or family_request.get("target") != request.get("target") or family_request.get("assurance") != request.get("assurance") or family_request.get("representation") != request.get("representation") or family_request.get("absolute_tolerance") != request.get("absolute_tolerance") or family_request.get("relative_tolerance") != request.get("relative_tolerance"):
            errors.append("family_identity_request")
            break
        if not trial.get("strategy_provenance") or not trial.get("selector_provenance") or not trial.get("membership_provenance"):
            errors.append("module_provenance")
            break
        if len(trial.get("witnesses", [])) != 2 or any(w.get("verification", {}).get("bindings") != "numerical_pass" or w.get("verification", {}).get("feasibility") != "numerical_pass" or w.get("verification", {}).get("objective") != "numerical_pass" or w.get("verification", {}).get("optimality") != "unsupported" or w.get("verification", {}).get("completeness") != "unsupported" for w in trial.get("witnesses", [])):
            errors.append("witness_verification")
            break
        if any(w.get("recomputed_objective") != 0 or w.get("maximum_absolute_residual") != 0 for w in trial.get("witnesses", [])) or trial.get("verification_summary", {}).get("maximum_absolute_residual") != 0:
            errors.append("witness_values")
            break
        if trial.get("verification_summary", {}).get("optimality") != "unsupported" or trial.get("verification_summary", {}).get("completeness") != "unsupported":
            errors.append("witness_evidence_scope")
            break
        timings = trial.get("timings_ns", {})
        if any(timings.get(phase, {}).get("available") is not True or type(timings.get(phase, {}).get("value")) is not int or timings[phase]["value"] < 0 for phase in PHASES):
            errors.append("timing_missing")
            break

    if not isinstance(measurement.get("events_sha256"), str) or len(measurement["events_sha256"]) != 64:
        errors.append("raw_events_hash")
    if measurement.get("stdout_normalized_to_events") is not True or measurement.get("algorithm_return_code") != 0 or measurement.get("launcher_exit_code") != 1:
        errors.append("process_status")
    if measurement.get("failed_trials") != 0 or measurement.get("passed_trials") != 16 or measurement.get("warmup_pairs") != 1 or measurement.get("measured_pairs") != 7:
        errors.append("trial_counts")
    if measurement.get("performance_conclusion") != "inconclusive" or measurement.get("limiter_profile") != {"performed": False, "limiter_identified": False, "reason": "No separate limiter profile was performed; the latency limiter remains unknown and this exact-fixture comparison is inconclusive."}:
        errors.append("limiter_or_conclusion")
    if measurement.get("summary") != timing_summary(trials):
        errors.append("summary_statistics")
    return errors


def render_svg(record):
    values = [e["timings_ns"]["end_to_end_strategy"]["value"] / 1_000_000 for e in record["measurement"]["events"][1:] if not e["warmup"]]
    low, high = 0.0, max(values) * 1.12 if values else 1.0
    y = lambda value: 190 - value / high * 145
    marks = []
    colors = {STRATEGIES[0]: "#2166ac", STRATEGIES[1]: "#b35806"}
    offsets = {STRATEGIES[0]: -4, STRATEGIES[1]: 4}
    for strategy in STRATEGIES:
        for trial in (e for e in record["measurement"]["events"][1:] if not e["warmup"] and e["strategy"] == strategy):
            x = 62 + (trial["repetition"] - 1) * 48 + offsets[strategy]
            value = trial["timings_ns"]["end_to_end_strategy"]["value"] / 1_000_000
            marks.append(f'<circle cx="{x}" cy="{y(value):.2f}" r="4.5" fill="{colors[strategy]}" aria-label="{html.escape(strategy)} repetition {trial["repetition"]}: {value:.3f} ms"/>')
    ticks = []
    for value in (0, 1, 2, 3, 4, 5, 6):
        if value <= high:
            py = y(value)
            ticks.append(f'<line x1="38" y1="{py:.2f}" x2="390" y2="{py:.2f}" stroke="#d7dee4"/><text x="32" y="{py + 4:.2f}" text-anchor="end" font-size="10">{value} ms</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Seven alternating paired T-S01 strategy timing observations" viewBox="0 0 430 235" width="100%" height="235">'
        '<text x="215" y="17" text-anchor="middle" font-size="13" font-weight="bold">Exact T-S01 per-strategy interval (ms)</text>'
        + ''.join(ticks) + '<line x1="38" y1="190" x2="390" y2="190" stroke="#18232d"/>'
        + ''.join(marks) + ''.join(f'<text x="{62+(rep-1)*48}" y="210" text-anchor="middle" font-size="10">{rep}</text>' for rep in range(1,8))
        + '<text x="214" y="229" text-anchor="middle" font-size="10">Measured pair (alternating AB / BA)</text>'
        + '<circle cx="108" cy="35" r="4.5" fill="#2166ac"/><text x="118" y="39" font-size="11">reach-back</text>'
        + '<circle cx="232" cy="35" r="4.5" fill="#b35806"/><text x="242" y="39" font-size="11">Strategy B</text></svg>')


def render_html(record):
    errors = validate(record)
    if errors:
        raise ValueError("invalid paired T-S01 report: " + ", ".join(errors))
    esc = lambda value: html.escape(str(value))
    resource_policy = html.escape(json.dumps(record["request"]["resource_policy"], sort_keys=True, separators=(",", ":")))
    events = record["measurement"]["events"]
    summary = record["measurement"]["summary"]
    timing_rows = []
    for strategy in STRATEGIES:
        stats = summary[strategy]["end_to_end_strategy"]
        timing_rows.append(f'<tr><th scope="row">{esc(strategy)}</th><td>{stats["median_ns"]:,}</td><td>{stats["min_ns"]:,}–{stats["max_ns"]:,}</td><td>{stats["range_ns"]:,}</td></tr>')
    trial_rows = []
    for trial in events[1:]:
        times = trial["timings_ns"]
        trial_rows.append('<tr>'
            + f'<td>{trial["repetition"]}</td><td>{"warmup" if trial["warmup"] else "measured"}</td><td>{esc(trial["strategy"])}</td>'
            + f'<td>{times["end_to_end_strategy"]["value"]:,}</td><td>{times["family_construction"]["value"]:,}</td><td>{times["witness_query"]["value"]:,}</td>'
            + f'<td>{times["original_verification"]["value"]:,}</td><td>{esc(trial["status"])}</td></tr>')
    source = record["source"]
    measurement = record["measurement"]
    return ''.join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Paired registered synthesis T-S01 report</title>',
        '<style>body{font:16px system-ui,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1rem;color:#17232c}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #b9c4cc;padding:.45rem .6rem;text-align:left}th{background:#f1f5f7}code{overflow-wrap:anywhere}.note{background:#fff3d3;padding:1rem}.scroll{overflow-x:auto}svg{max-width:100%}</style></head><body>',
        '<h1>Paired registered Strategy A / Strategy B comparison on T-S01</h1>',
        '<p>This versioned report records seven alternating measurements per registered strategy on the same exact two-stage integrator problem and optimal-family request. It is a single tiny exact-profile experiment.</p>',
        '<p class="note"><strong>Conclusion: inconclusive; no winner is claimed.</strong> No separate limiter profile was performed, so the latency limiter is unknown. The observed timing differences do not establish a general strategy ranking, speedup, application-scale result, or scalability result.</p>',
        '<h2>Problem and request</h2><p>Problem identity <code>'+esc(record['request']['problem_identity'])+'</code>; scenario SHA-256 <code>'+esc(record['scenario']['sha256'])+'</code>. The effective family request is <code>ts01_exact_integrator</code>, target <code>exact_optimal_relation</code>, H representation, numerical assurance, absolute/relative tolerance 1e−8, with no materialization limit.</p>',
        '<p>Both strategies received the same immutable resolved problem and provider registries. Each fresh plan/workspace ran through the public StrategyPort path; the report verifies the exact-profile complete-family result, selects two distinct witnesses, and checks both against the original problem. Original-witness checks establish bindings, feasibility, and objective only; they do not establish optimality or family completeness independently.</p>',
        '<p>Selector request copied from pinned measured source <code>'+esc(source['harness_commit'])+'</code> / <code>examples/registered_synthesis_comparison.cpp</code> SHA-256 <code>'+esc(source['measurement_source_file_sha256'])+'</code>: count 2, distinctness tolerance 0, seed 31, directions <code>[[1,-1],[-1,1]]</code>. Objective/problem identity is retained in each family identity.</p>',
        '<h2>Measured end-to-end intervals</h2><p>One excluded A/B warmup; seven measured pairs alternate A/B, B/A, A/B, B/A, A/B, B/A, A/B. Per-strategy interval: fresh StrategyRegistry::prepare through exclusive workspace creation, public StrategyPort family construction and exact-profile verifier, selector preparation/query, and original-problem verification of both selected histories. Shared scenario/provider setup is reported separately. Process start, JSON/file serialization, build, plots and report rendering are excluded. Times are nanoseconds; CTest duration is not used.</p>',
        render_svg(record),
        '<div class="scroll"><table><thead><tr><th>Strategy</th><th>Median (ns)</th><th>Min–max (ns)</th><th>Range width (ns)</th></tr></thead><tbody>'+''.join(timing_rows)+'</tbody></table></div>',
        '<p>The rows report descriptive sample summaries only. Seven repetitions on this fixture do not identify a performance winner. Internal LP/convex, projection, affine-sum, conversion, hull-membership, verifier subphase, CPU-time, and per-call memory counters are unavailable.</p>',
        '<h2>Raw trials</h2><div class="scroll"><table><thead><tr><th>Repetition</th><th>Kind</th><th>Strategy</th><th>Total (ns)</th><th>Family construction (ns)</th><th>Witness query (ns)</th><th>Original checks (ns)</th><th>Status</th></tr></thead><tbody>'+''.join(trial_rows)+'</tbody></table></div>',
        '<p>All 16 strategy trials passed (2 excluded warmup trials and 14 measured trials); failures: '+esc(measurement['failed_trials'])+'. Every result was registry-verified for this exact profile and returned two distinct selected histories. Each selected history passed numerical original-problem binding, feasibility, and objective checks with maximum reported residual 0 under 1e−8 tolerances. The numerical evidence label does not mean validated arithmetic.</p>',
        '<h2>Build and environment</h2><p>Measured source commit <code>'+esc(source['harness_commit'])+'</code>; Release executable SHA-256 <code>'+esc(record['build']['executable_sha256'])+'</code>; compiler <code>'+esc(record['build']['compiler'])+'</code>; requested resources: <code>'+resource_policy+'</code>. Host: '+esc(record['environment']['processor'])+', '+esc(record['environment']['physical_cores'])+' physical / '+esc(record['environment']['logical_processors'])+' logical cores, Windows build '+esc(record['environment']['os_version'])+'. Pre-run system CPU samples: '+esc(record['environment']['cpu_samples_summary'])+'.</p>',
        '<p>The algorithm process returned 0 and emitted all 17 records. The collection wrapper returned 1 because it compared Windows CRLF stdout bytes to the LF binary JSONL sidecar. Raw stdout and JSONL were preserved; they match byte-for-byte after CRLF-to-LF normalization. This collection defect is documented and did not alter algorithm return status or event data.</p>',
        '<h2>Reproducibility and downloads</h2><ul><li><a href="measurement-events.jsonl">Raw machine-readable events</a></li><li><a href="records.json">Typed report record</a></li><li><a href="trials.csv">Trial table (CSV)</a></li><li><a href="scenario.json">Scenario input</a></li><li><a href="build-provenance.json">Build provenance</a></li><li><a href="environment.json">Environment capture</a></li><li><a href="process-stdout.bin">Exact stdout bytes</a></li><li><a href="process-stderr.bin">Exact stderr bytes</a></li><li><a href="process-run.json">Process and collector status</a></li><li><a href="validation.json">Raw validation notes and checksums</a></li></ul>',
        '<p>Source strategy implementations are not modified by this report. The result covers only this exact discrete T-S01 fixture and the declared request, with numerical assurance. It does not serialize the live complete-family proof payload and does not close SYN-03/SYN-04 or OBS-04/#83.</p>',
        '</body></html>',
    ])

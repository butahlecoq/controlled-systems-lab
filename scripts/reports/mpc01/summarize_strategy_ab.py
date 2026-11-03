#!/usr/bin/env python3
"""Validate and summarize the paired registered T-S01 Strategy A/B run."""

import argparse
import hashlib
import json
import html
import statistics
import os
import shlex
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


def write_report(output: Path, measured: dict[str, list[dict]], environment: dict,
                 scenario: Path, events: Path, stdout: Path,
                 resource_profile: dict | None = None) -> None:
    svg_path = output.with_name("strategy-ab-ts01-control-plane.svg")
    report_path = output.with_suffix(".html")
    points = {strategy: [] for strategy in EXPECTED}
    for strategy in EXPECTED:
        for row in measured[strategy]:
            for witness in row["witnesses"]:
                controls = tuple(float(state[0]) for state in witness["controls"])
                if controls not in points[strategy]:
                    points[strategy].append(controls)

    colors = {EXPECTED[0]: "#1769aa", EXPECTED[1]: "#c23b22"}
    labels = {EXPECTED[0]: "Strategy A: reach-back", EXPECTED[1]: "Strategy B: paired capture"}
    margin, size = 75, 440
    px = lambda x: margin + x * size
    py = lambda y: margin + (1 - y) * size
    marks = []
    for tick in range(6):
        value = tick / 5
        x, y = px(value), py(value)
        marks.extend((
            f'<line x1="{x:.1f}" y1="{margin}" x2="{x:.1f}" y2="{margin+size}" class="grid"/>',
            f'<line x1="{margin}" y1="{y:.1f}" x2="{margin+size}" y2="{y:.1f}" class="grid"/>',
            f'<text x="{x:.1f}" y="{margin+size+24}" text-anchor="middle">{value:.1f}</text>',
            f'<text x="{margin-13}" y="{y+4:.1f}" text-anchor="end">{value:.1f}</text>',
        ))
    marks.append(f'<line x1="{px(0):.1f}" y1="{py(1):.1f}" x2="{px(1):.1f}" y2="{py(0):.1f}" class="optimal"/>')
    shapes = []
    for strategy in EXPECTED:
        for index, (u0, u1) in enumerate(points[strategy]):
            title = html.escape(f"{labels[strategy]} selected control history {index + 1}: u0={u0:g}, u1={u1:g}")
            if strategy == EXPECTED[0]:
                shapes.append(f'<circle cx="{px(u0):.1f}" cy="{py(u1):.1f}" r="6" fill="{colors[strategy]}" stroke="white" stroke-width="2"><title>{title}</title></circle>')
            else:
                shapes.append(f'<circle cx="{px(u0):.1f}" cy="{py(u1):.1f}" r="11" fill="none" stroke="{colors[strategy]}" stroke-width="3"><title>{title}</title></circle>')
    legend = "".join(
        f'<p><span style="color:{colors[s]}">{("●" if s == EXPECTED[0] else "◯")}</span> '
        f'{labels[s]}: {len(points[s])} distinct saved selected histories</p>'
        for s in EXPECTED
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 610" role="img" aria-labelledby="title desc">
<title id="title">T-S01 selected optimal control histories</title>
<desc id="desc">The exact minimizer segment u0 plus u1 equals one inside the unit square, with saved selected control histories from Strategy A and Strategy B.</desc>
<style>text{{font:14px sans-serif;fill:#263238}}.grid{{stroke:#d9e0e5;stroke-width:1}}.optimal{{stroke:#263238;stroke-width:3;stroke-dasharray:8 5}}.axis{{stroke:#263238;stroke-width:2}}</style>
<rect width="660" height="610" fill="white"/>
<text x="330" y="32" text-anchor="middle" font-size="19" font-weight="bold">T-S01 two-stage integrator: control plane</text>
{''.join(marks)}
<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{margin+size}" class="axis"/><line x1="{margin}" y1="{margin+size}" x2="{margin+size}" y2="{margin+size}" class="axis"/>
{''.join(shapes)}
<text x="{margin+size/2}" y="{margin+size+52}" text-anchor="middle">First-stage control u₀</text>
<text transform="translate(20 {margin+size/2}) rotate(-90)" text-anchor="middle">Second-stage control u₁</text>
<text x="{margin+size-5}" y="{margin+32}" text-anchor="end">Exact optimal family: u₀ + u₁ = 1</text>
</svg>'''
    svg_path.write_text(svg, encoding="utf-8")

    timing_rows = []
    for strategy in EXPECTED:
        values = [row["timings_ns"]["end_to_end_strategy"]["value"] for row in measured[strategy]]
        timing_rows.append(
            f'<tr><th>{html.escape(labels[strategy])}</th><td>{statistics.median(values)/1e6:.6f}</td>'
            f'<td>{min(values)/1e6:.6f}–{max(values)/1e6:.6f}</td></tr>')
    source_commit = html.escape(environment["source_commit"])
    scenario_hash = digest(scenario)
    event_hash = digest(events)
    stdout_hash = digest(stdout)
    scenario_href = html.escape(os.path.relpath(scenario, output.parent))
    if resource_profile is None:
        resource_note = "No separate limiter or per-attempt resource-cap profile was collected; these values do not support a general performance-winner claim."
        resource_link = ""
    else:
        limits = resource_profile["enforced_limits"]
        observed = resource_profile["observed"]
        wall_scope = resource_profile.get("timeout_scope", "the full capture invocation")
        limiter_note = (f" {len(resource_profile.get('separate_limiter_profiles', []))} separate limiter probes are retained in the profile."
                        if resource_profile.get("separate_limiter_profiles") else "")
        resource_note = (
            f"The supervised process tree completed under a {limits['memory_max_bytes']} byte cgroup-v2 memory cap "
            f"with swap disabled and a {resource_profile['requested_limits']['process_tree_wall_time_seconds']} second wall cap. "
            f"Wall-cap scope: {wall_scope}. "
            f"Observed peak process-tree memory was {observed['process_tree_peak_memory_bytes']} bytes; no OOM or timeout occurred. "
            f"This resource profile supports no general performance-winner claim.{limiter_note}"
        )
        resource_link = '<li>Enforced capture resource profile: <a href="resource-profile.json">JSON</a></li>'
    report = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MPC-01 T-S01 Strategy A/B result</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;color:#202a33;max-width:960px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbc5cc;padding:.45rem .7rem;text-align:left}}figure{{margin:1.5rem 0}}figure img{{width:min(100%,660px)}}.note{{border-left:4px solid #516b7b;padding:.4rem 1rem;background:#f4f7f8}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>MPC-01 registered Strategy A/B on T-S01</h1>
<p>This report renders the saved paired run for the two-stage integrator: <code>x₀=0</code>, <code>xₜ₊₁=xₜ+uₜ</code>, <code>uₜ∈[0,1]</code>, and terminal objective <code>(x₂−1)²</code>. It compares strategy outputs and descriptive functional timings for this single fixture.</p>
<figure><img src="{html.escape(svg_path.name)}" alt="Control histories on the exact optimal family in the u0-u1 plane"><figcaption>The dashed segment is the exact minimizing relation. Markers are selected control histories saved for each strategy; a ring around a filled marker shows both strategies selected that same history.</figcaption>{legend}</figure>
<h2>Saved run</h2><p>{environment['measurement']['warmup_pairs_excluded']} warmup pair(s) were excluded; {environment['measurement']['measured_alternating_pairs']} measured pairs alternated execution order. All {environment['measurement']['event_count_including_header'] - 1} trials completed successfully. Each strategy selected two distinct histories with zero original and recomputed objective; original-data feasibility and objective checks passed numerically. These witness checks do not establish separate optimality or completeness proofs.</p>
<h2>Descriptive timing</h2><table><thead><tr><th>Strategy</th><th>Median end-to-end (ms)</th><th>Range (ms)</th></tr></thead><tbody>{''.join(timing_rows)}</tbody></table>
<p>The interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. {resource_note}</p>
<h2>Reproducibility</h2><ul><li>Source commit: <code>{source_commit}</code></li><li>Scenario SHA-256: <code>{scenario_hash}</code></li><li>Event and stdout SHA-256: <code>{event_hash}</code> / <code>{stdout_hash}</code></li><li>Environment: <a href="strategy-ab-ts01-environment.json">saved environment metadata</a></li><li>Canonical paired record: <a href="comparison-record.json">JSON</a></li><li>Raw records: <a href="strategy-ab-ts01-events.jsonl">event JSONL</a> · <a href="strategy-ab-ts01-stdout.jsonl">stdout JSONL</a></li>{resource_link}<li>Scenario input: <a href="{scenario_href}">scenario JSON</a></li></ul>
<p class="note">This is one registered-strategy functional comparison, not a general performance ranking or the full #597 matrix. The separate OSQP/HPIPM solve-phase measurements use different timing boundaries.</p>
</body></html>'''
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--resource-profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    event_bytes, stdout_bytes = args.events.read_bytes(), args.stdout.read_bytes()
    if event_bytes != stdout_bytes:
        raise ValueError("saved event sidecar does not match stdout bytes")
    rows = [json.loads(line) for line in event_bytes.decode("utf-8").splitlines() if line]
    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    warmup_pairs = int(environment["measurement"]["warmup_pairs_excluded"])
    measured_pairs = int(environment["measurement"]["measured_alternating_pairs"])
    if measured_pairs < 5:
        raise ValueError("comparison-program timing requires at least five measured pairs")
    if len(rows) != 1 + 2 * (warmup_pairs + measured_pairs) or rows[0].get("event") != "header":
        raise ValueError("event count differs from the declared warmup and measured pairs")
    header, trials = rows[0], rows[1:]
    if header.get("schema") not in {
        "csl.synthesis.paired-ts01-event/1", "csl.synthesis.paired-family-event/1"
    }:
        raise ValueError("unsupported Strategy A/B event schema")
    if header.get("scenario_sha256") != digest(args.scenario):
        raise ValueError("event header does not bind the supplied T-S01 scenario")
    if header.get("profile") != "ts01_exact_integrator" or header.get("assurance") != "numerical":
        raise ValueError("event request is not the registered T-S01 numerical profile")
    if (len([row for row in trials if row["warmup"]]) != 2 * warmup_pairs or
            len([row for row in trials if not row["warmup"]]) != 2 * measured_pairs):
        raise ValueError("trial warmup/measured counts disagree with the capture environment")

    measured: dict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(trials):
        expected_rep = index // 2
        expected_position = index % 2
        if row.get("event") != "trial" or row.get("repetition") != expected_rep or row.get("order_position") != expected_position:
            raise ValueError("trial repetition or order is inconsistent")
        if bool(row.get("warmup")) != (expected_rep < warmup_pairs):
            raise ValueError("warmup flag differs from the capture environment")
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

    if set(measured) != set(EXPECTED) or any(len(rows) != measured_pairs for rows in measured.values()):
        raise ValueError("measured A/B result counts differ")
    lines = [
        "# Saved per-attempt Strategy A/B T-S01 run",
        "",
        "This functional measurement uses the same exact two-stage integrator equations as `ts01-exact-v1`: `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and terminal objective `(x2-1)^2`. It is a separate registered-strategy path from the OSQP/HPIPM QP solve-phase measurements; phase timings are not directly comparable.",
        "",
        f"- Source commit: `{json.loads(args.environment.read_text())['source_commit']}`.",
        f"- Scenario SHA-256: `{digest(args.scenario)}`.",
        f"- Event/stdout SHA-256: `{digest(args.events)}`.",
        f"- {warmup_pairs} excluded warmup pair(s) and {measured_pairs} measured alternating A/B pairs; all {len(trials)} trials passed.",
        "- Every measured result carries the registered T-S01 complete-family profile, two distinct selected witnesses, zero original/recomputed objective, and numerical-pass original-data checks. Witness checks do not claim separate optimality or completeness proofs; the profile-specific family status is retained separately.",
        "",
        "| Strategy | Median end-to-end (ms) | Range (ms) |",
        "|---|---:|---:|",
    ]
    for strategy in EXPECTED:
        values = [row["timings_ns"]["end_to_end_strategy"]["value"] for row in measured[strategy]]
        lines.append(f"| `{strategy}` | {statistics.median(values) / 1e6:.6f} | {min(values) / 1e6:.6f}–{max(values) / 1e6:.6f} |")
    resource_profile = None
    if args.resource_profile:
        resource_profile = json.loads(args.resource_profile.read_text(encoding="utf-8"))
        if resource_profile.get("schema") != "csl.mpc01-resource-profile/1" or resource_profile.get("status") != "completed":
            raise ValueError("resource profile is not a completed MPC-01 capture")
        enforced = resource_profile["enforced_limits"]
        observed = resource_profile["observed"]
        if (enforced.get("process_tree_wall_time") is not True or
                enforced.get("process_tree_memory") is not True or
                observed.get("timed_out") is not False or observed.get("exit_code") != 0 or
                enforced.get("memory_swap_max_bytes") != 0 or
                any(line.rsplit(" ", 1)[-1] != "0" for line in observed["memory_events"]
                    if line.rsplit(": ", 1)[-1].startswith(("max ", "oom ", "oom_kill ", "oom_group_kill ")))):
            raise ValueError("resource-limited capture did not complete cleanly under its declared caps")
        if json.loads(args.environment.read_text(encoding="utf-8"))["measurement"]["resource_profile_sha256"] != digest(args.resource_profile):
            raise ValueError("environment does not bind the supplied resource profile")
        lines[0] = "# Resource-limited saved Strategy A/B T-S01 capture"
    lines.extend([
        "",
        ("The timing interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. " +
         ("No separate limiter or per-attempt resource-cap profile was collected, so these tiny-case timings support no general performance winner claim."
          if resource_profile is None else
          f"The supervised process tree ran under a {resource_profile['enforced_limits']['memory_max_bytes']} byte cgroup-v2 memory cap with swap disabled and a {resource_profile['requested_limits']['process_tree_wall_time_seconds']} second watchdog. Wall-cap scope: {resource_profile.get('timeout_scope', 'the full capture invocation')}. Observed peak process-tree memory was {resource_profile['observed']['process_tree_peak_memory_bytes']} bytes; no OOM or timeout occurred. {len(resource_profile.get('separate_limiter_profiles', []))} separate limiter probes are retained. Timings support no general performance-winner claim.")),
        "",
        "Saved-data report: [`strategy-ab-ts01-summary.html`](strategy-ab-ts01-summary.html) with the control-plane figure [`strategy-ab-ts01-control-plane.svg`](strategy-ab-ts01-control-plane.svg).",
        "",
        "Regenerate the HTML, SVG, and Markdown summary from the retained records:",
        "",
        "```sh",
        "python3 scripts/reports/mpc01/summarize_strategy_ab.py \\",
        f"  --events {shlex.quote(str(args.events))} \\",
        f"  --stdout {shlex.quote(str(args.stdout))} \\",
        f"  --scenario {shlex.quote(str(args.scenario))} \\",
        f"  --environment {shlex.quote(str(args.environment))} \\",
        *([f"  --resource-profile {shlex.quote(str(args.resource_profile))} \\"] if args.resource_profile else []),
        f"  --output {shlex.quote(str(args.output))}",
        "```",
        "",
    ])
    args.output.write_text("\n".join(lines), encoding="utf-8")
    write_report(args.output, measured, json.loads(args.environment.read_text()),
                 args.scenario, args.events, args.stdout, resource_profile)


if __name__ == "__main__":
    main()

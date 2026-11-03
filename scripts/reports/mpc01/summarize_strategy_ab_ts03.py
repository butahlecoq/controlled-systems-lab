#!/usr/bin/env python3
"""Validate and render the saved Strategy A/B T-S03 capture."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import statistics
from pathlib import Path

from build_strategy_ab_records import build_record, canonical, validate_record


STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
LABELS = {
    STRATEGIES[0]: "Strategy A: reach-back",
    STRATEGIES[1]: "Strategy B: direct joint optimization",
}
COLORS = {STRATEGIES[0]: "#1769aa", STRATEGIES[1]: "#c23b22"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    read = lambda name: (bundle / name).read_bytes()
    events_path = bundle / "strategy-ab-ts03-events.jsonl"
    stdout_path = bundle / "strategy-ab-ts03-stdout.jsonl"
    supervisor_path = bundle / "capture-supervisor.py"
    scenario_path = bundle / "scenario.json"
    environment_path = bundle / "capture-environment.json"
    codec_environment_path = bundle / "codec-environment.json"
    resource_profile_path = bundle / "resource-profile.json"
    record_path = bundle / "comparison-record.json"
    events_bytes = events_path.read_bytes()
    if events_bytes != stdout_path.read_bytes():
        raise ValueError("event JSONL and stdout bytes differ")
    events = [json.loads(line) for line in events_bytes.decode().splitlines() if line]
    header, trials = events[0], events[1:]
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    environment_text = environment_path.read_text(encoding="utf-8")
    environment = json.loads(environment_text)
    profile_bytes = resource_profile_path.read_bytes()
    profile = json.loads(profile_bytes)
    record_text = record_path.read_text(encoding="utf-8")
    record = json.loads(record_text)
    validate_record(record)
    scenario_hash = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    events_hash = hashlib.sha256(events_bytes).hexdigest()
    profile_hash = hashlib.sha256(profile_bytes).hexdigest()
    supervisor_hash = hashlib.sha256(supervisor_path.read_bytes()).hexdigest()
    if (environment.get("scenario_sha256") != scenario_hash or
            environment.get("events_sha256") != events_hash or
            environment.get("measurement", {}).get("events_sha256") != events_hash or
            environment.get("measurement", {}).get("resource_profile_sha256") != profile_hash or
            environment.get("measurement", {}).get("capture_supervisor_sha256") != supervisor_hash or
            record_text != canonical(record) or
            canonical(build_record(events_path, scenario_path, environment_path,
                                   codec_environment_path)) != record_text):
        raise ValueError("capture metadata or canonical record does not bind the exact saved input bytes")
    if (len(events) != 13 or len(trials) != 12 or
            header.get("schema") != "csl.synthesis.paired-family-event/1" or
            header.get("profile") != "ts03_singular_integrator" or
            header.get("scenario_sha256") != scenario_hash or
            scenario.get("id") != "mpc01-ts03-singular-integrator-v1" or
            scenario.get("horizon") != 2 or scenario.get("initial_state") != [0] or
            scenario.get("controls") != {"kind": "box", "lower": [0], "upper": [1]} or
            scenario.get("model") != {"kind": "linear_discrete", "A": [[0]], "B": [[1]]} or
            scenario.get("objective") != {"kind": "quadratic", "Q": [[2]], "linear": [-2], "offset": 1}):
        raise ValueError("capture is not bound to the pinned T-S03 singular integrator")
    if (profile.get("status") != "completed" or profile.get("observed", {}).get("exit_code") != 0 or
            profile.get("observed", {}).get("timed_out") or
            profile.get("enforced_limits", {}).get("memory_max_bytes") != 2 * 1024**3 or
            profile.get("enforced_limits", {}).get("memory_swap_max_bytes") != 0 or
            profile.get("requested_limits", {}).get("process_tree_wall_time_seconds") != 300):
        raise ValueError("capture did not complete under its declared resource profile")
    if any(line.rsplit(" ", 1)[-1] != "0" for line in profile["observed"].get("memory_events", [])
           if line.startswith(("max ", "oom ", "oom_kill ", "oom_group_kill "))):
        raise ValueError("capture reached a cgroup memory/oom event")

    measured: dict[str, list[dict]] = {strategy: [] for strategy in STRATEGIES}
    points: dict[str, list[tuple[float, float]]] = {strategy: [] for strategy in STRATEGIES}
    for index, row in enumerate(trials):
        repetition, position = divmod(index, 2)
        expected = (STRATEGIES[position] if repetition == 0 or repetition % 2 == 1
                    else STRATEGIES[1 - position])
        if (row.get("event") != "trial" or row.get("repetition") != repetition or
                row.get("order_position") != position or row.get("strategy") != expected or
                row.get("status") != "passed" or row.get("termination") != "completed" or
                row.get("outcome") != "optimal" or not row.get("complete_family_verified") or
                row.get("distinct_witnesses") != 2):
            raise ValueError(f"invalid or incomplete T-S03 attempt at event {index + 1}")
        for witness in row["witnesses"]:
            controls = [control[0] for control in witness["controls"]]
            states = [state[0] for state in witness["states"]]
            if (len(controls) != 2 or not 0 <= controls[0] <= 1 or controls[1] != 1 or
                    states != [0, controls[0], 1] or witness["original_objective"] != 0 or
                    witness["recomputed_objective"] != 0 or
                    any(witness["verification"].get(key) != "numerical_pass"
                        for key in ("bindings", "feasibility", "objective"))):
                raise ValueError("selected witness failed original-model replay")
            point = (controls[0], controls[1])
            if point not in points[expected]:
                points[expected].append(point)
        summary = row["verification_summary"]
        if summary.get("optimality") != "unsupported" or summary.get("completeness") != "unsupported":
            raise ValueError("trajectory checks must not be presented as separate optimality/completeness proof fields")
        if not row["warmup"]:
            measured[expected].append(row)
    if any(len(measured[strategy]) != 5 for strategy in STRATEGIES):
        raise ValueError("expected five measured attempts for each strategy")

    output = bundle / "strategy-ab-ts03-summary.html"
    svg_path = bundle / "strategy-ab-ts03-control-plane.svg"
    left, top, size = 90, 72, 440
    px = lambda x: left + x * size
    py = lambda y: top + (1 - y) * size
    shapes = []
    for strategy in STRATEGIES:
        for x, y in points[strategy]:
            radius = 8 if strategy == STRATEGIES[0] else 12
            fill = COLORS[strategy] if strategy == STRATEGIES[0] else "none"
            shapes.append(
                f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{radius}" fill="{fill}" '
                f'stroke="{COLORS[strategy]}" stroke-width="3"><title>{html.escape(LABELS[strategy])}: u0={x:g}, u1={y:g}</title></circle>')
    grid = []
    for tick in range(6):
        value = tick / 5
        grid.extend((
            f'<line x1="{px(value):.1f}" y1="{top}" x2="{px(value):.1f}" y2="{top+size}" class="grid"/>',
            f'<line x1="{left}" y1="{py(value):.1f}" x2="{left+size}" y2="{py(value):.1f}" class="grid"/>',
            f'<text x="{px(value):.1f}" y="{top+size+22}" text-anchor="middle">{value:.1f}</text>',
            f'<text x="{left-12}" y="{py(value)+4:.1f}" text-anchor="end">{value:.1f}</text>'))
    svg_path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 650 600" role="img" aria-labelledby="title desc">
<title id="title">T-S03 singular integrator Strategy A/B selected histories</title>
<desc id="desc">The exact optimal family is the horizontal segment u1 equals one, with arbitrary u0 from zero to one. Filled and outlined markers show selected histories from Strategies A and B.</desc>
<style>text{{font:14px sans-serif;fill:#263238}}.grid{{stroke:#d9e0e5;stroke-width:1}}.family{{stroke:#263238;stroke-width:4;stroke-dasharray:8 5}}.axis{{stroke:#263238;stroke-width:2}}</style>
<rect width="650" height="600" fill="white"/><text x="325" y="30" text-anchor="middle" font-size="19" font-weight="bold">T-S03 singular integrator: control plane</text>
<circle cx="205" cy="51" r="7" fill="{COLORS[STRATEGIES[0]]}"/><text x="219" y="56">Strategy A: reach-back</text><circle cx="385" cy="51" r="9" fill="none" stroke="{COLORS[STRATEGIES[1]]}" stroke-width="3"/><text x="400" y="56">Strategy B</text>
{''.join(grid)}<line x1="{px(0)}" y1="{py(1)}" x2="{px(1)}" y2="{py(1)}" class="family"/>
<line x1="{left}" y1="{top}" x2="{left}" y2="{top+size}" class="axis"/><line x1="{left}" y1="{top+size}" x2="{left+size}" y2="{top+size}" class="axis"/>
{''.join(shapes)}<text x="{left+size/2}" y="{top+size+50}" text-anchor="middle">First-stage control u₀</text>
<text transform="translate(22 {top+size/2}) rotate(-90)" text-anchor="middle">Second-stage control u₁</text>
<text x="{left+size-4}" y="{top+23}" text-anchor="end">Exact optimal family: u₁ = 1, u₀ ∈ [0,1]</text></svg>''', encoding="utf-8")

    timing = {}
    for strategy in STRATEGIES:
        values = [row["timings_ns"]["end_to_end_strategy"]["value"] for row in measured[strategy]]
        timing[strategy] = (statistics.median(values) / 1e6, min(values) / 1e6, max(values) / 1e6)
    rows_html = "".join(
        f"<tr><th>{html.escape(LABELS[s])}</th><td>{timing[s][0]:.6f}</td>"
        f"<td>{timing[s][1]:.6f}–{timing[s][2]:.6f}</td></tr>" for s in STRATEGIES)
    event_hash = environment["events_sha256"]
    scenario_hash = environment["scenario_sha256"]
    binary_hash = environment["executable_sha256"]
    html_doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-01 T-S03 Strategy A/B</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;color:#202a33;max-width:980px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbc5cc;padding:.45rem .7rem;text-align:left}}figure img{{width:min(100%,650px)}}.note{{border-left:4px solid #516b7b;padding:.4rem 1rem;background:#f4f7f8}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>MPC-01 Strategy A/B on T-S03</h1><p>This synthetic two-stage scalar case has <code>x₀=0</code>, <code>xₜ₊₁=uₜ</code>, <code>uₜ∈[0,1]</code>, and terminal cost <code>(x₂−1)²</code>. Since <code>x₂=u₁</code>, the exact optimal family is <code>u₀∈[0,1], u₁=1</code>; the first control is free and the terminal objective is singular with respect to it.</p>
<figure><img src="{svg_path.name}" alt="Exact optimal family and saved controls from both strategies in the u0-u1 plane"><figcaption>The dashed segment is the exact optimal family. Filled and outlined markers are distinct witnesses selected in the saved run by Strategies A and B.</figcaption></figure>
<h2>Saved run</h2><p>One A/B warmup pair was excluded; five measured pairs alternated order. All 12 attempts completed, each reported its profile-specific complete-family verification, and both selected histories passed original-model binding, feasibility and objective replay with objective zero. The record keeps the separate trajectory-verifier optimality and completeness fields as unsupported; the exact family statement above follows directly from the stated dynamics and objective.</p>
<h2>Descriptive timing</h2><table><thead><tr><th>Strategy</th><th>Median end-to-end (ms)</th><th>Range (ms)</th></tr></thead><tbody>{rows_html}</tbody></table><p>Timing covers strategy preparation through selection and original-data verification of two witnesses. It excludes process startup, shared scenario/provider setup, serialization, build and rendering. This five-pair result on one small synthetic fixture is descriptive and does not establish a general solver winner.</p>
<h2>Resource limit and provenance</h2><p>The complete capture process tree ran under a 2 GiB cgroup-v2 memory cap with swap disabled and a 300-second suite-level watchdog. Observed peak process-tree memory was {profile['observed']['process_tree_peak_memory_bytes']:,} bytes, with zero cgroup max/OOM events. The watchdog covers the whole invocation, not each attempt. This is below the comparison contract's per-attempt default, so it does not satisfy that limiter profile.</p>
<ul><li>Source commit: <code>{environment['source_commit']}</code></li><li>Scenario SHA-256: <code>{scenario_hash}</code></li><li>Event/stdout SHA-256: <code>{event_hash}</code></li><li>Executable SHA-256: <code>{binary_hash}</code></li><li><a href="comparison-record.json">Canonical comparison record</a> · <a href="strategy-ab-ts03-events.jsonl">raw events</a> · <a href="strategy-ab-ts03-summary.md">Markdown summary</a> · <a href="capture-environment.json">capture environment</a> · <a href="codec-environment.json">codec environment</a> · <a href="resource-profile.json">resource profile</a> · <a href="scenario.json">scenario</a> · <a href="capture-supervisor.py">capture supervisor</a> · <a href="build-note.md">build/reproduction note</a> · <a href="SHA256SUMS">file checksums</a> · <a href="../../../../scripts/reports/mpc01/summarize_strategy_ab_ts03.py">report renderer source</a></li></ul>
<p class="note">This adds one Strategy A/B synthetic singular-objective slice to #597. It does not complete the T-S01/T-S02/#421/B04 matrix, external comparisons, publication catalogue integration or general performance ranking.</p></body></html>'''
    output.write_text(html_doc, encoding="utf-8")
    summary = [
        "# MPC-01 registered Strategy A/B on T-S03", "",
        "This synthetic singular-integrator fixture uses `x0=0`, `x[t+1]=u[t]`, independent `u0,u1 in [0,1]`, and terminal cost `(x2-1)^2`. Since `x2=u1`, the exact minimizer family is `u0 in [0,1], u1=1`; this analytic family was not inferred from a selected witness.", "",
        "One warmup pair was excluded; five measured pairs alternated order. All 12 attempts completed and reported profile-specific family verification. Both selected histories passed original-model binding, feasibility, and objective checks at objective zero. The verifier's separate trajectory optimality/completeness fields remain unsupported.", "",
        "| Strategy | Median end-to-end (ms) | Range (ms) |", "|---|---:|---:|",
    ]
    summary.extend(f"| `{s}` | {timing[s][0]:.6f} | {timing[s][1]:.6f}–{timing[s][2]:.6f} |" for s in STRATEGIES)
    summary.extend(["", "Timing is strategy preparation through selected-witness replay, excluding process startup, shared setup, serialization, build and rendering. Five pairs on this one small synthetic fixture are descriptive; they establish no general winner.", "", "The full process tree ran under a 2 GiB cgroup-v2 cap with swap disabled and a 300-second suite watchdog. The watchdog is suite-wide, not per-attempt, and does not meet the comparison contract default per-attempt limiter profile.", "", f"Source commit: `{environment['source_commit']}`. Scenario SHA-256: `{scenario_hash}`. Event SHA-256: `{event_hash}`. Executable SHA-256: `{binary_hash}`.", "", "This is a partial #597 increment. The broader fixture matrix, external comparison and publication catalogue integration remain outstanding.", ""])
    (bundle / "strategy-ab-ts03-summary.md").write_text("\n".join(summary), encoding="utf-8")


if __name__ == "__main__":
    main()

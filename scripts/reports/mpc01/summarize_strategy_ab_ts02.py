#!/usr/bin/env python3
"""Validate and render the saved T-S02 Strategy A/B capture."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import statistics
from pathlib import Path


EXPECTED = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
LABELS = {EXPECTED[0]: "Reach-back (Strategy A)", EXPECTED[1]: "Strategy B"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--resource-profile", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="HTML output path")
    args = parser.parse_args()

    event_bytes = args.events.read_bytes()
    if event_bytes != args.stdout.read_bytes():
        raise ValueError("event JSONL and saved stdout differ")
    rows = [json.loads(line) for line in event_bytes.decode("utf-8").splitlines() if line]
    if len(rows) != 13 or rows[0].get("event") != "header":
        raise ValueError("expected one header and twelve trials")
    header, trials = rows[0], rows[1:]
    if (header.get("schema") != "csl.synthesis.paired-family-event/1" or
            header.get("profile") != "ts02_constant_integrator" or
            header.get("assurance") != "numerical" or
            header.get("scenario_sha256") != digest(args.scenario)):
        raise ValueError("event header does not bind the T-S02 scenario")
    if len([row for row in trials if row["warmup"]]) != 2:
        raise ValueError("expected exactly one excluded warmup pair")

    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    profile_bytes = args.resource_profile.read_bytes()
    profile = json.loads(profile_bytes)
    record = json.loads(args.record.read_text(encoding="utf-8"))
    if (environment["scenario_sha256"] != digest(args.scenario) or
            environment["measurement"]["resource_profile_sha256"] != digest(args.resource_profile) or
            record.get("schema") != "csl.comparison-record/1" or
            len(record.get("attempts", [])) != 12):
        raise ValueError("environment or canonical record does not bind this capture")
    if (profile.get("schema") != "csl.mpc01-resource-profile/1" or
            profile.get("status") != "completed" or
            profile["enforced_limits"].get("memory_max_bytes") != 2147483648 or
            profile["enforced_limits"].get("memory_swap_max_bytes") != 0 or
            profile["requested_limits"].get("process_tree_wall_time_seconds") != 300 or
            profile["observed"].get("exit_code") != 0 or
            profile["observed"].get("timed_out") is not False):
        raise ValueError("capture did not complete under its declared resource profile")
    if any(line.rsplit(" ", 1)[-1] != "0" for line in profile["observed"]["memory_events"]
           if line.startswith(("max ", "oom ", "oom_kill ", "oom_group_kill "))):
        raise ValueError("capture reached a cgroup memory/oom event")

    measured = {strategy: [] for strategy in EXPECTED}
    selected = {}
    for index, row in enumerate(trials):
        repetition, position = divmod(index, 2)
        strategy = row.get("strategy")
        expected = (EXPECTED[position] if repetition == 0 or repetition % 2 == 1
                    else EXPECTED[1 - position])
        if (row.get("event") != "trial" or row.get("repetition") != repetition or
                row.get("order_position") != position or strategy != expected or
                row.get("status") != "passed" or row.get("termination") != "completed" or
                row.get("outcome") != "optimal" or not row.get("complete_family_verified") or
                row.get("distinct_witnesses") != 2):
            raise ValueError(f"invalid or incomplete T-S02 pair at row {index}")
        summary = row["verification_summary"]
        if summary.get("optimality") != "unsupported" or summary.get("completeness") != "unsupported":
            raise ValueError("witness checks must not be promoted to separate optimality/completeness proofs")
        for witness in row["witnesses"]:
            controls = [control[0] for control in witness["controls"]]
            states = [state[0] for state in witness["states"]]
            if (len(controls) != 2 or any(control < 0 or control > 1 for control in controls) or
                    states != [0, controls[0], controls[0] + controls[1]] or
                    witness["original_objective"] != 3 or witness["recomputed_objective"] != 3 or
                    any(witness["verification"].get(key) != "numerical_pass"
                        for key in ("bindings", "feasibility", "objective"))):
                raise ValueError("selected witness failed original-model replay")
        if not row["warmup"]:
            measured[strategy].append(row)
            selected[strategy] = [witness["controls"] for witness in row["witnesses"]]
    if any(len(attempts) != 5 for attempts in measured.values()):
        raise ValueError("expected five measured pairs per strategy")

    output = args.output.resolve()
    svg_path = output.with_name("strategy-ab-ts02-control-plane.svg")
    summary_path = output.with_suffix(".md")
    colors = {EXPECTED[0]: "#1874a5", EXPECTED[1]: "#d7652b"}
    points = []
    for strategy in EXPECTED:
        for witness_index, controls in enumerate(selected[strategy]):
            x, y = 100 + controls[0][0] * 420, 510 - controls[1][0] * 420
            points.append(
                f'<circle cx="{x}" cy="{y}" r="{9 if witness_index == 0 else 6}" '
                f'fill="{colors[strategy]}" fill-opacity=".82" stroke="white" stroke-width="2">'
                f'<title>{html.escape(LABELS[strategy])}, witness {witness_index + 1}: '
                f'u0={controls[0][0]:g}, u1={controls[1][0]:g}</title></circle>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 610" role="img" aria-labelledby="title desc">
<title id="title">T-S02 constant-integrator control plane</title>
<desc id="desc">The entire unit square is the exact optimal family. Both strategies return the same two checked corner histories.</desc>
<rect width="620" height="610" fill="white"/><text x="310" y="35" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">T-S02 control plane</text>
<rect x="100" y="90" width="420" height="420" fill="#cfe8dc" stroke="#28794d" stroke-width="3"/>
<text x="310" y="112" text-anchor="middle" font-family="sans-serif" font-size="14">Exact minimizer set: every (u₀,u₁) ∈ [0,1]²</text>
<line x1="100" y1="510" x2="520" y2="510" stroke="#263238" stroke-width="2"/><line x1="100" y1="90" x2="100" y2="510" stroke="#263238" stroke-width="2"/>
<text x="310" y="565" text-anchor="middle" font-family="sans-serif" font-size="16">First-stage control u₀</text><text transform="translate(30 300) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="16">Second-stage control u₁</text>
{''.join(points)}
<text x="310" y="595" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#475569">Strategy A blue · Strategy B orange · overlapping points are coincident</text></svg>'''
    svg_path.write_text(svg, encoding="utf-8")

    timing = {}
    for strategy in EXPECTED:
        values = [row["timings_ns"]["end_to_end_strategy"]["value"] for row in measured[strategy]]
        timing[strategy] = (statistics.median(values), min(values), max(values))
    scenario_hash = digest(args.scenario)
    event_hash = digest(args.events)
    build_provenance = environment["binary_build_provenance"]
    repository_root = Path(__file__).resolve().parents[3]
    build_note_href = html.escape(os.path.relpath(
        repository_root / build_provenance["build_note"]["path"], output.parent))
    process_record_href = html.escape(os.path.relpath(
        repository_root / build_provenance["process_record"]["path"], output.parent))
    checksum_href = html.escape(os.path.relpath(
        repository_root / build_provenance["checksum_manifest"]["path"], output.parent))
    record_resource_bound = all(
        json.loads(run["run"])["result"]["raw_output"].get("resource_profile_json") ==
        profile_bytes.decode("utf-8")
        for run in record["attempts"])
    if not record_resource_bound:
        raise ValueError("canonical attempts do not embed the exact limited-capture profile")

    report = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-01 T-S02 Strategy A/B</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;color:#202a33;max-width:980px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbc5cc;padding:.45rem .7rem;text-align:left}}figure img{{width:min(100%,620px)}}.note{{border-left:4px solid #516b7b;padding:.4rem 1rem;background:#f4f7f8}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>MPC-01 Strategy A/B on T-S02</h1><p>This functional capture uses the two-stage scalar integrator <code>x₀=0</code>, <code>xₜ₊₁=xₜ+uₜ</code>, <code>uₜ∈[0,1]</code>, with constant objective <code>J=3</code>. Thus every feasible control pair in the unit square is an exact minimizer; this deliberately simple case checks strategy-family plumbing and witness replay, not optimization difficulty.</p>
<figure><img src="{html.escape(svg_path.name)}" alt="The full unit square is the exact optimal family, with overlapping selected witnesses from both strategies"><figcaption>Both strategies selected the same two distinct corner histories. The filled square is the complete exact optimal family by the scenario definition.</figcaption></figure>
<h2>Saved run</h2><p>One excluded warmup pair and five measured alternating pairs; all 12 trials passed. Each trial marked the profile-specific family complete and returned two distinct histories. Independent original-model numerical checks passed for bindings, feasibility, and objective (both original and recomputed costs equal 3). Separate optimality and optimizer-completeness proof fields remain unsupported.</p>
<h2>Descriptive timing</h2><table><thead><tr><th>Strategy</th><th>Median end-to-end (ms)</th><th>Range (ms)</th></tr></thead><tbody>{''.join(f'<tr><th>{html.escape(LABELS[s])}</th><td>{timing[s][0]/1e6:.6f}</td><td>{timing[s][1]/1e6:.6f}–{timing[s][2]/1e6:.6f}</td></tr>' for s in EXPECTED)}</tbody></table>
<p>Timing covers strategy preparation through two original-problem witness checks. It excludes process startup, shared setup, serialization, build, and rendering. This tiny constant-objective case is not evidence for a general performance winner.</p>
<h2>Resource profile and provenance</h2><p>The whole capture process tree ran with a 2 GiB cgroup-v2 memory cap, swap disabled, and a 300-second suite-level watchdog. It completed in {profile['elapsed_wall_time_ns']/1e9:.6f} s with peak process-tree memory {profile['observed']['process_tree_peak_memory_bytes']} bytes and zero OOM/limit events. The wall limit applies to the full invocation, not individually restarted trials; this profile is below the default per-attempt 8 GiB cap and does not satisfy that per-attempt timeout contract.</p>
<p>Binary source revision <code>{html.escape(build_provenance['source_revision'])}</code> is tied to the exact executable SHA-256 by the retained earlier T-S02 build note and process record; the report checksum file pins both. The T-S02 capture executable hash matches that archived binary. The execution worktree commit records the launch directory only, and its captured dynamic-dependency list contains no CSL, HiGHS, or Qhull shared library.</p>
<ul><li>Source commit: <code>{html.escape(environment['source_commit'])}</code></li><li>Launch worktree commit: <code>{html.escape(environment['execution_worktree_commit'])}</code> (working directory only)</li><li>Executable SHA-256: <code>{html.escape(environment['executable_sha256'])}</code></li><li>Scenario SHA-256: <code>{scenario_hash}</code></li><li>Events SHA-256: <code>{event_hash}</code></li><li><a href="strategy-ab-ts02-environment.json">Capture environment</a> · <a href="strategy-ab-ts02-csl-environment.json">Codec environment</a> · <a href="resource-profile.json">Resource profile</a> · <a href="binary-dynamic-dependencies.txt">Dynamic dependencies</a></li><li>Archived build provenance: <a href="{build_note_href}">build note</a> · <a href="{process_record_href}">process record</a> · <a href="{checksum_href}">checksums</a></li><li><a href="strategy-ab-ts02-events.jsonl">Raw events</a> · <a href="strategy-ab-ts02-stdout.jsonl">Raw stdout</a> · <a href="scenario.json">Scenario</a></li><li><a href="strategy-ab-ts02-comparison-record.json">Canonical comparison record</a> with the exact profile bytes embedded in each attempt</li><li><a href="capture-supervisor.py">Capture supervisor</a></li></ul>
<p class="note">This is a limited T-S02 functional comparison slice for #597. It does not complete the broader MPC-01 matrix, external solver comparison, default per-attempt limiter profile, or general ranking.</p></body></html>'''
    output.write_text(report, encoding="utf-8")

    lines = [
        "# Resource-limited saved Strategy A/B T-S02 capture", "",
        "T-S02 is the two-stage scalar integrator with `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and constant objective `J=3`. Every feasible control pair is therefore an exact minimizer; this fixture checks family plumbing and witness replay, not optimization difficulty.", "",
        f"- Source commit: `{environment['source_commit']}`.", f"- Scenario SHA-256: `{scenario_hash}`.", f"- Event/stdout SHA-256: `{event_hash}`.",
        f"- Source revision `{build_provenance['source_revision']}` and executable SHA-256 `{build_provenance['executable_sha256']}` are cross-bound by the retained EXP-02 T-S02 build note/process record and its checksum file. The launch worktree commit `{environment['execution_worktree_commit']}` identifies the runtime working directory only; it is not represented as the source used to build the binary.",
        "- One excluded warmup pair; five measured alternating pairs; all 12 trials passed.",
        "- Each result marked its profile-specific family complete and returned two distinct histories. Original-model bindings, feasibility, and objective checks passed; separate proof fields for optimality and completeness remain unsupported.",
        "- The exact minimizer set is the full unit square. Both strategies returned the same two corner witnesses.", "",
        "| Strategy | Median end-to-end (ms) | Range (ms) |", "|---|---:|---:|",
    ]
    for strategy in EXPECTED:
        median, low, high = timing[strategy]
        lines.append(f"| `{strategy}` | {median/1e6:.6f} | {low/1e6:.6f}–{high/1e6:.6f} |")
    lines.extend(["", f"The process tree completed in {profile['elapsed_wall_time_ns']/1e9:.6f} s under a 2 GiB cgroup-v2 memory cap, no swap, and a 300-second suite-level watchdog; peak memory was {profile['observed']['process_tree_peak_memory_bytes']} bytes with zero OOM/limit events. This wall cap covers the whole capture invocation, not individual trials. The profile is below the default 8 GiB per-attempt cap and does not fulfill the default per-attempt timeout profile.", "", "The timings cover strategy preparation through original-problem witness verification; they exclude process startup, shared setup, JSON I/O, build and rendering. This tiny constant-objective fixture supports no general winner claim.", "", f"Report: [`{output.name}`]({output.name}); figure: [`{svg_path.name}`]({svg_path.name}).", ""])
    summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

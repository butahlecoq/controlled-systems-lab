#!/usr/bin/env python3
"""Render the HTML/SVG views from saved records only; never invokes the solver."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path


def read_records(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "csl.hull-benchmark-records/1":
        raise ValueError("unsupported records schema")
    return data


def svg(records: dict) -> str:
    summaries = records["summary"]
    width, height = 760, 400
    left, right, top, bottom = 76, 24, 28, 66
    plot_w, plot_h = width - left - right, height - top - bottom
    maxima = [s["max_ns"] / 1e6 for s in summaries if s.get("max_ns") is not None]
    y_max = max(maxima or [1]) * 1.15
    bars = []
    for index, row in enumerate(summaries):
        x = left + (index + 0.5) * plot_w / max(1, len(summaries))
        low, median, high = (row[key] / 1e6 for key in ("min_ns", "median_ns", "max_ns"))
        y = lambda value: top + plot_h * (1 - value / y_max)
        bars.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(high):.1f}" y2="{y(low):.1f}" stroke="#245a86" stroke-width="2"/>')
        bars.append(f'<line x1="{x-17:.1f}" x2="{x+17:.1f}" y1="{y(median):.1f}" y2="{y(median):.1f}" stroke="#a33d2b" stroke-width="7"/>')
        bars.append(f'<text x="{x:.1f}" y="{height-34}" text-anchor="middle">{row["points"]} points</text>')
    grid = []
    for tick in range(5):
        value = y_max * tick / 4
        y = top + plot_h * (1 - tick / 4)
        grid.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#d7dee6"/>')
        grid.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end">{value:.2f}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc" viewBox="0 0 {width} {height}">'
            '<title id="title">Hull reducer wall time by grid size</title>'
            '<desc id="desc">Median duration shown as a red horizontal marker; min to max range shown as a blue line, in milliseconds. Seven repetitions per case.</desc>'
            '<style>text{font:13px system-ui,sans-serif;fill:#17212b}</style>'
            + ''.join(grid) + ''.join(bars)
            + f'<text x="{left}" y="18">Duration (ms)</text>'
            + f'<text x="{left+plot_w/2}" y="{height-7}" text-anchor="middle">Deterministic unit-square lattice case</text></svg>')


def page(records: dict) -> str:
    rows = []
    for s in records["summary"]:
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            s["case_id"], s["points"], f'{s["median_ns"]/1e6:.3f}',
            f'{s["min_ns"]/1e6:.3f}–{s["max_ns"]/1e6:.3f}',
            f'{s["successes"]}/{s["attempts"]}', s["failures"], s["median_lp_calls"])) + "</tr>")
    failures = records["process"]["failures"]
    verdict = "All measured trials matched the independent fixture checks." if not failures else f"{failures} measured trial(s) failed verification; no successful-only ranking is reported."
    commit = html.escape(records["code_commit"])
    trial_text = html.escape(records["environment"]["trial_policy"])
    scope = html.escape(records["environment"]["timing_scope"])
    assurance = html.escape(records["fixture"]["assurance"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPT-05 LP-backed hull reduction results</title>
<style>body{{margin:2rem auto;padding:0 1rem;max-width:1000px;font:16px/1.55 system-ui,sans-serif;color:#17212b}}h1,h2{{line-height:1.2}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{padding:.5rem .6rem;border:1px solid #bdc7d1;text-align:right}}th:first-child,td:first-child{{text-align:left}}figure{{margin:1.5rem 0}}svg{{width:100%;height:auto}}.note{{padding:.8rem 1rem;background:#f2f5f8;border-left:4px solid #527a9f}}code{{overflow-wrap:anywhere}}a{{color:#14578a}}</style></head>
<body><h1>LP-backed finite hull reduction</h1>
<p>Versioned result record <code>{html.escape(records["report_id"])}</code>, measured against source commit <code>{commit}</code>. This is a single-adapter descriptive report, not a comparison or speedup claim.</p>
<p class="note">{html.escape(verdict)} A complete result means all candidates received correctly bound LP outcomes and removal witnesses passed binary64 tolerance checks. It does not establish exact or validated hull equality.</p>
<h2>Measured reducer-call duration</h2><figure><img src="latency.svg" alt="Median reducer-call duration and observed min-to-max range for three grid sizes"><figcaption>Seven measured runs per case; one warmup per case excluded. The red marker is median; blue span is min to max. Values are wall-clock time for <code>reduce_hull</code>; fixture construction, LP registration, and workspace factory are outside the interval, while first-use HiGHS initialization inside the call is included.</figcaption></figure>
<table><thead><tr><th>Case</th><th>Points</th><th>Median (ms)</th><th>Range (ms)</th><th>Verified / runs</th><th>Failures</th><th>Median LP calls</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Workload and verification</h2><p>{html.escape(records["fixture"]["definition"])}. The independent oracle checks the four expected square-corner IDs, all returned barycentric certificates against original coordinates, complete status, and that reducer-reported LP calls match the number of attempts. Assurances: {assurance}</p>
<p>HiGHS {html.escape(records["backend"]["version"])} with simplex, presolve off, parallel off, and one configured native thread. Cases were run in interleaved order, with a fresh LP workspace for each trial. Policy: {trial_text}</p>
<h2>Timing scope and limits</h2><p>{scope}</p><p>No general runtime complexity or application-throughput claim follows from these three 2-D regular grids. They do not benchmark other simplex methods, geometry representations, conversions, or alternative hull reducers. The separate sampling profile is not included in the measured values.</p>
<h2>Environment, failures, and raw data</h2><p>OS: {html.escape(records["environment"]["os"])}; CPU and memory/load snapshots and concurrent-work note are in <a href="records.json">records.json</a>. Process exit: {records["process"]["exit_code"]}; raw attempts: {records["process"]["trial_rows"]} including {records["process"]["warmup_rows"]} warmups.</p>
<ul><li><a href="records.json">Versioned raw and summary JSON</a></li><li><a href="trials.csv">Per-trial CSV including every outcome count</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="profile/README.md">Separate limiter profile and source mapping</a></li><li><a href="README.md">Reproduction and artifact notes</a></li></ul>
<p>Generated only from saved records. Rendering does not invoke the reducer or solver.</p></body></html>'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    records = read_records(args.records)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "latency.svg").write_text(svg(records), encoding="utf-8", newline="\n")
    (args.out / "index.html").write_text(page(records), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

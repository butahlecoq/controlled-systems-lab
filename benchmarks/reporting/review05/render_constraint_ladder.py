#!/usr/bin/env python3
"""Render the saved CONSTRAINT-01 capture."""
from __future__ import annotations
import argparse, html, json
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text())
    summary = json.loads((bundle / "summary.json").read_text())
    rows, shapes = [], []
    colors = {2: "#2563eb", 4: "#16a34a", 8: "#c2410c"}
    for case in summary["cases"]:
        count = case["state_rows_per_stage"]
        strategy_cells = []
        for strategy, label in (("csl.synthesis.reach-back", "Reach-back"),
                                ("csl.synthesis.strategy-b", "Strategy B")):
            record = case["strategies"][strategy]
            if record["median_ns"] is None:
                strategy_cells.append("no verified measured pair")
            else:
                strategy_cells.append(f"{record['median_ns']/1e6:.3f} ms<br><small>{record['min_ns']/1e6:.3f}–{record['max_ns']/1e6:.3f} ms<br>CPU {record['median_child_cpu_seconds']:.6f} s; RSS {record['median_peak_rss_kib']:.0f} KiB</small>")
            shape = record["representation_shape"] or {}
            shapes.append(f"<tr><th>{label}</th><td>{count}</td><td>{case['authored_state_rows_total']}</td><td>{shape.get('joint_coordinates','—')}</td><td>{shape.get('inequality_rows','—')}</td><td>{shape.get('equality_rows','—')}</td><td>{shape.get('nonzero_h_coefficients','—')}</td></tr>")
        rows.append(f"<tr><th>{count} per stage<br>({case['authored_state_rows_total']} total)</th><td>{strategy_cells[0]}</td><td>{strategy_cells[1]}</td><td>{case['verified_measured_attempts']}/12</td><td>{case['verified_paired_repetitions']}/6</td></tr>")
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 290" role="img" aria-labelledby="title desc"><title id="title">Equivalent state constraints with 2, 4, or 8 authored H rows</title><desc id="desc">All three scalar state descriptions define the same interval from minus two to two. Additional H inequalities are looser redundant bounds.</desc><rect width="820" height="290" fill="white"/><text x="30" y="30" font-family="sans-serif" font-size="18" font-weight="bold">Same state interval, increasing authored H-row count</text>']
    x0, x1, y = 90, 730, 145
    scale = (x1 - x0) / 8
    svg.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#334155" stroke-width="2"/><text x="{x1+12}" y="{y+5}" font-family="sans-serif" font-size="14">x</text>')
    for value in (-3, -2.5, -2, 0, 2, 2.5, 3):
        xpos = x0 + (value + 4) * scale
        svg.append(f'<line x1="{xpos}" y1="{y-5}" x2="{xpos}" y2="{y+5}" stroke="#475569"/><text x="{xpos-8}" y="{y+25}" font-family="sans-serif" font-size="12">{value:g}</text>')
    left, right = x0 + 2 * scale, x0 + 6 * scale
    svg.append(f'<rect x="{left}" y="{y-18}" width="{right-left}" height="36" rx="4" fill="#2563eb" fill-opacity="0.20" stroke="#1d4ed8" stroke-width="2"/><text x="{(left+right)/2-48}" y="{y+5}" font-family="sans-serif" font-size="13">feasible set [-2,2]</text>')
    svg.append(f'<line x1="{x0+1.5*scale}" y1="{y-34}" x2="{x0+1.5*scale}" y2="{y+34}" stroke="#16a34a" stroke-width="2" stroke-dasharray="5 4"/><line x1="{x0+6.5*scale}" y1="{y-34}" x2="{x0+6.5*scale}" y2="{y+34}" stroke="#16a34a" stroke-width="2" stroke-dasharray="5 4"/><text x="30" y="220" font-family="sans-serif" font-size="13" fill="#166534">4 rows/stage add bounds at ±2.5 (green)</text>')
    svg.append(f'<line x1="{x0+1*scale}" y1="{y-34}" x2="{x0+1*scale}" y2="{y+34}" stroke="#c2410c" stroke-width="2" stroke-dasharray="3 4"/><line x1="{x0+7*scale}" y1="{y-34}" x2="{x0+7*scale}" y2="{y+34}" stroke="#c2410c" stroke-width="2" stroke-dasharray="3 4"/><text x="30" y="247" font-family="sans-serif" font-size="13" fill="#9a3412">8 rows/stage also add looser bounds at ±3 (orange)</text><text x="30" y="275" font-family="sans-serif" font-size="12" fill="#475569">All are exact redundant inequalities over the shared state interval; dimension, horizon and dynamics stay fixed.</text></svg>')
    (bundle / "constraint-geometry.svg").write_text("".join(svg))
    env = manifest["environment"]
    source_hashes = html.escape(json.dumps(env["measurement_source_sha256"], sort_keys=True))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>REVIEW-05 state-constraint row pilot</title><style>body{{max-width:1080px;margin:2rem auto;padding:0 1rem;font:16px/1.55 system-ui;color:#17212b}}h1,h2{{line-height:1.2}}.note{{padding:1rem;background:#fff5dd;border-left:4px solid #bb7900}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{padding:.5rem;border:1px solid #aab4c0;text-align:left}}img{{width:min(100%,820px);height:auto}}code{{overflow-wrap:anywhere}}small{{color:#475569}}</style></head><body><h1>REVIEW-05: state-constraint row-count pilot</h1><p>At fixed state/control dimension n=1, horizon T=2, initial state, dynamics, controls and objective, this run increases authored state H rows from 2 to 4 to 8 per stage. Every variant defines the same interval [-2,2]; added inequalities are exact redundant bounds. Each fixture has three constrained stages.</p><p class="note"><strong>Evidence scope:</strong> the independent exact-rational fixture oracle checks the fixed scenario data, required initial/dynamics/control/state rows, attained zero objective, and feasibility of the zero history in every emitted relation. This proves the unique zero optimum for these three fixtures only; it is not a general completeness or arbitrary polyhedral-equivalence certificate.</p><h2>Matched measured runs</h2><table><thead><tr><th>Authored state rows</th><th>Reach-back median<br><small>run range; CPU; peak RSS</small></th><th>Strategy B median<br><small>run range; CPU; peak RSS</small></th><th>Verified attempts</th><th>Verified pairs</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p>One excluded warmup and six alternating measured pairs were attempted per case. The solver timing covers <code>SynthesisWorkspace::run()</code> only. The wrapper also records exact child user+system CPU and peak RSS from POSIX <code>wait4</code>; these receipts cover the complete isolated process and are not additive with solver time. One backend thread was requested and each process had 300 s CPU, 8 GiB address-space and 300 s wall limits. These are descriptive values; they establish no winner, speedup, memory scaling law or source-level limiter. Linux <code>perf</code> was unavailable.</p><h2>Constraint geometry</h2><figure><a href="constraint-geometry.svg"><img src="constraint-geometry.svg" alt="Three equivalent scalar state sets with 2, 4, or 8 authored inequalities per stage"></a><figcaption>Dashed lines show the added redundant bounds for the larger row counts.</figcaption></figure><h2>Emitted relation shape</h2><table><thead><tr><th>Strategy</th><th>Rows/stage</th><th>Authored total</th><th>Joint coordinates</th><th>Output inequality rows</th><th>Output equality rows</th><th>Nonzero H coefficients</th></tr></thead><tbody>{''.join(shapes)}</tbody></table><p>Output row and coefficient counts describe the emitted H-relation, not allocated bytes, solver iterations, sparse factorization work, or phase durations. The visual here is one-dimensional; the independent two-dimensional illustration remains in the <a href="../review05-dimension-20261031/index.html">dimension ladder report</a>.</p><h2>Reproducibility</h2><p>Data capture revision <code>{html.escape(env['source_revision'])}</code>, binary SHA-256 <code>{html.escape(env['binary_sha256'])}</code>. <a href="build-provenance.json">Build provenance</a>; <a href="build/configure.log">configure log</a>; <a href="build/build.log">full Release build log</a>; <a href="manifest.json">manifest</a>; <a href="attempts.jsonl">raw attempts</a>; <a href="checks.jsonl">exact-check results</a>; <a href="summary.json">summary</a>; <a href="diagnostics/README.md">excluded preflight and profiler diagnostics</a>; <a href="SHA256SUMS">file hashes</a>. Inputs: <a href="inputs/constraint01-n1-t2-r2.json">2 rows/stage</a>, <a href="inputs/constraint01-n1-t2-r4.json">4 rows/stage</a>, <a href="inputs/constraint01-n1-t2-r8.json">8 rows/stage</a>.</p><p>Measurement-source hashes: <code>{source_hashes}</code></p></body></html>'''
    (bundle / "index.html").write_text(page)
    print(bundle / "index.html")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

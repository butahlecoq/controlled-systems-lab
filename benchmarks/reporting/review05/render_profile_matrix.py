#!/usr/bin/env python3
"""Render the saved REVIEW-05 profile matrix as standalone HTML and SVGs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


PROFILES = (
    ("ts01_exact_integrator", "T-S01 exact integrator", "Segment", "#60a5fa"),
    ("ts02_constant_integrator", "T-S02 constant objective", "Full control square", "#34d399"),
    ("ts03_singular_integrator", "T-S03 singular objective", "Terminal edge", "#fbbf24"),
)
STRATEGIES = (
    ("csl.synthesis.reach-back", "Reach-back", "#60a5fa"),
    ("csl.synthesis.strategy-b", "Strategy B", "#f472b6"),
)


def geometry_svg() -> str:
    width, height, plot = 970, 330, 190
    panels = []
    for index, (_, title, family, color) in enumerate(PROFILES):
        left, top = 40 + index * 310, 70
        right, bottom = left + plot, top + plot
        panels.append(f'<g><text x="{left}" y="32" class="title">{html.escape(title)}</text>'
                      f'<rect x="{left}" y="{top}" width="{plot}" height="{plot}" class="frame"/>')
        for tick in range(1, 4):
            position = left + tick * plot / 4
            panels.append(f'<line x1="{position}" y1="{top}" x2="{position}" y2="{bottom}" class="grid"/>')
            position = top + tick * plot / 4
            panels.append(f'<line x1="{left}" y1="{position}" x2="{right}" y2="{position}" class="grid"/>')
        if index == 0:
            panels.append(f'<line x1="{left}" y1="{top}" x2="{right}" y2="{bottom}" stroke="{color}" stroke-width="5"/>')
        elif index == 1:
            panels.append(f'<rect x="{left}" y="{top}" width="{plot}" height="{plot}" '
                          f'fill="{color}" fill-opacity="0.27" stroke="{color}" stroke-width="4"/>')
        else:
            panels.append(f'<line x1="{left}" y1="{top}" x2="{right}" y2="{top}" stroke="{color}" stroke-width="6"/>')
        panels.append(f'<text x="{left}" y="{bottom + 26}" class="axis">0</text>'
                      f'<text x="{right}" y="{bottom + 26}" class="axis" text-anchor="end">1</text>'
                      f'<text x="{left + plot / 2}" y="{bottom + 47}" class="label" text-anchor="middle">u₀</text>'
                      f'<text x="{left - 16}" y="{top + plot / 2}" class="label" '
                      f'text-anchor="middle" transform="rotate(-90 {left - 16} {top + plot / 2})">u₁</text>'
                      f'<text x="{left}" y="{height - 12}" class="family">{html.escape(family)}</text></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            'aria-labelledby="geom-title geom-desc"><title id="geom-title">Analytic optimal control histories</title>'
            '<desc id="geom-desc">T-S01 optimal histories form a segment; T-S02 includes the full control square; '
            'T-S03 leaves the first control free and fixes the terminal control at one.</desc>'
            '<style>text{font-family:system-ui,sans-serif;fill:#e2e8f0}.title{font-size:16px;font-weight:650}'
            '.axis{font-size:12px;fill:#94a3b8}.label{font-size:14px}.family{font-size:13px;fill:#cbd5e1}'
            '.frame{fill:#0b1220;stroke:#475569;stroke-width:1}.grid{stroke:#334155;stroke-width:1}</style>'
            + ''.join(panels) + '</svg>')


def timing_svg(checks: dict) -> str:
    rows = []
    profiles = checks["profiles"]
    max_ms = 6.0
    width, height = 980, 330
    left, right, top, row_h = 300, 900, 72, 42
    for pindex, (profile, title, _, _) in enumerate(PROFILES):
        data = profiles[profile]["strategies"]
        for sindex, (strategy_id, strategy_name, color) in enumerate(STRATEGIES):
            item = data[strategy_id]["end_to_end_strategy_ns"]
            y = top + (pindex * 2 + sindex) * row_h
            start = left + item["min"] / 1e6 / max_ms * (right - left)
            end = left + item["max"] / 1e6 / max_ms * (right - left)
            median = left + item["median"] / 1e6 / max_ms * (right - left)
            label = f'{title} · {strategy_name}'
            rows.append(f'<text x="{left - 12}" y="{y + 5}" class="row" text-anchor="end">'
                        f'{html.escape(label)}</text><line x1="{start:.1f}" y1="{y}" x2="{end:.1f}" y2="{y}" '
                        f'stroke="{color}" stroke-width="8" stroke-linecap="round"/>'
                        f'<circle cx="{median:.1f}" cy="{y}" r="7" fill="#f8fafc" stroke="{color}" stroke-width="3"/>'
                        f'<text x="{right + 12}" y="{y + 5}" class="value">{item["median"] / 1e6:.3f} ms</text>')
    axes = []
    for ms in range(0, 7):
        x = left + ms / max_ms * (right - left)
        axes.append(f'<line x1="{x}" y1="{top - 20}" x2="{x}" y2="{top + 5 * row_h + 20}" class="grid"/>'
                    f'<text x="{x}" y="{height - 18}" class="axis" text-anchor="middle">{ms}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            'aria-labelledby="time-title time-desc"><title id="time-title">Paired end-to-end strategy timings</title>'
            '<desc id="time-desc">Each bar spans the observed minimum and maximum; the circle marks the median. '
            'Timings are descriptive and use one Release build.</desc>'
            '<style>text{font-family:system-ui,sans-serif;fill:#e2e8f0}.row{font-size:13px}.value{font-size:13px}'
            '.axis{font-size:12px;fill:#94a3b8}.grid{stroke:#334155;stroke-width:1}</style>'
            + ''.join(axes) + ''.join(rows) + '<text x="600" y="320" class="axis" text-anchor="middle">End-to-end strategy time (ms)</text></svg>')


def render(checks_path: Path, out: Path, source_commit: str) -> None:
    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    geometry = geometry_svg()
    timings = timing_svg(checks)
    (out / "optimal-control-histories.svg").write_text(geometry + "\n", encoding="utf-8")
    (out / "paired-timings.svg").write_text(timings + "\n", encoding="utf-8")
    rows = []
    for profile, title, family, _ in PROFILES:
        results = checks["profiles"][profile]["strategies"]
        cells = []
        for strategy, _, _ in STRATEGIES:
            item = results[strategy]
            t = item["end_to_end_strategy_ns"]
            cells.append(f'<td>{t["median"]/1e6:.3f} ms ({t["min"]/1e6:.3f}–{t["max"]/1e6:.3f})</td>')
        rows.append(f'<tr><th scope="row">{html.escape(title)}</th>{"".join(cells)}'
                    f'<td>{html.escape(family)}</td></tr>')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>REVIEW-05 exact-profile matrix</title>
<style>
body{{margin:0;background:#0b1020;color:#e2e8f0;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:2rem}}h1,h2{{line-height:1.2}}a{{color:#7dd3fc}}
.scope{{border-left:4px solid #fbbf24;background:#171d30;padding:.8rem 1rem}}
img{{width:100%;height:auto;border-radius:12px;background:#0f172a}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{border-bottom:1px solid #334155;padding:.55rem;text-align:left}}code{{color:#fde68a}}
small{{color:#94a3b8}}li{{margin:.35rem 0}}
</style></head><body><main>
<p>REVIEW-05 · paired synthesis profiles</p><h1>Three exact integrator profiles</h1>
<p class="scope"><strong>Scope.</strong> Each profile has one scalar state, one scalar control, and a two-step horizon.
This matrix changes the objective and optimal-family shape; it does not vary problem dimension or horizon.
Every measured attempt returned a registry-verified complete family and two distinct witnesses that passed original-problem
binding, feasibility, and objective checks. Assurance is numerical.</p>
<h2>End-to-end timings</h2><p>The interval includes strategy preparation, workspace creation, family construction and registered
verification, selection of two distinct histories, and original-problem witness checks. It excludes process startup, shared
scenario/provider setup, serialization, build, and rendering.</p>
<img src="paired-timings.svg" alt="Median end-to-end strategy times with observed minimum-to-maximum ranges">
<table><thead><tr><th>Profile</th><th>Reach-back</th><th>Strategy B</th><th>Optimal control-history set</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p>Across these tiny profiles, Strategy B has the lower median in each case. The performance conclusion remains
<strong>inconclusive</strong>: five or seven pairs per profile and no source-attributed limiter profile do not support a
general ranking. The spread and phase data are in <a href="checks.json">checks.json</a>; complete attempts are in
<a href="raw/">raw event records</a>.</p>
<h2>Optimal control histories</h2><p>Both axes are control values: horizontal <code>u₀</code>, vertical <code>u₁</code>.
These are analytic projections of the complete profiles, not reachable-state plots.</p>
<img src="optimal-control-histories.svg" alt="Optimal histories in the u0-u1 control plane: a segment, square, and terminal edge">
<p>The canonical H relations have five joint coordinates. Source declarations specify respectively 4 inequality and 4 equality
rows (10 nonzeros) for T-S01, 4 and 3 rows (11 nonzeros) for T-S02, and 2 and 4 rows (7 nonzeros) for T-S03. These are
static canonical sizes, not measured allocation or matrix-byte counts. All three fixtures have the same state/control dimension
and horizon, so they are not an output-growth sweep.</p>
<h2>Method and limits</h2><ul>
<li>T-S01: quadratic terminal objective; optimal control histories form <code>u₀+u₁=1</code>.</li>
<li>T-S02: constant objective; every control pair in <code>[0,1]²</code> is optimal.</li>
<li>T-S03: singular terminal objective; <code>u₁=1</code> while <code>u₀</code> remains free.</li>
<li>One excluded warmup pair per profile; 7 measured pairs for T-S01 and 5 for each remaining profile. Side order alternates within each profile.</li>
<li>One backend thread; per-process 300-second CPU and wall limits and 8 GiB address-space limit. All processes completed under 0.1 seconds.</li>
<li>No profiler or internal LP/convex call counters were collected. The measured medians are descriptive and do not establish
scalability or a general strategy winner.</li></ul>
<p>Source commit <code>{html.escape(source_commit)}</code>; build and host details are in
<a href="build-configuration.txt">build-configuration.txt</a>. Reproduction:
<code>benchmarks/reporting/review05/capture_profile_matrix.py</code> followed by
<code>benchmarks/reporting/review05/check_profile_matrix.py</code>.</p>
<small>This report is a partial #95 scalability evidence slice. General matched horizon/dimension workloads, runtime output growth,
and source-attributed limiter evidence remain outstanding.</small>
</main></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    render(args.checks, args.out, args.source_commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

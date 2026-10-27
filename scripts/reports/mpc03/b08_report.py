"""Deterministic saved-record renderer for the B08 MIQCP report."""
from __future__ import annotations

import html
import math
from fractions import Fraction


def hull(points):
    ordered = sorted(set((float(x), float(y)) for x, y in points))
    if len(ordered) <= 1:
        return ordered

    def cross(origin, left, right):
        return ((left[0] - origin[0]) * (right[1] - origin[1]) -
                (left[1] - origin[1]) * (right[0] - origin[0]))

    lower = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def render_svg(record: dict) -> str:
    result = record["result"]
    stages = result["projected_tube"]
    all_points = [point for stage in stages for point in stage["points"]]
    x_low = min(point[0] for point in all_points) - 0.15
    x_high = max(point[0] for point in all_points) + 0.15
    y_low = min(point[1] for point in all_points) - 0.15
    y_high = max(point[1] for point in all_points) + 0.15
    worst = result["worst_cost_corners"][0]["terminal_state"]
    worst_signs = "".join("+" if value == 1 else "−"
                          for value in result["worst_cost_corners"][0]["signs"])
    target = result["projected_target_x1_x3"]
    plan = ", ".join(f"{value:g}" for value in result["finite"]["actions"])
    width, height = 1040, 810
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">B08 displayed-data fixed-plan disturbance tube</title>',
        f'<desc id="desc">For fixed plan ({html.escape(plan)}), each stage shows every disturbance-corner history projected from the four-state model onto oxidizer flow x1 and fuel flow x3. The stage-four panel marks worst disturbance signs {worst_signs} and the projected target.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#20242b}.title{font-size:19px;font-weight:bold}.label{font-size:13px}.small{font-size:11px}.grid{stroke:#d8dde4;stroke-width:1}.hull{fill:#4c9fbb;fill-opacity:.18;stroke:#176b87;stroke-width:2}.point{fill:#176b87;fill-opacity:.36}.worst{stroke:#bd263b;stroke-width:3}.target{fill:#f2b544;stroke:#714f00;stroke-width:1.4}</style>',
        f'<text x="520" y="27" text-anchor="middle" class="title">B08 L04 disturbance tube — fixed plan ({html.escape(plan)})</text>',
        '<text x="520" y="46" text-anchor="middle" class="small">All corner histories at each stage, projected from the four-state model; panels use shared bounds.</text>',
    ]

    def px(x, x0):
        return x0 + 52 + (float(x) - x_low) / (x_high - x_low) * 380

    def py(y, y0):
        return y0 + 205 - (float(y) - y_low) / (y_high - y_low) * 179

    for index, stage in enumerate(stages):
        x0, y0 = 18 + (index % 2) * 510, 57 + (index // 2) * 245
        parts.append(f'<text x="{x0+3}" y="{y0+16}" class="label">Stage {stage["stage"]}: {stage["corner_history_count"]} disturbance histories</text>')
        for tick in range(5):
            x = x0 + 52 + tick * 95
            y = y0 + 205 - tick * 44.75
            x_value = x_low + tick * (x_high - x_low) / 4
            y_value = y_low + tick * (y_high - y_low) / 4
            parts.append(f'<line x1="{x:g}" y1="{y0+26}" x2="{x:g}" y2="{y0+205}" class="grid"/>')
            parts.append(f'<text x="{x:g}" y="{y0+220}" text-anchor="middle" class="small">{x_value:.1f}</text>')
            parts.append(f'<line x1="{x0+52}" y1="{y:g}" x2="{x0+432}" y2="{y:g}" class="grid"/>')
            parts.append(f'<text x="{x0+45}" y="{y+4:g}" text-anchor="end" class="small">{y_value:.1f}</text>')
        projected = [(point[0], point[1]) for point in stage["points"]]
        boundary = hull(projected)
        if len(boundary) >= 3:
            coordinates = " ".join(f"{px(x, x0):.2f},{py(y, y0):.2f}" for x, y in boundary)
            parts.append(f'<polygon points="{coordinates}" class="hull"/>')
        for x, y in projected:
            parts.append(f'<circle cx="{px(x, x0):.2f}" cy="{py(y, y0):.2f}" r="2.2" class="point"/>')
        if stage["stage"] == 4:
            parts.append(f'<path d="M {px(worst[0],x0)-6:.2f} {py(worst[2],y0):.2f} L {px(worst[0],x0)+6:.2f} {py(worst[2],y0):.2f} M {px(worst[0],x0):.2f} {py(worst[2],y0)-6:.2f} L {px(worst[0],x0):.2f} {py(worst[2],y0)+6:.2f}" class="worst"/>')
            tx, ty = px(target[0], x0), py(target[1], y0)
            parts.append(f'<circle cx="{tx:.2f}" cy="{ty:.2f}" r="5" class="target"/>')
        parts.append(f'<text x="{x0+242}" y="{y0+232}" text-anchor="middle" class="small">oxidizer flow x1 (kg/s)</text>')
        parts.append(f'<text x="{x0+12}" y="{y0+120}" text-anchor="middle" transform="rotate(-90 {x0+12} {y0+120})" class="small">fuel flow x3 (kg/s)</text>')
    parts.extend([
        '<circle cx="60" cy="792" r="4" class="point"/><text x="70" y="796" class="small">disturbance-corner point / projected hull</text>',
        '<path d="M 345 792 L 357 792 M 351 786 L 351 798" class="worst"/><text x="363" y="796" class="small">worst-cost terminal</text>',
        '<circle cx="520" cy="792" r="5" class="target"/><text x="531" y="796" class="small">projected target at stage 4</text>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def render_html(record: dict) -> str:
    result = record["result"]
    scenario = record["scenario"]
    finite = result["finite"]
    relaxation = result["relaxation"]
    exact = result["exact_reference"]
    upper = math.sqrt(float(Fraction(exact["minimum_squared_exact"])))
    lower = math.sqrt(float(result["bounds_squared"]["lower"]))
    actions = ", ".join(str(value) for value in scenario["actions_in_source_order"])
    plan = ", ".join(str(value) for value in finite.get("actions", []))
    tied_plans = html.escape(str(result["exact_minimizing_action_indices"]))
    commit = html.escape(record["source_commit"])
    root = f"https://github.com/butahlecoq/controlled-systems-lab/blob/{commit}"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B08 displayed-data robust minimax MIQCP</title>
<style>:root{{color-scheme:dark;--bg:#282828;--panel:#32302f;--fg:#ebdbb2;--muted:#bdae93;--accent:#8ec07c;--line:#504945}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:2rem 1.2rem}}h1,h2{{line-height:1.2}}a{{color:var(--accent)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:.5rem;padding:1rem;margin:1rem 0}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:.55rem;border-bottom:1px solid var(--line)}}code{{color:#fabd2f}}figure{{margin:1rem 0}}img{{max-width:100%;height:auto;background:#fff}}small,.muted{{color:var(--muted)}}</style></head><body><main>
<h1>B08 displayed-data robust minimax MIQCP</h1>
<p class="muted">Article-derived solve of the four-step L04 printed linear data. The original unrounded arrays and historical generator are unavailable; this is not a historical reproduction.</p>
<section class="panel"><h2>Model</h2><p>Four-state model <code>{html.escape(scenario['model'])}</code>, initial state {scenario['initial_state']}, target {scenario['target']}, ordered action catalogue ({actions}), and {len(result['projected_tube'][-1]['points'])} disturbance-corner histories. One fixed action sequence is shared across every history. The objective is the worst terminal Euclidean error; the finite model uses one-hot selectors and one quadratic epigraph constraint per disturbance corner.</p><p>The continuous relaxation replaces the finite action catalogue with its convex hull, the interval <code>[-0.6, 0.6]</code>. Its result is a lower bound on the finite optimum; rounding its controls is not a catalogue-feasible plan.</p></section>
<section class="panel"><h2>Results</h2><table><thead><tr><th>Method</th><th>Squared terminal cost</th><th>Terminal norm</th><th>Evidence</th></tr></thead><tbody>
<tr><td>Finite-action MIQCP</td><td>{finite.get('objective_squared')}</td><td>{upper:.12f}</td><td>{html.escape(finite.get('status','unavailable'))}; exact enumeration confirms the returned plan</td></tr>
<tr><td>Continuous-control QCP</td><td>{relaxation.get('global_dual_bound_squared')}</td><td>{lower:.12f}</td><td>{html.escape(relaxation.get('status','unavailable'))}; numerical global lower bound</td></tr></tbody></table>
<p>Exact displayed-data enumeration gives squared cost <code>{html.escape(exact['minimum_squared_exact'])}</code> and norm <code>{html.escape(exact['minimum_norm_decimal'])}</code>, with three tied action-index plans <code>{tied_plans}</code>. SCIP returned plan ({plan}), one of those exact ties. The article-reported norm <code>67.12</code> does not match the rounded displayed-data model.</p><p>The norm interval [{lower:.12f}, {upper:.12f}] is a lower/upper bound comparison. It is not an equal-problem speed ranking. Solver status and bounds use binary64 tolerances, not validated arithmetic.</p></section>
<figure><img src="disturbance-tube.svg" alt="All four-state disturbance-corner histories projected onto oxidizer flow x1 and fuel flow x3 at stages zero through four."><figcaption>The stage-four panel marks the exact displayed-data worst-cost corner and the target projected to (x1,x3). Each region is the convex hull of all disturbance-corner projections for the fixed plan.</figcaption></figure>
<section class="panel"><h2>Reproduce and inspect</h2><p>Optional report-only dependency: PySCIPOpt 6.3.0 (MIT) with bundled SCIP 10.0 (Apache-2.0). The PyPI wheels support Linux x86-64, Windows x86-64 and macOS x86-64/Apple Silicon. No CSL library dependency or installation surface is added.</p><pre><code>python3 -m venv .venv
.venv/bin/python -m pip install pyscipopt==6.3.0
.venv/bin/python scripts/reports/mpc03/b08_miqcp.py --output-dir /tmp/mpc03-b08-l04-miQCP-v1
python3 docs/research/tools/check_b08_displayed_exact.py --verify-record docs/research/evidence/b08-displayed-exact.json</code></pre><ul><li><a href="record.json">Saved report record</a></li><li><a href="solver-output.json">Raw solver output</a></li><li><a href="independent-oracle.json">Independent exact enumeration</a></li><li><a href="{root}/benchmarks/reporting/mpc03/b08_miqcp.py">Solver driver at commit {commit[:8]}</a></li><li><a href="{root}/docs/research/b08-displayed-exact-audit.md">Displayed-data scope and historical limits</a></li></ul></section>
<section class="panel"><h2>Limits</h2><p>The source paper's unrounded arrays and complete generator are unavailable. The rational oracle treats printed decimals as exact; SCIP receives binary64 coefficients. This case is unconstrained, linear, four-step and open-loop. It does not establish nonlinear-plant reproduction or validated arithmetic. Each solver timing is one exploratory capture and no runtime claim is made.</p></section>
</main></body></html>\n'''

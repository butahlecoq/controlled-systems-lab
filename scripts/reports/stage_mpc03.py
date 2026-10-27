"""Stage the saved MPC-03 pilot report and link it from the examples gallery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


REPORT_ID = "mpc03-open-loop-pilot-v1"
FILES = ("index.html", "record.json", "pilot-output.json", "build-provenance.json", "disturbance-tube.svg")
CARD = (
    '<article class="saved-figure" id="mpc03-open-loop-pilot-v1">'
    '<p class="eyebrow">Open-loop minimax · formulation pilot</p>'
    '<h3>A robust two-stage minimax bound</h3>'
    '<a href="../mpc03-open-loop-pilot-v1/index.html">'
    '<img src="../mpc03-open-loop-pilot-v1/disturbance-tube.svg" '
    'alt="Four endpoint disturbance histories projected onto intermediate and terminal state coordinates."></a>'
    '<p>A synthetic scalar example: finite actions and a shared-selector MILP give 2.25; '
    'the convex action relaxation gives lower bound 2.0. No timing is measured.</p>'
    '<p><a href="../mpc03-open-loop-pilot-v1/index.html">Open the saved report and raw record →</a></p></article>'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def result_points(record: dict) -> list[tuple[str, float, float]]:
    """Project every disturbance endpoint for the saved MILP's shared plan."""
    scenario = record["scenario"]
    result = record["result"]
    require(scenario.get("equations") == "x[t+1] = x[t] + u[t] + w[t]",
            "unsupported MPC-03 projection dynamics")
    catalogue = scenario["ordered_control_catalogue"]
    selectors = result["extensive_form_milp"]["shared_action_indices"]
    intervals = scenario["disturbance_intervals"]
    require(len(selectors) == 2 * len(catalogue) and len(intervals) == 2,
            "unexpected MPC-03 projection dimensions")
    controls = []
    for stage in range(2):
        weights = selectors[stage * len(catalogue):(stage + 1) * len(catalogue)]
        require(all(weight in (0, 1) for weight in weights) and sum(weights) == 1,
                "MPC-03 saved MILP plan is not one-hot")
        controls.append(sum(value * weight for value, weight in zip(catalogue, weights)))
    require(controls == [1, 1], "unsupported MPC-03 projection control plan")
    initial = float(scenario["initial_state"])
    points = []
    for first_sign, first in (("-", intervals[0][0]), ("+", intervals[0][1])):
        for second_sign, second in (("-", intervals[1][0]), ("+", intervals[1][1])):
            x1 = initial + controls[0] + first
            x2 = x1 + controls[1] + second
            points.append((first_sign + second_sign, x1, x2))
    objective = float(result["finite_upper_bound"])
    require(max(point[2] for point in points) == objective,
            "MPC-03 projected worst terminal state differs from saved result")
    return points


def render_svg(record: dict) -> str:
    points = result_points(record)
    safe_match = re.search(r"(-?\d+(?:\.\d+)?)\s*<=\s*x2\s*<=", record["result"]["safe_stages"][-1])
    require(safe_match is not None, "MPC-03 terminal safety threshold is missing")
    safety_lower = float(safe_match.group(1))
    x_values = [point[1] for point in points]
    y_values = [point[2] for point in points]
    x_low, x_high = min(x_values) - 0.125, max(x_values) + 0.125
    y_low = min(y_values) - 0.25
    y_high = max(y_values) + 0.25

    def px(value: float) -> float:
        return 100 + (value - x_low) * 550 / (x_high - x_low)

    def py(value: float) -> float:
        return 360 - (value - y_low) * 260 / (y_high - y_low)

    x_ticks = [x_low + (x_high - x_low) * index / 5 for index in range(6)]
    y_ticks = [y_low + (y_high - y_low) * index / 4 for index in range(5)]
    grid_x = "".join(f'<path d="M{px(value):g} 100V360"/>' for value in x_ticks)
    grid_y = "".join(f'<path d="M100 {py(value):g}H650"/>' for value in y_ticks)
    x_labels = "".join(f'<text x="{px(value):g}" y="380">{value:g}</text>' for value in x_ticks)
    y_labels = "".join(f'<text x="90" y="{py(value)+4:g}">{value:g}</text>' for value in reversed(y_ticks))
    by_history = {label: (x, y) for label, x, y in points}
    perimeter = ("--", "-+", "++", "+-")
    polygon = " ".join(("M" if i == 0 else "L") + f"{px(by_history[key][0]):g} {py(by_history[key][1]):g}"
                        for i, key in enumerate(perimeter)) + "Z"
    label_text = " ".join(f"{key}: ({x:g}, {y:g})" for key, x, y in points)
    worst = max(points, key=lambda point: point[2])
    markers = "".join(
        f'<circle cx="{px(x):g}" cy="{py(y):g}" r="{8 if label == worst[0] else 7}" '
        f'fill="{"#d97706" if label == worst[0] else "#235789"}"/>'
        f'<text x="{px(x):g}" y="{py(y)-12:g}">({label}){" worst" if label == worst[0] else ""}</text>'
        for label, x, y in points)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 460" role="img" aria-labelledby="title desc">
  <title id="title">Two-stage open-loop minimax disturbance histories</title>
  <desc id="desc">Saved-record projection of endpoint histories: {label_text}. The dashed polygon is their convex hull in intermediate state x1 and terminal state x2.</desc>
  <rect width="760" height="460" fill="#fff"/>
  <text x="380" y="30" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700">Fixed plan (u0,u1) = (1,1): four disturbance histories</text>
  <text x="380" y="55" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#444">2D state projection; terminal cost max x2 = {worst[2]:g}</text>
  <g stroke="#d8dee8" stroke-width="1">{grid_x}{grid_y}</g>
  <path d="M100 360H650M100 360V100" fill="none" stroke="#222" stroke-width="2"/>
  <path d="{polygon}" fill="#dce9f7" fill-opacity=".7" stroke="#50769e" stroke-width="2" stroke-dasharray="6 4"/>
  <path d="M100 {py(safety_lower):g}H650" stroke="#c23b32" stroke-width="2" stroke-dasharray="8 5"/>
  <text x="645" y="{py(safety_lower)-8:g}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#a52c25">terminal safety x2 &gt;= {safety_lower:g}</text>
  <g font-family="sans-serif" font-size="12" font-weight="700" text-anchor="middle">
    {markers}
  </g>
  <g font-family="sans-serif" font-size="12" fill="#333" text-anchor="middle">{x_labels}</g>
  <g font-family="sans-serif" font-size="12" fill="#333" text-anchor="end">{y_labels}</g>
  <text x="380" y="410" text-anchor="middle" font-family="sans-serif" font-size="14">Intermediate state x1</text>
  <text x="28" y="230" transform="rotate(-90 28 230)" text-anchor="middle" font-family="sans-serif" font-size="14">Terminal state and cost x2</text>
  <text x="380" y="450" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#555">Coordinates and hull are rendered from record.json; discrete endpoint histories remain labelled.</text>
</svg>\n'''


def render_html(record: dict) -> str:
    scenario = record["scenario"]
    result = record["result"]
    finite = result["finite_reference"]
    milp = result["extensive_form_milp"]
    relaxation = result["convex_action_relaxation"]
    source_commit = record["source_commit"]
    source_url = ("https://github.com/butahlecoq/controlled-systems-lab/blob/"
                  f"{source_commit}/benchmarks/reporting/mpc03/robust_minimax_driver.cpp")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Open-loop robust minimax formulation pilot</title>
<style>:root{{color-scheme:dark;--bg:#282828;--panel:#32302f;--fg:#ebdbb2;--muted:#bdae93;--accent:#8ec07c;--line:#504945}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}}main{{max-width:960px;margin:auto;padding:2rem 1.2rem}}h1,h2{{line-height:1.2}}a{{color:var(--accent)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:.5rem;padding:1rem;margin:1rem 0}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:.55rem;border-bottom:1px solid var(--line)}}code{{color:#fabd2f}}figure{{margin:1rem 0}}img{{max-width:100%;height:auto;background:#fff}}small,.muted{{color:var(--muted)}}</style></head><body><main>
<h1>Open-loop robust minimax formulation pilot</h1><p class="muted">Numerical formulation cross-check · timings not measured · Pages publication pending review</p>
<section class="panel"><h2>Case</h2><p>Two-stage scalar system <code>{scenario['equations']}</code>, initial state {scenario['initial_state']}, ordered finite control catalogue {tuple(scenario['ordered_control_catalogue'])}, and full interval disturbances {scenario['disturbance_intervals']}. The goal minimizes worst terminal x2 subject to {', '.join(result['safe_stages'])} for every disturbance history.</p>
<p>The solver and finite oracle enumerate {result['history_count']} endpoint products of the disturbance intervals. This covers the full intervals in this fixture: states and safety inequalities are affine in disturbances, while the terminal objective is linear, so all extrema over each disturbance box occur at endpoint products.</p></section>
<section class="panel"><h2>Results</h2><table><thead><tr><th>Method</th><th>Outcome</th></tr></thead><tbody>
<tr><td>Exhaustive finite-action oracle</td><td>{finite['value']:g}; {len(finite['minimizing_plan_indices'])} tied plans out of {finite['plan_count']}</td></tr>
<tr><td>Shared-selector extensive-form MILP</td><td>{milp['objective']:g} incumbent; {milp['best_bound']:g} best bound; reported gap {milp['gap']:g}</td></tr>
<tr><td>Continuous action-selector relaxation</td><td>{relaxation['lower_bound']:g} lower bound</td></tr></tbody></table>
<p>The interval [{result['relaxation_lower_bound']:g}, {result['finite_upper_bound']:g}] is a lower/upper bound comparison, not a speed ranking. The result uses binary64 numerical evidence, not validated arithmetic.</p></section>
<figure><img src="disturbance-tube.svg" alt="Saved endpoint histories projected onto intermediate state x1 and terminal state x2 axes."><figcaption>2D state projection of endpoint histories for a finite upper-bound plan. The polygon is rendered from the saved record's disturbance endpoints; it visualizes the continuous disturbance box image, not the original disturbance set.</figcaption></figure>
<section class="panel"><h2>Reproduce and inspect</h2><p>Configure a Release build with <code>-DCSL_ENABLE_HIGHS=ON -DCSL_BUILD_MPC03_REPORT=ON</code>, build <code>csl_mpc03_robust_minimax_report</code>, then run it with <code>--smoke</code>. No timing is collected.</p><ul><li><a href="record.json">Versioned result record</a></li><li><a href="pilot-output.json">Raw executable output</a></li><li><a href="build-provenance.json">Build provenance and reproduction command</a></li><li><a href="disturbance-tube.svg">SVG figure</a></li><li><a href="{source_url}">Driver at source commit {source_commit[:8]}</a></li></ul></section>
<section class="panel"><h2>Scope limits</h2><p>This is one synthetic two-stage scalar case, not a B08 reproduction. It does not implement quadratic or norm MIQCPs or the complete issue #599 comparison-record workflow. The Pages route and archive catalogue entry are pending review.</p></section>
</main></body></html>\n'''


def stage(source: Path, site: Path) -> None:
    source = source.resolve()
    site = site.resolve()
    require(source.is_dir(), "MPC-03 saved report bundle is missing")
    provenance = json.loads((source / "build-provenance.json").read_text(encoding="utf-8"))
    record = json.loads((source / "record.json").read_text(encoding="utf-8"))
    raw = (source / "pilot-output.json").read_bytes()
    require(record.get("schema") == "csl.mpc03-open-loop-pilot-record/1",
            "unexpected MPC-03 record schema")
    require(record.get("result") == json.loads(raw), "saved raw output differs from the report record")
    require(provenance.get("schema") == "csl.mpc03-pilot-provenance/1" and
            provenance.get("output_sha256") == hashlib.sha256(raw).hexdigest(),
            "MPC-03 output provenance hash differs")
    require(record.get("provenance") == provenance, "record and provenance metadata differ")
    scenario_hash = hashlib.sha256(json.dumps(record.get("scenario"), sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    require(record.get("scenario_sha256") == scenario_hash, "MPC-03 scenario hash differs")
    require(provenance.get("driver_path") == "benchmarks/reporting/mpc03/robust_minimax_driver.cpp",
            "unexpected MPC-03 driver path")
    driver = Path(__file__).resolve().parents[2] / provenance["driver_path"]
    require(driver.is_file() and not driver.is_symlink() and
            provenance.get("driver_sha256") == hashlib.sha256(driver.read_bytes()).hexdigest(),
            "MPC-03 driver provenance hash differs")
    for name in FILES:
        path = source / name
        require(path.is_file() and not path.is_symlink(), "missing or unsafe MPC-03 report asset: " + name)
    canonical_html = render_html(record)
    canonical_svg = render_svg(record)
    require((source / "index.html").read_text(encoding="utf-8") == canonical_html,
            "MPC-03 HTML differs from deterministic saved-record rendering")
    require((source / "disturbance-tube.svg").read_text(encoding="utf-8") == canonical_svg,
            "MPC-03 SVG differs from deterministic saved-record rendering")
    gallery = site / "examples/index.html"
    require(gallery.is_file() and not gallery.is_symlink(), "visual examples gallery is missing")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    require(marker in html or 'id="mpc03-open-loop-pilot-v1"' in html,
            "visual examples gallery insertion point is missing")
    require('id="mpc03-open-loop-pilot-v1"' not in html or CARD in html,
            "MPC-03 gallery route collides with existing content")
    route = site / REPORT_ID
    route.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if name == "index.html":
            (route / name).write_text(canonical_html, encoding="utf-8")
        elif name == "disturbance-tube.svg":
            (route / name).write_text(canonical_svg, encoding="utf-8")
        else:
            shutil.copyfile(source / name, route / name)
    if 'id="mpc03-open-loop-pilot-v1"' not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()

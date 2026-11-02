"""Render the saved MPC-06 exact cost evidence without running analysis."""
from __future__ import annotations

import html
import json
from pathlib import Path
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1"


def render_svg(result: dict) -> str:
    witness = result["objective"]["worst_case_witnesses"][0]
    row = next(path for path in result["vertex_paths"] if path["disturbances"] == witness)
    states = [[float(Fraction(value)) for value in point] for point in row["states"]]

    def project(point, left, top, extent, lo, hi):
        scale = extent / (hi - lo)
        return left + (point[0] - lo) * scale, top + extent - (point[1] - lo) * scale

    world = (80, 85, 390, -1.0, 1.0)
    zoom = (555, 180, 245, -0.32, 0.32)
    tube_vertices = ((1/8, 0), (-1/8, 1/4), (-1/8, 0), (1/8, -1/4))
    def polygon(spec):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in
                        (project(point, *spec) for point in tube_vertices))
    def polyline(spec):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in
                        (project(point, *spec) for point in states))
    markers = []
    labels = []
    colors = ("#f4a261", "#e76f51", "#2a9d8f", "#a78bfa")
    for i, state in enumerate(states):
        x, y = project(state, *zoom)
        markers.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{colors[i]}" stroke="#101923" stroke-width="2"/>')
        labels.append(f'<text x="{x+7:.2f}" y="{y-8:.2f}" class="stage">t={i}</text>')
    wx, wy = project((0, 0), *world)
    zx, zy = project((0, 0), *zoom)
    witness_text = html.escape(", ".join(witness))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 540" role="img" aria-labelledby="title desc">
<title id="title">MPC-06 tube policy: exact worst-case cost</title><desc id="desc">Global state constraint box and zoomed position-velocity trajectory within the exact RPI tube for a maximizing disturbance history.</desc>
<style>text{{font-family:system-ui,sans-serif;fill:#edf4f8}}.title{{font-size:21px;font-weight:700}}.muted{{font-size:13px;fill:#b0c0cc}}.stage{{font-size:12px;font-weight:700}}.axis{{stroke:#b0c0cc;stroke-width:1.4}}.grid{{stroke:#455766;stroke-width:1}}.panel{{fill:#172431;stroke:#324656;stroke-width:1.5}}</style>
<rect width="100%" height="100%" fill="#101923"/><text x="35" y="35" class="title">Fixed tube policy · nominal surrogate 0 · worst actual cost 3/8</text>
<text x="35" y="56" class="muted">Horizon 3 · disturbance witness ({witness_text})</text>
<rect x="{world[0]}" y="{world[1]}" width="{world[2]}" height="{world[2]}" class="panel"/><line x1="{world[0]+world[2]/2}" y1="{world[1]}" x2="{world[0]+world[2]/2}" y2="{world[1]+world[2]}" class="grid"/><line x1="{world[0]}" y1="{world[1]+world[2]/2}" x2="{world[0]+world[2]}" y2="{world[1]+world[2]/2}" class="grid"/>
<polygon points="{polygon(world)}" fill="#56b4e9" fill-opacity=".25" stroke="#56b4e9" stroke-width="2" stroke-dasharray="7 5"/><polyline points="{polyline(world)}" fill="none" stroke="#f4a261" stroke-width="3" stroke-linejoin="round"/><circle cx="{wx}" cy="{wy}" r="4" fill="white"/><text x="{world[0]+8}" y="{world[1]+20}" class="muted">state constraint box [-1,1]²</text>
<line x1="{world[0]}" y1="{world[1]+world[2]}" x2="{world[0]+world[2]}" y2="{world[1]+world[2]}" class="axis"/><line x1="{world[0]}" y1="{world[1]}" x2="{world[0]}" y2="{world[1]+world[2]}" class="axis"/><text x="{world[0]+world[2]/2}" y="{world[1]+world[2]+25}" class="muted" text-anchor="middle">position</text><text x="25" y="{world[1]+world[2]/2}" class="muted" text-anchor="middle" transform="rotate(-90 25 {world[1]+world[2]/2})">velocity</text>
<text x="{zoom[0]}" y="{zoom[1]-16}" class="title" style="font-size:17px">Zoom: RPI tube and worst path</text><rect x="{zoom[0]}" y="{zoom[1]}" width="{zoom[2]}" height="{zoom[2]}" class="panel"/><line x1="{zoom[0]+zoom[2]/2}" y1="{zoom[1]}" x2="{zoom[0]+zoom[2]/2}" y2="{zoom[1]+zoom[2]}" class="grid"/><line x1="{zoom[0]}" y1="{zoom[1]+zoom[2]/2}" x2="{zoom[0]+zoom[2]}" y2="{zoom[1]+zoom[2]/2}" class="grid"/>
<polygon points="{polygon(zoom)}" fill="#56b4e9" fill-opacity=".25" stroke="#56b4e9" stroke-width="2" stroke-dasharray="7 5"/><polyline points="{polyline(zoom)}" fill="none" stroke="#f4a261" stroke-width="3" stroke-linejoin="round"/><circle cx="{zx}" cy="{zy}" r="4" fill="white"/>{''.join(markers)}{''.join(labels)}
<line x1="{zoom[0]}" y1="{zoom[1]+zoom[2]}" x2="{zoom[0]+zoom[2]}" y2="{zoom[1]+zoom[2]}" class="axis"/><line x1="{zoom[0]}" y1="{zoom[1]}" x2="{zoom[0]}" y2="{zoom[1]+zoom[2]}" class="axis"/><text x="{zoom[0]+zoom[2]/2}" y="{zoom[1]+zoom[2]+22}" class="muted" text-anchor="middle">position</text><text x="{zoom[0]-16}" y="{zoom[1]+zoom[2]/2}" class="muted" text-anchor="middle" transform="rotate(-90 {zoom[0]-16} {zoom[1]+zoom[2]/2})">velocity</text>
<line x1="555" y1="478" x2="585" y2="478" stroke="#56b4e9" stroke-width="3" stroke-dasharray="7 5"/><text x="592" y="483" class="muted">exact RPI tube Z</text><line x1="710" y1="478" x2="740" y2="478" stroke="#f4a261" stroke-width="3"/><text x="747" y="483" class="muted">worst-cost path</text><text x="35" y="520" class="muted">White: nominal state z=0. Colored markers: x₀ to x₃. This is a maximizing witness for a fixed policy, not an optimal control.</text>
</svg>'''


def render_html(result: dict) -> str:
    objective = result["objective"]
    witness = html.escape(", ".join(objective["worst_case_witnesses"][0]))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-06 exact tube-policy cost</title><style>:root{{color-scheme:dark;--bg:#101923;--panel:#172431;--ink:#edf4f8;--muted:#b0c0cc;--line:#324656;--accent:#74d0ee}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:clamp(1rem,4vw,3rem)}}h1,h2{{line-height:1.2}}h1{{font-size:clamp(2rem,5vw,3rem)}}h2{{margin-top:2.5rem}}p,li{{max-width:82ch}}a{{color:var(--accent)}}.lede,.muted{{color:var(--muted)}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem 1.25rem;margin:1rem 0}}figure{{margin:1.5rem 0}}figure img{{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:8px}}table{{border-collapse:collapse;width:100%;max-width:950px}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:.55rem .7rem;vertical-align:top}}code{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap}}</style></head><body><main>
<p class="muted">New comparison · exact rational functional evidence · no timing experiment</p><h1>Tube feedback changes cost beyond the nominal surrogate</h1><p class="lede">For one fixed zero nominal plan and exact full-state gain <code>K=[-1,-2]</code>, exact enumeration gives nominal surrogate cost <strong>{html.escape(objective['nominal_surrogate_cost'])}</strong> and continuous-box worst-case actual cost <strong>{html.escape(objective['worst_case_actual_cost'])}</strong>.</p>
<figure><img src="trajectory.svg" alt="Global state constraint box and zoomed position-velocity trajectory inside the exact RPI tube"><figcaption>One maximizing trajectory in the position-velocity plane, shown with the exact RPI tube and state constraint box.</figcaption></figure>
<section class="card"><h2>Model and policy</h2><p><code>x[t+1]=A x[t]+B u[t]+E w[t]</code>, <code>u[t]=v[t]+K(x[t]-z[t])</code>, with <code>v[t]=0</code>, <code>x[0]=z[0]=0</code>, horizon 3, and stagewise independent <code>w[t]∈[-1/8,1/8]</code>. Full state is observed before each input; disturbance enters after the input.</p><p>Cost: <code>sum(t=0..2, ||x[t]||² + u[t]²) + ||x[3]||²</code>. The nominal surrogate evaluates the same expression on <code>z[t],v[t]</code>.</p></section>
<h2>Exact result</h2><table><tbody><tr><th>Nominal surrogate</th><td>{html.escape(objective['nominal_surrogate_cost'])}</td></tr><tr><th>Worst-case actual cost</th><td>{html.escape(objective['worst_case_actual_cost'])}</td></tr><tr><th>Maximizing disturbance</th><td><code>{witness}</code> and its sign reversal</td></tr><tr><th>Safety checks</th><td>{result['coverage']['disturbance_vertices_checked']} of {result['coverage']['expected_vertices']} disturbance vertices; all satisfy state and input bounds</td></tr></tbody></table><p>The cost is a convex quadratic in the stacked disturbance vector. A convex function on a compact box reaches its maximum at a vertex, so this exact rational enumeration establishes the maximum over the continuous disturbance box for this fixed policy.</p>
<h2>Evidence boundary</h2><p>This evaluates one fixed plan and one fixed gain. It does not optimize either, and is not a minimax optimum or globally optimal causal value. No terminal invariance, asymptotic-stability, approximation-family comparison, or performance claim is made. The exact RPI tube is inherited from the separately checked feasibility pilot; its source inputs and result are included as <a href="base-scenario.json">base scenario</a> and <a href="base-result.json">base result</a>.</p>
<h2>Reproduce</h2><pre><code>python scripts/reports/mpc06/build_tube_objective.py
python scripts/reports/mpc06/check_tube_objective.py</code></pre><ul><li><a href="result.json">Exact result</a></li><li><a href="verification.json">Independent verification</a></li><li><a href="scenario.json">Pinned scenario</a></li><li><a href="trajectory.svg">SVG figure</a></li><li><a href="SHA256SUMS">File checksums</a></li></ul><p class="muted">No API, dependency, installation, or release changes. The cost evaluation uses Python standard-library rational arithmetic, not an external solver.</p></main></body></html>'''


def write(result: dict) -> None:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    (BUNDLE / "trajectory.svg").write_text(render_svg(result), encoding="utf-8")
    (BUNDLE / "index.html").write_text(render_html(result), encoding="utf-8")


if __name__ == "__main__":
    write(json.loads((BUNDLE / "result.json").read_text(encoding="utf-8")))

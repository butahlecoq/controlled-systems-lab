#!/usr/bin/env python3
"""Render a saved MPC-06 tube result without invoking an algorithm."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def figure(record: dict) -> tuple[dict, str]:
    support = record["state_tightening_support"]
    state_bounds = [[-1.0, 1.0], [-1.0, 1.0]]
    tightened = record["tightened_state_bounds"]
    generator_radius = record["rpi_generator_radius"]
    # Vertices from the exact zonotope generator coefficients in result.json.
    r = generator_radius
    tube = [[r, 0.0], [-r, r * 2], [-r, 0.0], [r, -r * 2]]
    data = {
        "schema": "csl.mpc06-tube-figure-data/1",
        "sets": {
            "state_box_X": {"bounds": state_bounds, "relation": "exact"},
            "tightened_state_X_minus_Z": {"bounds": tightened, "relation": "exact support tightening"},
            "error_tube_Z": {"vertices": tube, "relation": "exact dyadic zonotope"},
            "input_U": record["input_constraints"],
            "tightened_input_U_minus_KZ": record["tightened_input_bounds"],
        },
        "state_support": support,
        "input_support": record["input_tightening_support"],
    }
    width, height = 1020, 520
    left_x, top, panel_w, panel_h = 75, 65, 510, 360
    right_x, right_w = 690, 250
    scale = panel_w / 2.2
    def sx(value: float) -> float: return left_x + panel_w / 2 + value * scale
    def sy(value: float) -> float: return top + panel_h / 2 - value * scale
    points = " ".join(f"{sx(x):.2f},{sy(v):.2f}" for x, v in tube)
    state = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Exact RPI tube and tightened state and input constraints">',
        '<rect width="100%" height="100%" fill="#111820"/>',
        '<text x="330" y="35" fill="#f4f1e8" text-anchor="middle" font-family="sans-serif" font-size="20">State plane</text>',
        f'<rect x="{sx(-1):.2f}" y="{sy(1):.2f}" width="{2*scale:.2f}" height="{2*scale:.2f}" fill="none" stroke="#a8b3bd" stroke-width="2" stroke-dasharray="8 6"/>',
        f'<rect x="{sx(tightened[0][0]):.2f}" y="{sy(tightened[1][1]):.2f}" width="{(tightened[0][1]-tightened[0][0])*scale:.2f}" height="{(tightened[1][1]-tightened[1][0])*scale:.2f}" fill="#e9c46a" fill-opacity=".25" stroke="#e9c46a" stroke-width="2"/>',
        f'<polygon points="{points}" fill="#56b4e9" fill-opacity=".7" stroke="#8bd3f7" stroke-width="3"/>',
        f'<text x="330" y="455" fill="#f4f1e8" text-anchor="middle" font-family="sans-serif">position</text>',
        f'<text x="25" y="250" fill="#f4f1e8" text-anchor="middle" font-family="sans-serif" transform="rotate(-90 25 250)">velocity</text>',
        '<text x="720" y="55" fill="#f4f1e8" font-family="sans-serif" font-size="20">Input constraint</text>',
    ]
    axis_y = 220
    def ux(value: float) -> float: return right_x + (value + 1.25) / 2.5 * right_w
    state += [
        f'<line x1="{ux(-1):.2f}" y1="{axis_y}" x2="{ux(1):.2f}" y2="{axis_y}" stroke="#a8b3bd" stroke-width="16"/>',
        f'<line x1="{ux(record["tightened_input_bounds"][0]):.2f}" y1="{axis_y}" x2="{ux(record["tightened_input_bounds"][1]):.2f}" y2="{axis_y}" stroke="#e9c46a" stroke-width="16"/>',
        f'<line x1="{ux(0.75):.2f}" y1="150" x2="{ux(0.75):.2f}" y2="290" stroke="#ff6b35" stroke-width="3"/>',
        f'<circle cx="{ux(1.125):.2f}" cy="{axis_y}" r="8" fill="#ff6b35"/>',
        f'<text x="{right_x+right_w/2}" y="250" fill="#f4f1e8" text-anchor="middle" font-family="sans-serif">u: U in gray; U⊖KZ in gold</text>',
        f'<text x="{ux(0.75):.2f}" y="130" fill="#ff9b76" text-anchor="middle" font-family="sans-serif">unsafe nominal v=0.75</text>',
        f'<text x="{ux(1.125):.2f}" y="315" fill="#ff9b76" text-anchor="middle" font-family="sans-serif">actual u=1.125</text>',
        '<g font-family="sans-serif" font-size="14" fill="#f4f1e8">',
        '<rect x="715" y="350" width="16" height="16" fill="none" stroke="#a8b3bd" stroke-width="2"/><text x="740" y="364">state set X</text>',
        '<rect x="715" y="380" width="16" height="16" fill="#e9c46a" fill-opacity=".5"/><text x="740" y="394">tightening X⊖Z</text>',
        '<rect x="715" y="410" width="16" height="16" fill="#56b4e9"/><text x="740" y="424">error tube Z</text>',
        '</g>', '</svg>']
    return data, "\n".join(state) + "\n"


def render(record_path: Path, out: Path) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    figure_data, svg = figure(record)
    out.mkdir(parents=True, exist_ok=True)
    (out / "figure-data.json").write_text(json.dumps(figure_data, indent=2) + "\n", encoding="utf-8")
    (out / "projection.svg").write_text(svg, encoding="utf-8")
    source_commit = html.escape(record.get("source_commit", "uncommitted source"))
    checker_hash = html.escape(record.get("checker_sha256", "not captured"))
    build = record["build"]
    host = record["capture_environment"]
    measurement = record["measurement"]
    state_x = record["tightened_state_bounds"][0]
    state_v = record["tightened_state_bounds"][1]
    input_u = record["tightened_input_bounds"]
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tube MPC exact feasibility pilot</title>
<style>
body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:2rem}}svg{{width:100%;height:auto}}
code{{overflow-wrap:anywhere}}.note{{background:#1a252e;border-left:4px solid #e9c46a;padding:.7rem 1rem}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #53616a;padding:.45rem .65rem;text-align:left}}
th{{background:#1a252e}}
</style><main>
<h1>Exact tube-MPC feasibility pilot</h1>
<p>This small study tests an affine double integrator with full-state feedback and stagewise additive disturbance. The feedback error matrix is nilpotent of index 2, so the finite tube sum has an exact zero tail.</p>
{svg}
<table><caption>Exact feasibility evidence</caption><thead><tr><th>Quantity</th><th>Result</th><th>Evidence</th></tr></thead><tbody>
<tr><td>RPI tube</td><td>Z = D ⊕ FD, generators (0,1) and (1,−1), radius 1/8</td><td>Exact H-relation inclusion verifies (A+BK)Z + EW ⊆ Z</td></tr>
<tr><td>State support and tightening</td><td>hZ(e₁)={record['state_tightening_support'][0]}; hZ(e₂)={record['state_tightening_support'][1]}; X⊖Z=[{state_x[0]},{state_x[1]}] × [{state_v[0]},{state_v[1]}]</td><td>Exact dyadic generator support</td></tr>
<tr><td>Input support and tightening</td><td>hKZ={record['input_tightening_support']}; U⊖KZ=[{input_u[0]},{input_u[1]}]</td><td>Exact dyadic generator support</td></tr>
<tr><td>Zero nominal plan</td><td>Initial tube membership and tightened feasibility established</td><td>Independent rational check</td></tr>
<tr><td>Matched disturbance reference</td><td>{record['matched_reference']['disturbance_paths_checked']} vertex paths; all safe; worst state coordinate {record['matched_reference']['worst_state_coordinate_abs']}; worst feedback input {record['matched_reference']['worst_feedback_input_abs']}</td><td>Exact rational replay for the same fixed plan and feedback law</td></tr>
<tr><td>Edge cases</td><td>Empty state tightening detected; unsafe v=0.75 rejected with actual u=1.125</td><td>Exact support values and dyadic witness</td></tr>
</tbody></table>
<p class="note">Scope: feasibility and safety only. No objective is evaluated; no nominal optimum, minimax cost, general causal optimum, or terminal invariance is claimed. This is one fixed nilpotent profile with continuous inputs and stagewise independent additive disturbance. No outer representation comparison is included; those comparisons remain gated by #99/#100.</p>
<h2>One descriptive timing observation</h2>
<p>{measurement['elapsed_ns']} ns for one {html.escape(build['configuration'])} analysis call (n=1, no warmups; range unavailable for a single run): {html.escape(measurement['scope'])}. Build/setup and JSON serialization are excluded, so this is not end-to-end application latency. Requested/actual workers: {measurement['requested_workers']}/{measurement['actual_workers']}; requested/actual native threads: {measurement['requested_native_threads']}/{measurement['actual_native_threads']} ({html.escape(measurement['parallelism'])}). Assessment: inconclusive; the limiter was not profiled, and no comparison or speed claim is made. The result was verified before reporting (errors: {measurement['errors']}; completed work: {str(measurement['work_completed']).lower()}).</p>
<p>Build: {html.escape(build['compiler_id'])} {html.escape(build['compiler_version'])}, {html.escape(build['configuration'])}; host: {html.escape(host['processor'])}, {html.escape(host['os'])}, {host['logical_cpus']} logical CPUs. Source commit: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source_commit}"><code>{source_commit}</code></a>. Independent checker SHA-256: <code>{checker_hash}</code>.</p>
<h2>Reproduce</h2><pre><code>cmake -S . -B build/mpc06 -DCSL_BUILD_MPC06_REPORT=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/mpc06 --config Release --target csl_mpc06_tube_pilot
python3 scripts/reports/mpc06/check_tube.py build/mpc06/csl_mpc06_tube_pilot</code></pre>
<p><a href="result.json">Saved result</a> · <a href="scenario.json">Complete scenario input</a> · <a href="README.md">Reproduction notes</a> · <a href="figure-data.json">Figure data</a> · <a href="projection.svg">Standalone SVG</a></p>
</main></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    render(args.record, args.out)

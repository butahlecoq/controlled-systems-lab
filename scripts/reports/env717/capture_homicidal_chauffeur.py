#!/usr/bin/env python3
"""Capture and render the finite HomicidalChauffeur reachability/minimax pilot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_homicidal_chauffeur as checker

SCENARIO = ROOT / "benchmarks/scenarios/env717-homicidal-chauffeur-pilot-v1.json"
DRIVER_SOURCE = ROOT / "benchmarks/reporting/env717/homicidal_chauffeur.cpp"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def convex_hull(points):
    points = sorted(set((float(point[0]), float(point[1])) for point in points))
    if len(points) <= 1:
        return points

    def cross(origin, a, b):
        return ((a[0] - origin[0]) * (b[1] - origin[1]) -
                (a[1] - origin[1]) * (b[0] - origin[0]))

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def project_layers(result):
    projections = []
    for name, desc, x_index, y_index, x_label, y_label in (
            ("pursuer-position-plane", "Pursuer position plane", 0, 1,
             "pursuer x position", "pursuer y position"),
            ("evader-position-plane", "Evader position plane", 3, 4,
             "evader x position", "evader y position")):
        layers = []
        for layer in result["figure_layers"]:
            forward = [[state["state"][x_index], state["state"][y_index]]
                       for state in layer["forward_states"]]
            winning = [[state["state"][x_index], state["state"][y_index]]
                       for state in layer["backward_winning_intersection"]]
            layers.append({"stage": layer["stage"], "time_seconds": layer["time_seconds"],
                "forward": forward, "forward_convex_envelope": convex_hull(forward),
                "winning_intersection": winning})
        terminal = result["figure_layers"][-1]["forward_states"]
        target = [[state["state"][x_index], state["state"][y_index]] for state in terminal
                  if math_distance(state["state"]) <= result["adaptation"]["target_radius"]]
        trajectory = [[row["state"][x_index], row["state"][y_index]]
                      for row in result["minimax_trajectory"]]
        projections.append({"name": name, "description": desc,
            "x_label": x_label, "y_label": y_label, "layers": layers,
            "terminal_target_projection": target, "minimax_trajectory": trajectory})
    return {"schema": "csl.env717-homicidal-chauffeur-figure/1",
        "projections": projections,
        "state_space": "5D physical state (pursuer x/y/heading and evader x/y); source time is represented by stages",
        "envelope_note": "filled polygons are convex hulls of projected finite states and are visual envelopes, not exact projected reachable sets"}


def math_distance(state):
    import math
    return math.hypot(state[0] - state[3], state[1] - state[4])


def svg_figure(data):
    width, height = 1280, 660
    colors = ["#74859a", "#5383b5", "#479b89", "#dc9144", "#9a5b8f"]
    panels = []
    for panel_id, projection in enumerate(data["projections"]):
        left, top, plot_width, plot_height = 82 + panel_id * 610, 84, 520, 470
        points = [point for layer in projection["layers"]
                  for group in (layer["forward"], layer["winning_intersection"])
                  for point in group]
        points += projection["minimax_trajectory"] + projection["terminal_target_projection"]
        xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
        ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
        xpad, ypad = max((xmax - xmin) * 0.08, 0.15), max((ymax - ymin) * 0.08, 0.15)
        xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad

        def xy(point):
            return (left + (point[0] - xmin) * plot_width / (xmax - xmin),
                    top + plot_height - (point[1] - ymin) * plot_height / (ymax - ymin))

        panels.append(f'<text x="{left + plot_width/2}" y="34" text-anchor="middle" class="title">{html.escape(projection["description"])}</text>')
        panels.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" class="frame"/>')
        for layer in projection["layers"]:
            color = colors[layer["stage"] % len(colors)]
            hull = [xy(point) for point in layer["forward_convex_envelope"]]
            if len(hull) >= 3:
                points_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in hull)
                panels.append(f'<polygon points="{points_text}" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-opacity="0.45" stroke-width="1" data-role="projected-convex-envelope"/>')
            for point in layer["forward"]:
                x, y = xy(point)
                panels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="{color}" opacity="0.78"/>')
            for point in layer["winning_intersection"]:
                x, y = xy(point)
                panels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="none" stroke="#b92e2e" stroke-width="1.25" data-role="winning-intersection"/>')
        for point in projection["terminal_target_projection"]:
            x, y = xy(point)
            panels.append(f'<path d="M {x:.2f} {y-6:.2f} L {x+6:.2f} {y:.2f} L {x:.2f} {y+6:.2f} L {x-6:.2f} {y:.2f} Z" class="target" data-role="terminal-target"/>')
        trajectory = [xy(point) for point in projection["minimax_trajectory"]]
        panels.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x,y in trajectory) + '" class="path"/>')
        for stage, (x, y) in enumerate(trajectory):
            panels.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="path-point"/><text x="{x+7:.1f}" y="{y-7:.1f}" class="stage">{stage}</text>')
        panels.append(f'<text x="{left+plot_width/2}" y="{top+plot_height+45}" text-anchor="middle">{html.escape(projection["x_label"])}</text>')
        panels.append(f'<text x="{left-48}" y="{top+plot_height/2}" text-anchor="middle" transform="rotate(-90 {left-48} {top+plot_height/2})">{html.escape(projection["y_label"])}</text>')
        panels.append(f'<text x="{left}" y="{top+plot_height+23}" class="tick">{xmin:.3g}</text><text x="{left+plot_width}" y="{top+plot_height+23}" text-anchor="end" class="tick">{xmax:.3g}</text>')
    legend = ('<g transform="translate(80,620)"><circle cx="0" cy="0" r="4" fill="#5383b5"/><text x="9" y="4">forward finite states by stage</text>'
        '<polygon points="270,-5 280,-5 285,0 280,5 270,5 265,0" fill="#5383b5" fill-opacity="0.18" stroke="#5383b5"/><text x="292" y="4">convex envelope of projected states</text>'
        '<circle cx="575" cy="0" r="4" fill="none" stroke="#b92e2e" stroke-width="1.25"/><text x="584" y="4">forward ∩ backward-winning</text>'
        '<line x1="830" y1="0" x2="860" y2="0" class="path"/><text x="870" y="4">selected worst-case minimax path</text>'
        '<path d="M 1120,-5 L 1125,0 L 1120,5 L 1115,0 Z" class="target"/><text x="1134" y="4">target</text></g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 660" role="img" aria-labelledby="title desc">'
        '<title id="title">HomicidalChauffeur projected reachable and winning sets</title>'
        '<desc id="desc">Pursuer and evader position projections show finite forward states by stage, visual convex envelopes, backward-winning intersections, terminal target states and the selected worst-case path.</desc>'
        '<rect width="1280" height="660" fill="#fff"/><style>text{font:14px system-ui,sans-serif;fill:#172033}.title{font-size:19px;font-weight:600}.frame{fill:#fff;stroke:#8493a5}.target{fill:none;stroke:#9a6711;stroke-width:1.6}.path{fill:none;stroke:#252e38;stroke-width:3}.path-point{fill:#e4572e;stroke:#fff;stroke-width:1.5}.stage{font-size:11px;font-weight:bold}.tick{font-size:11px;fill:#596779}</style>'
        + ''.join(panels) + legend + '</svg>')


def make_page(result, check, capture):
    path = result["minimax_trajectory"]
    actions = " → ".join(f"u={row['turn_rate']:g}, v={row['evader_heading']:.3g}" for row in path[:-1])
    counts = ", ".join(str(value) for value in result["graph_state_counts"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HomicidalChauffeur: finite reachability and minimax</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:78rem;margin:auto;padding:1.2rem;color:#172033}}img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd3dc;padding:.4rem .7rem;text-align:left}}.note{{background:#f4f6f8;padding:.8rem 1rem;border-left:4px solid #55718f}}.quiet{{color:#536273}}</style></head>
<body><h1>HomicidalChauffeur: finite reachability and minimax</h1>
<p>This report applies our finite-feedback reachability and causal minimax solvers to a source-derived pursuit-evasion game. Its physical state is five-dimensional: pursuer position and heading, plus evader position. Source time is represented by the stage index.</p>
<figure><img src="projections.svg" alt="Pursuer and evader position projections showing finite reachable states, projected convex envelopes, backward-winning intersections, the terminal target, and a selected minimax path"><figcaption>Panels show the pursuer and evader position planes. Dots are projected finite graph states. Light polygons are convex hulls of those projected points for visual orientation; they are not exact projections of the five-dimensional reachable sets. Red rings mark graph states that are both forward reachable and backward winning.</figcaption></figure>
<h2>Finite pilot results</h2><table><tbody><tr><th>Forward graph states by stage</th><td>{html.escape(counts)}</td></tr>
<tr><th>First robust terminal capture (distance ≤ 7.8)</th><td>{result['first_robust_capture_steps']} decisions ({result['first_robust_capture_steps'] * 0.1:.1f} s)</td></tr>
<tr><th>Finite causal minimax terminal separation</th><td>{result['finite_causal_minimax_terminal_separation']:.9f}</td></tr>
<tr><th>Selected pursuer turn-rate / evader heading path</th><td>{html.escape(actions)}</td></tr>
<tr><th>Independent replay</th><td>{check['status']}: {check['forward_states_checked']} states and {check['transition_cells_checked']} transition cells</td></tr></tbody></table>
<h2>Source model and finite adaptation</h2><p>The pinned source state is <code>(time, pursuer_x, pursuer_y, pursuer_heading, evader_x, evader_y)</code>. The pursuer travels at speed 3 with bounded turn rate <code>u ∈ [-1,1]</code>; the evader travels at speed 1 with heading <code>v ∈ [0,2π]</code>. Both use 0.1-second decisions and ten held-action RK4 substeps per decision. The source returns positive terminal Euclidean separation but does not specify separate payoff signs for the two agents.</p>
<p>This pilot uses the source default initial state, but shortens the horizon from 4.0 seconds to 0.4 seconds and samples the continuous actions as <code>u ∈ {{-1,0,1}}</code> and four cardinal evader headings. The capture set is an explicit analysis choice: terminal separation ≤ 7.8. The finite causal solver lets the evader observe the current pursuer turn rate before responding. The zero-sum interpretation (pursuer minimizes, evader maximizes) is an explicit analysis assumption, as are the finite actions and sequential response. The results describe this quantized finite game and do not reproduce continuous-action RL training or establish continuous-game optimality.</p>
<p>Source: <a href="https://github.com/imm-rl-lab/differential_game_gym/tree/af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8/Environments/HomicidalChauffeur">HomicidalChauffeur at pinned commit</a>, source blob <code>{result['source']['file_blob']}</code>, Apache-2.0 at that commit. Scenario SHA-256: <code>{result['scenario_sha256']}</code>.</p>
<h2>Reproduction and saved evidence</h2><p>Configure with <code>cmake -S . -B build/report -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release</code>, build <code>csl_env717_homicidal_chauffeur</code>, then run <code>python scripts/reports/env717/capture_homicidal_chauffeur.py build/report/csl_env717_homicidal_chauffeur --output reports/algorithm-results/env717-homicidal-chauffeur-v1</code>. The checker independently rebuilds all RK4 transitions, verifies each reachable layer, recomputes backward winning sets and finite minimax values, and checks the selected worst-case trajectory.</p>
<p class="quiet">No runtime or performance comparison was measured. <a href="result.json">Raw result</a> · <a href="figure-data.json">Figure data</a> · <a href="check.json">Independent check</a> · <a href="capture.json">Capture metadata</a> · <a href="README.md">Reproduction notes</a>.</p>
</body></html>'''


def capture(driver: Path, destination: Path):
    if destination.exists():
        raise ValueError("capture destination already exists")
    completed = subprocess.run([str(driver)], capture_output=True, text=True, timeout=120, check=True)
    result = json.loads(completed.stdout)
    check = checker.verify(result)
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if result["scenario_sha256"] != digest(SCENARIO.read_bytes()):
        raise ValueError("driver scenario hash differs from the reviewed scenario")
    if (scenario["source"]["commit"] != result["source"]["repository_commit"] or
            scenario["source"]["blob"] != result["source"]["file_blob"] or
            scenario["adaptation"]["turn_rate_catalogue"] != result["adaptation"]["turn_rate_catalogue"] or
            scenario["adaptation"]["evader_heading_catalogue_radians"] != result["adaptation"]["evader_heading_catalogue_radians"] or
            scenario["adaptation"]["objective_orientation"] != result["adaptation"]["objective_orientation"] or
            scenario["adaptation"]["information_pattern"] != result["adaptation"]["information_pattern"] or
            scenario["adaptation"]["horizon_steps"] != result["adaptation"]["horizon_steps"] or
            scenario["adaptation"]["state_quantization_scale"] != result["adaptation"]["state_quantization_scale"] or
            scenario["adaptation"]["reachability_target"] !=
            f"terminal Euclidean pursuer-evader distance <= {result['adaptation']['target_radius']}"):
        raise ValueError("scenario source or finite action catalog differs from the executable")
    if result["build"]["driver_sha256"] != digest(DRIVER_SOURCE.read_bytes()):
        raise ValueError("built driver source hash differs")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    if result["build"]["source_commit"] != head:
        raise ValueError("capture must use the current committed source head")
    destination.mkdir(parents=True)
    capture_record = {
        "schema": "csl.env717-homicidal-chauffeur-capture/1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": head, "driver_source_sha256": digest(DRIVER_SOURCE.read_bytes()),
        "scenario_sha256": digest(SCENARIO.read_bytes()),
        "algorithm_source_sha256": result["build"]["algorithm_source_sha256"],
        "executable_sha256": digest(driver.read_bytes()), "compiler": result["build"],
        "build_type": result["build"]["build_type"], "operating_system": platform.platform(),
        "machine": platform.machine(), "python": platform.python_version(),
        "command": "csl_env717_homicidal_chauffeur",
        "timing_claim": "none; report records finite game values and independently checked graph only",
        "solver_failures": 0,
    }
    figure = project_layers(result)
    files = {
        "result.json": json.dumps(result, indent=2, sort_keys=True) + "\n",
        "check.json": json.dumps(check, indent=2, sort_keys=True) + "\n",
        "figure-data.json": json.dumps(figure, indent=2, sort_keys=True) + "\n",
        "projections.svg": svg_figure(figure) + "\n",
        "capture.json": json.dumps(capture_record, indent=2, sort_keys=True) + "\n",
        "index.html": make_page(result, check, capture_record),
        "scenario.json": json.dumps(scenario, indent=2, sort_keys=True) + "\n",
        "README.md": """# HomicidalChauffeur finite reachability/minimax pilot

This source-attributed report applies CSL finite-feedback reachability and causal minimax to a bounded finite action catalogue and four 0.1-second stages. It does not reproduce the continuous-action RL outcome. The source, scenario, executable, complete reachable graph and independent replay are identified in the saved records.

Reproduce with `cmake -S . -B build/report -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, `cmake --build build/report --target csl_env717_homicidal_chauffeur`, then `python scripts/reports/env717/capture_homicidal_chauffeur.py build/report/csl_env717_homicidal_chauffeur --output reports/algorithm-results/env717-homicidal-chauffeur-v1`.

The independent checker reconstructs all quantized RK4 transitions, forward reachable states, backward capture sets, finite minimax values and the selected worst-case path. The zero-sum signs are an analysis assumption because the source returns positive separation without assigning separate payoffs. The plotted polygons are convex envelopes of projected graph states and are visual guides, not exact projected reachable sets. No timing or performance comparison is reported.
""",
    }
    for name, content in files.items():
        (destination / name).write_text(content, encoding="utf-8")
    sums = "".join(f"{digest((destination/name).read_bytes())}  {name}\n" for name in sorted(files))
    (destination / "SHA256SUMS").write_text(sums, encoding="ascii")
    return {"result": result, "check": check, "capture": capture_record,
            "files": sorted([*files, "SHA256SUMS"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.driver.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()

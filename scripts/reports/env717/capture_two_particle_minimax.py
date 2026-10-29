#!/usr/bin/env python3
"""Capture and render the verified finite TwoParticleGame pilot."""

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
import check_two_particle_minimax as checker

SCENARIO = ROOT / "benchmarks/scenarios/env717-two-particle-game-pilot-v1.json"
DRIVER_SOURCE = ROOT / "benchmarks/reporting/env717/two_particle_minimax.cpp"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def project_layers(result):
    projection_specs = [
        ("particle-1-phase-plane", "particle 1 phase plane", 0, 1,
            "x₁ position", "x₂ velocity"),
        ("particle-2-phase-plane", "particle 2 phase plane", 2, 3,
            "x₃ position", "x₄ velocity"),
    ]
    projections = []
    for name, description, x_index, y_index, x_label, y_label in projection_specs:
        layers = []
        for layer in result["figure_layers"]:
            layers.append({
                "stage": layer["stage"],
                "time_seconds": layer["time_seconds"],
                "forward": [[state["state"][x_index], state["state"][y_index]]
                            for state in layer["forward_states"]],
                "winning_intersection": [[state["state"][x_index], state["state"][y_index]]
                                          for state in layer["backward_winning_intersection"]],
            })
        trajectory = [[row["state"][x_index], row["state"][y_index]]
                      for row in result["minimax_trajectory"]]
        target_states = [state["state"] for state in result["figure_layers"][-1]["forward_states"]
                         if abs(state["state"][0] - state["state"][2]) <= result["target"]["radius"]]
        target_projection = [[state[x_index], state[y_index]] for state in target_states]
        projections.append({"name": name, "description": description,
            "x_label": x_label, "y_label": y_label,
            "target_projection": target_projection,
            "layers": layers, "minimax_trajectory": trajectory})
    return {"schema": "csl.env717-two-particle-figure/1", "projections": projections,
            "target": result["target"], "state_space": "4D finite quantized graph; points are projected graph states"}


def svg_figure(data) -> str:
    width, height = 1280, 620
    colors = ["#778da9", "#5383b5", "#479b89", "#dc9144", "#9a5b8f"]
    panels = []
    for panel_id, projection in enumerate(data["projections"]):
        left = 78 + panel_id * 610
        top, plot_width, plot_height = 86, 520, 440
        points = [point for layer in projection["layers"]
                  for group in (layer["forward"], layer["winning_intersection"])
                  for point in group]
        points += projection["minimax_trajectory"] + projection["target_projection"]
        if not points:
            raise ValueError("projection has no points")
        xmin = min(point[0] for point in points)
        xmax = max(point[0] for point in points)
        ymin = min(point[1] for point in points)
        ymax = max(point[1] for point in points)
        xpad = max((xmax - xmin) * 0.08, 0.15)
        ypad = max((ymax - ymin) * 0.08, 0.15)
        xmin, xmax = xmin - xpad, xmax + xpad
        ymin, ymax = ymin - ypad, ymax + ypad

        def xy(point):
            return (left + (point[0] - xmin) * plot_width / (xmax - xmin),
                    top + plot_height - (point[1] - ymin) * plot_height / (ymax - ymin))

        title = html.escape(projection["description"])
        x_label = html.escape(projection["x_label"])
        y_label = html.escape(projection["y_label"])
        panels.append(f'<text x="{left + plot_width / 2}" y="34" text-anchor="middle" class="title">{title}</text>')
        panels.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" class="frame"/>')
        for point in projection["target_projection"]:
            x, y = xy(point)
            panels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.0" class="target"/>')
        for layer in projection["layers"]:
            color = colors[layer["stage"] % len(colors)]
            for point in layer["forward"]:
                x, y = xy(point)
                panels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.7" fill="{color}" opacity="0.82"/>')
            for point in layer["winning_intersection"]:
                x, y = xy(point)
                panels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.0" fill="none" stroke="#b92e2e" stroke-width="1.25" opacity="0.9"/>')
        trajectory = [xy(point) for point in projection["minimax_trajectory"]]
        panels.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in trajectory) + '" class="path"/>')
        for index, (x, y) in enumerate(trajectory):
            panels.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="path-point"/>')
            panels.append(f'<text x="{x + 7:.1f}" y="{y - 7:.1f}" class="stage">{index}</text>')
        panels.append(f'<text x="{left + plot_width / 2}" y="{top + plot_height + 48}" text-anchor="middle">{x_label}</text>')
        panels.append(f'<text x="{left - 48}" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 {left - 48} {top + plot_height / 2})">{y_label}</text>')
        panels.append(f'<text x="{left}" y="{top + plot_height + 25}" class="tick">{xmin:.3g}</text>')
        panels.append(f'<text x="{left + plot_width}" y="{top + plot_height + 25}" text-anchor="end" class="tick">{xmax:.3g}</text>')
    legend = ('<g transform="translate(80,584)"><circle cx="0" cy="0" r="4" fill="#5383b5"/><text x="9" y="4">forward graph states (stage colors)</text>'
        '<circle cx="270" cy="0" r="4" fill="none" stroke="#b92e2e" stroke-width="1.25"/><text x="279" y="4">backward-winning ∩ forward states</text>'
        '<line x1="560" y1="0" x2="590" y2="0" class="path"/><text x="600" y="4">selected worst-case minimax path</text>'
        '<circle cx="920" cy="0" r="4" class="target"/><text x="930" y="4">projected terminal target states</text></g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 620" role="img" aria-labelledby="title desc">'
        '<title id="title">TwoParticleGame reachable and winning states</title>'
        '<desc id="desc">Forward finite-state graph nodes, backward-winning intersections, projected terminal target states, and a selected worst-case minimax path in each particle phase plane.</desc>'
        '<rect width="1280" height="620" fill="#fff"/>'
        '<style>text{font:14px system-ui,sans-serif;fill:#172033}.title{font-size:19px;font-weight:600}.frame{fill:#fff;stroke:#8493a5}.target{fill:#f6d58b;fill-opacity:.9;stroke:#9a6711;stroke-width:1.5}.path{fill:none;stroke:#252e38;stroke-width:3}.path-point{fill:#e4572e;stroke:#fff;stroke-width:1.5}.stage{font-size:11px;font-weight:bold}.tick{font-size:11px;fill:#596779}</style>'
        + ''.join(panels) + legend + '</svg>')


def make_page(result, check, capture):
    trajectory = result["minimax_trajectory"]
    steps = " → ".join(f"u={step['control']:g}, v={step['disturbance']:g}"
                        for step in trajectory[:-1])
    counts = ", ".join(str(value) for value in result["graph_state_counts"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwoParticleGame: finite reachability and minimax</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:78rem;margin:auto;padding:1.2rem;color:#172033}}img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd3dc;padding:.4rem .7rem;text-align:left}}.note{{background:#f4f6f8;padding:.8rem 1rem;border-left:4px solid #55718f}}.quiet{{color:#536273}}</style></head>
<body><h1>TwoParticleGame: finite reachability and minimax</h1>
<p>This example applies our finite-feedback reachability and causal minimax solvers to the source-derived two-particle game. The finite game has four physical state coordinates and a short four-stage horizon.</p>
<figure><img src="projections.svg" alt="Forward graph states, backward-winning intersections, projected terminal target states, and minimax path in particle phase planes x1-x2 and x3-x4"><figcaption>Panels show particle 1's (x₁,x₂) phase plane and particle 2's (x₃,x₄) phase plane. Gold points are projections of full states in the terminal target; projected graph nodes are points, not convex hulls. Stage colors distinguish time layers, and red points are both forward reachable and backward winning.</figcaption></figure>
<h2>Result</h2><table><tbody><tr><th>Forward graph states by stage</th><td>{html.escape(counts)}</td></tr>
<tr><th>First robust capture of |x₁−x₂| ≤ 1</th><td>{result['first_robust_capture_steps']} decisions ({result['first_robust_capture_steps'] * 0.2:.1f} s)</td></tr>
<tr><th>Finite causal minimax terminal gap</th><td>{result['finite_causal_minimax_terminal_gap']:.6f}</td></tr>
<tr><th>Selected minimizing-control / worst-response path</th><td>{html.escape(steps)}</td></tr>
<tr><th>Independent replay</th><td>{check['status']}: {check['forward_states_checked']} states, {check['transition_cells_checked']} transition cells, {check['backward_layers_checked']} winning layers</td></tr></tbody></table>
<h2>Source model and adaptation</h2><p>The source environment uses state <code>(t,x₁,v₁,x₂,v₂)</code>, parameters α=1, m₁=0.1, m₂=1, 0.2-second decisions, and 20 held-action RK4 substeps. Its terminal reward is <code>−|x₁−x₂|</code>; accordingly, u minimizes the terminal gap and v maximizes it. This pilot changes the source initial state from all zeros to <code>(0,2,0,0,0)</code>, truncates the 2-second source horizon to 0.8 seconds, and uses action catalogues <code>{html.escape(str(result['adaptation']['action_catalogue']))}</code>.</p>
<p class="note">The upstream Markov game supplies both agents' actions at a step. Our finite causal solver gives the disturbance player v the stronger within-stage information pattern: v sees u before responding. State values and policies are for this finite, quantized game; they do not reproduce or estimate the continuous-action RL outcome. The graph rounds each RK4 stage state to a 10⁻⁶ lattice and solves only states reachable from the selected initial point.</p>
<p>Source: <a href="https://github.com/imm-rl-lab/differential_game_gym/tree/af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8/Environments/TwoParticleGame">TwoParticleGame at pinned commit</a>, source blob <code>{result['source']['file_blob']}</code>, licensed Apache-2.0 at that commit. Scenario SHA-256: <code>{result['scenario_sha256']}</code>.</p>
<h2>Reproduction and evidence</h2><p>Build the optional report driver with <code>CSL_BUILD_ENV717_REPORT=ON</code>, run <code>csl_env717_two_particle_minimax</code>, and independently check it with <code>python scripts/reports/env717/check_two_particle_minimax.py DRIVER</code>. The raw result, scenario, independent check, figure data, build identity, and checksums are included with the report files.</p>
<p class="quiet">This is an illustrative finite game result, not a performance comparison. No speedup or continuous-game guarantee is claimed.</p>
<p>Capture: <code>{html.escape(capture['captured_at_utc'])}</code>; source commit <code>{result['source_commit']}</code>; executable SHA-256 <code>{capture['executable_sha256']}</code>.</p>
<p><a href="result.json">Raw result</a> · <a href="figure-data.json">Figure data</a> · <a href="check.json">Independent check</a> · <a href="capture.json">Capture metadata</a> · <a href="README.md">Reproduction notes</a></p>
</body></html>'''


def capture(driver: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("capture destination already exists")
    completed = subprocess.run([str(driver)], capture_output=True, text=True, timeout=120, check=True)
    result = json.loads(completed.stdout)
    check = checker.verify(result)
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if result["scenario_sha256"] != digest(SCENARIO.read_bytes()):
        raise ValueError("driver scenario hash does not match the reviewed scenario file")
    if (scenario["source"]["commit"] != result["source"]["repository_commit"] or
            scenario["source"]["blob"] != result["source"]["file_blob"] or
            scenario["adaptation"]["action_catalogue"] != result["adaptation"]["action_catalogue"] or
            scenario["adaptation"]["disturbance_catalogue"] != result["adaptation"]["disturbance_catalogue"] or
            scenario["adaptation"]["objective_orientation"] != result["adaptation"]["objective_orientation"]):
        raise ValueError("scenario metadata differs from the executable game request")
    if result["driver_sha256"] != digest(DRIVER_SOURCE.read_bytes()):
        raise ValueError("driver source hash differs from the built driver's source identity")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    if result["source_commit"] != head:
        raise ValueError("capture must be built from the current committed source head")
    destination.mkdir(parents=True)
    executable_sha = digest(driver.read_bytes())
    capture_record = {
        "schema": "csl.env717-two-particle-capture/1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": head,
        "driver_source_sha256": digest(DRIVER_SOURCE.read_bytes()),
        "scenario_sha256": digest(SCENARIO.read_bytes()),
        "algorithm_source_sha256": result["algorithm_source_sha256"],
        "executable_sha256": executable_sha,
        "compiler": result["build"],
        "build_type": result["build"]["build_type"],
        "operating_system": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "command": "csl_env717_two_particle_minimax",
        "timing_claim": "none; report records game values and checked state graph only",
        "solver_failures": 0,
    }
    figure_data = project_layers(result)
    files = {
        "result.json": json.dumps(result, indent=2, sort_keys=True) + "\n",
        "check.json": json.dumps(check, indent=2, sort_keys=True) + "\n",
        "figure-data.json": json.dumps(figure_data, indent=2, sort_keys=True) + "\n",
        "projections.svg": svg_figure(figure_data) + "\n",
        "capture.json": json.dumps(capture_record, indent=2, sort_keys=True) + "\n",
        "index.html": make_page(result, check, capture_record),
        "scenario.json": json.dumps(scenario, indent=2, sort_keys=True) + "\n",
        "README.md": (
            "# TwoParticleGame finite reachability/minimax pilot\n\n"
            "This is a source-derived finite-game example, not a continuous-action RL replay. "
            "The source commit, scenario, driver, executable, state graph, and independent replay are identified in the adjacent JSON records.\n\n"
            "Reproduce with `cmake -S . -B build/report -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, "
            "`cmake --build build/report --target csl_env717_two_particle_minimax`, then run "
            "`python scripts/reports/env717/check_two_particle_minimax.py build/report/csl_env717_two_particle_minimax`.\n\n"
            "The independent checker rebuilds the quantized RK4 graph, verifies every reachable state and transition, recomputes backward capture sets and dynamic minimax values, and replays the selected worst-case path. The report makes no timing or speedup claim.\n"
        ),
    }
    for name, contents in files.items():
        (destination / name).write_text(contents, encoding="utf-8")
    sums = "".join(f"{digest((destination / name).read_bytes())}  {name}\n"
                   for name in sorted(files))
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

#!/usr/bin/env python3
"""Independently replay the finite-catalogue TimeOptimalSphereGame report."""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import platform
from pathlib import Path
import subprocess
import sys

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "fd7709a6f8e4196665d36b4ac5d348173599c250"
INITIAL = (2_000_000, -1_000_000, -1)
SCALE = 1_000_000
INNER_STEPS = 10
HORIZON = 35
CATALOGUE = (-1, 0, 1)
DT = 0.01


def in_target(state: tuple[int, int, int]) -> bool:
    x, y, _ = state
    return x * x + y * y <= SCALE * SCALE


def advance_source(state: tuple[int, int, int], control: int, disturbance: int,
                   stage: int, collect_samples: bool = False) -> tuple[tuple[int, int, int], int, list[tuple[int, int]]]:
    x, y, captured_at = state
    samples = [(x, y)] if collect_samples else []
    if captured_at >= 0:
        return state, 0, samples
    if in_target(state):
        return (x, y, stage * INNER_STEPS), 0, samples
    for elapsed in range(1, INNER_STEPS + 1):
        numerator = state[1] + disturbance * SCALE
        assert numerator % 100 == 0 and state[1] % 100 == 0
        x = state[0] + elapsed * numerator // 100
        x += control * 50 * elapsed * (elapsed - 1)
        y = state[1] + control * (SCALE // 100) * elapsed
        if collect_samples:
            samples.append((x, y))
        if x * x + y * y <= SCALE * SCALE:
            return (x, y, stage * INNER_STEPS + elapsed), elapsed, samples
    return (x, y, -1), INNER_STEPS, samples


def build_graph() -> tuple[list[list[tuple[int, int, int]]], list[array]]:
    layers = [[INITIAL]]
    destinations: list[array] = []
    for stage in range(HORIZON):
        next_states: list[tuple[int, int, int]] = []
        next_ids: dict[tuple[int, int, int], int] = {}
        stage_destinations = array("I")
        for state in layers[-1]:
            for control in CATALOGUE:
                for disturbance in CATALOGUE:
                    successor, _, _ = advance_source(state, control, disturbance, stage)
                    destination = next_ids.get(successor)
                    if destination is None:
                        destination = len(next_states)
                        next_ids[successor] = destination
                        next_states.append(successor)
                    stage_destinations.append(destination)
                    if len(next_states) >= 2**32:
                        raise ValueError("fixture state catalogue exceeds the independent checker index type")
        layers.append(next_states)
        destinations.append(stage_destinations)
    return layers, destinations


def minimum_capture_steps(layers: list[list[tuple[int, int, int]]],
                          destinations: list[array]) -> list[list[int | None]]:
    """Compute the independent min-max number of remaining decisions to capture."""
    steps: list[list[int | None]] = [[] for _ in range(HORIZON + 1)]
    steps[-1] = [0 if state[2] >= 0 else None for state in layers[-1]]
    for stage in range(HORIZON - 1, -1, -1):
        row: list[int | None] = []
        for state_id, state in enumerate(layers[stage]):
            if state[2] >= 0:
                row.append(0)
                continue
            best = None
            for action in range(len(CATALOGUE)):
                branch = [steps[stage + 1][destinations[stage][state_id * 9 + action * 3 + disturbance]]
                          for disturbance in range(len(CATALOGUE))]
                if all(value is not None for value in branch):
                    candidate = 1 + max(branch)
                    if best is None or candidate < best:
                        best = candidate
            row.append(best)
        steps[stage] = row
    return steps


def solve_minimax(layers: list[list[tuple[int, int, int]]], destinations: list[array]) -> tuple[list[list[float | None]], list[list[list[int]]]]:
    values: list[list[float | None]] = [[] for _ in range(HORIZON + 1)]
    terminal = layers[-1]
    values[-1] = [state[2] * DT if state[2] >= 0 else None for state in terminal]
    optimal: list[list[list[int]]] = [[] for _ in range(HORIZON)]
    for stage in range(HORIZON - 1, -1, -1):
        stage_values: list[float | None] = []
        stage_optimal: list[list[int]] = []
        for state_id in range(len(layers[stage])):
            action_values: list[float | None] = []
            for action in range(len(CATALOGUE)):
                offset = state_id * 9 + action * 3
                branch_values = [values[stage + 1][destinations[stage][offset + disturbance]]
                                 for disturbance in range(len(CATALOGUE))]
                action_values.append(max(branch_values) if all(value is not None for value in branch_values) else None)
            feasible = [value for value in action_values if value is not None]
            if feasible:
                best = min(feasible)
                actions = [index for index, value in enumerate(action_values) if value == best]
                stage_values.append(best)
                stage_optimal.append(actions)
            else:
                stage_values.append(None)
                stage_optimal.append([])
        values[stage], optimal[stage] = stage_values, stage_optimal
    return values, optimal


def replay_worst_case(layers, destinations, values, optimal):
    current = 0
    samples = [(layers[0][0][0], layers[0][0][1])]
    controls, disturbances, stage_states = [], [], [list(layers[0][0])]
    for stage in range(HORIZON):
        state = layers[stage][current]
        if state[2] >= 0:
            break
        actions = optimal[stage][current]
        assert actions
        action = actions[0]
        offset = current * 9 + action * 3
        branch_values = [values[stage + 1][destinations[stage][offset + disturbance]]
                         for disturbance in range(len(CATALOGUE))]
        assert all(value is not None for value in branch_values)
        disturbance = max(range(len(CATALOGUE)), key=lambda i: branch_values[i])
        controls.append(CATALOGUE[action])
        disturbances.append(CATALOGUE[disturbance])
        successor, _, micro_samples = advance_source(
            state, CATALOGUE[action], CATALOGUE[disturbance], stage, collect_samples=True)
        samples.extend(micro_samples[1:])
        current = destinations[stage][offset + disturbance]
        stage_states.append(list(layers[stage + 1][current]))
        assert layers[stage + 1][current] == successor
    final_state = tuple(stage_states[-1])
    assert final_state[2] >= 0
    return {"microstep_positions_ticks": [list(p) for p in samples],
            "stage_states": stage_states,
            "control_actions": controls,
            "disturbance_actions": disturbances,
            "capture_inner_step": final_state[2],
            "capture_time_seconds": final_state[2] * DT}


def figure_layers(layers, steps):
    output = []
    for stage, states in enumerate(layers):
        forward = sorted({(state[0], state[1]) for state in states})
        wins = sorted({(state[0], state[1]) for state_id, state in enumerate(states)
                       if steps[stage][state_id] is not None and steps[stage][state_id] <= HORIZON - stage})
        output.append({"stage": stage, "elapsed_seconds": stage * 0.1,
                       "forward_positions_ticks": [list(p) for p in forward],
                       "winning_positions_ticks": [list(p) for p in wins]})
    return output


def verify(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-time-sphere-minimax/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    assert actual["source_model"]["initial_state"] == [2.0, -1.0]
    assert actual["source_model"]["outer_dt_seconds"] == 0.1
    assert actual["source_model"]["inner_euler_steps"] == INNER_STEPS
    assert actual["adaptation"]["control_catalogue"] == list(CATALOGUE)
    assert actual["adaptation"]["disturbance_catalogue"] == list(CATALOGUE)
    assert actual["adaptation"]["information_pattern"].startswith("u observes the current exact state")
    layers, destinations = build_graph()
    capture_steps = minimum_capture_steps(layers, destinations)
    first_winning = capture_steps[0][0]
    assert first_winning is not None
    selected_winning = figure_layers(layers, capture_steps)
    assert actual["first_guaranteed_capture_horizon_steps"] == first_winning
    assert first_winning == HORIZON
    assert actual["first_guaranteed_capture_horizon_seconds"] == first_winning * 0.1
    assert actual["forward_state_counts"] == [len(layer) for layer in layers]
    expected_winning = selected_winning
    assert actual["figure_layers"] == expected_winning
    assert actual["backward_winning_position_counts"] == [
        len(layer["winning_positions_ticks"]) for layer in expected_winning]

    values, optimal = solve_minimax(layers, destinations)
    value = values[0][0]
    assert value is not None
    assert math.isclose(actual["minimax_capture_time_seconds"], value, rel_tol=0.0, abs_tol=1e-12)
    assert actual["minimax_capture_inner_steps"] == round(value / DT)
    expected_trajectory = replay_worst_case(layers, destinations, values, optimal)
    assert actual["worst_case_minimax_trajectory"] == expected_trajectory
    timing = actual["timing"]
    assert timing["all_solver_calls_succeeded"] is True
    assert timing["finite_feedback_solver_calls"] == first_winning
    assert len(timing["finite_feedback_wall_ns_by_horizon"]) == first_winning
    assert all(type(ns) is int and ns > 0 for ns in timing["finite_feedback_wall_ns_by_horizon"])
    assert timing["finite_causal_minimax_solver_calls"] == 1
    assert all(type(ns) is int and ns > 0 for ns in timing["finite_causal_minimax_wall_ns"])
    assert type(timing["graph_build_wall_ns"]) is int and timing["graph_build_wall_ns"] > 0
    return {"layers": expected_winning,
            "initial_state_count": len(layers[0]),
            "selected_horizon": first_winning,
            "minimax_time": value,
            "trajectory": expected_trajectory}


def figure_data_record(analysis: dict) -> dict:
    return {"schema": "csl.env717-figure-data/1",
            "projection": {"x": "position x1", "y": "velocity x2", "units": "dimensionless source coordinates"},
            "display_geometry": "convex-hull envelopes are visual guides only; listed finite nodes are the exact sets",
            "layers": analysis["layers"],
            "target": {"shape": "disk", "center": [0.0, 0.0], "radius": 1.0},
            "trajectory": analysis["trajectory"]}


def _bounds(layers):
    points = [point for layer in layers for point in layer["forward_positions_ticks"]]
    xs = [point[0] / SCALE for point in points]
    ys = [point[1] / SCALE for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def _convex_hull(points):
    points = sorted({(point[0], point[1]) for point in points})
    if len(points) <= 2:
        return points
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
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


def svg_figure(analysis: dict) -> str:
    layers = analysis["layers"]
    xmin, xmax, ymin, ymax = _bounds(layers)
    xmin, xmax = min(xmin, -1.2), max(xmax, 1.2)
    ymin, ymax = min(ymin, -1.2), max(ymax, 1.2)
    width, height = 1200.0, 800.0
    left, top, plot_w, plot_h = 95.0, 70.0, 1010.0, 590.0
    xspan, yspan = max(xmax - xmin, 1e-9), max(ymax - ymin, 1e-9)
    def px(x): return left + (x - xmin) * plot_w / xspan
    def py(y): return top + (ymax - y) * plot_h / yspan
    colors = [f"#{int(32 + 190*t):02x}{int(104 + 85*(1-t)):02x}{int(210 - 140*t):02x}"
              for t in (i / max(len(layers)-1, 1) for i in range(len(layers)))]
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-labelledby="title desc">',
        '<title id="title">TimeOptimalSphereGame finite-catalogue minimax reachability</title>',
        '<desc id="desc">Convex-hull envelopes of each finite forward layer and its backward-winning intersection, the unit-disk target, and a worst-case trajectory under the causal minimax policy.</desc>',
        '<rect width="100%" height="100%" fill="#fbfcfe"/>',
        '<text x="95" y="30" font-family="sans-serif" font-size="21" font-weight="700" fill="#172554">TimeOptimalSphereGame: guaranteed capture under an adversarial input</text>',
        f'<text x="95" y="52" font-family="sans-serif" font-size="13" fill="#475569">Finite catalogues u,v ∈ {{−1,0,1}} · first robust capture by {analysis["selected_horizon"]} decisions · worst-case {analysis["minimax_time"]:.2f} s</text>',
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#334155"/>']
    for tick in range(6):
        xv = xmin + xspan * tick / 5
        yv = ymin + yspan * tick / 5
        chunks.append(f'<path d="M{px(xv):.1f},{top}V{top+plot_h} M{left},{py(yv):.1f}H{left+plot_w}" stroke="#e2e8f0" stroke-width="1"/>')
        chunks.append(f'<text x="{px(xv):.1f}" y="{top+plot_h+20}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#475569">{xv:.1f}</text>')
        chunks.append(f'<text x="{left-12}" y="{py(yv)+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#475569">{yv:.1f}</text>')
    for stage, layer in enumerate(layers):
        hull = _convex_hull(layer["forward_positions_ticks"])
        if len(hull) == 1:
            chunks.append(f'<circle cx="{px(hull[0][0]/SCALE):.1f}" cy="{py(hull[0][1]/SCALE):.1f}" r="3" fill="{colors[stage]}"/>')
        else:
            points = " ".join(f'{px(x/SCALE):.1f},{py(y/SCALE):.1f}' for x, y in hull)
            chunks.append(f'<polygon points="{points}" fill="{colors[stage]}" fill-opacity="0.025" stroke="{colors[stage]}" stroke-width="1.2" opacity="0.68"/>')
    disk_r = min(plot_w / xspan, plot_h / yspan)
    chunks.append(f'<circle cx="{px(0):.1f}" cy="{py(0):.1f}" r="{disk_r:.1f}" fill="#fef08a" fill-opacity="0.42" stroke="#ca8a04" stroke-width="2.2"/>')
    for stage, layer in enumerate(layers):
        hull = _convex_hull(layer["winning_positions_ticks"])
        if len(hull) == 1:
            chunks.append(f'<circle cx="{px(hull[0][0]/SCALE):.1f}" cy="{py(hull[0][1]/SCALE):.1f}" r="4" fill="none" stroke="#be123c" stroke-width="1.8"/>')
        else:
            points = " ".join(f'{px(x/SCALE):.1f},{py(y/SCALE):.1f}' for x, y in hull)
            chunks.append(f'<polygon points="{points}" fill="none" stroke="#be123c" stroke-width="1.6" stroke-dasharray="4 3" opacity="0.86"/>')
    trajectory = analysis["trajectory"]["microstep_positions_ticks"]
    trajectory_path = " ".join(("M" if i == 0 else "L") +
        f'{px(point[0]/SCALE):.1f},{py(point[1]/SCALE):.1f}' for i, point in enumerate(trajectory))
    chunks.append(f'<path d="{trajectory_path}" fill="none" stroke="#047857" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"/>')
    start = trajectory[0]
    finish = trajectory[-1]
    chunks.append(f'<circle cx="{px(start[0]/SCALE):.1f}" cy="{py(start[1]/SCALE):.1f}" r="5" fill="#1d4ed8" stroke="#fff" stroke-width="2"/>')
    chunks.append(f'<circle cx="{px(finish[0]/SCALE):.1f}" cy="{py(finish[1]/SCALE):.1f}" r="5" fill="#047857" stroke="#fff" stroke-width="2"/>')
    chunks.extend([
        f'<text x="{left + plot_w/2:.1f}" y="{top+plot_h+43}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#0f172a">Position x1</text>',
        f'<text x="23" y="{top + plot_h/2:.1f}" transform="rotate(-90 23 {top + plot_h/2:.1f})" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#0f172a">Velocity x2</text>',
        f'<rect x="{left+8}" y="{top+8}" width="530" height="82" rx="5" fill="#ffffff" fill-opacity="0.91"/>',
        f'<text x="{left+18}" y="{top+27}" font-family="sans-serif" font-size="12" fill="#1e3a8a">faint filled envelopes: forward finite-state layers (color marks stage)</text>',
        f'<text x="{left+18}" y="{top+46}" font-family="sans-serif" font-size="12" fill="#be123c">red dashed envelopes: backward-winning intersections</text>',
        f'<text x="{left+18}" y="{top+65}" font-family="sans-serif" font-size="12" fill="#047857">green: worst-case path under a causal minimax-optimal policy</text>',
        f'<text x="{left+18}" y="{top+83}" font-family="sans-serif" font-size="12" fill="#a16207">yellow: unit-disk target; start and capture are marked</text>',
        '<text x="95" y="785" font-family="sans-serif" font-size="11" fill="#64748b">Polygons are display-only convex-hull envelopes of exact finite nodes; full nodes and winning intersections are in figure-data.json. No continuous-boundary claim.</text>',
        '</svg>'])
    return "\n".join(chunks) + "\n"


def report_page(result: dict, analysis: dict) -> str:
    source_link = ("https://github.com/imm-rl-lab/optimal_control/blob/" +
                   SOURCE_COMMIT + "/Environments/TimeOptimalSphereGame/TimeOptimalSphereGame.py")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TimeOptimalSphereGame minimax report</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1.2rem;color:#172033}}h1,h2{{line-height:1.2}}figure{{margin:1.2rem 0}}svg{{width:100%;height:auto;border:1px solid #dbe2ea;border-radius:8px}}table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #dbe2ea;padding:.45rem .8rem;text-align:left}}code{{background:#eef2f7;padding:.1rem .3rem}}.note{{background:#eff6ff;padding:1rem;border-left:4px solid #2563eb}}nav a{{margin-right:.8rem}}</style></head>
<body><h1>TimeOptimalSphereGame: finite-catalogue minimax reachability</h1>
<p>This report replays the source's two-player time-to-target task on a finite action catalogue using CSL's finite-feedback reachability and finite-causal minimax solvers.</p>
<div class="note"><strong>Scope.</strong> The upstream model uses continuous actions u,v ∈ [-1,1] and trains u to minimize elapsed time while v maximizes it. This pilot discretizes both actions to {{-1,0,1}} and runs a finite horizon of {result['outer_horizon_steps']} decisions at 0.1 s per decision. It is a finite-catalogue adaptation, not a reproduction of the RL training run or a continuous-game guarantee.</div>
<figure><object data="reachability.svg" type="image/svg+xml" aria-label="Reachability and minimax trajectory figure"></object><figcaption>Each stage is shown in one position–velocity projection. The polygons are convex-hull display envelopes; exact finite nodes and winning intersections are available in the figure-data JSON.</figcaption></figure>
<h2>Result</h2><table><tbody>
<tr><th>First horizon where the initial state is robustly winning</th><td>{analysis['selected_horizon']} decisions ({analysis['selected_horizon']*0.1:.2f} s)</td></tr>
<tr><th>Finite-causal minimax worst-case target time</th><td>{analysis['minimax_time']:.2f} s ({round(analysis['minimax_time']/DT)} source Euler substeps)</td></tr>
<tr><th>Reachable states in the final layer</th><td>{len(analysis['layers'][-1]['forward_positions_ticks'])}</td></tr>
<tr><th>Winning positions in the initial layer</th><td>{len(analysis['layers'][0]['winning_positions_ticks'])}</td></tr>
<tr><th>Control and disturbance catalogues</th><td><code>{{-1, 0, 1}}</code> each</td></tr>
</tbody></table>
<p>The plotted worst-case path follows a minimax-optimal u action and, at each stage, a v action attaining the largest remaining minimax value. The discrete winning nodes are exact for this finite model; they do not establish a continuous-state winning boundary.</p>
<h2>Source and reproduction</h2><p><a href="{source_link}">Pinned upstream environment source</a>; source repository commit <code>{SOURCE_COMMIT}</code>, file blob <code>{SOURCE_BLOB}</code>. The repository metadata declares no license, so the report re-expresses the equations and does not redistribute source code.</p>
<nav><a href="result.json">Result JSON</a><a href="figure-data.json">Figure data</a><a href="capture.json">Capture</a><a href="environment.json">Environment</a><a href="README.md">Reproduction notes</a></nav>
<p>Solver timing is descriptive for this host and run. It is not a comparison or speedup claim.</p></body></html>
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_bundle(result: dict, analysis: dict, output: Path) -> None:
    if output.exists():
        raise ValueError(f"bundle destination already exists: {output}")
    output.mkdir(parents=True)
    figure = figure_data_record(analysis)
    environment = {"schema": "csl.environment-capture/1",
        "source_repository_commit": SOURCE_COMMIT, "source_file_blob": SOURCE_BLOB,
        "algorithm_source_sha256": result["algorithm_source_sha256"],
        "compiler": result["capture_environment"]["compiler"],
        "compiler_version": result["capture_environment"]["compiler_version"],
        "build_type": result["capture_environment"]["build_type"],
        "architecture": result["capture_environment"]["architecture"],
        "python": platform.python_version(), "platform": platform.platform(),
        "host_processor": platform.processor() or "unavailable"}
    capture = {"schema": "csl.capture/1", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": result["source_commit"], "driver_sha256": result["driver_sha256"],
        "algorithm_source_sha256": result["algorithm_source_sha256"],
        "host_processor": platform.processor() or "unavailable",
        "command": "build/env717-time-sphere-minimax/csl_env717_time_sphere_minimax --json", "solver_failures": 0,
        "notes": "One finite-game pilot capture; timings are descriptive and not compared."}
    readme = f'''# TimeOptimalSphereGame finite minimax pilot

Pinned source: `imm-rl-lab/optimal_control` commit `{SOURCE_COMMIT}`, blob `{SOURCE_BLOB}`. The upstream repository declares no license; this report contains re-expressed equations and parameters only.

The source state is `[x1 position, x2 velocity]`, initially `(2,-1)`, with inner-Euler dynamics `x1 += 0.01*(x2+v)` and `x2 += 0.01*u`. Each source decision holds u and v for ten inner steps (`dt=0.1`, inner step `0.01`). The target is the closed unit disk. Source reward is elapsed inner-Euler time until the target is entered. The upstream two-agent solver trains u on negative elapsed reward and v on positive elapsed reward, giving the finite pilot its minimizing-u/maximizing-v orientation.

This report discretizes each continuous interval `[-1,1]` to `{{-1,0,1}}`, keeps the source's ten held-action Euler substeps, and uses a 35-decision finite horizon. `finite_feedback` finds the first horizon at which the initial state is robustly winning. `finite_causal_minimax` minimizes the worst-case captured time on the same finite graph. The figure shows every forward finite state cloud and each layer's backward-winning intersection, plus one worst-case path under a minimax-optimal causal policy.

The result is a finite-catalogue adaptation. It does not reproduce RL training, certify a continuous-action policy, or establish a continuous-state winning boundary. Timings are one descriptive host capture with no comparison claim.

Reproduce by building `csl_env717_time_sphere_minimax`, running it to JSON, and checking the output with `scripts/reports/env717/check_time_sphere_minimax.py`. See `capture.json`, `environment.json`, and the exact source identities in `result.json`.
'''
    saved_result = dict(result)
    saved_result.pop("figure_layers")
    files = {"README.md": readme.encode(),
        "capture.json": (json.dumps(capture, indent=2) + "\n").encode(),
        "environment.json": (json.dumps(environment, indent=2) + "\n").encode(),
        "figure-data.json": (json.dumps(figure, separators=(",", ":")) + "\n").encode(),
        "index.html": report_page(result, analysis).encode(),
        "reachability.svg": svg_figure(analysis).encode(),
        "result.json": (json.dumps(saved_result, indent=2) + "\n").encode()}
    for name, content in files.items():
        (output / name).write_bytes(content)
    checksums = "".join(f"{sha256(files[name])}  {name}\n" for name in sorted(files))
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", type=Path, help="compiled release driver")
    parser.add_argument("--bundle", type=Path, help="write a checked report bundle")
    parser.add_argument("--result-json", type=Path, help="read a saved driver result instead of executing")
    args = parser.parse_args()
    if args.result_json:
        result = json.loads(args.result_json.read_text(encoding="utf-8"))
    else:
        completed = subprocess.run([str(args.driver), "--json"], check=True,
                                   capture_output=True, text=True)
        result = json.loads(completed.stdout)
    analysis = verify(result)
    if args.bundle:
        make_bundle(result, analysis, args.bundle)
    print(json.dumps({"status": "verified", "first_guaranteed_capture_horizon_steps": analysis["selected_horizon"],
        "minimax_capture_time_seconds": analysis["minimax_time"],
        "forward_state_counts": result["forward_state_counts"],
        "backward_winning_position_counts": result["backward_winning_position_counts"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Independently replay and render the nominal TimeOptimalSphereGame pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import platform
import subprocess
from pathlib import Path

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "fd7709a6f8e4196665d36b4ac5d348173599c250"
INITIAL = (2.0, -1.0)
DT, INNER_STEPS, INNER_DT = 0.1, 10, 0.01
TARGET_RADIUS = 1.0
CONTROLS = (-1, 0, 1)
MAX_HORIZON = 12
LATTICE_SCALE = 1_000_000
REPLAY_TOLERANCE = 2e-12


def in_target(state: tuple[float, float]) -> bool:
    return math.hypot(*state) <= TARGET_RADIUS


def advance_source(state: tuple[float, float], control: int) -> tuple[tuple[float, float], int]:
    """Replay ten explicit-Euler source substeps with adversarial v fixed to zero."""
    x1, x2 = state
    elapsed = 0
    for _ in range(INNER_STEPS):
        if math.hypot(x1, x2) <= TARGET_RADIUS:
            break
        x1 += INNER_DT * x2
        x2 += INNER_DT * control
        elapsed += 1
    return (round(x1, 12), round(x2, 12)), elapsed


def build_graph() -> tuple[list[list[tuple[float, float]]], list[dict]]:
    layers: list[list[tuple[float, float]]] = [[INITIAL]]
    edges: list[dict[tuple[float, float], list[tuple[float, float]]]] = []
    for _stage in range(MAX_HORIZON):
        next_layer: set[tuple[float, float]] = set()
        stage_edges = {}
        for state in layers[-1]:
            destinations = [advance_source(state, control)[0] for control in CONTROLS]
            stage_edges[state] = destinations
            next_layer.update(destinations)
        ordered = sorted(next_layer)
        layers.append(ordered)
        edges.append(stage_edges)
    return layers, edges


def solve_horizon(layers: list[list[tuple[float, float]]], edges: list[dict],
                  horizon: int) -> tuple[list[set[tuple[float, float]]],
                                         list[dict[tuple[float, float], list[int]]]]:
    winning: list[set[tuple[float, float]]] = [set() for _ in range(horizon + 1)]
    winning[-1] = {state for state in layers[horizon] if in_target(state)}
    admissible: list[dict[tuple[float, float], list[int]]] = [dict() for _ in range(horizon)]
    for stage in range(horizon - 1, -1, -1):
        next_winning = winning[stage + 1]
        for state in layers[stage]:
            actions = [index for index, destination in enumerate(edges[stage][state])
                       if destination in next_winning]
            if in_target(state):
                actions = list(range(len(CONTROLS)))
            admissible[stage][state] = actions
            if actions:
                winning[stage].add(state)
    return winning, admissible


def verify(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-time-sphere/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    assert actual["state_order"] == ["position_x1", "velocity_x2"]
    assert actual["lattice_scale"] == LATTICE_SCALE
    assert actual["maximum_horizon_steps"] == MAX_HORIZON
    assert actual["adaptation"]["adversarial_action"] == 0.0
    assert actual["adaptation"]["control_catalogue"] == list(CONTROLS)
    layers, edges = build_graph()
    assert actual["forward_layer_state_counts"] == [len(layer) for layer in layers]
    for horizon, saved in enumerate(actual["horizon_sweep"], start=1):
        assert saved["horizon_steps"] == horizon
        winning, _ = solve_horizon(layers, edges, horizon)
        assert saved["initial_winning"] is (INITIAL in winning[0])
        assert type(saved["solver_wall_ns"]) is int and saved["solver_wall_ns"] > 0
    selected_horizon = next(horizon for horizon in range(1, MAX_HORIZON + 1)
                            if INITIAL in solve_horizon(layers, edges, horizon)[0][0])
    assert actual["selected_horizon_steps"] == selected_horizon
    assert math.isclose(actual["selected_horizon_seconds"], selected_horizon * DT,
                        rel_tol=0.0, abs_tol=1e-15)
    winning, admissible = solve_horizon(layers, edges, selected_horizon)
    assert actual["initial_winning"] is True
    assert actual["forward_layers"] == [[list(state) for state in layer]
                                         for layer in layers[:selected_horizon + 1]]
    assert actual["backward_winning_layers"] == [
        [list(state) for state in layer if state in winning[t]]
        for t, layer in enumerate(layers[:selected_horizon + 1])]
    expected_actions = [
        [[CONTROLS[index] for index in admissible[t][state]] for state in layers[t]]
        for t in range(selected_horizon)]
    assert actual["admissible_actions"] == expected_actions
    expected_transitions = [
        [[layers[t + 1].index(destination) for destination in edges[t][state]]
         for state in layers[t]]
        for t in range(selected_horizon)]
    assert actual["transition_indices"] == expected_transitions

    max_discrepancy = 0.0
    for stage in range(selected_horizon):
        for state in layers[stage]:
            for control in CONTROLS:
                source, _ = advance_source(state, control)
                destination = edges[stage][state][CONTROLS.index(control)]
                max_discrepancy = max(max_discrepancy,
                    max(abs(a - b) for a, b in zip(source, destination)))
    assert max_discrepancy <= REPLAY_TOLERANCE

    state = INITIAL
    trajectory = [list(state)]
    controls = []
    elapsed_steps = 0
    for stage in range(selected_horizon):
        if in_target(state):
            break
        candidates = admissible[stage][state]
        assert candidates
        control = CONTROLS[candidates[0]]
        state, used = advance_source(state, control)
        elapsed_steps += used
        controls.append(control)
        trajectory.append(list(state))
    assert in_target(state)
    assert actual["trajectory"] == trajectory
    assert actual["trajectory_controls"] == controls
    assert actual["target_inner_steps"] == elapsed_steps
    assert math.isclose(actual["target_time_seconds"], elapsed_steps * INNER_DT,
                        rel_tol=0.0, abs_tol=1e-14)

    timing = actual["timing"]
    assert timing["warmup_calls"] == 0
    assert timing["measured_solver_calls"] == len(actual["horizon_sweep"])
    assert timing["comparison_claim"] is False
    assert timing["worker_threads_requested"] == timing["worker_threads_actual"] == 1
    assert timing["native_threads_requested"] == timing["native_threads_actual"] == 1
    assert timing["workspace_reuse"] == "none"
    assert timing["per_horizon_wall_ns"] == [r["solver_wall_ns"] for r in actual["horizon_sweep"]]
    assert timing["total_solver_wall_ns"] == sum(timing["per_horizon_wall_ns"])
    return {"layers": layers[:selected_horizon + 1],
            "winning_layers": winning,
            "trajectory": trajectory, "controls": controls,
            "objective_horizon": selected_horizon,
            "target_inner_steps": elapsed_steps,
            "max_source_replay_discrepancy": max_discrepancy}


def _scale(value: float, low: float, high: float, start: float, size: float) -> float:
    if high - low < 1e-15:
        return start + size / 2
    return start + size * (value - low) / (high - low)


def svg_figure(analysis: dict) -> str:
    width, height = 900, 680
    x, y, w, h = 115, 85, 680, 490
    points = [state for layer in analysis["layers"] for state in layer]
    xs, ys = [s[0] for s in points], [s[1] for s in points]
    pad_x = max((max(xs) - min(xs)) * 0.1, 0.15)
    pad_y = max((max(ys) - min(ys)) * 0.1, 0.15)
    xmin, xmax = min(xs) - pad_x, max(xs) + pad_x
    ymin, ymax = min(ys) - pad_y, max(ys) + pad_y
    sx = lambda value: _scale(value, xmin, xmax, x, w)
    sy = lambda value: y + h - _scale(value, ymin, ymax, 0.0, h)
    colors = ["#e2e8f0", "#60a5fa", "#22d3ee", "#94a3b8"]
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">TimeOptimalSphereGame nominal reachability</title>',
        '<desc id="desc">Forward finite-action states, backward-winning states for earliest target capture, a unit-disk target and a selected finite-feedback path.</desc>',
        '<rect width="100%" height="100%" fill="#111820"/>',
        '<text x="40" y="38" fill="#f4f1e8" font-family="sans-serif" font-size="25" font-weight="700">TimeOptimalSphereGame · nominal reachability</text>',
        f'<text x="{x}" y="{y-16}" fill="#f4f1e8" font-family="sans-serif" font-size="19" font-weight="700">State plane (x1,x2)</text>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#18232c" stroke="#53616c"/>',
        f'<defs><clipPath id="plot"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs>']
    radius_x = abs(sx(1.0) - sx(0.0))
    radius_y = abs(sy(1.0) - sy(0.0))
    lines.append(f'<ellipse clip-path="url(#plot)" cx="{sx(0):.2f}" cy="{sy(0):.2f}" rx="{radius_x:.2f}" ry="{radius_y:.2f}" fill="#d8b85a" fill-opacity=".12" stroke="#d8b85a" stroke-width="2" stroke-dasharray="7 5"/>')
    for stage, layer in enumerate(analysis["layers"]):
        color = colors[min(stage, len(colors) - 1)]
        for state in layer:
            lines.append(f'<circle cx="{sx(state[0]):.2f}" cy="{sy(state[1]):.2f}" r="2.8" fill="{color}" fill-opacity=".38"/>')
        for state in analysis["winning_layers"][stage]:
            if state in layer:
                lines.append(f'<circle cx="{sx(state[0]):.2f}" cy="{sy(state[1]):.2f}" r="4.0" fill="#f2c14e" fill-opacity=".88"/>')
    path = [(sx(state[0]), sy(state[1])) for state in analysis["trajectory"]]
    lines.append('<polyline points="' + " ".join(f"{px:.2f},{py:.2f}" for px, py in path) + '" fill="none" stroke="#fb7185" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    for px, py in path:
        lines.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="5.5" fill="#fb7185" stroke="#111820" stroke-width="1.5"/>')
    lines.extend([
        f'<text x="{x+w/2:.1f}" y="{y+h+35}" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="16">x1 position</text>',
        f'<text x="{x-45}" y="{y+h/2:.1f}" transform="rotate(-90 {x-45} {y+h/2:.1f})" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="16">x2 velocity</text>',
        '<circle cx="78" cy="620" r="4" fill="#60a5fa"/><text x="92" y="625" fill="#d6dee3" font-family="sans-serif" font-size="14">forward reachable finite states</text>',
        '<circle cx="390" cy="620" r="4" fill="#f2c14e"/><text x="404" y="625" fill="#d6dee3" font-family="sans-serif" font-size="14">backward-winning states</text>',
        '<circle cx="675" cy="620" r="4" fill="#fb7185"/><text x="689" y="625" fill="#d6dee3" font-family="sans-serif" font-size="14">selected feedback path</text>',
        '<text x="78" y="656" fill="#9eabb4" font-family="sans-serif" font-size="12">Gold disk: source target radius 1. The opponent action is fixed at zero in this nominal adaptation.</text>',
        '</svg>'])
    return "\n".join(lines)


def figure_data_record(analysis: dict) -> dict:
    return {"schema": "csl.env717-time-sphere-figure/1",
        "projection_pairs": [[0, 1]],
        "projection_labels": [["x1 position", "x2 velocity"]],
        "target": {"projection": [0, 1], "shape": "disk", "center": [0.0, 0.0],
                   "radius": TARGET_RADIUS},
        "stages": [{"stage": i, "states": [list(s) for s in layer],
                    "winning_states": [list(s) for s in analysis["winning_layers"][i]
                                       if s in layer]}
                   for i, layer in enumerate(analysis["layers"])],
        "trajectory": analysis["trajectory"], "controls": analysis["controls"],
        "earliest_horizon_steps": analysis["objective_horizon"],
        "source_target_time_seconds": analysis["target_inner_steps"] * INNER_DT,
        "max_source_replay_discrepancy": analysis["max_source_replay_discrepancy"]}


def source_url() -> str:
    return (f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/"
            "Environments/TimeOptimalSphereGame/TimeOptimalSphereGame.py")


def report_page(actual: dict, analysis: dict) -> str:
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TimeOptimalSphereGame nominal reachability report</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:2rem}}img{{width:100%;height:auto}}.note{{border-left:4px solid #f2c14e;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>TimeOptimalSphereGame: nominal reachability</h1><p>The pinned source is a two-state point with dynamics x1′=x2+v, x2′=u and a unit-disk target. This pilot freezes the adversarial input at v=0, uses controls u∈{{-1,0,1}}, and computes finite-state backward-winning sets with CSL's finite-feedback reachability solver.</p><p>The initial state first becomes winning within <strong>{analysis['objective_horizon']} outer steps ({analysis['objective_horizon']*DT:.1f} s)</strong>. Replaying the selected policy enters the disk after {analysis['target_inner_steps']} source Euler substeps ({analysis['target_inner_steps']*INNER_DT:.2f} s). The figure overlays forward reachable states, backward-winning intersections, the target disk and one selected feedback trajectory.</p><figure><img src="reachability.svg" alt="Forward reachable state layers, backward-winning intersections, target disk and selected finite-feedback trajectory"><figcaption>Finite action states in the source position–velocity plane.</figcaption></figure><p class="note"><strong>Adaptation:</strong> the source lets a second player choose v∈[-1,1] and asks for minimum time to capture under continuous actions. This pilot fixes v=0 and checks only the three finite control values through 1.2 seconds. It does not reproduce the original two-player RL optimum. The open-loop and feedback notions coincide here only because the opponent action is frozen and the selected trajectory is deterministic.</p><p>The horizon sweep records one solver call per candidate horizon, zero warmups and no performance comparison. The saved record includes all reachable transitions, backward-winning sets, feasible actions, source/compiler identity and checksums.</p><ul><li><a href="result.json">Complete reachability result</a></li><li><a href="figure-data.json">Projection and policy path data</a></li><li><a href="reachability.svg">Standalone SVG figure</a></li><li><a href="README.md">Reproduction and source notes</a></li><li><a href="{source_url()}">Pinned upstream source</a></li></ul><p>Measured CSL source commit: <code>{html.escape(actual['source_commit'])}</code>.</p></main></html>'''


def write_report(actual: dict, analysis: dict, output: Path) -> None:
    output.mkdir(parents=False, exist_ok=False)
    (output / "result.json").write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    figure_data = figure_data_record(analysis)
    (output / "figure-data.json").write_text(json.dumps(figure_data, indent=2) + "\n", encoding="utf-8")
    (output / "reachability.svg").write_text(svg_figure(analysis), encoding="utf-8")
    (output / "index.html").write_text(report_page(actual, analysis), encoding="utf-8")
    environment = {"schema": "csl.env717-time-sphere-environment/1",
        "source_repository": "https://github.com/imm-rl-lab/optimal_control",
        "source_repository_commit": SOURCE_COMMIT, "source_file_blob": SOURCE_BLOB,
        "adaptation": "finite-state nominal reachability with source opponent action fixed to zero",
        "maximum_horizon_seconds": MAX_HORIZON * DT, "performance_comparison": False,
        "algorithm_source_sha256": actual["algorithm_source_sha256"],
        "platform": platform.platform(), "python": platform.python_version()}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    capture = {"schema": "csl.env717-time-sphere-capture/1",
        "source_commit": actual["source_commit"], "driver_sha256": actual["driver_sha256"],
        "algorithm_source_sha256": actual["algorithm_source_sha256"],
        "compiler": actual["capture_environment"], "os": platform.platform(),
        "python": platform.python_version(), "worker_threads": 1, "native_threads": 1,
        "warmup_calls": 0, "measured_solver_calls": actual["timing"]["measured_solver_calls"]}
    (output / "capture.json").write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
    readme = f'''# TimeOptimalSphereGame nominal reachability pilot

The source is pinned to [{SOURCE_COMMIT}]({source_url()}) (blob `{SOURCE_BLOB}`). Its initial state is `(2,-1)`, outer step is `0.1 s`, ten source Euler substeps are used per step, and target is the unit disk. Source dynamics are `x1'=x2+v`, `x2'=u`; source time reward counts the inner substeps until the state enters the disk. The source repository has no declared license; this report re-expresses the equations and does not copy its code.

This pilot fixes the source opponent action at `v=0` and catalogs controller actions `u∈{{-1,0,1}}`. It runs the CSL finite-feedback table solver over horizons from 1 to {MAX_HORIZON} stages to find the first horizon whose backward-winning set contains the initial point. The selected finite-state policy's trajectory is replayed through the source update. This is a nominal finite-catalogue reachability result, not the original continuous two-player RL optimum.

## Reproduce

```sh
cmake -S . -B build/env717-time-sphere -DCMAKE_BUILD_TYPE=Release \\
  -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \\
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-time-sphere --target csl_env717_time_sphere --parallel 4
python3 scripts/reports/env717/check_time_sphere.py \\
  build/env717-time-sphere/csl_env717_time_sphere \\
  --output /tmp/env717-time-sphere-pilot-v1
```

`result.json` stores the complete finite graph, horizon sweep, winning states and selected path. The solver timings are descriptive and make no performance comparison.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(output.iterdir()) if path.is_file())
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        completed = subprocess.run([str(args.executable)], check=True, capture_output=True,
                                   text=True, timeout=120)
        actual = json.loads(completed.stdout)
        analysis = verify(actual)
        if args.output:
            write_report(actual, analysis, args.output)
            print(f"verified {actual['selected_horizon_steps']} stage horizon; wrote {args.output}")
        else:
            print(f"verified horizon {actual['selected_horizon_steps']} ({actual['selected_horizon_seconds']:.1f}s); "
                  f"capture in {analysis['target_inner_steps']} source inner steps")
        return 0
    except (AssertionError, OSError, ValueError, KeyError, subprocess.SubprocessError,
            json.JSONDecodeError) as error:
        print(f"TimeOptimalSphereGame verification failed: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

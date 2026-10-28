#!/usr/bin/env python3
"""Independently replay the pinned AirToAirInterception finite-game pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import os
import platform
import subprocess
from pathlib import Path

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "9054c9fcd01e49f3dbfd8b8ee8d12e7365e1d9b5"
DT, INNER_N, HORIZON = 0.05, 10, 3
INITIAL = (0., 0., 30., 0., 0., 80., 0., 200., -70., 0., 80.)
U = ((0., 0.), (4.35, 0.), (-4.35, 0.), (0., 5.), (0., -5.))
V = ((0., 0.), (0.66, 0.), (-0.66, 0.), (0., 1.), (0., -1.))


def advance(state: tuple[float, ...], u: tuple[float, float],
            v: tuple[float, float]) -> tuple[float, ...]:
    x = list(state)
    h = DT / INNER_N
    for _ in range(INNER_N):
        dx = (x[2], x[3], -x[3] + u[0], x[5], x[6], -x[6] + u[1],
              x[8], -v[0], x[10], -v[1])
        x = [x[0] + h, *(xi + h * di for xi, di in zip(x[1:], dx))]
    return tuple(x)


def relative(x: tuple[float, ...]) -> tuple[float, float, float, float]:
    return (x[1] - x[7], x[2] - x[8], x[4] - x[9], x[5] - x[10])


def range_value(x: tuple[float, ...]) -> float:
    rel = relative(x)
    return math.hypot(rel[0], rel[2])


def enumerate_game() -> dict:
    plans = []
    sequences = tuple(itertools.product(range(len(V)), repeat=HORIZON))
    for plan in itertools.product(range(len(U)), repeat=HORIZON):
        cases = []
        for sequence in sequences:
            states = [INITIAL]
            for ui, vi in zip(plan, sequence):
                states.append(advance(states[-1], U[ui], V[vi]))
            cases.append((range_value(states[-1]), sequence, states))
        plans.append((max(row[0] for row in cases), plan, cases))
    optimum = min(row[0] for row in plans)
    minimizing = [i for i, row in enumerate(plans) if row[0] <= optimum + 1e-9]
    selected = plans[minimizing[0]]
    worst = min((case for case in selected[2] if case[0] >= selected[0] - 1e-9),
                key=lambda case: case[1])
    return {"plans": plans, "value": optimum, "minimizing": minimizing,
            "selected_plan": selected[1], "worst_sequence": worst[1],
            "trajectory": worst[2]}


def verify(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-air-to-air-pilot/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    assert actual["horizon"] == HORIZON
    expected = enumerate_game()
    assert len(actual["plans"]) == 125
    assert actual["controller_plan_count"] == 125
    assert actual["disturbance_sequence_count_per_plan"] == 125
    assert actual["near_optimal_tolerance"] == 1e-10
    assert actual["minimizing_plan_indices"] == expected["minimizing"]
    assert math.isclose(actual["objective_value"], expected["value"], abs_tol=1e-8)
    for saved, (worst, plan, cases) in zip(actual["plans"], expected["plans"]):
        assert saved["control_indices"] == list(plan)
        assert math.isclose(saved["worst_terminal_range"], worst, abs_tol=1e-8)
        max_states = [case[2][-1] for case in cases if case[0] >= worst - 1e-8]
        assert any(max(abs(a - b) for a, b in zip(saved["maximizing_terminal_state"], state)) < 1e-7
                   for state in max_states)
    timing = actual["timing"]
    assert timing["warmup_calls"] == 0 and timing["measured_calls"] == 1
    assert len(timing["measured_wall_ns"]) == 1
    assert type(timing["measured_wall_ns"][0]) is int and timing["measured_wall_ns"][0] > 0
    assert timing["comparison_claim"] is False
    return expected


def feedback_sets(open_loop_value: float) -> dict:
    """Build finite-state causal winning layers on the exact enumerated graph."""
    layers: list[dict[tuple[float, ...], tuple[float, ...]]] = [{INITIAL: INITIAL}]
    edges: list[dict[tuple[float, ...], dict[int, dict[int, tuple[float, ...]]]]] = []
    for _ in range(HORIZON):
        layer_edges = {}
        following = {}
        for state in layers[-1]:
            actions = {}
            for ui, u in enumerate(U):
                outcomes = {}
                for vi, v in enumerate(V):
                    nxt = advance(state, u, v)
                    key = nxt
                    following.setdefault(key, nxt)
                    outcomes[vi] = key
                actions[ui] = outcomes
            layer_edges[state] = actions
        edges.append(layer_edges)
        layers.append(following)
    values: list[dict[tuple[float, ...], float]] = [{} for _ in range(HORIZON + 1)]
    values[-1] = {state: range_value(state) for state in layers[-1]}
    for t in range(HORIZON - 1, -1, -1):
        values[t] = {state: min(max(values[t + 1][nxt] for nxt in outcomes.values())
                                for outcomes in edges[t][state].values())
                     for state in layers[t]}
    feedback_value = values[0][INITIAL]
    winning = [{state for state in layer if values[t][state] <= feedback_value + 1e-8}
               for t, layer in enumerate(layers)]
    open_loop_winning = [{state for state in layer if values[t][state] <= open_loop_value + 1e-8}
                         for t, layer in enumerate(layers)]
    return {"forward": layers, "winning": winning, "open_loop_winning": open_loop_winning,
            "values": values, "feedback_value": feedback_value}


def svg_figure(expected: dict, sets: dict) -> str:
    width, height = 1160, 590
    panels = ((55, "Relative x position (m)", "Relative x velocity (m/s)", 0, 1),
              (625, "Relative y position (m)", "Relative y velocity (m/s)", 2, 3))
    colors = ("#a6cee3", "#1f78b4", "#33a02c", "#e31a1c")
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
              '<title>AirToAirInterception reachable and winning sets</title>',
              '<desc>Two relative position versus velocity projections. Points show all forward reachable stages, purple points show causal backward-winning states at the feedback minimax value, and the orange polyline shows one selected worst-case trajectory.</desc>',
              '<rect width="100%" height="100%" fill="white"/>',
              '<style>text{font:13px sans-serif}.title{font-size:18px;font-weight:bold}</style>',
              '<text x="580" y="28" text-anchor="middle" class="title">AirToAirInterception: 3-stage finite minimax adaptation</text>']
    for left, xlabel, ylabel, ix, iy in panels:
        x0, y0, pw, ph = left + 54, 95, 455, 390
        allpts = [state for layer in sets["forward"] for state in layer.values()]
        xs = [relative(s)[ix] for s in allpts]
        ys = [relative(s)[iy] for s in allpts]
        xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
        dx = max(xmax - xmin, 1.0); dy = max(ymax - ymin, 1.0)
        xmin -= dx * .06; xmax += dx * .06; ymin -= dy * .06; ymax += dy * .06
        def xy(state):
            rel = relative(state)
            return xy_values(rel[ix], rel[iy])
        def xy_values(xv, yv):
            return (x0 + (xv - xmin) / (xmax - xmin) * pw,
                    y0 + ph - (yv - ymin) / (ymax - ymin) * ph)
        chunks.append(f'<text x="{left+280}" y="60" text-anchor="middle" class="title">{html.escape(xlabel.split(" position")[0])} axis</text>')
        chunks.append(f'<path d="M{x0},{y0} V{y0+ph} H{x0+pw}" fill="none" stroke="#333"/>')
        chunks.append(f'<text x="{x0+pw/2}" y="{y0+ph+42}" text-anchor="middle">{html.escape(xlabel)}</text>')
        chunks.append(f'<text x="{left+12}" y="{y0+ph/2}" transform="rotate(-90 {left+12} {y0+ph/2})" text-anchor="middle">{html.escape(ylabel)}</text>')
        for tick in range(5):
            xv = xmin + (xmax - xmin) * tick / 4
            yv = ymin + (ymax - ymin) * tick / 4
            tx = x0 + pw * tick / 4
            ty = y0 + ph - ph * tick / 4
            chunks.append(f'<path d="M{tx:.2f},{y0+ph} v5 M{x0-5},{ty:.2f} h5" stroke="#333"/>')
            chunks.append(f'<text x="{tx:.2f}" y="{y0+ph+20}" text-anchor="middle">{xv:.4g}</text>')
            chunks.append(f'<text x="{x0-8}" y="{ty+4:.2f}" text-anchor="end">{yv:.4g}</text>')
        for t, layer in enumerate(sets["forward"]):
            points = {tuple(round(v, 10) for v in (relative(state)[ix], relative(state)[iy]))
                      for state in layer.values()}
            for xv, yv in points:
                x, y = xy_values(xv, yv)
                chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" fill="{colors[t]}" opacity=".42"/>')
        for t, layer in enumerate(sets["open_loop_winning"]):
            points = {tuple(round(v, 10) for v in (relative(state)[ix], relative(state)[iy]))
                      for state in layer}
            for xv, yv in points:
                x, y = xy_values(xv, yv)
                chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="#cab2d6" opacity=".42"/>')
        for t, layer in enumerate(sets["winning"]):
            points = {tuple(round(v, 10) for v in (relative(state)[ix], relative(state)[iy]))
                      for state in layer}
            for xv, yv in points:
                x, y = xy_values(xv, yv)
                chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#6a3d9a" opacity=".54"/>')
        pts = [xy(s) for s in expected["trajectory"]]
        chunks.append('<polyline points="' + ' '.join(f'{x:.2f},{y:.2f}' for x,y in pts) + '" fill="none" stroke="#ff7f00" stroke-width="3"/>')
        for x, y in pts:
            chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#ff7f00"/>')
    legend = (("R0 initial", colors[0]), ("R1 forward", colors[1]),
              ("R2 forward", colors[2]), ("R3 forward", colors[3]),
              ("Causal win @ open-loop value", "#cab2d6"),
              ("Causal win @ feedback value", "#6a3d9a"),
              ("Selected open-loop worst case", "#ff7f00"))
    for i, (label, color) in enumerate(legend):
        x = 42 + (i % 4) * 280; y = 544 + (i // 4) * 21
        if color == "#ff7f00":
            chunks.append(f'<path d="M{x-5},{y-4} h10" stroke="{color}" stroke-width="3"/>')
        else:
            chunks.append(f'<circle cx="{x}" cy="{y-4}" r="4" fill="{color}"/>')
        chunks.append(f'<text x="{x+12}" y="{y}">{label}</text>')
    return ''.join(chunks) + '</svg>\n'


def build_report(executable: Path, output: Path) -> None:
    run = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    actual = json.loads(run.stdout)
    expected = verify(actual)
    sets = feedback_sets(expected["value"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    def projected(layers, i):
        return [[list(point) for point in sorted({tuple(relative(s)[i:i+2]) for s in layer})]
                for layer in layers]
    figure_data = {"schema": "csl.env717-air-to-air-figure-data/1",
                   "relative_x_position_velocity": {
                       "forward_layers": projected(sets["forward"], 0),
                       "winning_layers": projected(sets["winning"], 0),
                       "open_loop_threshold_winning_layers": projected(sets["open_loop_winning"], 0)},
                   "relative_y_position_velocity": {
                       "forward_layers": projected(sets["forward"], 2),
                       "winning_layers": projected(sets["winning"], 2),
                       "open_loop_threshold_winning_layers": projected(sets["open_loop_winning"], 2)},
                   "selected_worst_case": [list(relative(s)) for s in expected["trajectory"]],
                   "open_loop_value": expected["value"],
                   "feedback_value": sets["feedback_value"]}
    (output / "figure-data.json").write_text(json.dumps(figure_data, indent=2) + "\n", encoding="utf-8")
    figure = svg_figure(expected, sets)
    (output / "projections.svg").write_text(figure, encoding="utf-8")
    feedback_gap = abs(expected["value"] - sets["feedback_value"])
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AirToAirInterception finite minimax pilot</title><main><h1>AirToAirInterception</h1><p>Three stages at 0.05 seconds each adapt the source 2-second continuous-action RL task to finite action catalogues. Source explicit-Euler dynamics use 10 inner steps per stage. This is not an RL reproduction or a continuous-action solution.</p><p>Fixed open-loop minimax terminal range: {expected['value']:.9g} m (125 plans × 125 disturbance sequences). Causal finite-state feedback minimax terminal range: {sets['feedback_value']:.9g} m (dynamic programming over the exact reachable transition graph). The values coincide within {feedback_gap:.3g} m for this finite adaptation.</p><p>The purple nodes show causal backward-winning states at the feedback minimax value; light purple shows the winning set at the open-loop minimax threshold. Both intersect the forward reachable layers. The orange path is the selected minimizing fixed open-loop plan under a maximizing disturbance sequence. Solver near-optimal tolerance: {actual['near_optimal_tolerance']:.1e}. One timing observation, zero warmups; no performance comparison is claimed.</p><figure><img src="projections.svg" alt="Relative position and velocity projections with forward reachable stages, feedback-winning intersections, and a selected open-loop worst-case path"><figcaption>Horizontal and vertical relative-motion phase planes; forward reachable nodes are colored R0–R3.</figcaption></figure><ul><li><a href="result.json">Complete enumerated result</a></li><li><a href="figure-data.json">Projection data</a></li></ul></main></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "environment.json").write_text(json.dumps({"schema":"csl.env717-air-to-air-environment/1", "source_repository":"https://github.com/imm-rl-lab/optimal_control", "source_repository_commit":SOURCE_COMMIT, "source_file_blob":SOURCE_BLOB, "source_horizon_seconds":2.0, "adapted_horizon_seconds":HORIZON*DT, "adapter":"finite 3-stage minimax with 5-point action catalogues per player; upstream continuous-action task is adapted, not reproduced", "near_optimal_tolerance":actual["near_optimal_tolerance"], "release":"pilot; no performance claim", "algorithm_source_sha256":actual["algorithm_source_sha256"], "platform":platform.platform(), "python":platform.python_version()}, indent=2)+"\n", encoding="utf-8")
    (output / "README.md").write_text("# AirToAirInterception finite minimax pilot\n\nSee `index.html`. Results were independently replayed against the pinned source Euler step. This is a 3-stage finite-action adaptation, not the source continuous-action RL task.\n", encoding="utf-8")
    cpu_model = "unknown"
    cpu_source = "unavailable"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                cpu_model = line.split(":", 1)[1].strip()
                cpu_source = "/proc/cpuinfo"
                break
    except OSError:
        pass
    (output / "capture.json").write_text(json.dumps({"schema":"csl.env717-capture/1", "source_commit":actual["source_commit"], "driver_sha256":actual["driver_sha256"], "renderer_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "capture_environment":{"os":platform.platform(), "processor":cpu_model, "processor_identity_source":cpu_source, "architecture":platform.machine(), "logical_cpus":os.cpu_count()}, "measurement":{"warmup_calls":0, "measured_calls":1, "measured_wall_ns":actual["timing"]["measured_wall_ns"], "limiter":"not profiled; single descriptive observation only", "comparison_claim":False}}, indent=2)+"\n", encoding="utf-8")
    sums = []
    for path in sorted(output.iterdir()):
        if path.name != "SHA256SUMS":
            sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(sums)+"\n", encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--build-report", type=Path)
    args = parser.parse_args()
    if args.build_report:
        build_report(args.executable.resolve(), args.build_report)
        print(f"AirToAirInterception report written to {args.build_report}")
        return 0
    completed = subprocess.run([str(args.executable)], check=True, capture_output=True, text=True)
    verify(json.loads(completed.stdout))
    print("AirToAirInterception finite-game replay passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

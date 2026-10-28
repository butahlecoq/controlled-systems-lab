#!/usr/bin/env python3
"""Independently verify and render the finite PointOnThePlane minimax pilot."""
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
SOURCE_BLOB = "2552484d02afca759ff909aca5e5854686a651c4"
DT, INNER_STEPS, HORIZON = 0.05, 10, 3
INNER_DT = DT / INNER_STEPS
INITIAL = (0.0, 2.0, 2.0, 1.0)
U = ((0.0, 0.0), (6.0, 0.0), (-6.0, 0.0), (0.0, 2.0), (0.0, -2.0))
V = ((0.0, 0.0), (2.0, 0.0), (-2.0, 0.0), (0.0, 4.0), (0.0, -4.0))
NEAR_TOLERANCE = 1e-10
REPLAY_TOLERANCE = 2e-11
FEEDBACK_TOLERANCE = 1e-9

_stage_times = [0.0]
_clock = 0.0
for _stage in range(HORIZON):
    for _ in range(INNER_STEPS):
        _clock += INNER_DT
    _stage_times.append(_clock)
STAGE_TIMES = tuple(_stage_times)


def advance_source(state: tuple[float, ...], stage: int,
                   control: tuple[float, float], disturbance: tuple[float, float]
                   ) -> tuple[float, ...]:
    """Reproduce the pinned source's ten explicit-Euler inner updates."""
    x = list(state)
    time = STAGE_TIMES[stage]
    for _ in range(INNER_STEPS):
        scale = math.exp(time / 5.0)
        derivative = (
            x[2],
            x[3],
            -4.0 * scale * x[0] - 0.1 * scale * x[2]
            - 8.0 * control[0] + 2.4 * scale * disturbance[0],
            -4.0 * scale * x[1] - 0.1 * scale * x[3]
            - 8.0 * control[1] + 2.4 * scale * disturbance[1],
        )
        x = [value + INNER_DT * slope for value, slope in zip(x, derivative)]
        time += INNER_DT
    return tuple(x)


def apply_map(state: tuple[float, ...], stage_map: dict,
              control: tuple[float, float], disturbance: tuple[float, float]
              ) -> tuple[float, ...]:
    return tuple(
        sum(stage_map["A"][i][j] * state[j] for j in range(4))
        + sum(stage_map["B"][i][j] * control[j] for j in range(2))
        + sum(stage_map["E"][i][j] * disturbance[j] for j in range(2))
        for i in range(4)
    )


def terminal_value(state: tuple[float, ...]) -> float:
    return math.hypot(state[0], state[1])


def enumerate_open_loop() -> tuple[list[dict], float, list[int], tuple, tuple, list]:
    disturbances = tuple(itertools.product(range(len(V)), repeat=HORIZON))
    plans: list[dict] = []
    all_cases: list[list[tuple[float, tuple[int, ...], tuple[float, ...], list[tuple[float, ...]]]]] = []
    for plan_index, plan in enumerate(itertools.product(range(len(U)), repeat=HORIZON)):
        cases = []
        for sequence in disturbances:
            states = [INITIAL]
            for stage, (ui, vi) in enumerate(zip(plan, sequence)):
                states.append(advance_source(states[-1], stage, U[ui], V[vi]))
            value = terminal_value(states[-1])
            cases.append((value, sequence, states[-1], states))
        worst = max(case[0] for case in cases)
        maximizing = next(case[2] for case in cases if case[0] == worst)
        maximizing_states = [list(case[2]) for case in cases if case[0] == worst]
        plans.append({"plan_index": plan_index, "control_indices": list(plan),
                      "controls": [list(U[index]) for index in plan],
                      "worst_terminal_norm": worst,
                      "maximizing_terminal_state": list(maximizing),
                      "_maximizing_terminal_states": maximizing_states})
        all_cases.append(cases)
    optimum = min(plan["worst_terminal_norm"] for plan in plans)
    minimizing = [plan["plan_index"] for plan in plans
                  if plan["worst_terminal_norm"] <= optimum + NEAR_TOLERANCE]
    selected_index = minimizing[0]
    selected_cases = all_cases[selected_index]
    selected_worst = max(case[0] for case in selected_cases)
    worst_case = next(case for case in selected_cases if case[0] == selected_worst)
    selected_plan = tuple(plans[selected_index]["control_indices"])
    return plans, optimum, minimizing, selected_plan, worst_case[1], worst_case[3]


def build_feedback_graph() -> tuple[list[list[tuple[float, ...]]], list[dict], float]:
    layers: list[set[tuple[float, ...]]] = [{INITIAL}]
    edges: list[dict[tuple[float, ...], list[list[tuple[float, ...]]]]] = []
    for stage in range(HORIZON):
        stage_edges = {}
        next_layer: set[tuple[float, ...]] = set()
        for state in layers[-1]:
            action_rows = []
            for control in U:
                outcomes = [advance_source(state, stage, control, disturbance) for disturbance in V]
                action_rows.append(outcomes)
                next_layer.update(outcomes)
            stage_edges[state] = action_rows
        edges.append(stage_edges)
        layers.append(next_layer)

    values = {state: terminal_value(state) for state in layers[-1]}
    value_layers: list[dict[tuple[float, ...], float]] = [{} for _ in range(HORIZON + 1)]
    value_layers[-1] = values
    for stage in range(HORIZON - 1, -1, -1):
        current = {}
        for state, action_rows in edges[stage].items():
            current[state] = min(max(value_layers[stage + 1][next_state]
                                     for next_state in outcomes)
                                for outcomes in action_rows)
        value_layers[stage] = current
    return [sorted(layer) for layer in layers], edges, value_layers[0][INITIAL]


def backward_winning(layers: list[list[tuple[float, ...]]], edges: list[dict],
                     threshold: float) -> list[set[tuple[float, ...]]]:
    winners: list[set[tuple[float, ...]]] = [set() for _ in range(HORIZON + 1)]
    winners[-1] = {state for state in layers[-1]
                   if terminal_value(state) <= threshold + FEEDBACK_TOLERANCE}
    for stage in range(HORIZON - 1, -1, -1):
        winners[stage] = {
            state for state, action_rows in edges[stage].items()
            if any(all(next_state in winners[stage + 1] for next_state in outcomes)
                   for outcomes in action_rows)
        }
    return winners


def verify(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-point-on-plane/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    assert actual["state_order"] == ["position_x1", "position_x2", "velocity_x3", "velocity_x4"]
    assert actual["horizon"] == HORIZON
    assert actual["controller_plan_count"] == 125
    assert actual["disturbance_sequence_count_per_plan"] == 125
    assert actual["near_optimal_tolerance"] == NEAR_TOLERANCE
    assert len(actual["stage_transition_maps"]) == HORIZON

    max_map_discrepancy = 0.0
    probes = [INITIAL, (0.2, -0.3, 1.1, -1.7), (2.0, 2.0, 0.0, 0.0)]
    for stage, stage_map in enumerate(actual["stage_transition_maps"]):
        for state in probes:
            for control in U:
                for disturbance in V:
                    source = advance_source(state, stage, control, disturbance)
                    mapped = apply_map(state, stage_map, control, disturbance)
                    max_map_discrepancy = max(max_map_discrepancy,
                        max(abs(a - b) for a, b in zip(source, mapped)))
    assert max_map_discrepancy <= REPLAY_TOLERANCE

    plans, optimum, minimizing, plan, sequence, trajectory = enumerate_open_loop()
    assert len(actual["plans"]) == len(plans)
    assert actual["minimizing_plan_indices"] == minimizing
    assert math.isclose(actual["objective_value"], optimum, rel_tol=0.0, abs_tol=REPLAY_TOLERANCE)
    for saved, expected in zip(actual["plans"], plans):
        assert saved["plan_index"] == expected["plan_index"]
        assert saved["control_indices"] == expected["control_indices"]
        assert math.isclose(saved["worst_terminal_norm"], expected["worst_terminal_norm"],
                            rel_tol=0.0, abs_tol=REPLAY_TOLERANCE)
        state = saved["maximizing_terminal_state"]
        assert any(max(abs(a - b) for a, b in zip(state, candidate)) <= REPLAY_TOLERANCE
                   for candidate in expected["_maximizing_terminal_states"])

    timing = actual["timing"]
    assert timing["warmup_calls"] == 0 and timing["measured_calls"] == 1
    assert len(timing["measured_wall_ns"]) == 1
    assert type(timing["measured_wall_ns"][0]) is int and timing["measured_wall_ns"][0] > 0
    assert timing["comparison_claim"] is False
    assert timing["worker_threads_requested"] == timing["worker_threads_actual"] == 1
    assert timing["native_threads_requested"] == timing["native_threads_actual"] == 1
    assert timing["workspace_reuse"] == "none"

    layers, edges, feedback_value = build_feedback_graph()
    assert feedback_value <= optimum + FEEDBACK_TOLERANCE
    winners = backward_winning(layers, edges, optimum)
    assert INITIAL in winners[0]
    return {"plans": plans, "objective_value": optimum, "minimizing_plan": plan,
            "worst_disturbance_sequence": sequence,
            "trajectory": [list(state) for state in trajectory],
            "layers": layers, "winning_layers": winners,
            "feedback_value": feedback_value,
            "max_source_map_discrepancy": max_map_discrepancy}


def _scale(value: float, low: float, high: float, start: float, size: float) -> float:
    if high - low < 1e-15:
        return start + size / 2
    return start + size * (value - low) / (high - low)


def svg_figure(analysis: dict) -> str:
    width, height = 1500, 650
    panels = [(70, 95, 650, 440, 0, 1, "Position plane", "x1", "x2"),
              (800, 95, 650, 440, 2, 3, "Velocity plane", "x3", "x4")]
    trajectory = analysis["trajectory"]
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             '<title id="title">PointOnThePlane: finite minimax reachable and winning geometry</title>',
             '<desc id="desc">Two panels show all forward reachable states and backward-winning intersections, with an open-loop worst-case path.</desc>',
             '<rect width="100%" height="100%" fill="#111820"/>',
             '<text x="50" y="42" fill="#f4f1e8" font-family="sans-serif" font-size="26" font-weight="700">PointOnThePlane · finite-action minimax pilot</text>']
    colors = ["#e2e8f0", "#60a5fa", "#22d3ee", "#94a3b8"]
    for stage_index, (x, y, w, h, ix, iy, title, xlabel, ylabel) in enumerate(panels):
        points = [state for layer in analysis["layers"] for state in layer]
        xs, ys = [s[ix] for s in points], [s[iy] for s in points]
        pad_x = max((max(xs) - min(xs)) * 0.08, 0.1)
        pad_y = max((max(ys) - min(ys)) * 0.08, 0.1)
        xmin, xmax = min(xs) - pad_x, max(xs) + pad_x
        ymin, ymax = min(ys) - pad_y, max(ys) + pad_y
        sx = lambda value: _scale(value, xmin, xmax, x, w)
        sy = lambda value: y + h - _scale(value, ymin, ymax, 0.0, h)
        lines.append(f'<text x="{x}" y="{y-18}" fill="#f4f1e8" font-family="sans-serif" font-size="20" font-weight="700">{title}</text>')
        lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#18232c" stroke="#53616c"/>')
        lines.append(f'<defs><clipPath id="panel-{stage_index}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs>')
        # The terminal target is a ball in position coordinates only.
        if ix == 0:
            r = analysis["objective_value"]
            rx = abs(sx(r) - sx(0.0))
            ry = abs(sy(r) - sy(0.0))
            lines.append(f'<ellipse clip-path="url(#panel-{stage_index})" cx="{sx(0.0):.2f}" cy="{sy(0.0):.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="#d8b85a" fill-opacity=".12" stroke="#d8b85a" stroke-dasharray="6 5"/>')
        for stage, layer in enumerate(analysis["layers"]):
            for state in layer:
                lines.append(f'<circle cx="{sx(state[ix]):.2f}" cy="{sy(state[iy]):.2f}" r="2.2" fill="{colors[stage]}" fill-opacity=".28"/>')
            winning = analysis["winning_layers"][stage]
            for state in winning:
                lines.append(f'<circle cx="{sx(state[ix]):.2f}" cy="{sy(state[iy]):.2f}" r="3.0" fill="#f2c14e" fill-opacity=".82"/>')
        path = [(sx(state[ix]), sy(state[iy])) for state in trajectory]
        path_data = " ".join(f'{px:.2f},{py:.2f}' for px, py in path)
        lines.append(f'<polyline points="{path_data}" fill="none" stroke="#fb7185" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>')
        for px, py in path:
            lines.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="5.2" fill="#fb7185" stroke="#111820" stroke-width="1.5"/>')
        lines.append(f'<text x="{x+w/2:.1f}" y="{y+h+33}" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="15">{xlabel}</text>')
        lines.append(f'<text x="{x-42}" y="{y+h/2:.1f}" transform="rotate(-90 {x-42} {y+h/2:.1f})" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="15">{ylabel}</text>')
    legend_y = 595
    lines.extend([
        f'<circle cx="80" cy="{legend_y}" r="4" fill="{colors[0]}"/><text x="93" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">forward k=0</text>',
        f'<circle cx="205" cy="{legend_y}" r="4" fill="{colors[1]}"/><text x="218" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">k=1</text>',
        f'<circle cx="285" cy="{legend_y}" r="4" fill="{colors[2]}"/><text x="298" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">k=2</text>',
        f'<circle cx="365" cy="{legend_y}" r="4" fill="{colors[3]}"/><text x="378" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">k=3</text>',
        f'<circle cx="470" cy="{legend_y}" r="4" fill="#f2c14e"/><text x="483" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">backward-winning intersections</text>',
        f'<circle cx="825" cy="{legend_y}" r="4" fill="#fb7185"/><text x="838" y="{legend_y+5}" fill="#d6dee3" font-family="sans-serif" font-size="13">open-loop worst-case trajectory</text>',
        f'<text x="80" y="630" fill="#9eabb4" font-family="sans-serif" font-size="12">Dashed gold terminal target is clipped to the position panel; discrete action catalogues produce projected points.</text>',
        '</svg>'])
    return "\n".join(lines)


def figure_data_record(analysis: dict) -> dict:
    return {"schema": "csl.env717-point-on-plane-figure/1",
        "projection_pairs": [[0, 1], [2, 3]],
        "projection_labels": [["x1 position coordinate", "x2 position coordinate"],
                              ["x3 velocity coordinate", "x4 velocity coordinate"]],
        "stages": [{"stage": i, "states": [list(s) for s in layer],
                    "winning_indices": [j for j, state in enumerate(layer)
                                        if state in analysis["winning_layers"][i]]}
                   for i, layer in enumerate(analysis["layers"])],
        "target": {"projection": [0, 1], "shape": "disk",
                   "center": [0.0, 0.0], "radius": analysis["objective_value"]},
        "selected_controls": [list(U[i]) for i in analysis["minimizing_plan"]],
        "selected_disturbances": [list(V[i]) for i in analysis["worst_disturbance_sequence"]],
        "trajectory": analysis["trajectory"],
        "open_loop_value": analysis["objective_value"],
        "feedback_value": analysis["feedback_value"],
        "feedback_threshold_tolerance": FEEDBACK_TOLERANCE,
        "max_source_map_discrepancy": analysis["max_source_map_discrepancy"]}


def report_page(actual: dict, analysis: dict) -> str:
    source_url = (f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/"
                  "Environments/PointOnThePlane/PointOnThePlane.py")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PointOnThePlane finite minimax report</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1200px;margin:auto;padding:2rem}}img{{width:100%;height:auto}}.note{{border-left:4px solid #f2c14e;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>PointOnThePlane: reachability and minimax</h1><p>The source has four physical coordinates: positions (x1,x2) and velocities (x3,x4). The two panels show those projections, all finite forward reachable states, their backward-winning intersections at the fixed-plan minimax threshold, and one independently replayed worst-case open-loop trajectory.</p><p>Open-loop minimax terminal position norm: <strong>{analysis['objective_value']:.10g}</strong>. The independently computed causal finite-state feedback value on the reachable graph is {analysis['feedback_value']:.10g}. The backward set targets terminal norm no greater than the open-loop minimax value; the feedback graph is separate evidence, not the fixed-plan solver result.</p><figure><img src="projections.svg" alt="Position and velocity projections with finite forward states, backward-winning intersections, a terminal target disk, and a worst-case trajectory"><figcaption>Finite reachable state projections. The control and disturbance catalogues contain zero and the four axis endpoints of the source ellipses.</figcaption></figure><p class="note"><strong>Adaptation:</strong> the upstream environment uses continuous controls and a 4-second horizon. This report uses three 0.05-second stages, finite catalogues, and the source's ten explicit-Euler substeps per stage. It is not a reproduction of the continuous-action RL task. Coordinate units are not specified by the source.</p><p>Timing is one cold-process finite-minimax call with no warmups; no performance comparison is claimed. The saved record includes stage transition maps, all 125 controller-plan outcomes, source/compiler identity, and raw input assumptions. The independent verifier replays all 15,625 plan/disturbance-sequence pairs and reconstructs the feedback graph.</p><ul><li><a href="result.json">Complete minimax result record</a></li><li><a href="figure-data.json">Projection and trajectory data</a></li><li><a href="projections.svg">Standalone SVG figure</a></li><li><a href="README.md">Reproduction and source notes</a></li><li><a href="{source_url}">Pinned upstream PointOnThePlane source</a></li></ul><p>Measured CSL source commit: <code>{html.escape(actual['source_commit'])}</code>.</p></main></html>'''


def write_report(actual: dict, analysis: dict, output: Path) -> None:
    output.mkdir(parents=False, exist_ok=False)
    source_url = (f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/"
                  "Environments/PointOnThePlane/PointOnThePlane.py")
    svg = svg_figure(analysis)
    figure_data = figure_data_record(analysis)
    (output / "result.json").write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    (output / "figure-data.json").write_text(json.dumps(figure_data, indent=2) + "\n", encoding="utf-8")
    (output / "projections.svg").write_text(svg, encoding="utf-8")
    (output / "index.html").write_text(report_page(actual, analysis), encoding="utf-8")
    environment = {"schema": "csl.env717-point-on-plane-environment/1",
        "source_repository": "https://github.com/imm-rl-lab/optimal_control",
        "source_repository_commit": SOURCE_COMMIT, "source_file_blob": SOURCE_BLOB,
        "source_horizon_seconds": 4.0, "adapted_horizon_seconds": HORIZON * DT,
        "adapter": "finite 3-stage open-loop minimax and independent causal finite-state graph",
        "performance_comparison": False,
        "algorithm_source_sha256": actual["algorithm_source_sha256"],
        "platform": platform.platform(), "python": platform.python_version()}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    capture = {"schema": "csl.env717-point-on-plane-capture/1",
        "source_commit": actual["source_commit"], "driver_sha256": actual["driver_sha256"],
        "algorithm_source_sha256": actual["algorithm_source_sha256"],
        "compiler": actual["capture_environment"], "os": platform.platform(),
        "python": platform.python_version(), "cpu_model": cpu,
        "worker_threads": 1, "native_threads": 1, "warmup_calls": 0,
        "measured_calls": 1, "workspace_reuse": "none"}
    (output / "capture.json").write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
    readme = f'''# PointOnThePlane finite minimax pilot

The source is pinned to [{SOURCE_COMMIT}]({source_url}) (blob `{SOURCE_BLOB}`). Its four physical states are position coordinates `(x1,x2)` followed by velocities `(x3,x4)`, initial state `{list(INITIAL)}`, and terminal reward `sqrt(x1^2+x2^2)`. The source uses `dt=0.05`, ten explicit-Euler inner steps, a 4-second horizon and action radii `u={ [6, 2] }`, `v={ [2, 4] }`. The source repository has no declared license; this report re-expresses equations and does not copy code.

The pilot keeps the source initial state, substep semantics, time-varying coefficients, and action scaling. It adapts the horizon to three stages (0.15 seconds) and the continuous action ellipses to five-point catalogues containing zero and the positive/negative axis endpoints. The minimizer commits to an open-loop control plan before the adversary selects a full disturbance sequence. The finite solver exhausts 125 plans and 125 disturbance histories per plan. It is not an RL reproduction.

The report also computes causal finite-state feedback values on the independently reconstructed finite transition graph. Its backward-winning sets target the open-loop minimax terminal norm; they are not claimed to solve the source continuous-state problem.

## Reproduce

```sh
cmake -S . -B build/env717-point-on-plane -DCMAKE_BUILD_TYPE=Release \\
  -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \\
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-point-on-plane --target csl_env717_point_on_plane --parallel 4
python3 scripts/reports/env717/check_point_on_plane.py \\
  build/env717-point-on-plane/csl_env717_point_on_plane \\
  --output /tmp/env717-point-on-plane-r1
```

The complete solver record is in `result.json`; independently derived projections, stage states and the selected trajectory are in `figure-data.json`. The one measured solver call is descriptive only; no algorithm comparison or speed claim is made.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    files = sorted(path for path in output.iterdir() if path.is_file())
    sums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                    for path in files)
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if not args.executable.is_file():
            raise ValueError(f"driver executable does not exist: {args.executable}")
        completed = subprocess.run([str(args.executable)], check=True, capture_output=True,
                                   text=True, timeout=120)
        actual = json.loads(completed.stdout)
        analysis = verify(actual)
        if args.output:
            write_report(actual, analysis, args.output)
            print(f"verified {len(analysis['plans'])} plans; wrote report to {args.output}")
        else:
            print(f"verified {len(analysis['plans'])} plans × 125 disturbance histories; "
                  f"open-loop value {analysis['objective_value']:.12g}; "
                  f"feedback value {analysis['feedback_value']:.12g}; "
                  f"max source/map discrepancy {analysis['max_source_map_discrepancy']:.3g}")
        return 0
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"PointOnThePlane verification failed: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

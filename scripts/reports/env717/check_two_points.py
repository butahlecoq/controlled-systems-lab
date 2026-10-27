#!/usr/bin/env python3
"""Independently enumerate, check, and plot the two-point game pilot."""

from __future__ import annotations

import hashlib
import html
import itertools
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

U = (-2.5, 0.0, 2.5)
V = (-1.0, 0.0, 1.0)
INITIAL = (4.5, 0.0, 0.0, 0.0)
HORIZON = 3
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"


def advance(state: tuple[float, ...], u: float, v: float) -> tuple[float, ...]:
    p1, v1, p2, v2 = state
    for _ in range(10):
        p1, v1, p2, v2 = (p1 + 0.01 * v1,
                          v1 + 0.01 * (-100.0 * v1 + 100.0 * u),
                          p2 + 0.01 * v2,
                          v2 + 0.01 * v)
    return p1, v1, p2, v2


def key(state: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(x, 12) for x in state)


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    values = sorted(set(points))
    if len(values) <= 2:
        return values

    def cross(o: tuple[float, float], a: tuple[float, float],
              b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in values:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(values):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def enumerate_game() -> tuple[dict, list[list[tuple[float, ...]]], list[set[tuple[float, ...]]]]:
    controls = list(itertools.product(U, repeat=HORIZON))
    disturbances = list(itertools.product(V, repeat=HORIZON))
    candidates = []
    for plan in controls:
        cases = []
        for disturbance in disturbances:
            states = [INITIAL]
            for u, v in zip(plan, disturbance):
                states.append(advance(states[-1], u, v))
            gap2 = (states[-1][0] - states[-1][2]) ** 2
            cases.append((gap2, disturbance, states))
        candidates.append((max(item[0] for item in cases), plan, cases))
    optimum = min(item[0] for item in candidates)
    minimizing = [i for i, item in enumerate(candidates)
                  if item[0] <= optimum + 1e-12]

    layers: list[set[tuple[float, ...]]] = [{key(INITIAL)}]
    groups: list[dict[tuple[float, ...], set[tuple[float, ...]]]] = [
        {(): {key(INITIAL)}}]
    for _stage in range(HORIZON):
        next_groups: dict[tuple[float, ...], set[tuple[float, ...]]] = {}
        for prefix, states in groups[-1].items():
            for u in U:
                next_groups[prefix + (u,)] = {
                    key(advance(state, u, v)) for state_key in states
                    for state in [tuple(state_key)] for v in V}
        groups.append(next_groups)
        next_layer = {key(advance(state, u, v))
                      for state_key in layers[-1]
                      for state in [tuple(state_key)]
                      for u in U for v in V}
        layers.append(next_layer)

    target = layers[-1]
    backward: list[set[tuple[float, ...]]] = [set() for _ in range(HORIZON + 1)]
    backward[-1] = {state for state in target
                    if (state[0] - state[2]) ** 2 <= optimum + 1e-12}
    for stage in range(HORIZON - 1, -1, -1):
        next_states = backward[stage + 1]
        for state in layers[stage]:
            if any(all(key(advance(state, u, v)) in next_states for v in V)
                   for u in U):
                backward[stage].add(state)

    index = minimizing[0]
    value, plan, cases = candidates[index]
    worst = [item for item in cases if item[0] == value]
    _, disturbance, trajectory = worst[0]
    record = {"optimum": optimum, "minimizing_indices": minimizing,
              "plans": candidates, "selected_plan": plan,
              "selected_disturbance": disturbance, "trajectory": trajectory,
              "layers": [sorted(layer) for layer in layers],
              "backward": [sorted(layer) for layer in backward],
              "forward_groups": [
                  [{"control_prefix": list(prefix), "vertices": sorted(states)}
                   for prefix, states in sorted(stage.items())]
                  for stage in groups]}
    return record, record["layers"], record["backward"]


def verify_record(source: dict) -> tuple[dict, dict]:
    assert source["schema"] == "csl.env717-two-points-pilot/1"
    assert source["source_repository_commit"] == SOURCE_COMMIT
    assert source["source_file_blob"] == SOURCE_BLOB
    oracle, layers, backward = enumerate_game()
    assert source["plan_count"] == 27 and len(source["plans"]) == 27
    assert source["minimizing_plan_indices"] == oracle["minimizing_indices"]
    assert math.isclose(source["objective_value"], oracle["optimum"], abs_tol=1e-11)
    assert math.isclose(source["worst_terminal_gap"], math.sqrt(oracle["optimum"]), abs_tol=1e-11)
    for actual, expected in zip(source["plans"], oracle["plans"]):
        expected_value, expected_controls, cases = expected
        assert actual["controls"] == list(expected_controls)
        assert math.isclose(actual["worst_terminal_squared_gap"], expected_value, abs_tol=1e-11)
        worst_states = [case[2][-1] for case in cases if case[0] == expected_value]
        assert any(all(math.isclose(a, b, abs_tol=1e-11)
                       for a, b in zip(actual["maximizing_terminal_state"], state))
                   for state in worst_states)
    assert tuple(oracle["selected_plan"]) == (-2.5, -2.5, -2.5)
    assert tuple(oracle["selected_disturbance"]) == (-1.0, -1.0, -1.0)
    timing = source["timing"]
    samples = timing["measured_wall_ns"]
    assert timing["warmup_calls"] == 1 and timing["measured_calls"] == 7
    assert len(samples) == 7 and all(type(sample) is int and sample > 0 for sample in samples)
    ordered = sorted(samples)
    assert timing["median_wall_ns"] == ordered[3]
    assert timing["min_wall_ns"] == ordered[0] and timing["max_wall_ns"] == ordered[-1]
    assert len(layers) == len(backward) == HORIZON + 1
    assert key(INITIAL) in backward[0]
    derived = {"forward_layers": layers, "robust_backward_layers": backward,
               "forward_groups": oracle["forward_groups"],
               "selected_plan": oracle["selected_plan"],
               "selected_worst_disturbance": oracle["selected_disturbance"],
               "trajectory": oracle["trajectory"],
               "terminal_target": "squared position gap <= minimax value",
               "intersection_semantics": "finite-catalogue state nodes in both forward layer and robust backward winning set"}
    return source, derived


def verify(executable: Path) -> tuple[dict, dict]:
    source = json.loads(subprocess.check_output([str(executable)], text=True))
    return verify_record(source)


def plot_svg(derived: dict) -> str:
    width, height = 1260, 650
    panels = [(75, 135, 520, 390, 0, 1, "Point 1 phase plane", "x1 position", "x2 velocity"),
              (665, 135, 520, 390, 2, 3, "Point 2 phase plane", "x3 position", "x4 velocity")]
    colors = ["#d6e7f0", "#56b4e9", "#00c49a", "#d9a441"]
    states_by_stage = derived["forward_layers"]
    groups_by_stage = derived["forward_groups"]
    back_by_stage = derived["robust_backward_layers"]
    trajectory = derived["trajectory"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Two points on parallel lines: forward reachability and robust backward sets</title>',
           '<desc id="desc">Forward reachable polytopes for each finite control prefix, robust backward winning nodes, their intersections, and one minimax trajectory, shown in both point phase planes.</desc>',
           '<rect width="100%" height="100%" fill="#111820"/>',
           '<text x="75" y="45" fill="#f4f1e8" font-family="sans-serif" font-size="27" font-weight="700">Two points on parallel lines · finite-action differential-game pilot</text>',
           '<text x="75" y="77" fill="#bac6ce" font-family="sans-serif" font-size="15">3 stages · dt = 0.1 s · 27 control plans × 27 disturbance sequences · robust target set is defined by the minimax value</text>']
    for x0, y0, pw, ph, xi, yi, title, xlabel, ylabel in panels:
        all_x = [state[xi] for layer in states_by_stage for state in layer]
        all_y = [state[yi] for layer in states_by_stage for state in layer]
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)
        xpad = max((xmax - xmin) * 0.08, 0.1)
        ypad = max((ymax - ymin) * 0.08, 0.1)
        xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad
        px = lambda val: x0 + (val - xmin) / (xmax - xmin) * pw
        py = lambda val: y0 + ph - (val - ymin) / (ymax - ymin) * ph
        out.append(f'<text x="{x0}" y="{y0 - 25}" fill="#f4f1e8" font-family="sans-serif" font-size="20" font-weight="700">{title}</text>')
        for tick in range(5):
            tx = xmin + (xmax - xmin) * tick / 4
            ty = ymin + (ymax - ymin) * tick / 4
            out.append(f'<line x1="{px(tx):.2f}" y1="{y0}" x2="{px(tx):.2f}" y2="{y0+ph}" stroke="#293640"/>')
            out.append(f'<line x1="{x0}" y1="{py(ty):.2f}" x2="{x0+pw}" y2="{py(ty):.2f}" stroke="#293640"/>')
            out.append(f'<text x="{px(tx):.2f}" y="{y0+ph+20}" fill="#bac6ce" font-family="sans-serif" font-size="11" text-anchor="middle">{tx:.2g}</text>')
            out.append(f'<text x="{x0-8}" y="{py(ty)+4:.2f}" fill="#bac6ce" font-family="sans-serif" font-size="11" text-anchor="end">{ty:.2g}</text>')
        out.append(f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#81909a"/>')
        for stage, groups in enumerate(groups_by_stage):
            for group in groups:
                projected = [(state[xi], state[yi]) for state in group["vertices"]]
                hull = convex_hull(projected)
                if len(hull) >= 3:
                    coords = " ".join(f'{px(x):.2f},{py(y):.2f}' for x, y in hull)
                    out.append(f'<polygon points="{coords}" fill="{colors[stage]}" fill-opacity="0.055" stroke="{colors[stage]}" stroke-opacity="0.28" stroke-width="0.8"/>')
        for stage, states in enumerate(states_by_stage):
            backward = {tuple(state) for state in back_by_stage[stage]}
            for state in states:
                inside = tuple(state) in backward
                color = "#f4a261" if inside else colors[stage]
                radius = 4.4 if inside else 2.3
                opacity = 0.92 if inside else 0.22
                out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="{radius}" fill="{color}" fill-opacity="{opacity}"/>')
        coords = " ".join(f'{px(state[xi]):.2f},{py(state[yi]):.2f}' for state in trajectory)
        out.append(f'<polyline points="{coords}" fill="none" stroke="#ff6b35" stroke-width="4" stroke-linejoin="round"/>')
        for state in trajectory:
            out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="5.5" fill="#ff6b35" stroke="#fff4e6" stroke-width="1.5"/>')
        out.append(f'<text x="{x0+pw/2}" y="{y0+ph+48}" fill="#f4f1e8" font-family="sans-serif" font-size="14" text-anchor="middle">{xlabel}</text>')
        out.append(f'<text x="{x0-48}" y="{y0+ph/2}" fill="#f4f1e8" font-family="sans-serif" font-size="14" text-anchor="middle" transform="rotate(-90 {x0-48} {y0+ph/2})">{ylabel}</text>')
    out.extend(['<rect x="79" y="583" width="9" height="9" fill="#56b4e9" fill-opacity="0.4" stroke="#56b4e9"/><text x="95" y="592" fill="#d2dce1" font-family="sans-serif" font-size="13">Forward reachable polytopes by stage/control prefix</text>',
                '<circle cx="470" cy="587" r="4" fill="#f4a261"/><text x="482" y="592" fill="#d2dce1" font-family="sans-serif" font-size="13">Forward ∩ robust backward vertices</text>',
                '<line x1="690" y1="587" x2="720" y2="587" stroke="#ff6b35" stroke-width="4"/><text x="730" y="592" fill="#d2dce1" font-family="sans-serif" font-size="13">Verified minimax trajectory (one worst-case disturbance)</text>',
                '<text x="75" y="626" fill="#93a4ae" font-family="sans-serif" font-size="12">Forward polygons exactly project convex disturbance-reachable polytopes per control prefix; backward nodes are finite-vertex feedback-game nodes, not continuous predecessor sets. Horizon: 0.3 s.</text>',
                '</svg>'])
    return "\n".join(out)


def render(executable: Path, output: Path | None) -> None:
    host = {"os": platform.platform(), "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "load_average_before_run": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "capture_started_unix_ns": time.time_ns()}
    source, derived = verify(executable)
    if output is None:
        return
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    (output / "figure-data.json").write_text(json.dumps(derived, indent=2) + "\n", encoding="utf-8")
    svg = plot_svg(derived)
    (output / "projections.svg").write_text(svg + "\n", encoding="utf-8")
    converter = shutil.which("rsvg-convert")
    if converter:
        subprocess.run([converter, "--output", str(output / "projections.png"),
                        str(output / "projections.svg")], check=True)
    timing = source["timing"]
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Two-point minimax pilot</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1320px;margin:auto;padding:2rem}}a{{color:#8bd3f7}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}</style><main><h1>Two points on parallel lines: reachability and minimax</h1><p>The finite-action minimax method exhausts 27 fixed control plans and all 27 adversarial disturbance vertex sequences per plan. An independent Python replay checks every plan score, minimizing plan, source-integrator trajectory, forward reachable polytopes, and backward vertex-game nodes. The two panels are the physical phase planes `(x1,x2)=(position₁, velocity₁)` and `(x3,x4)=(position₂, velocity₂)`.</p><div>{svg}</div><p class="note"><strong>Adaptation:</strong> the source uses continuous actions over 10 seconds. This pilot uses a 3-stage control catalogue and disturbance sets equal to the convex hull of the listed vertices. The discrete linear stage map is derived from the source’s ten explicit-Euler substeps. The minimax solver selects an open-loop control sequence against the full convex disturbance sets. Forward polygons exactly project each convex disturbance-reachable polytope for one fixed control prefix. The separately computed backwards nodes permit state-dependent controls in a finite vertex game; they are not complete continuous-state predecessor sets or the fixed-plan solver’s output. This is not a reproduction of the original continuous-control RL experiment.</p><p>Minimax squared gap: {source['objective_value']:.8g}; worst absolute gap: {source['worst_terminal_gap']:.8g}. Seven single-threaded solver-call observations after one warmup have median {timing['median_wall_ns']} ns and range {timing['min_wall_ns']}–{timing['max_wall_ns']} ns. No comparative speed claim is supported. <a href="result.json">Result JSON</a> · <a href="figure-data.json">Figure data</a> · <a href="projections.svg">Standalone SVG</a></p><p>Upstream commit <code>{SOURCE_COMMIT}</code>; source blob <code>{SOURCE_BLOB}</code>. Runtime environment: {html.escape(host['os'])}, {html.escape(host['processor'])}, {host['logical_cpus']} logical CPUs.</p></main></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    identity = {"renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "capture_environment": host}
    (output / "capture.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 4):
        raise SystemExit("usage: check_two_points.py EXECUTABLE [--output DIRECTORY]")
    if len(sys.argv) == 2:
        render(Path(sys.argv[1]).resolve(), None)
    elif sys.argv[2] != "--output":
        raise SystemExit("expected --output")
    else:
        render(Path(sys.argv[1]).resolve(), Path(sys.argv[3]))

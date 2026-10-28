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
LATTICE_SCALE = 2000
EULER_CROSSCHECK_TOLERANCE = 1e-10
ACTION_CODES = (-1, 0, 1)
DISTURBANCE_CODES = (-1, 0, 1)


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


def lattice_step(state: tuple[int, ...], action: int, disturbance: int) -> tuple[int, ...]:
    p1, v1, p2, v2 = state
    if v1 % 100 or v2 % 10:
        raise AssertionError("nonintegral fixed-scale transition division")
    result = (p1 + v1 // 100 + 450 * action, 5000 * action,
              p2 + v2 // 10 + 9 * disturbance, v2 + 200 * disturbance)
    if any(value < -(1 << 63) or value > (1 << 63) - 1 for value in result):
        raise AssertionError("feedback lattice coordinate exceeds int64")
    return result


def gap_numerator(state: tuple[int, ...]) -> int:
    gap = state[0] - state[2]
    if gap < -(1 << 63) or gap > (1 << 63) - 1:
        raise AssertionError("terminal gap subtraction exceeds int64")
    value = gap * gap
    if value > (1 << 63) - 1:
        raise AssertionError("terminal gap square exceeds int64")
    return value


def feedback_oracle(saved: dict) -> dict:
    feedback = saved["feedback"]
    layers: list[list[tuple[int, ...]]] = [[(9000, 0, 0, 0)]]
    for _ in range(HORIZON):
        next_layer = {lattice_step(state, a, d) for state in layers[-1]
                      for a in ACTION_CODES for d in DISTURBANCE_CODES}
        layers.append(sorted(next_layer))
    n = max(map(len, layers))
    assert feedback["scale"] == LATTICE_SCALE
    assert feedback["layer_states"] == [[list(state) for state in layer] for layer in layers]
    assert feedback["padded_state_count"] == n
    expected_stage_safe = [[i < len(layer) for i in range(n)] for layer in layers[:-1]]
    expected_terminal_safe = [i < len(layers[-1]) for i in range(n)]
    assert feedback["stage_safe_masks"] == expected_stage_safe
    assert feedback["terminal_safe_mask"] == expected_terminal_safe
    transitions: list[list[list[list[int]]]] = []
    max_discrepancy = 0.0
    for t in range(HORIZON):
        next_ids = {state: i for i, state in enumerate(layers[t + 1])}
        table = []
        for i in range(n):
            row = []
            for a in ACTION_CODES:
                successors = []
                for d in DISTURBANCE_CODES:
                    if i < len(layers[t]):
                        source = layers[t][i]
                        target = lattice_step(source, a, d)
                        assert target in next_ids, "real transition targets padding"
                        successors.append(next_ids[target])
                        physical_source = tuple(value / LATTICE_SCALE for value in source)
                        physical_target = tuple(value / LATTICE_SCALE for value in target)
                        euler_target = advance(physical_source, 2.5 * a, float(d))
                        discrepancy = max(abs(x-y) for x, y in zip(physical_target, euler_target))
                        max_discrepancy = max(max_discrepancy, discrepancy)
                    else:
                        # Padding cannot win; keep a complete in-range successor row.
                        successors.append(len(layers[t + 1]) if len(layers[t + 1]) < n else 0)
                row.append(successors)
            table.append(row)
        transitions.append(table)

    candidates = sorted({gap_numerator(state) for state in layers[-1]})
    assert feedback["candidate_count"] == len(candidates)
    assert max_discrepancy <= EULER_CROSSCHECK_TOLERANCE
    assert feedback["euler_crosscheck_tolerance"] == EULER_CROSSCHECK_TOLERANCE
    assert math.isclose(feedback["euler_max_abs_discrepancy"], max_discrepancy,
                        rel_tol=0.0, abs_tol=1e-18)

    def solve(candidate: int) -> tuple[list[list[bool]], list[list[list[int]]]]:
        wins = [[False] * n for _ in range(HORIZON + 1)]
        actions = [[[] for _ in range(n)] for _ in range(HORIZON)]
        for i, state in enumerate(layers[-1]):
            wins[-1][i] = gap_numerator(state) <= candidate
        for t in range(HORIZON - 1, -1, -1):
            for i in range(len(layers[t])):
                for ai, a in enumerate(ACTION_CODES):
                    if all(wins[t+1][j] for j in transitions[t][i][ai]):
                        actions[t][i].append(a)
                wins[t][i] = bool(actions[t][i])
        return wins, actions

    chosen = None
    expected = None
    solves = 0
    for candidate in candidates:
        solves += 1
        candidate_policy = solve(candidate)
        if candidate_policy[0][0][0]:
            chosen, expected = candidate, candidate_policy
            break
    assert chosen is not None and expected is not None
    assert feedback["threshold_numerator"] == chosen
    assert feedback["threshold_denominator"] == 4_000_000
    assert feedback["solve_count"] == solves
    assert feedback["winning"] == expected[0]
    assert feedback["admissible_action_codes"] == expected[1]
    assert feedback["action_codes"] == list(ACTION_CODES)
    assert feedback["disturbance_codes"] == list(DISTURBANCE_CODES)
    assert feedback["solver"] == "csl.reachability.finite_feedback.solve"
    assert feedback["information_pattern"] == "action selected from current exact state before disturbance vertex"
    assert "not cost-optimal" in feedback["selector"]

    # Replay every rectangular table cell, including unsafe padding.
    assert feedback["transition_table"] == transitions
    for t in range(HORIZON):
        for i in range(n):
            assert len(transitions[t][i]) == len(ACTION_CODES)
            assert all(len(row) == len(DISTURBANCE_CODES) for row in transitions[t][i])
            if i >= len(layers[t]):
                assert expected[1][t][i] == [] and not expected[0][t][i]

    # Recompute the first-admissible selector and its maximum-terminal-gap path.
    def worst(t: int, state: tuple[int, ...], disturbances: tuple[int, ...]):
        if t == HORIZON:
            return gap_numerator(state), [state], [], list(disturbances)
        i = {value: j for j, value in enumerate(layers[t])}[state]
        action = expected[1][t][i][0]
        options = []
        for d in DISTURBANCE_CODES:
            nxt = lattice_step(state, action, d)
            value, path, acts, ds = worst(t + 1, nxt, disturbances + (d,))
            options.append((value, [state] + path, [action] + acts, ds))
        return max(options, key=lambda item: (item[0], tuple(-d for d in item[3])))

    witness = worst(0, layers[0][0], ())
    assert feedback["worst_case_states"] == [list(state) for state in witness[1]]
    assert feedback["selected_actions"] == witness[2]
    assert feedback["worst_case_disturbances"] == witness[3]
    assert feedback["worst_terminal_gap_numerator"] == witness[0]
    return {"layers": layers, "transitions": transitions, "winning": expected[0],
            "actions": expected[1], "threshold": chosen, "witness": witness,
            "euler_max_abs_discrepancy": max_discrepancy, "padded_count": n}


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
    assert source["schema"] == "csl.env717-two-points-feedback/1"
    assert source["source_repository_commit"] == SOURCE_COMMIT
    assert source["source_file_blob"] == SOURCE_BLOB
    oracle, layers, backward = enumerate_game()
    feedback = feedback_oracle(source)
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
               "feedback_forward_layers": [[tuple(x / LATTICE_SCALE for x in state)
                                              for state in layer]
                                             for layer in feedback["layers"]],
               "feedback_backward_layers": [
                   [tuple(x / LATTICE_SCALE for x in state)
                    for i, state in enumerate(layer) if feedback["winning"][t][i]]
                   for t, layer in enumerate(feedback["layers"])],
               "feedback_trajectory": [tuple(x / LATTICE_SCALE for x in state)
                                       for state in feedback["witness"][1]],
               "feedback_threshold_numerator": feedback["threshold"],
               "feedback_threshold_denominator": 4_000_000,
               "feedback_max_abs_euler_discrepancy": feedback["euler_max_abs_discrepancy"],
               "terminal_target": "squared position gap <= minimax value",
               "intersection_semantics": "finite-catalogue state nodes in both forward layer and robust backward winning set"}
    return source, derived


def verify(executable: Path) -> tuple[dict, dict]:
    source = json.loads(subprocess.check_output([str(executable)], text=True))
    return verify_record(source)


def plot_svg(derived: dict) -> str:
    width, height = 1260, 700
    panels = [(75, 135, 520, 390, 0, 1, "Point 1 phase plane", "x1 position", "x2 velocity"),
              (665, 135, 520, 390, 2, 3, "Point 2 phase plane", "x3 position", "x4 velocity")]
    colors = ["#d6e7f0", "#56b4e9", "#00c49a", "#d9a441"]
    states_by_stage = derived["forward_layers"]
    groups_by_stage = derived["forward_groups"]
    back_by_stage = derived["robust_backward_layers"]
    trajectory = derived["trajectory"]
    feedback_trajectory = derived["feedback_trajectory"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Two points on parallel lines: forward reachability and robust backward sets</title>',
           '<desc id="desc">Forward reachable polytopes for each finite control prefix, robust backward winning nodes, their intersections, and one minimax trajectory, shown in both point phase planes.</desc>',
           '<rect width="100%" height="100%" fill="#111820"/>',
           '<text x="75" y="45" fill="#f4f1e8" font-family="sans-serif" font-size="27" font-weight="700">Two points on parallel lines · finite-action differential-game pilot</text>',
           '<text x="75" y="77" fill="#bac6ce" font-family="sans-serif" font-size="15">3 stages · fixed-plan minimax and CSL finite vertex feedback · exact scale-2000 state graph</text>']
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
                    terminal = stage == HORIZON
                    fill_opacity = "0.13" if terminal else "0.035"
                    stroke_opacity = "0.85" if terminal else "0.2"
                    stroke_width = "1.6" if terminal else "0.8"
                    out.append(f'<polygon points="{coords}" fill="{colors[stage]}" fill-opacity="{fill_opacity}" stroke="{colors[stage]}" stroke-opacity="{stroke_opacity}" stroke-width="{stroke_width}"/>')
        for stage, states in enumerate(states_by_stage):
            backward = {tuple(state) for state in back_by_stage[stage]}
            for state in states:
                inside = tuple(state) in backward
                color = "#f4a261" if inside else colors[stage]
                radius = 4.4 if inside else 2.3
                opacity = 0.92 if inside else 0.22
                out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="{radius}" fill="{color}" fill-opacity="{opacity}"/>')
        for states in derived["feedback_backward_layers"]:
            for state in states:
                out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="6.3" fill="none" stroke="#c77dff" stroke-width="1.5"/>')
        coords = " ".join(f'{px(state[xi]):.2f},{py(state[yi]):.2f}' for state in trajectory)
        out.append(f'<polyline points="{coords}" fill="none" stroke="#ff6b35" stroke-width="4" stroke-linejoin="round"/>')
        for state in trajectory:
            out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="5.5" fill="#ff6b35" stroke="#fff4e6" stroke-width="1.5"/>')
        feedback_coords = " ".join(f'{px(state[xi]):.2f},{py(state[yi]):.2f}' for state in feedback_trajectory)
        out.append(f'<polyline points="{feedback_coords}" fill="none" stroke="#57d9a3" stroke-width="3.5" stroke-dasharray="9 5" stroke-linejoin="round"/>')
        for state in feedback_trajectory:
            out.append(f'<circle cx="{px(state[xi]):.2f}" cy="{py(state[yi]):.2f}" r="4.8" fill="#57d9a3" stroke="#111820" stroke-width="1.4"/>')
        out.append(f'<text x="{x0+pw/2}" y="{y0+ph+48}" fill="#f4f1e8" font-family="sans-serif" font-size="14" text-anchor="middle">{xlabel}</text>')
        out.append(f'<text x="{x0-48}" y="{y0+ph/2}" fill="#f4f1e8" font-family="sans-serif" font-size="14" text-anchor="middle" transform="rotate(-90 {x0-48} {y0+ph/2})">{ylabel}</text>')
    out.extend(['<rect x="79" y="583" width="9" height="9" fill="#56b4e9" fill-opacity="0.4" stroke="#56b4e9"/><text x="95" y="592" fill="#d2dce1" font-family="sans-serif" font-size="13">Forward reachable polytopes by stage/control prefix</text>',
                '<rect x="79" y="607" width="12" height="10" fill="#d9a441" fill-opacity="0.3" stroke="#d9a441" stroke-width="1.5"/><text x="99" y="617" fill="#d2dce1" font-family="sans-serif" font-size="13">Stage 3 terminal reachable set (one projected set per control prefix)</text>',
                '<circle cx="650" cy="587" r="4" fill="#f4a261"/><text x="662" y="592" fill="#d2dce1" font-family="sans-serif" font-size="13">Fixed-plan forward ∩ backward vertices</text>',
                '<circle cx="650" cy="611" r="5" fill="none" stroke="#c77dff"/><text x="662" y="616" fill="#d2dce1" font-family="sans-serif" font-size="13">CSL feedback graph forward ∩ winning states</text>',
                '<line x1="79" y1="638" x2="105" y2="638" stroke="#ff6b35" stroke-width="4"/><text x="115" y="643" fill="#d2dce1" font-family="sans-serif" font-size="13">Open-loop worst-case trajectory</text>',
                '<line x1="470" y1="638" x2="496" y2="638" stroke="#57d9a3" stroke-width="3" stroke-dasharray="6 3"/><text x="506" y="643" fill="#d2dce1" font-family="sans-serif" font-size="13">First-admissible feedback selector worst case</text>',
                '<text x="75" y="674" fill="#93a4ae" font-family="sans-serif" font-size="12">Finite vertex graph only; neither trajectory nor winning nodes imply continuous-state feedback or an RL reproduction. Horizon: 0.3 s.</text>',
                '</svg>'])
    return "\n".join(out)


def report_page(source: dict, svg: str, host: dict) -> str:
    timing = source["timing"]
    feedback = source["feedback"]
    threshold = feedback["threshold_numerator"] / feedback["threshold_denominator"]
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Two-point minimax and finite feedback</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1320px;margin:auto;padding:2rem}}a{{color:#8bd3f7}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}</style><main><h1>Two points on parallel lines: reachability and minimax</h1><p>The report compares CSL finite-action minimax with CSL finite feedback on the same three-stage TwoPoints adaptation. The panels show `(x1,x2)=(position₁, velocity₁)` and `(x3,x4)=(position₂, velocity₂)`, including both open-loop and causal-feedback worst-case trajectories.</p><div>{svg}</div><p class="note"><strong>Scope:</strong> the source uses continuous actions over 10 seconds. This report uses three stages, actions `2.5a` for `a ∈ {{-1,0,1}}`, and disturbance vertices `d ∈ {{-1,0,1}}`. Its scale-2000 integer graph has exact transitions and a terminal squared-gap threshold of <code>{feedback['threshold_numerator']}/{feedback['threshold_denominator']} = {threshold:.8g}</code>. The Python checker independently rebuilds the graph, checks every transition and policy cell, verifies the threshold is minimal on the finite candidate set, and cross-checks the integer transitions against the source's ten binary64 Euler substeps (maximum absolute discrepancy {feedback['euler_max_abs_discrepancy']:.3g}, tolerance {feedback['euler_crosscheck_tolerance']:.1g}). Action is selected from the current state before the disturbance vertex is revealed. The solver returns feasible actions, not cost-optimal actions; the plotted selector chooses the first admissible action. The guarantee applies only to this exact finite vertex game, not continuous-state feedback or the original RL experiment.</p><p>Open-loop minimax squared gap: {source['objective_value']:.8g}; feedback threshold numerator/denominator: {feedback['threshold_numerator']}/{feedback['threshold_denominator']}. The finite-feedback solver considered {feedback['solve_count']} of {feedback['candidate_count']} distinct terminal gap candidates. Seven minimax solver-call observations after one warmup have median {timing['median_wall_ns']} ns; no comparative speed claim is supported. <a href="result.json">Result JSON</a> · <a href="figure-data.json">Figure data</a> · <a href="projections.svg">Standalone SVG</a></p><p>Upstream commit <code>{SOURCE_COMMIT}</code>; source blob <code>{SOURCE_BLOB}</code>. Runtime environment: {html.escape(host['os'])}, {html.escape(host['processor'])}, {host['logical_cpus']} logical CPUs.</p></main></html>'''


def processor_identity() -> tuple[str, str]:
    detected = platform.processor().strip()
    if detected:
        return detected, "platform.processor"
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                key_name, separator, value = line.partition(":")
                if separator and key_name.strip() in {"model name", "Hardware"} and value.strip():
                    return value.strip(), "/proc/cpuinfo"
        except OSError:
            pass
    return platform.machine() or "unavailable", "platform.machine fallback"


def render(executable: Path, output: Path | None) -> None:
    processor, processor_source = processor_identity()
    host = {"os": platform.platform(), "processor": processor,
            "processor_identity_source": processor_source,
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
    page = report_page(source, svg, host)
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

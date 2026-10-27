#!/usr/bin/env python3
"""Independently enumerate and render the finite UnequalGame pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import os
import platform
import statistics
import subprocess
from pathlib import Path

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "a05c7caafa8c36b44f75a8c3e3355677419af6c4"
HORIZON = 3
DT = 0.05
INITIAL = 1.0
U = (-2.0, 0.0, 2.0)
V = (-1.0, 0.0, 1.0)


def advance(x: float, u: float, v: float) -> float:
    return x + DT * (u + v)


def enumerate_game() -> dict:
    plans = []
    disturbances = list(itertools.product(V, repeat=HORIZON))
    for plan in itertools.product(U, repeat=HORIZON):
        cases = []
        for disturbance in disturbances:
            states = [INITIAL]
            for u, v in zip(plan, disturbance):
                states.append(advance(states[-1], u, v))
            cases.append((states[-1] ** 2, disturbance, states))
        plans.append((max(case[0] for case in cases), plan, cases))
    optimum = min(item[0] for item in plans)
    minimizing = [i for i, item in enumerate(plans) if item[0] <= optimum + 1e-12]

    layers = [{INITIAL}]
    groups = [{(): {INITIAL}}]
    for _ in range(HORIZON):
        next_groups = {}
        for prefix, states in groups[-1].items():
            for u in U:
                next_groups[prefix + (u,)] = {
                    advance(x, u, v) for x in states for v in V}
        groups.append(next_groups)
        layers.append({advance(x, u, v) for x in layers[-1] for u in U for v in V})

    backward = [set() for _ in range(HORIZON + 1)]
    backward[-1] = {x for x in layers[-1] if x * x <= optimum + 1e-12}
    for stage in range(HORIZON - 1, -1, -1):
        for x in layers[stage]:
            if any(all(advance(x, u, v) in backward[stage + 1] for v in V) for u in U):
                backward[stage].add(x)

    selected = plans[minimizing[0]]
    value, plan, cases = selected
    worst = next(case for case in cases if abs(case[0] - value) <= 1e-12)
    return {"optimum": optimum, "minimizing_indices": minimizing, "plans": plans,
            "selected_plan": plan, "selected_disturbance": worst[1],
            "trajectory": worst[2], "forward_layers": [sorted(layer) for layer in layers],
            "robust_backward_layers": [sorted(layer) for layer in backward],
            "forward_groups": [
                [{"control_prefix": list(prefix), "states": sorted(states)}
                 for prefix, states in sorted(stage.items())] for stage in groups]}


def verify_record(actual: dict) -> tuple[dict, dict]:
    assert actual["schema"] == "csl.env717-unequal-game-pilot/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    expected = enumerate_game()
    assert actual["plan_count"] == 27 and len(actual["plans"]) == 27
    assert actual["minimizing_plan_indices"] == expected["minimizing_indices"]
    assert math.isclose(actual["objective_value"], expected["optimum"], abs_tol=1e-12)
    for row, (value, plan, cases) in zip(actual["plans"], expected["plans"]):
        assert row["controls"] == list(plan)
        assert math.isclose(row["worst_terminal_squared_state"], value, abs_tol=1e-12)
        maximizers = [case[2][-1] for case in cases if math.isclose(case[0], value, abs_tol=1e-12)]
        assert any(math.isclose(row["maximizing_terminal_state"][0], x, abs_tol=1e-12)
                   for x in maximizers)
    assert expected["selected_plan"] == (-2.0, -2.0, -2.0)
    timing = actual["timing"]
    samples = timing["measured_wall_ns"]
    assert timing["warmup_calls"] == 1 and timing["measured_calls"] == 7
    assert len(samples) == 7 and all(type(value) is int and value > 0 for value in samples)
    ordered = sorted(samples)
    assert timing["median_wall_ns"] == ordered[3]
    assert timing["min_wall_ns"] == ordered[0] and timing["max_wall_ns"] == ordered[-1]
    assert len(expected["forward_layers"]) == HORIZON + 1
    assert INITIAL in expected["robust_backward_layers"][0]
    derived = {key: expected[key] for key in (
        "forward_layers", "robust_backward_layers", "forward_groups",
        "selected_plan", "selected_disturbance", "trajectory")}
    derived["terminal_target"] = f"x^2 <= {expected['optimum']:.12g}"
    return actual, derived


def plot_svg(data: dict, value: float) -> str:
    width, height = 1000, 620
    x0, y0, pw, ph = 100, 100, 820, 420
    all_values = [x for stage in data["forward_layers"] for x in stage]
    ymin, ymax = min(all_values) - 0.08, max(all_values) + 0.08
    tmax = HORIZON * DT
    px = lambda t: x0 + t / tmax * pw
    py = lambda x: y0 + ph - (x - ymin) / (ymax - ymin) * ph
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">UnequalGame: finite-action reachability and minimax</title>',
           '<desc id="desc">Time-position plot with forward reachable intervals, robust backward winning nodes and intersections, terminal target, and one worst-case minimax trajectory.</desc>',
           '<rect width="100%" height="100%" fill="#111820"/>',
           '<text x="60" y="42" fill="#f4f1e8" font-family="sans-serif" font-size="25" font-weight="700">UnequalGame · finite-action differential-game pilot</text>',
           f'<text x="60" y="72" fill="#bac6ce" font-family="sans-serif" font-size="14">3 stages · dt = {DT:g} s · 27 fixed control plans × 27 disturbance sequences · minimax terminal x² = {value:.6g}</text>']
    for tick in range(5):
        x = ymin + (ymax - ymin) * tick / 4
        out.append(f'<line x1="{x0}" y1="{py(x):.2f}" x2="{x0+pw}" y2="{py(x):.2f}" stroke="#293640"/>')
        out.append(f'<text x="{x0-10}" y="{py(x)+4:.2f}" fill="#bac6ce" font-family="sans-serif" font-size="12" text-anchor="end">{x:.3g}</text>')
    for stage in range(HORIZON + 1):
        t = stage * DT
        out.append(f'<line x1="{px(t):.2f}" y1="{y0}" x2="{px(t):.2f}" y2="{y0+ph}" stroke="#293640"/>')
        out.append(f'<text x="{px(t):.2f}" y="{y0+ph+24}" fill="#bac6ce" font-family="sans-serif" font-size="12" text-anchor="middle">{t:.2f}</text>')
    target = math.sqrt(value)
    visible_target_low = max(ymin, -target)
    visible_target_high = min(ymax, target)
    if visible_target_low <= visible_target_high:
        out.append(f'<rect x="{px(tmax)-18:.2f}" y="{py(visible_target_high):.2f}" width="36" height="{py(visible_target_low)-py(visible_target_high):.2f}" fill="#d9a441" fill-opacity="0.25"><title>Visible part of terminal target x² ≤ {value:.6g}</title></rect>')
    for stage, groups in enumerate(data["forward_groups"]):
        t = stage * DT
        for group in groups:
            states = group["states"]
            if states:
                opacity = "0.55" if stage == HORIZON else "0.2"
                out.append(f'<line x1="{px(t):.2f}" y1="{py(min(states)):.2f}" x2="{px(t):.2f}" y2="{py(max(states)):.2f}" stroke="#56b4e9" stroke-opacity="{opacity}" stroke-width="3"/>')
    for stage, states in enumerate(data["forward_layers"]):
        back = set(data["robust_backward_layers"][stage])
        t = stage * DT
        for x in states:
            if x in back:
                out.append(f'<circle cx="{px(t):.2f}" cy="{py(x):.2f}" r="5" fill="#f4a261" stroke="#fff" stroke-width="1"/>')
    trajectory = data["trajectory"]
    coords = " ".join(f'{px(i*DT):.2f},{py(x):.2f}' for i, x in enumerate(trajectory))
    out.append(f'<polyline points="{coords}" fill="none" stroke="#ff6b35" stroke-width="4" stroke-linejoin="round"/>')
    for i, x in enumerate(trajectory):
        out.append(f'<circle cx="{px(i*DT):.2f}" cy="{py(x):.2f}" r="5" fill="#ff6b35"/>')
    out.extend([f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#81909a"/>',
        f'<text x="{x0+pw/2}" y="{y0+ph+52}" fill="#f4f1e8" font-family="sans-serif" font-size="15" text-anchor="middle">Time (s)</text>',
        f'<text x="32" y="{y0+ph/2}" fill="#f4f1e8" font-family="sans-serif" font-size="15" text-anchor="middle" transform="rotate(-90 32 {y0+ph/2})">Position x</text>',
        '<text x="100" y="585" fill="#bac6ce" font-family="sans-serif" font-size="12">Blue: forward intervals by control prefix · gold: forward/backward intersection · orange: worst-case minimax trajectory · gold band: visible terminal target portion</text>',
        '</svg>'])
    return "\n".join(out)


def report_page(source: dict, svg: str) -> str:
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UnequalGame minimax pilot</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>UnequalGame: reachability and minimax</h1><p>CSL's finite-action minimax method exhausts 27 fixed control plans and all 27 adversarial disturbance sequences per plan. An independent enumeration replays every plan, its worst terminal state, the finite forward reachable sets, backward robust nodes, and a selected worst-case trajectory.</p><div>{svg}</div><p class="note"><strong>Adaptation:</strong> the upstream environment uses continuous controls and a 2-second horizon. This pilot uses three stages over 0.15 seconds and finite control/disturbance catalogues. The minimizer commits to an open-loop control sequence; the adversary chooses a full disturbance sequence. This is not a reproduction of the source RL training run.</p><p>Minimax squared terminal position: {source['objective_value']:.8g}. Seven single-threaded solver-call observations after one warmup have median {source['timing']['median_wall_ns']} ns and range {source['timing']['min_wall_ns']}–{source['timing']['max_wall_ns']} ns. No comparative speed claim is made. <a href="result.json">Result JSON</a> · <a href="figure-data.json">Figure data</a> · <a href="projections.svg">Standalone SVG</a></p><p>Source commit <code>{SOURCE_COMMIT}</code>; source blob <code>{SOURCE_BLOB}</code>. Runtime: {html.escape(source['environment']['compiler_id'])} {html.escape(source['environment']['compiler_version'])}, {html.escape(platform.platform())}.</p></main></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    actual = json.loads(subprocess.check_output([str(args.executable.resolve())], text=True))
    actual, derived = verify_record(actual)
    if args.output:
        output = args.output
        output.mkdir(parents=True, exist_ok=False)
        svg = plot_svg(derived, actual["objective_value"]) + "\n"
        capture = {"schema": "csl.env717-capture/1",
            "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "capture_environment": {"os": platform.platform(),
                "processor": platform.processor() or "unavailable",
                "processor_identity_source": "Python platform.processor; fallback unavailable",
                "logical_cpus": os.cpu_count()}}
        files = {"result.json": json.dumps(actual, indent=2) + "\n",
            "figure-data.json": json.dumps(derived, indent=2) + "\n",
            "capture.json": json.dumps(capture, indent=2) + "\n",
            "projections.svg": svg,
            "index.html": report_page(actual, svg[:-1])}
        files["README.md"] = ("# UnequalGame finite-action minimax pilot\n\n"
            "Source-attributed adaptation of the upstream UnequalGame differential game. "
            "This report uses a three-stage finite action catalogue over 0.15 seconds; "
            "the source uses continuous controls over two seconds. The captured result "
            "is an open-loop fixed-plan minimax value, not the continuous-action RL result.\n\n"
            f"Upstream commit: `{SOURCE_COMMIT}`. Source blob: `{SOURCE_BLOB}`. "
            "No license is declared by the upstream repository; this report re-expresses "
            "the equations and does not copy its implementation.\n")
        for name, content in files.items():
            (output / name).write_text(content, encoding="utf-8")
        sums = "".join(f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}\n"
                       for name in sorted(files))
        (output / "SHA256SUMS").write_text(sums, encoding="ascii")
    print(json.dumps({"objective_value": actual["objective_value"],
        "minimizing_plan_indices": actual["minimizing_plan_indices"],
        "source_commit": actual["source_commit"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

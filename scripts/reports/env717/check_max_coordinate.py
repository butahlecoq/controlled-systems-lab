#!/usr/bin/env python3
"""Independently replay and render the finite MaxCoordinateGame pilot."""
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

HORIZON = 3
DT = 0.1
INITIAL = (0.0, 0.2, 0.0)
CATALOGUE = (-1.0, 1.0)
DIRECTIONS = ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
              (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))


def source_step(state: tuple[float, ...], u: float, v: float) -> tuple[float, ...]:
    """Replay the source's 100 simultaneous Euler updates, not the grouped map."""
    result = list(state)
    h = DT / 100
    for _ in range(100):
        old = result[:]
        result[0] = old[0] + h
        result[1] = old[1] + (old[2] + v) * h
        result[2] = old[2] + (-old[1] + u) * h
    return tuple(result)


def enumerate_game() -> dict:
    plans = list(itertools.product(CATALOGUE, repeat=HORIZON))
    disturbances = list(itertools.product(CATALOGUE, repeat=HORIZON))
    plan_rows = []
    cases_by_plan = []
    for plan in plans:
        cases = []
        for disturbance in disturbances:
            states = [INITIAL]
            for u, v in zip(plan, disturbance):
                states.append(source_step(states[-1], u, v))
            terminal = states[-1]
            cases.append({"disturbance": disturbance, "states": states,
                          "terminal": terminal, "reward": max(abs(terminal[1]), abs(terminal[2]))})
        cases_by_plan.append(cases)
        plan_rows.append({"controls": plan, "worst_reward": max(c["reward"] for c in cases)})
    optimum = min(row["worst_reward"] for row in plan_rows)
    minimizing = [i for i, row in enumerate(plan_rows) if row["worst_reward"] <= optimum + 1e-12]
    selected_index = minimizing[0]
    selected = plan_rows[selected_index]
    worst = next(c for c in cases_by_plan[selected_index]
                 if abs(c["reward"] - selected["worst_reward"]) <= 1e-12)
    forward = [{INITIAL}]
    for _ in range(HORIZON):
        forward.append({source_step(state, u, v) for state in forward[-1]
                        for u in CATALOGUE for v in CATALOGUE})
    backward = [set() for _ in range(HORIZON + 1)]
    backward[-1] = {state for state in forward[-1]
                    if max(abs(state[1]), abs(state[2])) <= optimum + 1e-12}
    for stage in range(HORIZON - 1, -1, -1):
        for state in forward[stage]:
            if any(all(source_step(state, u, v) in backward[stage + 1]
                       for v in CATALOGUE) for u in CATALOGUE):
                backward[stage].add(state)
    return {"plans": plan_rows, "optimum": optimum, "minimizing_indices": minimizing,
            "selected_plan": selected["controls"], "selected_disturbance": worst["disturbance"],
            "trajectory": worst["states"], "forward_layers": [sorted(layer) for layer in forward],
            "backward_layers": [sorted(layer) for layer in backward],
            "component_scores": [[max(sum(a*b for a, b in zip(direction, c["terminal"]))
                for c in cases) for direction in DIRECTIONS] for cases in cases_by_plan]}


def verify_record(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-max-coordinate-pilot/1"
    assert actual["source_repository_commit"] == "f4d76c60f4003f50954174e96eafd8e514bd5441"
    assert actual["source_file_blob"] == "d509a1457023b14516d2789bd3033dbaa4110017"
    expected = enumerate_game()
    components = actual["component_results"]
    assert len(components) == len(DIRECTIONS)
    for component, direction in zip(components, DIRECTIONS):
        assert tuple(component["direction"]) == direction
        assert len(component["plans"]) == 8
    for i, scores in enumerate(expected["component_scores"]):
        actual_scores = [components[j]["plans"][i]["worst_signed_coordinate"]
                         for j in range(len(DIRECTIONS))]
        for value, score in zip(actual_scores, scores):
            assert math.isclose(value, score, abs_tol=1e-11)
        assert math.isclose(max(actual_scores), expected["plans"][i]["worst_reward"], abs_tol=1e-11)
    assert expected["minimizing_indices"]
    assert INITIAL in expected["backward_layers"][0]
    assert math.isclose(actual["objective_value"], expected["optimum"], abs_tol=1e-11)
    assert math.isclose(actual["objective_value"], min(
        max(component["plans"][i]["worst_signed_coordinate"] for component in components)
        for i in range(8)), abs_tol=1e-11)
    return expected


def svg(data: dict) -> str:
    width, height = 860, 620
    x0, y0, pw, ph = 90, 45, 700, 490
    states = [point for layer in data["forward_layers"] for point in layer]
    max_abs = max(max(abs(p[1]), abs(p[2])) for p in states) * 1.12
    def px(y): return x0 + (y + max_abs) / (2 * max_abs) * pw
    def py(z): return y0 + ph - (z + max_abs) / (2 * max_abs) * ph
    colors = ("#56b4e9", "#56b4e9", "#56b4e9", "#56b4e9")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="MaxCoordinateGame reachable phase-plane sets and worst-case trajectory">',
           '<rect width="100%" height="100%" fill="#111820"/>']
    for stage, layer in enumerate(data["forward_layers"]):
        radius = 2.3 if stage < HORIZON else 3.5
        for point in layer:
            robust = point in set(data["backward_layers"][stage])
            fill = "#e9c46a" if robust else colors[stage]
            opacity = "0.72" if robust else ("0.25" if stage < HORIZON else "0.65")
            out.append(f'<circle cx="{px(point[1]):.2f}" cy="{py(point[2]):.2f}" r="{radius}" fill="{fill}" fill-opacity="{opacity}"/>')
    trajectory = data["trajectory"]
    path = " ".join(f'{px(p[1]):.2f},{py(p[2]):.2f}' for p in trajectory)
    out.append(f'<polyline points="{path}" fill="none" stroke="#ff6b35" stroke-width="4"/>')
    for p in trajectory:
        out.append(f'<circle cx="{px(p[1]):.2f}" cy="{py(p[2]):.2f}" r="5" fill="#ff6b35"/>')
    out.extend([f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#81909a"/>',
        f'<text x="{x0+pw/2}" y="{y0+ph+42}" fill="#f4f1e8" font-family="sans-serif" font-size="16" text-anchor="middle">y</text>',
        f'<text x="30" y="{y0+ph/2}" fill="#f4f1e8" font-family="sans-serif" font-size="16" text-anchor="middle" transform="rotate(-90 30 {y0+ph/2})">z</text>',
        '<text x="90" y="590" fill="#bac6ce" font-family="sans-serif" font-size="13">Blue: forward reachable states · gold: robust backward-winning intersection · orange: worst-case minimax path</text>', '</svg>'])
    return "\n".join(out)


def page(result: dict, figure: str, host: dict) -> str:
    upstream = ("https://github.com/imm-rl-lab/optimal_control/blob/"
        "f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py")
    source = f"https://github.com/butahlecoq/controlled-systems-lab/tree/{result['source_commit']}"
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MaxCoordinateGame minimax pilot</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>MaxCoordinateGame: reachability and minimax</h1><p>CSL finite-action minimax solves the source oscillator on a short finite action catalogue. The source reward max(|y|,|z|) is represented exactly as the maximum of four signed linear terminal objectives; the four component values are combined per fixed control plan before selecting the minimum.</p><div>{figure}</div><p class="note"><strong>Adaptation:</strong> the source uses continuous controls over 4 seconds. This pilot uses three 0.1-second stages, controls and disturbances in {{−1,+1}}, and an open-loop control plan against a full adversarial sequence. It is not a reproduction of the original RL training run. The independent checker replays the source's 100 simultaneous Euler substeps per stage.</p><p>Minimax terminal reward: {result['objective_value']:.10g}. The figure shows the 2D oscillator phase plane (y,z), all forward reachable states, the robust backward-winning intersection, and one worst-case path. <a href="result.json">Result JSON</a> · <a href="figure-data.json">Figure data</a> · <a href="capture.json">Capture environment</a> · <a href="projections.svg">Standalone SVG</a></p><p>Upstream source: <a href="{upstream}">MaxCoordinateGame.py</a> at commit <code>f4d76c60f4003f50954174e96eafd8e514bd5441</code> (blob <code>d509a1457023b14516d2789bd3033dbaa4110017</code>). CSL measured source: <a href="{source}"><code>{result['source_commit']}</code></a>. Runtime OS: {html.escape(host['os'])}.</p></main></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    actual = json.loads(subprocess.check_output([str(args.executable.resolve())], text=True))
    derived = verify_record(actual)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        figure = svg(derived) + "\n"
        files = {
            "result.json": (json.dumps(actual, indent=2) + "\n").encode(),
            "figure-data.json": (json.dumps(derived, indent=2) + "\n").encode(),
            "projections.svg": figure.encode(),
        }
        host = {"os": platform.platform(), "processor": platform.processor() or "unavailable",
                "processor_identity_source": "Python platform.processor; fallback unavailable",
                "logical_cpus": os.cpu_count() or 0}
        capture = {"schema": "csl.env717-capture/1",
            "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "capture_environment": host}
        files["capture.json"] = (json.dumps(capture, indent=2) + "\n").encode()
        files["index.html"] = page(actual, figure[:-1], host).encode()
        files["README.md"] = ("# MaxCoordinateGame finite-action minimax pilot\n\n"
            "Source-attributed finite-game adaptation of the RL oscillator. The source reward is "
            "`max(|y|,|z|)`; the report combines four signed linear terminal objectives per fixed plan. "
            "The source uses continuous controls and a 4 s horizon; this pilot uses three 0.1 s stages "
            "with catalogues `{-1,+1}`. It is not an RL reproduction.\n\n"
            "The independent checker directly replays all 100 explicit-Euler substeps per stage, all "
            "8 fixed plans, and all 8 disturbance sequences per plan. The SVG shows the phase plane, "
            "forward reachable sets, robust backward-winning intersection, and a worst-case path.\n\n"
            "Upstream source: [MaxCoordinateGame.py](https://github.com/imm-rl-lab/optimal_control/blob/"
            "f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py), "
            "blob `d509a1457023b14516d2789bd3033dbaa4110017`. No license is declared; this report re-expresses "
            "the equations. Timings are descriptive only.\n").encode()
        files["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(value).hexdigest()}  {name}\n"
            for name, value in sorted(files.items()) if name != "SHA256SUMS").encode("ascii")
        for name, content in files.items():
            (args.output / name).write_bytes(content)
        print(f"verified {len(derived['plans'])} fixed plans; minimax reward {derived['optimum']:.12g}")
    else:
        print(f"verified {len(derived['plans'])} fixed plans; minimax reward {derived['optimum']:.12g}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently replay and render the finite SphereGame pilot."""
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
INITIAL = (0.0, 0.0, 0.5)
U = (-0.25, 0.0, 0.25)
V = (-0.5, 0.0, 0.5)
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "dd8ff3ce718570f05288dc4d8d343a8784ca2327"
SCENARIO = Path(__file__).resolve().parents[3] / "benchmarks/scenarios/env717-sphere-game-pilot-v1.json"


def advance(state: tuple[float, ...], u: float, v: float) -> tuple[float, ...]:
    return state[0] + DT, state[1] + DT * v, state[2] + DT * u


def score(state: tuple[float, ...]) -> float:
    return math.hypot(state[1], state[2])


def enumerate_game() -> dict:
    plans = []
    disturbances = list(itertools.product(V, repeat=HORIZON))
    for plan in itertools.product(U, repeat=HORIZON):
        cases = []
        for disturbance in disturbances:
            states = [INITIAL]
            for u, v in zip(plan, disturbance):
                states.append(advance(states[-1], u, v))
            cases.append({"disturbance": disturbance, "states": states,
                          "terminal": states[-1], "norm": score(states[-1])})
        worst = max(case["norm"] for case in cases)
        maximizers = [case for case in cases if math.isclose(case["norm"], worst, rel_tol=0.0, abs_tol=1e-12)]
        plans.append({"controls": plan, "worst_norm": worst, "cases": cases,
                      "maximizers": maximizers})
    optimum = min(plan["worst_norm"] for plan in plans)
    minimizing = [i for i, plan in enumerate(plans)
                  if plan["worst_norm"] <= optimum + 1e-12]
    selected = plans[minimizing[0]]
    worst = selected["maximizers"][0]
    forward = [{INITIAL}]
    for _ in range(HORIZON):
        forward.append({advance(state, u, v) for state in forward[-1]
                        for u in U for v in V})
    backward = [set() for _ in range(HORIZON + 1)]
    backward[-1] = {state for state in forward[-1]
                    if score(state) <= optimum + 1e-12}
    for stage in range(HORIZON - 1, -1, -1):
        for state in forward[stage]:
            if any(all(advance(state, u, v) in backward[stage + 1] for v in V) for u in U):
                backward[stage].add(state)
    return {"plans": plans, "optimum": optimum, "minimizing_indices": minimizing,
            "selected_plan": selected["controls"], "selected_disturbance": worst["disturbance"],
            "trajectory": worst["states"], "forward_layers": [sorted(layer) for layer in forward],
            "backward_layers": [sorted(layer) for layer in backward]}


def verify_record(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-sphere-game-pilot/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    scenario_bytes = SCENARIO.read_bytes()
    scenario = json.loads(scenario_bytes)
    assert actual["scenario_file"] == "benchmarks/scenarios/env717-sphere-game-pilot-v1.json"
    assert actual["scenario_sha256"] == hashlib.sha256(scenario_bytes).hexdigest()
    assert scenario["schema"] == "csl.env717-sphere-game-input/1"
    assert scenario["scenario_id"] == actual["case_id"]
    assert scenario["source"]["commit"] == actual["source_repository_commit"]
    assert scenario["source"]["blob"] == actual["source_file_blob"]
    assert scenario["source_model"]["state_order"] == actual["state_order"]
    for field in ("initial_state", "dt_seconds", "horizon_seconds", "control_u_bounds",
                  "disturbance_v_bounds", "dynamics", "reward"):
        assert scenario["source_model"][field] == actual["source_model"][field]
    assert scenario["adaptation"] == actual["adaptation"]
    assert scenario["numerics"] == actual["numerics"]
    model = actual["source_model"]
    assert model["initial_state"] == list(INITIAL)
    assert math.isclose(model["dt_seconds"], DT, rel_tol=0.0, abs_tol=1e-15)
    assert model["horizon_seconds"] == 8.0
    assert model["control_u_bounds"] == [-0.25, 0.25]
    assert model["disturbance_v_bounds"] == [-0.5, 0.5]
    assert model["dynamics"] == "time'=1; y'=v; z'=u"
    assert model["reward"] == "sqrt(y^2+z^2)-4 at termination"
    adaptation = actual["adaptation"]
    assert adaptation["horizon_steps"] == HORIZON
    assert math.isclose(adaptation["horizon_seconds"], HORIZON * DT, rel_tol=0.0, abs_tol=1e-15)
    assert adaptation["control_catalogue"] == list(U)
    assert adaptation["disturbance_catalogue"] == list(V)
    assert adaptation["information_pattern"] == "fixed open-loop control plan versus full adversarial sequence"
    assert adaptation["backward_geometry_information_pattern"] == "causal state-feedback control on the finite reachable graph; separate from the fixed-plan minimax solve"
    expected = enumerate_game()
    assert actual["plan_count"] == len(expected["plans"]) == 27
    assert actual["minimizing_plan_indices"] == expected["minimizing_indices"]
    assert math.isclose(actual["objective_value"], expected["optimum"], rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(actual["source_reward_value"], expected["optimum"] - 4.0, rel_tol=0.0, abs_tol=1e-12)
    assert len(actual["plans"]) == 27
    for actual_plan, expected_plan in zip(actual["plans"], expected["plans"]):
        assert actual_plan["controls"] == list(expected_plan["controls"])
        assert math.isclose(actual_plan["worst_terminal_norm"], expected_plan["worst_norm"], rel_tol=0.0, abs_tol=1e-12)
        terminal = tuple(actual_plan["maximizing_terminal_state"])
        assert any(terminal == tuple(case["terminal"]) for case in expected_plan["maximizers"])
    assert INITIAL in expected["backward_layers"][0]
    return expected


def svg(data: dict) -> str:
    width, height = 860, 620
    x0, y0, pw, ph = 90, 45, 700, 490
    states = [point for layer in data["forward_layers"] for point in layer]
    bound = max(max(abs(p[1]), abs(p[2])) for p in states) * 1.12
    def px(y): return x0 + (y + bound) / (2 * bound) * pw
    def py(z): return y0 + ph - (z + bound) / (2 * bound) * ph
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="SphereGame reachable phase-plane sets and minimax trajectory">',
           '<rect width="100%" height="100%" fill="#111820"/>']
    for stage, layer in enumerate(data["forward_layers"]):
        winning = set(data["backward_layers"][stage])
        for point in layer:
            good = point in winning
            color = "#e9c46a" if good else "#56b4e9"
            opacity = "0.72" if good else ("0.24" if stage < HORIZON else "0.62")
            radius = 2.4 if stage < HORIZON else 3.5
            out.append(f'<circle cx="{px(point[1]):.2f}" cy="{py(point[2]):.2f}" r="{radius}" fill="{color}" fill-opacity="{opacity}"/>')
    trajectory = data["trajectory"]
    path = " ".join(f'{px(p[1]):.2f},{py(p[2]):.2f}' for p in trajectory)
    out.append(f'<polyline points="{path}" fill="none" stroke="#ff6b35" stroke-width="4"/>')
    for point in trajectory:
        out.append(f'<circle cx="{px(point[1]):.2f}" cy="{py(point[2]):.2f}" r="5" fill="#ff6b35"/>')
    out.extend([f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#81909a"/>',
        f'<text x="{x0+pw/2}" y="{y0+ph+42}" fill="#f4f1e8" font-family="sans-serif" font-size="16" text-anchor="middle">y</text>',
        f'<text x="30" y="{y0+ph/2}" fill="#f4f1e8" font-family="sans-serif" font-size="16" text-anchor="middle" transform="rotate(-90 30 {y0+ph/2})">z</text>',
        '<text x="90" y="590" fill="#bac6ce" font-family="sans-serif" font-size="13">Blue: forward states · gold: causal feedback-winning nodes at open-loop threshold · orange: fixed-plan worst-case path</text>', '</svg>'])
    return "\n".join(out)


def page(result: dict, figure: str, host: dict) -> str:
    upstream = f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/Environments/SphereGame/SphereGame.py"
    source = f"https://github.com/butahlecoq/controlled-systems-lab/tree/{result['source_commit']}"
    timing = result["timing"]
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SphereGame minimax pilot</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>SphereGame: reachability and minimax</h1><p>The source reward is the terminal Euclidean norm of (y,z) minus 4. CSL's residual-norm terminal objective represents the norm directly; subtracting 4 preserves the minimax plan and gives the source reward value.</p><div>{figure}</div><p class="note"><strong>Adaptation:</strong> the source uses continuous controls over 8 seconds. This pilot uses three 0.1-second stages and finite catalogues drawn from the source action bounds. The controller commits to an open-loop plan before the disturbance sequence is chosen. This is not a reproduction of the original RL run.</p><p>Minimax norm: {result['objective_value']:.10g}; source reward: {result['source_reward_value']:.10g}. Gold points show a separate causal state-feedback winning set at the fixed-plan minimax threshold; orange is the worst-case path for the selected fixed plan.</p><p>Numerics: {html.escape(result['numerics']['arithmetic'])}; absolute decision/replay tolerances are 1e-12. Scenario input SHA-256: <code>{result['scenario_sha256']}</code>.</p><p>Timing: {timing['elapsed_ns']} ns for one solver call (zero warmups, n=1); request setup and JSON assembly are excluded. This is descriptive only, with no speed comparison.</p><p><a href="result.json">Result JSON</a> · <a href="scenario.json">Scenario input</a> · <a href="figure-data.json">Figure data</a> · <a href="capture.json">Capture environment</a> · <a href="projections.svg">Standalone SVG</a></p><p>Upstream source: <a href="{upstream}">SphereGame.py</a> at commit <code>{SOURCE_COMMIT}</code> (blob <code>{SOURCE_BLOB}</code>). CSL source: <a href="{source}"><code>{result['source_commit']}</code></a>. Runtime OS: {html.escape(host['os'])}.</p></main></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    actual = json.loads(subprocess.check_output([str(args.executable.resolve())], text=True))
    derived = verify_record(actual)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        scenario_bytes = SCENARIO.read_bytes()
        figure = svg(derived) + "\n"
        files = {
            "result.json": (json.dumps(actual, indent=2) + "\n").encode(),
            "scenario.json": scenario_bytes,
            "figure-data.json": (json.dumps(derived, indent=2) + "\n").encode(),
            "projections.svg": figure.encode(),
        }
        host = {"os": platform.platform(), "processor": platform.processor() or "unavailable",
                "processor_identity_source": "Python platform.processor; fallback unavailable",
                "logical_cpus": os.cpu_count() or 0}
        capture = {"schema": "csl.env717-capture/1",
            "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scenario_sha256": actual["scenario_sha256"],
            "capture_environment": host}
        files["capture.json"] = (json.dumps(capture, indent=2) + "\n").encode()
        files["index.html"] = page(actual, figure[:-1], host).encode()
        files["README.md"] = ("# SphereGame finite-action minimax pilot\n\n"
            "Source-attributed finite-game adaptation of the RL differential game. Source reward is "
            "`sqrt(y^2+z^2)-4`; the residual-norm minimax value is reduced by 4 for the source reward. "
            "The source uses continuous controls over 8 seconds; this pilot uses three stages over 0.3 s "
            "and finite catalogues `u={-0.25,0,0.25}`, `v={-0.5,0,0.5}`. It is not an RL reproduction.\n\n"
            "The independent checker replays all 27 fixed plans and 27 disturbance sequences per plan. "
            "The phase-plane figure shows forward states, a separate causal feedback winning set, and an "
            "open-loop worst-case path. The report records the binary64 arithmetic profile, all 1e-12 "
            "decision/replay tolerances, and the SHA-256 of the versioned scenario input.\n\n"
            f"Upstream source: [SphereGame.py](https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/Environments/SphereGame/SphereGame.py), "
            f"blob `{SOURCE_BLOB}`. No upstream license is declared; this report re-expresses its equations.\n").encode()
        files["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(value).hexdigest()}  {name}\n"
            for name, value in sorted(files.items()) if name != "SHA256SUMS").encode("ascii")
        for name, content in files.items():
            (args.output / name).write_bytes(content)
    print(f"verified 27 fixed plans; minimax norm {derived['optimum']:.12g}; source reward {derived['optimum']-4:.12g}")


if __name__ == "__main__":
    main()

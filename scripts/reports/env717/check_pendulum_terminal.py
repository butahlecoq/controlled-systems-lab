#!/usr/bin/env python3
"""Independently check and render the PendulumTerminal local-linear pilot."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "4c3ef514524fa98fab53b2de18dfa9127316263f"
STEP = 0.05
INITIAL = (0.25, 0.0)
ACTIONS = (-1.0, 0.0, 1.0)
HORIZON = 4
TOLERANCE = 2e-12


def close(actual: float, expected: float, field: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=TOLERANCE):
        raise ValueError(f"{field}: {actual!r} != {expected!r}")


def linear_step(state: tuple[float, float], action: float) -> tuple[float, float]:
    theta, theta_dot = state
    next_theta_dot = 0.75 * theta + theta_dot + 0.3 * action
    next_theta = 1.0375 * theta + 0.05 * theta_dot + 0.015 * action
    return next_theta, next_theta_dot


def source_step(state: tuple[float, float], action: float) -> tuple[float, float]:
    theta, theta_dot = state
    torque = 2.0 * action
    next_theta_dot = theta_dot + (15.0 * math.sin(theta) + 3.0 * torque) * STEP
    return theta + next_theta_dot * STEP, next_theta_dot


def source_cost(state: tuple[float, float], action: float) -> float:
    theta, theta_dot = state
    torque = 2.0 * action
    return theta * theta + 0.1 * theta_dot * theta_dot + 0.001 * torque * torque


def replay_source(actions: tuple[float, ...]) -> tuple[list[list[float]], float]:
    state = INITIAL
    states = [[0.0, *state]]
    cost = 0.0
    for action in actions:
        cost += source_cost(state, action)
        state = source_step(state, action)
        states.append([len(states) * STEP, *state])
    return states, cost


def linearized_layers() -> list[list[list[float]]]:
    layers: list[list[list[float]]] = [[[INITIAL[0], INITIAL[1]]]]
    for stage in range(1, HORIZON + 1):
        states = []
        for prefix in itertools.product(ACTIONS, repeat=stage):
            state = INITIAL
            for action in prefix:
                state = linear_step(state, action)
            states.append([state[0], state[1]])
        layers.append(states)
    return layers


def verify(record: dict) -> dict:
    if record.get("schema") != "csl.env717-pendulum-terminal-pilot/1":
        raise ValueError("unexpected result schema")
    if record.get("source_repository_commit") != SOURCE_COMMIT:
        raise ValueError("upstream source commit changed")
    if record.get("source_file_blob") != SOURCE_BLOB:
        raise ValueError("upstream PendulumTerminal source blob changed")
    if record.get("plan_count") != len(ACTIONS) ** HORIZON:
        raise ValueError("finite plan count does not match the declared catalogue")

    plans = record.get("plans")
    if not isinstance(plans, list) or len(plans) != record["plan_count"]:
        raise ValueError("all solver plan records must be present")
    expected_sequences = set(itertools.product(range(len(ACTIONS)), repeat=HORIZON))
    by_sequence: dict[tuple[int, ...], dict] = {}
    for plan in plans:
        indices = tuple(plan["action_indices"])
        if indices in by_sequence:
            raise ValueError(f"duplicate plan identity {indices}")
        by_sequence[indices] = plan
        if len(indices) != HORIZON or any(i < 0 or i >= len(ACTIONS) for i in indices):
            raise ValueError("plan contains invalid action indices")
        controls = tuple(ACTIONS[i] for i in indices)
        if tuple(plan["actions"]) != controls:
            raise ValueError("action values do not match catalogue indices")
        state = INITIAL
        expected_states = [[state[0], state[1]]]
        for action in controls:
            state = linear_step(state, action)
            expected_states.append([state[0], state[1]])
        for stage, (actual, expected) in enumerate(zip(plan["predicted_states"], expected_states)):
            if len(actual) != 2:
                raise ValueError("predicted states must contain theta and theta_dot")
            close(actual[0], expected[0], f"plan {indices} stage {stage} theta")
            close(actual[1], expected[1], f"plan {indices} stage {stage} theta_dot")
        expected_objective = state[0] ** 2 + 0.1 * state[1] ** 2
        close(plan["linearized_terminal_objective"], expected_objective,
              f"plan {indices} terminal objective")

    if set(by_sequence) != expected_sequences:
        raise ValueError("solver output does not cover every catalogue-index history")
    best_linear = min(plan["linearized_terminal_objective"] for plan in plans)
    close(record["linearized_objective_value"], best_linear, "linearized optimum")
    winners = {tuple(by_sequence_index["action_indices"])
               for index in record["linearized_minimizing_plan_indices"]
               for by_sequence_index in [plans[index]]}
    expected_winners = {sequence for sequence, plan in by_sequence.items()
                        if plan["linearized_terminal_objective"] == best_linear}
    if winners != expected_winners:
        raise ValueError("solver minimizers disagree with independent exhaustive linear enumeration")

    source_rows = []
    for index_sequence in sorted(expected_sequences):
        controls = tuple(ACTIONS[i] for i in index_sequence)
        trajectory, cost = replay_source(controls)
        source_rows.append((cost, index_sequence, controls, trajectory))
    source_optimum = min(row[0] for row in source_rows)
    source_winners = [row for row in source_rows
                      if math.isclose(row[0], source_optimum, rel_tol=0.0, abs_tol=1e-14)]
    if len(source_winners) != 1:
        raise ValueError(f"expected one source-catalogue minimizer, found {len(source_winners)}")

    selected_rows = [row for row in source_rows if row[1] in winners]
    if not selected_rows:
        raise ValueError("linearized optimizer selected no source replay")
    selected = min(selected_rows, key=lambda row: row[0])
    reference = source_winners[0]
    gap = selected[0] - source_optimum
    if gap < -1e-12:
        raise ValueError("candidate source cost is below the independent catalogue minimum")
    record["independent_source_catalogue_oracle"] = {
        "method": "exhaustive source-map replay over every fixed four-action sequence",
        "plan_count": len(source_rows),
        "objective": "sum of PendulumTerminal.step per-step costs before each transition",
        "minimum_cost": source_optimum,
        "minimizing_action_indices": list(reference[1]),
        "minimizing_actions": list(reference[2]),
        "minimizing_trajectory_time_theta_theta_dot": reference[3],
    }
    record["linearized_plan_source_replay"] = {
        "action_indices": list(selected[1]),
        "actions": list(selected[2]),
        "source_accumulated_cost": selected[0],
        "source_cost_gap_from_finite_catalogue_optimum": gap,
        "relative_gap": gap / source_optimum if source_optimum else 0.0,
        "trajectory_time_theta_theta_dot": selected[3],
    }
    record["linearized_reachable_layers_theta_theta_dot"] = linearized_layers()
    return record


def svg_plot(record: dict) -> str:
    width, height = 1080, 760
    left, right, top, bottom = 110, 1020, 86, 620
    layers = record["linearized_reachable_layers_theta_theta_dot"]
    trajectories = [record["linearized_plan_source_replay"]["trajectory_time_theta_theta_dot"],
                    record["independent_source_catalogue_oracle"]["minimizing_trajectory_time_theta_theta_dot"]]
    all_points = [(point[0], point[1]) for layer in layers for point in layer]
    all_points += [(point[1], point[2]) for trajectory in trajectories for point in trajectory]
    all_points += [(0.0, 0.0)]
    xmin, xmax = min(p[0] for p in all_points), max(p[0] for p in all_points)
    ymin, ymax = min(p[1] for p in all_points), max(p[1] for p in all_points)
    xpad = max((xmax - xmin) * 0.08, 0.025)
    ypad = max((ymax - ymin) * 0.08, 0.05)
    xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad

    def xy(theta: float, velocity: float) -> tuple[float, float]:
        x = left + (theta - xmin) / (xmax - xmin) * (right - left)
        y = bottom - (velocity - ymin) / (ymax - ymin) * (bottom - top)
        return x, y

    colors = ("#80a7bd", "#86b8c7", "#9ec9c6", "#dfb86b", "#f4a261")
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
              '<title id="title">PendulumTerminal affine reachability and nonlinear replay</title>',
              '<desc id="desc">Four-stage finite-action reachability in angle and angular velocity, with the local affine plan and the independently enumerated nonlinear source-map plan.</desc>',
              '<rect width="100%" height="100%" fill="#111820"/>',
              '<text x="110" y="38" fill="#f4f1e8" font-size="25" font-family="sans-serif">PendulumTerminal · four-step finite-action pilot</text>',
              '<text x="110" y="62" fill="#aab7c2" font-size="14" font-family="sans-serif">Projection: θ (rad) × θ̇ (rad/s) · source-map replay uses the declared semi-implicit Euler step</text>']
    for tick in range(6):
        x = left + tick * (right - left) / 5
        y = top + tick * (bottom - top) / 5
        xvalue = xmin + tick * (xmax - xmin) / 5
        yvalue = ymax - tick * (ymax - ymin) / 5
        pieces.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#293844"/>')
        pieces.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#293844"/>')
        pieces.append(f'<text x="{x:.2f}" y="{bottom + 24}" text-anchor="middle" fill="#c5d0d8" font-size="12" font-family="sans-serif">{xvalue:.3f}</text>')
        pieces.append(f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" fill="#c5d0d8" font-size="12" font-family="sans-serif">{yvalue:.3f}</text>')
    pieces.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#d8e1e8"/>')
    pieces.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#d8e1e8"/>')
    pieces.append(f'<text x="{(left + right) / 2}" y="{bottom + 52}" text-anchor="middle" fill="#f4f1e8" font-size="16" font-family="sans-serif">θ (rad)</text>')
    pieces.append(f'<text x="28" y="{(top + bottom) / 2}" transform="rotate(-90 28 {(top + bottom) / 2})" text-anchor="middle" fill="#f4f1e8" font-size="16" font-family="sans-serif">θ̇ (rad/s)</text>')

    for stage, layer in enumerate(layers):
        color = colors[min(stage, len(colors) - 1)]
        radius = 3.8 if stage == HORIZON else 3.1
        for theta, velocity in layer:
            x, y = xy(theta, velocity)
            pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}" opacity="0.44"/>')

    def polyline(trajectory: list[list[float]], color: str, dash: str, width_value: float) -> None:
        coords = " ".join(f"{xy(point[1], point[2])[0]:.2f},{xy(point[1], point[2])[1]:.2f}" for point in trajectory)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        pieces.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width_value}"{dash_attr}/>')
        for point in trajectory:
            x, y = xy(point[1], point[2])
            pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="{color}"/>')

    selected = record["linearized_plan_source_replay"]
    source_best = record["independent_source_catalogue_oracle"]
    predicted = next(plan["predicted_states"] for plan in record["plans"]
                     if plan["action_indices"] == selected["action_indices"])
    polyline([[i * STEP, *state] for i, state in enumerate(predicted)], "#f4a261", "4 4", 2.3)
    polyline(selected["trajectory_time_theta_theta_dot"], "#69b7e3", "", 3.2)
    polyline(source_best["minimizing_trajectory_time_theta_theta_dot"], "#84d69b", "8 4", 3.0)
    tx, ty = xy(0.0, 0.0)
    pieces.append(f'<path d="M {tx - 7:.2f} {ty - 7:.2f} L {tx + 7:.2f} {ty + 7:.2f} M {tx - 7:.2f} {ty + 7:.2f} L {tx + 7:.2f} {ty - 7:.2f}" stroke="#fa6e59" stroke-width="3"/>')

    legend = [("#80a7bd", "Affine-model forward reachable states"),
              ("#f4a261", "Surrogate prediction for selected plan"),
              ("#69b7e3", "Selected plan replayed on nonlinear source map"),
              ("#84d69b", "Best source-map plan in the same finite catalogue"),
              ("#fa6e59", "Target origin (visual reference only)")]
    for index, (color, label) in enumerate(legend):
        y = 680 + (index % 2) * 28
        x = 110 + (index // 2) * 320
        if color == "#fa6e59":
            pieces.append(f'<path d="M{x} {y - 6} l12 12 M{x} {y + 6} l12 -12" stroke="{color}" stroke-width="3"/>')
        else:
            pieces.append(f'<line x1="{x}" y1="{y}" x2="{x + 16}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        pieces.append(f'<text x="{x + 23}" y="{y + 4}" fill="#d2dce1" font-size="13" font-family="sans-serif">{label}</text>')
    pieces.append('<text x="110" y="746" fill="#93a4ae" font-size="12" font-family="sans-serif">Local affine reachability is exhaustive for the finite action catalogue; nonlinear curves are source-map replays.</text>')
    pieces.append('</svg>')
    return "\n".join(pieces)


def readme(record: dict) -> str:
    selected = record["linearized_plan_source_replay"]
    reference = record["independent_source_catalogue_oracle"]
    return f'''# PendulumTerminal local-linear finite-action pilot

The source is pinned to [{SOURCE_COMMIT}]({record['source_url']}) and blob
`{SOURCE_BLOB}`. Its dynamics and parameters are re-expressed here; upstream
source code is not copied. The repository metadata declares no license.

The source task randomizes its reset and runs for five seconds. This pilot fixes
the initial state to `(theta, theta_dot) = (0.25 rad, 0 rad/s)`, uses four
0.05-second steps and the action catalogue `[-1, 0, 1]`, and plans on a local
affine model linearized at the upright equilibrium. The planner minimizes the
terminal surrogate `theta_T^2 + 0.1 theta_dot_T^2`, not the source running cost.
Its unique finite-catalogue minimizer is `{selected['actions']}` with surrogate
value `{record['linearized_objective_value']:.12g}`.

The selected plan is replayed on the source nonlinear semi-implicit Euler map.
An independent exhaustive oracle checks all 81 source-map action sequences
using the source running cost. The selected plan costs
`{selected['source_accumulated_cost']:.12g}`; the best sequence in that same
finite catalogue is `{reference['minimizing_actions']}` at
`{reference['minimum_cost']:.12g}`. This gap describes the surrogate on this
pilot only. It is not a continuous-action or full-horizon optimality result.

The phase-plane plot shows every affine forward-reachable point for the finite
catalogue, the selected affine prediction, its nonlinear replay and the best
source-map finite-catalogue replay. No runtime or performance comparison is
reported.

Reproduce from a clean checkout:

```sh
cmake -S . -B build/env717 -DCMAKE_BUILD_TYPE=Release \\
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --config Release --target csl_env717_pendulum_terminal
python3 scripts/reports/env717/check_pendulum_terminal.py \\
  build/env717/csl_env717_pendulum_terminal \\
  --output reports/algorithm-results/env717-pendulum-terminal-pilot-v1
```

The raw record binds the upstream source, driver and algorithm source hashes.
The current source commit is `{record['source_commit']}`.
'''


def render(executable: Path, output: Path | None) -> None:
    raw = json.loads(subprocess.check_output([str(executable)], text=True))
    record = verify(raw)
    if output is None:
        return
    output.mkdir(parents=True, exist_ok=True)
    processor = platform.processor()
    if not processor and Path("/proc/cpuinfo").is_file():
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                processor = line.split(":", 1)[1].strip()
                break
    host = {"os": platform.platform(), "processor": processor,
            "logical_cpus": os.cpu_count(), "capture_started_unix_ns": time.time_ns(),
            "note": "environment context only; no runtime comparison was measured"}
    record["capture_environment"] = host
    record["renderer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / "README.md").write_text(readme(record), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (output / "environment.json").write_text(json.dumps(host, indent=2) + "\n", encoding="utf-8")
    svg = svg_plot(record)
    (output / "projection.svg").write_text(svg + "\n", encoding="utf-8")
    converter = shutil.which("rsvg-convert")
    if converter:
        subprocess.run([converter, "--output", str(output / "projection.png"),
                        str(output / "projection.svg")], check=True)
    png_link = ' · <a href="projection.png">PNG</a>' if converter else ""
    selected = record["linearized_plan_source_replay"]
    reference = record["independent_source_catalogue_oracle"]
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PendulumTerminal local-linear control pilot</title>
<style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:2rem}}a{{color:#8bd3f7}}.plot{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}code{{overflow-wrap:anywhere}}table{{border-collapse:collapse}}td,th{{padding:.35rem .7rem;border-bottom:1px solid #34434d;text-align:left}}</style>
<main><h1>PendulumTerminal: local-linear finite-action pilot</h1>
<p>The current finite-action solver exhausts all 81 four-step plans on a two-state affine model linearized at the upright equilibrium. An independent exhaustive enumeration then evaluates every plan using the pinned source environment's nonlinear semi-implicit Euler map and source running cost.</p>
<figure><img class="plot" src="projection.svg" alt="Angle and angular velocity projection showing affine forward reachable states, the selected plan's prediction and nonlinear replay, the source-map best finite-catalog plan, and the origin reference"><figcaption>Forward reachable points are exact for the declared affine pilot and finite action catalogue. Replay curves use the source nonlinear update.</figcaption></figure>
<table><tr><th>Result</th><th>Value</th></tr><tr><td>Linearized terminal objective</td><td>{record['linearized_objective_value']:.12g}</td></tr><tr><td>Selected action sequence</td><td>{selected['actions']}</td></tr><tr><td>Source running cost of selected sequence</td><td>{selected['source_accumulated_cost']:.12g}</td></tr><tr><td>Best source running cost in the same finite catalogue</td><td>{reference['minimum_cost']:.12g}</td></tr><tr><td>Cost gap from source finite-catalog optimum</td><td>{selected['source_cost_gap_from_finite_catalogue_optimum']:.12g} ({100*selected['relative_gap']:.4g}%)</td></tr><tr><td>Source-map catalogue minimizers</td><td>{reference['minimizing_actions']}</td></tr></table>
<p class="note"><strong>Scope:</strong> the upstream environment randomizes its reset state and runs for 5 seconds. This pilot fixes the initial state to (θ, θ̇) = (0.25 rad, 0 rad/s) and uses four 0.05-second steps. The planner minimizes a terminal quadratic on the local affine model; the source objective is a running cost. The selected action is replayed and compared with an independent exhaustive source-map oracle over the same 81 finite action sequences. These values do not establish continuous-action or full-horizon optimality.</p>
<p>Source: <a href="{record['source_url']}">PendulumTerminal.py</a>, commit <code>{record['source_repository_commit']}</code>, blob <code>{record['source_file_blob']}</code>. CSL source commit: <code>{record['source_commit']}</code>. Method: <code>{record['algorithm']}</code>; assurance is exhaustive only for the declared affine surrogate catalogue.</p>
<p><a href="result.json">Raw result and oracle record</a> · <a href="environment.json">Capture environment</a> · <a href="projection.svg">Standalone SVG</a>{png_link}</p>
<p>Reproduce with the command recorded in the repository's ENV-717 issue and <code>scripts/reports/env717/check_pendulum_terminal.py</code>. This pilot contains no timing comparison.</p></main></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    files = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    sums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 4):
        raise SystemExit("usage: check_pendulum_terminal.py EXECUTABLE [--output DIRECTORY]")
    if len(sys.argv) == 2:
        render(Path(sys.argv[1]).resolve(), None)
    else:
        if sys.argv[2] != "--output":
            raise SystemExit("expected --output")
        render(Path(sys.argv[1]).resolve(), Path(sys.argv[3]))

"""Independently replay and render the finite DubinsCar terminal pilot."""
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
SOURCE_BLOB = "98c7cda22d81248a25e22374e144ce8d605c45c2"
SOURCE_PATH = "Environments/DubinsCar/DubinsCar_Terminal.py"
SOURCE_URL = ("https://github.com/imm-rl-lab/optimal_control/blob/"
              f"{SOURCE_COMMIT}/{SOURCE_PATH}")
OUTER_DT = 0.1
INNER_STEPS = 20
INNER_DT = OUTER_DT / INNER_STEPS
OUTER_STEPS_PER_STAGE = 21
STAGES = 3
TARGET = (4.0, 0.0, 0.75 * math.pi)
ACTIONS = (-0.5, -0.125, 0.25, 0.625, 1.0)
EXPECTED_FIELDS = {
    "schema", "source_repository_commit", "source_file", "source_file_blob",
    "source_license", "state_order", "source_parameters", "adaptation",
    "objective_value", "minimizing_plan_indices", "driver_sha256",
    "source_commit", "capture_environment", "plans",
}


def advance(state: tuple[float, float, float, float], control: float):
    time, x, y, heading = state
    for _ in range(INNER_STEPS):
        x += math.cos(heading) * INNER_DT
        y += math.sin(heading) * INNER_DT
        heading += control * INNER_DT
        time += INNER_DT
    return time, x, y, heading


def loss(state):
    _, x, y, heading = state
    return (x - TARGET[0]) ** 2 + y ** 2 + (heading - TARGET[2]) ** 2


def replay_plan(indices):
    state = (0.0, 0.0, 0.0, 0.0)
    stage_states = []
    for action_index in indices:
        control = ACTIONS[action_index]
        for _ in range(OUTER_STEPS_PER_STAGE):
            state = advance(state, control)
        stage_states.append(state)
    return stage_states, state, loss(state)


def close(actual, expected, tol=1e-11):
    return math.isclose(float(actual), float(expected), rel_tol=tol, abs_tol=tol)


def verify(result):
    if set(result) != EXPECTED_FIELDS:
        raise ValueError("DubinsCar result schema differs")
    if (result["schema"] != "csl.env717-dubins-car/1" or
            result["source_repository_commit"] != SOURCE_COMMIT or
            result["source_file"] != SOURCE_PATH or
            result["source_file_blob"] != SOURCE_BLOB or
            result["source_license"] != "no license declared in upstream repository metadata"):
        raise ValueError("pinned DubinsCar source identity differs")
    if result["state_order"] != ["time", "x", "y", "heading"]:
        raise ValueError("state coordinate order differs")
    source = result["source_parameters"]
    adaptation = result["adaptation"]
    if source != {
        "initial_state": [0.0, 0.0, 0.0, 0.0],
        "terminal_time_seconds": 2.0 * math.pi,
        "dt_seconds": OUTER_DT,
        "inner_euler_steps_per_source_action": INNER_STEPS,
        "inner_euler_step_seconds": INNER_DT,
        "action_bounds": [-0.5, 1.0],
        "target": list(TARGET),
        "terminal_loss": "(x-4)^2+y^2+(heading-3*pi/4)^2",
        "source_update": "20 explicit-Euler steps of x'=cos(heading), y'=sin(heading), heading'=u",
    }:
        raise ValueError("source step data or target differs")
    if (adaptation["macro_stages"] != STAGES or
            adaptation["source_action_steps_per_macro_stage"] != OUTER_STEPS_PER_STAGE or
            adaptation["source_action_steps_total"] != 63 or
            adaptation["finite_control_catalogue"] != list(ACTIONS) or
            adaptation["plan_count"] != 125 or
            adaptation["semantics"] != (
                "one open-loop control chosen per macro stage and held for 21 source action steps; "
                "all 125 finite plans are enumerated") or
            adaptation["claim_boundary"] != (
                "exact minimizer of this finite catalogue only; not the continuous-action source problem")):
        raise ValueError("finite action adaptation differs")
    if len(result["plans"]) != len(ACTIONS) ** STAGES:
        raise ValueError("candidate plan count differs")
    expected = []
    for indices in itertools.product(range(len(ACTIONS)), repeat=STAGES):
        stages, terminal, value = replay_plan(indices)
        expected.append((indices, stages, terminal, value))
    for plan_index, (row, (indices, stages, terminal, value)) in enumerate(
            zip(result["plans"], expected)):
        if row["plan_index"] != plan_index:
            raise ValueError("plan rows are not in canonical enumeration order")
        if row["control_indices"] != list(indices):
            raise ValueError("control index sequence differs")
        if row["controls"] != [ACTIONS[index] for index in indices]:
            raise ValueError("control values differ")
        if len(row["stage_states"]) != STAGES:
            raise ValueError("stage state count differs")
        for saved_state, replayed_state in zip(row["stage_states"], stages):
            if len(saved_state) != 4 or any(not close(a, b) for a, b in zip(saved_state, replayed_state)):
                raise ValueError("independent Euler stage replay differs")
        if (len(row["terminal_state"]) != 4 or
                any(not close(a, b) for a, b in zip(row["terminal_state"], terminal))):
            raise ValueError("independent terminal state replay differs")
        if not close(row["terminal_loss"], value):
            raise ValueError("independent terminal objective replay differs")
    minimum = min(value for _, _, _, value in expected)
    minimizers = [i for i, row in enumerate(expected) if abs(row[3] - minimum) <= 1e-12]
    if not close(result["objective_value"], minimum) or result["minimizing_plan_indices"] != minimizers:
        raise ValueError("finite catalogue optimum differs")
    capture = result["capture_environment"]
    if not all(capture.get(name) for name in ("compiler", "compiler_version", "build_type", "architecture")):
        raise ValueError("build environment metadata is incomplete")
    if len(result.get("driver_sha256", "")) != 64:
        raise ValueError("driver source digest is incomplete")
    if len(result["source_commit"]) != 40:
        raise ValueError("CSL source commit is incomplete")
    return {"plans": expected, "minimum": minimum, "minimizers": minimizers}


def figure_data(analysis):
    stage_clouds = []
    for stage in range(STAGES):
        states_by_prefix = {}
        for row in analysis["plans"]:
            states_by_prefix.setdefault(row[0][:stage + 1], row[1][stage])
        stage_clouds.append([[state[1], state[2], state[3]]
                             for state in states_by_prefix.values()])
    selected = analysis["plans"][analysis["minimizers"][0]]
    indices = selected[0]
    state = (0.0, 0.0, 0.0, 0.0)
    trajectory = [list(state)]
    for action_index in indices:
        for _ in range(OUTER_STEPS_PER_STAGE):
            state = advance(state, ACTIONS[action_index])
            trajectory.append(list(state))
    return {"schema": "csl.env717-dubins-car-figure-data/1",
            "stage_clouds": stage_clouds,
            "selected_plan_index": analysis["minimizers"][0],
            "selected_plan_indices": list(indices),
            "trajectory": trajectory,
            "target": list(TARGET),
            "objective_value": analysis["minimum"]}


def svg_figure(data):
    width, height = 960, 600
    left, top, panel_w, panel_h = 72, 62, 590, 450
    xs = [point[0] for cloud in data["stage_clouds"] for point in cloud] + [data["target"][0]]
    ys = [point[1] for cloud in data["stage_clouds"] for point in cloud] + [data["target"][1]]
    xlo, xhi = min(xs) - 0.35, max(xs) + 0.35
    ylo, yhi = min(ys) - 0.35, max(ys) + 0.35

    def sx(x): return left + (x - xlo) / (xhi - xlo) * panel_w
    def sy(y): return top + panel_h - (y - ylo) / (yhi - ylo) * panel_h

    colors = ("#4cc9f0", "#f4a261", "#90be6d")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">DubinsCar finite catalogue reachable layers and selected path</title>',
        '<desc id="desc">The x-y plane shows finite forward candidate states after each of three control blocks and the selected open-loop trajectory to the terminal target.</desc>',
        '<rect width="100%" height="100%" fill="#101a23"/>',
        '<text x="480" y="32" fill="#f4f1e8" font-family="sans-serif" font-size="21" text-anchor="middle">DubinsCar · finite open-loop catalogue</text>',
        f'<rect x="{left}" y="{top}" width="{panel_w}" height="{panel_h}" fill="#18232c" stroke="#53616c"/>']
    for tick in range(6):
        x = xlo + tick * (xhi - xlo) / 5
        y = ylo + tick * (yhi - ylo) / 5
        parts.append(f'<line x1="{sx(x):.2f}" y1="{top}" x2="{sx(x):.2f}" y2="{top+panel_h}" stroke="#33424d"/>')
        parts.append(f'<line x1="{left}" y1="{sy(y):.2f}" x2="{left+panel_w}" y2="{sy(y):.2f}" stroke="#33424d"/>')
        parts.append(f'<text x="{sx(x):.2f}" y="{top+panel_h+19}" fill="#bdc8cf" font-size="11" text-anchor="middle">{x:.1f}</text>')
        parts.append(f'<text x="{left-8}" y="{sy(y)+4:.2f}" fill="#bdc8cf" font-size="11" text-anchor="end">{y:.1f}</text>')
    for stage, cloud in enumerate(data["stage_clouds"]):
        for x, y, _heading in cloud:
            parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="2.2" fill="{colors[stage]}" fill-opacity=".44"/>')
    trajectory = data["trajectory"]
    points = " ".join(f'{sx(state[1]):.2f},{sy(state[2]):.2f}' for state in trajectory)
    parts.append(f'<polyline points="{points}" fill="none" stroke="#fb7185" stroke-width="3" stroke-linejoin="round"/>')
    for stage, state in enumerate((trajectory[0], trajectory[21], trajectory[42], trajectory[63])):
        parts.append(f'<circle cx="{sx(state[1]):.2f}" cy="{sy(state[2]):.2f}" r="5" fill="{colors[min(stage,2)]}" stroke="#101a23" stroke-width="1.5"/>')
    tx, ty = data["target"][:2]
    parts.append(f'<path d="M {sx(tx)-7:.2f} {sy(ty)-7:.2f} L {sx(tx)+7:.2f} {sy(ty)+7:.2f} M {sx(tx)+7:.2f} {sy(ty)-7:.2f} L {sx(tx)-7:.2f} {sy(ty)+7:.2f}" stroke="#f2c14e" stroke-width="3"/>')
    heading_lo = min(min(state[3] for state in trajectory), data["target"][2]) - 0.15
    heading_hi = max(max(state[3] for state in trajectory), data["target"][2]) + 0.15
    hx = lambda time: 700 + time / trajectory[-1][0] * 220
    hy = lambda angle: 470 - (angle - heading_lo) / (heading_hi - heading_lo) * 100
    heading_points = " ".join(f'{hx(state[0]):.2f},{hy(state[3]):.2f}' for state in trajectory)
    parts.extend([
        '<text x="810" y="352" fill="#d6dee4" font-family="sans-serif" font-size="13" text-anchor="middle">heading over time</text>',
        '<rect x="700" y="365" width="220" height="105" fill="#18232c" stroke="#53616c"/>',
        f'<line x1="700" y1="{hy(data["target"][2]):.2f}" x2="920" y2="{hy(data["target"][2]):.2f}" stroke="#f2c14e" stroke-dasharray="4 4"/>',
        f'<polyline points="{heading_points}" fill="none" stroke="#fb7185" stroke-width="2.5"/>',
        f'<text x="700" y="490" fill="#bdc8cf" font-family="sans-serif" font-size="11">0 s</text>',
        f'<text x="920" y="490" fill="#bdc8cf" font-family="sans-serif" font-size="11" text-anchor="end">{trajectory[-1][0]:.1f} s</text>',
        f'<text x="920" y="{hy(data["target"][2])-5:.2f}" fill="#f2c14e" font-family="sans-serif" font-size="10" text-anchor="end">target 3π/4</text>'])
    parts.extend([
        f'<text x="{left+panel_w/2}" y="{top+panel_h+44}" fill="#cbd5dc" font-size="14" text-anchor="middle">x position</text>',
        f'<text x="18" y="{top+panel_h/2}" fill="#cbd5dc" font-size="14" text-anchor="middle" transform="rotate(-90 18 {top+panel_h/2})">y position</text>',
        '<g font-family="sans-serif" font-size="13" fill="#d6dee4">',
        '<circle cx="710" cy="105" r="4" fill="#4cc9f0"/><text x="725" y="110">after 2.1 s · 5 candidates</text>',
        '<circle cx="710" cy="137" r="4" fill="#f4a261"/><text x="725" y="142">after 4.2 s · 25 candidates</text>',
        '<circle cx="710" cy="169" r="4" fill="#90be6d"/><text x="725" y="174">after 6.3 s · 125 terminal states</text>',
        '<line x1="698" y1="207" x2="720" y2="207" stroke="#fb7185" stroke-width="3"/><text x="730" y="212">finite optimum trajectory</text>',
        '<path d="M 704 236 L 716 248 M 716 236 L 704 248" stroke="#f2c14e" stroke-width="3"/><text x="730" y="248">terminal target position (4, 0)</text>',
        f'<text x="700" y="300">best finite loss: {data["objective_value"]:.8g}</text>',
        f'<text x="700" y="326">best control indices: {data["selected_plan_indices"]}</text>',
        '</g></svg>'])
    return "\n".join(parts)


def report_page(result, data, svg):
    plan = result["plans"][data["selected_plan_index"]]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DubinsCar finite open-loop pilot</title>
<style>body{{margin:0;background:#101a23;color:#edf2f5;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:24px}}a{{color:#8bd3f7}}table{{border-collapse:collapse}}th,td{{border:1px solid #53616c;padding:8px;text-align:left}}svg{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}.note{{padding:12px;border-left:4px solid #f2c14e;background:#18232c}}</style></head><body><main>
<h1>DubinsCar finite open-loop pilot</h1>
<p>This report re-expresses the pinned <a href="{SOURCE_URL}">DubinsCar terminal environment</a>. The state is time, x position, y position, and heading. The model applies 20 explicit-Euler updates per 0.1-second source action step.</p>
<div class="note"><strong>Scope:</strong> the source allows a new continuous control every source step. This pilot uses three open-loop control choices, each held for 21 source steps, and checks all 125 plans. The reported minimum applies only to that finite catalogue. It is not a continuous-action optimum or a minimax result.</div>
<h2>Forward candidates and selected trajectory</h2>
{svg}
<h2>Finite catalogue result</h2>
<p>Minimum terminal squared error: <strong>{result['objective_value']:.12g}</strong>. Minimizing plan row: {data['selected_plan_index']}. Controls: <code>{html.escape(json.dumps(plan['controls']))}</code>.</p>
<table><thead><tr><th>Time</th><th>x</th><th>y</th><th>Heading</th></tr></thead><tbody>
{''.join(f'<tr><td>{state[0]:.4f}</td><td>{state[1]:.8f}</td><td>{state[2]:.8f}</td><td>{state[3]:.8f}</td></tr>' for state in [ [0,0,0,0], *plan['stage_states'] ])}
</tbody></table>
<h2>Reproduce and inspect</h2>
<p>Build <code>csl_env717_dubins_car</code> with <code>CSL_BUILD_ENV717_REPORT=ON</code>, then run <code>scripts/reports/env717/check_dubins_car.py</code> with the executable. The checker independently replays every finite plan.</p>
<ul><li><a href="result.json">Raw result record</a></li><li><a href="figure-data.json">Projection and trajectory data</a></li><li><a href="projections.svg">SVG figure</a></li><li><a href="README.md">Report notes and limits</a></li></ul>
<p>Source commit: <code>{result['source_commit']}</code>. Driver SHA-256: <code>{result['driver_sha256']}</code>.</p></main></body></html>'''


def read_result(executable: Path):
    completed = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def write_bundle(result, output: Path):
    analysis = verify(result)
    data = figure_data(analysis)
    selected_plan = result["plans"][analysis["minimizers"][0]]
    svg = svg_figure(data)
    output.mkdir(parents=True, exist_ok=True)
    environment = {"source_repository_commit": SOURCE_COMMIT, "source_file_blob": SOURCE_BLOB,
        "driver_sha256": result["driver_sha256"],
        "compiler": result["capture_environment"], "platform": platform.platform(),
        "python": platform.python_version(), "arithmetic": "IEEE-754 binary64"}
    capture = {"source_commit": result["source_commit"], "driver_sha256": result["driver_sha256"],
        "compiler": result["capture_environment"], "capture_kind": "one finite-catalogue solve; no performance claim"}
    readme = f'''# DubinsCar finite open-loop pilot

Pinned source: [{SOURCE_PATH}]({SOURCE_URL}) at `{SOURCE_COMMIT}` (blob `{SOURCE_BLOB}`). The upstream repository has no declared license. This report re-expresses the equations and does not copy source code.

## Model and adaptation

The recorded state is `(time, x, y, heading)`, initially `(0,0,0,0)`. Each 0.1-second source step uses 20 explicit-Euler updates of `x'=cos(heading)`, `y'=sin(heading)`, and `heading'=u`. The default terminal time is `2*pi`. Because the environment checks termination after each source step, the recorded trajectory ends at 6.3 seconds, after 63 source steps.

The source accepts controls in `[-0.5,1]` at every source step. This pilot divides the 63 steps into three blocks of 21 and holds one control per block. It enumerates the five-point catalogue `{json.dumps(ACTIONS)}`, for 125 complete open-loop plans. The objective is the source terminal loss `(x-4)^2 + y^2 + (heading-3*pi/4)^2`.

The selected finite plan is `{selected_plan['controls']}` with terminal loss `{result['objective_value']:.12g}`. The result is the exact minimum over the saved finite catalogue after binary64 replay. It is not a claim about the continuous-action problem.

The pinned source also has an `h` method over the three physical coordinates and a `step` method over the four-element state including time. The checked pilot follows the `step` integration and terminal reward. It does not use the alternate one-step `dynamics` helper from `DubinsCar.py`.

## Reproduce

```sh
cmake -S . -B build/env717-dubins-car -DCMAKE_BUILD_TYPE=Release \\
  -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \\
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-dubins-car --config Release --target csl_env717_dubins_car
python3 scripts/reports/env717/check_dubins_car.py \\
  build/env717-dubins-car/csl_env717_dubins_car \\
  --output reports/algorithm-results/env717-dubins-car-pilot-v1
```

No performance comparison is made. The driver records all 125 candidates, stage states, terminal states, objective values, source identity, and build provenance.
'''
    files = {"README.md": readme.encode(),
        "capture.json": (json.dumps(capture, indent=2) + "\n").encode(),
        "environment.json": (json.dumps(environment, indent=2) + "\n").encode(),
        "figure-data.json": (json.dumps(data, indent=2) + "\n").encode(),
        "index.html": report_page(result, data, svg).encode(),
        "projections.svg": svg.encode(),
        "result.json": (json.dumps(result, indent=2) + "\n").encode()}
    for name, content in files.items():
        (output / name).write_bytes(content)
    sums = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n"
                   for name, content in sorted(files.items()))
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--result", type=Path, help="Verify an existing driver result instead of running it")
    args = parser.parse_args()
    if args.result and args.executable:
        parser.error("choose either an executable or --result")
    if args.result:
        result = json.loads(args.result.read_text(encoding="utf-8"))
    elif args.executable:
        result = read_result(args.executable)
    else:
        parser.error("provide an executable or --result")
    analysis = verify(result)
    if args.output:
        write_bundle(result, args.output)
    print(json.dumps({"plan_count": len(analysis["plans"]), "objective_value": analysis["minimum"],
        "minimizing_plan_indices": analysis["minimizers"], "source_replay": "passed"}, indent=2))


if __name__ == "__main__":
    main()

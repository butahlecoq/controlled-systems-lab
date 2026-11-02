"""Independently replay and render the source-equation Van der Pol pilot."""
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
SOURCE_BLOB = "4380ec05c9d100d8b4c1cf0b931a111bc5d419db"
SOURCE_PATH = "Environments/VanDerPol/VanDerPol.py"
NOTEBOOK_BLOB = "c1295c110edf68003f93991e531b072af13e5c8f"
NOTEBOOK_PATH = "Environments/VanDerPol/VanDerPol.ipynb"
SOURCE_URL = f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/{SOURCE_PATH}"
NOTEBOOK_URL = f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/{NOTEBOOK_PATH}"
ACTIONS = (-1.0, 0.0, 1.0)
STAGES = 5
STEPS_PER_STAGE = 22
OUTER_DT = 0.1
INNER_STEPS = 10
INNER_DT = OUTER_DT / INNER_STEPS
TERMINAL_TIME = 11.0
EXPECTED_FIELDS = {
    "schema", "scenario_id", "reference_variant", "source_repository_commit", "source_file", "source_file_blob",
    "source_notebook", "source_notebook_blob", "source_license", "state_order", "source_parameters", "adaptation",
    "source_execution_status", "assumptions", "objective_value", "minimizing_plan_indices", "driver_sha256",
    "source_commit", "capture_environment", "plans",
}


def advance(state: tuple[float, float, float], control: float):
    time, position, velocity = state
    for _ in range(INNER_STEPS):
        time_rate = 1.0
        position_rate = velocity
        velocity_rate = (1.0 - position * position) * velocity - position + control
        time += time_rate * INNER_DT
        position += position_rate * INNER_DT
        velocity += velocity_rate * INNER_DT
    return time, position, velocity


def replay(indices):
    state = (0.0, 1.0, 0.0)
    trajectory = [state]
    stage_states = []
    running_cost = 0.0
    for stage, index in enumerate(indices):
        control = ACTIONS[index]
        for local_step in range(STEPS_PER_STAGE):
            state = advance(state, control)
            trajectory.append(state)
            completed = stage * STEPS_PER_STAGE + local_step + 1
            if completed < STAGES * STEPS_PER_STAGE:
                running_cost += 0.05 * control * control * OUTER_DT
        stage_states.append(state)
    terminal_cost = state[1] * state[1] + state[2] * state[2]
    return stage_states, trajectory, running_cost, terminal_cost


def close(actual, expected, tol=2e-11):
    return math.isclose(float(actual), float(expected), rel_tol=tol, abs_tol=tol)


def verify(result):
    if set(result) != EXPECTED_FIELDS:
        raise ValueError("Van der Pol result schema differs")
    if (result["schema"] != "csl.env717-vanderpol/1" or
            result["scenario_id"] != "env717-vanderpol-equation-replay-finite-catalogue-v1" or
            result["reference_variant"] != "equation-replayed finite-action reference; not direct execution of the upstream class" or
            result["source_repository_commit"] != SOURCE_COMMIT or
            result["source_file"] != SOURCE_PATH or
            result["source_file_blob"] != SOURCE_BLOB or
            result["source_notebook"] != NOTEBOOK_PATH or
            result["source_notebook_blob"] != NOTEBOOK_BLOB or
            result["source_license"] != "no license declared in upstream repository metadata"):
        raise ValueError("pinned Van der Pol source identity differs")
    if (result["source_execution_status"] != "step() raises NameError after state mutation because its return tuple references undefined _" or
            result["assumptions"] != [
                "the recorded derivative and reward equations define the intended transition despite the source return error",
                "one control from {-1,0,1} is held for 22 source steps in each of five report-level macro stages",
                "the final source step uses terminal cost instead of the nonterminal running penalty"]):
        raise ValueError("source-variant assumptions or execution defect differ")
    if result["state_order"] != ["time", "position", "velocity"]:
        raise ValueError("Van der Pol state coordinate order differs")
    if result["source_parameters"] != {
        "initial_state": [0.0, 1.0, 0.0],
        "terminal_time_seconds": TERMINAL_TIME,
        "outer_step_seconds": OUTER_DT,
        "inner_euler_steps_per_outer_step": INNER_STEPS,
        "inner_euler_step_seconds": INNER_DT,
        "control_bounds": [-1.0, 1.0],
        "dynamics": "time'=1; position'=velocity; velocity'=(1-position^2)*velocity-position+u",
        "running_cost": "0.05*u^2*dt for each nonterminal source step",
        "terminal_cost": "position^2+velocity^2",
        "source_execution_note": "upstream step mutates state then raises NameError because return value _ is undefined; this pilot independently re-expresses the recorded equations",
    }:
        raise ValueError("source task parameters or disclosed source defect differ")
    adaptation = result["adaptation"]
    if (adaptation != {
        "macro_stages": STAGES,
        "source_steps_per_macro_stage": STEPS_PER_STAGE,
        "total_source_steps": STAGES * STEPS_PER_STAGE,
        "finite_control_catalogue": list(ACTIONS),
        "plan_count": len(ACTIONS) ** STAGES,
        "semantics": "one open-loop control selected per 2.2-second macro stage; all finite plans are enumerated",
        "claim_boundary": "minimum of this finite open-loop catalogue only; not the continuous-action optimum",
    }):
        raise ValueError("finite-action adaptation differs")
    if len(result["plans"]) != len(ACTIONS) ** STAGES:
        raise ValueError("finite plan count differs")
    expected_rows = []
    for indices in itertools.product(range(len(ACTIONS)), repeat=STAGES):
        stages, trajectory, running, terminal = replay(indices)
        expected_rows.append((indices, stages, trajectory, running, terminal, running + terminal))
    for row_index, (row, expected) in enumerate(zip(result["plans"], expected_rows)):
        indices, stages, _trajectory, running, terminal, objective = expected
        if row["plan_index"] != row_index or row["control_indices"] != list(indices):
            raise ValueError("plans are not in canonical catalogue order")
        if row["controls"] != [ACTIONS[index] for index in indices]:
            raise ValueError("control sequence differs")
        if len(row["stage_states"]) != STAGES:
            raise ValueError("stage state count differs")
        for actual, wanted in zip(row["stage_states"], stages):
            if len(actual) != 3 or any(not close(a, b) for a, b in zip(actual, wanted)):
                raise ValueError("independent Euler stage replay differs")
        if (not close(row["running_cost"], running) or
                not close(row["terminal_cost"], terminal) or
                not close(row["objective"], objective)):
            raise ValueError("independent objective replay differs")
    minimum = min(row[-1] for row in expected_rows)
    minimizers = [i for i, row in enumerate(expected_rows) if abs(row[-1] - minimum) <= 1e-12]
    if (not close(result["objective_value"], minimum) or
            result["minimizing_plan_indices"] != minimizers):
        raise ValueError("finite catalogue minimum differs")
    capture = result["capture_environment"]
    if not all(capture.get(name) for name in ("compiler", "compiler_version", "build_type", "architecture")):
        raise ValueError("build environment metadata is incomplete")
    if len(result["driver_sha256"]) != 64 or len(result["source_commit"]) != 40:
        raise ValueError("capture identity is incomplete")
    return {"rows": expected_rows, "minimum": minimum, "minimizers": minimizers}


def figure_data(analysis):
    clouds = []
    for stage in range(STAGES):
        by_prefix = {}
        for row in analysis["rows"]:
            by_prefix.setdefault(row[0][:stage + 1], row[1][stage])
        clouds.append([[state[1], state[2]] for state in by_prefix.values()])
    selected = analysis["rows"][analysis["minimizers"][0]]
    return {
        "schema": "csl.env717-vanderpol-figure-data/1",
        "stage_clouds": clouds,
        "selected_plan_index": analysis["minimizers"][0],
        "selected_plan_indices": list(selected[0]),
        "controls": [ACTIONS[index] for index in selected[0]],
        "trajectory": [list(state) for state in selected[2]],
        "running_cost": selected[3],
        "terminal_cost": selected[4],
        "objective_value": analysis["minimum"],
    }


def svg_figure(data):
    width, height = 1120, 690
    left, top, plot_w, plot_h = 610, 52, 530, 475
    flat = [point for cloud in data["stage_clouds"] for point in cloud]
    flat += [[state[1], state[2]] for state in data["trajectory"]]
    xlo, xhi = min(p[0] for p in flat), max(p[0] for p in flat)
    ylo, yhi = min(p[1] for p in flat), max(p[1] for p in flat)
    xpad = max((xhi - xlo) * 0.08, 0.08)
    ypad = max((yhi - ylo) * 0.08, 0.08)
    xlo, xhi, ylo, yhi = xlo - xpad, xhi + xpad, ylo - ypad, yhi + ypad

    def sx(x): return left + (x - xlo) / (xhi - xlo) * plot_w
    def sy(y): return top + plot_h - (y - ylo) / (yhi - ylo) * plot_h

    colors = ("#49b6c7", "#f2a65a", "#93c47d", "#b38add", "#e58aa5")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Van der Pol finite open-loop stage projections</title>',
        '<desc id="desc">Position-velocity phase plane with endpoint clouds from each control stage and the selected finite-catalogue trajectory; lower charts show position and velocity over time.</desc>',
        '<rect width="100%" height="100%" fill="#101a23"/>',
        '<defs><marker id="timeArrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,6 L7,3 z" fill="#fff4d2"/></marker></defs>',
        '<text x="560" y="28" fill="#f4f1e8" font-family="sans-serif" font-size="20" text-anchor="middle">Van der Pol · finite open-loop catalogue</text>',
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#18232c" stroke="#53616c"/>']
    for tick in range(6):
        x = xlo + tick * (xhi - xlo) / 5
        y = ylo + tick * (yhi - ylo) / 5
        parts.extend([
            f'<line x1="{sx(x):.2f}" y1="{top}" x2="{sx(x):.2f}" y2="{top + plot_h}" stroke="#33424d"/>',
            f'<line x1="{left}" y1="{sy(y):.2f}" x2="{left + plot_w}" y2="{sy(y):.2f}" stroke="#33424d"/>',
            f'<text x="{sx(x):.2f}" y="{top + plot_h + 18}" fill="#bdc8cf" font-size="11" text-anchor="middle">{x:.2f}</text>',
            f'<text x="{left - 8}" y="{sy(y) + 4:.2f}" fill="#bdc8cf" font-size="11" text-anchor="end">{y:.2f}</text>'])
    for stage in reversed(range(STAGES)):
        cloud = data["stage_clouds"][stage]
        for x, y in cloud:
            parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3.1" fill="{colors[stage]}" fill-opacity=".58"/>')
    trajectory = data["trajectory"]
    points = " ".join(f'{sx(state[1]):.2f},{sy(state[2]):.2f}' for state in trajectory)
    parts.append(f'<polyline points="{points}" fill="none" stroke="#fff4d2" stroke-width="2.4" stroke-linejoin="round"/>')
    for stage in range(STAGES + 1):
        state = trajectory[stage * STEPS_PER_STAGE]
        parts.append(f'<circle cx="{sx(state[1]):.2f}" cy="{sy(state[2]):.2f}" r="5" fill="{colors[min(stage, STAGES - 1)]}" stroke="#101a23" stroke-width="1.5"/>')
    for stage in range(STAGES):
        index = stage * STEPS_PER_STAGE + STEPS_PER_STAGE // 2
        start, end = trajectory[index - 1], trajectory[index + 1]
        parts.append(f'<line x1="{sx(start[1]):.2f}" y1="{sy(start[2]):.2f}" x2="{sx(end[1]):.2f}" y2="{sy(end[2]):.2f}" stroke="#fff4d2" stroke-width="1.7" marker-end="url(#timeArrow)"/>')
    parts.extend([
        f'<text x="{left + plot_w / 2}" y="{top + plot_h + 44}" fill="#cbd5dc" font-size="14" text-anchor="middle">position x</text>',
        f'<text x="18" y="{top + plot_h / 2}" fill="#cbd5dc" font-size="14" text-anchor="middle" transform="rotate(-90 18 {top + plot_h / 2})">velocity dx/dt</text>',
        '<g font-family="sans-serif" font-size="12" fill="#d6dee4">'])
    for stage, (color, cloud) in enumerate(zip(colors, data["stage_clouds"]), start=1):
        y = 75 + (stage - 1) * 27
        parts.append(f'<circle cx="62" cy="{y}" r="4" fill="{color}"/><text x="76" y="{y + 4}">after stage {stage} · {len(cloud)} distinct prefixes</text>')
    parts.extend([
        '<line x1="50" y1="224" x2="72" y2="224" stroke="#fff4d2" stroke-width="2.4"/><text x="82" y="228">selected finite minimizer, direction follows time</text>',
        f'<text x="50" y="270">selected controls: {html.escape(json.dumps(data["controls"]))}</text>',
        f'<text x="50" y="294">J = {data["objective_value"]:.8g}</text>',
        f'<text x="50" y="318">running cost = {data["running_cost"]:.8g}</text>',
        f'<text x="50" y="342">terminal cost = {data["terminal_cost"]:.8g}</text>',
        '<text x="50" y="385" fill="#f2c14e">Source step() raises NameError after updating state;</text>',
        '<text x="50" y="405" fill="#f2c14e">the plotted path replays the pinned equations independently.</text>',
        '</g>'])
    # Time response charts share the same time axis and use separate scales.
    tx0, tx1 = 110, 570
    times = [state[0] for state in trajectory]
    for chart_index, (coord, y0, chart_h, label, color) in enumerate([
            (1, 552, 48, "position", "#49b6c7"), (2, 632, 48, "velocity", "#f2a65a")]):
        values = [state[coord] for state in trajectory]
        lo, hi = min(values), max(values)
        if hi == lo: hi = lo + 1.0
        sx_time = lambda t: tx0 + t / times[-1] * (tx1 - tx0)
        sy_val = lambda v: y0 + chart_h - (v - lo) / (hi - lo) * chart_h
        points = " ".join(f"{sx_time(t):.2f},{sy_val(v):.2f}" for t, v in zip(times, values))
        parts.extend([
            f'<text x="55" y="{y0 + 24}" fill="#cbd5dc" font-size="12">{label}</text>',
            f'<rect x="{tx0}" y="{y0}" width="{tx1 - tx0}" height="{chart_h}" fill="#18232c" stroke="#53616c"/>',
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>',
            f'<text x="{tx0}" y="{y0 + chart_h + 13}" fill="#bdc8cf" font-size="10">0</text>',
            f'<text x="{tx1}" y="{y0 + chart_h + 13}" fill="#bdc8cf" font-size="10" text-anchor="end">11 s</text>'])
    parts.append('</svg>')
    return "\n".join(parts)


def report_page(result, data, svg):
    source_bug = result["source_parameters"]["source_execution_note"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Van der Pol finite-action pilot</title><style>body{{margin:0;background:#101a23;color:#edf2f5;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1160px;margin:auto;padding:24px}}a{{color:#8bd3f7}}svg{{width:100%;height:auto}}.note{{padding:12px;border-left:4px solid #f2c14e;background:#18232c}}code{{overflow-wrap:anywhere}}table{{border-collapse:collapse}}th,td{{border:1px solid #53616c;padding:8px;text-align:left}}</style></head><body><main>
<h1>Van der Pol finite-action pilot</h1>
<p>This report re-expresses the pinned <a href="{SOURCE_URL}">upstream Van der Pol equations</a> and <a href="{NOTEBOOK_URL}">task notebook</a> at commit <code>{SOURCE_COMMIT}</code>. The state is time, position, and velocity. Each 0.1-second source action uses ten explicit-Euler substeps.</p>
<div class="note"><strong>Source limitation:</strong> the upstream <code>step()</code> mutates state and then raises <code>NameError</code> because its return tuple references undefined <code>_</code>. This report independently replays the documented update equations and reward; it does not claim to run the broken Python environment.</div>
<div class="note"><strong>Adaptation:</strong> the source has continuous scalar controls. This pilot enumerates five open-loop macro controls chosen from <code>{list(ACTIONS)}</code>, held for 22 source steps each. The minimum is over all 243 plans only; it is not a continuous-action optimum, minimax value, or performance comparison.</div>
<h2>Position–velocity phase plane and selected path</h2>{svg}
<h2>Finite-catalogue result</h2><p>Minimum objective: <strong>{result['objective_value']:.12g}</strong>. Selected catalogue row: {data['selected_plan_index']}; controls: <code>{html.escape(json.dumps(data['controls']))}</code>.</p>
<table><thead><tr><th>t</th><th>position</th><th>velocity</th></tr></thead><tbody>{''.join(f'<tr><td>{state[0]:.3f}</td><td>{state[1]:.9f}</td><td>{state[2]:.9f}</td></tr>' for state in [data['trajectory'][0], *[result['plans'][data['selected_plan_index']]['stage_states'][i] for i in range(STAGES)]])}</tbody></table>
<h2>Source and reproduce</h2><p>Scenario: <code>{result['scenario_id']}</code>. Upstream source blob: <code>{SOURCE_BLOB}</code>; notebook blob: <code>{NOTEBOOK_BLOB}</code>. No license is declared in the upstream repository. The notebook's CCEM score of -0.82 is a learning result, not a verified optimum; it labels the true value unknown, so this report does not use it as an oracle.</p>
<pre><code>cmake -S benchmarks/reporting/env717/vanderpol-build -B build/env717-vanderpol -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-vanderpol --config Release --target csl_env717_vanderpol
python3 scripts/reports/env717/check_vanderpol.py build/env717-vanderpol/csl_env717_vanderpol --output reports/algorithm-results/env717-vanderpol-pilot-v1</code></pre>
<p>{html.escape(source_bug)}</p><ul><li><a href="result.json">Result data</a></li><li><a href="figure-data.json">Figure data</a></li><li><a href="projections.svg">SVG figure</a></li><li><a href="README.md">Report notes</a></li></ul></main></body></html>'''


def read_result(executable):
    completed = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def write_bundle(result, output):
    analysis = verify(result)
    data = figure_data(analysis)
    svg = svg_figure(data)
    output.mkdir(parents=True, exist_ok=True)
    environment = {"scenario_id": result["scenario_id"],
        "reference_variant": result["reference_variant"],
        "source_repository_commit": SOURCE_COMMIT, "source_file_blob": SOURCE_BLOB,
        "source_notebook_blob": NOTEBOOK_BLOB,
        "driver_sha256": result["driver_sha256"], "compiler": result["capture_environment"],
        "platform": platform.platform(), "python": platform.python_version(),
        "arithmetic": "IEEE-754 binary64"}
    capture = {"source_commit": result["source_commit"], "driver_sha256": result["driver_sha256"],
        "compiler": result["capture_environment"],
        "capture_kind": "finite-catalogue equation replay; upstream step() defect disclosed; no performance claim"}
    selected = result["plans"][data["selected_plan_index"]]
    readme = f'''# Van der Pol finite-action pilot

Scenario: `{result['scenario_id']}` (`{result['reference_variant']}`).

Pinned source: [{SOURCE_PATH}]({SOURCE_URL}) at `{SOURCE_COMMIT}` (blob `{SOURCE_BLOB}`) and [{NOTEBOOK_PATH}]({NOTEBOOK_URL}) (blob `{NOTEBOOK_BLOB}`). The upstream repository declares no license. This report re-expresses the equations and does not copy upstream source code. The source note is [env717-vanderpol-source-notes.md](https://github.com/butahlecoq/controlled-systems-lab/blob/{result['source_commit']}/docs/research/env717-vanderpol-source-notes.md).

## Model and objective

The state is `(time, position, velocity)`, initially `(0,1,0)`. The update equations are `time'=1`, `position'=velocity`, and `velocity'=(1-position^2)*velocity-position+u`, with ten explicit-Euler steps per 0.1-second source step. Controls are clipped to `[-1,1]`; the terminal time is 11 seconds. The objective minimized here is the negative of the source reward: nonterminal steps contribute `0.05*u^2*dt`, and the terminal step contributes `position^2+velocity^2` instead of another running penalty.

The source `step()` has a defect: it references undefined `_` in its return tuple after mutating the state, so direct execution raises `NameError`. This artifact independently replays the source equations and reward as documented by the pinned Python file and notebook; it is not a direct run of that class.

The notebook lists a CCEM learning value of `-0.82` and says the true value is unknown. That learned value is not used as ground truth or compared to this finite catalogue.

## Finite adaptation

The source control is continuous. This report uses five macro stages of 22 source steps each, with one constant action per stage from `{json.dumps(ACTIONS)}`. It enumerates all 243 open-loop plans. The minimum is `{result['objective_value']:.12g}` at plan row `{data['selected_plan_index']}`, controls `{selected['controls']}`. This is a finite-catalogue result only, not the continuous-action optimum or a performance comparison.

## Reproduce

```sh
cmake -S benchmarks/reporting/env717/vanderpol-build -B build/env717-vanderpol -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-vanderpol --config Release --target csl_env717_vanderpol
python3 scripts/reports/env717/check_vanderpol.py build/env717-vanderpol/csl_env717_vanderpol --output reports/algorithm-results/env717-vanderpol-pilot-v1
```

The Python checker independently enumerates and replays every finite plan. No timing or algorithm-performance claim is made.
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
    sums = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(files.items()))
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--output", type=Path)
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
    print(json.dumps({"plan_count": len(analysis["rows"]), "objective_value": analysis["minimum"],
        "minimizing_plan_indices": analysis["minimizers"], "independent_replay": "passed"}, indent=2))


if __name__ == "__main__":
    main()

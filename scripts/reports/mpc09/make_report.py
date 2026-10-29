#!/usr/bin/env python3
"""Capture, independently verify, and render the finite MPC-09 report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_output_feedback as check  # noqa: E402

SOURCE_FILES = (
    "benchmarks/scenarios/mpc09-two-particle-output-feedback-v1.json",
    "benchmarks/reporting/mpc09/two_particle_output_feedback.cpp",
    "scripts/reports/mpc09/check_output_feedback.py",
    "scripts/reports/mpc09/make_report.py",
    "scripts/reports/stage_mpc09_output_feedback.py",
    "scripts/reports/landing.py",
    "scripts/reports/audit_visual_routes.py",
    ".github/workflows/algorithm-reports.yml",
    "tests/reporting/test_mpc09_output_feedback_publication.py",
    "cmake/OptionalReports.cmake",
    "CMakeLists.txt",
    "include/csl/optimization/finite_action_minimax.hpp",
    "include/csl/controllers/observed_replay.hpp",
    "src/controllers/observed_replay.cpp",
    "docs/contracts/information-patterns.md",
    "src/optimization/finite_action_minimax.cpp",
    "benchmarks/reporting/env717/two_particle_minimax.cpp",
    "reports/algorithm-results/env717-two-particle-minimax-v1/projections.svg",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def validate_scenario(result: dict) -> None:
    scenario = json.loads((ROOT / SOURCE_FILES[0]).read_text(encoding="utf-8"))
    adaptation = scenario["adaptation"]
    actual = result["adaptation"]
    expected = {
        "scenario_id": scenario["scenario_id"],
        "horizon_steps": adaptation["horizon_steps"],
        "horizon_seconds": adaptation["horizon_seconds"],
        "initial_states": adaptation["initial_states"],
        "control_catalogue": adaptation["control_catalogue"],
        "disturbance_catalogue": adaptation["disturbance_catalogue"],
        "measurement_error_catalogue": adaptation["measurement_error_catalogue"],
        "mhe_residual_bound": scenario["estimator"]["residual_bound"],
    }
    if any((round(actual.get(key), 12) != round(value, 12) if isinstance(value, float)
            else actual.get(key) != value) for key, value in expected.items()):
        raise ValueError("native result differs from the versioned scenario input")
    if result["source"].get("repository_commit") != scenario["source"]["commit"]:
        raise ValueError("native source pin differs from the versioned scenario input")


def svg_figure(data: dict) -> str:
    width, height = 1160, 690
    panels = ((70, 120, 500, 470, 0, 1, "Particle 1 phase plane: position x1, velocity v1"),
              (630, 120, 500, 470, 2, 3, "Particle 2 phase plane: position x2, velocity v2"))
    colors = {"certainty_equivalent_receding": "#1769aa", "set_based_robust_receding": "#cc4b16"}
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#fff"/>',
            '<style>text{font-family:Arial,sans-serif;fill:#263238}.title{font-size:24px;font-weight:bold}.sub{font-size:14px}.axis{stroke:#445;stroke-width:1.5}.grid{stroke:#d9e0e5;stroke-width:1}.ce{fill:none;stroke:#1769aa;stroke-width:3}.rb{fill:none;stroke:#cc4b16;stroke-width:3;stroke-dasharray:8 5}.est{stroke:#111;stroke-width:3;stroke-dasharray:none}.point{stroke:#fff;stroke-width:1.5}.set{fill:#8d99a6;opacity:.42;stroke:#52616b;stroke-width:1}</style>',
            '<text x="70" y="38" class="title">TwoParticleGame output-feedback MPC: matched finite rows</text>',
            f'<text x="70" y="65" class="sub">Selected row {data["row_id"]}; full-history MHE estimate and compatible hidden states</text>',
            '<text x="70" y="87" class="sub">Source-derived RK4 plant; noisy relative-position sensor; finite catalogue only</text>']
    for x0, y0, w, h, xi, yi, title in panels:
        samples = []
        for arm in data["controllers"]:
            for p in arm["trace"]:
                if p["stage"] < len(data["actual_state_stages"]):
                    samples.append((p["actual_state"][xi], p["actual_state"][yi]))
                    estimate_state = p.get("estimate")
                    if estimate_state is not None:
                        samples.append((estimate_state[xi], estimate_state[yi]))
                    for posterior in p.get("posterior_states", []):
                        samples.append((posterior[xi], posterior[yi]))
        xs, ys = [a for a, _ in samples], [b for _, b in samples]
        xmin, xmax = min(xs) - .15, max(xs) + .15
        ymin, ymax = min(ys) - .3, max(ys) + .3
        if xmax - xmin < .1: xmin, xmax = xmin - .1, xmax + .1
        if ymax - ymin < .1: ymin, ymax = ymin - .1, ymax + .1
        def sx(value: float) -> float: return x0 + (value - xmin) / (xmax - xmin) * w
        def sy(value: float) -> float: return y0 + h - (value - ymin) / (ymax - ymin) * h
        for i in range(6):
            gx = x0 + w * i / 5
            gy = y0 + h * i / 5
            body.append(f'<line x1="{gx:.1f}" y1="{y0}" x2="{gx:.1f}" y2="{y0+h}" class="grid"/>')
            body.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{x0+w}" y2="{gy:.1f}" class="grid"/>')
            body.append(f'<text x="{gx-18:.1f}" y="{y0+h+20}" class="sub">{xmin+(xmax-xmin)*i/5:.2f}</text>')
            body.append(f'<text x="{x0-54}" y="{gy+5:.1f}" class="sub">{ymax-(ymax-ymin)*i/5:.2f}</text>')
        body.extend((f'<line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" class="axis"/>',
                     f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" class="axis"/>',
                     f'<text x="{x0+40}" y="{y0-22}" class="sub">{html.escape(title)}</text>',
                     f'<text x="{x0+w/2-50}" y="{y0+h+47}" class="sub">position (model units)</text>',
                     f'<text transform="translate({x0-66},{y0+h/2}) rotate(-90)" class="sub">velocity (model units/s)</text>'))
        for arm in data["controllers"]:
            trace = arm["trace"]
            color_class = "ce" if arm["label"] == "certainty_equivalent_receding" else "rb"
            actual = [(sx(p["actual_state"][xi]), sy(p["actual_state"][yi])) for p in trace]
            body.append(f'<polyline points="{" ".join(f"{a:.2f},{b:.2f}" for a,b in actual)}" class="{color_class}"/>')
            for p, (px, py) in zip(trace[:-1], actual[:-1]):
                body.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6" fill="{colors[arm["label"]]}" class="point"><title>stage {p["stage"]}, observed {p["observation"]:.2f}, u={p["control"]:.0f}</title></circle>')
                for hidden in p.get("posterior_states", []):
                    body.append(f'<circle cx="{sx(hidden[xi]):.2f}" cy="{sy(hidden[yi]):.2f}" r="8" class="set"/>')
                estimate_state = p.get("estimate")
                if estimate_state is not None:
                    body.append(f'<path d="M {sx(estimate_state[xi])-7:.2f} {sy(estimate_state[yi])-7:.2f} l 14 14 m 0 -14 l -14 14" class="est"/>')
    body.extend(('<line x1="90" y1="655" x2="125" y2="655" class="ce"/><text x="135" y="660" class="sub">certainty-equivalent actual path</text>',
                 '<line x1="390" y1="655" x2="425" y2="655" class="rb"/><text x="435" y="660" class="sub">set-based actual path</text>',
                 '<circle cx="760" cy="655" r="7" class="set"/><text x="775" y="660" class="sub">posterior finite states</text>',
                 '<path d="M 963 648 l 14 14 m 0 -14 l -14 14" class="est"/><text x="985" y="660" class="sub">MHE estimate</text>',
                 '</svg>'))
    return "\n".join(body) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    executable, build_dir, output = args.executable.resolve(), args.build_dir.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {output}")
    if not args.build_log.is_file() or args.build_log.stat().st_size == 0:
        raise SystemExit("a nonempty native build log is required")
    raw = subprocess.run([str(executable)], check=True, capture_output=True, text=True).stdout
    result = json.loads(raw)
    validate_scenario(result)
    verification = check.verify(result)
    result["independent_verification"] = verification
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copyfile(args.build_log, output / "build.log")

    arms = result["controllers"]
    selected_id = max(range(len(arms[0]["runs"])),
                      key=lambda i: max(arms[0]["runs"][i]["terminal_gap"], arms[1]["runs"][i]["terminal_gap"]))
    selected = []
    for arm in arms:
        run = arm["runs"][selected_id]
        trace = []
        for stage, state in enumerate(run["states"]):
            point = {"stage": stage, "actual_state": state, "estimate": None,
                     "posterior_states": [], "observation": None, "control": None}
            if stage < check.HORIZON:
                decision = run["decisions"][stage]
                point["estimate"] = decision["estimate"]
                point["posterior_states"] = decision["posterior_states"]
                point["observation"] = decision["available_observations"][-1]["value"][0]
                point["control"] = decision["action"]
            trace.append(point)
        selected.append({"label": arm["label"], "terminal_gap": run["terminal_gap"], "trace": trace})
    figure_data = {"schema": "csl.mpc09-output-feedback-figure/1", "row_id": selected_id,
                   "actual_state_stages": list(range(check.HORIZON + 1)), "controllers": selected}
    (output / "figure-data.json").write_text(json.dumps(figure_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "projections.svg").write_text(svg_figure(figure_data), encoding="utf-8")

    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER") or "unknown"
    compiler_version = subprocess.run([compiler, "--version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    source_hashes = {name: sha256(ROOT / name) for name in SOURCE_FILES}
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], check=True,
                            capture_output=True, text=True).stdout
    try:
        output_relative = output.relative_to(ROOT).as_posix().rstrip("/")
    except ValueError:
        output_relative = None
    status_entries = [line for line in status.splitlines()
                      if not (output_relative and line[3:].split(" -> ")[-1].startswith(output_relative))]
    environment = {"platform": platform.platform(), "machine": platform.machine(),
                   "logical_cpus": __import__("os").cpu_count(), "compiler": compiler_version,
                   "build_type": cache_value(cache, "CMAKE_BUILD_TYPE"),
                   "measurement": "No timing comparison collected; numerical and policy behavior only."}
    (output / "environment.json").write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capture = {"schema": "csl.mpc09-output-feedback-capture/1", "source_commit": commit,
               "working_tree_clean": not bool(status_entries), "compiler": compiler_version,
               "cmake_build_type": cache_value(cache, "CMAKE_BUILD_TYPE"),
               "report_executable_sha256": sha256(executable), "source_sha256": source_hashes,
               "scenario_sha256": sha256(ROOT / SOURCE_FILES[0]), "platform": environment["platform"],
               "machine": environment["machine"], "logical_cpus": environment["logical_cpus"],
               "measurement": environment["measurement"], "run": [str(executable)]}
    (output / "capture.json").write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ref = verification["causal_reference"]
    ce, robust = arms
    readme = f'''# MPC-09 TwoParticleGame output-feedback pilot

This report adapts the source-attributed `TwoParticleGame` from the RL differential-game repository to an explicit finite output-feedback experiment. It uses the source RK4 flow at 0.2-second decision intervals, two initial states, three control and disturbance values, an additive-noise relative-position sensor, and a three-stage horizon. The noisy outputs enter the reviewed CSL affine observation and replay API. The source code is not copied; the pinned source and Apache-2.0 license are recorded in `result.json`.

The certainty-equivalent planner uses a full-history constrained least-squares state hypothesis. The set-based planner retains every state compatible with the complete noisy observation history. Both call CSL `finite_action_minimax`, execute only the first action, and replan after the next reading. The convex hulls used by that planner are exact for its convex terminal gap objective: the maximum is attained at vertices, which are the authored finite states and disturbance endpoints. Their lookahead does not branch on future observations.

The saved run covers {ce['rows_evaluated']} matched rows. The certainty-equivalent worst terminal gap is {ce['worst_terminal_gap']:.9f} ({ce['terminal_capture_violations']} misses of the finite `gap <= 1` target); the set-based receding worst gap is {robust['worst_terminal_gap']:.9f} ({robust['terminal_capture_violations']} misses). An independent complete finite observation-history dynamic program has worst gap {ref['worst_terminal_gap']:.9f} and optimal first action(s) {ref['optimal_first_actions']}. The set-based receding planner uses open-loop future controls and is not the same controller as that feedback-tree reference. The verifier replays each state, released measurement, estimate, posterior, action, and terminal outcome. A separate missed/delayed sample replay shows that releasing a reading at stage two changes the next action from 0 to 3 in its declared finite fixture.

These are finite catalogue results. They do not reproduce the continuous-action RL training task, certify continuous observation noise, or establish global output-feedback optimality. No timing or speed comparison was made. The source differential-game reachability figure with forward and backward sets is available in the [TwoParticleGame minimax report](https://butahlecoq.github.io/controlled-systems-lab/env717-two-particle-minimax-31bb367020af7a94b1a7/).

Reproduce from the repository root with a Release build:

```sh
cmake -S . -B build/mpc09 -DCSL_BUILD_MPC09_REPORT=ON -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/mpc09 --target csl_mpc09_output_feedback_report --parallel 2 2>&1 | tee /tmp/mpc09-build.log
python3 scripts/reports/mpc09/make_report.py \\
  --executable build/mpc09/csl_mpc09_output_feedback_report \\
  --build-dir build/mpc09 --build-log /tmp/mpc09-build.log \\
  --output /tmp/mpc09-output-feedback
```

`result.json` contains all 864 trajectories per controller with observations, estimates, posterior states, actions and terminal outcomes. `figure-data.json` and `projections.svg` show both particle phase planes for a matched worst-case row. `capture.json`, `environment.json`, `build.log`, and `SHA256SUMS` preserve build and input provenance.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-09 output-feedback pilot</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b}}img{{width:100%;height:auto;border:1px solid #ccd}}table{{border-collapse:collapse}}td,th{{padding:.45rem .8rem;border:1px solid #ccd;text-align:left}}code{{background:#eef;padding:.1rem .25rem}}</style><h1>TwoParticleGame: output-feedback MPC</h1><p>Finite noisy-observation adaptation of the RL differential-game environment. See <a href="https://github.com/imm-rl-lab/differential_game_gym/tree/af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8/Environments/TwoParticleGame">pinned source</a> and its Apache-2.0 license.</p><img src="projections.svg" alt="Both particle phase-plane projections showing actual trajectories, finite posterior states, and MHE estimates"><table><thead><tr><th>Controller</th><th>Worst terminal gap</th><th>Capture misses</th><th>Rows</th></tr></thead><tbody><tr><td>Certainty-equivalent</td><td>{ce['worst_terminal_gap']:.9f}</td><td>{ce['terminal_capture_violations']}</td><td>{ce['rows_evaluated']}</td></tr><tr><td>Set-based robust</td><td>{robust['worst_terminal_gap']:.9f}</td><td>{robust['terminal_capture_violations']}</td><td>{robust['rows_evaluated']}</td></tr><tr><td>Complete finite-history reference</td><td>{ref['worst_terminal_gap']:.9f}</td><td>finite optimum</td><td>all listed branches</td></tr></tbody></table><p>Finite catalogue only; no continuous-noise or global output-feedback guarantee. The receding planners do not branch on future observations. <a href="result.json">Raw result</a> · <a href="figure-data.json">Figure data</a> · <a href="README.md">Method and reproduction</a> · <a href="https://butahlecoq.github.io/controlled-systems-lab/env717-two-particle-minimax-31bb367020af7a94b1a7/">Reachability and minimax sets report</a>.</p></html>'''
    (output / "index.html").write_text(body, encoding="utf-8")
    names = sorted(path.name for path in output.iterdir() if path.is_file())
    (output / "SHA256SUMS").write_text("".join(f"{sha256(output / name)}  {name}\n" for name in names), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

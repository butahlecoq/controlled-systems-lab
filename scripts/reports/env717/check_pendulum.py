#!/usr/bin/env python3
"""Check, replay, and publish the pinned Gym Pendulum finite-action pilot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

UPSTREAM_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
UPSTREAM_NOTEBOOK_BLOB = "db58eb7779d84a3a5032288734d61f6d6dcdba09"
GYM_COMMIT = "c755d5c35a25ab118746e2ba885894ff66fb8c43"
GYM_SOURCE_BLOB = "10ced4d43d218fbf0bb344b3bbc006fcaa7f8362"
GYM_REGISTRY_BLOB = "a90b0370730e74d783971a1a3f0771c5a2fb572e"
SOURCE_URL = (f"https://github.com/imm-rl-lab/optimal_control/tree/{UPSTREAM_COMMIT}"
              "/Environments/Pendulum")
GYM_SOURCE_URL = (f"https://github.com/openai/gym/blob/{GYM_COMMIT}"
                  "/gym/envs/classic_control/pendulum.py")
GYM_REGISTRY_URL = (f"https://github.com/openai/gym/blob/{GYM_COMMIT}/gym/envs/__init__.py")
DT = 0.05
GRAVITY = 10.0
MASS = 1.0
LENGTH = 1.0
MAX_SPEED = 8.0
MAX_TORQUE = 2.0
INITIAL = (1.5, 0.0)
ACTIONS = (-2.0, -1.0, 0.0, 1.0, 2.0)
HORIZON = 10
PLAN_COUNT = len(ACTIONS) ** HORIZON
WARMUPS = 2
MEASURED = 7
TOLERANCE = 2e-10
BUNDLE_FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
                "phase-plane.svg", "result.json", "SHA256SUMS")


def close(actual: float, expected: float, name: str, tolerance: float = TOLERANCE) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(f"{name}: {actual!r} != {expected!r}")


def angle_normalize(angle: float) -> float:
    return ((angle + math.pi) % (2.0 * math.pi)) - math.pi


def advance(state: tuple[float, float], action: float) -> tuple[float, float]:
    theta, theta_dot = state
    torque = max(-MAX_TORQUE, min(MAX_TORQUE, action))
    next_dot = theta_dot + (3.0 * GRAVITY / (2.0 * LENGTH) * math.sin(theta)
                            + 3.0 / (MASS * LENGTH * LENGTH) * torque) * DT
    next_dot = max(-MAX_SPEED, min(MAX_SPEED, next_dot))
    return theta + next_dot * DT, next_dot


def stage_cost(state: tuple[float, float], action: float) -> float:
    theta, theta_dot = state
    return angle_normalize(theta) ** 2 + 0.1 * theta_dot ** 2 + 0.001 * action ** 2


def plan_from_index(index: int) -> tuple[float, ...]:
    digits = []
    for _ in range(HORIZON):
        digits.append(index % len(ACTIONS))
        index //= len(ACTIONS)
    return tuple(ACTIONS[digit] for digit in digits)


def replay(actions: tuple[float, ...]) -> dict:
    state = INITIAL
    objective = 0.0
    trajectory = [{"step": 0, "time_seconds": 0.0, "theta_rad": state[0],
                   "theta_dot_rad_s": state[1],
                   "action_torque_nm": actions[0] if actions else 0.0}]
    for stage, action in enumerate(actions):
        objective += stage_cost(state, action)
        state = advance(state, action)
        trajectory.append({"step": stage + 1, "time_seconds": (stage + 1) * DT,
                           "theta_rad": state[0], "theta_dot_rad_s": state[1],
                           "action_torque_nm": actions[stage + 1] if stage + 1 < len(actions) else 0.0})
    return {"objective_cost": objective, "reward": -objective,
            "terminal_state": list(state), "trajectory": trajectory}


def enumerate_catalogue() -> tuple[float, int, tuple[float, ...], int]:
    best = math.inf
    best_index = -1
    best_actions: tuple[float, ...] = ()
    minimizer_count = 0
    for plan_index in range(PLAN_COUNT):
        actions = plan_from_index(plan_index)
        state = INITIAL
        objective = 0.0
        for action in actions:
            objective += stage_cost(state, action)
            state = advance(state, action)
        if objective < best:
            best = objective
            best_index = plan_index
            best_actions = actions
            minimizer_count = 1
        elif objective == best:
            minimizer_count += 1
            if plan_index < best_index:
                best_index = plan_index
                best_actions = actions
    return best, best_index, best_actions, minimizer_count


def verify(result: dict) -> dict:
    expected = {
        "schema": "csl.env717-pendulum/1",
        "environment": "Pendulum-v0",
        "source_repository_commit": UPSTREAM_COMMIT,
        "source_notebook": "Environments/Pendulum/Pendulum.ipynb",
        "source_notebook_blob": UPSTREAM_NOTEBOOK_BLOB,
        "simulator_repository": "openai/gym", "simulator_version": "v0.21.0",
        "simulator_commit": GYM_COMMIT,
        "simulator_source": "gym/envs/classic_control/pendulum.py",
        "simulator_source_blob": GYM_SOURCE_BLOB,
        "simulator_registry_source": "gym/envs/__init__.py",
        "simulator_registry_blob": GYM_REGISTRY_BLOB,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"source identity differs: {key}")
    source = result.get("source_model", {})
    if (source.get("sample_period_seconds") != DT or
            source.get("gravity_m_s2") != GRAVITY or
            source.get("mass_kg") != MASS or source.get("length_m") != LENGTH or
            source.get("max_speed_rad_s") != MAX_SPEED or
            source.get("max_torque_nm") != MAX_TORQUE):
        raise ValueError("Gym v0.21.0 source parameters differ")
    adaptation = result.get("pilot_adaptation", {})
    if (adaptation.get("initial_state") != list(INITIAL) or
            adaptation.get("action_catalogue_torque_nm") != list(ACTIONS) or
            adaptation.get("horizon_steps") != HORIZON or
            adaptation.get("plan_count") != PLAN_COUNT):
        raise ValueError("finite pilot inputs differ")

    best, best_index, actions, minimizer_count = enumerate_catalogue()
    expected_replay = replay(actions)
    optimum = result.get("finite_catalogue_optimum", {})
    close(optimum.get("objective_cost", math.nan), best, "finite objective")
    close(optimum.get("reward", math.nan), -best, "finite reward")
    if (result.get("search", {}).get("complete_plan_count") != PLAN_COUNT or
            result["search"].get("evaluated_plan_count") != PLAN_COUNT or
            result["search"].get("complete") is not True or
            result["search"].get("minimizer_count") != minimizer_count or
            result["search"].get("selected_plan_index") != best_index):
        raise ValueError("finite catalogue enumeration evidence differs")
    if optimum.get("selected_action_indices") != [ACTIONS.index(action) for action in actions]:
        raise ValueError("selected finite plan differs from independent enumeration")
    if optimum.get("selected_actions_torque_nm") != list(actions):
        raise ValueError("selected action values differ")
    for actual, expected_state, coordinate in zip(optimum.get("terminal_state", []),
                                                   expected_replay["terminal_state"], ("theta", "theta_dot")):
        close(actual, expected_state, f"finite terminal {coordinate}")
    if len(optimum.get("trajectory", [])) != HORIZON + 1:
        raise ValueError("finite replay trajectory length differs")
    for actual, expected_row in zip(optimum["trajectory"], expected_replay["trajectory"]):
        for key in ("time_seconds", "theta_rad", "theta_dot_rad_s", "action_torque_nm"):
            close(actual[key], expected_row[key], f"finite trajectory {key}")

    baseline = replay((0.0,) * HORIZON)
    saved_baseline = result.get("zero_torque_baseline", {})
    close(saved_baseline.get("objective_cost", math.nan), baseline["objective_cost"], "baseline objective")
    for actual, expected_state in zip(saved_baseline.get("terminal_state", []), baseline["terminal_state"]):
        close(actual, expected_state, "baseline terminal state")
    for actual, expected_row in zip(saved_baseline.get("trajectory", []), baseline["trajectory"]):
        for key in ("time_seconds", "theta_rad", "theta_dot_rad_s"):
            close(actual[key], expected_row[key], f"baseline trajectory {key}")

    measurement = result.get("runtime_measurement", {})
    samples = measurement.get("raw_elapsed_ns", [])
    measured_repetitions = measurement.get("measured_repetitions")
    if (measurement.get("schema") != "csl.env717-runtime-measurement/1" or
            measurement.get("warmup_repetitions") != WARMUPS or
            not isinstance(measured_repetitions, int) or not 1 <= measured_repetitions <= 1000 or
            measurement.get("successful_repetitions") != measured_repetitions or
            measurement.get("failed_repetitions") != 0 or len(samples) != measured_repetitions or
            any(not isinstance(sample, int) or sample <= 0 for sample in samples) or
            measurement.get("median_elapsed_ns") != statistics.median(samples) or
            measurement.get("minimum_elapsed_ns") != min(samples) or
            measurement.get("maximum_elapsed_ns") != max(samples) or
            measurement.get("worker_threads") != 1):
        raise ValueError("runtime measurement protocol differs")
    provenance = result.get("provenance", {})
    for key in ("driver_sha256", "source_commit", "compiler_id", "compiler_version", "build_type", "architecture"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ValueError(f"missing build provenance: {key}")
    return {"objective_cost": best, "plan_index": best_index,
            "actions": actions, "minimizer_count": minimizer_count,
            "trajectory": expected_replay["trajectory"]}


def figure_data(analysis: dict, result: dict) -> dict:
    return {"schema": "csl.env717-figure-data/1", "coordinates": ["theta_rad", "theta_dot_rad_s"],
            "tracks": {"finite_catalogue_optimum": result["finite_catalogue_optimum"]["trajectory"],
                       "zero_torque_baseline": result["zero_torque_baseline"]["trajectory"]},
            "finite_catalogue": {"action_count": len(ACTIONS), "horizon_steps": HORIZON,
                                 "plan_count": PLAN_COUNT, "minimizer_count": analysis["minimizer_count"]}}


def make_svg(data: dict) -> str:
    tracks = data["tracks"]
    points = [row for trajectory in tracks.values() for row in trajectory]
    xs = [row["theta_rad"] for row in points]
    ys = [row["theta_dot_rad_s"] for row in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_pad = max((x_max - x_min) * 0.08, 0.05)
    y_pad = max((y_max - y_min) * 0.08, 0.05)
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad
    left, top, width, height = 100.0, 95.0, 760.0, 440.0

    def px(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * width

    def py(y: float) -> float:
        return top + (y_max - y) / (y_max - y_min) * height

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 680" role="img" aria-labelledby="title desc">',
             '<title id="title">Pendulum finite-action phase portrait</title>',
             '<desc id="desc">Theta versus angular velocity for the selected finite-catalogue plan and zero-torque baseline.</desc>',
             '<rect width="1000" height="680" fill="#101820"/>',
             '<text x="500" y="38" text-anchor="middle" fill="#f3f7f9" font-family="sans-serif" font-size="22">Pendulum-v0: angle–angular velocity</text>']
    for i in range(6):
        x = x_min + (x_max - x_min) * i / 5
        y = y_min + (y_max - y_min) * i / 5
        parts += [f'<line x1="{px(x):.2f}" y1="{top}" x2="{px(x):.2f}" y2="{top + height}" stroke="#344653"/>',
                  f'<text x="{px(x):.2f}" y="{top + height + 22}" text-anchor="middle" fill="#b9c6ce" font-family="sans-serif" font-size="12">{x:.3f}</text>',
                  f'<line x1="{left}" y1="{py(y):.2f}" x2="{left + width}" y2="{py(y):.2f}" stroke="#344653"/>',
                  f'<text x="{left - 12}" y="{py(y) + 4:.2f}" text-anchor="end" fill="#b9c6ce" font-family="sans-serif" font-size="12">{y:.3f}</text>']
    parts += [f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#91a2ad" stroke-width="1.5"/>',
              f'<text x="{left + width / 2}" y="{top + height + 54}" text-anchor="middle" fill="#e8eef2" font-family="sans-serif" font-size="16">angle theta (rad)</text>',
              f'<text x="26" y="{top + height / 2}" transform="rotate(-90 26 {top + height / 2})" text-anchor="middle" fill="#e8eef2" font-family="sans-serif" font-size="16">angular velocity (rad/s)</text>']
    styles = (("finite_catalogue_optimum", "#2e8b57", "finite-catalogue optimum"),
              ("zero_torque_baseline", "#ed7d31", "zero-torque baseline"))
    for key, color, label in styles:
        trajectory = tracks[key]
        coords = " ".join(f"{px(row['theta_rad']):.2f},{py(row['theta_dot_rad_s']):.2f}" for row in trajectory)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
        for idx in (0, len(trajectory) - 1):
            row = trajectory[idx]
            parts.append(f'<circle cx="{px(row["theta_rad"]):.2f}" cy="{py(row["theta_dot_rad_s"]):.2f}" r="5" fill="{color}" stroke="#101820" stroke-width="1.5"/>')
    for index, (key, color, label) in enumerate(styles):
        y = 600 + index * 24
        parts += [f'<line x1="260" y1="{y}" x2="294" y2="{y}" stroke="{color}" stroke-width="3"/>',
                  f'<text x="304" y="{y + 5}" fill="#d7e0e5" font-family="sans-serif" font-size="13">{html.escape(label)}</text>']
    parts.append(f'<text x="500" y="665" text-anchor="middle" fill="#9badb8" font-family="sans-serif" font-size="12">Initial state (theta, theta_dot)=({INITIAL[0]:.2f}, {INITIAL[1]:.2f}); 5 actions; 10 steps</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def make_html(result: dict, data: dict, svg_name: str = "phase-plane.svg") -> str:
    optimum = result["finite_catalogue_optimum"]
    baseline = result["zero_torque_baseline"]
    rows = "".join(
        f"<tr><th>{label}</th><td>{obj:.10f}</td><td>({state[0]:.6f}, {state[1]:.6f})</td></tr>"
        for label, obj, state in (("Finite catalogue optimum", optimum["objective_cost"], optimum["terminal_state"]),
                                  ("Zero torque", baseline["objective_cost"], baseline["terminal_state"])))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pendulum-v0 finite-action pilot</title>
<style>body{{margin:0;background:#101820;color:#edf3f6;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:24px}}figure{{margin:24px 0}}img{{width:100%;height:auto;border:1px solid #344653}}table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #40515d}}a{{color:#9fd5ff}}code{{overflow-wrap:anywhere}}</style></head>
<body><main><h1>Pendulum-v0: finite-action control pilot</h1>
<p>This source-attributed report re-expresses the Gym v0.21.0 Pendulum equations and scores a short fixed open-loop catalogue. It is an authored initial-state and action-catalogue adaptation, not the continuous-action, full-horizon Gym task.</p>
<figure><img src="{html.escape(svg_name)}" alt="Angle versus angular velocity trajectories for the selected finite action plan and zero-torque baseline"><figcaption>Unwrapped angle versus angular velocity; circles mark initial and terminal states.</figcaption></figure>
<table><thead><tr><th>Track</th><th>Accumulated cost</th><th>Terminal (theta, theta dot)</th></tr></thead><tbody>{rows}</tbody></table>
<p>Finite scope: {PLAN_COUNT:,} open-loop plans, {HORIZON} steps of {DT:.2f} s, torque catalogue {list(ACTIONS)} N·m, authored initial state {list(INITIAL)}. The search is exhaustive only over this catalogue and horizon.</p>
<p>Upstream notebook: <a href="{SOURCE_URL}">pinned `optimal_control` source</a> (blob <code>{UPSTREAM_NOTEBOOK_BLOB}</code>). Adopted simulator sources: <a href="{GYM_SOURCE_URL}">Pendulum dynamics</a> and <a href="{GYM_REGISTRY_URL}">Gym registry</a>; both are pinned to Gym v0.21.0 commit <code>{GYM_COMMIT}</code>. Raw record and figure data are included beside this page.</p>
<p>Reproduction: build the optional <code>csl_env717_pendulum</code> report driver and run <code>python3 scripts/reports/env717/check_pendulum.py &lt;driver&gt; --output &lt;new-directory&gt;</code>.</p>
</main></body></html>'''


def report_readme(result: dict) -> str:
    best = result["finite_catalogue_optimum"]
    baseline = result["zero_torque_baseline"]
    timing = result["runtime_measurement"]
    return f'''# Pendulum-v0 finite-action pilot

This report re-expresses the pinned Gym v0.21.0 Pendulum dynamics; it does not copy the upstream implementation. The original `optimal_control` notebook points to Gym `Pendulum-v0` but does not pin a simulator version. This pilot adopts Gym v0.21.0 commit `{GYM_COMMIT}` and records the exact environment and registry blobs.

## Model and scope

The physical state is `(theta, theta_dot)`. Gym uses `dt={DT}`, `g={GRAVITY}`, `m=l=1`, torque bound `[-{MAX_TORQUE},{MAX_TORQUE}]`, and angular-speed bound `[-{MAX_SPEED},{MAX_SPEED}]`. Each step clips the action, evaluates `angle_normalize(theta)^2 + 0.1*theta_dot^2 + 0.001*u^2` at the pre-step state, updates and clips angular velocity, then advances the angle using the clipped new velocity. The reward is the negative cost. Gym's `Pendulum-v0` wrapper has a 200-step time limit; this pilot uses only {HORIZON} steps.

The source reset samples random states. The pilot authors the reproducible initial state `{list(INITIAL)}` and restricts the continuous torque to `{list(ACTIONS)}` N·m. It exhaustively evaluates all `{PLAN_COUNT:,}` fixed open-loop sequences. The reported minimum is exact only for this finite catalogue, horizon and binary64 transition implementation; it is not a continuous-action or full-horizon optimum and is not a minimax result.

## Results

The finite-catalogue plan has accumulated source cost `{best['objective_cost']:.12f}` and reward `{best['reward']:.12f}`. Its selected torques are `{best['selected_actions_torque_nm']}` N·m; its terminal state is `({best['terminal_state'][0]:.10f}, {best['terminal_state'][1]:.10f})`. The zero-torque baseline has cost `{baseline['objective_cost']:.12f}`. The saved position-velocity phase portrait is generated from these replayed trajectories.

The native Release enumerator reports median `{timing['median_elapsed_ns'] / 1e6:.3f} ms` per complete catalogue search across `{timing['measured_repetitions']}` sequential repetitions after `{timing['warmup_repetitions']}` warmups (range `{timing['minimum_elapsed_ns'] / 1e6:.3f}–{timing['maximum_elapsed_ns'] / 1e6:.3f} ms`). The timed region includes decoding and propagation of every plan; it excludes JSON serialization, independent Python verification and report rendering. This is one implementation and one fixture, so no comparative performance conclusion is made. Raw repetitions and host/compiler data are in `result.json` and `capture.json`.

## Provenance and reproduction

- Upstream environment notebook: {SOURCE_URL}/Pendulum.ipynb (blob `{UPSTREAM_NOTEBOOK_BLOB}`).
- Adopted Gym source: {GYM_SOURCE_URL} (blob `{GYM_SOURCE_BLOB}`); registry: {GYM_REGISTRY_URL} (blob `{GYM_REGISTRY_BLOB}`).
- Upstream Gym license at this commit: MIT. The upstream `optimal_control` repository has no declared license; this report re-expresses equations and copies no source implementation.
- Build and run: `cmake -S benchmarks/reporting/env717/pendulum-build -B build/env717-pendulum -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`, `cmake --build build/env717-pendulum --target csl_env717_pendulum --parallel 2`, then `python3 scripts/reports/env717/check_pendulum.py build/env717-pendulum/csl_env717_pendulum --output reports/algorithm-results/env717-pendulum-pilot-v1`.
- The complete raw record, independently replayed optimum and checksums are saved with this report.
'''


def processor_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() == "model name" and value.strip():
                return value.strip()
    return platform.processor().strip() or platform.uname().processor.strip() or "unavailable"


def verify_result_and_bundle(result: dict, bundle: Path | None = None,
                             analysis: dict | None = None) -> None:
    if analysis is None:
        analysis = verify(result)
    if bundle is None:
        return
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("report bundle must be a real directory")
    entries = tuple(bundle.iterdir())
    if {path.name for path in entries} != set(BUNDLE_FILES) or any(path.is_symlink() or not path.is_file() for path in entries):
        raise ValueError("report bundle inventory differs")
    contents = {path.name: path.read_bytes() for path in entries}
    sums = {}
    for line in contents["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate checksum entry")
        sums[name] = digest
    actual = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items() if name != "SHA256SUMS"}
    if sums != actual:
        raise ValueError("report checksum inventory differs")
    result_bytes = contents["result.json"]
    if json.loads(result_bytes) != result:
        raise ValueError("saved result differs from verified result")
    data = figure_data(analysis, result)
    expected = {
        "README.md": report_readme(result).encode(),
        "figure-data.json": (json.dumps(data, indent=2, sort_keys=True) + "\n").encode(),
        "phase-plane.svg": make_svg(data).encode(),
        "index.html": make_html(result, data).encode(),
    }
    for name, value in expected.items():
        if contents[name] != value:
            raise ValueError(f"saved {name} differs from its verified source data")
    capture = json.loads(contents["capture.json"])
    if capture.get("runtime_measurement") != result["runtime_measurement"]:
        raise ValueError("capture measurement differs from result")


def create_bundle(result: dict, output: Path, analysis: dict) -> None:
    data = figure_data(analysis, result)
    environment = {
        "source_commit": result["provenance"]["source_commit"],
        "driver_sha256": result["provenance"]["driver_sha256"],
        "simulator_commit": GYM_COMMIT, "simulator_source_blob": GYM_SOURCE_BLOB,
        "platform": platform.platform(), "machine": platform.machine(),
        "processor": processor_model(), "logical_cpu_count": os.cpu_count(),
        "python": platform.python_version(), "arithmetic": "IEEE-754 binary64"}
    capture = {"schema": "csl.env717-capture/1", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
               "environment": environment, "runtime_measurement": result["runtime_measurement"],
               "capture_scope": "source-equation finite-action enumeration; no Gym package install or RL training run"}
    files = {
        "README.md": report_readme(result).encode(),
        "capture.json": (json.dumps(capture, indent=2, sort_keys=True) + "\n").encode(),
        "figure-data.json": (json.dumps(data, indent=2, sort_keys=True) + "\n").encode(),
        "index.html": make_html(result, data).encode(),
        "phase-plane.svg": make_svg(data).encode(),
        "result.json": (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()}
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (output / name).write_bytes(content)
    checksums = "".join(f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files))
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")
    verify_result_and_bundle(result, output, analysis)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-bundle", type=Path)
    parser.add_argument("--repetitions", type=int, default=MEASURED)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 1000:
        parser.error("--repetitions must be in 1..1000")
    if args.verify_bundle:
        result = json.loads((args.verify_bundle / "result.json").read_text(encoding="utf-8"))
        verify_result_and_bundle(result, args.verify_bundle)
        print(f"verified {PLAN_COUNT:,} finite action plans and bundle {args.verify_bundle}")
        return 0
    if args.executable and args.result:
        parser.error("choose either an executable or --result")
    if args.executable:
        completed = subprocess.run([str(args.executable.resolve(strict=True)), "--measure", str(args.repetitions)],
                                   check=True, capture_output=True, text=True)
        result = json.loads(completed.stdout)
    elif args.result:
        result = json.loads(args.result.read_text(encoding="utf-8"))
    else:
        parser.error("provide an executable, --result, or --verify-bundle")
    analysis = verify(result)
    if args.output:
        if not args.executable:
            parser.error("--output requires the native executable")
        create_bundle(result, args.output, analysis)
        print(f"captured and independently verified {PLAN_COUNT:,} plans in {args.output}")
    else:
        print(json.dumps({"plan_count": PLAN_COUNT, "objective_cost": analysis["objective_cost"],
                          "selected_plan_index": analysis["plan_index"],
                          "minimizer_count": analysis["minimizer_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

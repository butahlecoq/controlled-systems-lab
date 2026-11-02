#!/usr/bin/env python3
"""Independently replay and render the ENV-717 EarthOrbitalMotion catalog."""
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
import time

UPSTREAM_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
UPSTREAM_BLOB = "ce97d9d223a6ba6d02ce9a8f6a2fba26ef0fdd7d"
SOURCE_URL = (f"https://github.com/imm-rl-lab/optimal_control/blob/{UPSTREAM_COMMIT}/"
              "Environments/EarthOrbitalMotion/EarthOrbitalMotion.py")
G = 6.67448478e-20
EARTH_MASS = 5.9726e24
SPACECRAFT_MASS = 50.0
SAMPLE_PERIOD = 100.0
INNER_STEPS = 100
HORIZON = 20
BLOCK_LENGTHS = (7, 7, 6)
ACTION_VALUES = (-0.5, 0.0, 0.5)
ACTIONS = tuple((radial, angular) for radial in ACTION_VALUES for angular in ACTION_VALUES)
PLAN_COUNT = len(ACTIONS) ** len(BLOCK_LENGTHS)
INITIAL_RADIUS = 7000.0
TARGET_RADIUS = 6900.0
RUNNING_COST = 0.001
WARMUPS = 2
DEFAULT_REPETITIONS = 7
BUNDLE_FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
                "orbit-phase-plane.svg", "result.json", "SHA256SUMS")
ROOT = Path(__file__).resolve().parents[3]
DRIVER = ROOT / "benchmarks/reporting/env717/earth_orbit.cpp"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unreported"


def derivative(state: tuple[float, float, float, float], action: tuple[float, float]):
    radius, radial_velocity, angle, angular_rate = state
    radial, angular = action
    return (radial_velocity,
            radius * angular_rate * angular_rate - G * EARTH_MASS / radius**2
            + radial / (1000.0 * SPACECRAFT_MASS),
            angular_rate,
            -2.0 * angular_rate * radial_velocity / radius
            + angular / (radius * SPACECRAFT_MASS * 1000.0))


def add_scaled(state, delta, scale):
    return tuple(state[i] + scale * delta[i] for i in range(4))


def advance(state, action):
    step = SAMPLE_PERIOD / INNER_STEPS
    for _ in range(INNER_STEPS):
        k1 = derivative(state, action)
        k2 = derivative(add_scaled(state, k1, step / 2.0), action)
        k3 = derivative(add_scaled(state, k2, step / 2.0), action)
        k4 = derivative(add_scaled(state, k3, step), action)
        state = tuple(state[i] + step * (k1[i] + 2*k2[i] + 2*k3[i] + k4[i]) / 6.0
                      for i in range(4))
    return state


def decode(index: int) -> tuple[int, int, int]:
    result = []
    for _ in BLOCK_LENGTHS:
        result.append(index % len(ACTIONS))
        index //= len(ACTIONS)
    return tuple(result)


def target_rate() -> float:
    return math.sqrt(G * EARTH_MASS / TARGET_RADIUS**3)


def evaluate(control_indices: tuple[int, int, int]):
    state = (INITIAL_RADIUS, 0.0, 0.0, math.sqrt(G * EARTH_MASS / INITIAL_RADIUS**3))
    objective = 0.0
    trajectory = [{"stage": 0, "time_seconds": 0.0, "radius_km": state[0],
                   "radial_velocity_km_s": state[1], "angle_rad": state[2],
                   "angular_rate_rad_s": state[3], "control": list(ACTIONS[control_indices[0]])}]
    stage = 0
    for block, count in enumerate(BLOCK_LENGTHS):
        action = ACTIONS[control_indices[block]]
        action_cost = RUNNING_COST * math.hypot(*action) * SAMPLE_PERIOD
        for _ in range(count):
            state = advance(state, action)
            stage += 1
            if stage == HORIZON:
                objective += math.hypot(TARGET_RADIUS - state[0],
                                         100000.0 * (target_rate() - state[3]))
            else:
                objective += action_cost
            next_control = ACTIONS[control_indices[block if stage < sum(BLOCK_LENGTHS[:block+1])
                                                       else min(block+1, len(BLOCK_LENGTHS)-1)]]
            trajectory.append({"stage": stage, "time_seconds": stage * SAMPLE_PERIOD,
                               "radius_km": state[0], "radial_velocity_km_s": state[1],
                               "angle_rad": state[2], "angular_rate_rad_s": state[3],
                               "control": list(next_control)})
    return objective, state, trajectory


def close(actual: float, expected: float, name: str, tolerance: float = 2e-8) -> None:
    if not math.isclose(actual, expected, rel_tol=2e-11, abs_tol=tolerance):
        raise ValueError(f"{name}: {actual!r} != {expected!r}")


def verify(raw: dict) -> dict:
    expected = {"schema": "csl.env717-earth-orbit/1",
                "source_repository_commit": UPSTREAM_COMMIT,
                "source_file_blob": UPSTREAM_BLOB,
                "plan_count": PLAN_COUNT,
                "warmups": WARMUPS}
    for key, value in expected.items():
        if raw.get(key) != value:
            raise ValueError(f"source or catalog identity differs: {key}")
    if raw.get("build_type") != "Release":
        raise ValueError("the recorded search must be built in Release mode")
    if raw.get("driver_sha256") != digest(DRIVER.read_bytes()):
        raise ValueError("driver hash does not match the source file")

    records = raw.get("plans")
    if not isinstance(records, list) or len(records) != PLAN_COUNT:
        raise ValueError("the complete 729-plan record is required")
    minimum = math.inf
    selected = -1
    selected_replay = None
    zero_objective = None
    seen = set()
    for index, record in enumerate(records):
        expected_indices = decode(index)
        if record.get("plan_index") != index or tuple(record.get("control_indices", ())) != expected_indices:
            raise ValueError(f"plan identity differs at {index}")
        if any(i < 0 or i >= len(ACTIONS) for i in expected_indices):
            raise ValueError(f"invalid action index in plan {index}")
        objective, terminal, trajectory = evaluate(expected_indices)
        close(record.get("objective_cost", math.nan), objective, f"objective[{index}]")
        recorded_state = record.get("terminal_state", ())
        if len(recorded_state) != 4:
            raise ValueError(f"terminal-state shape differs at plan {index}")
        for coordinate, (actual, expected_value) in enumerate(zip(recorded_state, terminal)):
            close(actual, expected_value, f"terminal[{index}][{coordinate}]")
        seen.add(index)
        if objective < minimum:
            minimum, selected = objective, index
            selected_replay = trajectory
        if expected_indices == (4, 4, 4):
            zero_objective = objective
    if len(seen) != PLAN_COUNT:
        raise ValueError("catalogue has missing or duplicate plans")
    if raw.get("selected_plan_index") != selected:
        raise ValueError("selected plan differs from independent exhaustive replay")
    close(raw.get("minimum_objective_cost", math.nan), minimum, "minimum objective")
    if zero_objective is None or zero_objective <= minimum:
        raise ValueError("zero-action baseline is not worse than the selected plan")
    return {"selected_index": selected, "objective": minimum,
            "zero_objective": zero_objective, "trajectory": selected_replay}


def profile_probe(driver: Path) -> dict:
    try:
        import resource
    except ImportError:
        return {"available": False, "reason": "resource usage counters are unavailable on this platform"}
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    subprocess.run([str(driver), "--repetitions", "1"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    user = after.ru_utime - before.ru_utime
    system = after.ru_stime - before.ru_stime
    return {"available": True, "run_type": "separate, unreported profiling probe",
            "warmups": WARMUPS, "measured_searches": 1,
            "user_cpu_seconds": user, "system_cpu_seconds": system,
            "wall_seconds": elapsed,
            "cpu_utilization_percent": 100.0 * (user + system) / elapsed}


def svg_plot(selected: list[dict], zero: list[dict]) -> str:
    width, height = 900, 620
    left, right, top, bottom = 104, 852, 68, 520
    radii = [p["radius_km"] for path in (selected, zero) for p in path] + [TARGET_RADIUS]
    rates = [p["angular_rate_rad_s"] for path in (selected, zero) for p in path] + [target_rate()]
    rlo, rhi = min(radii) - 5.0, max(radii) + 5.0
    wlo, whi = min(rates) - 0.000002, max(rates) + 0.000002
    def xy(point):
        x = left + (point["radius_km"] - rlo) / (rhi - rlo) * (right - left)
        y = bottom - (point["angular_rate_rad_s"] - wlo) / (whi - wlo) * (bottom - top)
        return x, y
    def polyline(path, color, dash=""):
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, path))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"{dash_attr}/>'
    target_x = left + (TARGET_RADIUS - rlo) / (rhi-rlo) * (right-left)
    target_y = bottom - (target_rate()-wlo)/(whi-wlo)*(bottom-top)
    selected_start = xy(selected[0])
    selected_end = xy(selected[-1])
    zero_end = xy(zero[-1])
    ticks = []
    for i in range(6):
        x = left + i * (right-left)/5
        y = top + i * (bottom-top)/5
        rvalue = rlo + i*(rhi-rlo)/5
        wvalue = whi - i*(whi-wlo)/5
        ticks.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#e1e5ec"/>')
        ticks.append(f'<text x="{x:.2f}" y="{bottom+24}" text-anchor="middle">{rvalue:.1f}</text>')
        ticks.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#e1e5ec"/>')
        ticks.append(f'<text x="{left-12}" y="{y+4:.2f}" text-anchor="end">{wvalue:.7f}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">EarthOrbitalMotion radius and angular-rate trajectories</title>
<desc id="desc">Finite-catalog selected plan and zero-action baseline in radius-angular-rate coordinates. Target orbit is marked with a cross.</desc>
<rect width="100%" height="100%" fill="#fff"/><text x="{width/2}" y="32" text-anchor="middle" font-size="20" font-family="sans-serif">EarthOrbitalMotion: selected finite plan and zero-action baseline</text>
<g font-family="sans-serif" font-size="12">{''.join(ticks)}</g>
<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="#26364a"/>
{polyline(zero, '#718096', '8 5')}{polyline(selected, '#1565c0')}
<circle cx="{selected_start[0]:.2f}" cy="{selected_start[1]:.2f}" r="5" fill="#fff" stroke="#17212f" stroke-width="2"/>
<circle cx="{selected_end[0]:.2f}" cy="{selected_end[1]:.2f}" r="5" fill="#1565c0" stroke="#fff" stroke-width="1"/>
<circle cx="{zero_end[0]:.2f}" cy="{zero_end[1]:.2f}" r="4" fill="#fff" stroke="#718096" stroke-width="2"/>
<path d="M {target_x-8:.2f} {target_y:.2f} h 16 M {target_x:.2f} {target_y-8:.2f} v 16" stroke="#c62828" stroke-width="3"/>
<text x="{(left+right)/2}" y="{height-35}" text-anchor="middle" font-family="sans-serif">Radius (km)</text>
<text x="25" y="{(top+bottom)/2}" transform="rotate(-90 25 {(top+bottom)/2})" text-anchor="middle" font-family="sans-serif">Angular rate (rad/s)</text>
<line x1="{left+20}" y1="{bottom-44}" x2="{left+55}" y2="{bottom-44}" stroke="#1565c0" stroke-width="3"/><text x="{left+63}" y="{bottom-40}" font-family="sans-serif">selected plan</text>
<line x1="{left+220}" y1="{bottom-44}" x2="{left+255}" y2="{bottom-44}" stroke="#718096" stroke-width="3" stroke-dasharray="8 5"/><text x="{left+263}" y="{bottom-40}" font-family="sans-serif">zero action</text>
<path d="M {left+390} {bottom-44} h 20 M {left+400} {bottom-54} v 20" stroke="#c62828" stroke-width="3"/><text x="{left+417}" y="{bottom-40}" font-family="sans-serif">target orbit</text>
</svg>'''


def make_bundle(raw: dict, output: Path, repetitions: int, driver: Path) -> dict:
    checked = verify(raw)
    limiter_profile = profile_probe(driver)
    zero_index = sum(4 * (9 ** block) for block in range(len(BLOCK_LENGTHS)))
    zero = evaluate(decode(zero_index))[2]
    raw["independent_verification"] = {
        "complete_catalogue_replayed": True, "verified_plan_count": PLAN_COUNT,
        "selected_plan_index": checked["selected_index"],
        "relative_tolerance": 2e-11, "absolute_tolerance": 2e-8,
        "method": "independent Python RK4 replay of every recorded plan"}
    measurements = raw["measured_repetitions_ns"]
    if len(measurements) != repetitions or any(value <= 0 for value in measurements):
        raise ValueError("timing repetition count or values differ")
    figure_data = {"schema": "csl.env717-earth-orbit-figure/1",
                   "coordinates": ["radius_km", "angular_rate_rad_s"],
                   "selected_plan_index": checked["selected_index"],
                   "selected_trajectory": checked["trajectory"],
                   "zero_control_trajectory": zero,
                   "target": {"radius_km": TARGET_RADIUS, "angular_rate_rad_s": target_rate()}}
    durations_ms = [value / 1e6 for value in measurements]
    capture = {"schema": "csl.env717-earth-orbit-capture/1",
               "captured_at_utc": datetime.now(timezone.utc).isoformat(),
               "host": {"os": platform.platform(), "machine": platform.machine(),
                        "cpu_model": cpu_model(), "python": sys.version,
                        "logical_cpu_count": os.cpu_count()},
               "build": {"compiler_id": raw["compiler_id"], "compiler_version": raw["compiler_version"],
                         "configuration": raw["build_type"], "architecture": raw["architecture"],
                         "library_source_commit": raw["source_commit"]},
               "measurement": {"repetitions": repetitions, "warmups": WARMUPS,
                               "requested_workers": 1, "actual_workers": 1,
                               "failed_plans": 0,
                               "median_ms": statistics.median(durations_ms),
                               "range_ms": [min(durations_ms), max(durations_ms)],
                               "raw_repetitions_ns": measurements,
                               "timed_region": "complete 729-plan decode, RK4 propagation and scoring; excludes JSON export, independent replay and rendering"},
               "limiter_profile": limiter_profile}
    objective = checked["objective"]
    selected_indices = decode(checked["selected_index"])
    selected_actions = [list(ACTIONS[i]) for i in selected_indices]
    result_summary = {
        "schema": raw["schema"], "environment": "EarthOrbitalMotion",
        "source_repository": "imm-rl-lab/optimal_control",
        "source_repository_commit": UPSTREAM_COMMIT,
        "source_file": "Environments/EarthOrbitalMotion/EarthOrbitalMotion.py",
        "source_file_blob": UPSTREAM_BLOB, "source_file_url": SOURCE_URL,
        "source_license": "no license declared in repository metadata; equations re-expressed",
        "source_model": {"state_order": ["time_seconds", "radius_km", "radial_velocity_km_s",
                                                  "angle_rad", "angular_rate_rad_s"],
                          "gravitational_constant_km3_kg_s2": G,
                          "earth_mass_kg": EARTH_MASS, "spacecraft_mass_kg": SPACECRAFT_MASS,
                          "sample_period_seconds": SAMPLE_PERIOD, "inner_rk4_steps_per_sample": INNER_STEPS,
                          "original_terminal_time_seconds": 2000,
                          "action_bounds": [[-0.5, -0.5], [0.5, 0.5]],
                          "terminal_cost": "norm([target_radius-radius, 100000*(target_rate-angular_rate)])",
                          "running_cost": "0.001 * norm(action) * dt"},
        "pilot_adaptation": {"initial_radius_km": INITIAL_RADIUS,
                             "source_default_initial_radius_km": TARGET_RADIUS,
                             "initial_radial_velocity_km_s": 0.0,
                             "initial_angular_rate": "source constructor circular rate at authored initial radius",
                             "target_radius_km": TARGET_RADIUS,
                             "horizon_steps": HORIZON,
                             "action_catalogue": [list(a) for a in ACTIONS],
                             "piecewise_constant_block_lengths": list(BLOCK_LENGTHS),
                             "plan_count": PLAN_COUNT,
                             "policy_information_pattern": "open-loop; 3 fixed control vectors selected before rollout"},
        "finite_catalogue_result": {"complete_plan_count": PLAN_COUNT,
                                    "selected_plan_index": checked["selected_index"],
                                    "selected_control_indices": list(selected_indices),
                                    "selected_block_actions": selected_actions,
                                    "minimum_cost": objective, "source_reward": -objective,
                                    "zero_control_cost": checked["zero_objective"],
                                    "terminal_state_physical_order": [HORIZON * SAMPLE_PERIOD,
                                        *raw["plans"][checked["selected_index"]]["terminal_state"]]},
        "search": {"status": "complete", "failed_plan_count": 0,
                   "evaluated_plan_count": PLAN_COUNT,
                   "selected_plan_independently_replayed": True,
                   "all_plan_scores_independently_replayed": True},
        "raw_driver_record": raw}
    if output.exists() and (output.is_symlink() or not output.is_dir() or any(output.iterdir())):
        raise ValueError("refusing to overwrite a nonempty or unsafe output directory")
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "README.md": render_readme(result_summary, capture).encode(),
        "capture.json": (json.dumps(capture, indent=2, sort_keys=True) + "\n").encode(),
        "figure-data.json": (json.dumps(figure_data, indent=2, sort_keys=True) + "\n").encode(),
        "index.html": render_html(result_summary, capture).encode(),
        "orbit-phase-plane.svg": svg_plot(checked["trajectory"], zero).encode(),
        "result.json": (json.dumps(result_summary, indent=2, sort_keys=True) + "\n").encode(),
    }
    for name, data in files.items():
        (output / name).write_bytes(data)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items()))
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")
    return result_summary


def render_html(result: dict, capture: dict) -> str:
    summary = result["finite_catalogue_result"]
    timing = capture["measurement"]
    selected = html.escape(json.dumps(result["pilot_adaptation"]["action_catalogue"]))
    profile = capture["limiter_profile"]
    profile_text = (f"A separate, unreported process probe used {profile['cpu_utilization_percent']:.1f}% CPU, "
                    "consistent with compute-bound integration." if profile.get("available") else
                    "A separate CPU-usage probe was unavailable on this platform.")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EarthOrbitalMotion finite-catalog control pilot</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#17212f}}img,object{{max-width:100%}}code{{background:#eef1f5;padding:.15rem .3rem}}</style>
<main><h1>EarthOrbitalMotion finite-catalog control pilot</h1>
<p>This is a source-equation adaptation of the upstream nonlinear orbital-control environment. It uses 729 open-loop plans from a three-block finite action catalog. It is exact only over those plans and inputs; it is not an optimum over continuous controls or feedback policies.</p>
<p>Source: <a href="{SOURCE_URL}">pinned upstream file</a>, commit <code>{UPSTREAM_COMMIT}</code>, blob <code>{UPSTREAM_BLOB}</code>. The source repository has no declared license; the equations are re-expressed, not copied.</p>
<h2>Orbit phase plane</h2><object data="orbit-phase-plane.svg" type="image/svg+xml"><img src="orbit-phase-plane.svg" alt="Radius and angular rate trajectories"></object>
<p>Horizontal coordinate is orbital radius in km; vertical coordinate is angular rate in rad/s. The red cross marks the 6900 km target circular orbit. The gray dashed line shows zero control; blue shows the selected plan.</p>
<h2>Finite-catalog result</h2><p>Complete catalog: {PLAN_COUNT} plans. Selected plan index {summary['selected_plan_index']}, cost {summary['minimum_cost']:.12f}; zero-control cost {summary['zero_control_cost']:.12f}. The cost is the negative of the source reward accumulated over the authored finite episode.</p>
<p>Block actions (radial, angular): <code>{html.escape(json.dumps(summary['selected_block_actions']))}</code>. Catalog vectors: <code>{selected}</code>.</p>
<h2>Timing scope</h2><p>Release enumeration median {timing['median_ms']:.3f} ms over {timing['repetitions']} repetitions (range {timing['range_ms'][0]:.3f}–{timing['range_ms'][1]:.3f} ms). The timer includes full plan decoding, RK4 propagation and scoring, and excludes export and independent replay. {html.escape(profile_text)} This is descriptive for one small finite catalog, not a comparison or performance claim.</p>
<h2>Reproduction</h2><p>Build <code>csl_env717_earth_orbit</code> with <code>CSL_BUILD_ENV717_REPORT=ON</code>, then run <code>python3 scripts/reports/env717/check_earth_orbit.py &lt;driver&gt; --output &lt;directory&gt;</code>. The checker independently replays all 729 plans, writes the JSON evidence, phase-plane SVG and SHA256 manifest.</p>
<p><a href="result.json">Raw result</a> · <a href="figure-data.json">Figure data</a> · <a href="capture.json">Capture metadata</a> · <a href="SHA256SUMS">Checksums</a></p></main></html>'''


def render_readme(result: dict, capture: dict) -> str:
    summary = result["finite_catalogue_result"]
    timing = capture["measurement"]
    profile = capture["limiter_profile"]
    profile_text = (f"A separate, unreported process profile used {profile['cpu_utilization_percent']:.1f}% CPU, "
                    "so the search is compute-bound by integration." if profile.get("available") else
                    "A separate CPU-usage profile was unavailable on this platform.")
    return f'''# EarthOrbitalMotion finite-catalog control pilot

This report re-expresses the source equations from [`EarthOrbitalMotion.py`]({SOURCE_URL}) at upstream commit `{UPSTREAM_COMMIT}` (blob `{UPSTREAM_BLOB}`). The repository has no declared license, so this report copies no source implementation.

## Model and adaptation

The physical state is `(time, radius, radial velocity, angle, angular rate)` in seconds, km, km/s, radians and radians/s. The source parameters are `G={G}`, Earth mass `{EARTH_MASS}` kg, spacecraft mass `{SPACECRAFT_MASS}` kg, `dt=100 s`, 100 RK4 substeps per decision and terminal time 2000 s. Each action has radial and angular components bounded by `[-0.5, 0.5]`. Running cost is `0.001 * norm(action) * dt`; the terminal cost is the Euclidean norm of radius error and `100000` times angular-rate error.

The source default starts on the 6900 km target orbit and therefore has a zero-control baseline. This pilot authors an initial radius of 7000 km, with zero radial velocity and the source constructor's circular angular rate at that radius. It retains the 6900 km target, 20 decision stages and 2000 second horizon. The continuous controls are replaced by nine grid vectors from `{-0.5, 0, 0.5}²`. A plan chooses one vector for each of three fixed blocks of 7, 7 and 6 stages. The complete `9³=729` open-loop catalog is exhaustively scored. The result is not a continuous-action optimum, feedback policy, minimax result or RL-training reproduction.

## Result

Independent Python replay verifies every one of the 729 plans. Selected plan index `{summary['selected_plan_index']}` has cost `{summary['minimum_cost']:.12f}` (source reward `{-summary['minimum_cost']:.12f}`), compared with zero-control cost `{summary['zero_control_cost']:.12f}`. The selected block actions are `{summary['selected_block_actions']}`. The [phase-plane plot](orbit-phase-plane.svg) uses radius and angular rate, with both selected and zero-action trajectories and the target orbit.

The single-worker C++ Release driver reports median `{timing['median_ms']:.3f} ms` across {timing['repetitions']} sequential complete catalog searches after {timing['warmups']} warmups (range `{timing['range_ms'][0]:.3f}–{timing['range_ms'][1]:.3f} ms`); every plan completed successfully. It times plan decoding, source-equation propagation and scoring, not JSON export or independent verification. Each pass performs 1,458,000 inner RK4 steps. {profile_text} This single small fixture has no comparison claim; timings are descriptive.

## Reproduction

Configure and build with the repository's pinned CMake/Ninja versions:

```sh
mise exec cmake@3.31.6 ninja@1.12.1 -- cmake -S . -B build/env717-report \\
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \\
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_ENV717_REPORT=ON
mise exec cmake@3.31.6 ninja@1.12.1 -- cmake --build build/env717-report \\
  --target csl_env717_earth_orbit --parallel 2
python3 scripts/reports/env717/check_earth_orbit.py \\
  build/env717-report/csl_env717_earth_orbit \\
  --output reports/algorithm-results/env717-earth-orbit-pilot-v1
```

The checker independently enumerates and replays all plans, creates `result.json`, `figure-data.json`, `capture.json`, an HTML page, SVG figure and `SHA256SUMS`. The output remains scoped to the finite action and state adaptation above.
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", type=Path)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    completed = subprocess.run([str(args.driver), "--repetitions", str(args.repetitions)],
                               check=True, text=True, capture_output=True)
    raw = json.loads(completed.stdout)
    if args.output:
        result = make_bundle(raw, args.output, args.repetitions, args.driver)
        print(json.dumps(result["finite_catalogue_result"], sort_keys=True))
    else:
        verified = verify(raw)
        print(json.dumps({"selected_plan_index": verified["selected_index"],
                          "minimum_objective_cost": verified["objective"],
                          "zero_control_cost": verified["zero_objective"],
                          "verified_plans": PLAN_COUNT}, sort_keys=True))


if __name__ == "__main__":
    main()

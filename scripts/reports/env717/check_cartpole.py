"""Independently replay and publish the pinned finite-horizon CartPole pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import platform
import subprocess
from pathlib import Path

UPSTREAM_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
UPSTREAM_ENV_BLOB = "21d1122b701df85e21b5225fdbd42ff9f3bd702e"
UPSTREAM_LEARNING_BLOB = "5af9324376c342da177a411394730ccc3f7edd5b"
UPSTREAM_SOLVER_BLOB = "87485e23497e286022d76c6f2e70e0469aa18584"
GYM_COMMIT = "c755d5c35a25ab118746e2ba885894ff66fb8c43"
GYM_ENV_BLOB = "e11adcba6f413017e8661e8990dde668a63a129c"
GYM_REGISTRY_BLOB = "a90b0370730e74d783971a1a3f0771c5a2fb572e"
HORIZON = 14
PLAN_COUNT = 1 << HORIZON
GRAVITY = 9.8
CART_MASS = 1.0
POLE_MASS = 0.1
TOTAL_MASS = CART_MASS + POLE_MASS
HALF_POLE_LENGTH = 0.5
POLEMASS_LENGTH = POLE_MASS * HALF_POLE_LENGTH
FORCE_MAGNITUDE = 10.0
TIME_STEP = 0.02
CART_THRESHOLD = 2.4
ANGLE_THRESHOLD = 12.0 * 2.0 * math.pi / 360.0
INITIAL = (0.0, 0.0, 0.0, 0.0)


def close(left, right, *, absolute=2e-12, relative=2e-12):
    return math.isclose(left, right, rel_tol=relative, abs_tol=absolute)


def advance(state, control):
    x, x_dot, theta, theta_dot = state
    force = -FORCE_MAGNITUDE if control == 0 else FORCE_MAGNITUDE
    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)
    temp = (force + POLEMASS_LENGTH * theta_dot * theta_dot * sin_theta) / TOTAL_MASS
    theta_acc = (GRAVITY * sin_theta - cos_theta * temp) / (
        HALF_POLE_LENGTH * (4.0 / 3.0 - POLE_MASS * cos_theta * cos_theta / TOTAL_MASS))
    x_acc = temp - POLEMASS_LENGTH * theta_acc * cos_theta / TOTAL_MASS
    following = (x + TIME_STEP * x_dot, x_dot + TIME_STEP * x_acc,
                 theta + TIME_STEP * theta_dot, theta_dot + TIME_STEP * theta_acc)
    terminated = (following[0] < -CART_THRESHOLD or following[0] > CART_THRESHOLD or
                  following[2] < -ANGLE_THRESHOLD or following[2] > ANGLE_THRESHOLD)
    return following, terminated


def controls_for(plan_index):
    return [(plan_index >> step) & 1 for step in range(HORIZON)]


def replay(plan_index):
    controls = controls_for(plan_index)
    state = INITIAL
    steps = 0
    terminated = False
    trace = [state]
    for control in controls:
        state, terminated = advance(state, control)
        steps += 1
        trace.append(state)
        if terminated:
            break
    return {"plan_index": plan_index, "control_indices": controls,
            "reward": steps, "steps_executed": steps,
            "terminated": terminated, "terminal_state": state}, trace


def reachable_layers():
    """Enumerate distinct binary64 states after each live finite-action prefix."""
    live = {INITIAL}
    layers = []
    for _ in range(HORIZON):
        reached = set()
        terminated = set()
        following_live = set()
        for state in live:
            for control in (0, 1):
                next_state, done = advance(state, control)
                reached.add(next_state)
                if done:
                    terminated.add(next_state)
                else:
                    following_live.add(next_state)
        layers.append({"states": [list(state) for state in sorted(reached)],
                       "terminated_states": [list(state) for state in sorted(terminated)],
                       "reachable_state_count": len(reached),
                       "terminated_state_count": len(terminated)})
        live = following_live
    return layers


def verify(result):
    expected = {
        "schema": "csl.env717-cartpole/1",
        "scenario_id": "env717-cartpole-center-start-14-step-finite-catalogue-v1",
        "upstream_repository_commit": UPSTREAM_COMMIT,
        "upstream_environment_notebook": "Environments/CartPole/CartPole.ipynb",
        "upstream_environment_notebook_blob": UPSTREAM_ENV_BLOB,
        "upstream_learning_notebook": "CartPole_with_DCEM.ipynb",
        "upstream_learning_notebook_blob": UPSTREAM_LEARNING_BLOB,
        "upstream_solver": "Solvers/OneAgentSolver.py",
        "upstream_solver_blob": UPSTREAM_SOLVER_BLOB,
        "simulator_repository": "openai/gym",
        "simulator_version": "v0.21.0",
        "simulator_commit": GYM_COMMIT,
        "simulator_source": "gym/envs/classic_control/cartpole.py",
        "simulator_source_blob": GYM_ENV_BLOB,
        "simulator_registry_source": "gym/envs/__init__.py",
        "simulator_registry_blob": GYM_REGISTRY_BLOB,
        "state_order": ["cart_position_m", "cart_velocity_m_per_s", "pole_angle_rad",
                        "pole_angular_velocity_rad_per_s"],
    }
    if not isinstance(result, dict) or any(result.get(key) != value for key, value in expected.items()):
        raise ValueError("CartPole report identity differs")
    if result.get("reference_variant") != "equation-replayed Gym CartPole-v1 finite-horizon adaptation":
        raise ValueError("CartPole reference variant differs")
    params = result.get("source_parameters", {})
    parameter_values = {
        "gravity_m_per_s2": GRAVITY, "cart_mass_kg": CART_MASS, "pole_mass_kg": POLE_MASS,
        "pole_half_length_m": HALF_POLE_LENGTH, "force_magnitude_newtons": FORCE_MAGNITUDE,
        "sample_period_seconds": TIME_STEP, "cart_position_termination_threshold_m": CART_THRESHOLD,
        "pole_angle_termination_threshold_rad": ANGLE_THRESHOLD,
        "registered_cartpole_v1_time_limit_steps": 500, "initial_state": list(INITIAL),
        "integrator": "explicit Euler using old position and angle rates",
        "reward": "+1 per action, including the first terminal action",
        "termination": "strict cart position or pole angle threshold; stop immediately on done",
    }
    if any(params.get(key) != value for key, value in parameter_values.items()):
        raise ValueError("CartPole source parameters differ")
    if params.get("reset_support") != [[-0.05, 0.05]] * 4:
        raise ValueError("CartPole reset support differs")
    adaptation = result.get("adaptation", {})
    if (adaptation.get("horizon_environment_steps") != HORIZON or
            adaptation.get("plan_count") != PLAN_COUNT or
            adaptation.get("initial_state_choice") != "the exact zero vector, the midpoint of the source reset support" or
            adaptation.get("time_limit_handling") != "the 14-step pilot horizon is shorter than CartPole-v1's 500-step wrapper cap" or
            adaptation.get("semantics") != "finite open-loop action sequences; action history is fixed before the first transition" or
            adaptation.get("claim_boundary") != "maximum reward over this initial state and 14-step finite action catalogue only; not a learned policy or the original 500-step task"):
        raise ValueError("CartPole adaptation semantics differ")
    if adaptation.get("finite_action_catalogue") != [[0, "push left", -10.0], [1, "push right", 10.0]]:
        raise ValueError("CartPole finite action catalogue differs")
    if (result.get("upstream_dependency_status") !=
            "the upstream repository does not pin Gym; adopted Gym v0.21.0 because the pinned solver expects the legacy reset/step API"):
        raise ValueError("CartPole unpinned-dependency caveat is missing")
    performance = result.get("performance", {})
    if (performance.get("metric") != "finite_catalogue_enumeration_elapsed" or
            performance.get("unit") != "ns" or performance.get("worker_threads") != 1 or
            performance.get("warmup_repetitions") != 5 or
            not isinstance(performance.get("measured_repetitions"), int) or
            not 1 <= performance["measured_repetitions"] <= 1000):
        raise ValueError("CartPole measurement metadata differs")
    samples = performance.get("raw_elapsed_ns")
    if (not isinstance(samples, list) or len(samples) != performance["measured_repetitions"] or
            any(not isinstance(value, int) or value <= 0 for value in samples)):
        raise ValueError("CartPole timing samples are incomplete")
    ordered = sorted(samples)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else ordered[len(ordered) // 2 - 1] // 2 + ordered[len(ordered) // 2] // 2
    if (performance.get("median_elapsed_ns") != median or
            performance.get("minimum_elapsed_ns") != ordered[0] or
            performance.get("maximum_elapsed_ns") != ordered[-1]):
        raise ValueError("CartPole timing summary differs from samples")
    if not result.get("driver_sha256") or len(result["driver_sha256"]) != 64:
        raise ValueError("CartPole driver hash is missing")
    capture = result.get("capture_environment", {})
    if not all(capture.get(key) for key in ("compiler", "compiler_version", "build_type", "architecture")):
        raise ValueError("CartPole build metadata is incomplete")
    plans = result.get("plans")
    if not isinstance(plans, list) or len(plans) != PLAN_COUNT:
        raise ValueError("CartPole plan catalogue size differs")
    best_reward = -1
    maximizers = []
    transition_count = 0
    terminated_plan_count = 0
    terminated_before_horizon_count = 0
    for index, observed in enumerate(plans):
        expected_plan, _ = replay(index)
        if observed.get("plan_index") != index or observed.get("control_indices") != expected_plan["control_indices"]:
            raise ValueError(f"CartPole plan identity differs at row {index}")
        if (observed.get("reward") != expected_plan["reward"] or
                observed.get("steps_executed") != expected_plan["steps_executed"] or
                observed.get("terminated") is not expected_plan["terminated"]):
            raise ValueError(f"CartPole reward/termination differs at plan {index}")
        transition_count += expected_plan["steps_executed"]
        terminated_plan_count += int(expected_plan["terminated"])
        terminated_before_horizon_count += int(
            expected_plan["terminated"] and expected_plan["steps_executed"] < HORIZON)
        state = observed.get("terminal_state")
        if not isinstance(state, list) or len(state) != 4 or any(
                not close(actual, expected) for actual, expected in zip(state, expected_plan["terminal_state"])):
            raise ValueError(f"CartPole terminal state differs at plan {index}")
        if expected_plan["reward"] > best_reward:
            best_reward, maximizers = expected_plan["reward"], [index]
        elif expected_plan["reward"] == best_reward:
            maximizers.append(index)
    if result.get("objective_value") != best_reward or result.get("maximizing_plan_indices") != maximizers:
        raise ValueError("CartPole optimum family differs from exhaustive replay")
    enumeration = result.get("enumeration", {})
    if (enumeration.get("plan_count") != PLAN_COUNT or
            enumeration.get("transition_count") != transition_count or
            enumeration.get("terminated_plan_count") != terminated_plan_count or
            enumeration.get("terminated_before_horizon_count") != terminated_before_horizon_count or
            enumeration.get("all_plans_completed") is not True):
        raise ValueError("CartPole enumeration work count differs from independent replay")
    return {"maximum_reward": best_reward, "maximizers": maximizers,
            "transition_count": transition_count,
            "early_terminated_count": terminated_before_horizon_count}


def figure_data(analysis):
    layers = reachable_layers()
    selected_index = analysis["maximizers"][0]
    selected, trace = replay(selected_index)
    return {"schema": "csl.env717-cartpole-figure-data/1", "state_order": [
        "cart_position_m", "cart_velocity_m_per_s", "pole_angle_rad", "pole_angular_velocity_rad_per_s"],
        "projection_panels": [[0, 1], [2, 3]], "selected_plan_index": selected_index,
        "selected_plan_control_indices": selected["control_indices"],
        "selected_plan_reward": selected["reward"],
        "selected_plan_states": [list(state) for state in trace], "layers": layers}


def _bounds(values, threshold=None):
    low, high = min(values), max(values)
    if threshold is not None:
        low, high = min(low, -threshold), max(high, threshold)
    span = high - low
    pad = max(span * 0.08, 1e-3)
    return low - pad, high + pad


def svg_figure(data):
    width, height = 1280, 740
    panel = {"width": 570, "height": 490, "top": 102, "bottom": 592}
    specifications = [
        {"x_index": 0, "y_index": 1, "x_label": "Cart position x (m)",
         "y_label": "Cart velocity ẋ (m/s)", "title": "Cart position–velocity plane",
         "x_threshold": CART_THRESHOLD, "y_threshold": None},
        {"x_index": 2, "y_index": 3, "x_label": "Pole angle θ (rad)",
         "y_label": "Pole angular velocity θ̇ (rad/s)", "title": "Pole angle–angular velocity plane",
         "x_threshold": ANGLE_THRESHOLD, "y_threshold": None},
    ]
    all_states = [state for layer in data["layers"] for state in layer["states"]]
    all_failed = [state for layer in data["layers"] for state in layer["terminated_states"]]
    selected = data["selected_plan_states"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">CartPole finite-action reachable states and selected plan</title>',
        '<desc id="desc">Two coordinate projections show all finite-action prefix states, early termination points, and one selected maximum-reward trajectory.</desc>',
        '<rect width="100%" height="100%" fill="#101a23"/>',
        '<text x="640" y="34" fill="#f4f1e8" font-family="sans-serif" font-size="23" text-anchor="middle">CartPole · 14-step finite open-loop catalogue</text>',
        '<text x="640" y="61" fill="#b6c6d2" font-family="sans-serif" font-size="14" text-anchor="middle">Finite prefix states · early terminations · one maximizing plan · center initial state</text>']
    for panel_index, spec in enumerate(specifications):
        left = 42 + panel_index * 636
        plot_left, plot_right = left + 72, left + 592
        plot_top, plot_bottom = panel["top"], panel["bottom"]
        x_values = [state[spec["x_index"]] for state in all_states]
        y_values = [state[spec["y_index"]] for state in all_states]
        xmin, xmax = _bounds(x_values, spec["x_threshold"])
        ymin, ymax = _bounds(y_values, spec["y_threshold"])
        def project(x, y):
            return (plot_left + (x - xmin) / (xmax - xmin) * (plot_right - plot_left),
                    plot_bottom - (y - ymin) / (ymax - ymin) * (plot_bottom - plot_top))
        parts.extend([f'<text x="{(plot_left+plot_right)/2:.1f}" y="86" fill="#f4f1e8" font-family="sans-serif" font-size="18" text-anchor="middle">{html.escape(spec["title"])}</text>',
            f'<rect x="{plot_left}" y="{plot_top}" width="{plot_right-plot_left}" height="{plot_bottom-plot_top}" fill="#15232d" stroke="#71808c"/>'])
        for tick in range(5):
            value = xmin + tick * (xmax - xmin) / 4
            px, _ = project(value, ymin)
            parts.append(f'<path d="M {px:.2f} {plot_top} V {plot_bottom}" stroke="#33434e"/>')
            parts.append(f'<text x="{px:.2f}" y="{plot_bottom+20}" fill="#b6c6d2" font-family="sans-serif" font-size="11" text-anchor="middle">{value:.3g}</text>')
            value = ymin + tick * (ymax - ymin) / 4
            _, py = project(xmin, value)
            parts.append(f'<path d="M {plot_left} {py:.2f} H {plot_right}" stroke="#33434e"/>')
            parts.append(f'<text x="{plot_left-8}" y="{py+4:.2f}" fill="#b6c6d2" font-family="sans-serif" font-size="11" text-anchor="end">{value:.3g}</text>')
        if spec["x_threshold"] is not None:
            for threshold in (-spec["x_threshold"], spec["x_threshold"]):
                px, _ = project(threshold, ymin)
                parts.append(f'<path d="M {px:.2f} {plot_top} V {plot_bottom}" stroke="#ef6b5b" stroke-dasharray="5 4" opacity="0.85"/>')
        parts.append(f'<text x="{(plot_left+plot_right)/2:.1f}" y="{plot_bottom+51}" fill="#d9e1e6" font-family="sans-serif" font-size="14" text-anchor="middle">{html.escape(spec["x_label"])}</text>')
        parts.append(f'<text x="{left+18}" y="{(plot_top+plot_bottom)/2:.1f}" fill="#d9e1e6" font-family="sans-serif" font-size="14" text-anchor="middle" transform="rotate(-90 {left+18} {(plot_top+plot_bottom)/2:.1f})">{html.escape(spec["y_label"])}</text>')
        for stage, layer in enumerate(data["layers"], start=1):
            opacity = 0.14 + 0.34 * stage / HORIZON
            for state in layer["states"]:
                px, py = project(state[spec["x_index"]], state[spec["y_index"]])
                parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.0" fill="#63b4e6" opacity="{opacity:.2f}"/>')
            for state in layer["terminated_states"]:
                px, py = project(state[spec["x_index"]], state[spec["y_index"]])
                parts.append(f'<path d="M {px-3:.2f} {py-3:.2f} l 6 6 m -6 0 l 6 -6" stroke="#ff6b6b" stroke-width="1.4"/>')
        trajectory = [project(state[spec["x_index"]], state[spec["y_index"]]) for state in selected]
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in trajectory)
        parts.append(f'<polyline points="{points}" fill="none" stroke="#ffd166" stroke-width="3" stroke-linejoin="round"/>')
        for x, y in trajectory:
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="#ffd166" stroke="#101a23" stroke-width="1"/>')
    parts.extend(['<circle cx="398" cy="692" r="4" fill="#63b4e6" opacity="0.8"/><text x="410" y="697" fill="#d9e1e6" font-family="sans-serif" font-size="13">reachable finite-action prefixes</text>',
        '<path d="M 701 688 l 8 8 m -8 0 l 8 -8" stroke="#ff6b6b" stroke-width="1.5"/><text x="716" y="697" fill="#d9e1e6" font-family="sans-serif" font-size="13">first terminating state</text>',
        '<path d="M 1004 692 h 35" stroke="#ffd166" stroke-width="3"/><text x="1046" y="697" fill="#d9e1e6" font-family="sans-serif" font-size="13">selected maximizing trajectory</text>',
        '</svg>'])
    return "\n".join(parts)


def report_page(result, data, svg, report_generation, profile):
    selected = result["plans"][data["selected_plan_index"]]
    controls = " → ".join("R" if control else "L" for control in selected["control_indices"])
    term_count = result["enumeration"]["terminated_plan_count"]
    early_term_count = result["enumeration"]["terminated_before_horizon_count"]
    report_median = report_generation["median_elapsed_ns"] / 1e6
    profile_shares = [run["advance_state_self_percent"] for run in profile["runs"]]
    profile_low, profile_high = min(profile_shares), max(profile_shares)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CartPole finite-action pilot</title><style>body{{margin:0;background:#101a23;color:#edf2f5;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1240px;margin:auto;padding:24px}}a{{color:#8bd3f7}}svg{{width:100%;height:auto}}.note{{padding:12px;border-left:4px solid #f2c14e;background:#18232c}}table{{border-collapse:collapse}}th,td{{border:1px solid #53616c;padding:8px;text-align:left}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>CartPole finite-action pilot</h1>
<p>This report re-expresses the pinned <a href="https://github.com/imm-rl-lab/optimal_control/blob/{UPSTREAM_COMMIT}/CartPole_with_DCEM.ipynb">upstream DCEM notebook</a> and <a href="https://github.com/imm-rl-lab/optimal_control/blob/{UPSTREAM_COMMIT}/Environments/CartPole/CartPole.ipynb">environment note</a>. The notebook uses <code>gym.make("CartPole-v1")</code> but does not pin Gym; this pilot records the adopted <a href="https://github.com/openai/gym/tree/{GYM_COMMIT}">Gym v0.21.0</a> implementation, whose legacy reset/step API matches the pinned upstream solver.</p>
<p>The finite fixture starts at the exact zero vector (the midpoint of the source's independent uniform reset intervals), applies left/right forces of ±10 N for at most {HORIZON} steps, and exhaustively checks all {PLAN_COUNT:,} open-loop plans. The source uses explicit Euler at 0.02 s, a 1 m cart, 0.1 kg pole, 0.5 m half-length, and gravity 9.8 m/s². A step earns +1 including the first terminating step; the episode then stops.</p>
<p>The best finite reward is <strong>{result['objective_value']}</strong> of {HORIZON} steps, attained by {len(result['maximizing_plan_indices']):,} plans. The displayed witness is the smallest plan index, <code>{data['selected_plan_index']}</code> ({html.escape(controls)}). {early_term_count:,} plans terminate before the horizon; another {term_count - early_term_count:,} terminate on step {HORIZON} and still receive that step's reward.</p>
<div class="note"><strong>Scope:</strong> this is a deterministic, 14-step, finite open-loop adaptation from the center initial state. It is not a learned policy, a minimax calculation, or a solution of the original 500-step RL task. The upstream repository does not record its installed Gym version; no comparison is made to the notebook's learned episode scores.</div>
{svg}
<h2>Inputs and reproduction</h2><p>State order: cart position, cart velocity, pole angle, pole angular velocity. The figure shows the finite prefix states and first-termination states in both coordinate planes; the gold path is one independently replayed maximizing plan. Red vertical lines mark cart-position termination thresholds; termination angle thresholds are included in the pole panel.</p>
<pre><code>cmake -S benchmarks/reporting/env717/cartpole-build -B build/env717-cartpole -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-cartpole --config Release --target csl_env717_cartpole
python3 scripts/reports/env717/check_cartpole.py build/env717-cartpole/csl_env717_cartpole --repetitions 9
python3 scripts/reports/env717/check_cartpole.py --result reports/algorithm-results/env717-cartpole-pilot-v1/result.json --report-generation-evidence reports/algorithm-results/env717-cartpole-pilot-v1/report-generation.json --limiter-profile reports/algorithm-results/env717-cartpole-pilot-v1/profile.json --output build/env717-cartpole-reproduction</code></pre>
<p>Enumeration median: {result['performance']['median_elapsed_ns']/1e6:.6f} ms (range {result['performance']['minimum_elapsed_ns']/1e6:.6f}–{result['performance']['maximum_elapsed_ns']/1e6:.6f} ms across {result['performance']['measured_repetitions']} measured repetitions). The implementation completed {result['enumeration']['transition_count']:,} state transitions across {PLAN_COUNT:,} plans; these counts are independently reconstructed from the full result. This single-host measurement is descriptive, not a comparison or speedup claim.</p>
<p>Full report collection median: {report_median:.3f} ms (range {report_generation['minimum_elapsed_ns']/1e6:.3f}–{report_generation['maximum_elapsed_ns']/1e6:.3f} ms over {report_generation['measured_runs']} measured runs after {report_generation['warmup_runs']} discarded warmup). This includes the native collector, Python full-catalogue replay, projections, and report files; it excludes CMake configuration/build.</p>
<p>A separate GNU gprof diagnostic build sampled <code>advance_state</code> at {profile_low:.2f}–{profile_high:.2f}% self CPU across two profiles. Its 10 ms sampling interval is coarse, instrumentation changes runtime, and call-arc totals were excluded because they disagreed with the independently checked transition count. The flat samples identify finite transition propagation as the dominant hot path; they do not support a speedup claim.</p>
<table><tr><th>Quantity</th><th>Recorded value</th></tr><tr><td>Action plans</td><td>{PLAN_COUNT:,}</td></tr><tr><td>State transitions replayed</td><td>{result['enumeration']['transition_count']:,}</td></tr><tr><td>Maximum finite-horizon reward</td><td>{result['objective_value']} / {HORIZON}</td></tr><tr><td>Maximizing plans</td><td>{len(result['maximizing_plan_indices']):,}</td></tr><tr><td>Terminated before horizon</td><td>{early_term_count:,}</td></tr><tr><td>Terminated on final step</td><td>{term_count - early_term_count:,}</td></tr><tr><td>Enumeration median/range</td><td>{result['performance']['median_elapsed_ns']/1e6:.6f} ms / {result['performance']['minimum_elapsed_ns']/1e6:.6f}–{result['performance']['maximum_elapsed_ns']/1e6:.6f} ms</td></tr><tr><td>Full report collection median/range</td><td>{report_median:.3f} ms / {report_generation['minimum_elapsed_ns']/1e6:.3f}–{report_generation['maximum_elapsed_ns']/1e6:.3f} ms</td></tr></table>
<h2>Files</h2><ul><li><a href="result.json">Full result and every plan</a></li><li><a href="figure-data.json">Reachable-prefix figure data</a></li><li><a href="projections.svg">SVG figure</a></li><li><a href="profile.json">Limiter profile evidence</a></li><li><a href="report-generation.json">Full report-generation trials</a></li><li><a href="README.md">Reproduction notes</a></li></ul></main></body></html>'''


def report_readme(result, data, report_generation, profile):
    selected = result["plans"][data["selected_plan_index"]]
    return f'''# CartPole finite-action pilot

Upstream source commit: `{UPSTREAM_COMMIT}`. The source environment notebook is blob `{UPSTREAM_ENV_BLOB}`; the DCEM learning notebook is blob `{UPSTREAM_LEARNING_BLOB}`; `OneAgentSolver.py` is blob `{UPSTREAM_SOLVER_BLOB}`. The upstream calls Gym `CartPole-v1` but records no Gym package pin. This report adopts Gym v0.21.0 at `{GYM_COMMIT}`. The pinned solver unpacks the legacy four-value step result, which is the reason for this version selection. The Gym CartPole source file blob is `{GYM_ENV_BLOB}` and its registry blob is `{GYM_REGISTRY_BLOB}`.

This report independently re-expresses, rather than copies, the source equations. The upstream repository declares no license in its metadata; the adopted Gym source is MIT licensed. Initial state is the exact zero vector, the midpoint of the source reset support `[-0.05,0.05]^4`. The adaptation enumerates all `{PLAN_COUNT}` left/right open-loop plans for `{HORIZON}` steps or until the first strict position/angle termination. Every executed action receives reward `+1`, including the first terminating action. The maximum is `{result['objective_value']}` and `{len(result['maximizing_plan_indices'])}` plans attain it. The selected smallest-index witness is plan `{data['selected_plan_index']}` with `{selected['steps_executed']}` executed actions.

The figure shows exact finite-prefix point catalogs in `(cart position, cart velocity)` and `(pole angle, pole angular velocity)`, including first-termination states and one maximum-reward trajectory. The result file preserves all plan outcomes; the Python checker independently replays every plan and constructs the figure data.

This finite, deterministic, 14-step open-loop result is not a learned policy, minimax result, or solution of the original 500-step RL task. The notebook's learned episode scores are not compared because its Gym dependency is not pinned and those scores use different policy semantics.

## Reproduce

```sh
cmake -S benchmarks/reporting/env717/cartpole-build -B build/env717-cartpole -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-cartpole --config Release --target csl_env717_cartpole
python3 scripts/reports/env717/check_cartpole.py build/env717-cartpole/csl_env717_cartpole --repetitions 9
python3 scripts/reports/env717/capture_cartpole_report_generation.py --executable build/env717-cartpole/csl_env717_cartpole --checker scripts/reports/env717/check_cartpole.py --profile reports/algorithm-results/env717-cartpole-pilot-v1/profile.json --output build/env717-cartpole/report-generation.json
python3 scripts/reports/env717/check_cartpole.py build/env717-cartpole/csl_env717_cartpole --repetitions 9 --report-generation-evidence build/env717-cartpole/report-generation.json --limiter-profile reports/algorithm-results/env717-cartpole-pilot-v1/profile.json --output build/env717-cartpole/reproduction
```

Enumeration timing includes allocation, all `{result['enumeration']['transition_count']}` completed state transitions, termination checks, and reward evaluation for all plans. Five warmups preceded nine measured Release calls; the single-host median and range are descriptive only.

The full report collection was separately timed over `{report_generation['measured_runs']}` runs after `{report_generation['warmup_runs']}` discarded warmup, with median `{report_generation['median_elapsed_ns'] / 1e6:.3f} ms` (range `{report_generation['minimum_elapsed_ns'] / 1e6:.3f}–{report_generation['maximum_elapsed_ns'] / 1e6:.3f} ms`). This includes the native collector, independent full-catalogue replay, projection generation and report file writes; it excludes configure/build.

The limiter diagnostic uses GNU gprof 2.47 on a separate Release `-pg -fno-inline` build. Two 300-repetition profiles used 10 ms samples and placed `{min(run['advance_state_self_percent'] for run in profile['runs']):.2f}–{max(run['advance_state_self_percent'] for run in profile['runs']):.2f}%` of sampled self CPU in `advance_state`. The profiles are coarse and instrumented; call-arc totals were not used because they disagree with independently verified transition totals. `profile.json` and `report-generation.json` preserve the evidence and limits.
'''


def processor_model():
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in ("model name", "hardware") and value.strip():
                return value.strip()
    return platform.processor().strip() or platform.uname().processor.strip() or "unavailable"


def verify_performance_evidence(report_generation: dict, profile: dict, result: dict):
    if not isinstance(report_generation, dict) or not isinstance(profile, dict):
        raise ValueError("CartPole full-run or limiter-profile evidence must be JSON objects")
    raw_report_samples = report_generation.get("raw_elapsed_ns")
    process_statuses = report_generation.get("process_statuses")
    warmup_samples = report_generation.get("warmup_elapsed_ns")
    profile_runs = profile.get("runs")
    runner_path = Path(__file__).with_name("capture_cartpole_report_generation.py")
    valid_statuses = (isinstance(process_statuses, list) and len(process_statuses) == 6 and
        all(isinstance(item, dict) and item.get("status") == "completed" and
            isinstance(item.get("elapsed_ns"), int) and
            item["elapsed_ns"] > 0 for item in process_statuses) and
        sum(item.get("kind") == "warmup" for item in process_statuses) == 1 and
        sum(item.get("kind") == "measured" for item in process_statuses) == 5 and
        [item.get("index") for item in process_statuses if item.get("kind") == "measured"] == list(range(5)) and
        [item.get("index") for item in process_statuses if item.get("kind") == "warmup"] == [0] and
        [item["elapsed_ns"] for item in process_statuses if item.get("kind") == "measured"] == raw_report_samples and
        [item["elapsed_ns"] for item in process_statuses if item.get("kind") == "warmup"] == warmup_samples)
    if (report_generation.get("schema") != "csl.env717-cartpole-report-generation/1" or
            report_generation.get("metric") != "full_report_collection_elapsed" or
            report_generation.get("measured_runs") != 5 or
            report_generation.get("warmup_runs") != 1 or
            report_generation.get("failed_runs") != 0 or
            not isinstance(raw_report_samples, list) or len(raw_report_samples) != 5 or
            any(not isinstance(sample, int) or sample <= 0 for sample in raw_report_samples) or
            report_generation.get("minimum_elapsed_ns") != min(raw_report_samples) or
            report_generation.get("maximum_elapsed_ns") != max(raw_report_samples) or
            report_generation.get("median_elapsed_ns") != sorted(raw_report_samples)[2] or
            not isinstance(warmup_samples, list) or len(warmup_samples) != 1 or
            not isinstance(warmup_samples[0], int) or warmup_samples[0] <= 0 or
            not valid_statuses or
            report_generation.get("driver_sha256") != result.get("driver_sha256") or
            report_generation.get("checker_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or
            report_generation.get("runner_sha256") != hashlib.sha256(runner_path.read_bytes()).hexdigest() or
            not isinstance(report_generation.get("host_logical_cpu_count"), int) or
            report_generation["host_logical_cpu_count"] < 1 or
            not isinstance(report_generation.get("python"), str) or
            not report_generation.get("scope") or
            profile.get("schema") != "csl.env717-cartpole-limiter-profile/1" or
            not isinstance(profile_runs, list) or len(profile_runs) != 2 or
            profile.get("tool") != "GNU gprof 2.47" or
            profile.get("build_type") != "Release" or
            profile.get("source_commit") != result.get("source_commit") or
            profile.get("driver_sha256") != result.get("driver_sha256") or
            profile.get("diagnostic_only") is not True or
            profile.get("build_flags") != ["-O3", "-DNDEBUG", "-pg", "-fno-inline"] or
            not isinstance(profile.get("profile_binary_sha256"), str) or
            len(profile["profile_binary_sha256"]) != 64 or
            profile.get("call_arc_use") != "excluded because gprof call counts disagree with independently verified transition counts" or
            any(not isinstance(run, dict) or run.get("top_function") != "advance_state" or
                not isinstance(run.get("advance_state_self_percent"), (float, int)) or
                not 0 < run["advance_state_self_percent"] <= 100 or
                run.get("sample_period_ms") != 10 or
                run.get("repetitions") != 300 or
                run.get("transition_count") != result["enumeration"]["transition_count"] or
                not isinstance(run.get("gmon_sha256"), str) or len(run["gmon_sha256"]) != 64 or
                not isinstance(run.get("flat_profile_sha256"), str) or len(run["flat_profile_sha256"]) != 64 or
                not isinstance(run.get("flat_profile_excerpt"), list) or
                not run["flat_profile_excerpt"] or
                "advance_state(" not in run.get("flat_profile_top_row", "") or
                f"{run['advance_state_self_percent']:.2f}" not in run["flat_profile_top_row"]
                for run in profile_runs)):
        raise ValueError("CartPole full-run or limiter-profile evidence differs")


def write_report(result, output: Path, report_generation: dict, profile: dict):
    analysis = verify(result)
    data = figure_data(analysis)
    svg = svg_figure(data)
    verify_performance_evidence(report_generation, profile, result)
    report_generation_bytes = (json.dumps(report_generation, indent=2) + "\n").encode()
    profile_bytes = (json.dumps(profile, indent=2) + "\n").encode()
    environment = {"scenario_id": result["scenario_id"], "reference_variant": result["reference_variant"],
        "upstream_repository_commit": UPSTREAM_COMMIT, "upstream_environment_notebook_blob": UPSTREAM_ENV_BLOB,
        "upstream_learning_notebook_blob": UPSTREAM_LEARNING_BLOB, "upstream_solver_blob": UPSTREAM_SOLVER_BLOB,
        "simulator_version": result["simulator_version"], "simulator_commit": GYM_COMMIT,
        "simulator_source_blob": GYM_ENV_BLOB, "simulator_registry_blob": GYM_REGISTRY_BLOB,
        "driver_sha256": result["driver_sha256"], "build": result["capture_environment"],
        "platform": platform.platform(), "machine": platform.machine(), "processor": processor_model(),
        "logical_cpu_count": os.cpu_count(), "python": platform.python_version(),
        "arithmetic": "IEEE-754 binary64"}
    capture = {"source_commit": result["source_commit"], "driver_sha256": result["driver_sha256"],
        "build": result["capture_environment"],
        "capture_kind": "source-equation finite-action enumeration and descriptive single-host timing; no Gym installation or RL training run",
        "performance": result["performance"],
        "report_generation_sha256": hashlib.sha256(report_generation_bytes).hexdigest(),
        "limiter_profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "report_generation": report_generation, "limiter_profile": profile}
    readme = report_readme(result, data, report_generation, profile)
    files = {"README.md": readme.encode(), "capture.json": (json.dumps(capture, indent=2) + "\n").encode(),
        "environment.json": (json.dumps(environment, indent=2) + "\n").encode(),
        "figure-data.json": (json.dumps(data, indent=2) + "\n").encode(),
        "index.html": report_page(result, data, svg, report_generation, profile).encode(),
        "projections.svg": svg.encode(),
        "result.json": (json.dumps(result, indent=2) + "\n").encode(),
        "report-generation.json": report_generation_bytes, "profile.json": profile_bytes}
    output.mkdir(parents=True, exist_ok=False)
    for filename, content in files.items():
        (output / filename).write_bytes(content)
    checksums = "".join(f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files))
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-generation-evidence", type=Path)
    parser.add_argument("--limiter-profile", type=Path)
    parser.add_argument("--repetitions", type=int, default=9)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 1000:
        parser.error("--repetitions must be in 1..1000")
    if args.result and args.executable:
        parser.error("choose either an executable or --result")
    if args.result:
        result = json.loads(args.result.read_text(encoding="utf-8"))
    elif args.executable:
        completed = subprocess.run([str(args.executable), "--measure", str(args.repetitions)],
            check=True, capture_output=True, text=True)
        result = json.loads(completed.stdout)
    else:
        parser.error("provide an executable or --result")
    verify(result)
    if args.output:
        if not args.report_generation_evidence or not args.limiter_profile:
            parser.error("--output requires --report-generation-evidence and --limiter-profile")
        report_generation = json.loads(args.report_generation_evidence.read_text(encoding="utf-8"))
        profile = json.loads(args.limiter_profile.read_text(encoding="utf-8"))
        write_report(result, args.output, report_generation, profile)
    else:
        print(json.dumps({"scenario_id": result["scenario_id"], "plan_count": PLAN_COUNT,
            "maximum_reward": result["objective_value"],
            "maximizing_plan_count": len(result["maximizing_plan_indices"]),
            "terminated_before_horizon_count": result["enumeration"]["terminated_before_horizon_count"],
            "terminated_on_final_step_count": result["enumeration"]["terminated_plan_count"] - result["enumeration"]["terminated_before_horizon_count"],
            "transition_count": result["enumeration"]["transition_count"],
            "verified_plans": len(result["plans"])}))


if __name__ == "__main__":
    main()

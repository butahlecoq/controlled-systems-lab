#!/usr/bin/env python3
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
try:
    import resource
except ImportError:  # pragma: no cover - Windows Python
    resource = None
import shutil
import statistics
import subprocess
import sys
import time

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "1b26ba326fbbce4c31a29f211b97dd3981a227e9"
AGENT_BLOB = "d426400cab0b0a18d9819acea84d082991899a06"
SOURCE_URL = ("https://github.com/imm-rl-lab/optimal_control/tree/"
              f"{SOURCE_COMMIT}/Environments/UnlimitedBolzaProblem")
SCALE = 20_000
OUTER_DT = 0.1
INNER_DT = 0.01
HORIZON = 10
ACTIONS = (-2, -1, 0, 1, 2)
PLAN_COUNT = len(ACTIONS) ** HORIZON
TOLERANCE = 2e-10
FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
         "phase-plane.svg", "result.json", "SHA256SUMS")


def close(actual: float, expected: float, field: str, tolerance: float = TOLERANCE) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(f"{field}: {actual!r} != {expected!r}")


def f(t: float) -> float:
    q = t / math.sqrt(2.0)
    return (math.sin(q) * math.cosh(q) - math.cos(q) * math.sinh(q)) / math.sqrt(2.0)


def df(t: float) -> float:
    q = t / math.sqrt(2.0)
    return math.sin(q) * math.sinh(q)


def d2f(t: float) -> float:
    q = t / math.sqrt(2.0)
    return (math.sin(q) * math.cosh(q) + math.cos(q) * math.sinh(q)) / math.sqrt(2.0)


def d3f(t: float) -> float:
    q = t / math.sqrt(2.0)
    return math.cos(q) * math.cosh(q)


def analytic_policy(initial_position: float, initial_velocity: float) -> tuple[float, float]:
    a, b, c, d = d3f(1.0), f(1.0), -d2f(1.0), d3f(1.0)
    rhs1 = -0.5 - d2f(1.0) * initial_position - df(1.0) * initial_velocity
    rhs2 = -0.5 + df(1.0) * initial_position + f(1.0) * initial_velocity
    determinant = a * d - b * c
    if abs(determinant) < 1e-14:
        raise ValueError("analytic boundary system is singular")
    return ((rhs1 * d - b * rhs2) / determinant,
            (a * rhs2 - rhs1 * c) / determinant)


def analytic_control(policy: tuple[float, float], initial_position: float,
                     initial_velocity: float, t: float) -> float:
    eta1, eta2 = policy
    return (-df(t) * initial_position - f(t) * initial_velocity
            - d2f(t) * eta1 + d3f(t) * eta2)


def rk4_reference(initial_position: float, initial_velocity: float,
                  policy: tuple[float, float], steps: int = 1000) -> dict:
    h = 1.0 / steps
    x, v, running = initial_position, initial_velocity, 0.0

    def derivative(t: float, state: tuple[float, float, float]) -> tuple[float, float, float]:
        sx, sv, _ = state
        u = analytic_control(policy, initial_position, initial_velocity, t)
        return sv, u, sx * sx + u * u

    trajectory = [{"time_seconds": 0.0, "position": x, "velocity": v,
                   "control": analytic_control(policy, initial_position, initial_velocity, 0.0)}]
    for index in range(steps):
        t = index * h
        state = (x, v, running)
        k1 = derivative(t, state)
        k2 = derivative(t + h / 2, tuple(state[j] + h * k1[j] / 2 for j in range(3)))
        k3 = derivative(t + h / 2, tuple(state[j] + h * k2[j] / 2 for j in range(3)))
        k4 = derivative(t + h, tuple(state[j] + h * k3[j] for j in range(3)))
        x, v, running = tuple(state[j] + h * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]) / 6
                              for j in range(3))
        if (index + 1) % (steps // 100) == 0:
            t_next = (index + 1) * h
            trajectory.append({"time_seconds": t_next, "position": x, "velocity": v,
                               "control": analytic_control(policy, initial_position,
                                                           initial_velocity, t_next)})
    return {"objective": running + x + v, "running_cost_integral": running,
            "terminal_state": [x, v], "trajectory": trajectory,
            "integration": f"independent RK4, {steps} uniform steps"}


def source_step(state: tuple[float, float], control: float) -> tuple[float, float]:
    x, v = state
    for _ in range(10):
        old_x, old_v = x, v
        x = old_x + INNER_DT * old_v
        v = old_v + INNER_DT * control
    return x, v


def sampled_replay(initial_position: float, initial_velocity: float,
                   policy: tuple[float, float]) -> dict:
    state = initial_position, initial_velocity
    running = 0.0
    trajectory = []
    for stage in range(HORIZON + 1):
        t = stage * OUTER_DT
        control = (analytic_control(policy, initial_position, initial_velocity, t)
                   if stage < HORIZON else 0.0)
        trajectory.append({"time_seconds": t, "position": state[0],
                           "velocity": state[1], "control": control})
        if stage < HORIZON:
            running += OUTER_DT * (state[0] ** 2 + control ** 2)
            state = source_step(state, control)
    return {"objective": running + state[0] + state[1], "running_cost_sum": running,
            "terminal_state": list(state), "trajectory": trajectory,
            "policy": "continuous analytic feedback sampled at each outer step and held over ten source Euler substeps"}


def exact_finite_catalogue_oracle(initial_position: float, initial_velocity: float) -> dict:
    # Integer ticks make the source's reduced ten-Euler-step map exact:
    # x' = x + .1 v + .0045 u, v' = v + .1 u.
    # The accumulated objective is an integer numerator over 10*SCALE^2.
    denominator = 10 * SCALE * SCALE
    initial = (round(initial_position * SCALE), round(initial_velocity * SCALE))
    layer: dict[tuple[int, int], tuple[int, int, tuple[int, ...]]] = {
        initial: (0, 1, ())
    }
    layer_sizes = [1]
    for _stage in range(HORIZON):
        next_layer: dict[tuple[int, int], tuple[int, int, tuple[int, ...]]] = {}
        for (x_tick, v_tick), (cost_numerator, path_count, path) in layer.items():
            for action in ACTIONS:
                next_state = (x_tick + v_tick // 10 + 90 * action,
                              v_tick + 2_000 * action)
                increment = x_tick * x_tick + action * action * SCALE * SCALE
                candidate_cost = cost_numerator + increment
                candidate_path = path + (action,)
                old = next_layer.get(next_state)
                if old is None or candidate_cost < old[0]:
                    next_layer[next_state] = (candidate_cost, path_count, candidate_path)
                elif candidate_cost == old[0]:
                    next_layer[next_state] = (old[0], old[1] + path_count,
                                              min(old[2], candidate_path))
        layer = next_layer
        layer_sizes.append(len(layer))

    best_numerator: int | None = None
    best_count = 0
    best_path: tuple[int, ...] | None = None
    best_state: tuple[int, int] | None = None
    for (x_tick, v_tick), (cost_numerator, count, path) in layer.items():
        objective_numerator = cost_numerator + 10 * SCALE * (x_tick + v_tick)
        if best_numerator is None or objective_numerator < best_numerator:
            best_numerator, best_count, best_path, best_state = objective_numerator, count, path, (x_tick, v_tick)
        elif objective_numerator == best_numerator:
            best_count += count
            if best_path is None or path < best_path:
                best_path, best_state = path, (x_tick, v_tick)
    assert best_numerator is not None and best_path is not None and best_state is not None
    return {"objective": best_numerator / denominator,
            "objective_numerator": best_numerator, "objective_denominator": denominator,
            "selected_controls": list(best_path),
            "terminal_state": [best_state[0] / SCALE, best_state[1] / SCALE],
            "optimal_plan_count": best_count, "complete_plan_count": PLAN_COUNT,
            "distinct_states_by_stage": layer_sizes,
            "oracle": "independent exact-integer dynamic programming by (position, velocity) state"}


def verify(result: dict) -> dict:
    if result.get("schema") != "csl.env717-unlimited-bolza-pilot/1":
        raise ValueError("report schema differs")
    if (result.get("source_repository_commit") != SOURCE_COMMIT or
            result.get("source_file_blob") != SOURCE_BLOB or
            result.get("optimal_agent_blob") != AGENT_BLOB):
        raise ValueError("pinned upstream source identity differs")
    if result.get("source_url") != SOURCE_URL:
        raise ValueError("source URL differs")

    provenance = result.get("provenance", {})
    for field, length in (("driver_sha256", 64), ("algorithm_source_sha256", 64),
                          ("source_commit", 40)):
        value = provenance.get(field)
        if (not isinstance(value, str) or len(value) != length or
                any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"provenance field is invalid: {field}")

    source_model = result["source_model"]
    if source_model["outer_step_seconds"] != OUTER_DT or source_model["inner_step_seconds"] != INNER_DT:
        raise ValueError("source step parameters differ")
    if source_model["inner_steps_per_outer_step"] != 10 or source_model["horizon_seconds"] != 1.0:
        raise ValueError("source integration horizon differs")
    pilot = result["pilot_adaptation"]
    initial_x = pilot["initial_position"]
    initial_v = pilot["initial_velocity"]
    if pilot["finite_control_catalogue"] != list(ACTIONS) or pilot["finite_horizon_steps"] != HORIZON:
        raise ValueError("finite pilot catalogue or horizon differs")
    if initial_x == 0.0 and initial_v == 0.0:
        raise ValueError("authored pilot initial state must differ from the upstream zero default")

    policy = analytic_policy(initial_x, initial_v)
    continuous = rk4_reference(initial_x, initial_v, policy)
    sampled = sampled_replay(initial_x, initial_v, policy)
    oracle = exact_finite_catalogue_oracle(initial_x, initial_v)
    saved_continuous = result["continuous_analytic_reference"]
    saved_sampled = result["sampled_analytic_feedback_replay"]
    saved_finite = result["finite_catalogue_optimum"]
    for field in ("objective", "running_cost_integral"):
        close(saved_continuous[field], continuous[field], f"continuous.{field}")
    for field in ("objective", "running_cost_sum"):
        close(saved_sampled[field], sampled[field], f"sampled.{field}")
    for actual, expected, field in zip(saved_continuous["terminal_state"],
                                       continuous["terminal_state"], ("x", "v")):
        close(actual, expected, f"continuous.terminal.{field}")
    for actual, expected, field in zip(saved_sampled["terminal_state"],
                                       sampled["terminal_state"], ("x", "v")):
        close(actual, expected, f"sampled.terminal.{field}")

    # Independent stationarity and transversality checks for the source's
    # closed-form feedback basis: u'' + x = 0, lambda_x(T)=2u'(T)=1,
    # lambda_v(T)=-2u(T)=1.
    close(analytic_control(policy, initial_x, initial_v, 1.0), -0.5,
          "terminal costate lambda_v")
    u_prime_terminal = (-d2f(1.0) * initial_x - df(1.0) * initial_v
                        - d3f(1.0) * policy[0] - f(1.0) * policy[1])
    close(2 * u_prime_terminal, 1.0, "terminal costate lambda_x")
    for row in continuous["trajectory"][::10]:
        t = row["time_seconds"]
        u_second = (-d3f(t) * initial_x - d2f(t) * initial_v
                    + f(t) * policy[0] - df(t) * policy[1])
        close(u_second + row["position"], 0.0, f"Euler-Lagrange residual at t={t}", 1e-8)

    close(saved_finite["objective"], oracle["objective"], "finite objective", 1e-11)
    close(saved_finite["running_cost_sum"] + sum(saved_finite["terminal_state"]),
          oracle["objective"], "finite objective decomposition", 1e-11)
    if saved_finite["selected_controls"] != oracle["selected_controls"]:
        raise ValueError("finite selected plan differs from independent exact-integer DP")
    if saved_finite["plan_count"] != PLAN_COUNT or oracle["complete_plan_count"] != PLAN_COUNT:
        raise ValueError("finite plan count differs")
    if saved_finite["tie_count"] != oracle["optimal_plan_count"]:
        raise ValueError("finite tie count differs from exact-integer DP")
    for actual, expected, field in zip(saved_finite["terminal_state"],
                                       oracle["terminal_state"], ("x", "v")):
        close(actual, expected, f"finite.terminal.{field}", 1e-11)
    if saved_finite["replayed_terminal_state"] != saved_finite["terminal_state"]:
        for actual, expected in zip(saved_finite["replayed_terminal_state"], saved_finite["terminal_state"]):
            close(actual, expected, "finite replay endpoint", 1e-11)
    measurement = result.get("runtime_measurement")
    if measurement is not None:
        if measurement.get("schema") != "csl.env717-runtime-measurement/1":
            raise ValueError("runtime measurement schema differs")
        durations = measurement.get("duration_ns", [])
        blocks = measurement.get("blocks", [])
        if (measurement.get("measured_blocks") != 4 or
                measurement.get("calls_per_block") != 7 or
                measurement.get("warmups_per_block") != 1 or
                measurement.get("successful_calls") != 28 or
                measurement.get("failed_calls") != 0 or
                measurement.get("all_calls_match_independent_finite_plan") is not True or
                len(durations) != 28 or len(blocks) != 4 or
                any(not isinstance(value, int) or value <= 0 for value in durations)):
            raise ValueError("runtime measurement call protocol is incomplete")
        if (measurement.get("minimum_ns") != min(durations) or
                measurement.get("maximum_ns") != max(durations) or
                measurement.get("median_ns") != statistics.median(durations)):
            raise ValueError("runtime measurement summary differs from raw samples")
        for index, block in enumerate(blocks, start=1):
            block_durations = block.get("durations_ns", [])
            if (block.get("block") != index or block.get("warmups") != 1 or
                    block.get("measured_calls") != 7 or block.get("successful_calls") != 7 or
                    block.get("failed_calls") != 0 or len(block_durations) != 7 or
                    any(not isinstance(value, int) or value <= 0 for value in block_durations)):
                raise ValueError(f"runtime measurement block {index} is incomplete")
        profile = measurement.get("limiter_profile", {})
        if profile.get("status") == "complete":
            if (profile.get("excluded_from_reported_samples") is not True or
                    profile.get("finite_catalogue_plan_count") != PLAN_COUNT or
                    profile.get("solver_elapsed_ns", 0) <= 0 or
                    profile.get("whole_process_cpu_percent", 0) <= 0):
                raise ValueError("excluded limiter profile is incomplete")
        elif profile.get("status") != "unavailable":
            raise ValueError("limiter profile has an unknown status")
    if len(saved_continuous["trajectory"]) != 101 or len(saved_sampled["trajectory"]) != 11:
        raise ValueError("trajectory sample count differs")
    if len(saved_finite["trajectory"]) != 11:
        raise ValueError("finite trajectory sample count differs")
    elapsed = saved_finite.get("elapsed_ns")
    if not isinstance(elapsed, int) or elapsed <= 0:
        raise ValueError("finite solver timing is missing or nonpositive")
    return {"continuous": continuous, "sampled": sampled, "finite_oracle": oracle,
            "analytic_policy": policy}


def run_driver(executable: Path) -> dict:
    completed = subprocess.run([str(executable)], capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"native report driver failed ({completed.returncode}): {completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("native report driver output is not JSON") from error


def profile_trial(executable: Path) -> dict:
    profiler_tools = {name: shutil.which(name) for name in ("perf", "strace", "pidstat")}
    if resource is None:
        return {"status": "unavailable", "reason": "child-process resource accounting is unavailable",
                "other_profiler_tools": profiler_tools}
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter_ns()
    result = run_driver(executable)
    wall_ns = time.perf_counter_ns() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    summary = result["finite_catalogue_optimum"]
    if summary.get("plan_count") != PLAN_COUNT or not isinstance(summary.get("elapsed_ns"), int):
        raise ValueError("excluded profile run did not complete the finite catalogue")
    user_seconds = after.ru_utime - before.ru_utime
    system_seconds = after.ru_stime - before.ru_stime
    cpu_percent = 100.0 * (user_seconds + system_seconds) / (wall_ns / 1e9)
    cpu_to_solver_ratio = ((user_seconds + system_seconds) / (summary["elapsed_ns"] / 1e9)
                           if summary["elapsed_ns"] > 0 else None)
    return {"status": "complete", "command": "Python subprocess wall clock plus resource.getrusage(RUSAGE_CHILDREN)",
            "excluded_from_reported_samples": True,
            "finite_catalogue_plan_count": summary["plan_count"],
            "solver_elapsed_ns": summary["elapsed_ns"],
            "whole_process_wall_ns": wall_ns,
            "user_cpu_seconds": user_seconds, "system_cpu_seconds": system_seconds,
            "whole_process_cpu_percent": cpu_percent,
            "maximum_resident_set_size": after.ru_maxrss,
            "maximum_resident_set_size_unit": "KiB" if platform.system() == "Linux" else "platform-specific resource units",
            "process_cpu_to_solver_time_ratio": cpu_to_solver_ratio,
            "other_profiler_tools": profiler_tools,
            "interpretation": "The timed solver phase is exhaustive CPU enumeration; single-process CPU use and process CPU time are the available limiter evidence. perf, strace and pidstat availability is recorded separately."}


def capture(executable: Path, oracle_result: dict, blocks_count: int = 4,
            repetitions: int = 7) -> tuple[dict, dict]:
    def load_average() -> list[float] | None:
        try:
            return list(os.getloadavg())
        except (AttributeError, OSError):
            return None

    blocks = []
    limiter_profile = profile_trial(executable)
    for block_id in range(blocks_count):
        start_ns = time.time_ns()
        before = load_average()
        warm = run_driver(executable)
        warm_summary = warm.get("finite_catalogue_optimum", {})
        if (warm.get("schema") != "csl.env717-unlimited-bolza-pilot/1" or
                warm_summary.get("plan_count") != PLAN_COUNT or
                warm_summary.get("selected_controls") != oracle_result["finite_catalogue_optimum"]["selected_controls"] or
                not isinstance(warm_summary.get("elapsed_ns"), int) or warm_summary["elapsed_ns"] <= 0):
            raise ValueError("warmup selected a different finite plan")
        samples = []
        failed = 0
        for _ in range(repetitions):
            try:
                measured = run_driver(executable)
                summary = measured["finite_catalogue_optimum"]
                if (summary["plan_count"] != PLAN_COUNT or
                        summary["selected_controls"] != oracle_result["finite_catalogue_optimum"]["selected_controls"] or
                        not math.isclose(summary["objective"],
                                         oracle_result["finite_catalogue_optimum"]["objective"],
                                         rel_tol=0.0, abs_tol=1e-11)):
                    raise ValueError("measured call did not complete the verified finite catalogue solve")
                samples.append(summary["elapsed_ns"])
            except Exception:
                failed += 1
                raise
        after = load_average()
        blocks.append({"block": block_id + 1, "started_unix_ns": start_ns,
                       "warmups": 1, "measured_calls": repetitions,
                       "successful_calls": len(samples), "failed_calls": failed,
                       "durations_ns": samples, "median_ns": statistics.median(samples),
                       "minimum_ns": min(samples), "maximum_ns": max(samples),
                       "load_average_before": before, "load_average_after": after})
    all_samples = [value for block in blocks for value in block["durations_ns"]]
    measurement = {"schema": "csl.env717-runtime-measurement/1",
                  "scope": "one native exhaustive finite-catalogue solve over 5^10=9,765,625 plans; excludes analytic reference, Python oracle, JSON serialization, report rendering and build",
                  "warmups_per_block": 1, "measured_blocks": blocks_count,
                  "calls_per_block": repetitions, "successful_calls": len(all_samples),
                  "failed_calls": sum(block["failed_calls"] for block in blocks),
                  "parallelism": "single executable process; sequential calls; one worker thread",
                  "all_calls_match_independent_finite_plan": True,
                  "duration_ns": all_samples,
                  "median_ns": statistics.median(all_samples),
                  "minimum_ns": min(all_samples), "maximum_ns": max(all_samples),
                  "blocks": blocks,
                  "limitation": "single implementation descriptive runtime only; no competing algorithm, end-to-end user latency comparison, or performance winner",
                  "limiter_profile": limiter_profile}
    environment = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
                   "platform": platform.platform(), "python": sys.version,
                   "logical_cpu_count": os.cpu_count(), "load_average": load_average(),
                   "executable": str(executable.resolve())}
    return measurement, environment


def _points(trajectory: list[dict], bounds: tuple[float, float, float, float],
            plot: tuple[float, float, float, float]) -> str:
    xmin, xmax, ymin, ymax = bounds
    left, top, width, height = plot
    result = []
    for item in trajectory:
        px = left + (item["position"] - xmin) / (xmax - xmin) * width
        py = top + height - (item["velocity"] - ymin) / (ymax - ymin) * height
        result.append(f"{px:.2f},{py:.2f}")
    return " ".join(result)


def make_svg(result: dict) -> str:
    series = [
        ("continuous analytic reference", result["continuous_analytic_reference"]["trajectory"], "#1976d2", 3.0),
        ("sampled feedback, source Euler replay", result["sampled_analytic_feedback_replay"]["trajectory"], "#ed7d31", 2.6),
        ("finite-catalogue optimum", result["finite_catalogue_optimum"]["trajectory"], "#2e8b57", 2.6),
    ]
    points = [(row["position"], row["velocity"])
              for _, trajectory, _, _ in series for row in trajectory]
    xmin, xmax = min(x for x, _ in points), max(x for x, _ in points)
    ymin, ymax = min(y for _, y in points), max(y for _, y in points)
    padx, pady = max(0.08, (xmax - xmin) * 0.08), max(0.08, (ymax - ymin) * 0.08)
    bounds = (xmin - padx, xmax + padx, ymin - pady, ymax + pady)
    plot = (100.0, 100.0, 760.0, 460.0)
    xmin, xmax, ymin, ymax = bounds
    left, top, width, height = plot
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700" role="img" aria-labelledby="title desc">',
        '<title id="title">Unlimited Bolza phase-plane trajectories</title>',
        '<desc id="desc">Position versus velocity for the continuous analytic reference, its sampled source-step replay, and the best finite-action plan.</desc>',
        '<rect width="1000" height="700" fill="#101820"/>',
        '<text x="500" y="42" text-anchor="middle" fill="#f3f7f9" font-family="sans-serif" font-size="22">UnlimitedBolzaProblem: position–velocity phase plane</text>',
    ]
    for tick in range(6):
        xvalue = xmin + (xmax - xmin) * tick / 5
        xpixel = left + width * tick / 5
        yvalue = ymin + (ymax - ymin) * tick / 5
        ypixel = top + height - height * tick / 5
        svg.append(f'<line x1="{xpixel:.2f}" y1="{top}" x2="{xpixel:.2f}" y2="{top + height}" stroke="#344653"/>')
        svg.append(f'<text x="{xpixel:.2f}" y="{top + height + 24}" text-anchor="middle" fill="#b9c6ce" font-family="sans-serif" font-size="12">{xvalue:.3f}</text>')
        svg.append(f'<line x1="{left}" y1="{ypixel:.2f}" x2="{left + width}" y2="{ypixel:.2f}" stroke="#344653"/>')
        svg.append(f'<text x="{left - 12}" y="{ypixel + 4:.2f}" text-anchor="end" fill="#b9c6ce" font-family="sans-serif" font-size="12">{yvalue:.3f}</text>')
    svg.extend([
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#91a2ad" stroke-width="1.5"/>',
        f'<text x="{left + width / 2}" y="{top + height + 54}" text-anchor="middle" fill="#e8eef2" font-family="sans-serif" font-size="16">position x</text>',
        f'<text x="26" y="{top + height / 2}" transform="rotate(-90 26 {top + height / 2})" text-anchor="middle" fill="#e8eef2" font-family="sans-serif" font-size="16">velocity v</text>',
    ])
    for label, trajectory, color, stroke in series:
        svg.append(f'<polyline points="{_points(trajectory, bounds, plot)}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linejoin="round" stroke-linecap="round"/>')
        first = trajectory[0]
        last = trajectory[-1]
        for row, radius in ((first, 4), (last, 5)):
            px = left + (row["position"] - xmin) / (xmax - xmin) * width
            py = top + height - (row["velocity"] - ymin) / (ymax - ymin) * height
            svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{radius}" fill="{color}" stroke="#101820" stroke-width="1.5"/>')
    legend_y = 620
    for index, (label, _, color, stroke) in enumerate(series):
        x = 86 + index * 290
        svg.append(f'<line x1="{x}" y1="{legend_y}" x2="{x + 34}" y2="{legend_y}" stroke="{color}" stroke-width="{stroke}"/>')
        svg.append(f'<text x="{x + 44}" y="{legend_y + 5}" fill="#d7e0e5" font-family="sans-serif" font-size="12">{html.escape(label)}</text>')
    svg.extend([
        '<text x="500" y="675" text-anchor="middle" fill="#9badb8" font-family="sans-serif" font-size="12">Authored pilot initial state (x,v)=(1,0); finite action catalogue {-2,-1,0,1,2}; horizon 1 s</text>',
        '</svg>',
    ])
    return "\n".join(svg)


def make_readme(result: dict, measurement: dict) -> str:
    continuous = result["continuous_analytic_reference"]
    sampled = result["sampled_analytic_feedback_replay"]
    finite = result["finite_catalogue_optimum"]
    profile = measurement["limiter_profile"]
    if profile["status"] == "complete":
        profile_text = (f"The excluded child-process profile recorded {profile['whole_process_cpu_percent']:.1f}% CPU use, "
                        f"{profile['maximum_resident_set_size']} {profile['maximum_resident_set_size_unit']} maximum RSS, "
                        "and no available perf/strace/pidstat profiler; details are in `capture.json`.")
    else:
        profile_text = "Child-process CPU profiling was unavailable; this is recorded in `capture.json`. No limiter-based performance conclusion is claimed."
    return f"""# Unlimited Bolza Problem: analytic reference and finite catalogue

This report re-expresses the upstream double-integrator equations and analytic feedback basis. It does not copy upstream source code. The pinned source has no declared license. The main differential-game reachability example remains [TwoPointsOnParallelLines](https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-33ebdad360671940fb54/index.html).

## Model and scope

The source state is `[time, position, velocity]` with `time'=1`, `position'=velocity`, and `velocity'=control`. Each 0.1-second outer step holds one action over ten explicit Euler substeps of 0.01 seconds. The source control is unbounded. Its reward is the negative of `0.1*(position^2 + control^2)` evaluated at the pre-step state, plus terminal reward `-position(T)-velocity(T)` when time reaches one second. The report minimizes the corresponding positive cost.

The upstream initial physical state defaults to `(0,0)`, which makes a poor visual example. This pilot authors `(position, velocity)=(1,0)`. The finite-action comparison restricts actions to `{-2,-1,0,1,2}` over ten stages; it is an exact optimum only for this 5^10 finite catalogue and the source Euler map. It does not solve the original unbounded-control problem.

## Results

The re-expressed continuous analytic feedback reference has objective `{continuous['objective']:.12f}` and terminal state `({continuous['terminal_state'][0]:.10f}, {continuous['terminal_state'][1]:.10f})`. The policy is independently checked against the Euler–Lagrange residual and terminal costate conditions, and its objective is integrated with RK4.

Sampling that policy once per outer step and holding it over the ten source Euler substeps gives objective `{sampled['objective']:.12f}`. Exhaustive enumeration of all `{finite['plan_count']:,}` finite action sequences gives catalogue minimum `{finite['objective']:.12f}`, controls `{finite['selected_controls']}`, and terminal state `({finite['terminal_state'][0]:.10f}, {finite['terminal_state'][1]:.10f})`. A separate exact-integer dynamic program over the finite state graph verifies the catalogue result.

The phase-plane plot shows position `x` against velocity `v`; the three curves use different solution tracks and are not an algorithm ranking on a matched guarantee. The retained runtime is the native exhaustive finite-catalogue solver call only: median `{measurement['median_ns']:,} ns` across `{measurement['successful_calls']}` sequential calls (range `{measurement['minimum_ns']:,}–{measurement['maximum_ns']:,} ns`). {profile_text} It is descriptive for this one implementation; no competing solver, end-to-end latency, or performance winner is claimed.

## Provenance and reproduction

- Upstream environment: [{SOURCE_URL}]({SOURCE_URL})
- Environment source blob: `{SOURCE_BLOB}`; analytic-agent blob: `{AGENT_BLOB}`.
- Driver, algorithm-source fingerprint and repository commit: `result.json`.
- Raw runtime blocks and host load data: `capture.json`.
- Figure data and checksums: `figure-data.json`, `SHA256SUMS`.

Build and run the native driver:

```sh
cmake -S . -B build/env717 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCSL_DEPENDENCY_PROBES=OFF -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --target csl_env717_unlimited_bolza --parallel 4
python3 scripts/reports/env717/check_unlimited_bolza.py build/env717/csl_env717_unlimited_bolza --output reports/algorithm-results/env717-unlimited-bolza-pilot-v1
```

The report is supplementary single-controller coverage for #717. It is not an RL training reproduction, a continuous unbounded-control optimum from CSL, or a comparison of reachability-set representations.
"""


def make_html(result: dict, svg_name: str = "phase-plane.svg") -> str:
    values = (result["continuous_analytic_reference"],
              result["sampled_analytic_feedback_replay"], result["finite_catalogue_optimum"])
    rows = "\n".join(f"<tr><th>{label}</th><td>{value['objective']:.12f}</td><td>({value['terminal_state'][0]:.8f}, {value['terminal_state'][1]:.8f})</td></tr>"
                     for label, value in zip(("Continuous analytic reference", "Sampled source Euler replay", "Finite catalogue optimum"), values))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unlimited Bolza phase-plane example</title>
<style>body{{max-width:1100px;margin:2rem auto;padding:0 1rem;background:#101820;color:#e8eef2;font:16px/1.5 system-ui,sans-serif}}a{{color:#8ecbff}}img{{width:100%;height:auto;border:1px solid #40505a}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.55rem;border-bottom:1px solid #40505a;text-align:left}}code{{overflow-wrap:anywhere}}</style></head>
<body><main><h1>Unlimited Bolza Problem</h1><p>Source-attributed double-integrator example with an analytic feedback reference, a source-step replay, and an exact finite-catalogue search.</p>
<figure><img src="{svg_name}" alt="Position-velocity phase plane with continuous, sampled, and finite-catalogue trajectories"><figcaption>Position versus velocity; point markers show initial and terminal states.</figcaption></figure>
<table><thead><tr><th>Track</th><th>Objective</th><th>Terminal (x, v)</th></tr></thead><tbody>{rows}</tbody></table>
<p>The finite result covers only the authored catalogue {{-2,-1,0,1,2}} over ten stages. It does not solve the original unbounded-control problem. Read the <a href="README.md">scope and reproduction notes</a>, inspect the <a href="result.json">raw result</a> and <a href="figure-data.json">figure data</a>, or open the <a href="{svg_name}">standalone SVG</a>.</p>
<p>Upstream source identity: <a href="{SOURCE_URL}">pinned environment</a> and analytic-agent file. This is supplementary to the <a href="https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-33ebdad360671940fb54/index.html">TwoPointsOnParallelLines differential-game reachability example</a>.</p></main></body></html>
"""


def create_bundle(executable: Path, output: Path) -> None:
    result = run_driver(executable)
    verify(result)
    oracle_result = result
    measurement, environment = capture(executable, oracle_result)
    result["runtime_measurement"] = measurement
    verify(result)
    figure_data = {"schema": "csl.env717-figure-data/1", "coordinates": ["position", "velocity"],
                   "tracks": {"continuous_analytic_reference": result["continuous_analytic_reference"]["trajectory"],
                              "sampled_analytic_feedback_replay": result["sampled_analytic_feedback_replay"]["trajectory"],
                              "finite_catalogue_optimum": result["finite_catalogue_optimum"]["trajectory"]}}
    output.mkdir(parents=True, exist_ok=False)
    payloads = {
        "result.json": (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
        "capture.json": (json.dumps({"measurement": measurement, "environment": environment}, indent=2, sort_keys=True) + "\n").encode(),
        "figure-data.json": (json.dumps(figure_data, indent=2, sort_keys=True) + "\n").encode(),
        "phase-plane.svg": (make_svg(result) + "\n").encode(),
        "index.html": make_html(result).encode(),
        "README.md": make_readme(result, measurement).encode(),
    }
    for name, content in payloads.items():
        (output / name).write_bytes(content)
    sums = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n"
                   for name, content in sorted(payloads.items()))
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")


def verify_bundle(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("report bundle must be a real directory")
    entries = tuple(directory.iterdir())
    if {entry.name for entry in entries} != set(FILES):
        raise ValueError("report bundle inventory differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("report bundle entries must be regular files")
    files = {name: (directory / name).read_bytes() for name in FILES}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate report checksum entry")
        checksums[name] = digest
    expected = {name: hashlib.sha256(data).hexdigest()
                for name, data in files.items() if name != "SHA256SUMS"}
    if checksums != expected:
        raise ValueError("report checksum inventory differs")
    result = json.loads(files["result.json"])
    verify(result)
    svg = make_svg(result) + "\n"
    if files["phase-plane.svg"] != svg.encode():
        raise ValueError("saved SVG differs from regenerated figure")
    if files["index.html"] != make_html(result).encode():
        raise ValueError("saved HTML differs from regenerated page")
    figure_data = {"schema": "csl.env717-figure-data/1", "coordinates": ["position", "velocity"],
                   "tracks": {"continuous_analytic_reference": result["continuous_analytic_reference"]["trajectory"],
                              "sampled_analytic_feedback_replay": result["sampled_analytic_feedback_replay"]["trajectory"],
                              "finite_catalogue_optimum": result["finite_catalogue_optimum"]["trajectory"]}}
    if files["figure-data.json"] != (json.dumps(figure_data, indent=2, sort_keys=True) + "\n").encode():
        raise ValueError("saved figure data differs from result trajectories")
    measurement = result["runtime_measurement"]
    if files["README.md"] != make_readme(result, measurement).encode():
        raise ValueError("saved README differs from result data")
    capture_doc = json.loads(files["capture.json"])
    if capture_doc.get("measurement") != measurement:
        raise ValueError("capture record differs from result measurement")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and capture the UnlimitedBolza report")
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-bundle", type=Path)
    args = parser.parse_args()
    if args.verify_bundle:
        verify_bundle(args.verify_bundle)
        print(f"verified {args.verify_bundle}")
        return 0
    if args.output:
        create_bundle(args.executable.resolve(), args.output)
        verify_bundle(args.output)
        print(f"captured and verified {args.output}")
    else:
        result = run_driver(args.executable.resolve())
        oracle = verify(result)
        print(f"verified {PLAN_COUNT:,} finite plans; DP states by stage: {oracle['finite_oracle']['distinct_states_by_stage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

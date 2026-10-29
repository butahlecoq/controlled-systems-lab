#!/usr/bin/env python3
"""Independently replay and verify the finite MPC-09 output-feedback pilot."""

from __future__ import annotations

import functools
import itertools
import json
import math
import subprocess
import sys

HORIZON = 3
DT = 0.2
INNER_STEPS = 20
ACTIONS = (-3.0, 0.0, 3.0)
DISTURBANCES = ACTIONS
ERRORS = (-0.2, 0.2)
INITIAL = ((0.0, 0.0, -0.2, 0.0), (0.0, 0.0, 0.2, 0.0))
RESOLUTION = 0.1
RESIDUAL_BOUND = 0.25
CAPTURE_RADIUS = 1.0
TOL = 2e-8


def derivative(x: tuple[float, ...], u: float, v: float) -> tuple[float, ...]:
    return (x[1], -10 * x[1] + 10 * u, x[3], v)


def rk4(x: tuple[float, ...], u: float, v: float) -> tuple[float, ...]:
    h = DT / INNER_STEPS
    for _ in range(INNER_STEPS):
        k1 = derivative(x, u, v)
        k2 = derivative(tuple(a + h * b / 2 for a, b in zip(x, k1)), u, v)
        k3 = derivative(tuple(a + h * b / 2 for a, b in zip(x, k2)), u, v)
        k4 = derivative(tuple(a + h * b for a, b in zip(x, k3)), u, v)
        x = tuple(a + h * (b + 2 * c + 2 * d + e) / 6
                  for a, b, c, d, e in zip(x, k1, k2, k3, k4))
    return x


def sensor(x: tuple[float, ...], error: float) -> float:
    scaled = (x[0] - x[2] + error) / RESOLUTION
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    return rounded * RESOLUTION


def close(a: float, b: float, tolerance: float = TOL) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def history_key(history: tuple[float, ...]) -> tuple[int, ...]:
    return tuple(round(y / RESOLUTION) for y in history)


@functools.lru_cache(maxsize=None)
def candidate_rows(history: tuple[float, ...], used: tuple[float, ...]):
    result = []
    for initial_id, initial in enumerate(INITIAL):
        for v_ids in itertools.product(range(len(DISTURBANCES)), repeat=len(used)):
            x = initial
            states = [x]
            for u, v_id in zip(used, v_ids):
                x = rk4(x, u, DISTURBANCES[v_id])
                states.append(x)
            residuals = tuple(y - (x[0] - x[2]) for y, x in zip(history, states))
            if all(abs(r) <= RESIDUAL_BOUND + 1e-10 for r in residuals):
                result.append({"state": states[-1], "states": states,
                               "initial_id": initial_id, "v_ids": v_ids,
                               "cost": sum(r * r for r in residuals)})
    return result


@functools.lru_cache(maxsize=None)
def estimate(history: tuple[float, ...], used: tuple[float, ...]):
    candidates = candidate_rows(history, used)
    if not candidates:
        raise ValueError("no MHE candidate is consistent with a listed row")
    best = candidates[0]
    for candidate in candidates[1:]:
        delta = candidate["cost"] - best["cost"]
        if abs(delta) > 1e-12:
            if delta < 0:
                best = candidate
        elif (candidate["initial_id"], candidate["v_ids"]) < (
                best["initial_id"], best["v_ids"]):
            best = candidate
    return best["state"], candidates


@functools.lru_cache(maxsize=None)
def posterior(history: tuple[float, ...], used: tuple[float, ...]):
    current = []
    for candidate in candidate_rows(history, used):
        if all(any(close(sensor(state, error), y, 1e-12)
                   for error in ERRORS)
               for state, y in zip(candidate["states"], history)):
            if not any(all(close(a, b, 1e-10) for a, b in zip(candidate["state"], known))
                       for known in current):
                current.append(candidate["state"])
    return tuple(sorted(current))


@functools.lru_cache(maxsize=None)
def plan_value(current: tuple[tuple[float, ...], ...], controls: tuple[float, ...]):
    worst = 0.0
    for disturbance_path in itertools.product(DISTURBANCES, repeat=len(controls)):
        for initial in current:
            x = initial
            for u, v in zip(controls, disturbance_path):
                x = rk4(x, u, v)
            worst = max(worst, abs(x[0] - x[2]))
    return worst


@functools.lru_cache(maxsize=None)
def first_action(history: tuple[float, ...], used: tuple[float, ...], robust: bool):
    if robust:
        current = posterior(history, used)
    else:
        current, _ = estimate(history, used)
        current = (current,)
    remaining = HORIZON - len(used)
    plans = itertools.product(ACTIONS, repeat=remaining)
    best_plan = None
    best_value = math.inf
    for plan in plans:
        value = plan_value(tuple(current), tuple(plan))
        if value < best_value - 1e-10:
            best_value, best_plan = value, plan
    if best_plan is None:
        raise ValueError("empty action-plan catalogue")
    return best_plan[0]


def scenario_rows():
    for initial_id, v_path, error_path in itertools.product(
            range(len(INITIAL)), itertools.product(DISTURBANCES, repeat=HORIZON),
            itertools.product(ERRORS, repeat=HORIZON + 1)):
        yield initial_id, v_path, error_path


@functools.lru_cache(maxsize=None)
def replay_oracle(stage: int, belief: tuple[tuple[float, ...], ...]):
    if stage == HORIZON:
        return max(abs(x[0] - x[2]) for x in belief)
    best = math.inf
    for u in ACTIONS:
        branches: dict[float, set[tuple[float, ...]]] = {}
        for x in belief:
            for v in DISTURBANCES:
                successor = rk4(x, u, v)
                for error in ERRORS:
                    y = sensor(successor, error)
                    branches.setdefault(y, set()).add(tuple(round(z, 12) for z in successor))
        worst = max(replay_oracle(stage + 1, tuple(sorted(states)))
                    for states in branches.values())
        best = min(best, worst)
    return best


def causal_reference():
    branches: dict[float, set[tuple[float, ...]]] = {}
    for x in INITIAL:
        for error in ERRORS:
            branches.setdefault(sensor(x, error), set()).add(tuple(round(z, 12) for z in x))
    value = max(replay_oracle(0, tuple(sorted(states)))
                for states in branches.values())
    first_actions = []
    for states in branches.values():
        belief = tuple(sorted(states))
        branch_values = []
        for u in ACTIONS:
            children: dict[float, set[tuple[float, ...]]] = {}
            for x in belief:
                for v in DISTURBANCES:
                    successor = rk4(x, u, v)
                    for error in ERRORS:
                        children.setdefault(sensor(successor, error), set()).add(
                            tuple(round(z, 12) for z in successor))
            branch_values.append(max(replay_oracle(1, tuple(sorted(child)))
                                     for child in children.values()))
        minimum = min(branch_values)
        first_actions.extend(ACTIONS[i] for i, value_i in enumerate(branch_values)
                             if close(value_i, minimum, 1e-10))
    return {"worst_terminal_gap": value,
            "initial_observation_count": len(branches),
            "optimal_first_actions": sorted(set(first_actions)),
            "scope": "complete finite observation-history game on the listed initial, v, and sensor-error catalogues"}


def verify(actual: dict) -> dict:
    if actual.get("schema") != "csl.mpc09-two-particle-output-feedback/1":
        raise ValueError("result schema differs")
    source = actual.get("source", {})
    if (source.get("repository_commit") != "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8" or
            source.get("file_blob") != "7e7d326f8ff81f7dacc05ac72848eeaac6a03021" or
            source.get("license") != "Apache-2.0"):
        raise ValueError("source identity or license differs")
    adaptation = actual.get("adaptation", {})
    if (adaptation.get("initial_states") != [list(x) for x in INITIAL] or
            adaptation.get("control_catalogue") != list(ACTIONS) or
            adaptation.get("disturbance_catalogue") != list(DISTURBANCES) or
            adaptation.get("measurement_error_catalogue") != list(ERRORS) or
            not close(adaptation.get("sensor_resolution", math.nan), RESOLUTION) or
            not close(adaptation.get("mhe_residual_bound", math.nan), RESIDUAL_BOUND)):
        raise ValueError("controller result differs from the declared finite scenario")
    arms = actual.get("controllers", [])
    if [arm.get("label") for arm in arms] != [
            "certainty_equivalent_receding", "set_based_robust_receding"]:
        raise ValueError("controller labels or order differ")
    expected_rows = 2 * len(DISTURBANCES) ** HORIZON * len(ERRORS) ** (HORIZON + 1)
    histories_by_arm = [dict(), dict()]
    for arm_id, arm in enumerate(arms):
        if len(arm.get("runs", [])) != expected_rows:
            raise ValueError("the result omits an authored row")
        worst = 0.0
        violations = 0
        for expected_id, ((initial_id, v_path, error_path), run) in enumerate(
                zip(scenario_rows(), arm["runs"])):
            if run.get("row_id") != expected_id or run.get("initial_index") != initial_id:
                raise ValueError("row enumeration differs")
            if tuple(run.get("disturbances", ())) != tuple(v_path):
                raise ValueError("disturbance sequence differs")
            if tuple(run.get("measurement_errors", ())) != tuple(error_path):
                raise ValueError("measurement-error sequence differs")
            x = INITIAL[initial_id]
            history, used = [], []
            trace = run.get("trace", [])
            if len(trace) != HORIZON + 1:
                raise ValueError("trajectory length differs")
            for stage, point in enumerate(trace):
                if point.get("stage") != stage:
                    raise ValueError("stage ordering differs")
                y = sensor(x, error_path[stage])
                if not all(close(a, b) for a, b in zip(point.get("state", ()), x)):
                    raise ValueError("state replay differs from the source RK4 step")
                if not close(point.get("observation", math.nan), y):
                    raise ValueError("sensor replay differs")
                history.append(y)
                if stage < HORIZON:
                    is_robust = arm_id == 1
                    expected_u = first_action(tuple(history), tuple(used), is_robust)
                    if not close(point.get("control", math.nan), expected_u):
                        raise ValueError("reported controller action differs from independent fixed-plan minimax")
                    key = history_key(tuple(history))
                    prior = histories_by_arm[arm_id].setdefault(key, expected_u)
                    if not close(prior, expected_u):
                        raise ValueError("identical observation histories select different actions")
                    if not close(point.get("control", math.nan), expected_u):
                        raise ValueError("saved action differs from the independently verified action")
                    estimate_state, estimate_candidates = estimate(tuple(history), tuple(used))
                    if not all(close(a, b) for a, b in zip(point.get("estimate", ()), estimate_state)):
                        raise ValueError("saved MHE state differs from independent full-history least squares")
                    expected_mhe = min(c["cost"] for c in estimate_candidates)
                    if not close(point.get("mhe_residual_cost", math.nan), expected_mhe):
                        raise ValueError("saved MHE residual objective differs")
                    posterior_set = posterior(tuple(history), tuple(used))
                    if point.get("posterior_size") != len(posterior_set):
                        raise ValueError("saved posterior size differs from independent history filtering")
                    saved_posterior = point.get("posterior_states", [])
                    if len(saved_posterior) != len(posterior_set) or any(
                            not all(close(a, b, 1e-10) for a, b in zip(saved, expected))
                            for saved, expected in zip(saved_posterior, posterior_set)):
                        raise ValueError("saved information set differs from independent history filtering")
                    used.append(expected_u)
                    x = rk4(x, expected_u, v_path[stage])
            cost = abs(x[0] - x[2])
            if not close(run.get("terminal_gap", math.nan), cost):
                raise ValueError("terminal cost differs")
            if bool(run.get("terminal_capture")) != (cost <= CAPTURE_RADIUS + 1e-12):
                raise ValueError("terminal capture label differs")
            worst = max(worst, cost)
            violations += cost > CAPTURE_RADIUS + 1e-12
        if not close(arm.get("worst_terminal_gap", math.nan), worst):
            raise ValueError("worst-case objective differs")
        if arm.get("terminal_capture_violations") != violations:
            raise ValueError("capture-violation count differs")
        if arm.get("rows_evaluated") != expected_rows:
            raise ValueError("row count differs")
    timing = actual.get("observation_timing_checks", {})
    if timing.get("schema") != "csl.mpc09-observation-timing-check/1":
        raise ValueError("missed/delayed observation evidence is missing")
    controls = (0.0, 0.0)
    v_path = (-3.0, 3.0)
    noise_path = (-0.2, 0.2)
    truth0 = INITIAL[0]
    y0 = sensor(truth0, noise_path[0])
    truth1 = rk4(truth0, controls[0], v_path[0])
    y1 = sensor(truth1, noise_path[1])
    missed = candidate_rows((y0,), (controls[0],))
    missed_set = posterior((y0,), (controls[0],))
    delayed = candidate_rows((y0, y1), controls)
    delayed_set = posterior((y0, y1), controls)
    if (timing.get("decision_1", {}).get("sample_at_stage_1") != "missed" or
            timing["decision_1"].get("hidden_state_was_read") is not False or
            timing["decision_1"].get("state_hypothesis_count") != len(missed) or
            timing["decision_1"].get("posterior_state_count") != len(missed_set)):
        raise ValueError("missing observation changed state information or hypothesis counts")
    released = timing.get("released_samples_at_decision_2", [])
    if released != [{"state_stage": 0, "available_stage": 0, "value": y0},
                    {"state_stage": 1, "available_stage": 2, "value": y1}]:
        raise ValueError("delayed sample release timestamp differs")
    delay_estimate, delay_candidates = estimate((y0, y1), controls)
    if (not delayed or timing.get("decision_2", {}).get("delayed_stage_1_sample_released") is not True or
            timing["decision_2"].get("state_hypothesis_count") != len(delayed) or
            timing["decision_2"].get("posterior_state_count") != len(delayed_set) or
            any(not close(a, b) for a, b in zip(timing["decision_2"].get("estimate", ()), delay_estimate)) or
            len(timing["decision_2"].get("posterior_states", [])) != len(delayed_set)):
        raise ValueError("delayed observation was not incorporated at its release stage")
    failed = timing.get("inconsistent_history", {})
    if failed.get("status") != "no_compatible_hypothesis" or failed.get("candidate_count") != 0:
        raise ValueError("estimator failure did not report an empty compatible prior")
    oracle = causal_reference()
    return {"schema": "csl.mpc09-two-particle-check/1", "status": "verified",
            "rows_per_controller": expected_rows,
            "distinct_history_counts": [len(rows) for rows in histories_by_arm],
            "causal_reference": oracle,
            "finite_catalogue_scope_only": True}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_output_feedback.py DRIVER")
    raw = subprocess.check_output([sys.argv[1]], text=True)
    actual = json.loads(raw)
    print(json.dumps(verify(actual), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

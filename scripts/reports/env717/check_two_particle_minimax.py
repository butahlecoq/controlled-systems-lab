#!/usr/bin/env python3
"""Independently replay the finite TwoParticleGame and check both solvers."""

from __future__ import annotations

import itertools
import json
import math
import subprocess
import sys

SCALE = 1_000_000
HORIZON = 4
INNER_STEPS = 20
DT = 0.2
ACTIONS = (-3, 0, 3)
INITIAL = (2 * SCALE, 0, 0, 0)
TARGET_RADIUS_TICKS = SCALE


def round_ticks(value: float) -> int:
    scaled = value * SCALE
    return math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)


def derivative(state: tuple[float, ...], control: int, disturbance: int) -> tuple[float, ...]:
    x1, v1, x2, v2 = state
    del x1, x2
    return (v1, -10.0 * v1 + 10.0 * control, v2, float(disturbance))


def advance(state_ticks: tuple[int, ...], control: int, disturbance: int) -> tuple[int, ...]:
    state = tuple(value / SCALE for value in state_ticks)
    h = DT / INNER_STEPS
    for _ in range(INNER_STEPS):
        k1 = derivative(state, control, disturbance)
        k2 = derivative(tuple(x + h * y / 2 for x, y in zip(state, k1)), control, disturbance)
        k3 = derivative(tuple(x + h * y / 2 for x, y in zip(state, k2)), control, disturbance)
        k4 = derivative(tuple(x + h * y for x, y in zip(state, k3)), control, disturbance)
        state = tuple(x + h * (a + 2 * b + 2 * c + d) / 6
                      for x, a, b, c, d in zip(state, k1, k2, k3, k4))
    return tuple(round_ticks(value) for value in state)


def build_graph():
    layers = [[INITIAL]]
    transitions = []
    for _ in range(HORIZON):
        next_states = set()
        rows = {}
        for state in layers[-1]:
            row = []
            for control in ACTIONS:
                destinations = []
                for disturbance in ACTIONS:
                    successor = advance(state, control, disturbance)
                    destinations.append(successor)
                    next_states.add(successor)
                row.append(destinations)
            rows[state] = row
        layers.append(sorted(next_states))
        transitions.append(rows)
    return layers, transitions


def value_tables(layers, transitions):
    values = [None] * (HORIZON + 1)
    values[-1] = {state: abs(state[0] - state[2]) / SCALE for state in layers[-1]}
    for stage in range(HORIZON - 1, -1, -1):
        values[stage] = {}
        for state in layers[stage]:
            action_scores = [max(values[stage + 1][successor]
                                 for successor in transitions[stage][state][action_id])
                             for action_id in range(len(ACTIONS))]
            values[stage][state] = min(action_scores)
    return values


def winning_sets(layers, transitions, terminal_stage):
    winning = [set() for _ in range(terminal_stage + 1)]
    winning[terminal_stage] = {state for state in layers[terminal_stage]
                               if abs(state[0] - state[2]) <= TARGET_RADIUS_TICKS}
    for stage in range(terminal_stage - 1, -1, -1):
        winning[stage] = {
            state for state in layers[stage]
            if any(all(successor in winning[stage + 1]
                       for successor in transitions[stage][state][action_id])
                   for action_id in range(len(ACTIONS)))
        }
    return winning


def expected_trajectory(layers, transitions, values):
    path = []
    state = INITIAL
    for stage in range(HORIZON + 1):
        row = {"stage": stage, "time_seconds": stage * DT,
               "state_ticks": list(state),
               "state": [value / SCALE for value in state],
               "minimax_value": values[stage][state]}
        if stage < HORIZON:
            scores = [max(values[stage + 1][successor]
                          for successor in transitions[stage][state][action_id])
                      for action_id in range(len(ACTIONS))]
            control_id = next(index for index, score in enumerate(scores)
                              if math.isclose(score, min(scores), rel_tol=0, abs_tol=1e-12))
            disturbance_scores = [values[stage + 1][successor]
                                  for successor in transitions[stage][state][control_id]]
            disturbance_id = next(index for index, score in enumerate(disturbance_scores)
                                  if math.isclose(score, max(disturbance_scores), rel_tol=0, abs_tol=1e-12))
            row["control"] = ACTIONS[control_id]
            row["disturbance"] = ACTIONS[disturbance_id]
            state = transitions[stage][state][control_id][disturbance_id]
        path.append(row)
    return path


def close(a, b, tolerance=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def verify(actual):
    if actual.get("schema") != "csl.env717-two-particle-minimax/1":
        raise ValueError("result schema differs")
    source = actual.get("source", {})
    if (source.get("repository_commit") != "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8" or
            source.get("file_blob") != "7e7d326f8ff81f7dacc05ac72848eeaac6a03021" or
            "Apache-2.0" not in source.get("license", "")):
        raise ValueError("pinned source identity or license differs")
    if actual.get("adaptation", {}).get("information_pattern") != (
            "finite causal game: u chooses from the observed current state; then v observes u and responds before the next state is observed"):
        raise ValueError("game information pattern is missing")
    if actual.get("adaptation", {}).get("objective_orientation") != (
            "u minimizes the terminal absolute position gap (maximizes the source reward); v maximizes the gap"):
        raise ValueError("source reward orientation differs")
    layers, transitions = build_graph()
    if actual.get("graph_state_counts") != [len(layer) for layer in layers]:
        raise ValueError("forward reachable graph counts differ from independent RK4 replay")
    expected_layers = actual.get("figure_layers", [])
    if len(expected_layers) != HORIZON + 1:
        raise ValueError("figure layer count differs")
    winning = winning_sets(layers, transitions, HORIZON)
    for stage, (expected, states) in enumerate(zip(expected_layers, layers)):
        if expected.get("stage") != stage:
            raise ValueError("figure stage labels are out of order")
        forward = [item["ticks"] for item in expected.get("forward_states", [])]
        backward = [item["ticks"] for item in expected.get("backward_winning_intersection", [])]
        if forward != [list(state) for state in states]:
            raise ValueError(f"forward reachable states differ at stage {stage}")
        if backward != [list(state) for state in states if state in winning[stage]]:
            raise ValueError(f"backward-winning intersection differs at stage {stage}")
    horizons = actual.get("capture_horizon_sweep", [])
    expected_sweep = []
    for steps in range(1, HORIZON + 1):
        reachable = winning_sets(layers, transitions, steps)
        expected_sweep.append({"steps": steps, "seconds": steps * DT,
                               "initial_state_winning": INITIAL in reachable[0]})
    if len(horizons) != len(expected_sweep) or any(
            observed != expected for observed, expected in zip(horizons, expected_sweep)):
        raise ValueError("robust capture horizon sweep differs from independent backward induction")
    if actual.get("first_robust_capture_steps") != 4:
        raise ValueError("first robust capture is not at the expected fourth stage")
    values = value_tables(layers, transitions)
    if not close(actual.get("finite_causal_minimax_terminal_gap"), values[0][INITIAL]):
        raise ValueError("causal minimax value differs from independent dynamic programming")
    path = expected_trajectory(layers, transitions, values)
    observed_path = actual.get("minimax_trajectory", [])
    if len(observed_path) != len(path):
        raise ValueError("minimax trajectory length differs")
    for observed, expected in zip(observed_path, path):
        if (observed.get("stage") != expected["stage"] or
                observed.get("state_ticks") != expected["state_ticks"] or
                observed.get("control") != expected.get("control") or
                observed.get("disturbance") != expected.get("disturbance") or
                not close(observed.get("minimax_value"), expected["minimax_value"])):
            raise ValueError("minimax policy trajectory differs from independent replay")
    if not close(values[0][INITIAL], 0.859899, 1e-6):
        raise ValueError("analytic pilot value changed")
    return {"schema": "csl.env717-two-particle-check/1",
            "status": "verified", "forward_states_checked": sum(map(len, layers)),
            "transition_cells_checked": sum(len(layer) for layer in layers[:-1]) * 9,
            "backward_layers_checked": len(winning), "minimax_value": values[0][INITIAL],
            "target_horizon": 4, "trajectory_steps_checked": HORIZON}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_two_particle_minimax.py DRIVER")
    completed = subprocess.run([sys.argv[1]], capture_output=True, text=True,
                               timeout=120, check=True)
    result = json.loads(completed.stdout)
    print(json.dumps(verify(result), indent=2))


if __name__ == "__main__":
    main()

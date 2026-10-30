#!/usr/bin/env python3
"""Independently reconstruct the finite HomicidalChauffeur graph and values."""

from __future__ import annotations

import json
import math
import subprocess
import sys

SCALE = 1_000_000
HORIZON = 4
INNER_STEPS = 10
DT = 0.1
TURN_RATES = (-1.0, 0.0, 1.0)
EVADER_HEADINGS = (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0)
INITIAL = (0, 0, 0, 2_500_000, 7_500_000)
TARGET_RADIUS = 7.8
SOURCE_STATE_ORDER = ["time", "pursuer_x", "pursuer_y", "pursuer_heading",
                      "evader_x", "evader_y"]


def round_ticks(value: float) -> int:
    scaled = value * SCALE
    return math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)


def derivative(state: tuple[float, ...], turn_rate: float,
               evader_heading: float) -> tuple[float, ...]:
    return (3.0 * math.cos(state[2]), 3.0 * math.sin(state[2]), turn_rate,
            math.cos(evader_heading), math.sin(evader_heading))


def advance(state_ticks: tuple[int, ...], turn_rate: float,
            evader_heading: float) -> tuple[int, ...]:
    state = tuple(value / SCALE for value in state_ticks)
    step_size = DT / INNER_STEPS
    for _ in range(INNER_STEPS):
        k1 = derivative(state, turn_rate, evader_heading)
        k2 = derivative(tuple(x + step_size * y / 2 for x, y in zip(state, k1)),
                         turn_rate, evader_heading)
        k3 = derivative(tuple(x + step_size * y / 2 for x, y in zip(state, k2)),
                         turn_rate, evader_heading)
        k4 = derivative(tuple(x + step_size * y for x, y in zip(state, k3)),
                         turn_rate, evader_heading)
        state = tuple(x + step_size * (a + 2 * b + 2 * c + d) / 6
                      for x, a, b, c, d in zip(state, k1, k2, k3, k4))
    return tuple(round_ticks(value) for value in state)


def separation(state: tuple[int, ...]) -> float:
    return math.hypot(state[0] - state[3], state[1] - state[4]) / SCALE


def build_graph():
    layers = [[INITIAL]]
    transitions = []
    for _ in range(HORIZON):
        rows = {}
        successors = set()
        for state in layers[-1]:
            action_rows = []
            for turn_rate in TURN_RATES:
                row = [advance(state, turn_rate, heading) for heading in EVADER_HEADINGS]
                action_rows.append(row)
                successors.update(row)
            rows[state] = action_rows
        transitions.append(rows)
        layers.append(sorted(successors))
    return layers, transitions


def winning_sets(layers, transitions, steps):
    winning = [set() for _ in range(steps + 1)]
    winning[-1] = {state for state in layers[steps]
                   if separation(state) <= TARGET_RADIUS}
    for stage in range(steps - 1, -1, -1):
        winning[stage] = {
            state for state in layers[stage]
            if any(all(successor in winning[stage + 1]
                       for successor in transitions[stage][state][action_id])
                   for action_id in range(len(TURN_RATES)))
        }
    return winning


def value_tables(layers, transitions):
    values = [None] * (HORIZON + 1)
    values[-1] = {state: separation(state) for state in layers[-1]}
    for stage in range(HORIZON - 1, -1, -1):
        values[stage] = {}
        for state in layers[stage]:
            scores = [max(values[stage + 1][successor]
                          for successor in transitions[stage][state][action_id])
                      for action_id in range(len(TURN_RATES))]
            values[stage][state] = min(scores)
    return values


def trajectory(layers, transitions, values):
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
                      for action_id in range(len(TURN_RATES))]
            control_id = next(index for index, value in enumerate(scores)
                              if math.isclose(value, min(scores), rel_tol=0, abs_tol=1e-12))
            response_values = [values[stage + 1][successor]
                               for successor in transitions[stage][state][control_id]]
            response_id = next(index for index, value in enumerate(response_values)
                               if math.isclose(value, max(response_values), rel_tol=0, abs_tol=1e-12))
            row["turn_rate"] = TURN_RATES[control_id]
            row["evader_heading"] = EVADER_HEADINGS[response_id]
            state = transitions[stage][state][control_id][response_id]
        path.append(row)
    return path


def close(a, b, tolerance=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def verify(actual):
    if actual.get("schema") != "csl.env717-homicidal-chauffeur/1":
        raise ValueError("result schema differs")
    source = actual.get("source", {})
    if (source.get("repository_commit") != "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8" or
            source.get("file_blob") != "f770a5c81c363ba628c987ee70f84af483c81b10" or
            "Apache-2.0" not in source.get("license", "")):
        raise ValueError("pinned source identity or license differs")
    adaptation = actual.get("adaptation", {})
    if (adaptation.get("state_quantization_scale") != SCALE or
            adaptation.get("target_radius") != TARGET_RADIUS or
            adaptation.get("horizon_steps") != HORIZON or
            adaptation.get("turn_rate_catalogue") != list(TURN_RATES) or
            adaptation.get("evader_heading_catalogue_radians") != list(EVADER_HEADINGS) or
            adaptation.get("initial_state") != [0.0, 0.0, 0.0, 0.0, 2.5, 7.5]):
        raise ValueError("finite lattice or reachability target differs")
    if (actual.get("source_state_order") != SOURCE_STATE_ORDER or
            actual.get("projection_labels") != {
                "pursuer": ["pursuer x position", "pursuer y position"],
                "evader": ["evader x position", "evader y position"]}):
        raise ValueError("source or physical state ordering differs")
    if adaptation.get("information_pattern") != (
            "finite causal response: pursuer chooses from the current state, then evader observes that turn rate and responds before the next state is observed"):
        raise ValueError("finite game information pattern is missing")
    if adaptation.get("objective_orientation") != (
            "analysis adaptation: pursuer turn rate minimizes terminal Euclidean separation and evader heading maximizes it; source returns positive separation but does not specify per-agent payoff signs"):
        raise ValueError("zero-sum payoff-sign assumption is not disclosed")
    layers, transitions = build_graph()
    if actual.get("graph_state_counts") != [len(layer) for layer in layers]:
        raise ValueError("forward state counts differ from independent RK4 reconstruction")
    figure_layers = actual.get("figure_layers", [])
    if len(figure_layers) != HORIZON + 1:
        raise ValueError("figure layer count differs")
    winning = winning_sets(layers, transitions, HORIZON)
    for stage, (observed, states) in enumerate(zip(figure_layers, layers)):
        if observed.get("stage") != stage:
            raise ValueError("figure stage labels are out of order")
        if not close(observed.get("time_seconds"), stage * DT):
            raise ValueError("figure layer time differs from stage")
        forward = observed.get("forward_states", [])
        if [item.get("ticks") for item in forward] != [list(s) for s in states]:
            raise ValueError(f"forward state set differs at stage {stage}")
        for item, state in zip(forward, states):
            if item.get("state") != [value / SCALE for value in state]:
                raise ValueError(f"forward state coordinates differ at stage {stage}")
        expected_winning = [list(state) for state in states if state in winning[stage]]
        winning_items = observed.get("backward_winning_intersection", [])
        if [item.get("ticks") for item in winning_items] != expected_winning:
            raise ValueError(f"backward-winning intersection differs at stage {stage}")
        for item, state in zip(winning_items, (state for state in states if state in winning[stage])):
            if item.get("state") != [value / SCALE for value in state]:
                raise ValueError(f"backward-winning coordinates differ at stage {stage}")
    expected_capture = []
    first_capture = -1
    for steps in range(1, HORIZON + 1):
        wins = INITIAL in winning_sets(layers, transitions, steps)[0]
        expected_capture.append({"steps": steps, "seconds": steps * DT,
                                 "initial_state_winning": wins})
        if wins and first_capture < 0:
            first_capture = steps
    if actual.get("capture_horizon_sweep") != expected_capture:
        raise ValueError("robust capture horizon sweep differs from independent backward induction")
    if actual.get("first_robust_capture_steps") != first_capture or first_capture != 4:
        raise ValueError("first robust capture stage differs")
    values = value_tables(layers, transitions)
    if not close(actual.get("finite_causal_minimax_terminal_separation"), values[0][INITIAL]):
        raise ValueError("finite causal minimax value differs from independent dynamic programming")
    expected_path = trajectory(layers, transitions, values)
    observed_path = actual.get("minimax_trajectory", [])
    if len(observed_path) != len(expected_path):
        raise ValueError("minimax trajectory length differs")
    for observed, expected in zip(observed_path, expected_path):
        for key in ("stage", "state_ticks", "turn_rate", "evader_heading"):
            if observed.get(key) != expected.get(key):
                raise ValueError(f"minimax path differs at {key}")
        if (observed.get("state") != expected["state"] or
                not close(observed.get("time_seconds"), expected["time_seconds"])):
            raise ValueError("minimax path coordinates or time differ")
        if not close(observed.get("minimax_value"), expected["minimax_value"]):
            raise ValueError("minimax path value differs")
    if not close(values[0][INITIAL], 7.778040783932288, 1e-9):
        raise ValueError("pilot minimax value differs from the checked finite-game reference")
    return {"schema": "csl.env717-homicidal-chauffeur-check/1", "status": "verified",
            "forward_states_checked": sum(map(len, layers)),
            "transition_cells_checked": sum(len(layer) for layer in layers[:-1]) *
                                          len(TURN_RATES) * len(EVADER_HEADINGS),
            "backward_layers_checked": HORIZON + 1,
            "first_robust_capture_steps": first_capture,
            "finite_causal_minimax_terminal_separation": values[0][INITIAL],
            "trajectory_steps_checked": HORIZON}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_homicidal_chauffeur.py DRIVER")
    completed = subprocess.run([sys.argv[1]], capture_output=True, text=True, timeout=120, check=True)
    print(json.dumps(verify(json.loads(completed.stdout)), indent=2))


if __name__ == "__main__":
    main()

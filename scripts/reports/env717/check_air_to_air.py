#!/usr/bin/env python3
"""Independently replay the pinned AirToAirInterception finite-game pilot."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
from pathlib import Path

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "9054c9fcd01e49f3dbfd8b8ee8d12e7365e1d9b5"
DT, INNER_N, HORIZON = 0.05, 10, 3
INITIAL = (0., 0., 30., 0., 0., 80., 0., 200., -70., 0., 80.)
U = ((0., 0.), (4.35, 0.), (-4.35, 0.), (0., 5.), (0., -5.))
V = ((0., 0.), (0.66, 0.), (-0.66, 0.), (0., 1.), (0., -1.))


def advance(state: tuple[float, ...], u: tuple[float, float],
            v: tuple[float, float]) -> tuple[float, ...]:
    x = list(state)
    h = DT / INNER_N
    for _ in range(INNER_N):
        dx = (x[2], x[3], -x[3] + u[0], x[5], x[6], -x[6] + u[1],
              x[8], -v[0], x[10], -v[1])
        x = [x[0] + h, *(xi + h * di for xi, di in zip(x[1:], dx))]
    return tuple(x)


def relative(x: tuple[float, ...]) -> tuple[float, float, float, float]:
    return (x[1] - x[7], x[2] - x[8], x[4] - x[9], x[5] - x[10])


def range_value(x: tuple[float, ...]) -> float:
    rel = relative(x)
    return math.hypot(rel[0], rel[2])


def enumerate_game() -> dict:
    plans = []
    sequences = tuple(itertools.product(range(len(V)), repeat=HORIZON))
    for plan in itertools.product(range(len(U)), repeat=HORIZON):
        cases = []
        for sequence in sequences:
            states = [INITIAL]
            for ui, vi in zip(plan, sequence):
                states.append(advance(states[-1], U[ui], V[vi]))
            cases.append((range_value(states[-1]), sequence, states))
        plans.append((max(row[0] for row in cases), plan, cases))
    optimum = min(row[0] for row in plans)
    minimizing = [i for i, row in enumerate(plans) if row[0] <= optimum + 1e-9]
    selected = plans[minimizing[0]]
    worst = min((case for case in selected[2] if case[0] >= selected[0] - 1e-9),
                key=lambda case: case[1])
    return {"plans": plans, "value": optimum, "minimizing": minimizing,
            "selected_plan": selected[1], "worst_sequence": worst[1],
            "trajectory": worst[2]}


def verify(actual: dict) -> dict:
    assert actual["schema"] == "csl.env717-air-to-air-pilot/1"
    assert actual["source_repository_commit"] == SOURCE_COMMIT
    assert actual["source_file_blob"] == SOURCE_BLOB
    assert actual["horizon"] == HORIZON
    expected = enumerate_game()
    assert len(actual["plans"]) == 125
    assert actual["controller_plan_count"] == 125
    assert actual["disturbance_sequence_count_per_plan"] == 125
    assert actual["minimizing_plan_indices"] == expected["minimizing"]
    assert math.isclose(actual["objective_value"], expected["value"], abs_tol=1e-8)
    for saved, (worst, plan, cases) in zip(actual["plans"], expected["plans"]):
        assert saved["control_indices"] == list(plan)
        assert math.isclose(saved["worst_terminal_range"], worst, abs_tol=1e-8)
        max_states = [case[2][-1] for case in cases if case[0] >= worst - 1e-8]
        assert any(max(abs(a - b) for a, b in zip(saved["maximizing_terminal_state"], state)) < 1e-7
                   for state in max_states)
    timing = actual["timing"]
    assert timing["warmup_calls"] == 0 and timing["measured_calls"] == 1
    assert len(timing["measured_wall_ns"]) == 1
    assert type(timing["measured_wall_ns"][0]) is int and timing["measured_wall_ns"][0] > 0
    assert timing["comparison_claim"] is False
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    completed = subprocess.run([str(args.executable)], check=True, capture_output=True, text=True)
    verify(json.loads(completed.stdout))
    print("AirToAirInterception finite-game replay passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

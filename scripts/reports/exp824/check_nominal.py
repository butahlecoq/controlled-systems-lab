#!/usr/bin/env python3
"""Independently check the source-derived deterministic and minimax fixtures."""
from __future__ import annotations

from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import sys

ACTIONS = (Fraction("-2.5"), Fraction("0"), Fraction("2.5"))
DISTURBANCES = (Fraction("-1"), Fraction("0"), Fraction("1"))
NOMINAL_DISTURBANCE = Fraction("1")
TOL = 1e-8


def step(state: tuple[Fraction, ...], control: Fraction, disturbance: Fraction) -> tuple[Fraction, ...]:
    x1, x2, x3, x4 = state
    return (x1 + Fraction("0.01") * x2 + Fraction("0.09") * control,
            control,
            x3 + Fraction("0.1") * x4 + Fraction("0.0045") * disturbance,
            x4 + Fraction("0.1") * disturbance)


def objective(state: tuple[Fraction, ...]) -> Fraction:
    return (state[0] - state[2]) ** 2


def close(actual: float, expected: Fraction | float, tolerance: float = TOL) -> bool:
    return math.isfinite(actual) and abs(actual - float(expected)) <= tolerance * max(1.0, abs(float(expected)))


def replay(plan: tuple[int, ...], disturbances: tuple[Fraction, ...]) -> list[tuple[Fraction, ...]]:
    states = [(Fraction("4.5"), Fraction(0), Fraction(0), Fraction(0))]
    for action_index, disturbance in zip(plan, disturbances):
        states.append(step(states[-1], ACTIONS[action_index], disturbance))
    return states


def invert(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    rows = [list(row) + [float(i == j) for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-14:
            raise AssertionError("saved parallelotope frame is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scale = rows[column][column]
        rows[column] = [value / scale for value in rows[column]]
        for row in range(size):
            if row == column:
                continue
            scale = rows[row][column]
            rows[row] = [a - scale * b for a, b in zip(rows[row], rows[column])]
    return [row[size:] for row in rows]


def contains(trace: dict, stage_index: int, point: tuple[Fraction, ...]) -> None:
    stage = trace["stages"][stage_index]
    representation = trace["representation"]
    p = [float(value) for value in point]
    if representation == "exact_polytope":
        if stage_index == 0 and not stage["vertices"]:
            return
        assert any(all(close(float(value), exact) for value, exact in zip(vertex, point))
                   for vertex in stage["vertices"]), (representation, stage_index, p)
    elif representation == "box":
        assert all(lo - TOL <= value <= hi + TOL
                   for value, lo, hi in zip(p, stage["lower"], stage["upper"])), (representation, stage_index, p)
    elif representation == "zonotope":
        center = stage["center"]
        generators = stage["generators"]
        columns = generators["cols"]
        values = generators["values"]
        for row, value in enumerate(p):
            radius = sum(abs(values[row * columns + column]) for column in range(columns))
            assert center[row] - radius - TOL <= value <= center[row] + radius + TOL, (representation, stage_index, row)
    elif representation == "parallelotope":
        frame = trace["frame"]
        n = frame["rows"]
        matrix = [frame["values"][row * n:(row + 1) * n] for row in range(n)]
        inverse = invert(matrix)
        y = [sum(inverse[row][col] * p[col] for col in range(n)) for row in range(n)]
        assert all(lo - TOL <= value <= hi + TOL
                   for value, lo, hi in zip(y, stage["lower"], stage["upper"])), (representation, stage_index, y)
    elif representation == "ellipsoid":
        distance = 0.0
        for value, center, radius in zip(p, stage["center"], stage["radii"]):
            delta = value - center
            if radius == 0.0:
                assert abs(delta) <= TOL
            else:
                distance += (delta / radius) ** 2
        assert distance <= 1.0 + TOL, (representation, stage_index, distance)
    else:
        raise AssertionError(f"unknown trace representation {representation}")


def check(record: dict) -> dict:
    assert record["schema"] == "csl.issue824-two-points-nominal/1"
    assert record["environment"] == "TwoPointsOnParallelLines"
    assert record["adaptation"]["nominal_opponent_input"] == [1.0, 1.0, 1.0]
    plans = list(itertools.product(range(3), repeat=3))
    nominal_scores = []
    for track in record["nominal_tracks"]:
        assert track["coverage"] == "complete"
        expected_bound = ("finite_catalogue_minimum_under_binary64"
                          if track["representation"] == "exact_polytope" else "none_certified")
        assert track["objective_bound_direction"] == expected_bound
        assert len(track["attempts"]) == len(plans)
        assert len(track["trace"]["stages"]) == 4
        scores = []
        for plan, attempt in zip(plans, track["attempts"]):
            assert attempt["status"] == "scored"
            expected_attempt_evidence = ("finite_catalogue_objective_under_binary64"
                if track["representation"] == "exact_polytope" else "none_certified")
            assert attempt["objective_bound_direction"] == expected_attempt_evidence
            assert tuple(attempt["action_indices"]) == plan
            expected = objective(replay(plan, (NOMINAL_DISTURBANCE,) * 3)[-1])
            assert close(attempt["candidate_score"], expected), (track["representation"], plan, attempt, str(expected))
            scores.append(expected)
        selected_index = min(range(len(scores)), key=lambda index: scores[index])
        assert track["selected_attempt"] == selected_index
        selected_plan = plans[selected_index]
        states = replay(selected_plan, (NOMINAL_DISTURBANCE,) * 3)
        saved_states = track["replay"]["states"]
        assert len(saved_states) == len(states)
        for saved, expected in zip(saved_states, states):
            assert all(close(value, exact) for value, exact in zip(saved, expected))
        assert close(track["replay"]["terminal_objective"], objective(states[-1]))
        assert close(track["candidate_score"], objective(states[-1]))
        for index, state in enumerate(states):
            contains(track["trace"], index, state)
        nominal_scores.append(float(objective(states[-1])))

    minimax_values = []
    for plan in plans:
        worst = max(objective(replay(plan, history)[-1])
                    for history in itertools.product(DISTURBANCES, repeat=3))
        minimax_values.append(worst)
    expected_minimax = min(minimax_values)
    assert close(record["exact_finite_minimax"]["value"], expected_minimax)
    assert abs(min(nominal_scores) - float(expected_minimax)) > 1e-9
    return {"schema": "csl.issue824-two-points-nominal-check/1",
        "status": "passed", "nominal_tracks_checked": len(nominal_scores),
        "nominal_action_plans_checked_per_track": len(plans),
        "nominal_exact_objective": min(nominal_scores),
        "finite_minimax_plans_checked": len(plans),
        "finite_minimax_disturbance_histories_per_plan": 27,
        "finite_minimax_exact_value": float(expected_minimax),
        "checked_trace_stages_per_track": 4}


def main() -> None:
    path = Path(sys.argv[1])
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") == "csl.issue824-two-points-nominal-bundle/1":
        record = record["nominal_result"]
    print(json.dumps(check(record), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

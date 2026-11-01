#!/usr/bin/env python3
"""Independently enumerate the finite TwoPoints fixed-plan game in rationals."""
from __future__ import annotations

from fractions import Fraction as F
from itertools import product
from typing import Any

METHODS = ("exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid")
CONTROLS = (-F(5, 2), F(0), F(5, 2))
DISTURBANCES = (-F(1), F(0), F(1))


def step(state: tuple[F, ...], control: F, disturbance: F) -> tuple[F, ...]:
    x1, x2, x3, x4 = state
    return (x1 + F(1, 100) * x2 + F(9, 100) * control,
            control,
            x3 + F(1, 10) * x4 + F(9, 2000) * disturbance,
            x4 + F(1, 10) * disturbance)


def replay(plan: tuple[int, ...]) -> tuple[F, list[F]]:
    worst = F(-1)
    losses: list[F] = []
    for disturbance_indices in product(range(3), repeat=3):
        state = (F(9, 2), F(0), F(0), F(0))
        for control_index, disturbance_index in zip(plan, disturbance_indices):
            state = step(state, CONTROLS[control_index], DISTURBANCES[disturbance_index])
        loss = (state[0] - state[2]) ** 2
        losses.append(loss)
        worst = max(worst, loss)
    return worst, losses


def check(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema") != "csl.issue824.matched-minimax-benchmark/1":
        raise ValueError("unexpected matched minimax result schema")
    if tuple(record.get("methods", ())) != METHODS:
        raise ValueError("the matched result must contain all five representation tracks")
    if len(record.get("samples", [])) != 25:
        raise ValueError("expected five rotated measurements for each of five methods")
    oracle: list[tuple[F, tuple[int, ...]]] = []
    for plan in product(range(3), repeat=3):
        value, _ = replay(plan)
        oracle.append((value, plan))
    optimum = min(value for value, _ in oracle)
    method_rows = {name: [] for name in METHODS}
    for sample in record["samples"]:
        method = sample.get("method")
        if method not in method_rows or sample.get("elapsed_ns", 0) <= 0:
            raise ValueError("measurement row is missing its method or positive duration")
        if sample.get("outcome", {}).get("status") != "completed":
            raise ValueError(f"{method} attempt failed: {sample.get('error', sample)}")
        outcome = sample["outcome"]
        if outcome.get("candidate_plans") != 27:
            raise ValueError(f"{method} did not score all 27 plans")
        plan = tuple(outcome.get("selected_action_indices", ()))
        if len(plan) != 3 or any(index not in range(3) for index in plan):
            raise ValueError(f"{method} selected an invalid three-stage plan")
        replay_value, _ = replay(plan)
        reported = F(str(outcome["replayed_worst_value"]))
        if abs(reported - replay_value) > F(1, 10**9):
            raise ValueError(f"{method} selected-plan replay differs from rational enumeration")
        if method == "exact_polytope":
            exact_optimum = F(str(outcome["reported_optimum"]))
            if abs(exact_optimum - optimum) > F(1, 10**9):
                raise ValueError("exact finite minimax value differs from rational all-plan enumeration")
            if replay_value != optimum:
                raise ValueError("exact selected plan is not a rational minimizer")
        method_rows[method].append(sample)
    for method, samples in method_rows.items():
        if len(samples) != 5:
            raise ValueError(f"{method} has {len(samples)} measurements, expected five")
    return {"schema": "csl.issue824.matched-minimax-check/1", "status": "verified",
        "oracle": "exact Fraction replay of every control plan and all 27 disturbance histories",
        "control_plan_count": len(oracle), "disturbance_histories_per_plan": 27,
        "exact_finite_minimax_value": float(optimum),
        "measurement_samples_verified": sum(map(len, method_rows.values())),
        "failures": 0, "selected_plan_full_history_replay": "verified for all 25 timed outcomes",
        "exact_search_complete": "verified across all 27 control plans"}

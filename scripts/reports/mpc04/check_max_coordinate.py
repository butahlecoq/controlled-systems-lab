#!/usr/bin/env python3
"""Independent replay and completeness checks for the MPC-04 pilot record."""
from __future__ import annotations
import itertools
import json
import math
import sys
from pathlib import Path

T = 4
ACTIONS = (-1.0, 1.0)
DISTURBANCES = (-1.0, 1.0)
INITIAL = (0.0, 0.2, 0.0)
H = 2

def advance(s, u, v):
    t, y, z = s
    h = 0.001
    for _ in range(100):
        y, z = y + h * (z + v), z + h * (-y + u)
    return (t + 0.1, y, z)

def objective(s):
    return max(abs(s[1]), abs(s[2]))

def close(a, b, tol=2e-12):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)

def check(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "csl.mpc04.max-coordinate-pilot/1"
    assert data["source"]["environment"] == "MaxCoordinateGame"
    assert data["source"]["commit"] == "f4d76c60f4003f50954174e96eafd8e514bd5441"
    all_histories = set(itertools.product(DISTURBANCES, repeat=T))
    assert data["fixtures"]["strict_two_step"]["fixed_plan_squared"] == 2
    assert data["fixtures"]["strict_two_step"]["executed_replanning_worst_squared"] == 2
    assert data["fixtures"]["strict_two_step"]["causal_squared"] == 1
    assert data["fixtures"]["strict_two_step"]["history_squared"] == {
        "(-1, 0)": 2, "(0, 0)": 1, "(1, 0)": 2}
    assert data["fixtures"]["scalar_two_step"]["fixed_plan"] == 2
    assert data["fixtures"]["scalar_two_step"]["executed_replanning_worst"] == 0
    assert data["fallback_fixtures"]["deadline"] == {"episodes": 16, "fallback_steps": 64}
    assert data["fallback_fixtures"]["solver_failure"] == {"episodes": 16, "fallback_steps": 64}
    variants = data["variants"]
    assert len(variants) == 4
    episode_index = {}
    for row in data["episodes"]:
        key = (row["policy"], row["horizon"])
        episode_index.setdefault(key, []).append(row)
    for key, rows in episode_index.items():
        assert len(rows) == len(all_histories)
        assert {tuple(row["disturbances"]) for row in rows} == all_histories
        assert len({tuple(row["disturbances"]) for row in rows}) == len(rows)
        policy, horizon = key
        assert policy in ("nominal_zero_disturbance", "finite_minimax")
        moving = horizon == "moving_fixed_2_stage_lookahead"
        for row in rows:
            hist = tuple(row["disturbances"])
            states = [tuple(s) for s in row["states"]]
            assert len(states) == T + 1 and states[0] == INITIAL
            assert len(row["decisions"]) == T
            for k, decision in enumerate(row["decisions"]):
                requested = H if moving else T-k
                assert decision["requested_horizon"] == requested
                assert decision["effective_horizon"] == requested
                assert tuple(decision["observed_state"]) == states[k]
                action = decision["action"]
                assert action in ACTIONS or decision["fallback"] and action == 0.0
                assert decision["status"] in ("solved", "deadline_fallback", "solver_failure_fallback")
                assert decision["fallback"] == (decision["status"] != "solved")
                assert isinstance(decision["solve_ns"], int) and decision["solve_ns"] >= 0
                nxt = advance(states[k], action, hist[k])
                assert all(close(a, b) for a, b in zip(nxt, states[k+1]))
                if not decision["fallback"]:
                    plan = tuple(decision["remaining_plan"])
                    assert len(plan) == requested and plan[0] == action
                    candidate_values = []
                    if policy == "finite_minimax":
                        suffixes = itertools.product(DISTURBANCES, repeat=requested)
                    else:
                        suffixes = [(0.0,) * requested]
                    for suffix in suffixes:
                        s = states[k]
                        for u, v in zip(plan, suffix):
                            s = advance(s, u, v)
                        candidate_values.append(objective(s) ** 2)
                    planned = max(candidate_values)
                    assert close(decision["planned_squared_objective"], planned)
                    best = math.inf
                    for candidate in itertools.product(ACTIONS, repeat=requested):
                        values = []
                        suffixes = (itertools.product(DISTURBANCES, repeat=requested)
                                    if policy == "finite_minimax" else [(0.0,) * requested])
                        for suffix in suffixes:
                            s = states[k]
                            for u, v in zip(candidate, suffix):
                                s = advance(s, u, v)
                            values.append(objective(s) ** 2)
                        best = min(best, max(values))
                    assert close(planned, best)
            terminal = states[-1]
            assert close(row["terminal_original_objective"], objective(terminal))
            assert row["violations"] == 0
            assert row["fallback_count"] == sum(d["fallback"] for d in row["decisions"])
            assert row["completed"] is True
    for key, stats in variants.items():
        assert stats["episodes"] == 16
        assert stats["completed_episodes"] == 16
        assert stats["violations"] == 0
        assert stats["decision_count"] == 64
        assert len(stats["per_decision_latency_ns"]) == 64
    svg = path.with_name("trajectory.svg").read_text(encoding="utf-8")
    for token in ("Phase plane (y,z)", "Control and applied disturbance", "scored endpoint"):
        assert token in svg
    print("MPC-04 record replay passed: 64 episodes, 256 state transitions, 4 variants; all 16 histories each.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_max_coordinate.py result.json")
    check(Path(sys.argv[1]))

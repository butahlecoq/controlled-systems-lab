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
QP_POLICIES = {"linear_qp_nominal_linf", "linear_qp_finite_history_robust_linf"}
ROBUST_POLICIES = {"finite_minimax", "linear_qp_finite_history_robust_linf"}
POLICIES = {"nominal_zero_disturbance", "finite_minimax"} | QP_POLICIES
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


def check_solver_residuals(evidence):
    assert evidence["primal"] is not None and evidence["dual"] is not None
    for family, names in ((evidence["primal"], ("rows", "variables")),
                          (evidence["dual"], ("stationarity", "signs", "complementarity"))):
        assert family["verifier_id"] and family["verifier_version"]
        for name in names:
            residual = family[name]
            assert residual is not None
            assert residual["violation"] <= (family["absolute_tolerance"]
                                               + family["relative_tolerance"] * residual["scale"])


def terminal_cost(state, controls, disturbance_suffix):
    for action, disturbance in zip(controls, disturbance_suffix):
        state = advance(state, action, disturbance)
    return objective(state) ** 2


def check_qp_fixture(data):
    fixture = data["qp_analytic_fixture"]
    initial = (0.0, 0.1, 0.0)
    zero = advance(initial, 0.0, 0.0)
    unit = advance(initial, 1.0, 0.0)
    gain_y, gain_z = unit[1] - zero[1], unit[2] - zero[2]
    expected_action = -(zero[1] + zero[2]) / (gain_y + gain_z)
    expected_y = zero[1] + gain_y * expected_action
    expected_z = zero[2] + gain_z * expected_action
    expected_cost = max(abs(expected_y), abs(expected_z)) ** 2
    assert -1.0 < expected_action < 1.0 and expected_y > 0.0 > expected_z
    assert close(expected_y, -expected_z, 1e-9)
    assert close(fixture["expected_control"], expected_action, 1e-9)
    assert close(fixture["expected_terminal_squared_objective"], expected_cost, 1e-9)
    assert abs(fixture["selected_control"] - expected_action) < 2e-4
    assert close(fixture["primary_squared_objective"], expected_cost, 2e-6)
    assert fixture["selected_squared_objective"] <= expected_cost + 2e-6
    assert fixture["tie_tolerance"] == 1e-7 and fixture["status"] == "optimal"
    for solve in fixture["solver_residuals"].values():
        check_solver_residuals(solve)


def check(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "csl.mpc04.max-coordinate-pilot/3"
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
    for kind, status in (("deadline", "deadline_fallback"),
                         ("solver_failure", "solver_failure_fallback")):
        fixture = data["native_fallback_fixtures"][kind]
        assert fixture["completed"] is True
        assert fixture["fallback_count"] == T and fixture["steps"] == T
        assert fixture["statuses"] == [status] * T
        assert fixture["actions"] == [0.0] * T
    qp = data["qp"]
    implementation = data["algorithm_implementation"]
    assert len(implementation["commit"]) == 40
    assert len(implementation["native_executable_sha256"]) == 64
    assert not Path(implementation["native_executable"]).is_absolute()
    assert implementation["native_executable_path_scope"] in {
        "repository-relative", "external-basename-only"}
    assert implementation["algorithm_sources_dirty"] is False
    assert set(implementation["source_sha256"]) == {
        "native_driver", "report_driver", "independent_checker", "cmake_target"}
    assert all(len(digest) == 64 for digest in implementation["source_sha256"].values())
    assert qp["action_domain"] == "continuous [-1,1] per stage"
    assert qp["objective"] == "terminal squared max-coordinate via scalar epigraph"
    assert qp["provider_id"] and qp["provider_version"]
    assert isinstance(qp["provider_setup_ns"], int) and qp["provider_setup_ns"] > 0
    assert "common open-loop control vector" in qp["robust_plan_semantics"]
    measurements = data["measurement"]
    assert measurements["repetitions"] == 5 and measurements["controller_order_alternated"] is True
    repetition_records = measurements["repetition_records"]
    assert len(repetition_records) == 5
    assert len({row["stable_outcome_sha256"] for row in repetition_records}) == 1
    assert len({tuple(row["controller_order"]) for row in repetition_records}) == 2
    check_qp_fixture(data)

    variants = data["variants"]
    assert len(variants) == 8
    episode_index = {}
    for row in data["episodes"]:
        key = (row["policy"], row["horizon"])
        episode_index.setdefault(key, []).append(row)
    expected_keys = {(policy, horizon) for policy in POLICIES for horizon in (
        "shrinking_to_episode_terminal", "moving_fixed_2_stage_lookahead")}
    assert set(episode_index) == expected_keys
    selected_actions = {}
    for key, rows in episode_index.items():
        assert len(rows) == len(all_histories)
        assert {tuple(row["disturbances"]) for row in rows} == all_histories
        assert len({tuple(row["disturbances"]) for row in rows}) == len(rows)
        policy, horizon = key
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
                if policy in QP_POLICIES:
                    assert -1.0 - 1e-7 <= action <= 1.0 + 1e-7 or decision["fallback"] and action == 0.0
                else:
                    assert action in ACTIONS or decision["fallback"] and action == 0.0
                assert decision["status"] in ("solved", "deadline_fallback", "solver_failure_fallback")
                assert decision["fallback"] == (decision["status"] != "solved")
                for name in ("solve_ns", "primary_solve_ns", "tie_solve_ns"):
                    assert isinstance(decision[name], int) and decision[name] >= 0
                nxt = advance(states[k], action, hist[k])
                assert all(close(a, b) for a, b in zip(nxt, states[k+1]))
                if not decision["fallback"]:
                    plan = tuple(decision["remaining_plan"])
                    assert len(plan) == requested and close(plan[0], action, 1e-10)
                    if policy in QP_POLICIES:
                        assert all(-1.0 - 1e-7 <= value <= 1.0 + 1e-7 for value in plan)
                    else:
                        assert all(value in ACTIONS for value in plan)

                    suffixes = (itertools.product(DISTURBANCES, repeat=requested)
                                if policy in ROBUST_POLICIES else [(0.0,) * requested])
                    planned = max(terminal_cost(states[k], plan, suffix) for suffix in suffixes)
                    assert close(decision["planned_squared_objective"], planned, 2e-7)
                    best = math.inf
                    for candidate in itertools.product(ACTIONS, repeat=requested):
                        candidate_suffixes = (itertools.product(DISTURBANCES, repeat=requested)
                                              if policy in ROBUST_POLICIES else [(0.0,) * requested])
                        value = max(terminal_cost(states[k], candidate, suffix)
                                    for suffix in candidate_suffixes)
                        best = min(best, value)

                    if policy in QP_POLICIES:
                        assert decision["solver_status"] == "optimal"
                        assert decision["provider_id"] == qp["provider_id"]
                        assert decision["provider_version"] == qp["provider_version"]
                        assert decision["primary_squared_objective"] is not None
                        for solve in decision["solver_residuals"].values():
                            check_solver_residuals(solve)
                        assert planned <= best + 2e-6
                        primary = math.sqrt(max(0.0, decision["primary_squared_objective"]))
                        assert math.sqrt(planned) <= primary + qp["tie_tolerance"] + 2e-6
                        assert all(sample["solve_ns"] >= sample["primary_solve_ns"] + sample["tie_solve_ns"]
                                   for sample in decision["timing_repetitions"])
                        action_key = (policy, horizon, k, states[k])
                        if action_key in selected_actions:
                            assert close(selected_actions[action_key], action, 2e-6)
                        selected_actions[action_key] = action
                    else:
                        assert close(planned, best)
            terminal = states[-1]
            assert close(row["terminal_original_objective"], objective(terminal))
            assert row["violations"] == 0
            assert row["fallback_count"] == sum(d["fallback"] for d in row["decisions"])
            assert row["completed"] is True
    for stats in variants.values():
        assert stats["episodes"] == 16
        assert stats["completed_episodes"] == 16
        assert stats["violations"] == 0
        assert stats["decision_count"] == 64
        assert len(stats["per_decision_latency_ns"]) == 64
        assert stats["timing_sample_count"] == 320
        assert len(stats["per_decision_latency_samples_ns"]) == 320
        assert stats["decision_latency_range_ns"] == [
            min(stats["per_decision_latency_samples_ns"]),
            max(stats["per_decision_latency_samples_ns"])]
    svg = path.with_name("trajectory.svg").read_text(encoding="utf-8")
    for token in ("Phase plane (y,z)", "Control and applied disturbance", "scored endpoint",
                  "nominal finite action", "finite minimax", "QP nominal",
                  "QP finite-history robust", "solid: shrinking horizon; dashed: moving horizon"):
        assert token in svg
    print("MPC-04 replay passed: 128 episodes, 512 transitions, 8 variants; all 16 histories each.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_max_coordinate.py result.json")
    check(Path(sys.argv[1]))

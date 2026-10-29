#!/usr/bin/env python3
"""Finite-catalogue MPC-04 pilot for source-derived MaxCoordinateGame."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "d509a1457023b14516d2789bd3033dbaa4110017"
SOURCE_PATH = "Environments/MaxCoordinateGame/MaxCoordinateGame.py"
ACTIONS = (-1.0, 1.0)
DISTURBANCES = (-1.0, 1.0)
EPISODE_STEPS = 4
FIXED_LOOKAHEAD = 2
INITIAL_STATE = (0.0, 0.2, 0.0)  # source order: time, y, z
DT = 0.1
INNER_EULER_STEPS = 100

State = tuple[float, float, float]


def advance(s: State, u: float, v: float) -> State:
    """Replay the source's held-action explicit-Euler step (100 substeps)."""
    t, y, z = s
    h = DT / INNER_EULER_STEPS
    for _ in range(INNER_EULER_STEPS):
        next_y = y + h * (z + v)
        next_z = z + h * (-y + u)
        y, z = next_y, next_z
    return (t + DT, y, z)


def objective(s: State) -> float:
    return max(abs(s[1]), abs(s[2]))


def objective_squared(s: State) -> float:
    return objective(s) ** 2


@dataclass(frozen=True)
class Horizon:
    name: str
    fixed: int | None

    def at(self, step: int) -> int:
        return EPISODE_STEPS - step if self.fixed is None else self.fixed


SHRINKING = Horizon("shrinking_to_episode_terminal", None)
MOVING = Horizon("moving_fixed_2_stage_lookahead", FIXED_LOOKAHEAD)


@dataclass
class Decision:
    step: int
    observed_state: State
    action: float
    status: str
    requested_horizon: int
    effective_horizon: int
    planned_squared_objective: float | None
    solve_ns: int
    remaining_plan: tuple[float, ...]
    fallback: bool = False


def plan_value(state: State, controls: tuple[float, ...], disturbances: tuple[float, ...]) -> float:
    for u, v in zip(controls, disturbances):
        state = advance(state, u, v)
    return objective_squared(state)


def solve(state: State, horizon: int, robust: bool, deadline_ns: int) -> tuple[float, tuple[float, ...], float, str, int]:
    start = time.perf_counter_ns()
    best: tuple[float, tuple[int, ...], tuple[float, ...]] | None = None
    for indices in itertools.product(range(len(ACTIONS)), repeat=horizon):
        controls = tuple(ACTIONS[i] for i in indices)
        if robust:
            value = max(plan_value(state, controls, vs)
                        for vs in itertools.product(DISTURBANCES, repeat=horizon))
        else:
            value = plan_value(state, controls, (0.0,) * horizon)
        candidate = (value, indices, controls)
        # Authored action order is the deterministic tie selector.
        if best is None or candidate[:2] < best[:2]:
            best = candidate
        if time.perf_counter_ns() - start > deadline_ns:
            return 0.0, (), math.nan, "deadline_fallback", time.perf_counter_ns() - start
    assert best is not None
    elapsed = time.perf_counter_ns() - start
    return best[2][0], best[2], best[0], "solved", elapsed


def run_episode(policy: str, horizon: Horizon, disturbance_history: tuple[float, ...],
                deadline_ns: int = 50_000_000) -> dict:
    state: State = INITIAL_STATE
    states = [state]
    decisions: list[Decision] = []
    for step, disturbance in enumerate(disturbance_history):
        requested = horizon.at(step)
        effective = requested
        try:
            action, plan, value, status, elapsed = solve(
                state, effective, policy == "finite_minimax", deadline_ns)
        except Exception:
            action, plan, value, status, elapsed = 0.0, (), None, "solver_failure_fallback", 0
        if status == "deadline_fallback":
            value = None
        fallback = status != "solved"
        if fallback:
            action = 0.0
        decisions.append(Decision(step, state, action, status, requested,
                                  effective, value, elapsed, plan, fallback))
        # Apply the current disturbance only after the action is committed.
        state = advance(state, action, disturbance)
        states.append(state)
    return {
        "policy": policy,
        "horizon": horizon.name,
        "disturbances": disturbance_history,
        "states": states,
        "decisions": [asdict(d) for d in decisions],
        "terminal_state": state,
        "terminal_original_objective": objective(state),
        "fallback_count": sum(d.fallback for d in decisions),
        "violations": 0,
        "completed": True,
    }


def histories() -> Iterable[tuple[float, ...]]:
    return itertools.product(DISTURBANCES, repeat=EPISODE_STEPS)


def fixture_fixed_plan_value(initial: tuple, action_sets: tuple[tuple, ...],
                             disturbance_sets: tuple[tuple, ...], transition: Callable,
                             score: Callable) -> int:
    values = []
    for plan in itertools.product(*action_sets):
        values.append(max(score(fixture_transition(initial, plan, suffix, transition))
                          for suffix in itertools.product(*disturbance_sets)))
    return min(values)


def fixture_transition(initial: tuple, plan: tuple, suffix: tuple, transition: Callable) -> tuple:
    state = initial
    for stage, (action, disturbance) in enumerate(zip(plan, suffix)):
        state = transition(stage, state, action, disturbance)
    return state


def run_fixture_loop(initial: tuple, action_sets: tuple[tuple, ...],
                     disturbance_sets: tuple[tuple, ...], transition: Callable,
                     score: Callable) -> dict[tuple, int]:
    output: dict[tuple, int] = {}
    for history in itertools.product(*disturbance_sets):
        state = initial
        for stage, realized in enumerate(history):
            candidates = []
            for plan in itertools.product(*action_sets[stage:]):
                worst = max(score(fixture_transition(state, plan, suffix, transition))
                            for suffix in itertools.product(*disturbance_sets[stage:]))
                candidates.append((worst, plan))
            _, chosen = min(candidates, key=lambda row: (row[0], row[1]))
            state = transition(stage, state, chosen[0], realized)
        output[history] = score(state)
    return output


def causal_fixture_value(initial: tuple, action_sets: tuple[tuple, ...],
                         disturbance_sets: tuple[tuple, ...], transition: Callable,
                         score: Callable) -> int:
    memo = {}
    def value(stage: int, state: tuple) -> int:
        if stage == len(action_sets):
            return score(state)
        key = (stage, state)
        if key not in memo:
            memo[key] = min(max(value(stage + 1, transition(stage, state, a, d))
                                for d in disturbance_sets[stage])
                            for a in action_sets[stage])
        return memo[key]
    return value(0, initial)


def check_policy_gap_fixtures() -> dict:
    # Exact authored fixtures in docs/research/finite-policy-class-reference.md.
    def vector_transition(_stage: int, state: tuple[int, int], action: int, disturbance: int) -> tuple[int, int]:
        x, y = state
        return (x + action + disturbance, x + y - disturbance)
    actions = ((0, 1), (-1, 1))
    disturbances = ((-1, 0, 1), (0,))
    cost = lambda state: state[0] ** 2 + state[1] ** 2
    fixed = fixture_fixed_plan_value((0, 0), actions, disturbances, vector_transition, cost)
    replanned = run_fixture_loop((0, 0), actions, disturbances, vector_transition, cost)
    causal = causal_fixture_value((0, 0), actions, disturbances, vector_transition, cost)
    assert (fixed, max(replanned.values()), causal) == (2, 2, 1)
    assert [replanned[(-1, 0)], replanned[(0, 0)], replanned[(1, 0)]] == [2, 1, 2]

    def scalar_transition(_stage: int, state: tuple[int], action: int, disturbance: int) -> tuple[int]:
        return (state[0] + action + disturbance,)
    scalar_actions = ((0,), (-1, 1))
    scalar_disturbances = ((-1, 1), (0,))
    absolute = lambda state: abs(state[0])
    scalar_fixed = fixture_fixed_plan_value((0,), scalar_actions, scalar_disturbances,
                                            scalar_transition, absolute)
    scalar_replanned = run_fixture_loop((0,), scalar_actions, scalar_disturbances,
                                        scalar_transition, absolute)
    assert scalar_fixed == 2
    assert scalar_replanned == {(-1, 0): 0, (1, 0): 0}
    return {
        "strict_two_step": {"fixed_plan_squared": fixed,
                            "executed_replanning_worst_squared": max(replanned.values()),
                            "causal_squared": causal,
                            "history_squared": {str(k): v for k, v in replanned.items()}},
        "scalar_two_step": {"fixed_plan": scalar_fixed,
                            "executed_replanning_worst": max(scalar_replanned.values()),
                            "history_costs": {str(k): v for k, v in scalar_replanned.items()}},
    }


def check_fallback_semantics() -> dict:
    # A zero budget deterministically expires every finite solve at its first plan.
    deadline_rows = [run_episode("nominal_zero_disturbance", SHRINKING, tuple(history), deadline_ns=0)
                     for history in histories()]
    assert all(row["fallback_count"] == EPISODE_STEPS for row in deadline_rows)
    assert all(all(d["status"] == "deadline_fallback" and d["action"] == 0.0
                   for d in row["decisions"]) for row in deadline_rows)
    original_solve = solve
    def fail_solve(*_args, **_kwargs):
        raise RuntimeError("injected fixture failure")
    globals()["solve"] = fail_solve
    try:
        failure_rows = [run_episode("finite_minimax", SHRINKING, tuple(history))
                        for history in histories()]
    finally:
        globals()["solve"] = original_solve
    assert all(row["fallback_count"] == EPISODE_STEPS for row in failure_rows)
    assert all(all(d["status"] == "solver_failure_fallback" and d["action"] == 0.0
                   for d in row["decisions"]) for row in failure_rows)
    return {"deadline": {"episodes": len(deadline_rows), "fallback_steps": sum(r["fallback_count"] for r in deadline_rows)},
            "solver_failure": {"episodes": len(failure_rows), "fallback_steps": sum(r["fallback_count"] for r in failure_rows)}}


def aggregate(rows: list[dict]) -> dict:
    values = [r["terminal_original_objective"] for r in rows]
    times = [d["solve_ns"] for r in rows for d in r["decisions"]]
    return {
        "episodes": len(rows), "completed_episodes": sum(r["completed"] for r in rows),
        "violations": sum(r["violations"] for r in rows),
        "fallback_steps": sum(r["fallback_count"] for r in rows),
        "worst_terminal_original_objective": max(values),
        "median_terminal_original_objective": statistics.median(values),
        "mean_terminal_original_objective": statistics.mean(values),
        "decision_count": len(times), "per_decision_latency_ns": times,
        "median_decision_latency_ns": statistics.median(times),
        "max_decision_latency_ns": max(times),
    }


def write_svg(path: Path, records: list[dict]) -> None:
    width, height = 1100, 710
    x0, y0, pw, ph = 90, 90, 900, 370
    colors = {"nominal_zero_disturbance": "#2878b5", "finite_minimax": "#ce5b31"}
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#222}.title{font-size:22px;font-weight:bold}.label{font-size:15px}.small{font-size:11px}.grid{stroke:#ddd}.axis{stroke:#333;stroke-width:1.3}</style>',
           '<text x="50" y="35" class="title">MaxCoordinateGame: finite closed-loop MPC comparison</text>',
           '<text x="50" y="58" class="small">4 scored steps · 16 complete disturbance histories per variant · source-derived 100-substep map</text>',
           f'<text x="{x0}" y="78" class="label">Phase plane (y,z), all executed history trajectories</text>']
    states = [s for r in records for s in r["states"]]
    ymin, ymax = min(s[1] for s in states), max(s[1] for s in states)
    zmin, zmax = min(s[2] for s in states), max(s[2] for s in states)
    dy, dz = max(ymax-ymin, 1e-9), max(zmax-zmin, 1e-9)
    ymin -= .08*dy; ymax += .08*dy; zmin -= .08*dz; zmax += .08*dz
    sx = lambda y: x0 + 50 + (y-ymin)/(ymax-ymin)*(pw-70)
    sy = lambda z: y0 + ph - 35 - (z-zmin)/(zmax-zmin)*(ph-60)
    svg += [f'<line x1="{x0+50}" y1="{y0+ph-35}" x2="{x0+pw}" y2="{y0+ph-35}" class="axis"/>',
            f'<line x1="{x0+50}" y1="{y0+10}" x2="{x0+50}" y2="{y0+ph-35}" class="axis"/>']
    for policy, color in colors.items():
        for row in (r for r in records if r["policy"] == policy):
            coords = " ".join(f'{sx(s[1]):.2f},{sy(s[2]):.2f}' for s in row["states"])
            dash = ' stroke-dasharray="5 3"' if row["horizon"] == MOVING.name else ""
            opacity = "0.16" if row["horizon"] == MOVING.name else "0.28"
            svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.3" stroke-opacity="{opacity}"{dash}/>')
        x_legend = 140 if policy.startswith("nominal") else 440
        label = "nominal; solid shrinking, dashed moving lookahead" if policy.startswith("nominal") else "finite minimax; solid shrinking, dashed moving lookahead"
        svg.append(f'<circle cx="{x_legend}" cy="490" r="4" fill="{color}"/>')
        svg.append(f'<text x="{x_legend+10}" y="494" class="small">{label}</text>')
    svg += [f'<text x="{x0+pw/2}" y="{y0+ph-4}" text-anchor="middle" class="small">y</text>',
            f'<text x="{x0+4}" y="{y0+15}" class="small">z</text>']
    # Timeline summaries span all histories for each controller under shrinking horizon.
    tx, ty, tw, th = 90, 535, 900, 150
    svg.append(f'<text x="{tx}" y="{ty-10}" class="label">Control and applied disturbance by step (all 16 histories)</text>')
    sx_t = lambda t: tx + 75 + t / EPISODE_STEPS * (tw-120)
    sy_u = lambda u: ty + 18 + (1-u)/2 * 58
    svg.append(f'<text x="{tx+5}" y="{ty+26}" class="small">u</text>')
    for val in (-1, 0, 1):
        y = sy_u(val)
        svg += [f'<line x1="{sx_t(0)}" y1="{y:.1f}" x2="{sx_t(EPISODE_STEPS)}" y2="{y:.1f}" class="grid"/>',
                f'<text x="{sx_t(0)-10}" y="{y+4:.1f}" text-anchor="end" class="small">{val}</text>']
    for k in range(EPISODE_STEPS):
        for policy, offset in (("nominal_zero_disturbance", -5), ("finite_minimax", 5)):
            subset = [r for r in records if r["policy"] == policy and r["horizon"] == SHRINKING.name]
            controls = [r["decisions"][k]["action"] for r in subset]
            x = sx_t(k + .5) + offset
            svg.append(f'<line x1="{x}" y1="{sy_u(min(controls)):.1f}" x2="{x}" y2="{sy_u(max(controls)):.1f}" stroke="{colors[policy]}" stroke-width="7" stroke-opacity="0.6"/>')
            svg.append(f'<circle cx="{x}" cy="{sy_u(statistics.median(controls)):.1f}" r="4" fill="{colors[policy]}"/>')
        svg.append(f'<text x="{tx+5}" y="{ty+106}" class="small">v</text>')
        # Each catalogue value is shown; duplicate histories are represented by count labels.
        values = [r["disturbances"][k] for r in records if r["policy"] == "nominal_zero_disturbance" and r["horizon"] == SHRINKING.name]
        x = sx_t(k + .5)
        for disturbance, label, xoff in ((-1.0, "−1 × 8", -18), (1.0, "+1 × 8", 18)):
            cy = ty + (100 if disturbance < 0 else 125)
            svg.append(f'<circle cx="{x+xoff:.1f}" cy="{cy}" r="4" fill="#555"/>')
            svg.append(f'<text x="{x+xoff:.1f}" y="{cy+14}" text-anchor="middle" class="small">{label}</text>')
    for k in range(EPISODE_STEPS+1):
        svg.append(f'<text x="{sx_t(k)}" y="{ty+th-2}" text-anchor="middle" class="small">{k}</text>')
    svg.append(f'<line x1="{sx_t(EPISODE_STEPS)}" y1="{ty+12}" x2="{sx_t(EPISODE_STEPS)}" y2="{ty+th-16}" stroke="#111" stroke-dasharray="5 4"/>')
    svg.append(f'<text x="{sx_t(EPISODE_STEPS)+8}" y="{ty+25}" class="small">scored endpoint</text>')
    svg.append('</svg>')
    path.write_text('\n'.join(svg), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture_evidence = check_policy_gap_fixtures()
    fallback_evidence = check_fallback_semantics()
    rows = []
    for policy in ("nominal_zero_disturbance", "finite_minimax"):
        for horizon in (SHRINKING, MOVING):
            for disturbance in histories():
                rows.append(run_episode(policy, horizon, tuple(disturbance)))
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(f"{row['policy']}::{row['horizon']}", []).append(row)
    report = {
        "schema": "csl.mpc04.max-coordinate-pilot/1",
        "source": {"repository": "imm-rl-lab/optimal_control", "commit": SOURCE_COMMIT,
                   "path": SOURCE_PATH, "blob": SOURCE_BLOB, "environment": "MaxCoordinateGame"},
        "source_model": {"state_order": ["time", "y", "z"], "initial_state": INITIAL_STATE,
                         "dt_seconds": DT, "inner_euler_steps": INNER_EULER_STEPS,
                         "dynamics": "y'=z+v; z'=-y+u", "terminal_objective": "max(abs(y),abs(z))"},
        "adaptation": {"episode_steps": EPISODE_STEPS, "controls": ACTIONS,
                       "disturbances": DISTURBANCES, "history_count": len(list(histories())),
                       "fixed_lookahead": FIXED_LOOKAHEAD,
                       "observation": "exact full state (time,y,z) before each action",
                       "missing_observation_policy": "unsupported; missing observations do not reveal or reconstruct hidden state",
                       "controller_reset": "fresh stateless policy and initial state per disturbance history",
                       "warm_start": "none; each finite enumeration restarts from its authored plan catalogue",
                       "decision_order": "observe full state; select u; apply current v; advance",
                       "moving_horizon_prediction": "source dynamics continue beyond scored episode endpoint",
                       "tie_selector": "minimize binary64 objective, then first plan in authored action order on exact equality",
                       "deadline_ns_per_decision": 50000000,
                       "fallback": "apply u=0 after timeout/solver failure, count the decision, continue the episode",
                       "stability_scope": "finite episode outcomes only; no recursive feasibility or stability theorem"},
        "objective": {"planning": "terminal squared max-coordinate objective; zero nominal disturbance or finite min-max",
                      "reported": "source terminal max(abs(y),abs(z))"},
        "scope": "finite-action, four-step source-derived adaptation; not a reproduction of the continuous-action four-second RL task; finite disturbance histories only",
        "fixtures": fixture_evidence,
        "fallback_fixtures": fallback_evidence,
        "variants": {key: aggregate(group) for key, group in grouped.items()},
        "episodes": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    write_svg(args.output / "trajectory.svg", rows)
    summary = {key: {k: v for k, v in value.items() if k != "per_decision_latency_ns"}
               for key, value in report["variants"].items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the optional SCIP B08 displayed-data formulations and save a report bundle."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
REPORT_ID = "mpc03-b08-l04-miQCP-v1"
OUTPUTS = ("solver-output.json", "independent-oracle.json", "record.json", "index.html", "disturbance-tube.svg")
SOURCE_SHA256 = "6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f"
ACTIONS = (0.6, 0.3, 0.0, -0.3, -0.6)
X0 = (1182.074, 119560.0, 459.832, 45260.0)
TARGET = (1200.0, 0.0, 450.0, 0.0)
B = (20.073, 0.0, -10.473, 0.0)
HORIZON = 4


def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unavailable"


def canonical_hash(value: object) -> str:
    packed = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(packed).hexdigest()


def step(state, action=0.0, disturbance=(0.0, 0.0)):
    x1, x2, x3, x4 = state
    w1, w2 = disturbance
    return (x1 + B[0] * action + w1,
            x2 - 25.0 * x1,
            x3 + B[2] * action - w2,
            x4 - 25.0 * x3)


def histories():
    result = []
    for signs in itertools.product((-1, 1), repeat=2 * HORIZON):
        disturbances = tuple((0.1 * (1 + t) * signs[2 * t],
                              0.1 * (1 + 3 * t) * signs[2 * t + 1])
                             for t in range(HORIZON))
        result.append((signs, disturbances))
    return result


def coefficient_data(scenarios):
    impacts = []
    for t in range(HORIZON):
        state = (0.0, 0.0, 0.0, 0.0)
        for stage in range(HORIZON):
            state = step(state, 1.0 if stage == t else 0.0)
        impacts.append(state)
    bases = []
    for _, disturbance in scenarios:
        state = X0
        for w in disturbance:
            state = step(state, 0.0, w)
        bases.append(state)
    return bases, impacts


def terminal_expression(base, impacts, controls, quicksum):
    return [base[k] + quicksum(impacts[t][k] * controls[t] for t in range(HORIZON))
            for k in range(4)]


def solve(kind, scenarios, bases, impacts):
    try:
        from pyscipopt import Model, quicksum, __version__ as pyscipopt_version
    except ImportError as error:
        raise RuntimeError("Install the optional PySCIPOpt 6.3.0 report dependency") from error

    model = Model(f"B08 L04 {kind}")
    model.hideOutput()
    model.setParam("limits/time", 300.0)
    model.setParam("parallel/maxnthreads", 1)
    selectors = []
    controls = []
    for t in range(HORIZON):
        if kind == "finite-miQCP":
            stage = [model.addVar(f"y_{t}_{j}", vtype="B") for j in range(len(ACTIONS))]
            model.addCons(quicksum(stage) == 1, name=f"one_action_{t}")
            selectors.append(stage)
            controls.append(quicksum(ACTIONS[j] * stage[j] for j in range(len(ACTIONS))) )
        else:
            controls.append(model.addVar(f"u_{t}", vtype="C",
                                         lb=min(ACTIONS), ub=max(ACTIONS)))
    epigraph = model.addVar("worst_squared_terminal_cost", vtype="C", lb=0.0)
    for scenario, base in enumerate(bases):
        terminal = terminal_expression(base, impacts, controls, quicksum)
        model.addCons(quicksum((terminal[k] - TARGET[k]) ** 2 for k in range(4)) <= epigraph,
                      name=f"disturbance_corner_{scenario}")
    model.setObjective(epigraph, "minimize")
    started = time.perf_counter_ns()
    model.optimize()
    elapsed = time.perf_counter_ns() - started
    status = str(model.getStatus())
    result = {
        "formulation": kind,
        "status": status,
        "elapsed_ns_single_capture": elapsed,
        "objective_squared": float(model.getObjVal()) if model.getNSols() else None,
        "global_dual_bound_squared": float(model.getDualbound()),
        "relative_gap": float(model.getGap()) if model.getNSols() else None,
        "node_count": int(model.getNNodes()),
        "solution_count": int(model.getNSols()),
        "limit_seconds": 300.0,
        "requested_threads": 1,
        "pyscipopt_version": pyscipopt_version,
        "scip_version": str(model.version()),
    }
    if model.getNSols():
        solution = model.getBestSol()
        if kind == "finite-miQCP":
            selector_values = [[float(model.getSolVal(solution, var)) for var in stage]
                               for stage in selectors]
            indices = [max(range(len(ACTIONS)), key=lambda j: selector_values[t][j])
                       for t in range(HORIZON)]
            result.update({"selector_values": selector_values,
                           "action_indices": indices,
                           "actions": [ACTIONS[j] for j in indices]})
        else:
            values = [float(model.getSolVal(solution, var)) for var in controls]
            result.update({"relaxed_controls": values,
                           "controls_are_catalogue_feasible": all(v in ACTIONS for v in values)})
    model.freeProb()
    return result


def norm_squared(state):
    return sum((state[k] - TARGET[k]) ** 2 for k in range(4))


def plan_worst(indices, scenarios):
    evaluated = []
    for signs, disturbance in scenarios:
        terminal = X0
        for t, w in enumerate(disturbance):
            terminal = step(terminal, ACTIONS[indices[t]], w)
        evaluated.append((norm_squared(terminal), signs, terminal))
    worst = max(row[0] for row in evaluated)
    return worst, [{"signs": list(signs), "terminal_state": list(terminal)}
                   for value, signs, terminal in evaluated if value == worst]


def projected_tube(indices):
    stages = []
    for stage_count in range(HORIZON + 1):
        points = []
        for signs in itertools.product((-1, 1), repeat=2 * stage_count):
            state = X0
            for t in range(stage_count):
                disturbance = (0.1 * (1 + t) * signs[2 * t],
                               0.1 * (1 + 3 * t) * signs[2 * t + 1])
                state = step(state, ACTIONS[indices[t]], disturbance)
            points.append([state[0], state[2]])
        stages.append({"stage": stage_count, "corner_history_count": len(points), "points": points})
    return stages


def run(args):
    scenarios = histories()
    bases, impacts = coefficient_data(scenarios)
    source = {
        "source_id": "L04",
        "source_sha256": SOURCE_SHA256,
        "state_dimension": 4,
        "horizon": HORIZON,
        "initial_state": list(X0),
        "target": list(TARGET),
        "input_vector": list(B),
        "actions_in_source_order": list(ACTIONS),
        "disturbance_bounds_by_stage": [[0.1 * (1 + t), 0.1 * (1 + 3 * t)] for t in range(HORIZON)],
        "model": "x1'=x1+20.073u+w1; x2'=x2-25x1; x3'=x3-10.473u-w2; x4'=x4-25x3",
        "cost": "min over one fixed finite control plan of the maximum Euclidean norm of the four-state terminal error",
        "assumptions": ["The printed decimal values are treated as exact by the rational reference.",
                        "The MIQCP receives binary64 coefficients.",
                        "The four-step model is unconstrained and linear."],
    }
    finite = solve("finite-miQCP", scenarios, bases, impacts)
    relaxed = solve("convex-control-QCP", scenarios, bases, impacts)
    oracle_script = ROOT / "docs/research/tools/check_b08_displayed_exact.py"
    saved_oracle = ROOT / "docs/research/evidence/b08-displayed-exact.json"
    oracle_result = subprocess.run([sys.executable, str(oracle_script)], check=True,
                                   capture_output=True, text=True)
    oracle = json.loads(oracle_result.stdout)
    if oracle != json.loads(saved_oracle.read_text(encoding="utf-8")):
        raise RuntimeError("independent exact B08 result differs from its frozen record")
    if finite.get("action_indices"):
        action_values = [str(Fraction(str(ACTIONS[i])))
                         for i in finite["action_indices"]]
        if action_values not in oracle["exact_minimizers"]:
            raise RuntimeError("MIQCP plan is not an exact displayed-data minimizer")
        if abs(finite["objective_squared"] - float(Fraction(oracle["minimum_squared_exact"]))) > 1e-6:
            raise RuntimeError("MIQCP objective differs from the independent exact oracle")
    upper = float(Fraction(oracle["minimum_squared_exact"]))
    lower = relaxed["global_dual_bound_squared"]
    if relaxed["status"] == "optimal" and lower > upper + 1e-6:
        raise RuntimeError("convex-control lower bound exceeds the exact finite optimum")
    if relaxed.get("relaxed_controls"):
        controls = relaxed["relaxed_controls"]
        # Re-evaluate the relaxed control on each independently generated corner row.
        states = []
        for base in bases:
            terminal = tuple(base[k] + sum(impacts[t][k] * controls[t] for t in range(HORIZON))
                             for k in range(4))
            states.append(sum((terminal[k] - TARGET[k]) ** 2 for k in range(4)))
        direct_cost = max(states)
        relaxed["direct_corner_cost_squared"] = direct_cost
        relaxed["direct_cost_matches_solver_within_1e-6"] = (
            relaxed["objective_squared"] is not None and
            abs(direct_cost - relaxed["objective_squared"]) <= 1e-6 * max(1.0, direct_cost))
    solver_output = {"schema": "csl.mpc03-b08-solver-output/1",
                     "scenario_sha256": canonical_hash(source),
                     "disturbance_history_count": len(scenarios),
                     "finite_miqcp": finite,
                     "convex_control_qcp": relaxed,
                     "timing_scope": "one exploratory solve per formulation; no performance comparison",
                     "warmups": 0,
                     "attempt_count_per_formulation": 1,
                     "thread_limit": 1}
    source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   check=True, capture_output=True, text=True).stdout.strip()
    driver_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    solver_output["source_commit"] = source_commit
    solver_output["driver_path"] = driver_path
    solver_output["driver_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    solver_output["environment"] = {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "machine": platform.machine(), "logical_cpus": os.cpu_count(),
        "cpu_model": cpu_model(),
        "memory_limit": "not enforced for this local exploratory capture",
        "solver_threads": 1,
    }
    record = {
        "schema": "csl.mpc03-b08-miQCP-record/1",
        "case_id": "b08-l04-displayed-rounded-open-loop",
        "scope": "Four-step open-loop finite-action minimax on L04 printed linear data, with a continuous-control convex-hull lower-bound relaxation.",
        "limits": ["The original unrounded arrays and historical generator are unavailable.",
                   "The rational oracle treats printed decimals as exact; SCIP receives binary64 coefficients.",
                   "No nonlinear trajectory, historical reproduction, or solver-speed comparison is claimed."],
        "source_commit": source_commit,
        "scenario": source,
        "scenario_sha256": canonical_hash(source),
        "solver_output_sha256": None,
        "oracle_sha256": None,
        "result": None,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "solver-output.json").write_text(json.dumps(solver_output, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "independent-oracle.json").write_text(json.dumps(oracle, indent=2) + "\n", encoding="utf-8")
    record["solver_output_sha256"] = hashlib.sha256((args.output_dir / "solver-output.json").read_bytes()).hexdigest()
    record["oracle_sha256"] = hashlib.sha256((args.output_dir / "independent-oracle.json").read_bytes()).hexdigest()
    record["result"] = {
        "finite": finite,
        "relaxation": relaxed,
        "exact_reference": oracle,
        "exact_minimizing_action_indices": [
            [next(index for index, action in enumerate(ACTIONS)
                  if Fraction(str(action)) == Fraction(value)) for value in plan]
            for plan in oracle["exact_minimizers"]
        ],
        "bounds_squared": {"lower": lower, "upper": upper, "lower_le_upper": lower <= upper + 1e-6},
        "bound_scope": "continuous action interval yields a numerical lower bound; exact finite enumeration supplies the feasible upper bound",
        "no_speed_claim": True,
    }
    if finite.get("action_indices"):
        worst, worst_corners = plan_worst(finite["action_indices"], scenarios)
        record["result"]["worst_cost_corners"] = worst_corners
        record["result"]["plan_worst_squared_cost_binary64"] = worst
        record["result"]["projected_tube"] = projected_tube(finite["action_indices"])
        record["result"]["projected_target_x1_x3"] = [TARGET[0], TARGET[2]]
    (args.output_dir / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    from b08_report import render_html, render_svg
    (args.output_dir / "index.html").write_text(render_html(record), encoding="utf-8")
    (args.output_dir / "disturbance-tube.svg").write_text(render_svg(record), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "reports/algorithm-results" / REPORT_ID)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

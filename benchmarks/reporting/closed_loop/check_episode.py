"""Independent fixed-RK4 and physical-cost check for one completed episode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from check_replay import independent_cost, rk4_step
from contracts import canonical_sha256, manifest_sha256
from task_models import objective


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    task, controls = data["task"], data["controls"]
    if manifest_sha256(task) != data["task_sha256"]:
        raise ValueError("checker input task hash does not match the original task")
    if canonical_sha256(controls) != data["controls_sha256"]:
        raise ValueError("checker input controls differ from the executed control history")
    if len(controls) != task["episode"]["intervals"]:
        raise ValueError("checker requires the complete original fixed horizon")
    sub = data["report_subintervals_per_hold"]
    replay_states = np.asarray(data["replay_physical_states"], dtype=float)
    if replay_states.ndim != 2 or replay_states.shape[0] != task["episode"]["intervals"] * sub + 1:
        raise ValueError("checker replay has an incomplete report grid")
    endpoints = replay_states[np.arange(task["episode"]["intervals"] + 1) * sub]
    source = data["scenario"]
    source_steps = task["source"].get("execution_profile", {}).get("substeps_per_source_hold", 100)
    x = np.asarray([state["initial"] for state in task["model"]["states"]], dtype=float).tolist()
    fixed = [x[:]]; h = task["episode"]["dt"] / source_steps
    for control in controls:
        for _ in range(source_steps):
            x = rk4_step(task["model"]["case_id"], source["parameters"], x, control, h)
        fixed.append(x[:])
    fixed = np.asarray(fixed)
    costs = independent_cost(task, endpoints.tolist(), controls, source)
    adapter_cost = objective(task, endpoints, controls)
    bounds = task["control_domains"]["continuous"]["bounds"]
    u = np.asarray(controls, dtype=float)
    control_violation = np.maximum(np.maximum(np.asarray(bounds)[:, 0] - u.min(axis=0),
                                               u.max(axis=0) - np.asarray(bounds)[:, 1]), 0)
    state_violation = []; endpoint_state_violation = []
    for index, state in enumerate(task["model"]["states"]):
        bound = state["bounds"]
        violation = 0.0 if bound is None else float(max(
            np.max(np.maximum(bound[0] - endpoints[:, index], 0)),
            np.max(np.maximum(endpoints[:, index] - bound[1], 0))))
        full_violation = 0.0 if bound is None else float(max(
            np.max(np.maximum(bound[0] - replay_states[:, index], 0)),
            np.max(np.maximum(replay_states[:, index] - bound[1], 0))))
        endpoint_state_violation.append(violation); state_violation.append(full_violation)
    domain = {"minimum_radius_km": float(replay_states[:, 0].min()),
              "positive_radius": bool(replay_states[:, 0].min() > 0)} if "ORBIT" in task["model"]["case_id"] else {}
    out = {"schema": "csl.closed-loop.independent-episode-check/1", "status": "complete",
        "task_sha256": data["task_sha256"], "controls_sha256": data["controls_sha256"],
        "hold_endpoint_max_abs_difference_from_applied_execution": np.max(
            np.abs(endpoints - np.asarray(data["applied_hold_endpoints"])), axis=0).tolist(),
        "independent_objective": costs, "task_adapter_objective": adapter_cost,
        "objective_difference": abs(costs["total"] - adapter_cost["total"]),
        "sampled_physical_state_bound_violation_by_coordinate": state_violation,
        "hold_endpoint_state_bound_violation_by_coordinate": endpoint_state_violation,
        "sampled_state_count": int(len(replay_states)),
        "sampled_state_scope": "CSL replay initial state and report samples, including 20 samples per original hold; numerical diagnostics only",
        "control_bound_violation_by_coordinate": control_violation.tolist(), "model_domain": domain,
        "fixed_rk4": {"substeps_per_original_interval": source_steps,
            "hold_endpoint_max_abs_difference_from_CSL": np.max(np.abs(fixed - endpoints), axis=0).tolist(),
            "physical_objective": independent_cost(task, fixed.tolist(), controls, source),
            "method": "separately transcribed classical fixed-step RK4; numerical diagnostic only"}}
    args.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": out["status"], "task_sha256": out["task_sha256"],
        "objective_difference": out["objective_difference"],
        "fixed_rk4_endpoint_difference": out["fixed_rk4"]["hold_endpoint_max_abs_difference_from_CSL"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

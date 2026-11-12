"""Build a source-bound native H-tube request from the frozen LV task."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contracts import ROOT, load_task, manifest_sha256
from task_models import prediction_receipt, source_scenario


LOTKA_TASK = "syn-nl-lv-01"
SAVED_NMPC = Path(
    "reports/closed-loop-pilot/closed-loop-pilot-v1/raw/attempts/syn-nl-lv-01/"
    "syn-nl-lv-01-20261111T114908Z-8dc20bed/attempt.json"
)
SAVED_NMPC_SHA256 = "1170640f63491a70ce30a06e8b07f0da6e1426e8a610effebc9dfc38a32fb7ce"
SAVED_NMPC_TASK_SHA256 = "520ab0f686c4c33efd7ecc2aebdf73735e528e1ae410e42224b82e7200769cec"


def build_request(task: dict | None = None) -> dict:
    """Return complete physical-coordinate inputs for the geometry-only C++ runner."""
    task = load_task(LOTKA_TASK) if task is None else task
    if task.get("task_id") != "syn-nl-lv-01/continuous-receding/1":
        raise ValueError("the first full-state tube capture is bound to the original Lotka task")
    if task["model"]["model_id"] != "syn-nl-lv-01/ode/1":
        raise ValueError("Lotka source plant identity changed")
    if task["prediction"]["affine_model_id"] != "syn-nl-lv-01/frozen-coexistence-affine/1":
        raise ValueError("Lotka frozen-affine predictor identity changed")
    if task["control_domains"]["continuous"]["semantics"] != \
            "independent admissible control at every physical interval":
        raise ValueError("source continuous control domain does not describe all admissible holds")
    if task["terminal_condition"] != {
            "kind": "physical-state-bounds", "objective_target_is_feasibility_constraint": False}:
        raise ValueError("the physical terminal bounds and soft objective target must stay distinct")

    receipt = prediction_receipt(task)
    task_sha = manifest_sha256(task)
    scenario = source_scenario(task)
    count = task["episode"]["intervals"]
    dt = task["episode"]["dt"]
    if count != 30 or dt != 0.1 or task["episode"]["final_time"] != 3:
        raise ValueError("the original 30-stage 0.1-day task grid is required")
    if receipt["task_sha256"] != task_sha or receipt["source_model_sha256"] != task["source"]["sha256"]:
        raise ValueError("prediction receipt is not bound to the task and source scenario")
    physical = receipt["physical_coefficients"]
    if not isinstance(physical, list) or len(physical) != count:
        raise ValueError("prediction receipt must include every original physical affine stage")

    state_coordinates = []
    for row in task["model"]["states"]:
        bounds = row.get("bounds")
        if bounds is None or len(bounds) != 2:
            raise ValueError("the Lotka geometry profile requires explicit physical state bounds")
        state_coordinates.append({
            "name": row["name"], "unit": row["unit"], "scale": row["scale"],
            "initial": row["initial"], "bounds": list(bounds),
        })
    control_coordinates = []
    for row in task["model"]["controls"]:
        bounds = row.get("bounds")
        if bounds is None or len(bounds) != 2:
            raise ValueError("the Lotka continuous profile requires explicit physical control bounds")
        control_coordinates.append({"name": row["name"], "unit": row["unit"], "bounds": list(bounds)})
    if task["control_domains"]["continuous"]["bounds"] != [row["bounds"] for row in control_coordinates]:
        raise ValueError("continuous action profile does not match the source actuator bounds")

    for stage in physical:
        a, b, offset = stage.get("A"), stage.get("B"), stage.get("c")
        n, m = len(state_coordinates), len(control_coordinates)
        if len(a) != n or any(len(row) != n for row in a) or \
                len(b) != n or any(len(row) != m for row in b) or len(offset) != n:
            raise ValueError("physical affine coefficient shape differs from source coordinates")

    # Keep every source cost term verbatim for identity and interpretation. The
    # tube computation consumes no objective and never invokes a cost optimizer.
    return {
        "schema": "csl.nominal-h-tube-input/1",
        "source": {
            "task_id": task["task_id"], "task_sha256": task_sha,
            "source_case_id": task["source"]["case_id"],
            "source_model_id": task["source"]["model_id"],
            "source_scenario_path": task["source"]["path"],
            "source_scenario_sha256": task["source"]["sha256"],
            "plant_model_id": task["model"]["model_id"],
            "predictor_model_id": task["prediction"]["affine_model_id"],
            "predictor_producer": receipt["producer"],
            "prediction_receipt": receipt,
        },
        "profile": {
            "action_profile_id": task["control_domains"]["continuous"]["problem_id"],
            "action_profile": "continuous_box_all_admissible_controls",
            "forward_role": task["roles"]["forward_reachability"],
            "backward_role": task["roles"]["backward_feasibility"],
            "assurance": receipt["coefficient_assurance"],
            "optimizer_selection": "not_used",
            "optimizer_reason": "This capture computes full-state geometry only; it does not select or optimize controls.",
        },
        "time": {
            "unit": task["episode"]["time_unit"], "dt": dt,
            "intervals": count, "final_time": task["episode"]["final_time"],
            "grid": [k * dt for k in range(count + 1)],
        },
        "state_coordinates": state_coordinates,
        "control_coordinates": control_coordinates,
        "initial_state": [row["initial"] for row in state_coordinates],
        "state_constraints": [row["bounds"] for row in state_coordinates],
        "control_constraints": [row["bounds"] for row in control_coordinates],
        "terminal_feasibility": {
            "kind": "physical-state-bounds",
            "bounds": [row["bounds"] for row in state_coordinates],
            "source": "original task model physical state bounds",
        },
        "objective_metadata": {
            "objective_id": task["objective"]["objective_id"],
            "source_objective": task["objective"],
            "soft_terminal_target": task["objective"]["source_definition"]["terminal_target"],
            "physical_terminal_feasibility_is_soft_target": False,
            "optimizer_selection": "not_used",
        },
        "physical_coefficients": physical,
        "scaled_coefficients_for_audit_only": receipt["scaled_coefficients"],
        "coefficient_scope": receipt["validity"],
        "coefficient_producer_receipt": {
            key: receipt[key] for key in (
                "discretization_method", "coefficient_assurance", "linearization_receipt",
                "discretization_receipt", "source_model_sha256")
        },
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_saved_nmpc(root: Path = ROOT) -> dict:
    """Read the fixed saved continuous NMPC record and verify its known hashes."""
    path = root / SAVED_NMPC
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SAVED_NMPC_SHA256:
        raise ValueError("saved Lotka NMPC record hash differs from the source-bound record")
    value = json.loads(raw)
    if value.get("task_sha256") != SAVED_NMPC_TASK_SHA256:
        raise ValueError("saved Lotka NMPC task hash differs from the source-bound task")
    if value.get("model_id") != "syn-nl-lv-01/ode/1":
        raise ValueError("saved NMPC trajectory must retain the original nonlinear plant identity")
    return {"path": SAVED_NMPC.as_posix(), "sha256": digest, "record": value}

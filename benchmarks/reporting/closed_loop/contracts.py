"""Load source-bound closed-loop task contracts and preserve their identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "docs/contracts/closed-loop"
def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_task(task_id: str) -> dict:
    path = CONTRACTS / f"{task_id}.json"
    task = json.loads(path.read_text())
    validate_task(task)
    expected = (CONTRACTS / f"{task_id}.sha256").read_text().split()[0]
    if manifest_sha256(task) != expected:
        raise ValueError("canonical task manifest hash mismatch")
    return task


def validate_task(task: dict) -> None:
    if task.get("schema") != "csl.closed-loop.task/1":
        raise ValueError("unsupported closed-loop task schema")
    model = task["model"]
    episode = task["episode"]
    controls = model["controls"]
    states = model["states"]
    n = episode["intervals"]
    if not task["task_id"] or not model["model_id"] or not task["objective"]["objective_id"]:
        raise ValueError("task, model and objective identities are required")
    names = [field["name"] for field in states + controls]
    if len(names) != len(set(names)):
        raise ValueError("state and control coordinate names must be unique")
    expected_shape = {"SYN-NL-LV-01": (2, 1), "SYN-NL-FUEL-01": (4, 2),
                      "ENV717-EARTH-ORBIT-CONTINUOUS-01": (4, 2)}.get(model["case_id"])
    if expected_shape is None or (len(states), len(controls)) != expected_shape:
        raise ValueError("state and control dimensions do not match the task identity")
    for field in states + controls:
        if not field["unit"]:
            raise ValueError("coordinate units are required")
        bounds = field.get("bounds")
        if bounds is not None and (len(bounds) != 2 or bounds[0] > bounds[1]):
            raise ValueError("coordinate bounds must be ordered pairs")
    if any(not field.get("scale", 1) > 0 for field in states):
        raise ValueError("state scales must be positive")
    for field in states:
        bounds = field.get("bounds")
        if bounds is not None and not bounds[0] <= field["initial"] <= bounds[1]:
            raise ValueError(f"initial state {field['name']} is outside its physical bounds")
    if n <= 0 or episode["dt"] <= 0 or abs(episode["final_time"] - n * episode["dt"]) > 1e-12:
        raise ValueError("time grid must reach the fixed final time")
    protocol = episode["closed_loop"]
    if protocol != {
        "observation": "exact-full-execution-state",
        "players": 1,
        "second_player": False,
        "optimization_horizon": "shrinking-to-fixed-terminal",
        "apply": "first-zero-order-held-input",
        "warm_start": "shift-prior-primal-drop-applied-stage-no-terminal-repeat;zero-duals",
        "failure": "stop-before-next-input-no-fallback",
    }:
        raise ValueError("unsupported closed-loop information or timing protocol")
    if task["source"]["sha256"] != source_sha256(task):
        raise ValueError("source manifest hash mismatch")
    if task["source"].get("model_id", model["model_id"]) != model["model_id"]:
        raise ValueError("source and task model identities differ")
    domains = task["control_domains"]
    if domains["continuous"]["problem_id"] == domains["finite"]["problem_id"]:
        raise ValueError("continuous and finite control adaptations need distinct identities")
    if domains["continuous"]["bounds"] != [field["bounds"] for field in controls]:
        raise ValueError("continuous action bounds must match the physical actuator declarations")
    for action in domains["finite"]["actions"]:
        if len(action) != len(controls):
            raise ValueError("finite action has the wrong control dimension")
        if any(field["bounds"] is not None and not field["bounds"][0] <= value <= field["bounds"][1]
               for field, value in zip(controls, action)):
            raise ValueError("finite action lies outside physical actuator bounds")
    if task["roles"]["forward_reachability"] != "all-admissible-control-family":
        raise ValueError("forward reachability role must cover all admissible controls")
    terminal_kind = task["terminal_condition"]["kind"]
    backward_role = task["roles"]["backward_feasibility"]
    if model["case_id"] in {"SYN-NL-LV-01", "SYN-NL-FUEL-01"}:
        if terminal_kind != "physical-state-bounds" or backward_role != "predecessors-of-terminal-physical-state-bounds":
            raise ValueError("synthetic-task terminal feasibility must use its physical state bounds")
    elif terminal_kind != "positive-radius-model-domain" or backward_role != "predecessors-of-terminal-model-domain-r-positive":
        raise ValueError("orbit backward feasibility must name its actual model domain")
    if task["terminal_condition"]["objective_target_is_feasibility_constraint"]:
        raise ValueError("the soft objective target is not a hard terminal constraint")
    if task["roles"]["policy_trajectory"] != "one-deterministic-policy-trajectory":
        raise ValueError("a policy trajectory cannot be identified as a set")


def source_sha256(task: dict) -> str:
    source = task["source"]
    if source["kind"] == "mpc11-scenario":
        value = json.loads((ROOT / source["path"]).read_text())
        return canonical_sha256(value)
    if source["kind"] == "earth-orbit-source-file":
        return hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest()
    raise ValueError("unknown source kind")


def manifest_sha256(task: dict) -> str:
    return canonical_sha256(task)

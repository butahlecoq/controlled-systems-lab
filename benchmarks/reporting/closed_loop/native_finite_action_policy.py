"""Source-bound native finite-action receding-horizon policy adapter.

The adapter keeps one JSONL native process alive for an episode. It uses the
source task's finite action adaptation and affine prediction receipt; applied
controls are still executed and checked by the common independent plant runner.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any

from contracts import manifest_sha256
from task_models import prediction_receipt, validate_source_binding


def _positive_limit(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _representation(controller_id: str) -> tuple[str, int]:
    names = {"exact_polytope": 0, "box": 1, "zonotope": 2,
             "parallelotope": 3, "ellipsoid": 4}
    requested = os.environ.get("CSL_NATIVE_FINITE_ACTION_REPRESENTATION")
    if requested is None:
        for name in names:
            if controller_id.endswith("/" + name) or controller_id.endswith(":" + name):
                requested = name
                break
    requested = requested or "exact_polytope"
    if requested not in names:
        raise ValueError(f"unsupported native finite-action representation {requested!r}")
    return requested, names[requested]


def _terminal_objective(task: dict[str, Any]) -> dict[str, Any]:
    dimension = len(task["model"]["states"])
    if task["objective"]["kind"] == "dimensionless-quadratic":
        spec = task["objective"]["source_definition"]
        target = spec["terminal_target"]
        scales = spec["terminal_scale"]
        weights = spec["terminal_weights"]
        q = [[0.0] * dimension for _ in range(dimension)]
        linear = [0.0] * dimension
        offset = 0.0
        for i, (target_i, scale, weight) in enumerate(zip(target, scales, weights)):
            q[i][i] = 2.0 * weight / (scale * scale)
            linear[i] = -2.0 * weight * target_i / (scale * scale)
            offset += weight * (target_i / scale) ** 2
        return {"kind": "quadratic", "Q": q, "linear": linear, "offset": offset}
    if task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        target = task["objective"]["target"]
        return {"kind": "euclidean", "map": [[1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 100000.0]],
            "target": [target["radius_km"], 100000.0 * target["angular_rate_rad_s"]],
            "weights": []}
    raise ValueError("source objective has no native finite-action terminal lowering")


def _running_cost(task: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    n = task["episode"]["intervals"]
    objective = task["objective"]
    case = task["model"]["case_id"]
    stages: list[dict[str, Any]] = []
    if objective["kind"] == "dimensionless-quadratic":
        source = objective["source_definition"]
        references = receipt.get("reference_inputs", receipt.get("input_references"))
        if len(references) != n:
            raise ValueError("source prediction receipt has the wrong full-horizon input references")
        for stage in range(n):
            if isinstance(source["running_reference"], str):
                reference = references[stage]
            else:
                reference = source["running_reference"]
            stages.append({"stage": stage, "terms": [{
                "kind": "quadratic", "reference": reference,
                "scales": source["running_scale"],
                "weights": [1.0] * len(reference),
                "coefficient": source["running_weight"]}]})
    elif case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        for stage in range(n - 1):
            stages.append({"stage": stage, "terms": [{
                "kind": "euclidean", "map": [[1.0, 0.0], [0.0, 1.0]],
                "offset": [0.0, 0.0], "coefficient": 0.001 * task["episode"]["dt"]}]})
    else:
        raise ValueError("source objective has no native finite-action running-cost lowering")
    return {"objective_id": objective["objective_id"], "stages": stages}


def _native_request(task: dict[str, Any], task_sha256: str, controller_id: str,
                    action_profile_id: str, observed_state: list[float], stage: int,
                    representation_index: int, receipt: dict[str, Any]) -> dict[str, Any]:
    n = task["episode"]["intervals"]
    physical = receipt["physical_coefficients"]
    full_stages = physical if isinstance(physical, list) else [physical] * n
    if len(full_stages) != n:
        raise ValueError("prediction receipt must describe every absolute update")
    predictor_stages = [{"A": row["A"], "B": row["B"], "c": row.get("c", row.get("offset"))}
                        for row in full_stages[stage:]]
    if any(row["c"] is None for row in predictor_stages):
        raise ValueError("prediction receipt is missing an affine offset")
    return {
        "schema": "csl.closed-loop.native-policy-query/1",
        "task_id": task["task_id"], "task_sha256": task_sha256,
        "source_model_id": task["model"]["model_id"],
        "controller_id": controller_id, "action_profile_id": action_profile_id,
        "problem_id": task["control_domains"]["finite"]["problem_id"] + f"/update-{stage}",
        "request_id": f"{controller_id}/update-{stage}",
        "absolute_update_index": stage, "observed_physical_state": observed_state,
        "original_horizon": n, "dt": task["episode"]["dt"],
        "predictor_model_id": receipt["model_id"], "predictor_assurance": receipt["coefficient_assurance"],
        "predictor_stages": predictor_stages,
        "actions": task["control_domains"]["finite"]["actions"],
        "state_bounds": [row["bounds"] for row in task["model"]["states"]],
        "terminal_objective": _terminal_objective(task),
        "running_cost": _running_cost(task, receipt),
        "representation_index": representation_index,
        "representation_name": _representation(controller_id)[0],
        "search_policy": "stage-layered-backward-viability" if representation_index == 0 else "fixed-plan-mpc",
        "limits": {"max_plans": _positive_limit("CSL_NATIVE_MAX_PLANS", 4096),
                   "max_points_per_stage": _positive_limit("CSL_NATIVE_MAX_POINTS", 10000),
                   "max_score_evaluations": _positive_limit("CSL_NATIVE_MAX_SCORES", 10000),
                   "max_generators_per_stage": _positive_limit("CSL_NATIVE_MAX_GENERATORS", 512),
                   "max_beam_width": _positive_limit("CSL_NATIVE_GRAPH_BEAM_WIDTH", 16),
                   "max_graph_nodes": _positive_limit("CSL_NATIVE_GRAPH_MAX_NODES", 2048)},
    }


class NativeFiniteActionPolicy:
    def __init__(self, task: dict[str, Any], *, task_sha256: str,
                 controller_id: str, action_profile_id: str) -> None:
        validate_source_binding(task)
        if manifest_sha256(task) != task_sha256:
            raise ValueError("native controller received a different source-bound task")
        expected_action_id = task["control_domains"]["finite"]["problem_id"]
        if action_profile_id != expected_action_id:
            raise ValueError("native finite-action policy needs the task's distinct finite-action profile")
        executable = os.environ.get("CSL_CLOSED_LOOP_NATIVE_POLICY_BRIDGE")
        if not executable:
            raise ValueError("set CSL_CLOSED_LOOP_NATIVE_POLICY_BRIDGE to the built csl_closed_loop_native_policy executable")
        path = Path(executable).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("native policy bridge path is not a file")
        self.task = task
        self.task_sha256 = task_sha256
        self.controller_id = controller_id
        self.action_profile_id = action_profile_id
        self.representation, self.representation_index = _representation(controller_id)
        self.receipt = prediction_receipt(task)
        self.process = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def query(self, task_id: str, observed_physical_state: list[float], absolute_update_index: int) -> dict[str, Any]:
        if task_id != self.task["task_id"]:
            raise ValueError("native controller query task identity changed")
        n = self.task["episode"]["intervals"]
        if not isinstance(absolute_update_index, int) or not 0 <= absolute_update_index < n:
            raise ValueError("native controller update index is outside the physical episode")
        state = [float(value) for value in observed_physical_state]
        if len(state) != len(self.task["model"]["states"]) or not all(math.isfinite(value) for value in state):
            raise ValueError("observed state has the wrong dimension or a nonfinite coordinate")
        request = _native_request(self.task, self.task_sha256, self.controller_id,
            self.action_profile_id, state, absolute_update_index, self.representation_index, self.receipt)
        if self.process.poll() is not None or self.process.stdin is None or self.process.stdout is None:
            return {"status": "failed", "task_sha256": self.task_sha256,
                    "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                    "invocations": [], "reason": "native policy bridge exited before query"}
        try:
            self.process.stdin.write(json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("native policy bridge closed its output")
            response = json.loads(line)
        except (BrokenPipeError, OSError, ValueError, RuntimeError) as error:
            return {"status": "failed", "task_sha256": self.task_sha256,
                    "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                    "invocations": [], "reason": str(error)}
        response["task_sha256"] = self.task_sha256
        response["task_id"] = task_id
        response["action_profile_id"] = self.action_profile_id
        response.setdefault("policy_id", self.controller_id)
        response.setdefault("invocations", [])
        if response.get("status") == "accepted":
            semantics = response.get("selector", {}).get("policy_semantics",
                "nominal receding-horizon fixed-plan MPC")
            response["policy_semantics"] = semantics
            response["prediction_profile"] = {"model_id": self.receipt["model_id"],
                "assurance": self.receipt["coefficient_assurance"],
                "validity": self.receipt["validity"], "representation": self.representation,
                "policy_semantics": semantics}
        return response

    def close(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.wait(timeout=5)
        if self.process.stderr:
            self.process.stderr.close()


def create_policy(task: dict[str, Any], *, task_sha256: str,
                  controller_id: str, action_profile_id: str) -> NativeFiniteActionPolicy:
    return NativeFiniteActionPolicy(task, task_sha256=task_sha256,
        controller_id=controller_id, action_profile_id=action_profile_id)

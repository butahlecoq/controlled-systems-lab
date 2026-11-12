"""Source-bound native finite-action receding-horizon policy adapter.

The adapter keeps one JSONL native process alive for an episode. It uses the
source task's finite action adaptation and affine prediction receipt; applied
controls are still executed and checked by the common independent plant runner.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from contracts import manifest_sha256
from task_models import prediction_receipt, validate_source_binding


def _reject_nonstandard_number(token: str):
    raise ValueError(f"native bridge response contains nonstandard JSON number {token}")


def _positive_limit(name: str, default: int,
                    factory_options: Mapping[str, object] | None = None) -> int:
    option = {
        "CSL_NATIVE_MAX_PLANS": "max_plans",
        "CSL_NATIVE_MAX_POINTS": "max_points_per_stage",
        "CSL_NATIVE_MAX_SCORES": "max_score_evaluations",
        "CSL_NATIVE_MAX_GENERATORS": "max_generators_per_stage",
        "CSL_NATIVE_GRAPH_BEAM_WIDTH": "max_beam_width",
        "CSL_NATIVE_GRAPH_MAX_NODES": "max_graph_nodes",
    }[name]
    declared_limits = factory_options.get("limits") if factory_options is not None else None
    if declared_limits is not None:
        if not isinstance(declared_limits, Mapping) or option not in declared_limits:
            raise ValueError(f"factory_options.limits must provide {option}")
        value = int(declared_limits[option])
        if value <= 0:
            raise ValueError(f"factory_options.limits.{option} must be positive")
        return value
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _representation(controller_id: str,
                    factory_options: Mapping[str, object] | None = None) -> tuple[str, int]:
    names = {"exact_polytope": 0, "box": 1, "zonotope": 2,
             "parallelotope": 3, "ellipsoid": 4}
    requested = (str(factory_options["representation"]) if factory_options is not None and
        "representation" in factory_options else os.environ.get("CSL_NATIVE_FINITE_ACTION_REPRESENTATION"))
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
                    representation_index: int, receipt: dict[str, Any],
                    factory_options: Mapping[str, object] | None = None) -> dict[str, Any]:
    n = task["episode"]["intervals"]
    physical = receipt["physical_coefficients"]
    full_stages = physical if isinstance(physical, list) else [physical] * n
    if len(full_stages) != n:
        raise ValueError("prediction receipt must describe every absolute update")
    predictor_stages = [{"A": row["A"], "B": row["B"], "c": row.get("c", row.get("offset"))}
                        for row in full_stages[stage:]]
    if any(row["c"] is None for row in predictor_stages):
        raise ValueError("prediction receipt is missing an affine offset")
    request = {
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
        "representation_name": _representation(controller_id, factory_options)[0],
        "limits": {"max_plans": _positive_limit("CSL_NATIVE_MAX_PLANS", 4096, factory_options),
                   "max_points_per_stage": _positive_limit("CSL_NATIVE_MAX_POINTS", 10000, factory_options),
                   "max_score_evaluations": _positive_limit("CSL_NATIVE_MAX_SCORES", 10000, factory_options),
                   "max_generators_per_stage": _positive_limit("CSL_NATIVE_MAX_GENERATORS", 512, factory_options),
                   "max_beam_width": _positive_limit("CSL_NATIVE_GRAPH_BEAM_WIDTH", 16, factory_options),
                   "max_graph_nodes": _positive_limit("CSL_NATIVE_GRAPH_MAX_NODES", 2048, factory_options)},
    }
    if representation_index == 0:
        request["search_policy"] = "stage-layered-backward-viability"
        if factory_options:
            required = ("reachable_set_method", "hull_provider", "vertex_lp_provider",
                        "conversion_provider", "checker_budget", "control_optimizer")
            missing = [key for key in required if key not in factory_options]
            if missing:
                raise ValueError("factory_options is missing selected graph roles: " + ", ".join(missing))
        else:
            reachable_id = os.environ.get("CSL_NATIVE_REACHABLE_SET_METHOD", "csl.geometry.affine-sum")
            source_index = reachable_id == "csl.geometry.affine-sum.source-index"
            request.update({
                "reachable_set_method": {"id": reachable_id,
                    "version": os.environ.get("CSL_NATIVE_REACHABLE_SET_VERSION", "1.0.0")},
                "hull_provider": {"id": os.environ.get("CSL_NATIVE_HULL_PROVIDER",
                    "csl.hull.source.quickhull-2d" if source_index else "csl.hull.lp-membership"),
                    "version": os.environ.get("CSL_NATIVE_HULL_PROVIDER_VERSION", "1.0.0")},
                "vertex_lp_provider": "not_used" if source_index else {
                    "id": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER", "phase-one-bland"),
                    "version": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER_VERSION", "1")},
                "conversion_provider": "not_used",
                "checker_budget": {"max_points": int(os.environ.get("CSL_NATIVE_GEOMETRY_CHECKER_MAX_POINTS", "64")),
                    "wall_ms": int(os.environ.get("CSL_NATIVE_GEOMETRY_CHECKER_WALL_MS", "5000"))},
                "control_optimizer": {"id": os.environ.get("CSL_NATIVE_CONTROL_OPTIMIZER",
                    "csl.optimization.finite-action-stage-layered-graph"),
                    "version": os.environ.get("CSL_NATIVE_CONTROL_OPTIMIZER_VERSION", "1.0.0")},
            })
        if factory_options:
            request.update({key: factory_options[key] for key in (
                "reachable_set_method", "hull_provider", "vertex_lp_provider",
                "conversion_provider", "checker_budget", "control_optimizer")})
    return request


class NativeFiniteActionPolicy:
    def __init__(self, task: dict[str, Any], *, task_sha256: str,
                 controller_id: str, action_profile_id: str,
                 factory_options: Mapping[str, object] | None = None) -> None:
        if factory_options is not None and not isinstance(factory_options, Mapping):
            raise ValueError("factory_options must be a mapping")
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
        self.factory_options = dict(factory_options or {})
        self.representation, self.representation_index = _representation(controller_id, self.factory_options)
        self.receipt = prediction_receipt(task)
        backend_profile = self.factory_options.get("build_backend_profile", {})
        if not isinstance(backend_profile, Mapping):
            raise ValueError("factory_options.build_backend_profile must be a mapping")
        self.preparation_receipt = {"executable": str(path),
            "executable_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "build_backend_profile": dict(backend_profile),
            "predictor_model_id": self.receipt["model_id"],
            "predictor_assurance": self.receipt["coefficient_assurance"],
            "objective_id": task["objective"]["objective_id"],
            "original_horizon": task["episode"]["intervals"],
            "action_profile_id": action_profile_id, "representation": self.representation}
        self.process = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self.last_query_capture = None
        self.query_capture_callback = None

    def set_query_capture_callback(self, callback) -> None:
        self.query_capture_callback = callback

    def _publish_query_capture(self) -> None:
        if self.query_capture_callback is not None and self.last_query_capture is not None:
            self.query_capture_callback(self.last_query_capture)

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
            self.action_profile_id, state, absolute_update_index, self.representation_index, self.receipt,
            self.factory_options)
        if self.process.poll() is not None or self.process.stdin is None or self.process.stdout is None:
            return {"status": "failed", "task_sha256": self.task_sha256,
                    "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                    "invocations": [], "reason": "native policy bridge exited before query"}
        request_line = json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n"
        self.last_query_capture = {"schema": "csl.closed-loop.native-query-capture/3",
            "capture_kind": "bridge-exchange", "bridge_request_sent": False,
            "bridge_request_transmission_status": "prepared",
            "request_sha256": hashlib.sha256(request_line.encode("utf-8")).hexdigest(),
            "bridge_request_raw": request_line, "bridge_response_raw": None,
            "bridge_response_sha256": None, "response_parse_status": "not_received"}
        self._publish_query_capture()
        try:
            self.last_query_capture["bridge_request_transmission_status"] = "attempted"
            self._publish_query_capture()
            self.process.stdin.write(request_line)
            self.process.stdin.flush()
            self.last_query_capture["bridge_request_sent"] = True
            self.last_query_capture["bridge_request_transmission_status"] = "sent"
            self._publish_query_capture()
            line = self.process.stdout.readline()
            self.last_query_capture["bridge_response_raw"] = line
            self.last_query_capture["bridge_response_sha256"] = hashlib.sha256(line.encode("utf-8")).hexdigest()
            self.last_query_capture["response_parse_status"] = "raw_received" if line else "missing_response"
            self._publish_query_capture()
            if not line:
                raise RuntimeError("native policy bridge closed its output")
            response = json.loads(line, parse_constant=_reject_nonstandard_number)
        except (BrokenPipeError, OSError, ValueError, RuntimeError) as error:
            if self.last_query_capture is not None:
                self.last_query_capture["response_parse_status"] = "malformed_json" if isinstance(error, ValueError) else \
                    self.last_query_capture.get("response_parse_status", "not_received")
                self._publish_query_capture()
            return {"status": "failed", "task_sha256": self.task_sha256,
                    "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                    "invocations": [], "reason": str(error)}
        self.last_query_capture["response_parse_status"] = "parsed"
        self._publish_query_capture()
        actual_build_profile = response.get("build_backend_profile")
        if not isinstance(actual_build_profile, Mapping):
            return {"status": "failed", "task_sha256": self.task_sha256,
                    "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                    "invocations": [], "reason": "native executable omitted its compiled backend profile"}
        expected_build_profile = self.preparation_receipt["build_backend_profile"]
        if any(value != "unspecified" and actual_build_profile.get(key) != value
                for key, value in expected_build_profile.items()):
            response.pop("control", None)
            response["status"] = "failed"
            response["reason"] = "native executable build/backend profile differs from the selected manifest profile"
            response["build_backend_profile"] = dict(actual_build_profile)
            return response
        self.preparation_receipt["build_backend_profile"] = dict(actual_build_profile)
        response["build_backend_profile"] = dict(actual_build_profile)
        response["task_sha256"] = self.task_sha256
        response["task_id"] = task_id
        response["action_profile_id"] = self.action_profile_id
        response.setdefault("policy_id", self.controller_id)
        response.setdefault("invocations", [])
        response["native_query_capture"] = {"schema": "csl.closed-loop.native-query-capture/3",
            "capture_kind": self.last_query_capture["capture_kind"],
            "bridge_request_sent": self.last_query_capture["bridge_request_sent"],
            "request_sha256": self.last_query_capture["request_sha256"],
            "bridge_response_sha256": self.last_query_capture["bridge_response_sha256"],
            "response_parse_status": self.last_query_capture["response_parse_status"]}
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
                  controller_id: str, action_profile_id: str,
                  factory_options: Mapping[str, object] | None = None) -> NativeFiniteActionPolicy:
    return NativeFiniteActionPolicy(task, task_sha256=task_sha256,
        controller_id=controller_id, action_profile_id=action_profile_id,
        factory_options=factory_options)

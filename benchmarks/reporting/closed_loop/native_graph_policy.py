"""Persistent bridge to the source-bound finite-action native controller."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from task_models import prediction_receipt, source_scenario


_PROFILES = {
    "native-exact-polytope-backward-graph/1": (0, True, "exact-polytope"),
    "native-box-mpc/1": (1, True, "box"),
    "native-zonotope-mpc/1": (2, True, "zonotope"),
    "native-parallelotope-mpc/1": (3, True, "parallelotope"),
    "native-ellipsoid-mpc/1": (4, True, "ellipsoid"),
    "native-exact-polytope-fixed-plan-mpc/1": (0, False, "exact-polytope"),
    "native-box-fixed-plan-mpc/1": (1, False, "box"),
    "native-zonotope-fixed-plan-mpc/1": (2, False, "zonotope"),
    "native-parallelotope-fixed-plan-mpc/1": (3, False, "parallelotope"),
    "native-ellipsoid-fixed-plan-mpc/1": (4, False, "ellipsoid"),
}


def _capture_safe(value):
    """Keep failure evidence JSON-writable, including nonfinite native values."""
    if isinstance(value, Mapping):
        return {str(key): _capture_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_capture_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": repr(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"unserializable_type": type(value).__name__, "repr": repr(value)}


def _profile(controller_id: str) -> tuple[int, bool, str]:
    for suffix, profile in _PROFILES.items():
        if controller_id.endswith(suffix):
            return profile
    raise ValueError(f"unrecognized native controller profile: {controller_id}")


def _source_cost(task: dict) -> dict:
    n = task["episode"]["intervals"]
    controls = len(task["model"]["controls"])
    case = task["model"]["case_id"]
    if case in {"SYN-NL-LV-01", "SYN-NL-FUEL-01"}:
        scenario = source_scenario(task)
        import affine as mpc11_affine
        source_model = mpc11_affine.model(scenario)
        definition = task["objective"]["source_definition"]
        references = source_model["reference_commands"]
        if len(references) != n:
            raise ValueError("source affine reference schedule does not cover the original horizon")
        stages = []
        for stage, reference in enumerate(references):
            stages.append({"stage": stage, "terms": [{"kind": "quadratic",
                "reference": reference, "scales": definition["running_scale"],
                "weights": [1.0] * controls, "coefficient": definition["running_weight"]}]})
        return {"objective_id": task["objective"]["objective_id"], "stages": stages}
    if case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        stages = [{"stage": stage, "terms": [{"kind": "euclidean",
            "map": [[1.0, 0.0], [0.0, 1.0]], "offset": [0.0, 0.0],
            "coefficient": 0.001 * task["episode"]["dt"]}]}
            for stage in range(n - 1)]
        return {"objective_id": task["objective"]["objective_id"], "stages": stages}
    raise ValueError(f"no source cost adapter for {case}")


def _terminal_objective(task: dict) -> dict:
    case = task["model"]["case_id"]
    if case in {"SYN-NL-LV-01", "SYN-NL-FUEL-01"}:
        source = task["objective"]["source_definition"]
        target = source["terminal_target"]
        scales = source["terminal_scale"]
        weights = source["terminal_weights"]
        dimension = len(target)
        q = [[0.0] * dimension for _ in range(dimension)]
        linear = [0.0] * dimension
        offset = 0.0
        for i in range(dimension):
            weight = weights[i] / (scales[i] * scales[i])
            q[i][i] = 2.0 * weight
            linear[i] = -2.0 * weight * target[i]
            offset += weight * target[i] * target[i]
        return {"kind": "quadratic", "Q": q, "linear": linear, "offset": offset}
    if case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        target = task["objective"]["target"]
        omega_target = target["angular_rate_rad_s"]
        return {"kind": "norm", "map": [[1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 100000.0]],
            "target": [target["radius_km"], 100000.0 * omega_target], "weights": [1.0, 1.0]}
    raise ValueError(f"no source terminal objective adapter for {case}")


def _prediction_stages(task: dict, receipt: dict, stage: int) -> list[dict]:
    coefficients = receipt["physical_coefficients"]
    n = task["episode"]["intervals"]
    if isinstance(coefficients, list):
        if len(coefficients) != n:
            raise ValueError("time-varying predictor does not cover the original task horizon")
        return coefficients[stage:]
    return [coefficients for _ in range(n - stage)]


def _candidate_action_histories(action_count: int, horizon: int, budget: int) -> dict:
    if action_count <= 0 or horizon <= 0 or budget <= 0:
        raise ValueError("candidate history generation needs positive action, horizon, and budget counts")
    full_count = action_count ** horizon
    if full_count <= budget:
        candidates = [list(row) for row in itertools.product(range(action_count), repeat=horizon)]
        return {"policy_id": "exhaustive-full-action-product/1", "candidates": candidates,
            "full_action_history_count": str(full_count), "search_coverage": "complete",
            "candidate_budget": budget}
    if budget < action_count:
        return {"policy_id": "constant-and-single-switch-full-horizon/1", "candidates": [],
            "full_action_history_count": str(full_count), "search_coverage": "unsupported-budget-below-action-count",
            "candidate_budget": budget, "constant_history_count": action_count,
            "available_single_switch_history_count": (horizon - 1) * action_count * (action_count - 1)}
    candidates = [[action] * horizon for action in range(action_count)]
    switch_count = (horizon - 1) * action_count * (action_count - 1)
    remaining = min(switch_count, budget - len(candidates))
    for selected in range(remaining):
        if remaining == switch_count:
            flat_index = selected
        elif remaining == 1:
            flat_index = 0
        else:
            flat_index = (selected * (switch_count - 1)) // (remaining - 1)
        switch_ordinal, pair_index = divmod(flat_index, action_count * (action_count - 1))
        left, right_offset = divmod(pair_index, action_count - 1)
        right = right_offset if right_offset < left else right_offset + 1
        switch = switch_ordinal + 1
        candidates.append(([left] * switch) + ([right] * (horizon - switch)))
    return {"policy_id": "constant-and-single-switch-full-horizon/1", "candidates": candidates,
        "full_action_history_count": str(full_count), "search_coverage": "incomplete",
        "candidate_budget": budget, "constant_history_count": action_count,
        "available_single_switch_history_count": switch_count,
        "selected_single_switch_history_count": remaining}


class NativeGraphPolicy:
    def __init__(self, task: dict, task_sha256: str, controller_id: str,
                 action_profile_id: str, factory_options: Mapping[str, object] | None = None):
        self.task = task
        self.task_sha256 = task_sha256
        self.controller_id = controller_id
        self.action_profile_id = action_profile_id
        if factory_options is not None and not isinstance(factory_options, Mapping):
            raise ValueError("factory_options must be a mapping")
        self.factory_options = dict(factory_options or {})
        self.representation_index, self.use_backward_graph, self.representation_name = _profile(controller_id)
        declared_representation = self.factory_options.get("representation")
        if declared_representation is not None and declared_representation != self.representation_name:
            raise ValueError("factory_options.representation differs from the controller profile")
        finite = task["control_domains"]["finite"]
        if action_profile_id != finite["problem_id"]:
            raise ValueError("native finite-action controllers require the task's declared finite action profile")
        executable = os.environ.get("CSL_NATIVE_POLICY_BRIDGE")
        if not executable:
            raise ValueError("CSL_NATIVE_POLICY_BRIDGE must name the built csl_closed_loop_native_policy executable")
        self.executable = Path(executable).resolve(strict=True)
        if not os.access(self.executable, os.X_OK):
            raise ValueError("native policy bridge is not executable")
        self.process = subprocess.Popen([str(self.executable)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1)
        self.last_query_capture = None
        self.query_capture_callback = None
        self.receipt = prediction_receipt(task)
        self.running_cost = _source_cost(task)
        self.terminal_objective = _terminal_objective(task)
        self.actions = finite["actions"]
        self.original_horizon = task["episode"]["intervals"]
        self.dt = task["episode"]["dt"]
        self.state_bounds = [field.get("bounds") for field in task["model"]["states"]]
        self.limits = self._limits()
        backend_profile = self.factory_options.get("build_backend_profile")
        if backend_profile is not None and not isinstance(backend_profile, Mapping):
            raise ValueError("factory_options.build_backend_profile must be a mapping")
        backend_profile = dict(backend_profile or {
            "build_type": os.environ.get("CSL_NATIVE_BUILD_TYPE", "unspecified"),
            "CSL_ENABLE_HIGHS": os.environ.get("CSL_NATIVE_HAS_HIGHS", "unspecified"),
            "CSL_ENABLE_QHULL": os.environ.get("CSL_NATIVE_HAS_QHULL", "unspecified"),
        })
        self.preparation_receipt = {"executable": str(self.executable),
            "executable_sha256": hashlib.sha256(self.executable.read_bytes()).hexdigest(),
            "native_stderr": "inherited supervised worker stderr; shared across native queries, not isolated per call",
            "build_backend_profile": backend_profile,
            "predictor_model_id": self.receipt["model_id"],
            "predictor_assurance": self.receipt["coefficient_assurance"],
            "objective_id": task["objective"]["objective_id"],
            "original_horizon": self.original_horizon, "action_profile_id": action_profile_id,
            "representation": self.representation_name,
            "controller_semantics": ("finite-action receding-horizon graph MPC with source-cost ranking, numerical H predecessor membership, discrete transition witnesses, and the explicitly selected representation's one-step outer edge filter"
                if self.use_backward_graph else
                "finite-action receding-horizon fixed-plan MPC using exhaustive full action histories when within budget, otherwise a deterministic bounded catalogue of full-horizon constant and single-switch histories; exact source running-cost ranking, authored state-constraint replay, and a separately recomputed original affine trajectory")}

    def _limits(self) -> dict[str, int]:
        keys = ("max_beam_width", "max_graph_nodes", "max_plans", "max_points_per_stage",
                "max_score_evaluations", "max_generators_per_stage")
        defaults = {
            "max_beam_width": ("CSL_NATIVE_GRAPH_BEAM_WIDTH", 8),
            "max_graph_nodes": ("CSL_NATIVE_GRAPH_MAX_NODES", 512),
            "max_plans": ("CSL_NATIVE_MAX_PLANS", 512),
            "max_points_per_stage": ("CSL_NATIVE_MAX_POINTS_PER_STAGE", 100000),
            "max_score_evaluations": ("CSL_NATIVE_MAX_SCORE_EVALUATIONS", 100000),
            "max_generators_per_stage": ("CSL_NATIVE_MAX_GENERATORS_PER_STAGE", 1000),
        }
        declared = self.factory_options.get("limits")
        if declared is not None and not isinstance(declared, Mapping):
            raise ValueError("factory_options.limits must be a mapping")
        result = {}
        for key in keys:
            if declared is not None and key not in declared:
                raise ValueError(f"factory_options.limits is missing {key}")
            raw = declared[key] if declared is not None else os.environ.get(defaults[key][0], defaults[key][1])
            value = int(raw)
            if value <= 0:
                raise ValueError(f"factory_options.limits.{key} must be positive")
            result[key] = value
        return result

    def set_query_capture_callback(self, callback) -> None:
        self.query_capture_callback = callback

    def _publish_query_capture(self) -> None:
        if self.query_capture_callback is not None and self.last_query_capture is not None:
            self.query_capture_callback(_capture_safe(self.last_query_capture))

    def _method_option(self, key: str, env_id: str, env_version: str, default_id: str,
                       default_version: str) -> dict[str, str]:
        declared = self.factory_options.get(key)
        if declared is not None:
            if not isinstance(declared, Mapping) or not declared.get("id") or not declared.get("version"):
                raise ValueError(f"factory_options.{key} must provide id and version")
            return {"id": str(declared["id"]), "version": str(declared["version"])}
        return {"id": os.environ.get(env_id, default_id),
                "version": os.environ.get(env_version, default_version)}

    def _geometry_options(self) -> dict[str, object]:
        if self.factory_options:
            required = ("reachable_set_method", "hull_provider", "vertex_lp_provider",
                        "conversion_provider", "checker_budget", "control_optimizer")
            missing = [key for key in required if key not in self.factory_options]
            if missing:
                raise ValueError("factory_options is missing selected graph roles: " + ", ".join(missing))
        reachable = self._method_option("reachable_set_method", "CSL_NATIVE_REACHABLE_SET_METHOD",
            "CSL_NATIVE_REACHABLE_SET_VERSION", "csl.geometry.affine-sum", "1.0.0")
        source_index = reachable["id"] == "csl.geometry.affine-sum.source-index"
        hull = self._method_option("hull_provider", "CSL_NATIVE_HULL_PROVIDER",
            "CSL_NATIVE_HULL_PROVIDER_VERSION",
            "csl.hull.source.quickhull-2d" if source_index else "csl.hull.lp-membership", "1.0.0")
        declared_lp = self.factory_options.get("vertex_lp_provider")
        if declared_lp is not None:
            if declared_lp == "not_used":
                lp: object = "not_used"
            elif isinstance(declared_lp, Mapping) and declared_lp.get("id") and declared_lp.get("version"):
                lp = {"id": str(declared_lp["id"]), "version": str(declared_lp["version"])}
            else:
                raise ValueError("factory_options.vertex_lp_provider must be not_used or provide id and version")
        elif source_index:
            lp = "not_used"
        else:
            lp = {"id": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER", "phase-one-bland"),
                  "version": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER_VERSION", "1")}
        conversion = self.factory_options.get("conversion_provider", "not_used")
        if conversion != "not_used" and (not isinstance(conversion, Mapping) or
                not conversion.get("id") or not conversion.get("version")):
            raise ValueError("factory_options.conversion_provider must be not_used or provide id and version")
        checker = self.factory_options.get("checker_budget", {"max_points": 64, "wall_ms": 5000})
        if not isinstance(checker, Mapping) or "max_points" not in checker or "wall_ms" not in checker:
            raise ValueError("factory_options.checker_budget must provide max_points and wall_ms")
        checker = {"max_points": int(checker["max_points"]), "wall_ms": int(checker["wall_ms"])}
        if checker["max_points"] <= 0 or checker["wall_ms"] < 0:
            raise ValueError("factory_options.checker_budget must have positive capacity and nonnegative wall limit")
        optimizer = self._method_option("control_optimizer", "CSL_NATIVE_CONTROL_OPTIMIZER",
            "CSL_NATIVE_CONTROL_OPTIMIZER_VERSION", "csl.optimization.finite-action-stage-layered-graph", "1.0.0")
        return {"reachable_set_method": reachable, "hull_provider": hull,
            "vertex_lp_provider": lp, "conversion_provider": conversion,
            "checker_budget": checker, "control_optimizer": optimizer}

    def query(self, task_id: str, observed_physical_state: list[float], absolute_update_index: int) -> dict:
        self.last_query_capture = None
        if task_id != self.task["task_id"] or not 0 <= absolute_update_index < self.original_horizon:
            raise ValueError("query task or absolute update index differs from the source-bound task")
        predictor_stages = _prediction_stages(self.task, self.receipt, absolute_update_index)
        horizon = len(predictor_stages)
        state_bounds = self.state_bounds
        request = {"schema": "csl.closed-loop.native-policy-query/1", "task_id": task_id,
            "task_sha256": self.task_sha256, "source_model_id": self.task["model"]["model_id"],
            "controller_id": self.controller_id, "action_profile_id": self.action_profile_id,
            "problem_id": self.task["task_id"], "request_id": f"{self.controller_id}/update-{absolute_update_index}",
            "absolute_update_index": absolute_update_index, "observed_physical_state": observed_physical_state,
            "original_horizon": self.original_horizon, "dt": self.dt,
            "predictor_model_id": self.receipt["model_id"],
            "predictor_assurance": self.receipt["coefficient_assurance"],
            "predictor_stages": predictor_stages, "actions": self.actions,
            "state_bounds": state_bounds,
            "terminal_objective": self.terminal_objective, "running_cost": self.running_cost,
            "representation_index": self.representation_index, "representation_name": self.representation_name,
            "limits": self.limits}
        if self.use_backward_graph:
            request["search_policy"] = "stage-layered-backward-viability"
            request.update(self._geometry_options())
        else:
            candidate_search = _candidate_action_histories(
                len(self.actions), horizon, self.limits["max_plans"])
            if not candidate_search["candidates"]:
                response = {"status": "unsupported", "task_id": task_id,
                    "task_sha256": self.task_sha256, "action_profile_id": self.action_profile_id,
                    "policy_id": self.controller_id, "invocations": [],
                    "mathematical_support": "not_evaluated",
                    "candidate_plan_search": {"policy_id": candidate_search["policy_id"],
                        "candidate_count": 0, "candidate_budget": candidate_search["candidate_budget"],
                        "full_action_history_count": candidate_search["full_action_history_count"],
                        "search_coverage": "not_evaluated",
                        "available_single_switch_history_count": candidate_search[
                            "available_single_switch_history_count"]},
                    "reason": "candidate plan budget is smaller than the source action catalogue; no histories were searched"}
                self.last_query_capture = {"schema": "csl.closed-loop.native-query-capture/2",
                    "capture_kind": "adapter-preflight", "bridge_request_sent": False,
                    "request": _capture_safe(request), "bridge_response_raw": None,
                    "bridge_response_sha256": None, "adapter_response": _capture_safe(response)}
                self._publish_query_capture()
                response["native_query_capture"] = _capture_safe(self.last_query_capture)
                return response
            request["candidate_action_indices"] = candidate_search["candidates"]
            request["candidate_search_policy"] = candidate_search["policy_id"]
            request["candidate_search_full_action_history_count"] = candidate_search["full_action_history_count"]
            request["candidate_search_coverage"] = candidate_search["search_coverage"]
            request["candidate_search_budget"] = candidate_search["candidate_budget"]
        request_json = None
        self.last_query_capture = {"schema": "csl.closed-loop.native-query-capture/2",
            "capture_kind": "bridge-exchange", "bridge_request_sent": False,
            "request": _capture_safe(request), "request_json": None,
            "bridge_request_raw": None, "bridge_request_transmission_status": "not_started",
            "request_sha256": None, "bridge_response_raw": None,
            "bridge_response_sha256": None, "response_parse_status": "not_received"}
        self._publish_query_capture()
        request_json = json.dumps(request, separators=(",", ":"), allow_nan=False)
        request_line = request_json + "\n"
        self.last_query_capture["request_json"] = request_json
        self.last_query_capture["bridge_request_raw"] = request_line
        self.last_query_capture["request_sha256"] = hashlib.sha256(request_line.encode("utf-8")).hexdigest()
        self.last_query_capture["bridge_request_transmission_status"] = "prepared"
        self._publish_query_capture()
        assert self.process.stdin is not None and self.process.stdout is not None
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
        if not line:
            self.last_query_capture["response_parse_status"] = "missing_response"
            self._publish_query_capture()
            raise RuntimeError(f"native policy bridge exited before returning a response (code {self.process.poll()})")
        self.last_query_capture["response_parse_status"] = "raw_received"
        self._publish_query_capture()
        try:
            response = json.loads(line)
        except (json.JSONDecodeError, ValueError) as error:
            self.last_query_capture["response_parse_status"] = "malformed_json"
            self._publish_query_capture()
            raise ValueError(f"native policy bridge returned malformed JSON: {error}") from error
        self.last_query_capture["parsed_response"] = _capture_safe(response)
        self.last_query_capture["response_parse_status"] = "parsed"
        self._publish_query_capture()
        if not isinstance(response, dict):
            raise ValueError("native policy bridge response must be a JSON object")
        native_response = dict(response)
        actual_build_profile = response.get("build_backend_profile")
        if not isinstance(actual_build_profile, Mapping):
            failed = {"status": "failed", "task_sha256": self.task_sha256,
                "action_profile_id": self.action_profile_id, "policy_id": self.controller_id,
                "invocations": [], "reason": "native executable omitted its compiled backend profile"}
            failed["native_query_capture"] = _capture_safe(self.last_query_capture)
            return failed
        expected_build_profile = self.preparation_receipt["build_backend_profile"]
        if any(value != "unspecified" and actual_build_profile.get(key) != value
                for key, value in expected_build_profile.items()):
            response.pop("control", None)
            response["status"] = "incompatible"
            response["reason"] = "native executable build/backend profile differs from the selected manifest profile"
            response["build_backend_profile"] = actual_build_profile
            response["native_query_capture"] = _capture_safe(self.last_query_capture)
            return response
        self.preparation_receipt["build_backend_profile"] = dict(actual_build_profile)
        response["build_backend_profile"] = dict(actual_build_profile)
        if response.get("task_id") != task_id or response.get("task_sha256") != self.task_sha256:
            raise ValueError(f"native controller response does not echo source task identity: {response}")
        if response.get("action_profile_id") != self.action_profile_id:
            raise ValueError("native controller response does not echo action profile")
        response["policy_semantics"] = self.preparation_receipt["controller_semantics"]
        response["prediction_profile"] = {"model_id": self.receipt["model_id"],
            "assurance": self.receipt["coefficient_assurance"], "task_sha256": self.task_sha256,
            "remaining_prediction_steps": horizon, "original_update_index": absolute_update_index}
        response["coverage"] = response.get("selector", {}).get("search_coverage",
            response.get("graph_receipt", {}).get("search_coverage", "not_applicable"))
        response["query_receipt"] = {"schema": "csl.closed-loop.native-query-capture/1",
            "task_id": task_id, "task_sha256": self.task_sha256,
            "action_profile_id": self.action_profile_id, "absolute_update_index": absolute_update_index,
            "request": request,
            "bridge_response_sha256": hashlib.sha256(json.dumps(native_response, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
            "bridge_response": native_response}
        response["native_query_capture"] = _capture_safe(self.last_query_capture)
        return response

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try: self.process.wait(timeout=1)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        if self.process.returncode not in (0, None):
            raise RuntimeError(f"native policy bridge exited with status {self.process.returncode}")


def create_policy(task: dict, *, task_sha256: str, controller_id: str,
                  action_profile_id: str,
                  factory_options: Mapping[str, object] | None = None) -> NativeGraphPolicy:
    return NativeGraphPolicy(task, task_sha256, controller_id, action_profile_id, factory_options)

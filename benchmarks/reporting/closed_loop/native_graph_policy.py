"""Persistent bridge to the source-bound finite-action native controller."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
            q[i][i] = weights[i] / (scales[i] * scales[i])
            linear[i] = -2.0 * q[i][i] * target[i]
            offset += q[i][i] * target[i] * target[i]
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


class NativeGraphPolicy:
    def __init__(self, task: dict, task_sha256: str, controller_id: str, action_profile_id: str):
        self.task = task
        self.task_sha256 = task_sha256
        self.controller_id = controller_id
        self.action_profile_id = action_profile_id
        self.representation_index, self.use_backward_graph, self.representation_name = _profile(controller_id)
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
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self.receipt = prediction_receipt(task)
        self.running_cost = _source_cost(task)
        self.terminal_objective = _terminal_objective(task)
        self.actions = finite["actions"]
        self.original_horizon = task["episode"]["intervals"]
        self.dt = task["episode"]["dt"]
        self.state_bounds = [field.get("bounds") for field in task["model"]["states"]]
        self.preparation_receipt = {"executable": str(self.executable),
            "executable_sha256": hashlib.sha256(self.executable.read_bytes()).hexdigest(),
            "predictor_model_id": self.receipt["model_id"],
            "predictor_assurance": self.receipt["coefficient_assurance"],
            "objective_id": task["objective"]["objective_id"],
            "original_horizon": self.original_horizon, "action_profile_id": action_profile_id,
            "representation": self.representation_name,
            "controller_semantics": ("finite-action receding-horizon graph MPC with source-cost ranking, numerical H predecessor membership, discrete transition witnesses, and the explicitly selected representation's one-step outer edge filter"
                if self.use_backward_graph else
                "finite-action receding-horizon fixed-plan MPC using the selected representation profile, exact source running-cost ranking, authored state-constraint replay, and a separately recomputed original affine trajectory")}

    def query(self, task_id: str, observed_physical_state: list[float], absolute_update_index: int) -> dict:
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
            "limits": {"max_beam_width": int(os.environ.get("CSL_NATIVE_GRAPH_BEAM_WIDTH", "8")),
                "max_graph_nodes": int(os.environ.get("CSL_NATIVE_GRAPH_MAX_NODES", "512")),
                "max_plans": int(os.environ.get("CSL_NATIVE_MAX_PLANS", "512")),
                "max_points_per_stage": int(os.environ.get("CSL_NATIVE_MAX_POINTS_PER_STAGE", "100000")),
                "max_score_evaluations": int(os.environ.get("CSL_NATIVE_MAX_SCORE_EVALUATIONS", "100000")),
                "max_generators_per_stage": int(os.environ.get("CSL_NATIVE_MAX_GENERATORS_PER_STAGE", "1000"))}}
        if self.use_backward_graph:
            request["search_policy"] = "stage-layered-backward-viability"
            reachable_id = os.environ.get("CSL_NATIVE_REACHABLE_SET_METHOD", "csl.geometry.affine-sum")
            source_index = reachable_id == "csl.geometry.affine-sum.source-index"
            request["reachable_set_method"] = {"id": reachable_id,
                "version": os.environ.get("CSL_NATIVE_REACHABLE_SET_VERSION", "1.0.0")}
            request["hull_provider"] = {"id": os.environ.get("CSL_NATIVE_HULL_PROVIDER",
                "csl.hull.source.quickhull-2d" if source_index else "csl.hull.lp-membership"),
                "version": os.environ.get("CSL_NATIVE_HULL_PROVIDER_VERSION", "1.0.0")}
            request["vertex_lp_provider"] = "not_used" if source_index else {
                "id": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER", "phase-one-bland"),
                "version": os.environ.get("CSL_NATIVE_VERTEX_LP_PROVIDER_VERSION", "1")}
            request["conversion_provider"] = os.environ.get("CSL_NATIVE_CONVERSION_PROVIDER", "not_used")
            request["checker_budget"] = {
                "max_points": int(os.environ.get("CSL_NATIVE_GEOMETRY_CHECKER_MAX_POINTS", "64")),
                "wall_ms": int(os.environ.get("CSL_NATIVE_GEOMETRY_CHECKER_WALL_MS", "5000"))}
            request["control_optimizer"] = {"id": os.environ.get("CSL_NATIVE_CONTROL_OPTIMIZER",
                "csl.optimization.finite-action-stage-layered-graph"),
                "version": os.environ.get("CSL_NATIVE_CONTROL_OPTIMIZER_VERSION", "1.0.0")}
        self.last_request = request
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":"), allow_nan=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"native policy bridge exited before returning a response (code {self.process.poll()})")
        response = json.loads(line)
        native_response = dict(response)
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
        if self.process.returncode not in (0, None):
            raise RuntimeError(f"native policy bridge exited with status {self.process.returncode}")


def create_policy(task: dict, *, task_sha256: str, controller_id: str,
                  action_profile_id: str) -> NativeGraphPolicy:
    return NativeGraphPolicy(task, task_sha256, controller_id, action_profile_id)

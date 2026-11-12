"""Source-bound request for a continuous full-history policy query."""
from __future__ import annotations

from native_graph_policy import _prediction_stages, _source_cost, _terminal_objective


FAMILIES = ("polytope", "box", "zonotope", "parallelotope", "ellipsoid")
GEOMETRY_IDS = {f"native-continuous-history-{family}-ipopt/1": family for family in FAMILIES}


def geometry_memberships(export, family, state_dimension, horizon):
    if (not isinstance(export, dict) or export.get("status") != "complete"
            or export.get("family") != family or export.get("scope") != "forward_relevant_from_observation"):
        raise ValueError("feedback geometry does not match the selected family and scope")
    stages = export.get("stages")
    if not isinstance(stages, list) or len(stages) != horizon + 1:
        raise ValueError("feedback geometry must cover every history stage")
    memberships = []
    for k, stage in enumerate(stages):
        if stage.get("stage") != k or stage.get("coordinates") != list(range(state_dimension)):
            raise ValueError("feedback geometry stage or state coordinate order differs")
        rows = stage.get("memberships")
        if not isinstance(rows, list) or len(rows) != 3 or {row.get("role") for row in rows} != {"forward", "backward", "intersection"}:
            raise ValueError("feedback geometry must retain forward, backward and intersection sets")
        for row in rows:
            if row.get("indices") != list(range(k * state_dimension, (k + 1) * state_dimension)):
                raise ValueError("feedback geometry membership has wrong history coordinates")
            expected = "h" if family in {"polytope", "box", "parallelotope"} else family
            if row.get("kind") != expected:
                raise ValueError("feedback geometry membership differs from requested family")
            if row.get("relation") not in {"outer", "equivalent"}:
                raise ValueError("feedback geometry is not an outer set")
            memberships.append(row)
    return memberships


def make_request(task, task_sha256, receipt, observed, stage, *, history_solver=None, geometry_family=None):
    n = task["episode"]["intervals"]
    if not isinstance(stage, int) or not 0 <= stage < n:
        raise ValueError("query stage must belong to the original horizon")
    if history_solver is None:
        history_solver = ("casadi-ipopt" if task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01"
                          else "csl.convex.highs")
    if history_solver not in {"csl.convex.highs", "casadi-ipopt"}:
        raise ValueError("unknown history solver")
    action_profile = task["control_domains"]["continuous"]
    result = {"schema": "csl.closed-loop.native-policy-query/1", "mode": "continuous-history/1",
            "history_solver": history_solver,
            "task_id": task["task_id"], "task_sha256": task_sha256,
            "source_model_id": task["model"]["model_id"],
            "controller_id": "native-continuous-affine-history-mpc/1",
            "action_profile_id": action_profile["problem_id"], "problem_id": task["task_id"],
            "request_id": f"continuous-history/update-{stage}",
            "absolute_update_index": stage, "observed_physical_state": list(observed),
            "original_horizon": n, "dt": task["episode"]["dt"],
            "predictor_model_id": receipt["model_id"],
            "predictor_assurance": receipt["coefficient_assurance"],
            "predictor_stages": _prediction_stages(task, receipt, stage),
            "state_bounds": [field.get("bounds") for field in task["model"]["states"]],
            "control_bounds": action_profile["bounds"],
            "terminal_objective": _terminal_objective(task), "running_cost": _source_cost(task)}
    if geometry_family is not None:
        if geometry_family not in FAMILIES or history_solver != "casadi-ipopt":
            raise ValueError("feedback family requires explicitly selected IPOPT")
        result.update({"geometry_family": geometry_family, "geometry_max_generators": 1000})
    return result


class HistoryPolicy:
    """Re-solve the full remaining affine history from each observation."""
    def __init__(self, task, task_sha256, controller_id, action_profile_id, factory_options=None):
        import hashlib
        import os
        import subprocess
        from pathlib import Path
        from contracts import manifest_sha256
        from task_models import prediction_receipt, validate_source_binding

        validate_source_binding(task)
        if manifest_sha256(task) != task_sha256:
            raise ValueError("history policy task hash differs from the source-bound task")
        if controller_id not in {"native-continuous-affine-history-mpc/1", "native-continuous-affine-history-ipopt/1", *GEOMETRY_IDS}:
            raise ValueError("unknown continuous history policy profile")
        if (controller_id == "native-continuous-affine-history-ipopt/1"
                and task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01"):
            raise ValueError("orbit already selects the IPOPT history solver in the original profile")
        self.geometry_family = GEOMETRY_IDS.get(controller_id)
        self.history_solver = ("casadi-ipopt" if self.geometry_family is not None or controller_id == "native-continuous-affine-history-ipopt/1"
            or task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01" else "csl.convex.highs")
        if action_profile_id != task["control_domains"]["continuous"]["problem_id"]:
            raise ValueError("continuous history policy requires the original continuous action domain")
        if factory_options:
            raise ValueError("continuous history provider options are not registered")
        receipt = prediction_receipt(task)
        executable = Path(os.environ["CSL_NATIVE_POLICY_BRIDGE"]).resolve(strict=True)
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, bufsize=1)
        self.task, self.task_sha256, self.controller_id = task, task_sha256, controller_id
        self.action_profile_id = action_profile_id
        self.receipt = receipt
        self.last_query_capture = None
        self.query_capture_callback = None
        self.preparation_receipt = {"executable": str(executable),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "binary_source": "unknown",
            "action_profile_id": action_profile_id, "original_horizon": task["episode"]["intervals"],
            "geometry": self.geometry_family or "not_used", "history_solver": self.history_solver,
            "controller_semantics": "observed-state direct affine-history MPC"}

    def set_query_capture_callback(self, callback):
        self.query_capture_callback = callback

    def _capture(self):
        import copy
        if self.query_capture_callback is not None:
            self.query_capture_callback(copy.deepcopy(self.last_query_capture))

    def query(self, task_id, observed_physical_state, absolute_update_index):
        import hashlib
        import json
        import numpy as np
        from history_validation import validate

        self.last_query_capture = None
        if task_id != self.task["task_id"]:
            raise ValueError("query task differs from source-bound task")
        if (self.task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01"
                and observed_physical_state[0] <= 0):
            raise ValueError("observed orbit radius must be positive")
        request = make_request(self.task, self.task_sha256, self.receipt,
                               observed_physical_state, absolute_update_index, history_solver=self.history_solver,
                               geometry_family=self.geometry_family)
        request["controller_id"] = self.controller_id
        raw = json.dumps(request, separators=(",", ":"), allow_nan=False) + "\n"
        self.last_query_capture = {"schema": "csl.closed-loop.native-query-capture/2",
            "capture_kind": "bridge-exchange", "request": request, "bridge_request_raw": raw,
            "request_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "bridge_request_sent": False, "bridge_request_transmission_status": "prepared",
            "response_parse_status": "not_received", "bridge_response_raw": None}
        self._capture()
        self.last_query_capture["bridge_request_transmission_status"] = "attempted"
        self._capture()
        self.process.stdin.write(raw); self.process.stdin.flush()
        self.last_query_capture["bridge_request_sent"] = True
        self.last_query_capture["bridge_request_transmission_status"] = "sent"
        self._capture()
        response_raw = self.process.stdout.readline()
        self.last_query_capture["bridge_response_raw"] = response_raw
        self.last_query_capture["bridge_response_sha256"] = hashlib.sha256(response_raw.encode()).hexdigest()
        self._capture()
        if not response_raw:
            self.last_query_capture["response_parse_status"] = "missing_response"
            self._capture()
            raise RuntimeError("native history bridge exited before responding")
        self.last_query_capture["response_parse_status"] = "raw_received"
        self._capture()
        try:
            response = json.loads(response_raw)
        except (json.JSONDecodeError, ValueError):
            self.last_query_capture["response_parse_status"] = "malformed_json"
            self._capture()
            raise
        self.last_query_capture["parsed_response"] = response
        self.last_query_capture["response_parse_status"] = "parsed"
        self._capture()
        if response.get("task_id") != task_id or response.get("task_sha256") != self.task_sha256 or response.get("action_profile_id") != self.action_profile_id:
            raise ValueError("native history response has a different task identity")
        result = {"task_sha256": self.task_sha256, "action_profile_id": self.action_profile_id,
                  "policy_id": self.controller_id, "status": "failed", "invocations": [],
                  "native_query_capture": self.last_query_capture}
        if "history_relation" in response and "history_objective" in response:
            result["invocations"].extend([
                {"operation": "history.recover", "module_id": "csl::synthesis::recover_joint_history",
                 "profile_id": self.controller_id, "provider": "public-function"},
                {"operation": "history.compile-cost", "module_id": "csl::optimization::compile_history_cost",
                 "profile_id": self.controller_id, "provider": "public-function"}])
        if isinstance(response.get("geometry"), dict):
            for stage_record in response["geometry"].get("stages", []):
                for membership in stage_record.get("memberships", []):
                    for call in membership.get("providers", []):
                        if call.get("actual"):
                            result.setdefault("geometry_invocations", []).append({
                                "operation": "feedback.geometry", "actual_method_id": call["actual"],
                                "version": call.get("actual_version") or "unknown", "role": "reachable_set_method",
                                "absolute_stage": absolute_update_index + stage_record["stage"],
                                "geometry_role": membership["role"], "request_id": call["request"]})
                    for call in membership.get("support_calls", []):
                        if call.get("actual"):
                            result.setdefault("geometry_invocations", []).append({
                                "operation": "feedback.support", "actual_method_id": call["actual"],
                                "version": call.get("actual_version") or "unknown", "role": "support_lp",
                                "absolute_stage": absolute_update_index + stage_record["stage"],
                                "geometry_role": membership["role"], "program_id": call["program"],
                                "outcome": call["status"]})
        if response.get("status") not in {"solved", "exported"}:
            result["status"] = response.get("status", "failed")
            result["reason"] = response.get("reason", "native history export failed")
            if "solver_receipt" in response:
                result["solve_receipt"] = {"bridge_response": response, "solver": response["solver_receipt"]}
                result["invocations"].append({"operation": "controller.solve", "module_id": "continuous-history-mpc",
                    "profile_id": self.controller_id, "provider": response["solver_receipt"]["provider"],
                    "version": response["solver_receipt"].get("version", "unknown")})
            return result
        if response.get("requested_solver") != self.history_solver:
            raise ValueError("native history response differs from the explicitly selected solver")
        expected_status = "solved" if self.history_solver == "csl.convex.highs" else "exported"
        if response["status"] != expected_status:
            raise ValueError("native history response does not match the explicitly selected solver route")
        relation, compiled = response["history_relation"], response["history_objective"]
        memberships = (geometry_memberships(response.get("geometry"), self.geometry_family,
            len(observed_physical_state), len(request["predictor_stages"]))
            if self.geometry_family is not None else None)
        if response["status"] == "solved":
            primal = np.asarray(response["primal"], dtype=float)
            solver_receipt = response["solver_receipt"]
            q = compiled["quadratic"]
            solver_cost = float(0.5 * primal @ np.asarray(q["Q"]) @ primal + np.asarray(q["linear"]) @ primal + q["offset"])
        else:
            from history_norm_solver import solve
            n = len(observed_physical_state)
            m = len(request["control_bounds"])
            controls = [np.clip(np.zeros(m), np.asarray(request["control_bounds"])[:, 0],
                                np.asarray(request["control_bounds"])[:, 1]) for _ in request["predictor_stages"]]
            states = [np.asarray(observed_physical_state, dtype=float)]
            for row, control in zip(request["predictor_stages"], controls):
                states.append(np.asarray(row["A"]) @ states[-1] + np.asarray(row["B"]) @ control + np.asarray(row["c"]))
            initial = np.concatenate([*states, *controls])
            positive = [n * k for k in range(1, len(states))] if self.task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01" else []
            solver_receipt = solve(relation, compiled, initial=initial, positive_indices=positive,
                                   geometry_memberships=memberships or ())
            result["invocations"].append({"operation": "controller.solve", "module_id": "continuous-history-mpc",
                "profile_id": self.controller_id, "provider": "casadi-ipopt",
                "version": solver_receipt.get("version", "unknown")})
            self.last_query_capture["solver_receipt"] = solver_receipt
            self._capture()
            if not solver_receipt["success"]:
                result["solve_receipt"] = {"bridge_response": response, "solver": solver_receipt}
                result["reason"] = "history norm solver failed: " + str(solver_receipt)
                return result
            primal, solver_cost = solver_receipt["primal"], solver_receipt["objective"]
        provider = solver_receipt.get("provider", "casadi-ipopt")
        if response["status"] == "solved":
            result["invocations"].append({"operation": "controller.solve", "module_id": "continuous-history-mpc",
                "profile_id": self.controller_id, "provider": provider,
                "version": solver_receipt.get("version", "unknown")})
        result["solve_receipt"] = {"bridge_response": response, "solver": solver_receipt}
        try:
            checks = validate(self.task, absolute_update_index, observed_physical_state,
                              request["predictor_stages"], relation, primal, solver_cost,
                              geometry_memberships=memberships,
                              geometry_factors=solver_receipt.get("geometry_factors") if memberships else None)
        except (ValueError, FloatingPointError) as error:
            result["reason"] = "history validation failed: " + str(error)
            return result
        result["solve_receipt"]["independent_validation"] = checks
        if not checks["accepted"]:
            result["reason"] = "full-history source or feasibility verification failed"
            return result
        result.update({"status": "accepted", "control": checks["controls"][0],
            "selected_plan": {"states": checks["states"], "controls": checks["controls"],
                              "source_cost": checks["source_cost"]},
            "policy_semantics": ("observed-state affine-history MPC with full-state F/B/I family memberships"
                if self.geometry_family else "fresh observed-state affine history MPC; numerical local evidence"),
            "coverage": "not_applicable"})
        return result

    def close(self):
        from subprocess import TimeoutExpired
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except TimeoutExpired:
            self.process.terminate()
            self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        if self.process.returncode not in (0, None):
            raise RuntimeError(f"native history bridge exited with status {self.process.returncode}")


def create_policy(task, *, task_sha256, controller_id, action_profile_id, factory_options=None):
    return HistoryPolicy(task, task_sha256, controller_id, action_profile_id, factory_options)

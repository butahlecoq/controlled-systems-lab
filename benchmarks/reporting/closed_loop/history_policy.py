"""Source-bound request for a continuous full-history policy query."""
from __future__ import annotations

from native_graph_policy import _prediction_stages, _source_cost, _terminal_objective


def make_request(task, task_sha256, receipt, observed, stage):
    n = task["episode"]["intervals"]
    if not isinstance(stage, int) or not 0 <= stage < n:
        raise ValueError("query stage must belong to the original horizon")
    action_profile = task["control_domains"]["continuous"]
    return {"schema": "csl.closed-loop.native-policy-query/1", "mode": "continuous-history/1",
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


class HistoryPolicy:
    """Re-solve the full remaining affine history from each observation."""
    def __init__(self, task, task_sha256, controller_id, action_profile_id, factory_options=None):
        import hashlib
        import os
        import subprocess
        from pathlib import Path
        from task_models import prediction_receipt

        if action_profile_id != task["control_domains"]["continuous"]["problem_id"]:
            raise ValueError("continuous history policy requires the original continuous action domain")
        if factory_options:
            raise ValueError("continuous history provider options are not registered")
        executable = Path(os.environ["CSL_NATIVE_POLICY_BRIDGE"]).resolve(strict=True)
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, bufsize=1)
        self.task, self.task_sha256, self.controller_id = task, task_sha256, controller_id
        self.action_profile_id = action_profile_id
        self.receipt = prediction_receipt(task)
        self.last_query_capture = None
        self.query_capture_callback = None
        self.preparation_receipt = {"executable": str(executable),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "binary_source": "unknown",
            "action_profile_id": action_profile_id, "original_horizon": task["episode"]["intervals"],
            "geometry": "not_used", "controller_semantics": "observed-state direct affine-history MPC"}

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
                               observed_physical_state, absolute_update_index)
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
        if response.get("status") not in {"accepted", "exported"}:
            result["status"] = response.get("status", "failed")
            result["reason"] = response.get("reason", "native history export failed")
            if "solver_receipt" in response:
                result["solve_receipt"] = {"bridge_response": response, "solver": response["solver_receipt"]}
                result["invocations"].append({"operation": "controller.solve", "module_id": "continuous-history-mpc",
                    "profile_id": self.controller_id, "provider": response["solver_receipt"]["provider"],
                    "version": response["solver_receipt"].get("version", "unknown")})
            return result
        relation, compiled = response["history_relation"], response["history_objective"]
        if response["status"] == "accepted":
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
            solver_receipt = solve(relation, compiled, initial=initial, positive_indices=positive)
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
        if response["status"] == "accepted":
            result["invocations"].append({"operation": "controller.solve", "module_id": "continuous-history-mpc",
                "profile_id": self.controller_id, "provider": provider,
                "version": solver_receipt.get("version", "unknown")})
        result["solve_receipt"] = {"bridge_response": response, "solver": solver_receipt}
        try:
            checks = validate(self.task, absolute_update_index, observed_physical_state,
                              request["predictor_stages"], relation, primal, solver_cost)
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
            "policy_semantics": "fresh observed-state affine history MPC; numerical local evidence",
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

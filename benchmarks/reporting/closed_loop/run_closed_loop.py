#!/usr/bin/env python3
"""Resolve, prepare, run, replay, and save source-bound closed-loop pilot attempts.

Each invocation creates a new immutable attempt directory. A worker checkpoint
is atomically replaced after each stage, and retries never overwrite failures.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import threading
import signal
import subprocess
import sys
import time
import uuid

import numpy as np

from contracts import ROOT, load_task, manifest_sha256
from task_models import (make_held_step_request, make_replay_request, objective,
                         source_scenario, validate_held_step_response,
                         validate_source_binding)
from capabilities import MANIFEST, resolve_graph, validate_resolved_graph, SIDECAR

HERE = Path(__file__).resolve().parent
MPC11 = ROOT / "benchmarks/reporting/mpc11"
sys.path.insert(0, str(MPC11))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        with temp.open("w") as stream:
            json.dump(json_safe(value), stream, indent=2, allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def json_safe(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    return value


def prepare_graph(task: dict, graph: dict, bridge: Path) -> tuple[object | None, dict]:
    validate_resolved_graph(graph)
    if graph["task_sha256"] != manifest_sha256(task): raise ValueError("resolved graph task binding changed")
    if not bridge.is_file(): raise ValueError("common execution bridge is missing")
    if graph["controller"].get("policy_factory"):
        factory_spec = graph["controller"]["policy_factory"]
        policy = load_policy_adapter(factory_spec)(task, task_sha256=graph["task_sha256"],
            controller_id=graph["controller"]["id"], action_profile_id=graph["action_profile_id"])
        details = getattr(policy, "preparation_receipt", {})
        return policy, {"status": "prepared", "controller_id": graph["controller"]["id"],
            "profile_id": graph["graph_id"], "policy_factory": factory_spec,
            "execution_binary_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
            "adapter_receipt": details, "nlp_solve_performed": False}
    adapter = graph["controller"]["adapter"]
    if adapter == "mpc11_nmpc":
        from nmpc import build_controller
        source = source_scenario(task)
        controller, metadata = build_controller(source, 0)
        runtime = {name: importlib.metadata.version(name) for name in ("do-mpc", "casadi", "numpy", "scipy")}
        return (controller, metadata), {"status": "prepared", "controller_id": graph["controller"]["id"],
            "profile_id": graph["graph_id"], "provider_versions": runtime,
            "solver_profile": graph["controller"]["solver"], "remaining_horizon": metadata["remaining_horizon"],
            "solver_interface": str(type(controller.S).__name__), "execution_binary_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
            "nlp_solve_performed": False}
    if adapter == "orbit_direct_shooting":
        import casadi as ca
        if not ca.has_nlpsol("ipopt"): raise RuntimeError("manifest-selected CasADi IPOPT provider is unavailable")
        runtime = {"casadi": importlib.metadata.version("casadi"), "numpy": importlib.metadata.version("numpy"),
                   "ipopt_plugin": "available through CasADi"}
        return None, {"status": "prepared", "controller_id": graph["controller"]["id"],
            "profile_id": graph["graph_id"], "provider_versions": runtime,
            "solver_profile": graph["controller"]["solver"], "plugin_prepared": "ipopt",
            "execution_binary_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(), "nlp_solve_performed": False}
    raise ValueError(f"manifest controller adapter {adapter!r} has no registered loader")


def controller_query(task: dict, graph: dict, state: np.ndarray, stage: int, previous, prepared=None):
    adapter = graph["controller"]["adapter"]
    if adapter == "orbit_direct_shooting":
        from orbit_nmpc import solve
        result = solve(task, state, stage, previous)
        control = result.get("predicted_controls", [[]])[0] if result.get("predicted_controls") else None
        controller_id = graph["controller"]["id"]
        return {"status": "accepted" if result["accepted"] else "rejected", "control": control,
                "policy_id": controller_id, "invocations": [
                    {"operation": "controller.solve", "module_id": controller_id,
                     "provider": "CasADi/IPOPT", "version": f"casadi{importlib.metadata.version('casadi')}; Ipopt plugin version unavailable",
                     "profile_id": result["solver_profile"]}],
                "solve_receipt": result, "next_guess": {"predicted_controls": result.get("predicted_controls"),
                    "predicted_mesh_physical": result.get("predicted_mesh_physical")}}
    if adapter != "mpc11_nmpc": raise ValueError(f"unsupported manifest controller adapter {adapter!r}")
    from nmpc import build_controller, initialize_guess, solve_update
    source = source_scenario(task)
    mpc, meta = prepared if stage == 0 and prepared is not None else build_controller(source, stage)
    guess = initialize_guess(mpc, source, stage, state / np.asarray([v["scale"] for v in task["model"]["states"]]), previous)
    result, next_primal = solve_update(mpc, source, stage,
        state / np.asarray([v["scale"] for v in task["model"]["states"]]), guess, meta)
    result["controller_id"] = source["controller_id"]
    return {"status": "accepted" if result["accepted"] else "rejected",
            "control": result["predicted_controls"][0] if result["predicted_controls"] else None,
            "policy_id": source["controller_id"], "invocations": [
                {"operation": "controller.solve", "module_id": source["controller_id"], "provider": "do-mpc/CasADi/IPOPT-MUMPS",
                 "version": f"do-mpc{importlib.metadata.version('do-mpc')}/casadi{importlib.metadata.version('casadi')}",
                 "profile_id": "mpc11-nominal-shrinking-radau3/1"}],
            "solve_receipt": result, "next_guess": next_primal}


def load_policy_adapter(spec: str):
    module_name, separator, function_name = spec.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("policy adapter must use module:function syntax")
    factory = getattr(importlib.import_module(module_name), function_name)
    return factory


def validate_policy_response(task: dict, task_hash: str, action_profile_id: str, query: dict) -> dict:
    if not isinstance(query, dict): raise ValueError("policy query response must be a mapping")
    if query.get("task_sha256") != task_hash:
        raise ValueError("policy response is not bound to the original full task hash")
    if query.get("action_profile_id") != action_profile_id:
        raise ValueError("policy response action profile differs from the task control domain")
    if query.get("status") not in {"accepted", "rejected", "unsupported", "failed"}:
        raise ValueError("policy response has an unsupported outcome status")
    if not isinstance(query.get("policy_id"), str) or not query["policy_id"]:
        raise ValueError("policy response must identify the selected policy")
    if not isinstance(query.get("invocations"), list):
        raise ValueError("policy response must include its actual invocation trace")
    for call in query["invocations"]:
        if not isinstance(call, dict) or not all(call.get(key) for key in ("operation", "module_id", "profile_id")) or not (call.get("provider") or call.get("provider_id")):
            raise ValueError("every policy invocation needs operation, module, provider, and profile identities")
    return query


def worker(task_name: str, attempt: Path, bridge: Path, policy_adapter: str | None = None,
           requested_controller_id: str | None = None, requested_action_profile_id: str | None = None,
           graph_path: Path | None = None) -> int:
    task = load_task(task_name); validate_source_binding(task)
    task_hash = manifest_sha256(task)
    if graph_path is None: raise ValueError("worker requires an admitted resolved graph")
    graph = json.loads(graph_path.read_text())
    if graph["task_sha256"] != task_hash: raise ValueError("resolved graph task hash differs from worker task")
    if policy_adapter and policy_adapter != graph["controller"].get("policy_factory"):
        raise ValueError("requested adapter factory differs from the manifest-selected policy adapter")
    if requested_controller_id and requested_controller_id != graph["controller"]["id"]:
        raise ValueError("requested controller differs from the resolved capability graph")
    expected_action_profile = graph["action_profile_id"]
    if requested_action_profile_id and requested_action_profile_id != expected_action_profile:
        raise ValueError("requested action profile differs from the resolved capability graph")
    prepared_controller, preparation = prepare_graph(task, graph, bridge)
    scales = np.asarray([s["scale"] for s in task["model"]["states"]])
    state = np.asarray([s["initial"] for s in task["model"]["states"]], dtype=float)
    controls = []; states = [state.tolist()]; stages = []; previous = None
    default_controller_id = graph["controller"]["id"]
    controller_id = requested_controller_id or default_controller_id
    action_profile_id = expected_action_profile
    policy = prepared_controller if graph["controller"].get("policy_factory") else None
    ledger = {"schema": "csl.closed-loop.attempt/1", "attempt_id": attempt.name,
        "task_id": task["task_id"], "task_sha256": task_hash, "source_sha256": task["source"]["sha256"],
        "model_id": task["model"]["model_id"], "action_profile_id": action_profile_id,
        "objective_id": task["objective"]["objective_id"], "controller_id": controller_id,
        "resolved_graph": graph, "preparation_receipt": preparation,
        "selected_initial_state_physical": state.tolist(), "original_intervals": task["episode"]["intervals"],
        "original_final_time": task["episode"]["final_time"], "status": "in-progress", "controls": controls,
        "physical_states": states, "stages": stages,
        "module_roles": {"vertex_lp": graph["inactive_roles"]["vertex_lp"],
                         "set_reducer": graph["inactive_roles"]["set_reducer"],
                         "representation": graph["inactive_roles"]["representation"],
                         "converter": graph["inactive_roles"]["converter"], "controller": controller_id,
                         "execution": graph["execution"]["id"]},
        "geometry_work": {"vertices": 0, "set_operations": 0, "claim": "pure NMPC; no representation comparison"},
        "resource_limits": {"requested": {"wall_seconds": 300, "address_space_bytes": 8 * 1024**3,
              "cpu_seconds": 300, "worker_count": 1, "solver_threads": 1},
            "enforced": {"wall_seconds": "subprocess timeout with process-group termination",
              "address_space_bytes": "POSIX RLIMIT_AS on worker process", "cpu_seconds": "POSIX RLIMIT_CPU on worker process",
              "worker_count": "one worker", "solver_threads": "environment requests one BLAS/OMP/MKL thread"},
            "observed": {"worker_pid": os.getpid(), "platform": platform.platform(), "python": platform.python_version(),
                "effective_cpu_seconds": resource.getrlimit(resource.RLIMIT_CPU),
                "effective_address_space_bytes": resource.getrlimit(resource.RLIMIT_AS),
                "thread_environment": {key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                "python_process_threads": threading.active_count()}},
        "assurance": "observed-state single-player policy trajectory; local NLP diagnostics; no global optimality, reachability, safety, or robustness guarantee"}
    atomic_json(attempt / "attempt.json", ledger)
    n = task["episode"]["intervals"]
    for j in range(n):
        started = time.monotonic()
        row = {"update_index": j, "absolute_time": j * task["episode"]["dt"],
               "observed_physical": state.tolist(), "observed_scaled": (state / scales).tolist(),
               "original_task_sha256": task_hash, "status": "started", "module_calls": [],
               "requested_modules": {"controller": {"id": graph["controller"]["id"], "version": graph["controller"]["version"]},
                   "vertex_lp": "not_used", "set_reducer": "not_used", "representation": "not_used", "converter": "not_used",
                   "execution": {"id": graph["execution"]["id"], "version": graph["execution"]["version"]}}}
        atomic_json(attempt / f"stage-{j:03d}.json", row)
        try:
            query = (policy.query(task["task_id"], state.tolist(), j) if policy is not None
                     else controller_query(task, graph, state, j, previous, prepared_controller))
            if policy is not None:
                query = validate_policy_response(task, task_hash, action_profile_id, query)
            row.update({"status": query["status"], "policy_id": query["policy_id"],
                        "controller_invocations": query["invocations"]})
            receipt = query.get("solve_receipt", query.get("query_receipt"))
            if receipt is not None: row["solve_receipt"] = receipt
            row["invoked_modules"] = [call["module_id"] for call in query["invocations"]]
            for field in ("predicted_sets", "recovered_control", "composition_id", "profile_id", "query_receipt",
                          "policy_semantics", "prediction_profile", "coverage"):
                if field in query: row[field] = query[field]
            if query["status"] != "accepted" or query["control"] is None:
                row["failure"] = "controller-rejected; no fallback action applied"
                stages.append(row); atomic_json(attempt / f"stage-{j:03d}.json", row)
                break
            action = [float(v) for v in query["control"]]
            held = make_held_step_request(task, state, action, j,
                hashlib.sha256((task_hash + json.dumps(controls, separators=(",", ":"))).encode()).hexdigest(),
                action_profile_id=action_profile_id)
            row["held_step_request"] = held
            req_path = attempt / f"execution-request-{j:03d}.json"; atomic_json(req_path, held["bridge_request"])
            response = execute_held_step_bridge(bridge, req_path, attempt, j, row)
            execution = validate_held_step_response(held, response)
            row["execution"] = execution
            row["module_calls"].append({"operation": "execution.advance", "provider": graph["execution"]["provider"],
                "module_id": graph["execution"]["id"], "version": "CSL 0.1.0",
                "profile_id": held["execution_profile_id"], "status": execution["status"],
                "accepted_steps": sum(r["accepted_steps"] for r in execution["integration_receipts"]),
                "rejected_steps": sum(r["rejected_steps"] for r in execution["integration_receipts"])})
            state = np.asarray(execution["physical_states"][-1])
            controls.append(action); states.append(state.tolist()); previous = query.get("next_guess")
            row["status"] = "applied-and-observed"; row["applied_control"] = action
        except Exception as error:
            row.update({"status": "failed", "failure": f"{type(error).__name__}: {error}"})
        row["stage_elapsed_seconds"] = time.monotonic() - started
        stages.append(row); atomic_json(attempt / f"stage-{j:03d}.json", row)
        ledger.update({"controls": controls, "physical_states": states, "stages": stages,
                       "completed_holds": len(controls), "status": "in-progress"})
        atomic_json(attempt / "attempt.json", ledger)
        if row["status"] != "applied-and-observed":
            break
    complete = len(controls) == n
    ledger.update({"status": "complete" if complete else "incomplete", "completed_holds": len(controls),
        "controls": controls, "physical_states": states, "stages": stages,
        "elapsed_seconds": sum(row.get("stage_elapsed_seconds", 0) for row in stages),
        "physical_objective": objective(task, states, controls) if complete else None,
        "controls_sha256": hashlib.sha256(json.dumps(controls, separators=(",", ":")).encode()).hexdigest()})
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if policy is not None:
        try:
            policy.close()
            ledger["policy_adapter_lifecycle"] = {"close": "complete", "adapter": policy_adapter}
        except Exception as error:
            ledger["policy_adapter_lifecycle"] = {"close": "failed", "adapter": policy_adapter,
                                                   "error": f"{type(error).__name__}: {error}"}
    ledger["resource_limits"]["observed"].update({"worker_wall_seconds": ledger["elapsed_seconds"],
        "worker_cpu_seconds": usage.ru_utime + usage.ru_stime, "worker_max_rss_kib": usage.ru_maxrss,
        "rss_accounting_scope": "worker process only; bridge subprocess peaks are not included"})
    atomic_json(attempt / "attempt.json", ledger)
    return 0 if complete else 2


def limited_worker():
    resource.setrlimit(resource.RLIMIT_CPU, (300, 301))
    cap = 8 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))


def checker_limits(cpu_seconds: int, address_space_bytes: int):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))


def _proc_peak_rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"): return int(line.split()[1])
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return None


def run_limited(command: list[str], stdout_path: Path, stderr_path: Path, *, wall_seconds: int,
                cpu_seconds: int, address_space_bytes: int) -> dict:
    """Run one isolated checker with measured wall time and process RSS high-water."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic(); peak_rss_kib = None
    with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
        process = subprocess.Popen(command, stdout=stdout_stream, stderr=stderr_stream,
            start_new_session=True, preexec_fn=lambda: checker_limits(cpu_seconds, address_space_bytes))
        status = "completed"
        while process.poll() is None:
            current = _proc_peak_rss_kib(process.pid)
            if current is not None: peak_rss_kib = max(peak_rss_kib or 0, current)
            if time.monotonic() - started >= wall_seconds:
                status = "timed_out"
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
                break
            time.sleep(0.02)
    elapsed = time.monotonic() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    if process.returncode not in (0, None) and status == "completed": status = "failed"
    return {"status": status, "return_code": process.returncode, "wall_seconds": elapsed,
        "requested": {"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
                      "address_space_bytes": address_space_bytes},
        "enforced": {"wall": "polling supervisor with process-group termination",
            "cpu": "POSIX RLIMIT_CPU on checker process", "address_space": "POSIX RLIMIT_AS on checker process",
            "process_group": True},
        "observed": {"peak_rss_kib": peak_rss_kib,
            "cpu_seconds": max(0.0, after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime),
            "memory_scope": "checker process only; no machine-wide or child-tree memory counter"}}


def run_task(task_name: str, root: Path, bridge: Path, policy_adapter: str | None = None,
             controller_id: str | None = None, action_profile_id: str | None = None) -> dict:
    attempt_started = time.monotonic()
    attempt_id = f"{task_name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    attempt = root / task_name / "attempts" / attempt_id
    attempt.mkdir(parents=True, exist_ok=False)
    requested = {"task_name": task_name, "controller_id": controller_id,
        "action_profile_id": action_profile_id, "policy_adapter": policy_adapter,
        "bridge": str(bridge)}
    atomic_json(attempt / "request.json", {"schema": "csl.closed-loop.run-request/1",
        "attempt_id": attempt_id, "requested": requested,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    initial = {"schema": "csl.closed-loop.attempt/1", "attempt_id": attempt_id,
        "task_id": None, "status": "resolving", "algorithm_status": "not_started",
        "overall_status": "incomplete", "completed_holds": 0, "requested": requested}
    atomic_json(attempt / "attempt.json", initial)
    try:
        task = load_task(task_name); validate_source_binding(task)
        requested_action_profile_id = action_profile_id
        action_profile_id = action_profile_id or task["control_domains"]["continuous"]["problem_id"]
        capability_manifest, graph = resolve_graph(task, action_profile_id, controller_id)
        selected_controller_id = graph["controller"]["id"]
        if policy_adapter and policy_adapter != graph["controller"].get("policy_factory"):
            raise ValueError("requested policy adapter is not the factory selected by the admitted capability graph")
        if not bridge.is_file(): raise ValueError(f"common execution bridge does not exist: {bridge}")
    except Exception as error:
        status = "refused" if isinstance(error, (ValueError, KeyError, FileNotFoundError)) else "preparation_failed"
        refusal = {**initial, "task_id": task.get("task_id") if "task" in locals() else None,
            "status": status, "algorithm_status": status, "overall_status": status,
            "refusal": {"type": type(error).__name__, "reason": str(error)},
            "completed_holds": 0, "actual_solver_invocations": 0}
        atomic_json(attempt / "resolution-refusal.json", refusal["refusal"] | {
            "schema": "csl.closed-loop.resolution-refusal/1", "requested": requested})
        atomic_json(attempt / "attempt.json", refusal)
        return {"task_id": refusal["task_id"] or task_name, "attempt": str(attempt),
            "status": status, "algorithm_status": status, "postcheck_status": "not_run",
            "render_status": "not_run", "overall_status": status, "completed_holds": 0}
    controller_id = selected_controller_id
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        HERE / "run_closed_loop.py", HERE / "orbit_nmpc.py", HERE / "task_models.py", HERE / "check_episode.py",
        HERE / "check_replay.py", HERE / "capabilities.py", MPC11 / "nmpc.py", MPC11 / "affine.py"]}
    source_hashes["docs/catalogue/closed-loop-pilot-capabilities-v1.json"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    mem_available = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"): mem_available = int(line.split()[1]) * 1024; break
    except OSError: pass
    manifest = {"schema": "csl.closed-loop.run-manifest/1", "attempt_id": attempt_id,
        "task_sha256": manifest_sha256(task), "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "source_hashes": source_hashes,
        "python": sys.version, "platform": platform.platform(), "bridge": str(bridge),
        "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
        "capability_manifest_sha256": SIDECAR.read_text().split()[0],
        "graph_id": graph["graph_id"], "graph_fingerprint": graph["graph_fingerprint"],
        "resolved_modules": graph["controller"], "execution_module": graph["execution"],
        "host_allocation": {"logical_cpus": os.cpu_count(), "mem_available_bytes_at_start": mem_available,
            "suite_memory_request_bytes": min(2 * 1024**3, int(mem_available * .75)) if mem_available else None,
            "suite_worker_count": 1, "suite_memory_enforcement": "none; per-process RLIMIT_AS only; no machine-wide limiter"},
        "claim": "one-off correctness pilot; clocks descriptive, no speed comparison"}
    atomic_json(attempt / "run-manifest.json", manifest)
    initial.update({"task_id": task["task_id"], "task_sha256": manifest_sha256(task),
        "status": "prepared", "resolved_graph_id": graph["graph_id"],
        "graph_fingerprint": graph["graph_fingerprint"]})
    atomic_json(attempt / "attempt.json", initial)
    graph_path = attempt / "resolved-graph.json"
    atomic_json(graph_path, graph)
    atomic_json(attempt / "resolution-receipt.json", {
        "schema": "csl.closed-loop.resolution-receipt/1",
        "capability_manifest_id": capability_manifest["manifest_id"],
        "capability_manifest_sha256": SIDECAR.read_text().split()[0],
        "task_id": task["task_id"], "task_sha256": manifest_sha256(task),
        "requested_controller_id": requested["controller_id"] or controller_id,
        "requested_action_profile_id": requested_action_profile_id or action_profile_id,
        "selected_controller_id": graph["controller"]["id"],
        "selected_controller_version": graph["controller"]["version"],
        "selected_execution_id": graph["execution"]["id"],
        "selected_execution_version": graph["execution"]["version"],
        "graph_id": graph["graph_id"], "graph_fingerprint": graph["graph_fingerprint"],
        "resolved_graph_path": "resolved-graph.json"})
    env = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"): env[key] = "1"
    command = [sys.executable, str(HERE / "run_closed_loop.py"), "--worker", "--task", task_name,
               "--attempt", str(attempt), "--bridge", str(bridge), "--graph", str(graph_path)]
    if policy_adapter: command.extend(["--policy-adapter", policy_adapter])
    if controller_id: command.extend(["--controller-id", controller_id])
    if action_profile_id: command.extend(["--action-profile-id", action_profile_id])
    started = time.monotonic(); proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, preexec_fn=limited_worker, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=300)
        status = "completed" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try: stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL); stdout, stderr = proc.communicate()
        status = "timed_out"
    (attempt / "worker-stdout.txt").write_text(stdout or "")
    (attempt / "worker-stderr.txt").write_text(stderr or "")
    final_path = attempt / "attempt.json"
    result = json.loads(final_path.read_text()) if final_path.exists() else {"status": "incomplete", "completed_holds": 0}
    prior_ledger_status = result.get("status")
    if status != "completed" and prior_ledger_status not in {"complete", "incomplete", "refused", "preparation_failed"}:
        result["status"] = "incomplete"
    if status != "completed":
        result["terminal_supervisor_failure"] = {"status": status, "return_code": proc.returncode,
            "prior_ledger_status": prior_ledger_status, "preserved_stage_records": True,
            "reason": "worker stopped before writing terminal attempt status" if prior_ledger_status == "in-progress" else None}
    result["supervisor"] = {"status": status, "return_code": proc.returncode,
        "wall_seconds": time.monotonic() - started, "termination_scope": "worker process group",
        "stdout": "worker-stdout.txt", "stderr": "worker-stderr.txt"}
    if status == "completed" and result.get("status") == "complete":
        try:
            replay_attempt(task, result, attempt, bridge)
        except Exception as error:
            result["independent_replay"] = {"common": {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                "tight": {"status": "not_run", "reason": "common postcheck could not be prepared"}}
            result["postcheck_failure"] = {"type": type(error).__name__, "reason": str(error),
                "retained_controls_and_episode": True}
            try:
                render_attempt(task, result, attempt)
            except Exception as render_error:
                result["render"] = {"status": "failed", "error": f"{type(render_error).__name__}: {render_error}"}
    elif result.get("physical_states"):
        result["sampled_constraint_diagnostics"] = physical_constraints(task, result["physical_states"], result["controls"])
    result["end_to_end"] = {"wall_seconds": time.monotonic() - attempt_started,
        "scope": "worker launch, execution, independent CSL replay, bounded checker processes, and rendering",
        "worker_wall_seconds": result["supervisor"]["wall_seconds"],
        "performance_claim": "descriptive single attempt; no speed comparison"}
    result.update(derive_outcome_status(result))
    atomic_json(final_path, result)
    return {"task_id": task["task_id"], "attempt": str(attempt), "status": status,
            "algorithm_status": result.get("algorithm_status"),
            "postcheck_status": result.get("postcheck_status"), "render_status": result.get("render_status"),
            "overall_status": result.get("overall_status"),
            "completed_holds": result.get("completed_holds", 0), "task_sha256": manifest_sha256(task)}


def derive_outcome_status(result: dict) -> dict:
    algorithm = result.get("algorithm_status", result.get("status", "incomplete"))
    replay = result.get("independent_replay", {})
    postcheck = "complete" if all(replay.get(name, {}).get("status") == "complete"
                                   for name in ("common", "tight")) else ("failed" if replay else "not_run")
    render = result.get("render", {}).get("status", "not_run")
    overall = "complete" if algorithm == "complete" and postcheck == "complete" and render == "complete" else "incomplete"
    return {"algorithm_status": algorithm, "postcheck_status": postcheck,
            "render_status": render, "overall_status": overall}


def execute_held_step_bridge(bridge: Path, request_path: Path, attempt: Path,
                             stage_index: int, row: dict, timeout_seconds: int = 120) -> dict:
    """Run one execution slice and persist both streams before parsing its response."""
    started = time.monotonic()
    stdout_path = attempt / f"execution-stdout-{stage_index:03d}.txt"
    stderr_path = attempt / f"execution-stderr-{stage_index:03d}.txt"

    def output_text(value):
        if value is None: return ""
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    try:
        proc = subprocess.run([str(bridge), str(request_path)], capture_output=True, text=True, timeout=timeout_seconds)
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        row["execution_process"] = {"status": "completed" if proc.returncode == 0 else "failed",
            "return_code": proc.returncode, "wall_seconds": time.monotonic() - started,
            "stdout": stdout_path.name, "stderr": stderr_path.name}
        if proc.returncode != 0:
            raise RuntimeError(f"held-step bridge exited {proc.returncode}; see {stderr_path.name}")
    except subprocess.TimeoutExpired as error:
        stdout_path.write_text(output_text(error.stdout), encoding="utf-8")
        stderr_path.write_text(output_text(error.stderr), encoding="utf-8")
        row["execution_process"] = {"status": "timed_out", "return_code": None,
            "wall_seconds": time.monotonic() - started, "stdout": stdout_path.name,
            "stderr": stderr_path.name, "timeout_seconds": timeout_seconds}
        raise
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        row["execution_process"]["response_parse_failure"] = f"{type(error).__name__}: {error}"
        raise


def physical_constraints(task: dict, states, controls) -> dict:
    x = np.asarray(states, dtype=float); u = np.asarray(controls, dtype=float)
    bounds = [row["bounds"] for row in task["model"]["states"]]
    state_violations = []
    for i, bound in enumerate(bounds):
        state_violations.append(0.0 if bound is None else float(max(np.max(np.maximum(bound[0] - x[:, i], 0)),
            np.max(np.maximum(x[:, i] - bound[1], 0)))) if len(x) else 0.0)
    action_bounds = np.asarray(task["control_domains"]["continuous"]["bounds"])
    control_violation = float(max(np.max(np.maximum(action_bounds[:, 0, None] - u.T, 0)),
        np.max(np.maximum(u.T - action_bounds[:, 1, None], 0)))) if len(u) else 0.0
    domain = {"minimum_radius_km": float(x[:, 0].min())} if "ORBIT" in task["model"]["case_id"] and len(x) else {}
    if domain:
        domain["positive_radius"] = domain["minimum_radius_km"] > 0
    return {"sampled_state_bound_violation_by_coordinate": state_violations,
            "control_bound_violation_by_coordinate":
                (np.maximum(np.maximum(action_bounds[:, 0] - u.min(axis=0), u.max(axis=0) - action_bounds[:, 1]), 0).tolist() if len(u) else []),
            "control_bound_violation_max": control_violation, "model_domain": domain,
            "scope": "sampled endpoints and controls; no continuous-time enclosure"}


def replay_attempt(task: dict, result: dict, attempt: Path, bridge: Path, tag: str | None = None) -> None:
    postcheck_started = time.monotonic()
    controls = result["controls"]
    witness = hashlib.sha256((result["task_sha256"] + json.dumps(controls, separators=(",", ":"))).encode()).hexdigest()
    replay_rows = {}
    for label, tight in (("common", False), ("tight", True)):
        request = make_replay_request(task, controls, witness, sensitivity=tight)
        path = attempt / (f"{tag}-{label}" if tag else f"full-replay-{label}"); path.mkdir(exist_ok=False)
        atomic_json(path / "request.json", request)
        process_record = run_limited([str(bridge), str(path / "request.json")], path / "stdout.json",
            path / "stderr.txt", wall_seconds=5, cpu_seconds=5, address_space_bytes=1024**3)
        try:
            stdout = (path / "stdout.json").read_text()
            row = json.loads(stdout) if stdout else {"status": "no-output"}
            row["checker_process"] = process_record
            if process_record["return_code"] != 0 or row.get("status") != "complete":
                row["status"] = "failed-or-incomplete"
            else:
                sub = request["report_subintervals_per_hold"]
                check_input = {"task": task, "task_sha256": result["task_sha256"], "controls": controls,
                    "controls_sha256": request["controls_sha256"], "report_subintervals_per_hold": sub,
                    "replay_physical_states": row["physical_states"],
                    "applied_hold_endpoints": result["physical_states"], "scenario": request["scenario"]}
                atomic_json(path / "check-input.json", check_input)
                check_path = HERE / "check_episode.py"
                check_process = run_limited([sys.executable, str(check_path), "--input", str(path / "check-input.json"),
                    "--output", str(path / "independent-check.json")], path / "checker-stdout.txt",
                    path / "checker-stderr.txt", wall_seconds=5, cpu_seconds=5, address_space_bytes=1024**3)
                row["independent_checker_process"] = check_process
                if check_process["return_code"] == 0:
                    checked = json.loads((path / "independent-check.json").read_text())
                    row["hold_endpoint_max_abs_difference"] = checked["hold_endpoint_max_abs_difference_from_applied_execution"]
                    row["independent_physical_objective"] = checked["independent_objective"]
                    row["objective_adapter"] = checked["task_adapter_objective"]
                    row["objective_difference"] = checked["objective_difference"]
                    row["sampled_constraint_diagnostics"] = {"state_bound_violation_by_coordinate": checked["sampled_physical_state_bound_violation_by_coordinate"],
                        "hold_endpoint_state_bound_violation_by_coordinate": checked["hold_endpoint_state_bound_violation_by_coordinate"],
                        "sampled_state_count": checked["sampled_state_count"], "sampled_state_scope": checked["sampled_state_scope"],
                        "control_bound_violation_by_coordinate": checked["control_bound_violation_by_coordinate"], "model_domain": checked["model_domain"]}
                    if label == "common": row["independent_fixed_rk4"] = checked["fixed_rk4"]
                else:
                    row["status"] = "inconclusive-checker-failure"
            atomic_json(path / "record.json", row)
            replay_rows[label] = {"status": row["status"], "hold_endpoint_max_abs_difference": row.get("hold_endpoint_max_abs_difference"),
                                  "objective_difference": row.get("objective_difference")}
        except Exception as error:
            (path / "exception.txt").write_text(f"{type(error).__name__}: {error}\n")
            atomic_json(path / "record.json", {"status": "failed", "error": str(error), "checker_process": process_record})
            replay_rows[label] = {"status": "failed", "error": str(error)}
    result["independent_replay"] = replay_rows
    result["sampled_constraint_diagnostics"] = physical_constraints(task, result["physical_states"], controls)
    try:
        render_attempt(task, result, attempt, tag)
    except Exception as error:
        result["render"] = {"status": "failed", "error": str(error)}
    outcome = derive_outcome_status(result)
    result.update(outcome)
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
        "benchmarks/reporting/closed_loop/run_closed_loop.py", "benchmarks/reporting/closed_loop/check_episode.py",
        "benchmarks/reporting/closed_loop/check_replay.py", "benchmarks/reporting/closed_loop/task_models.py"]}
    checker_id = tag or "initial"
    postcheck = {"schema": "csl.closed-loop.postcheck/1", "postcheck_id": checker_id,
        "original_attempt_id": result["attempt_id"], "task_id": result["task_id"],
        "task_sha256": result["task_sha256"], "source_sha256": result["source_sha256"],
        "controls_sha256": result["controls_sha256"], "witness_sha256": witness,
        "checker_source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "checker_source_hashes": source_hashes, "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
        "results": replay_rows, "postcheck_status": outcome["postcheck_status"],
        "render_status": outcome["render_status"], "overall_status": outcome["overall_status"],
        "requested_checker_budget": {"wall_seconds": 5, "cpu_seconds": 5,
            "address_space_bytes": 1024**3},
        "memory_scope": "each replay and independent Python checker process receives 1 GiB RLIMIT_AS; no machine-wide or descendant-tree memory counter",
        "postcheck_wall_seconds": time.monotonic() - postcheck_started,
        "claim": "independent numerical replay and fixed-RK4 diagnostic; no validated enclosure"}
    postcheck_path = attempt / f"postcheck-{checker_id}.json"
    atomic_json(postcheck_path, postcheck)
    result["postcheck_record"] = postcheck_path.name
    if tag:
        with (attempt / "replay-retries.jsonl").open("a") as stream:
            stream.write(json.dumps({"postcheck_id": checker_id, "postcheck_record": postcheck_path.name,
                "task_sha256": result["task_sha256"], "controls_sha256": result["controls_sha256"]}, allow_nan=False) + "\n")
            stream.flush(); os.fsync(stream.fileno())


def render_attempt(task: dict, result: dict, attempt: Path, tag: str | None = None) -> None:
    import matplotlib.pyplot as plt
    states = np.asarray(result["physical_states"]); controls = np.asarray(result["controls"])
    dt = task["episode"]["dt"]; times = np.arange(len(states)) * dt
    fig, axes = plt.subplots(len(task["model"]["states"]), 1, figsize=(9, 2.2 * len(task["model"]["states"])), sharex=True)
    axes = np.atleast_1d(axes)
    for index, (ax, field) in enumerate(zip(axes, task["model"]["states"])):
        ax.plot(times, states[:, index], color="#2463a6", linewidth=1.8)
        ax.set_ylabel(f"{field['name']} ({field['unit']})"); ax.grid(alpha=.25)
    axes[-1].set_xlabel(f"Time ({task['episode']['time_unit']})")
    short_name = {"SYN-NL-LV-01": "Lotka–Volterra", "SYN-NL-FUEL-01": "Fuel", "ENV717-EARTH-ORBIT-CONTINUOUS-01": "Earth orbit"}[task["model"]["case_id"]]
    fig.suptitle(f"{short_name} observed-state NMPC, {result.get('completed_holds', 0)}/{task['episode']['intervals']} holds")
    trajectory_name = f"{tag}-trajectory.png" if tag else "trajectory.png"
    controls_name = f"{tag}-controls.png" if tag else "controls.png"
    fig.tight_layout(); fig.savefig(attempt / trajectory_name, dpi=150); plt.close(fig)
    if len(controls):
        fig, ax = plt.subplots(figsize=(8, 3)); control_times = (np.arange(len(controls)) + .5) * dt
        for i, field in enumerate(task["model"]["controls"]): ax.step(control_times, controls[:, i], where="mid", label=f"{field['name']} ({field['unit']})")
        ax.set_xlabel(f"Time ({task['episode']['time_unit']})"); ax.set_ylabel("Applied input"); ax.grid(alpha=.25); ax.legend()
        fig.tight_layout(); fig.savefig(attempt / controls_name, dpi=150); plt.close(fig)
    phase_name = f"{tag}-phase.png" if tag else "phase.png"
    planes = []
    case = task["model"]["case_id"]
    if case == "SYN-NL-FUEL-01":
        for plane in task["coordinate_maps"]["requested_physical_planes"]:
            planes.append((plane["names"], plane["units"], plane["indices"]))
        target = task["objective"]["source_definition"]["terminal_target"]
    elif case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        planes.append((["r", "omega"], ["km", "rad/s"], [0, 3]))
        target = None
    else:
        planes.append(([field["name"] for field in task["model"]["states"]],
                       [field["unit"] for field in task["model"]["states"]], [0, 1]))
        target = task["objective"]["source_definition"]["terminal_target"]
    fig, axes = plt.subplots(1, len(planes), figsize=(5 * len(planes), 4), squeeze=False)
    for ax, (names, units, indices) in zip(axes[0], planes):
        i, j = indices
        ax.plot(states[:, i], states[:, j], color="#2463a6", linewidth=1.8, label="observed trajectory")
        ax.scatter(states[0, i], states[0, j], marker="*", s=100, color="#29844a", label="start", zorder=3)
        if target is not None:
            ax.scatter(target[i], target[j], marker="D", s=55, color="#e0a21a", label="soft objective target", zorder=3)
        elif case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
            goal = task["objective"]["target"]
            ax.scatter(goal["radius_km"], goal["angular_rate_rad_s"], marker="D", s=55,
                       color="#e0a21a", label="soft objective target", zorder=3)
        ax.scatter(states[-1, i], states[-1, j], marker="x", s=70, color="#b73a3a", label="end", zorder=4)
        ax.set_xlabel(f"{names[0]} ({units[0]})"); ax.set_ylabel(f"{names[1]} ({units[1]})")
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle(f"{short_name} source-defined phase projections")
    fig.tight_layout(); fig.savefig(attempt / phase_name, dpi=150); plt.close(fig)
    result["render"] = {"status": "complete", "plots": [trajectory_name, phase_name] + ([controls_name] if len(controls) else []),
        "phase_projections": [{"coordinates": names, "units": units, "indices": indices} for names, units, indices in planes],
        "target_marker": "soft objective reference, not a terminal constraint"}


def write_coverage(root: Path) -> Path:
    rows = []
    for path in sorted(root.glob("*/attempts/*/attempt.json")):
        try: record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError): continue
        replay = record.get("independent_replay", {})
        postchecks = []
        for postcheck_path in sorted(path.parent.glob("postcheck-*.json"), key=lambda item: item.stat().st_mtime_ns):
            try: postchecks.append(json.loads(postcheck_path.read_text()))
            except (OSError, json.JSONDecodeError): continue
        render_records = []
        for render_path in sorted(path.parent.glob("render-retry-*.json"), key=lambda item: item.stat().st_mtime_ns):
            try: render_records.append(json.loads(render_path.read_text()))
            except (OSError, json.JSONDecodeError): continue
        if postchecks:
            latest = postchecks[-1].get("results", {})
            replay = {"common": latest.get("common", {}), "tight": latest.get("tight", {})}
        reconciliation_path = path.parent / "supervisor-reconciliation.json"
        reconciliation = json.loads(reconciliation_path.read_text()) if reconciliation_path.exists() else None
        algorithm_status = reconciliation.get("derived_terminal_status") if reconciliation else record.get("algorithm_status", record.get("status"))
        replay_statuses = [replay.get(name, {}).get("status") for name in ("common", "tight")]
        postcheck_status = ("complete" if replay_statuses == ["complete", "complete"] else
                            ("failed" if any(status not in (None, "not_run") for status in replay_statuses) else "not_run"))
        render_status = record.get("render", {}).get("status", "not_run")
        if postchecks:
            latest_check = postchecks[-1]
            postcheck_status = latest_check.get("postcheck_status", postcheck_status)
            render_status = latest_check.get("render_status", render_status)
        if render_records:
            render_status = render_records[-1].get("status", render_records[-1].get("render", {}).get("status", render_status))
        overall_status = coverage_overall_status(algorithm_status, postcheck_status, render_status)
        rows.append({"attempt_id": record.get("attempt_id"), "task_id": record.get("task_id"),
            "task_sha256": record.get("task_sha256"),
            "status": overall_status, "overall_status": overall_status,
            "algorithm_status": algorithm_status, "postcheck_status": postcheck_status,
            "render_status": render_status, "ledger_status": record.get("status"),
            "supervisor_reconciliation": reconciliation,
            "completed_holds": record.get("completed_holds", 0), "original_intervals": record.get("original_intervals"),
            "physical_objective": record.get("physical_objective"),
            "common_replay": replay.get("common", {}).get("status"), "tight_replay": replay.get("tight", {}).get("status"),
            "postcheck_records": [row.get("postcheck_id") for row in postchecks],
            "graph_id": record.get("resolved_graph", {}).get("graph_id"),
            "graph_fingerprint": record.get("resolved_graph", {}).get("graph_fingerprint"),
            "attempt_record": str(path.relative_to(root))})
    for path in sorted(root.glob("*/attempts/*/runner-startup-failure.json")):
        try: failure = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError): continue
        rows.append({"attempt_id": failure.get("attempt_id"), "task_id": failure.get("task_id"),
            "status": failure.get("status"), "overall_status": failure.get("status"),
            "algorithm_status": failure.get("status"), "postcheck_status": "not_run",
            "render_status": "not_run", "completed_holds": failure.get("completed_holds", 0),
            "failure": failure.get("failure"), "actual_solver_invocations": failure.get("actual_solver_invocations", 0),
            "attempt_record": str(path.relative_to(root))})
    rows.sort(key=lambda row: row.get("attempt_id", ""))
    coverage = {"schema": "csl.closed-loop.coverage/1", "source_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "attempts": rows,
        "representation_claim": "pure NMPC graph bypasses set modules; zero set work is recorded and no representation performance is inferred"}
    output = root / ("coverage-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8] + ".json")
    atomic_json(output, coverage)
    return output


def coverage_overall_status(algorithm: str, postcheck: str, render: str) -> str:
    """Derive coverage status from the latest displayed phase receipts."""
    if algorithm == postcheck == render == "complete":
        return "complete"
    if algorithm not in ("complete", "incomplete"):
        return algorithm
    return "incomplete"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=["syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01", "all"], default="all")
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "reports/closed-loop-pilot")
    parser.add_argument("--worker", action="store_true"); parser.add_argument("--attempt", type=Path)
    parser.add_argument("--graph", type=Path, help="resolved, fingerprinted capability graph for worker mode")
    parser.add_argument("--policy-adapter", help="persistent in-process policy factory as module:function")
    parser.add_argument("--controller-id", help="selected policy identity passed to an external adapter")
    parser.add_argument("--action-profile-id", help="task-declared continuous or finite per-step action-domain identity")
    parser.add_argument("--replay-only", type=Path, help="independently replay a saved complete attempt without rerunning its controller")
    parser.add_argument("--render-only", type=Path, help="render source-defined views for a saved complete attempt without changing its record")
    parser.add_argument("--coverage-only", action="store_true", help="write a coverage index from saved append-only attempt records")
    args = parser.parse_args()
    if args.worker:
        if args.bridge is None or args.attempt is None or args.graph is None: parser.error("worker mode requires --bridge, --attempt, and --graph")
        return worker(args.task, args.attempt, args.bridge.resolve(), args.policy_adapter, args.controller_id,
                      args.action_profile_id, args.graph.resolve())
    if args.bridge is None and not args.render_only and not args.coverage_only: parser.error("--bridge is required")
    if args.coverage_only:
        path = write_coverage(args.output_root.resolve()); print(json.dumps({"coverage_record": str(path)})); return 0
    if args.render_only:
        attempt = args.render_only.resolve(); result = json.loads((attempt / "attempt.json").read_text())
        task_name = {"syn-nl-lv-01/continuous-receding/1": "syn-nl-lv-01",
                     "env717-earth-orbit/continuous-receding/1": "earth-orbit",
                     "syn-nl-fuel-01/continuous-receding/1": "syn-nl-fuel-01"}.get(result.get("task_id"))
        if task_name is None: parser.error("saved attempt has an unknown task identity")
        task = load_task(task_name); validate_source_binding(task)
        if result.get("task_sha256") != manifest_sha256(task) or result.get("status") != "complete":
            parser.error("render-only requires a complete attempt bound to the current immutable task")
        tag = "render-retry-" + uuid.uuid4().hex[:8]
        try:
            render_attempt(task, result, attempt, tag)
            render_status = "complete"
            error = None
        except Exception as failure:
            result["render"] = {"status": "failed", "error": f"{type(failure).__name__}: {failure}"}
            render_status = "failed"
            error = result["render"]["error"]
        source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
            "benchmarks/reporting/closed_loop/run_closed_loop.py", "benchmarks/reporting/closed_loop/task_models.py"]}
        render_record = {"schema": "csl.closed-loop.render/1", "render_id": tag,
            "attempt_id": result["attempt_id"], "task_sha256": result["task_sha256"],
            "controls_sha256": result["controls_sha256"], "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "renderer_source_hashes": source_hashes,
            "render": result["render"], "status": render_status, "error": error}
        atomic_json(attempt / f"{tag}.json", render_record)
        print(json.dumps(render_record, indent=2))
        return 0 if render_status == "complete" else 1
    if args.replay_only:
        attempt = args.replay_only.resolve(); result = json.loads((attempt / "attempt.json").read_text())
        task_name = {"syn-nl-lv-01/continuous-receding/1": "syn-nl-lv-01",
                     "env717-earth-orbit/continuous-receding/1": "earth-orbit",
                     "syn-nl-fuel-01/continuous-receding/1": "syn-nl-fuel-01"}.get(result.get("task_id"))
        if task_name is None: parser.error("existing attempt has an unknown task identity")
        task = load_task(task_name); validate_source_binding(task)
        if result.get("task_sha256") != manifest_sha256(task) or result.get("status") != "complete":
            parser.error("replay-only requires a complete attempt bound to the current immutable task")
        tag = "full-replay-retry-" + uuid.uuid4().hex[:8]
        replay_attempt(task, result, attempt, args.bridge.resolve(), tag)
        print(json.dumps({"attempt": str(attempt), "replay_retry": tag, "status": result["overall_status"],
                          "algorithm_status": result["algorithm_status"],
                          "postcheck_status": result["postcheck_status"],
                          "render_status": result["render_status"],
                          "independent_replay": result["independent_replay"]}, indent=2))
        return 0 if result["overall_status"] == "complete" else 1
    names = ["syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"] if args.task == "all" else [args.task]
    rows = [run_task(name, args.output_root.resolve(), args.bridge.resolve(), args.policy_adapter,
                     args.controller_id, args.action_profile_id) for name in names]
    coverage_path = write_coverage(args.output_root.resolve())
    print(json.dumps({"schema": "csl.closed-loop.coverage/1", "coverage_record": str(coverage_path), "attempts": rows,
        "coverage": [{"task_id": row["task_id"], "algorithm_status": row.get("algorithm_status"),
            "postcheck_status": row.get("postcheck_status"), "render_status": row.get("render_status"),
            "overall_status": row.get("overall_status"), "completed_holds": row["completed_holds"],
            "actual_observed_state_updates": row["completed_holds"]} for row in rows]}, indent=2))
    return 0 if all(row.get("overall_status") == "complete" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

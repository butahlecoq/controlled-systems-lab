#!/usr/bin/env python3
"""Resolve, prepare, run, replay, and save source-bound closed-loop pilot attempts.

Each invocation creates a new immutable attempt directory. A worker checkpoint
is atomically replaced after each stage, and retries never overwrite failures.
"""
from __future__ import annotations

import argparse
import hashlib
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

HERE = Path(__file__).resolve().parent
MPC11 = ROOT / "benchmarks/reporting/mpc11"
sys.path.insert(0, str(MPC11))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    with temp.open("w") as stream:
        json.dump(json_safe(value), stream, indent=2, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def json_safe(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    return value


def controller_query(task: dict, state: np.ndarray, stage: int, previous):
    case = task["model"]["case_id"]
    if case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        from orbit_nmpc import solve
        result = solve(task, state, stage, previous)
        control = result.get("predicted_controls", [[]])[0] if result.get("predicted_controls") else None
        return {"status": "accepted" if result["accepted"] else "rejected", "control": control,
                "policy_id": "syn-nl-orbit-01/source-cost-direct-shooting/1", "invocations": [
                    {"operation": "controller.solve", "module_id": "syn-nl-orbit-01/source-cost-direct-shooting/1",
                     "provider": "CasADi/IPOPT", "profile_id": result["solver_profile"]}],
                "solve_receipt": result, "next_guess": {"predicted_controls": result.get("predicted_controls"),
                    "predicted_mesh_physical": result.get("predicted_mesh_physical")}}
    from nmpc import build_controller, initialize_guess, solve_update
    source = source_scenario(task)
    mpc, meta = build_controller(source, stage)
    guess = initialize_guess(mpc, source, stage, state / np.asarray([v["scale"] for v in task["model"]["states"]]), previous)
    result, next_primal = solve_update(mpc, source, stage,
        state / np.asarray([v["scale"] for v in task["model"]["states"]]), guess, meta)
    result["controller_id"] = source["controller_id"]
    return {"status": "accepted" if result["accepted"] else "rejected",
            "control": result["predicted_controls"][0] if result["predicted_controls"] else None,
            "policy_id": source["controller_id"], "invocations": [
                {"operation": "controller.solve", "module_id": source["controller_id"], "provider": "do-mpc/CasADi/IPOPT-MUMPS",
                 "profile_id": "mpc11-nominal-shrinking-radau3/1"}],
            "solve_receipt": result, "next_guess": next_primal}


def worker(task_name: str, attempt: Path, bridge: Path) -> int:
    task = load_task(task_name); validate_source_binding(task)
    task_hash = manifest_sha256(task)
    scales = np.asarray([s["scale"] for s in task["model"]["states"]])
    state = np.asarray([s["initial"] for s in task["model"]["states"]], dtype=float)
    controls = []; states = [state.tolist()]; stages = []; previous = None
    case = task["model"]["case_id"]
    controller_id = "syn-nl-orbit-01/source-cost-direct-shooting/1" if "ORBIT" in case else source_scenario(task)["controller_id"]
    ledger = {"schema": "csl.closed-loop.attempt/1", "attempt_id": attempt.name,
        "task_id": task["task_id"], "task_sha256": task_hash, "source_sha256": task["source"]["sha256"],
        "model_id": task["model"]["model_id"], "action_profile_id": task["control_domains"]["continuous"]["problem_id"],
        "objective_id": task["objective"]["objective_id"], "controller_id": controller_id,
        "selected_initial_state_physical": state.tolist(), "original_intervals": task["episode"]["intervals"],
        "original_final_time": task["episode"]["final_time"], "status": "in-progress", "controls": controls,
        "physical_states": states, "stages": stages,
        "module_roles": {"vertex_lp": "not_used", "set_reducer": "not_used", "representation": "not_used",
                         "converter": "not_used", "controller": controller_id,
                         "execution": task["episode"]["execution"].get("profile_id", "common-adaptive-replay/CSL-simulation-rk4-step-doubling/1")},
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
               "requested_modules": {"controller": controller_id, "vertex_lp": "not_used", "set_reducer": "not_used",
                   "representation": "not_used", "converter": "not_used", "execution": "CSL::simulation"}}
        atomic_json(attempt / f"stage-{j:03d}.json", row)
        try:
            query = controller_query(task, state, j, previous)
            row.update({"status": query["status"], "policy_id": query["policy_id"],
                        "controller_invocations": query["invocations"], "solve_receipt": query["solve_receipt"]})
            row["invoked_modules"] = [call["module_id"] for call in query["invocations"]]
            if query["status"] != "accepted" or query["control"] is None:
                row["failure"] = "controller-rejected; no fallback action applied"
                stages.append(row); atomic_json(attempt / f"stage-{j:03d}.json", row)
                break
            action = [float(v) for v in query["control"]]
            held = make_held_step_request(task, state, action, j,
                hashlib.sha256((task_hash + json.dumps(controls, separators=(",", ":"))).encode()).hexdigest())
            row["held_step_request"] = held
            req_path = attempt / f"execution-request-{j:03d}.json"; atomic_json(req_path, held["bridge_request"])
            proc = subprocess.run([str(bridge), str(req_path)], capture_output=True, text=True, timeout=120)
            response = json.loads(proc.stdout)
            execution = validate_held_step_response(held, response)
            row["execution"] = execution
            row["module_calls"].append({"operation": "execution.advance", "provider": "CSL::simulation",
                "module_id": "CSL::simulation/adaptive-rk4-step-doubling/1",
                "profile_id": held["execution_profile_id"], "status": execution["status"],
                "accepted_steps": sum(r["accepted_steps"] for r in execution["integration_receipts"]),
                "rejected_steps": sum(r["rejected_steps"] for r in execution["integration_receipts"])})
            state = np.asarray(execution["physical_states"][-1])
            controls.append(action); states.append(state.tolist()); previous = query["next_guess"]
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
    ledger["resource_limits"]["observed"].update({"worker_wall_seconds": ledger["elapsed_seconds"],
        "worker_cpu_seconds": usage.ru_utime + usage.ru_stime, "worker_max_rss_kib": usage.ru_maxrss,
        "rss_accounting_scope": "worker process only; bridge subprocess peaks are not included"})
    atomic_json(attempt / "attempt.json", ledger)
    return 0 if complete else 2


def limited_worker():
    resource.setrlimit(resource.RLIMIT_CPU, (300, 301))
    cap = 8 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))


def run_task(task_name: str, root: Path, bridge: Path) -> dict:
    task = load_task(task_name); validate_source_binding(task)
    attempt_id = f"{task_name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    attempt = root / task_name / "attempts" / attempt_id
    attempt.mkdir(parents=True, exist_ok=False)
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        HERE / "run_closed_loop.py", HERE / "orbit_nmpc.py", HERE / "task_models.py",
        MPC11 / "nmpc.py", MPC11 / "affine.py"]}
    manifest = {"schema": "csl.closed-loop.run-manifest/1", "attempt_id": attempt_id,
        "task_sha256": manifest_sha256(task), "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "source_hashes": source_hashes,
        "python": sys.version, "platform": platform.platform(), "bridge": str(bridge),
        "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
        "claim": "one-off correctness pilot; clocks descriptive, no speed comparison"}
    atomic_json(attempt / "run-manifest.json", manifest)
    env = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"): env[key] = "1"
    command = [sys.executable, str(HERE / "run_closed_loop.py"), "--worker", "--task", task_name,
               "--attempt", str(attempt), "--bridge", str(bridge)]
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
    result["supervisor"] = {"status": status, "return_code": proc.returncode,
        "wall_seconds": time.monotonic() - started, "termination_scope": "worker process group",
        "stdout": "worker-stdout.txt", "stderr": "worker-stderr.txt"}
    if status == "completed" and result.get("status") == "complete":
        replay_attempt(task, result, attempt, bridge)
    elif result.get("physical_states"):
        result["sampled_constraint_diagnostics"] = physical_constraints(task, result["physical_states"], result["controls"])
    atomic_json(final_path, result)
    return {"task_id": task["task_id"], "attempt": str(attempt), "status": status,
            "completed_holds": result.get("completed_holds", 0), "task_sha256": manifest_sha256(task)}


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
    from check_replay import independent_cost, rk4_step
    controls = result["controls"]
    witness = hashlib.sha256((result["task_sha256"] + json.dumps(controls, separators=(",", ":"))).encode()).hexdigest()
    replay_rows = {}
    for label, tight in (("common", False), ("tight", True)):
        request = make_replay_request(task, controls, witness, sensitivity=tight)
        path = attempt / (f"{tag}-{label}" if tag else f"full-replay-{label}"); path.mkdir(exist_ok=False)
        atomic_json(path / "request.json", request)
        started = time.monotonic()
        try:
            proc = subprocess.run([str(bridge), str(path / "request.json")], capture_output=True, text=True,
                                  timeout=300, check=False)
            (path / "stdout.json").write_text(proc.stdout); (path / "stderr.txt").write_text(proc.stderr)
            row = json.loads(proc.stdout) if proc.stdout else {"status": "no-output"}
            row["process_return_code"] = proc.returncode
            row["elapsed_seconds"] = time.monotonic() - started
            if proc.returncode != 0 or row.get("status") != "complete":
                row["status"] = "failed-or-incomplete"
            else:
                sub = request["report_subintervals_per_hold"]
                endpoints = np.asarray(row["physical_states"])[np.arange(task["episode"]["intervals"] + 1) * sub]
                expected = np.asarray(result["physical_states"])
                row["hold_endpoint_max_abs_difference"] = np.max(np.abs(endpoints - expected), axis=0).tolist()
                source = request["scenario"]
                row["independent_physical_objective"] = independent_cost(task, endpoints.tolist(), controls, source)
                row["objective_adapter"] = objective(task, endpoints.tolist(), controls)
                row["objective_difference"] = abs(row["independent_physical_objective"]["total"] - row["objective_adapter"]["total"])
                row["sampled_constraint_diagnostics"] = physical_constraints(task, endpoints.tolist(), controls)
                if label == "common":
                    states = [np.asarray([s["initial"] for s in task["model"]["states"]], dtype=float)]
                    params = source["parameters"]; x = states[0].tolist(); dt = task["episode"]["dt"]
                    inner = task["source"].get("execution_profile", {}).get("substeps_per_source_hold", 100)
                    h = dt / inner
                    for control in controls:
                        for _ in range(inner): x = rk4_step(task["model"]["case_id"], params, x, control, h)
                        states.append(np.asarray(x))
                    fixed = np.asarray(states)
                    row["independent_fixed_rk4"] = {"substeps_per_hold": inner,
                        "hold_endpoint_max_abs_difference": np.max(np.abs(fixed - endpoints), axis=0).tolist(),
                        "physical_objective": independent_cost(task, fixed.tolist(), controls, source),
                        "method": "separately transcribed Python fixed-step classical RK4; numerical diagnostic only"}
            atomic_json(path / "record.json", row)
            replay_rows[label] = {"status": row["status"], "hold_endpoint_max_abs_difference": row.get("hold_endpoint_max_abs_difference"),
                                  "objective_difference": row.get("objective_difference")}
        except Exception as error:
            (path / "exception.txt").write_text(f"{type(error).__name__}: {error}\n")
            atomic_json(path / "record.json", {"status": "failed", "error": str(error), "elapsed_seconds": time.monotonic() - started})
            replay_rows[label] = {"status": "failed", "error": str(error)}
    result["independent_replay"] = replay_rows
    result["sampled_constraint_diagnostics"] = physical_constraints(task, result["physical_states"], controls)
    try:
        render_attempt(task, result, attempt, tag)
    except Exception as error:
        result["render"] = {"status": "failed", "error": str(error)}


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
    fig.suptitle(f"{task['task_id']} observed-state NMPC, {result.get('completed_holds', 0)}/{task['episode']['intervals']} holds")
    trajectory_name = f"{tag}-trajectory.png" if tag else "trajectory.png"
    controls_name = f"{tag}-controls.png" if tag else "controls.png"
    fig.tight_layout(); fig.savefig(attempt / trajectory_name, dpi=150); plt.close(fig)
    if len(controls):
        fig, ax = plt.subplots(figsize=(8, 3)); control_times = (np.arange(len(controls)) + .5) * dt
        for i, field in enumerate(task["model"]["controls"]): ax.step(control_times, controls[:, i], where="mid", label=f"{field['name']} ({field['unit']})")
        ax.set_xlabel(f"Time ({task['episode']['time_unit']})"); ax.set_ylabel("Applied input"); ax.grid(alpha=.25); ax.legend()
        fig.tight_layout(); fig.savefig(attempt / controls_name, dpi=150); plt.close(fig)
    result["render"] = {"status": "complete", "plots": [trajectory_name] + ([controls_name] if len(controls) else [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=["syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01", "all"], default="all")
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "reports/closed-loop-pilot")
    parser.add_argument("--worker", action="store_true"); parser.add_argument("--attempt", type=Path)
    parser.add_argument("--replay-only", type=Path, help="independently replay a saved complete attempt without rerunning its controller")
    args = parser.parse_args()
    if args.worker:
        if args.bridge is None or args.attempt is None: parser.error("worker mode requires --bridge and --attempt")
        return worker(args.task, args.attempt, args.bridge.resolve())
    if args.bridge is None: parser.error("--bridge is required")
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
        result.setdefault("replay_retries", []).append({"tag": tag, "independent_replay": result["independent_replay"], "render": result.get("render")})
        atomic_json(attempt / "attempt.json", result)
        print(json.dumps({"attempt": str(attempt), "replay_retry": tag, "status": result["status"],
                          "independent_replay": result["independent_replay"]}, indent=2))
        return 0
    names = ["syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"] if args.task == "all" else [args.task]
    rows = [run_task(name, args.output_root.resolve(), args.bridge.resolve()) for name in names]
    print(json.dumps({"schema": "csl.closed-loop.coverage/1", "attempts": rows,
        "coverage": [{"task_id": row["task_id"], "status": row["status"], "completed_holds": row["completed_holds"],
                      "actual_observed_state_updates": row["completed_holds"]} for row in rows]}, indent=2))
    return 0 if all(row["status"] == "completed" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

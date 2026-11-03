#!/usr/bin/env python3
"""Capture one Strategy A/B invocation inside a cgroup-v2 systemd scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import signal
import subprocess
import time


def cgroup_v2_path() -> pathlib.Path:
    for line in pathlib.Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            result = pathlib.Path("/sys/fs/cgroup") / path.lstrip("/")
            if result.is_dir():
                return result
    raise RuntimeError("capture must run inside a cgroup-v2 systemd scope")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_timeout(header: dict, strategy: str, repetition: int,
                      position: int, warmup: bool, status: str) -> dict:
    schema = header["schema"]
    unavailable = {"available": False, "reason": "attempt ended before phase completed"}
    return {
        "schema": schema, "event": "trial", "repetition": repetition,
        "warmup": warmup, "order_position": position, "strategy": strategy,
        "strategy_version": "", "strategy_provenance": [],
        "selector_provenance": [], "membership_provenance": [],
        "status": status, "termination": status, "outcome": "unknown",
        "complete_family_verified": False, "assurance": "numerical",
        "family_identity": None, "distinct_witnesses": 0, "witnesses": [],
        "verification_summary": {"residual_count": 0, "maximum_absolute_residual": 0,
                                  "optimality": "unsupported", "completeness": "unsupported"},
        "timings_ns": {key: unavailable for key in (
            "preparation", "workspace_creation", "family_construction",
            "selector_preparation", "selector_workspace_creation", "witness_query",
            "original_verification", "end_to_end_strategy")},
        "error": "supervisor recorded " + status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--scenario", type=pathlib.Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--order-position", type=int, choices=(0, 1), required=True)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--memory-bytes", type=int, default=8 * 1024**3)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    executable = args.executable.resolve(strict=True)
    scenario = args.scenario.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cgroup = cgroup_v2_path()
    memory_limit = int((cgroup / "memory.max").read_text().strip())
    swap_limit = int((cgroup / "memory.swap.max").read_text().strip())
    if memory_limit != args.memory_bytes or swap_limit != 0:
        raise SystemExit(f"unexpected cgroup limits memory={memory_limit}, swap={swap_limit}")

    event_path = output / "events.jsonl"
    stdout_path = output / "stdout.jsonl"
    stderr_path = output / "stderr.log"
    command = [str(executable), "--measure-attempt", args.profile, str(scenario),
               args.strategy, str(args.repetition), str(args.order_position),
               "1" if args.warmup else "0", str(event_path)]
    load_before = os.getloadavg()
    start = time.monotonic_ns()
    process = subprocess.Popen(command, cwd=pathlib.Path.cwd(), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    elapsed = time.monotonic_ns() - start
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    rows = []
    if event_path.exists():
        rows = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line]
    header = next((row for row in rows if row.get("event") == "header"), None)
    if header is None:
        (output / "capture-failure.json").write_text(json.dumps({
            "schema": "csl.mpc01-attempt-capture-failure/1",
            "reason": "attempt produced no event header",
            "command": command,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
            "stdout": stdout,
            "stderr": stderr,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise RuntimeError("attempt produced no event header; raw stdout/stderr retained")
    trials = [row for row in rows if row.get("event") == "trial"]
    memory_events = (cgroup / "memory.events").read_text().splitlines()
    oom_event = any(line.startswith(("oom ", "oom_kill ", "oom_group_kill ")) and
                    int(line.split()[1]) > 0 for line in memory_events)
    status = ("timed_out" if timed_out else "resource_limited" if oom_event else
              "completed" if process.returncode == 0 else "failed")
    if not trials:
        trials = [synthetic_timeout(header, args.strategy, args.repetition,
                                    args.order_position, args.warmup, status)]
    if len(trials) != 1:
        raise RuntimeError(f"expected one trial event, got {len(trials)}")
    trial = trials[0]
    if (trial.get("strategy") != args.strategy or trial.get("repetition") != args.repetition or
            trial.get("order_position") != args.order_position or
            trial.get("warmup") is not args.warmup):
        raise RuntimeError("trial identity differs from the requested attempt")
    # The C++ event file and stdout must be identical for ordinary completed attempts.
    if status == "completed" and event_path.read_bytes() != stdout_path.read_bytes():
        raise RuntimeError("event file and stdout differ")
    if status != "completed" and trial.get("termination") not in (
            "failed", "refused", "unsupported", "incomplete", "timed_out", "resource_limited", "cancelled"):
        trial = synthetic_timeout(header, args.strategy, args.repetition,
                                  args.order_position, args.warmup, status)
    if trial.get("termination") == "unknown":
        trial["termination"] = "failed"
        trial["status"] = "failed"

    receipt = {
        "schema": "csl.mpc01-attempt-resource-receipt/1",
        "attempt_id": output.name,
        "status": status,
        "command": command,
        "timeout_scope": "one strategy attempt and its process tree",
        "elapsed_wall_time_ns": elapsed,
        "requested_limits": {"process_tree_wall_time_seconds": args.timeout_seconds,
                             "process_tree_memory_bytes": memory_limit,
                             "maximum_concurrent_jobs": 1},
        "enforced_limits": {"process_tree_wall_time": True,
                             "process_tree_memory": True,
                             "wall_mechanism": "Python watchdog with process-group SIGTERM/SIGKILL",
                             "memory_mechanism": "systemd user scope on Linux cgroup v2, memory.max",
                             "memory_max_bytes": memory_limit,
                             "memory_swap_max_bytes": swap_limit},
        "observed": {"process_tree_peak_memory_bytes": int((cgroup / "memory.peak").read_text().strip()),
                     "memory_events": memory_events,
                     "memory_current_bytes": int((cgroup / "memory.current").read_text().strip()),
                     "timed_out": timed_out, "exit_code": process.returncode,
                     "trial_status": trial["status"], "trial_termination": trial["termination"]},
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine(), "logical_cpu_count": os.cpu_count(),
                 "load_average_before": load_before, "load_average_after": os.getloadavg()},
        "scenario_sha256": sha256(scenario),
        "trial": trial,
    }
    (output / "resource-profile.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "trial.jsonl").write_text(
        json.dumps(trial, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

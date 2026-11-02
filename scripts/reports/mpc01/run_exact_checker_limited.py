#!/usr/bin/env python3
"""Run the MPC-01 exact candidate checker under its separate comparison budget."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


MEMORY_MAX_BYTES = 8 * 1024**3
CHECKER_TIMEOUT_SECONDS = 5


def cgroup_path() -> Path:
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            return Path("/sys/fs/cgroup") / path.lstrip("/")
    raise RuntimeError("checker worker is not in a cgroup-v2 scope")


def worker(args: argparse.Namespace) -> int:
    root = Path(args.bundle).resolve()
    scope = cgroup_path()
    memory_limit = int((scope / "memory.max").read_text().strip())
    swap_limit = int((scope / "memory.swap.max").read_text().strip())
    if memory_limit != MEMORY_MAX_BYTES or swap_limit != 0:
        raise RuntimeError(f"checker scope limits differ: memory={memory_limit}, swap={swap_limit}")
    checker = Path(args.checker).resolve()
    command = [sys.executable, str(checker), "--attempts", str(root / "native-attempts.jsonl"),
               "--double-integrator", "examples/scenarios/double-integrator-generality.json",
               "--b04-case", "docs/research/evidence/b04-reference-v1/canonical-case.json",
               "--b04-reference", "docs/research/evidence/b04-reference-v1/exact-optimal-reference.json",
               "--output", str(root / "exact-candidate-checks.jsonl")]
    started_ns = time.monotonic_ns()
    status, exit_code = "failed", None
    try:
        process = subprocess.Popen(command, cwd=args.repo, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=CHECKER_TIMEOUT_SECONDS)
            exit_code = process.returncode
            status = "completed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timed_out"
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            exit_code = process.returncode
    except Exception as error:
        stdout, stderr = "", f"{type(error).__name__}: {error}\n"
    elapsed_ns = time.monotonic_ns() - started_ns
    (root / "exact-checker.stdout.log").write_text(stdout, encoding="utf-8")
    (root / "exact-checker.stderr.log").write_text(stderr, encoding="utf-8")
    profile = {
        "schema": "csl.mpc01-exact-checker-resource-profile/1",
        "status": status,
        "command": command,
        "timeout_scope": "exact candidate checker process tree",
        "elapsed_wall_time_ns": elapsed_ns,
        "requested_limits": {"wall_time_seconds": CHECKER_TIMEOUT_SECONDS,
                             "memory_bytes": MEMORY_MAX_BYTES, "memory_swap_bytes": 0,
                             "maximum_concurrent_jobs": 1},
        "enforced_limits": {"process_tree_wall_time": True, "process_tree_memory": True,
                            "wall_mechanism": "Python monotonic watchdog; process-group SIGTERM then SIGKILL",
                            "memory_mechanism": "systemd user scope on Linux cgroup v2",
                            "memory_max_bytes": memory_limit, "memory_swap_max_bytes": swap_limit},
        "observed": {"process_tree_peak_memory_bytes": int((scope / "memory.peak").read_text().strip()),
                     "memory_events": (scope / "memory.events").read_text().splitlines(),
                     "cpu_stat": (scope / "cpu.stat").read_text().splitlines(),
                     "exit_code": exit_code},
        "checker_sha256": hashlib.sha256(checker.read_bytes()).hexdigest(),
    }
    (root / "exact-checker-resource-profile.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "exit_code": exit_code,
                      "elapsed_wall_time_ns": elapsed_ns,
                      "peak_bytes": profile["observed"]["process_tree_peak_memory_bytes"]}, sort_keys=True))
    return 0 if status == "completed" else 1


def run(args: argparse.Namespace) -> int:
    command = ["systemd-run", "--user", "--scope", "--quiet",
               "--property", f"MemoryMax={MEMORY_MAX_BYTES}",
               "--property", "MemorySwapMax=0", "--property", "CPUQuota=100%",
               sys.executable, str(Path(__file__).resolve()), "--worker",
               "--bundle", str(Path(args.bundle).resolve()), "--checker", args.checker,
               "--repo", str(Path(args.repo).resolve())]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        return result.returncode
    root = Path(args.bundle).resolve()
    entries = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (root / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--checker", default="scripts/reports/mpc01/verify_saved_exact_optimality.py")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    return worker(args) if args.worker else run(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run one report capture under the delegated Linux process-tree limits."""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path


WALL_LIMIT_SECONDS = 300
MEMORY_LIMIT_BYTES = 8 * 1024**3


def cgroup_directory() -> Path:
    for line in Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            return Path("/sys/fs/cgroup") / path.lstrip("/")
    raise RuntimeError("process is not running in a cgroup v2 hierarchy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-output", required=True, type=Path)
    parser.add_argument("--capture-dir", required=True, type=Path)
    parser.add_argument("--publish-output", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command after -- is required")

    cgroup = cgroup_directory()
    memory_max = int((cgroup / "memory.max").read_text(encoding="ascii").strip())
    if memory_max != MEMORY_LIMIT_BYTES:
        raise RuntimeError(f"expected {MEMORY_LIMIT_BYTES} byte cgroup cap, got {memory_max}")
    before = time.monotonic_ns()
    load_before = os.getloadavg()
    status = "failed"
    exit_code: int | None = None
    timed_out = False
    stdout = ""
    stderr = ""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=WALL_LIMIT_SECONDS)
        exit_code = process.returncode
        status = "completed" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired:
        timed_out = True
        status = "timed_out"
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        exit_code = process.returncode
    elapsed = time.monotonic_ns() - before
    args.resource_output.parent.mkdir(parents=True, exist_ok=True)
    args.resource_output.with_suffix(".stdout.log").write_text(stdout, encoding="utf-8")
    args.resource_output.with_suffix(".stderr.log").write_text(stderr, encoding="utf-8")
    profile = {
        "schema": "csl.issue824.resource-profile/1",
        "profile": "comparison-program-default-enforced",
        "status": status,
        "command": command,
        "started_monotonic_ns": before,
        "elapsed_wall_time_ns": elapsed,
        "requested_limits": {
            "process_tree_wall_time_seconds": WALL_LIMIT_SECONDS,
            "process_tree_memory_bytes": MEMORY_LIMIT_BYTES,
            "maximum_concurrent_jobs": 1,
        },
        "enforced_limits": {
            "process_tree_wall_time": True,
            "process_tree_memory": True,
            "wall_mechanism": "Python watchdog; SIGTERM then SIGKILL to supervised process group",
            "memory_mechanism": "systemd user scope on Linux cgroup v2, memory.max",
            "memory_cgroup": str(cgroup),
            "memory_max_bytes": memory_max,
            "memory_swap_max_bytes": int((cgroup / "memory.swap.max").read_text(encoding="ascii").strip()),
        },
        "observed": {
            "process_tree_peak_memory_bytes": int((cgroup / "memory.peak").read_text(encoding="ascii").strip()),
            "memory_events": (cgroup / "memory.events").read_text(encoding="ascii").strip().splitlines(),
            "timed_out": timed_out,
            "exit_code": exit_code,
        },
        "measurement_scope": "five order-rotated Release repetitions per method, warmups, five end-to-end solver/check/serialization trials; build excluded",
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "load_average_before": load_before,
            "load_average_after": os.getloadavg(),
        },
    }
    args.resource_output.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8")
    if status == "completed":
        finalizer = Path(__file__).with_name("finalize_limited_report.py")
        finalized = subprocess.run([
            sys.executable, str(finalizer), str(args.capture_dir),
            str(args.resource_output), str(args.publish_output),
        ], check=False)
        if finalized.returncode != 0:
            return finalized.returncode
    print(stdout, end="")
    print(stderr, end="", file=__import__("sys").stderr)
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

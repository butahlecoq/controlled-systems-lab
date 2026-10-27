#!/usr/bin/env python3
"""Run paired Strategy A/B exact-profile measurements with retained process evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
PROFILES = {
    "ts02_constant_integrator": REPORT / "ts02-constant-integrator.json",
    "ts03_singular_integrator": REPORT / "ts03-singular-integrator.json",
}
MEMORY_LIMIT = 8 * 1024**3
CPU_LIMIT = 300
WALL_LIMIT = 300


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def limit_child() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT + 5))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def run_profile(executable: Path, profile: str, raw: Path) -> int:
    scenario = PROFILES[profile]
    paths = {
        "events": raw / f"{profile}.jsonl",
        "stdout": raw / f"{profile}.stdout.bin",
        "stderr": raw / f"{profile}.stderr.bin",
        "process": raw / f"{profile}.process.json",
    }
    for path in paths.values():
        if path.exists():
            raise SystemExit(f"refusing to overwrite retained run file: {path}")
    command = [str(executable), "--measure-profile", profile, str(scenario), str(paths["events"])]
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=WALL_LIMIT, preexec_fn=limit_child, check=False)
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        returncode = 124
    elapsed = time.monotonic() - started
    paths["stdout"].write_bytes(stdout)
    paths["stderr"].write_bytes(stderr)
    process = {
        "command": command,
        "working_directory": str(ROOT),
        "scenario_sha256": digest(scenario.read_bytes()),
        "executable_sha256": digest(executable.read_bytes()),
        "exit_code": returncode,
        "timed_out": timed_out,
        "elapsed_wall_seconds": elapsed,
        "resource_limits": {
            "cpu_seconds_hard": CPU_LIMIT + 5,
            "cpu_seconds_soft": CPU_LIMIT,
            "address_space_bytes": MEMORY_LIMIT,
            "wall_timeout_seconds": WALL_LIMIT,
            "scope": "whole per-profile process: one warmup pair plus five measured pairs",
        },
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
    }
    paths["process"].write_text(json.dumps(process, indent=2, sort_keys=True) + "\n")
    print(f"{profile}: exit={returncode}, timeout={timed_out}, wall={elapsed:.6f}s")
    return returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=REPORT / "raw")
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    if not executable.is_file():
        raise SystemExit("executable must be a regular file")
    args.raw.mkdir(parents=True, exist_ok=True)
    failures = 0
    for profile in PROFILES:
        failures += int(run_profile(executable, profile, args.raw) != 0)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

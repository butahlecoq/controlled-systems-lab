#!/usr/bin/env python3
"""Capture paired runs for the registered T-S01/T-S02/T-S03 profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXP02 = ROOT / "reports/algorithm-results/exp02-paired-profiles-20261027-r1"
PROFILES = {
    "ts01_exact_integrator": ROOT / "examples/scenarios/two-stage-integrator.json",
    "ts02_constant_integrator": EXP02 / "ts02-constant-integrator.json",
    "ts03_singular_integrator": EXP02 / "ts03-singular-integrator.json",
}
PAIR_COUNTS = {"ts01_exact_integrator": 7, "ts02_constant_integrator": 5,
               "ts03_singular_integrator": 5}
MEMORY_LIMIT = 8 * 1024**3
CPU_LIMIT = 300
WALL_LIMIT = 300


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def limit_child() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT + 5))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def command_for(executable: Path, profile: str, scenario: Path, events: Path) -> list[str]:
    if profile == "ts01_exact_integrator":
        return [str(executable), "--measure", str(scenario), str(events)]
    return [str(executable), "--measure-profile", profile, str(scenario), str(events)]


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
    command = command_for(executable, profile, scenario, paths["events"])
    try:
        load_before = os.getloadavg()
    except OSError:
        load_before = None
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=WALL_LIMIT,
                                   preexec_fn=limit_child, check=False)
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        returncode = 124
    elapsed = time.monotonic() - started
    paths["stdout"].write_bytes(stdout)
    paths["stderr"].write_bytes(stderr)
    try:
        load_after = os.getloadavg()
    except OSError:
        load_after = None
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        source_commit = None
    process = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "profile": profile,
        "measured_pairs": PAIR_COUNTS[profile],
        "command": command,
        "working_directory": str(ROOT),
        "scenario_sha256": digest(scenario.read_bytes()),
        "executable_sha256": digest(executable.read_bytes()),
        "exit_code": returncode,
        "timed_out": timed_out,
        "elapsed_wall_seconds": elapsed,
        "resource_limits": {
            "cpu_seconds_soft": CPU_LIMIT,
            "cpu_seconds_hard": CPU_LIMIT + 5,
            "address_space_bytes": MEMORY_LIMIT,
            "wall_timeout_seconds": WALL_LIMIT,
            "scope": "whole profile process, including one warmup and all measured pairs",
        },
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "load_average_before": load_before,
            "load_average_after": load_after,
        },
    }
    paths["process"].write_text(json.dumps(process, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(f"{profile}: exit={returncode}, timeout={timed_out}, wall={elapsed:.6f}s")
    return returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
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

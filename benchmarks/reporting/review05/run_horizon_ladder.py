#!/usr/bin/env python3
"""Capture bounded paired runs for REVIEW-05 HORIZON-01."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path


STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
SCENARIOS = {2: "horizon01-t02.json", 4: "horizon01-t04.json", 8: "horizon01-t08.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def limit_process() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    address_space = 8 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))


def physical_memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def environment(binary: Path, source_dir: Path, repo_dir: Path) -> dict[str, object]:
    try:
        load = os.getloadavg()
    except (AttributeError, OSError):
        load = None
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_dir, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout
    source_files = ("CMakeLists.txt", "horizon_ladder.cpp", "run_horizon_ladder.py",
                    "check_horizon_ladder.py", "summarize_horizon_ladder.py")
    return {
        "source_revision": revision,
        "source_worktree_dirty": bool(status),
        "measurement_source_sha256": {name: sha256(source_dir / name) for name in source_files},
        "host": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "physical_memory_bytes": physical_memory_bytes(),
        "load_average_at_start": list(load) if load else None,
        "python": platform.python_version(),
        "binary_sha256": sha256(binary),
        "requested_threads_per_strategy": 1,
        "requested_driver_workers": 1,
        "observed_driver_workers": 1,
        "limits": {
            "cpu_seconds": 300,
            "address_space_bytes": 8 * 1024**3,
            "mechanism": "POSIX RLIMIT_CPU and RLIMIT_AS on each strategy process",
            "process_timeout_seconds": 300,
            "scope": "single strategy process",
            "enforced": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--scenarios", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    driver = args.driver.resolve(strict=True)
    scenario_dir = args.scenarios.resolve(strict=True)
    source_dir = Path(__file__).resolve().parent
    repo_dir = scenario_dir.parents[3]
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must not exist or must be empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir()
    (output / "inputs").mkdir()

    scenario_paths = {horizon: scenario_dir / name for horizon, name in SCENARIOS.items()}
    for path in scenario_paths.values():
        if not path.is_file():
            parser.error(f"missing pinned scenario: {path}")
        shutil.copyfile(path, output / "inputs" / path.name)
    manifest = {
        "schema": "csl.review05.horizon-manifest/1",
        "track": "new-comparison",
        "fixture": "HORIZON-01-scalar-integrator",
        "scenario_sha256": {str(t): sha256(p) for t, p in scenario_paths.items()},
        "environment": environment(driver, source_dir, repo_dir),
        "schedule": {
            "warmup_pairs_per_horizon": 1,
            "measured_pairs_per_horizon": 6,
            "alternation": "AB,BA,AB,BA,AB,BA per horizon",
            "horizon_order": "rotates by repetition index across 2,4,8",
            "timed_region": "C++ steady_clock around SynthesisWorkspace::run only",
            "process_startup_and_setup": "excluded from strategy_run_ns; process_wall_ns retained separately",
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    attempts_path = output / "attempts.jsonl"
    attempt_number = 0
    with attempts_path.open("x", encoding="utf-8") as records:
        for repetition in range(7):  # zero is the excluded warmup pair
            warmup = repetition == 0
            rotation = repetition % len(SCENARIOS)
            horizons = list(SCENARIOS)
            horizons = horizons[rotation:] + horizons[:rotation]
            for horizon in horizons:
                if warmup:
                    first_index = horizon % 2
                else:
                    first_index = (repetition + horizon // 2) % 2
                ordered_strategies = (STRATEGIES[first_index], STRATEGIES[1 - first_index])
                for order_position, strategy in enumerate(ordered_strategies):
                    attempt_number += 1
                    attempt_id = f"t{horizon:02d}-r{repetition:02d}-p{order_position}-{attempt_number:03d}"
                    command = [str(driver), str(scenario_paths[horizon]), strategy]
                    started = time.monotonic_ns()
                    try:
                        process = subprocess.run(
                            command,
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=300,
                            preexec_fn=limit_process,
                        )
                        process_wall_ns = time.monotonic_ns() - started
                        stdout = process.stdout
                        stderr = process.stderr
                        return_code = process.returncode
                        process_status = "completed" if return_code == 0 else "failed"
                    except subprocess.TimeoutExpired as timeout:
                        process_wall_ns = time.monotonic_ns() - started
                        stdout = timeout.stdout or b""
                        stderr = timeout.stderr or b""
                        return_code = None
                        process_status = "timed_out"
                    except Exception as error:  # retain launcher failures as attempts
                        process_wall_ns = time.monotonic_ns() - started
                        stdout = b""
                        stderr = str(error).encode("utf-8", errors="replace")
                        return_code = None
                        process_status = "failed_to_launch"

                    raw_base = output / "raw" / attempt_id
                    stdout_path = raw_base.with_suffix(".stdout")
                    stderr_path = raw_base.with_suffix(".stderr")
                    stdout_path.write_bytes(stdout)
                    stderr_path.write_bytes(stderr)
                    parsed = None
                    parse_error = None
                    if process_status == "completed":
                        try:
                            parsed = json.loads(stdout.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as error:
                            process_status = "invalid_output"
                            parse_error = str(error)

                    row = {
                        "attempt_id": attempt_id,
                        "horizon": horizon,
                        "repetition": repetition,
                        "warmup": warmup,
                        "order_position": order_position,
                        "strategy": strategy,
                        "process_status": process_status,
                        "return_code": return_code,
                        "process_wall_ns": process_wall_ns,
                        "scenario_sha256": manifest["scenario_sha256"][str(horizon)],
                        "command": command,
                        "stdout_path": str(stdout_path.relative_to(output)),
                        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                        "stderr_path": str(stderr_path.relative_to(output)),
                        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                        "parse_error": parse_error,
                        "result": parsed,
                    }
                    records.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                    records.flush()
                    os.fsync(records.fileno())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

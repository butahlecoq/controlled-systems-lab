#!/usr/bin/env python3
"""Capture repeated, isolated gprof samples for one pinned horizon fixture."""

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

from check_horizon_ladder import check_attempt

STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
SUPPORTED_HORIZONS = {2, 4, 8}
PINNED_SCENARIOS = {
    2: ("horizon01-t02.json", "056032df5c8a30e376e00c5a0743606211486a0e268b209919ba771bc2efeb76"),
    4: ("horizon01-t04.json", "ba86e625b4a6daae09d3db8400551e23277400b20fdd78893c9fc9b9c98b2dd3"),
    8: ("horizon01-t08.json", "af2b5471d85111d2225b5abf579c3b367bce18765763b567be0bc598290c73d4"),
}
CPU_LIMIT = 300
MEMORY_LIMIT = 8 * 1024**3
WALL_LIMIT = 300


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT + 5))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--process-groups", type=int, default=5)
    parser.add_argument("--repeats-per-process", type=int, default=50)
    args = parser.parse_args()
    if args.process_groups < 1 or args.repeats_per_process < 20:
        parser.error("use at least one process group and 20 repetitions per process")
    if args.repeats_per_process > 1000:
        parser.error("repetitions per process may not exceed 1000")

    driver = args.driver.resolve(strict=True)
    scenario = args.scenario.resolve(strict=True)
    scenario_data = json.loads(scenario.read_text(encoding="utf-8"))
    horizon = scenario_data.get("horizon")
    if horizon not in SUPPORTED_HORIZONS:
        parser.error(f"scenario horizon must be one of {sorted(SUPPORTED_HORIZONS)}")
    expected_name, expected_hash = PINNED_SCENARIOS[horizon]
    if scenario.name != expected_name or sha256(scenario) != expected_hash:
        parser.error(f"scenario does not match the pinned T={horizon} fixture")
    repository = scenario.parents[4]
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must not exist or must be empty")
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    profiles = output / "gmon"
    raw.mkdir()
    profiles.mkdir()
    input_copy = output / scenario.name
    input_copy.write_bytes(scenario.read_bytes())
    scenario_hash = sha256(input_copy)
    source_files = ("CMakeLists.txt", "horizon_ladder.cpp", "capture_source_profile.py",
                    "verify_source_profile.py", "check_horizon_ladder.py")
    source_root = Path(__file__).resolve().parent
    source_status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repository, text=True)

    attempts: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []
    processes: list[dict[str, object]] = []
    started_all = time.monotonic()
    for group in range(args.process_groups):
        order = STRATEGIES if group % 2 == 0 else tuple(reversed(STRATEGIES))
        for position, strategy in enumerate(order):
            process_id = f"g{group:02d}-p{position}-{strategy.rsplit('.', 1)[-1]}"
            stdout_path = raw / f"{process_id}.stdout"
            stderr_path = raw / f"{process_id}.stderr"
            prefix = profiles / process_id
            environment = os.environ.copy()
            environment["GMON_OUT_PREFIX"] = str(prefix)
            command = [str(driver), str(input_copy), strategy, str(args.repeats_per_process)]
            started = time.monotonic_ns()
            try:
                child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         cwd=repository, env=environment, preexec_fn=limits)
                try:
                    stdout, stderr = child.communicate(timeout=WALL_LIMIT)
                    process_status = "completed" if child.returncode == 0 else "failed"
                    return_code = child.returncode
                except subprocess.TimeoutExpired:
                    child.kill()
                    stdout, stderr = child.communicate()
                    process_status, return_code = "timed_out", child.returncode
            except OSError as error:
                stdout, stderr, child = b"", str(error).encode(), None
                process_status, return_code = "failed_to_launch", None
            elapsed_ns = time.monotonic_ns() - started
            stdout_path.write_bytes(stdout)
            stderr_path.write_bytes(stderr)
            pid = child.pid if child is not None else None
            profile_path = Path(f"{prefix}.{pid}") if pid is not None else None
            profile_exists = bool(profile_path and profile_path.is_file())
            output_lines = stdout.decode("utf-8", errors="replace").splitlines()
            results: list[dict[str, object] | None] = []
            parse_errors: list[str | None] = []
            for line in output_lines:
                try:
                    results.append(json.loads(line))
                    parse_errors.append(None)
                except json.JSONDecodeError as error:
                    results.append(None)
                    parse_errors.append(str(error))
            if len(results) != args.repeats_per_process:
                process_status = "wrong_output_count"
            processes.append({
                "process_id": process_id, "group": group, "order_position": position,
                "strategy": strategy, "command": command, "pid": pid,
                "process_status": process_status, "return_code": return_code,
                "elapsed_wall_ns": elapsed_ns, "expected_results": args.repeats_per_process,
                "observed_results": len(results),
                "stdout_path": str(stdout_path.relative_to(output)),
                "stdout_sha256": sha256(stdout_path),
                "stderr_path": str(stderr_path.relative_to(output)),
                "stderr_sha256": sha256(stderr_path),
                "gmon_path": str(profile_path.relative_to(output)) if profile_exists else None,
                "gmon_sha256": sha256(profile_path) if profile_exists else None,
            })
            for repetition in range(args.repeats_per_process):
                result = results[repetition] if repetition < len(results) else None
                attempt_id = f"{process_id}-r{repetition:03d}"
                attempt = {
                    "schema": "csl.review05.source-profile-attempt/1",
                    "attempt_id": attempt_id, "process_id": process_id,
                    "output_line": repetition,
                    "horizon": horizon, "repetition": repetition, "strategy": strategy,
                    "process_status": "completed" if result is not None and process_status == "completed" else process_status,
                    "scenario_sha256": scenario_hash,
                }
                if result is None or process_status != "completed":
                    detail = (f"process status: {process_status}" if process_status != "completed" else
                              f"missing or invalid JSON result: {parse_errors[repetition] if repetition < len(parse_errors) else 'no output line'}")
                    status, reasons = "unavailable", [detail]
                else:
                    status, reasons = check_attempt(
                        {"process_status": "completed", "result": result,
                         "horizon": horizon, "strategy": strategy}, scenario_hash)
                if not profile_exists:
                    reasons.append("gprof output file missing")
                    if status == "verified":
                        status = "unavailable"
                attempts.append(attempt)
                checks.append({"attempt_id": attempt_id, "process_id": process_id,
                               "strategy": strategy, "status": status, "reasons": reasons,
                               "profile_present": profile_exists})
            print(f"group {group + 1}/{args.process_groups}, {strategy}: {process_status}, "
                  f"{len(results)}/{args.repeats_per_process} outputs, profile={profile_exists}", flush=True)

    for name, rows in (("attempts.jsonl", attempts), ("checks.jsonl", checks),
                       ("processes.jsonl", processes)):
        with (output / name).open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        load_average = list(os.getloadavg())
    except OSError:
        load_average = None
    manifest = {
        "schema": "csl.review05.source-profile-manifest/1",
        "claim": "source-attribution diagnostic only; gprof-instrumented execution times are not performance measurements",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
        "source_worktree_dirty": bool(source_status),
        "measurement_source_sha256": {name: sha256(source_root / name) for name in source_files},
        "driver_sha256": sha256(driver), "scenario_sha256": scenario_hash,
        "scenario": str(scenario), "scenario_file": input_copy.name, "horizon": horizon,
        "process_groups": args.process_groups,
        "repetitions_per_strategy": args.process_groups * args.repeats_per_process,
        "repetitions_per_process": args.repeats_per_process,
        "schedule": "process order alternates by group; fresh workspace per strategy run",
        "total_elapsed_wall_seconds": time.monotonic() - started_all,
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "logical_cpus": os.cpu_count(), "load_average_after": load_average},
        "resource_limits_per_process": {"cpu_seconds_soft": CPU_LIMIT,
                                         "cpu_seconds_hard": CPU_LIMIT + 5,
                                         "address_space_bytes": MEMORY_LIMIT,
                                         "wall_timeout_seconds": WALL_LIMIT,
                                         "mechanism": "POSIX RLIMIT_CPU, RLIMIT_AS, subprocess timeout"},
        "instrumentation": {"profiler": "GNU gprof", "environment": "GMON_OUT_PREFIX",
                            "release_flags": "-O3 -DNDEBUG -g",
                            "profile_driver_compile_flag": "-pg",
                            "link_flags": "-pg"},
        "attempts": len(attempts), "processes": len(processes),
        "verified_attempts": sum(check["status"] == "verified" for check in checks),
        "profile_files": sum(process["gmon_path"] is not None for process in processes),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    print(json.dumps({"attempts": len(attempts), "processes": len(processes),
                      "checks": counts, "profile_files": manifest["profile_files"],
                      "manifest": str(output / "manifest.json")}, indent=2))
    return 0 if counts == {"verified": len(attempts)} else 1


if __name__ == "__main__":
    raise SystemExit(main())

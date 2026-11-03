#!/usr/bin/env python3
"""Run alternating Strategy A/B trials, each in its own enforced resource scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys


STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
MEMORY_BYTES = 8 * 1024**3
TIMEOUT_SECONDS = 300


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def cache_value(cache: dict[str, str], name: str) -> str:
    return cache.get(name, "unknown")


def source_tree_sha256(root: pathlib.Path, revision: str) -> str:
    archive = subprocess.run(["git", "archive", "--format=tar", revision], cwd=root,
                             check=True, capture_output=True).stdout
    return sha256(archive)


def cmake_compiler_metadata(build_dir: pathlib.Path) -> dict[str, str]:
    candidates = sorted(build_dir.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(candidates) != 1:
        raise RuntimeError(f"expected one CMake compiler metadata file, found {len(candidates)}")
    values: dict[str, str] = {}
    for line in candidates[0].read_text().splitlines():
        for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION", "CMAKE_CXX_COMPILER"):
            prefix = f'set({key} "'
            if line.startswith(prefix) and line.endswith('")'):
                values[key] = line[len(prefix):-2]
    if not all(values.get(key) for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION")):
        raise RuntimeError(f"incomplete compiler metadata in {candidates[0]}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--build-dir", type=pathlib.Path, required=True)
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--scenario", type=pathlib.Path, required=True)
    parser.add_argument("--profile", choices=("ts01_exact_integrator", "ts02_constant_integrator"), required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--binary-source-commit", help="commit used to build the executable; defaults to HEAD")
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    build_dir = args.build_dir.resolve(strict=True)
    binary = args.binary.resolve(strict=True)
    scenario_input = args.scenario
    scenario = (root / scenario_input).resolve(strict=True) if not scenario_input.is_absolute() else scenario_input.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if git(root, "status", "--porcelain"):
        raise SystemExit("source worktree must be clean at capture start")
    if not scenario.is_relative_to(root):
        raise SystemExit("scenario must be inside the source checkout")
    affinity = sorted(os.sched_getaffinity(0))
    if not affinity:
        raise SystemExit("no available logical CPU for serialized capture")
    cpu = affinity[0]
    helper = root / "scripts/reports/mpc01/capture_strategy_ab_attempt.py"
    attempts_dir = output / "attempts"
    attempts_dir.mkdir()
    headers: list[dict] = []
    trials: list[dict] = []
    receipts: list[dict] = []
    process_receipts = []
    process_log = output / "systemd-scope-processes.jsonl"

    for repetition in range(6):
        warmup = repetition == 0
        position = 0 if warmup else (repetition - 1) % 2
        order = STRATEGIES if position == 0 else tuple(reversed(STRATEGIES))
        for order_position, strategy in enumerate(order):
            key = f"r{repetition:02d}-p{order_position}-{strategy.rsplit('.', 1)[-1]}"
            attempt_dir = attempts_dir / key
            command = [
                "systemd-run", "--user", "--scope", "--quiet",
                "-p", f"MemoryMax={MEMORY_BYTES}", "-p", "MemorySwapMax=0",
                "-p", "CPUQuota=100%", "-p", f"AllowedCPUs={cpu}",
                sys.executable, str(helper), "--executable", str(binary),
                "--scenario", str(scenario), "--profile", args.profile,
                "--strategy", strategy, "--repetition", str(repetition),
                "--order-position", str(order_position), "--output-dir", str(attempt_dir),
                "--memory-bytes", str(MEMORY_BYTES), "--timeout-seconds", str(TIMEOUT_SECONDS),
            ]
            if warmup:
                command.append("--warmup")
            started = subprocess.run(command, cwd=root, capture_output=True, text=True)
            process_receipts.append({"attempt": key, "command": command,
                                     "exit_code": started.returncode,
                                     "stdout": started.stdout, "stderr": started.stderr})
            with process_log.open("a", encoding="utf-8") as log:
                log.write(json.dumps(process_receipts[-1], sort_keys=True) + "\n")
            if started.returncode:
                raise RuntimeError(f"scope capture failed for {key}: {started.stderr}")
            attempt_receipt = json.loads((attempt_dir / "resource-profile.json").read_text())
            event_rows = [json.loads(line) for line in (attempt_dir / "events.jsonl").read_text().splitlines() if line]
            header = next(row for row in event_rows if row.get("event") == "header")
            trial = json.loads((attempt_dir / "trial.jsonl").read_text())
            if header.get("profile") != args.profile or header.get("scenario_sha256") != sha256(scenario.read_bytes()):
                raise RuntimeError(f"input binding failed for {key}")
            headers.append(header)
            trials.append(trial)
            receipts.append(attempt_receipt)

    limiter_dir = output / "limiter-profile"
    limiter_dir.mkdir()
    limiter_receipts = []
    for order_position, strategy in enumerate(STRATEGIES):
        key = f"separate-warmup-{strategy.rsplit('.', 1)[-1]}"
        attempt_dir = limiter_dir / key
        command = [
            "systemd-run", "--user", "--scope", "--quiet",
            "-p", f"MemoryMax={MEMORY_BYTES}", "-p", "MemorySwapMax=0",
            "-p", "CPUQuota=100%", "-p", f"AllowedCPUs={cpu}",
            sys.executable, str(helper), "--executable", str(binary),
            "--scenario", str(scenario), "--profile", args.profile,
            "--strategy", strategy, "--repetition", "0",
            "--order-position", str(order_position), "--warmup",
            "--output-dir", str(attempt_dir),
            "--memory-bytes", str(MEMORY_BYTES), "--timeout-seconds", str(TIMEOUT_SECONDS),
        ]
        started = subprocess.run(command, cwd=root, capture_output=True, text=True)
        receipt_path = attempt_dir / "resource-profile.json"
        if started.returncode or not receipt_path.is_file():
            (limiter_dir / f"{key}-supervisor-failure.json").write_text(
                json.dumps({"command": command, "exit_code": started.returncode,
                            "stdout": started.stdout, "stderr": started.stderr},
                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise RuntimeError(f"separate limiter profile failed for {key}: {started.stderr}")
        limiter_receipts.append(json.loads(receipt_path.read_text()))

    if len(set(json.dumps(header, sort_keys=True) for header in headers)) != 1:
        # Shared setup durations legitimately differ between restarted attempts.
        comparable = [{key: value for key, value in header.items() if key != "shared_setup_ns"}
                      for header in headers]
        if len(set(json.dumps(header, sort_keys=True) for header in comparable)) != 1:
            raise RuntimeError("attempt headers disagree on the resolved comparison contract")
    event_bytes = (json.dumps(headers[0], sort_keys=True, separators=(",", ":")) + "\n" +
                   "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in trials)).encode()
    (output / "events.jsonl").write_bytes(event_bytes)
    (output / "stdout.jsonl").write_bytes(event_bytes)

    peaks = [receipt["observed"]["process_tree_peak_memory_bytes"] for receipt in receipts]
    aggregate = {
        "schema": "csl.mpc01-resource-profile/1",
        "profile": "linux-cgroup-v2-per-attempt",
        "status": "completed" if all(r["status"] == "completed" for r in receipts) else "attempts_retained",
        "timeout_scope": "each individual Strategy A or Strategy B attempt is restarted and supervised in its own process tree",
        "requested_limits": {"process_tree_wall_time_seconds": TIMEOUT_SECONDS,
                             "process_tree_memory_bytes": MEMORY_BYTES,
                             "maximum_concurrent_jobs": 1},
        "enforced_limits": {"process_tree_wall_time": True, "process_tree_memory": True,
                             "wall_mechanism": "Python watchdog with process-group SIGTERM/SIGKILL",
                             "memory_mechanism": "systemd user scope on Linux cgroup v2, memory.max",
                             "memory_max_bytes": MEMORY_BYTES, "memory_swap_max_bytes": 0,
                             "cpu_quota": "100%", "allowed_cpus": [cpu]},
        "attempt_count": len(receipts), "attempts": receipts,
        "separate_limiter_profiles": limiter_receipts,
        "elapsed_wall_time_ns": sum(r["elapsed_wall_time_ns"] for r in receipts),
        "observed": {"process_tree_peak_memory_bytes": max(peaks),
                     "memory_events": [f"{receipt['attempt_id']}: {line}"
                                       for receipt in receipts
                                       for line in receipt["observed"]["memory_events"]],
                     "exit_code": 0 if all(r["status"] == "completed" for r in receipts) else 1,
                     "timed_out": any(r["observed"]["timed_out"] for r in receipts),
                     "all_attempts_completed": all(r["status"] == "completed" for r in receipts)},
        "supervisor_processes": process_receipts,
    }
    profile_bytes = (json.dumps(aggregate, indent=2, sort_keys=True) + "\n").encode()
    (output / "resource-profile.json").write_bytes(profile_bytes)

    cache_path = build_dir / "CMakeCache.txt"
    cache = {}
    for line in cache_path.read_text().splitlines():
        if line and not line.startswith("#") and ":" in line and "=" in line:
            key, rest = line.split(":", 1)
            cache[key] = rest.split("=", 1)[1]
    execution_commit = git(root, "rev-parse", "HEAD")
    source_commit = args.binary_source_commit or execution_commit
    git(root, "cat-file", "-e", f"{source_commit}^{{commit}}")
    compiler = cmake_compiler_metadata(build_dir)
    compiler_path = compiler.get("CMAKE_CXX_COMPILER", cache_value(cache, "CMAKE_CXX_COMPILER"))
    compiler_version_result = subprocess.run([compiler_path, "--version"], check=True,
                                             capture_output=True, text=True)
    compiler_banner = compiler_version_result.stdout.splitlines()[0]
    source_file_bytes = subprocess.run(["git", "show", f"{source_commit}:examples/registered_synthesis_comparison.cpp"],
                                       cwd=root, check=True, capture_output=True).stdout
    binary_hash = sha256(binary.read_bytes())
    scenario_relative = scenario.relative_to(root).as_posix()
    cpu_model = "unknown"
    for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines():
        if line.lower().startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    environment = {
        "build": {"type": cache_value(cache, "CMAKE_BUILD_TYPE"),
                  "compiler": compiler["CMAKE_CXX_COMPILER_ID"] + " " + compiler["CMAKE_CXX_COMPILER_VERSION"],
                  "compiler_id": compiler["CMAKE_CXX_COMPILER_ID"],
                  "compiler_version": compiler["CMAKE_CXX_COMPILER_VERSION"],
                  "compiler_path": compiler_path, "compiler_banner": compiler_banner,
                  "compiler_metadata_file": str((build_dir / sorted(build_dir.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))[0].relative_to(build_dir))),
                  "generator": cache_value(cache, "CMAKE_GENERATOR"),
                  "flags": cache_value(cache, "CMAKE_CXX_FLAGS_RELEASE")},
        "executable": str(binary), "executable_sha256": binary_hash,
        "execution_worktree_clean_before_run": True,
        "execution_worktree_commit": execution_commit,
        "host": {"cpu": cpu_model, "kernel": platform.release(),
                 "logical_cpus": os.cpu_count(), "os": platform.platform(),
                 "load_average_before_capture": receipts[0]["host"]["load_average_before"],
                 "load_average_after_capture": receipts[-1]["host"]["load_average_after"]},
        "measurement": {"command": "registered_synthesis_comparison --measure-attempt, repeated as individual systemd scopes",
                        "event_count_including_header": len(trials) + 1,
                        "measured_alternating_pairs": 5, "warmup_pairs_excluded": 1,
                        "resource_profile": "resource-profile.json",
                        "resource_profile_sha256": sha256(profile_bytes),
                        "capture_supervisor": helper.relative_to(root).as_posix(),
                        "capture_supervisor_sha256": sha256(helper.read_bytes()),
                        "separate_limiter_profile": "separate-limiter-profiles in resource-profile.json",
                        "per_attempt_wall_time_cap": TIMEOUT_SECONDS,
                        "process_tree_wall_time_cap_seconds": TIMEOUT_SECONDS,
                        "process_tree_memory_cap_bytes": MEMORY_BYTES,
                        "process_tree_memory_swap_max_bytes": 0,
                        "timeout_scope": "one strategy attempt per scope",
                        "cpu_time_or_peak_memory_profiled": True},
        "scenario": scenario_relative, "scenario_sha256": sha256(scenario.read_bytes()),
        "source_commit": source_commit, "source_dirty_before_run": False,
        "source_file": "examples/registered_synthesis_comparison.cpp",
        "source_file_sha256": sha256(source_file_bytes),
        "source_tree_sha256": source_tree_sha256(root, source_commit),
        "execution_worktree_role": "The executable was built from source_commit; compiler identity comes from the configured CMake compiler metadata and banner.",
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n")
    codec_environment = {
        "schema": "csl.obs04-environment/1",
        "build": {"schema": "csl.obs04-build/1", "source_revision": source_commit,
                  "source_dirty": False, "build_type": environment["build"]["type"],
                  "compiler_id": compiler["CMAKE_CXX_COMPILER_ID"],
                  "compiler_version": compiler["CMAKE_CXX_COMPILER_VERSION"],
                  "cxx_standard": "20", "source_tree_sha256": source_tree_sha256(root, source_commit),
                  "backends": {}},
        "execution": {"warmup_repetitions": 1,
                      "observed_driver_workers": 1, "requested_workers": 1,
                      "requested_backend_threads": 1,
                      "cache_policy": "One excluded warmup pair; five measured pairs alternate A/B then B/A; each strategy attempt uses a fresh process scope.",
                      "workspace_policy": "fresh-workspace-per-attempt",
                      "tolerances": {"absolute": float(headers[0]["absolute_tolerance"]),
                                     "relative": float(headers[0]["relative_tolerance"])}},
        "runtime": {"schema": "csl.obs04-runtime/1", "os_family": platform.system(),
                    "os_version": platform.platform(), "architecture": platform.machine(),
                    "logical_cpus": os.cpu_count(),
                    "cpu_model": {"status": "available", "value": cpu_model},
                    "kernel": {"status": "available", "value": platform.release()},
                    "binary_sha256": {"status": "available", "value": binary_hash}},
    }
    (output / "codec-environment.json").write_text(json.dumps(codec_environment, indent=2, sort_keys=True) + "\n")
    subprocess.run([sys.executable, str(root / "scripts/reports/mpc01/write_strategy_ab_build_note.py"),
                    "--root", str(root), "--build-dir", str(build_dir), "--binary", str(binary),
                    "--source-commit", source_commit, "--output-dir", str(output)],
                   cwd=root, check=True)
    print(json.dumps({"output_dir": str(output), "attempts": len(trials),
                      "passed": sum(row.get("status") == "passed" for row in trials),
                      "retained_nonpass": sum(row.get("status") != "passed" for row in trials),
                      "maximum_peak_bytes": max(peaks)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

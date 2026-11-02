#!/usr/bin/env python3
"""Run each MPC-01 solver/start-mode attempt in its own bounded systemd scope."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


FIXTURES = (
    "ts01", "ts02", "ts03-singular", "infeasible", "unbounded",
    "double-integrator-421", "b04-reference-v1",
)
METHODS = ("osqp-sparse-qp", "hpipm-structured-ocp-qp")
START_MODES = ("cold", "warm_if_available")
ATTEMPT_TIMEOUT_SECONDS = 300
MEMORY_MAX_BYTES = 8 * 1024**3


def cgroup_path() -> Path:
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            return Path("/sys/fs/cgroup") / path.lstrip("/")
    raise RuntimeError("worker is not in a cgroup-v2 scope")


def worker(args: argparse.Namespace) -> int:
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"attempt-{args.index:03d}"
    stdout_path = output.with_suffix(".stdout")
    stderr_path = output.with_suffix(".stderr")
    command = [args.binary, "--single-attempt", args.fixture, args.method,
               args.start_mode, str(args.repetition)]
    scope = cgroup_path()
    memory_limit = int((scope / "memory.max").read_text().strip())
    swap_limit = int((scope / "memory.swap.max").read_text().strip())
    if memory_limit != MEMORY_MAX_BYTES or swap_limit != 0:
        raise RuntimeError(f"scope limits differ: memory={memory_limit}, swap={swap_limit}")
    allowed_cpus = sorted(os.sched_getaffinity(0))
    if not allowed_cpus:
        raise RuntimeError("no CPU is available to the attempt")
    command = ["/usr/bin/taskset", "-c", str(allowed_cpus[0]), *command]

    started_ns = time.monotonic_ns()
    status = "failed"
    exit_code = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=ATTEMPT_TIMEOUT_SECONDS)
            exit_code = process.returncode
            status = "completed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timed_out"
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            exit_code = process.returncode
    except Exception as error:
        stdout, stderr = "", f"{type(error).__name__}: {error}\n"
    elapsed_ns = time.monotonic_ns() - started_ns
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    memory_events = (scope / "memory.events").read_text().splitlines()
    event_counts = {key: int(value) for key, value in
                    (line.split() for line in memory_events)}
    if event_counts.get("oom_kill", 0) or event_counts.get("oom", 0):
        status = "resource_limited"
    lines = [line for line in stdout.splitlines() if line.strip()]
    event = json.loads(lines[-1]) if status == "completed" and len(lines) == 1 else None
    row = {
        "schema": "csl.mpc01-resource-attempt/1",
        "index": args.index,
        "fixture": args.fixture,
        "method": args.method,
        "start_mode": args.start_mode,
        "repetition": args.repetition,
        "status": status,
        "termination": "completed" if status == "completed" else status,
        "exit_code": exit_code,
        "attempt_wall_time_ns": elapsed_ns,
        "attempt_limit_seconds": ATTEMPT_TIMEOUT_SECONDS,
        "resource_scope": "one solver/start-mode/repetition process tree",
        "enforced": {
            "memory_max_bytes": memory_limit,
            "memory_swap_max_bytes": swap_limit,
            "cpu_quota": "100%",
            "cpu_affinity": allowed_cpus[0],
            "wall_watchdog_seconds": ATTEMPT_TIMEOUT_SECONDS,
            "wall_mechanism": "Python monotonic watchdog; process-group SIGTERM then SIGKILL",
            "memory_mechanism": "systemd user scope on Linux cgroup v2",
        },
        "observed": {
            "process_tree_peak_memory_bytes": int((scope / "memory.peak").read_text().strip()),
            "memory_events": memory_events,
            "cpu_stat": (scope / "cpu.stat").read_text().splitlines(),
        },
        "stdout_file": stdout_path.name,
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_file": stderr_path.name,
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "attempt": event,
    }
    print(json.dumps(row, sort_keys=True))
    return 0 if status == "completed" and event is not None else 1


def build_identity(root: Path, binary: Path) -> dict:
    repo = Path(__file__).resolve().parents[3]
    revision = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    cache = binary.resolve().parent / "CMakeCache.txt"
    compiler_config = cache.parent / "CMakeFiles" / "3.31.6" / "CMakeCXXCompiler.cmake"
    cache_values = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith("//") and not line.startswith("#"):
                key, _, value = line.partition("=")
                cache_values[key.split(":", 1)[0]] = value
    compiler_text = compiler_config.read_text(encoding="utf-8") if compiler_config.exists() else ""
    def compiler_setting(name: str) -> str:
        match = re.search(rf'^set\({name} "([^"]*)"\)$', compiler_text, re.MULTILINE)
        return match.group(1) if match else "unknown"
    source_paths = [
        repo / "benchmarks/reporting/mpc01/main.cpp",
        repo / "benchmarks/reporting/mpc01/model.cpp",
        repo / "benchmarks/reporting/mpc01/fixtures.cpp",
        repo / "benchmarks/reporting/mpc01/osqp_adapter.cpp",
        repo / "benchmarks/reporting/mpc01/hpipm_adapter.cpp",
        repo / "benchmarks/reporting/mpc01/native/CMakeLists.txt",
        repo / "scripts/reports/mpc01/run_resource_limited_attempts.py",
        repo / "scripts/reports/mpc01/run_exact_checker_limited.py",
        repo / "scripts/reports/mpc01/verify_saved_exact_optimality.py",
    ]
    return {
        "schema": "csl.mpc01-build-identity/1",
        "source_revision": revision,
        "working_tree_changes_included": True,
        "binary_path": str(binary.resolve()),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "cmake_cache_path": str(cache),
        "build_type": cache_values.get("CMAKE_BUILD_TYPE", "unknown"),
        "cxx_compiler": cache_values.get("CMAKE_CXX_COMPILER", "unknown"),
        "cxx_compiler_id": compiler_setting("CMAKE_CXX_COMPILER_ID"),
        "cxx_compiler_version": compiler_setting("CMAKE_CXX_COMPILER_VERSION"),
        "cmake_version": compiler_config.parent.name if compiler_config.exists() else "unknown",
        "release_flags": {
            "c": cache_values.get("CMAKE_C_FLAGS_RELEASE", "unknown"),
            "cxx": cache_values.get("CMAKE_CXX_FLAGS_RELEASE", "unknown"),
        },
        "mpc01_report_enabled": cache_values.get("CSL_BUILD_MPC01_REPORT", "unknown"),
        "dependency_pins": {
            "osqp": "1.0.0",
            "hpipm": "e3a56c1caddd7f12d125d84f337b9a9e5c186271",
            "blasfeo": "d6251233923c9b475fe894fb729fb63ab693e301",
        },
        "source_files": {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source_paths},
        "postprocess_sources": {
            str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (repo / "scripts/reports/mpc01/summarize_per_attempt.py",
                         repo / "scripts/reports/mpc01/b04_native_smoke_projection.py")
        },
    }


def run(args: argparse.Namespace) -> int:
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=False)
    host = {"platform": sys.platform, "logical_cpu_count": os.cpu_count(),
            "load_average_before": os.getloadavg()}
    started_at = datetime.now(timezone.utc).isoformat()
    rows = root / "attempts.jsonl"
    index = 0
    with rows.open("x", encoding="utf-8") as records:
        for repetition in range(args.repetitions):
            # Rotate solver order by repetition while keeping cold/warm pairs adjacent.
            methods = METHODS if repetition % 2 == 0 else tuple(reversed(METHODS))
            for fixture in FIXTURES:
                for method in methods:
                    for start_mode in START_MODES:
                        command = [
                            "systemd-run", "--user", "--scope", "--quiet",
                            "--property", f"MemoryMax={MEMORY_MAX_BYTES}",
                            "--property", "MemorySwapMax=0",
                            "--property", "CPUQuota=100%",
                            sys.executable, str(Path(__file__).resolve()), "--worker",
                            "--output-dir", str(root), "--binary", args.binary,
                            "--index", str(index), "--fixture", fixture,
                            "--method", method, "--start-mode", start_mode,
                            "--repetition", str(repetition),
                        ]
                        completed = subprocess.run(command, text=True, capture_output=True)
                        output = completed.stdout.strip().splitlines()
                        if output:
                            try:
                                record = json.loads(output[-1])
                            except json.JSONDecodeError:
                                record = {"schema": "csl.mpc01-resource-attempt/1", "index": index,
                                          "fixture": fixture, "method": method, "start_mode": start_mode,
                                          "repetition": repetition, "status": "failed",
                                          "termination": "failed", "systemd_stdout": completed.stdout,
                                          "systemd_stderr": completed.stderr}
                        else:
                            record = {"schema": "csl.mpc01-resource-attempt/1", "index": index,
                                      "fixture": fixture, "method": method, "start_mode": start_mode,
                                      "repetition": repetition, "status": "failed", "termination": "failed",
                                      "systemd_stdout": completed.stdout, "systemd_stderr": completed.stderr}
                        records.write(json.dumps(record, sort_keys=True) + "\n")
                        records.flush()
                        if completed.returncode != 0:
                            print(f"attempt {index} {fixture}/{method}/{start_mode}: {record['status']}",
                                  file=sys.stderr)
                        index += 1
    summary = {"schema": "csl.mpc01-resource-attempt-summary/1", "attempts": index,
               "completed": 0, "failed": 0, "timed_out": 0, "resource_limited": 0,
               "repetitions": args.repetitions, "fixtures": list(FIXTURES),
               "methods": list(METHODS), "start_modes": list(START_MODES)}
    completed_events = []
    all_rows = [json.loads(line) for line in rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = args.repetitions * len(FIXTURES) * len(METHODS) * len(START_MODES)
    if len(all_rows) != expected or [row.get("index") for row in all_rows] != list(range(expected)):
        raise RuntimeError(f"expected {expected} ordered attempts, received {len(all_rows)}")
    for row in all_rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
        if row.get("attempt") is not None:
            event = row["attempt"]
            if (event.get("method") != row["method"] or event.get("start_mode") != row["start_mode"] or
                    event.get("repetition") != row["repetition"]):
                raise RuntimeError(f"attempt metadata mismatch at index {row['index']}")
            event = dict(row["attempt"])
            event["resource_profile"] = {
                "schema": "csl.mpc01-per-attempt-resource-receipt/1",
                "status": row["status"],
                "attempt_wall_time_ns": row["attempt_wall_time_ns"],
                "enforced": row["enforced"],
                "observed": row["observed"],
                "stdout_sha256": row["stdout_sha256"],
                "stderr_sha256": row["stderr_sha256"],
            }
            completed_events.append(event)
        if row.get("status") == "completed":
            if (row.get("enforced", {}).get("memory_max_bytes") != MEMORY_MAX_BYTES or
                    row.get("enforced", {}).get("memory_swap_max_bytes") != 0 or
                    row.get("enforced", {}).get("wall_watchdog_seconds") != ATTEMPT_TIMEOUT_SECONDS):
                raise RuntimeError(f"resource limits missing at index {row['index']}")
            for field, hash_field in (("stdout_file", "stdout_sha256"), ("stderr_file", "stderr_sha256")):
                path = root / row[field]
                if hashlib.sha256(path.read_bytes()).hexdigest() != row[hash_field]:
                    raise RuntimeError(f"{field} hash mismatch at index {row['index']}")
    if len(completed_events) != summary["completed"]:
        raise RuntimeError("completed native event count differs from completed attempt count")
    (root / "native-attempts.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                for event in completed_events), encoding="utf-8")
    binary = Path(args.binary).resolve()
    record_path = root / "comparison-records.jsonl"
    records_result = subprocess.run(
        [str(binary), "--records-from-attempts", str(root / "native-attempts.jsonl"), str(record_path)],
        text=True, capture_output=True)
    if records_result.returncode != 0:
        raise RuntimeError(f"canonical record construction failed: {records_result.stderr}")
    (root / "build-identity.json").write_text(
        json.dumps(build_identity(root, binary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    host["load_average_after"] = os.getloadavg()
    (root / "capture-profile.json").write_text(json.dumps({
        "schema": "csl.mpc01-per-attempt-capture-profile/1",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "attempt_scope": "one fixture, solver, start mode and repetition per transient systemd scope",
        "attempt_count": index,
        "attempt_wall_limit_seconds": ATTEMPT_TIMEOUT_SECONDS,
        "attempt_memory_limit_bytes": MEMORY_MAX_BYTES,
        "attempt_memory_swap_limit_bytes": 0,
        "maximum_concurrent_jobs": 1,
        "solver_threads": 1,
        "host": host,
    }, indent=2, sort_keys=True) + "\n")
    checksums = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (root / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")
    return 0 if summary["completed"] == index else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--fixture", choices=FIXTURES, default=FIXTURES[0])
    parser.add_argument("--method", choices=METHODS, default=METHODS[0])
    parser.add_argument("--start-mode", choices=START_MODES, default=START_MODES[0])
    parser.add_argument("--repetition", type=int, default=0)
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 1000:
        parser.error("--repetitions must be from 1 to 1000")
    return worker(args) if args.worker else run(args)


if __name__ == "__main__":
    raise SystemExit(main())

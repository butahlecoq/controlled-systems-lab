"""Collect one fixed-source EXT-01 run; copy this exact script into the report tooling."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import psutil


ROOT = Path.cwd().resolve()
BUILD = ROOT / "build" / "ext01-report"
OUT = BUILD / "evidence"
EXE = BUILD / "Release" / "csl_ext01_fixed_plan_report.exe"
SOURCE = "fd75a63657bc6b1d8cbd26c644bd8fb39cc1a3ec"
HARNESS = "11b7bc74e4756bafc2c6c450628d10c6a62f8f39"
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import collector_common as common


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True,
                                        ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def validate(events: bytes, *, minimum_interval: bool = True) -> tuple[list[dict], list[dict]]:
    rows = [json.loads(line) for line in events.splitlines()]
    expected = ["l19", "integrator_feasible", "integrator_violation", "b08_rounded"]
    if len(rows) != 32:
        raise ValueError(f"expected 32 raw trial rows, observed {len(rows)}")
    for round_number in range(8):
        group = rows[4 * round_number:4 * (round_number + 1)]
        names = expected if round_number % 2 == 0 else list(reversed(expected))
        if [row.get("fixture") for row in group] != names:
            raise ValueError("alternating fixture order differs")
        for row in group:
            fixture = row["fixture"]
            batch = 1 if fixture == "b08_rounded" else 10000 if fixture == "l19" else 5000
            if (row.get("schema") != "csl.ext01-raw-trial/1" or
                row.get("round") != round_number or
                row.get("warmup") is not (round_number == 0) or
                row.get("batch") != batch or row.get("checked_calls") != batch or
                type(row.get("elapsed_ns")) is not int or
                (minimum_interval and row["elapsed_ns"] < 20_000_000)):
                raise ValueError("raw trial envelope, work, or interval differs")
            result = row["result"]
            if fixture == "l19":
                if (result.get("status") != "numerical_value" or
                    result.get("worst_value") != 1 or result.get("maximizer") != [0] or
                    result.get("evaluated_vertices") != 3 or
                    result.get("sampled_points") != [0, 1, 2] or
                    result.get("observed_objective_values") != [1, 0, 1] or
                    result.get("stationary_midpoint_value") != 0):
                    raise ValueError("L19 oracle mismatch")
            elif fixture == "integrator_feasible":
                if result != {"status": "numerical_reachable", "stages": 3,
                              "terminal_candidates": 4, "terminal_worst_value": 4}:
                    raise ValueError("integrator feasible oracle mismatch")
            elif fixture == "integrator_violation":
                if result != {"status": "robust_violation", "stage": 1,
                              "violating_successor": [-1]}:
                    raise ValueError("integrator violation oracle mismatch")
            elif (result.get("status") != "numerical_reference" or
                  result.get("plan_count") != 625 or
                  result.get("disturbance_histories") != 160000 or
                  result.get("ties_at_1e-8") != 3 or
                  abs(result.get("minimum_worst_value", float("inf")) - 67.150601101407) > 1e-8):
                raise ValueError("B08 rounded oracle mismatch")
    measured = [row for row in rows if not row["warmup"]]
    summary = []
    for fixture in expected:
        group = [row for row in measured if row["fixture"] == fixture]
        values = [row["elapsed_ns"] for row in group]
        if len(values) != 7:
            raise ValueError("expected seven observations per fixture")
        summary.append({"fixture": fixture, "attempts": len(group), "successes": len(group),
                        "failures": 0, "batch": group[0]["batch"],
                        "median_elapsed_ns": statistics.median(values),
                        "min_elapsed_ns": min(values), "max_elapsed_ns": max(values)})
    return rows, summary


def run_monitored(name: str, *, command_override: list[str] | None = None) -> dict:
    command = command_override or [str(EXE), "--measure", "7"]
    start = time.perf_counter_ns()
    samples = []
    stdout_path = OUT / f"{name}.stdout.jsonl"
    stderr_path = OUT / f"{name}.stderr.txt"
    timed_out = False
    try:
        with stdout_path.open("wb") as output, stderr_path.open("wb") as errors:
            with subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=errors) as process:
                observed = psutil.Process(process.pid)
                while process.poll() is None:
                    if time.perf_counter_ns() - start > 120_000_000_000:
                        timed_out = True
                        process.kill()
                        break
                    try:
                        cpu = observed.cpu_times()
                        rss = observed.memory_info().rss
                        samples.append({"elapsed_ns": time.perf_counter_ns() - start,
                                        "cpu_seconds": cpu.user + cpu.system,
                                        "rss_bytes": rss})
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(0.02)
                return_code = process.wait()
            output.flush()
            errors.flush()
        stdout, stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
    except OSError as error:
        stdout, stderr, return_code = b"", str(error).encode(), 127
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
    wall = time.perf_counter_ns() - start
    save_json(f"{name}.process.json", {
        "schema": "csl.ext01-process-capture/1",
        "command": ["TEST_COMMAND"] if command_override else ["REPORT_EXE", "--measure", "7"],
        "return_code": return_code, "timed_out": timed_out, "wall_ns": wall,
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
        "samples": samples,
        "max_observed_rss_bytes": max((row["rss_bytes"] for row in samples), default=None),
        "last_observed_cpu_seconds": samples[-1]["cpu_seconds"] if samples else None})
    if return_code != 0 or stderr or timed_out:
        raise ValueError(f"{name} process failed; raw stdout/stderr retained")
    return {"stdout": stdout, "wall_ns": wall, "samples": samples}


def main() -> None:
    if ROOT != Path(__file__).resolve().parents[3]:
        raise ValueError("run collector from the configured source root")
    if git("rev-parse", "HEAD") != HARNESS or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source must be the exact clean reviewed harness commit")
    source_delta = git("diff", "--name-only", SOURCE, HARNESS).splitlines()
    if sorted(source_delta) != sorted([
        "CMakeLists.txt", "benchmarks/reporting/ext01/fixed_plan_driver.cpp",
        "cmake/OptionalReports.cmake", "scripts/reports/ext01/README.md",
        "scripts/reports/ext01/check_smoke.py"]):
        raise ValueError("source-to-harness delta differs from reviewed report harness")
    if not EXE.is_file():
        raise ValueError("Release report binary absent")
    # The shared collector produces a fresh clean verbose Release rebuild log.
    def run_build(command: list[str]) -> tuple[str, str, int, bool]:
        cmake = "C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
        completed = subprocess.run([cmake, *command[1:]], cwd=ROOT,
                                   capture_output=True, timeout=600)
        return (completed.stdout.decode("utf-8", errors="replace"),
                completed.stderr.decode("utf-8", errors="replace"),
                completed.returncode, False)
    common.fresh_release_build(BUILD, "csl_ext01_fixed_plan_report",
                               OUT / "fresh-build.json", ROOT,
                               source_commit=SOURCE, harness_commit=HARNESS,
                               run=run_build,
                               validate_log=lambda: common.validate_build_log(
                                   OUT / "fresh-build.json", BUILD, EXE, ROOT))
    graph = common.release_graph(BUILD, EXE, ROOT,
        target_name="csl_ext01_fixed_plan_report",
        required={"csl_ext01_fixed_plan_report", "csl_fixed_plan_disturbance",
                  "csl_worst_case_vertex", "csl_objectives", "csl_model", "csl_sets"})
    save_json("build-graph.json", graph)
    cpu = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    host_before = psutil.cpu_percent(interval=1.0)
    profile = run_monitored("profile")
    profile_rows, _ = validate(profile["stdout"], minimum_interval=False)
    host_between = psutil.cpu_percent(interval=1.0)
    measurement = run_monitored("accepted")
    rows, summary = validate(measurement["stdout"])
    host_after = psutil.cpu_percent(interval=1.0)
    if sum(row["elapsed_ns"] for row in rows) > measurement["wall_ns"]:
        raise ValueError("nested trial intervals exceed child process wall time")
    if git("rev-parse", "HEAD") != HARNESS or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source changed during collection")
    raw = measurement["stdout"]
    record = {
        "schema": "csl.ext01-fixed-plan-records/1",
        "report_id": "ext01-fixed-plan-20261016-11b7bc74",
        "source_commit": SOURCE, "harness_commit": HARNESS,
        "source_tree": git("rev-parse", "HEAD^{tree}"),
        "source_delta": source_delta,
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "build": {"configuration": "Release", "binary_sha256": sha(EXE.read_bytes()),
                  "driver_sha256": sha((ROOT / "benchmarks/reporting/ext01/fixed_plan_driver.cpp").read_bytes()),
                  "fresh_build_sha256": sha((OUT / "fresh-build.json").read_bytes()),
                  "graph_sha256": sha((OUT / "build-graph.json").read_bytes()),
                  "compiler": graph["compiler"], "cmake": graph["cmake"]},
        "inputs": {"b08_saved_reference_sha256": sha((ROOT / "docs/research/reference-b08.json").read_bytes()),
                   "authored_fixture_sha256": sha((ROOT / "benchmarks/reporting/ext01/fixed_plan_driver.cpp").read_bytes()),
                   "assumptions": "Independent compact V disturbances, affine model, convex H safety; displayed rounded B08 arrays."},
        "environment": {"system": platform.system(), "release": platform.release(),
                        "version": platform.version(), "machine": platform.machine(),
                        "processor": platform.processor(), "physical_cores": cpu,
                        "logical_processors": logical,
                        "memory_total_bytes": psutil.virtual_memory().total,
                        "python": platform.python_version(), "psutil": psutil.__version__,
                        "requested_driver_workers": 1,
                        "actual_native_threads": None,
                        "actual_native_threads_reason": "No native thread-count counter in the report driver; standalone process is sequential at the fixture loop.",
                        "host_cpu_percent_before_profile": host_before,
                        "host_cpu_percent_between_runs": host_between,
                        "host_cpu_percent_after_measurement": host_after,
                        "concurrent_work_note": "No other known local heavy build active; ordinary background processes not controlled."},
        "arithmetic": {"type": "binary64", "objective_policy_absolute_tolerance": 1e-8,
                       "objective_policy_relative_tolerance": 1e-8,
                       "b08_tie_absolute_tolerance": 1e-8,
                       "assurance": "numerical; no validated rounding enclosure"},
        "timing": {"unit": "ns", "clock": "steady_clock",
                   "scope": "Fixture construction, public API calls, literal checks and JSON result object; excludes process startup, JSONL serialization, persistence, rendering.",
                   "warmup_rounds": 1, "measured_rounds": 7,
                   "minimum_admitted_batch_interval_ns": 20_000_000,
                   "interval_interpretation": "The L19 10000-call batch is about 44 ms on this host; report its batch time with range, not an extrapolated single-call latency or throughput claim.",
                   "workspace_reuse": "Fixture and API results constructed anew for each checked call; one warmup round excluded.",
                   "order": "Alternating fixture order by round", "profile_is_reported": False,
                   "raw_sha256": sha(raw), "stderr_sha256": sha((OUT / "accepted.stderr.txt").read_bytes())},
        "attempts": len(rows), "successes": len(rows), "failures": 0,
        "summary": summary, "trials": rows,
        "performance_conclusion": "Exploratory single-adapter observations; no comparator or speedup claim."
    }
    save_json("records.json", record)
    save_json("collection-status.json", {"status": "complete", "schema": "csl.ext01-collection-status/1",
                                         "records_sha256": sha((OUT / "records.json").read_bytes()),
                                         "raw_sha256": sha(raw), "failure_count": 0,
                                         "profile_attempts": len(profile_rows)})
    print("saved 32 validated trial records at", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        (OUT / "collection-error.txt").write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        raise

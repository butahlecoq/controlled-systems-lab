"""Validate EXT-07 capture receipts and save an immutable report record."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess


LEGACY_SOURCE_FILES = (
    "driver.cpp", "smoke.jsonl", "measure.jsonl", "smoke.stderr.txt",
    "measure.stderr.txt", "prebuild.json", "postrun.json", "host.json",
    "configure.log", "build.log", "CMakeCXXCompiler.raw.cmake",
)
PROCESS_CPU_SOURCE_FILES = ("driver.cpp", "process_cpu_json.hpp", *LEGACY_SOURCE_FILES[1:])
SOURCE_FILES = ("driver.cpp", "process_cpu_json.hpp", "operation_cpu_json.hpp",
                *LEGACY_SOURCE_FILES[1:])
EXPECTED_PROVIDER = "csl.lp.highs@1.1.0+highs.1.11.0"
EXPECTED_VERIFIER = "csl.hybrid.one-step-scalar-interval"
TOLERANCE = 1e-8


def source_files_for_record(record: dict) -> tuple[str, ...]:
    if record.get("schema") == "csl.ext07-hybrid-profile-report/1":
        return LEGACY_SOURCE_FILES
    if record.get("schema") == "csl.ext07-hybrid-profile-report/2":
        return PROCESS_CPU_SOURCE_FILES
    require(record.get("schema") == "csl.ext07-hybrid-profile-report/3",
            "Unsupported EXT-07 report schema")
    return SOURCE_FILES


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "Expected JSON object: " + path.name)
    return value


def jsonl(path: Path, expected_count: int) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(rows) == expected_count and all(isinstance(row, dict) for row in rows),
            "EXT-07 JSONL row count or shape differs: " + path.name)
    return rows


def validate_run(row: dict, phase: str, repetition: int, calls: int,
                 process_cpu: bool = True, operation_cpu: bool = False) -> None:
    require(row.get("phase") == phase and row.get("repetition") == repetition and
            row.get("calls") == calls and row.get("failures") == 0 and
            row.get("status") == "passed" and row.get("path_count") == 1,
            "EXT-07 run status or identity differs")
    require(row.get("relation_rows") == 7 and row.get("relation_matrix_elements") == 28,
            "EXT-07 joint relation resource record differs")
    require(abs(row.get("objective", float("nan"))) <= TOLERANCE and
            abs(row.get("control", float("nan"))) <= TOLERANCE,
            "EXT-07 optimizer result differs from analytic zero minimum")
    require(row.get("provider") == EXPECTED_PROVIDER and row.get("termination") == "completed" and
            row.get("outcome") == "optimal", "EXT-07 solver identity or outcome differs")
    require(row.get("verifier") == EXPECTED_VERIFIER and row.get("verifier_version") == "1" and
            row.get("feasibility") == row.get("optimality") == row.get("coverage") == "established",
            "EXT-07 complete-family verifier result differs")
    if process_cpu:
        validate_process_cpu_observations(row, calls, 1)
    if operation_cpu:
        validate_operation_observations(row, calls, [8])
    for name in ("setup_total_ns", "assembly_total_ns", "solve_total_ns", "verify_total_ns",
                 "end_to_end_total_ns"):
        require(isinstance(row.get(name), int) and row[name] > 0,
                "EXT-07 timing field unavailable or nonpositive: " + name)
    for name in ("objective_lower", "objective_upper"):
        value = row.get(name)
        require(value is None or abs(value) <= TOLERANCE,
                "EXT-07 solver objective bound excludes the analytic optimum")
    for name in ("primal_row_violation", "primal_variable_violation"):
        value = row.get(name)
        require(value is None or 0 <= value <= TOLERANCE,
                "EXT-07 solver residual exceeds the reported feasibility tolerance")
    require(not row.get("error"), "EXT-07 driver recorded an error")


def validate_process_cpu_observations(row: dict, calls: int, branches: int) -> None:
    observations = row.get("process_cpu_observations")
    require(isinstance(observations, list) and len(observations) == calls,
            "EXT-07 process CPU observation count differs from calls")
    allowed_reasons = {"unsupported_platform", "clock_read_failed", "clock_regressed"}
    for call in observations:
        require(isinstance(call, list) and len(call) == branches,
                "EXT-07 process CPU observations do not match branch inventory")
        for value in call:
            require(isinstance(value, dict), "EXT-07 process CPU observation is not an object")
            if value.get("status") == "observed":
                nanos = value.get("nanoseconds")
                require(isinstance(nanos, int) and not isinstance(nanos, bool) and nanos >= 0 and
                        set(value) == {"status", "nanoseconds"},
                        "EXT-07 process CPU duration is invalid")
            else:
                require(value.get("status") == "unavailable" and
                        value.get("reason") in allowed_reasons and
                        set(value) == {"status", "reason"},
                        "EXT-07 process CPU unavailable reason is invalid")


def process_cpu_summary(rows: list[dict], branch_labels: list[str]) -> dict:
    result = []
    for index, label in enumerate(branch_labels):
        observed = []
        unavailable = {}
        for row in rows:
            for call in row["process_cpu_observations"]:
                value = call[index]
                if value["status"] == "observed":
                    observed.append(value["nanoseconds"])
                else:
                    reason = value["reason"]
                    unavailable[reason] = unavailable.get(reason, 0) + 1
        result.append({
            "branch": label,
            "observed_calls": len(observed),
            "unavailable_calls": sum(unavailable.values()),
            "unavailable_reasons": unavailable,
            "min_nanoseconds": min(observed) if observed else None,
            "median_nanoseconds": int(statistics.median(observed)) if observed else None,
            "max_nanoseconds": max(observed) if observed else None,
        })
    return {
        "scope": "process CPU accumulated across all threads during workspace creation and branch execution",
        "attribution": "process-scoped, not provider-only; unrelated concurrent process work may contribute",
        "branches": result,
    }


OPERATION_KINDS = {"initial_state", "post_state_invariant", "mode_flow",
                   "continuous_control", "pre_reset_invariant", "transition_guard",
                   "reset_relation"}
OPERATION_UNAVAILABLE_REASONS = {"unsupported_platform", "read_failed", "clock_regressed"}


def operation_signature(operation: dict) -> tuple:
    return (operation["kind"], operation["stage"], operation["mode"], operation["edge"],
            operation["implementation_id"], operation["implementation_version"],
            operation["joint_variables"])


def validate_operation_observations(row: dict, calls: int,
                                    operations_per_path: list[int]) -> None:
    observations = row.get("operation_observations")
    require(isinstance(observations, list) and len(observations) == calls,
            "EXT-07 operation observation count differs from calls")
    reference = None
    expected_keys = {"kind", "stage", "mode", "edge", "implementation_id", "implementation_version",
                     "joint_variables", "rows_added", "matrix_elements_added",
                     "cumulative_rows", "cumulative_matrix_elements",
                     "elapsed_wall_nanoseconds", "completed", "thread_cpu"}
    for call in observations:
        require(isinstance(call, list) and len(call) == len(operations_per_path),
                "EXT-07 operation paths differ from the path inventory")
        identities = []
        for path_index, path in enumerate(call):
            require(isinstance(path, list) and len(path) == operations_per_path[path_index],
                    "EXT-07 operation count differs from the composer trace")
            path_identities = []
            for operation in path:
                require(isinstance(operation, dict) and set(operation) == expected_keys,
                        "EXT-07 operation record has an invalid shape")
                require(operation["kind"] in OPERATION_KINDS and
                        isinstance(operation["stage"], int) and not isinstance(operation["stage"], bool) and
                        operation["stage"] >= 0 and
                        (operation["mode"] is None or isinstance(operation["mode"], str)) and
                        (operation["edge"] is None or isinstance(operation["edge"], str)) and
                        isinstance(operation["implementation_id"], str) and operation["implementation_id"] and
                        isinstance(operation["implementation_version"], str) and operation["implementation_version"],
                        "EXT-07 operation identity is invalid")
                for name in ("joint_variables", "rows_added", "matrix_elements_added",
                             "cumulative_rows", "cumulative_matrix_elements",
                             "elapsed_wall_nanoseconds"):
                    require(isinstance(operation[name], int) and not isinstance(operation[name], bool) and
                            operation[name] >= 0, "EXT-07 operation count or duration is invalid: " + name)
                require(operation["joint_variables"] > 0 and operation["completed"] is True and
                        operation["matrix_elements_added"] ==
                        operation["rows_added"] * operation["joint_variables"] and
                        operation["cumulative_matrix_elements"] ==
                        operation["cumulative_rows"] * operation["joint_variables"],
                        "EXT-07 successful operation resource deltas differ")
                cpu = operation["thread_cpu"]
                require(isinstance(cpu, dict), "EXT-07 thread CPU observation is not an object")
                if cpu.get("status") == "observed":
                    require(set(cpu) == {"status", "nanoseconds"} and
                            isinstance(cpu["nanoseconds"], int) and
                            not isinstance(cpu["nanoseconds"], bool) and cpu["nanoseconds"] >= 0,
                            "EXT-07 observed thread CPU duration is invalid")
                else:
                    require(cpu.get("status") == "unavailable" and
                            cpu.get("reason") in OPERATION_UNAVAILABLE_REASONS and
                            set(cpu) == {"status", "reason"},
                            "EXT-07 thread CPU unavailable reason is invalid")
                path_identities.append(operation_signature(operation))
            identities.append(path_identities)
        if reference is None:
            reference = identities
        else:
            require(identities == reference,
                    "EXT-07 operation identity/order changed across calls")


def operation_cpu_summary(rows: list[dict]) -> dict:
    summaries = {}
    for row in rows:
        for call in row["operation_observations"]:
            for path_index, path in enumerate(call):
                for operation_index, operation in enumerate(path):
                    key = (path_index, operation_index)
                    summary = summaries.setdefault(key, {"identity": operation_signature(operation),
                        "observed": [], "unavailable": {}})
                    cpu = operation["thread_cpu"]
                    if cpu["status"] == "observed":
                        summary["observed"].append(cpu["nanoseconds"])
                    else:
                        reason = cpu["reason"]
                        summary["unavailable"][reason] = summary["unavailable"].get(reason, 0) + 1
    return {
        "scope": "CPU consumed by the synchronous composing thread during each relation operation",
        "operations": [{
            "path_index": path_index,
            "operation_index": operation_index,
            "identity": {name: value for name, value in zip(
                ("kind", "stage", "mode", "edge", "implementation_id", "implementation_version",
                 "joint_variables"), summary["identity"])},
            "observed_calls": len(summary["observed"]),
            "unavailable_calls": sum(summary["unavailable"].values()),
            "unavailable_reasons": summary["unavailable"],
            "min_nanoseconds": min(summary["observed"]) if summary["observed"] else None,
            "median_nanoseconds": int(statistics.median(summary["observed"])) if summary["observed"] else None,
            "max_nanoseconds": max(summary["observed"]) if summary["observed"] else None,
        } for (path_index, operation_index), summary in sorted(summaries.items())],
    }


def collect(capture: Path, source: Path, output_root: Path) -> Path:
    capture = capture.resolve(strict=True)
    source = source.resolve(strict=True)
    pre, post, host = (read_json(capture / name) for name in
                       ("prebuild.json", "postrun.json", "host.json"))
    commit = pre["commit"]
    require(pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("status") == post.get("status") == [] and
            pre.get("commit") == post.get("commit") == host.get("source_commit") == commit and
            pre.get("tree") == post.get("tree") == host.get("source_tree") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "EXT-07 frozen source receipts differ")
    driver = source / "benchmarks/reporting/ext07/driver.cpp"
    cpu_header = source / "benchmarks/reporting/ext07/process_cpu_json.hpp"
    operation_cpu_header = source / "benchmarks/reporting/ext07/operation_cpu_json.hpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/driver.cpp"], cwd=source),
        "EXT-07 driver differs from its frozen source commit")
    require(cpu_header.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/process_cpu_json.hpp"], cwd=source),
        "EXT-07 CPU JSON helper differs from its frozen source commit")
    require(operation_cpu_header.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/operation_cpu_json.hpp"], cwd=source),
        "EXT-07 operation CPU JSON helper differs from its frozen source commit")
    executable = capture / ("build/Release/csl_ext07_hybrid_report.exe" if os.name == "nt"
                            else "build/csl_ext07_hybrid_report")
    require(sha(executable.read_bytes()) == post.get("executable_sha256"),
            "EXT-07 measured executable hash differs")
    cache = (capture / "CMakeCache.raw.txt").read_text(encoding="utf-8", errors="replace")
    multiconfig_release = ("CMAKE_CONFIGURATION_TYPES:STRING=Debug;Release;MinSizeRel;RelWithDebInfo" in cache and
                           "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache)
    singleconfig_release = ("CMAKE_BUILD_TYPE:STRING=Release" in cache and
                            "CMAKE_GENERATOR:INTERNAL=Unix Makefiles" in cache)
    require(all(key in cache for key in (
        "BUILD_TESTING:BOOL=OFF", "CSL_ENABLE_HIGHS:BOOL=ON",
        "CSL_ENABLE_QHULL:BOOL=OFF", "CSL_BUILD_EXT07_REPORT:BOOL=ON")) and
        (multiconfig_release or singleconfig_release),
        "EXT-07 measured Release configuration differs")
    require((capture / "smoke.stderr.txt").read_bytes() ==
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "EXT-07 report driver wrote stderr")
    smoke = jsonl(capture / "smoke.jsonl", 1)
    measure = jsonl(capture / "measure.jsonl", 8)
    validate_run(smoke[0], "smoke", 0, 1, operation_cpu=True)
    validate_run(measure[0], "warmup", 0, 10, operation_cpu=True)
    for repetition, row in enumerate(measure[1:]):
        validate_run(row, "trial", repetition, 20, operation_cpu=True)
    source_hashes = {name: sha((driver if name == "driver.cpp" else
                                cpu_header if name == "process_cpu_json.hpp" else
                                operation_cpu_header if name == "operation_cpu_json.hpp" else
                                capture / name).read_bytes()) for name in SOURCE_FILES}
    rows = measure[1:]
    def median_total(key: str) -> int:
        return int(statistics.median(row[key] for row in rows))
    scenario = {
        "horizon": 1, "modes": ["coast", "terminal"],
        "allowed_terminal_modes": ["terminal"],
        "edges": [{"id": "coast-to-terminal", "source": "coast", "target": "terminal"}],
        "state_dimension": 1, "control_dimension": 1,
        "initial_mode": "coast", "initial_state": [0],
        "dynamics": {"A": [[1]], "B": [[1]], "offset": [0]},
        "control_interval": [0, 1], "source_invariants": "universal",
        "transition_guard": [0, 0.5], "reset": {"type": "identity"},
        "terminal_invariant": "universal",
        "terminal_mode_data": {
            "flow": {"A": [[1]], "B": [[1]], "offset": [0]},
            "control_set": "universal",
            "active_stages": [1],
            "flow_used_by_horizon": False,
        },
        "terminal_objective": "minimize x_terminal",
        "relation_coordinates": ["x0", "u0", "x_pre1", "x1"],
    }
    unsigned = {
        "schema": "csl.ext07-hybrid-profile-report/3",
        "source_commit": commit,
        "source_tree": pre["tree"],
        "source_sha256": source_hashes,
        "scenario": scenario,
        "scenario_sha256": sha(encoded(scenario)),
        "analytic": {
            "feasible_relation": "x0=0, x_pre1=u0, x1=u0, 0<=u0<=0.5",
            "optimal_family": "x0=u0=x_pre1=x1=0",
            "minimum_objective": 0,
            "expected_path_count": 1,
        },
        "capability_profile": {
            "supported_case": "one-step scalar linear dynamics, bounded interval control/guard, deterministic scalar affine reset, linear objective",
            "dimensions_and_counts": {"horizon": 1, "modes": 2, "edges": 1,
                                      "state_dimension": 1, "control_dimension": 1,
                                      "paths": 1, "joint_variables": 4},
            "assurance": "numerical binary64; this report does not establish validated arithmetic or broader scalability",
        },
        "source_receipts": {"prebuild": pre, "postrun": post},
        "environment": host,
        "measurement": {
            "warmup": measure[0], "trials": rows,
            "raw_smoke_sha256": source_hashes["smoke.jsonl"],
            "raw_measure_sha256": source_hashes["measure.jsonl"],
            "measured_calls": sum(row["calls"] for row in rows),
            "failures": sum(row["failures"] for row in rows),
            "median_batch_end_to_end_ns": median_total("end_to_end_total_ns"),
            "min_batch_end_to_end_ns": min(row["end_to_end_total_ns"] for row in rows),
            "max_batch_end_to_end_ns": max(row["end_to_end_total_ns"] for row in rows),
            "median_phase_total_ns": {key.removesuffix("_total_ns"): median_total(key)
                                       for key in ("setup_total_ns", "assembly_total_ns",
                                                   "solve_total_ns", "verify_total_ns",
                                                   "end_to_end_total_ns")},
            "process_cpu": process_cpu_summary(rows, ["coast-to-terminal"]),
            "operation_thread_cpu": operation_cpu_summary(rows),
            "comparison": "single adapter; descriptive measurements only; no comparator or speedup claim",
        },
        "evidence_scope": "140 successful measured public hybrid portfolio calls over one fixed analytic one-step scalar fixture; each call constructs the path H relation, solves the branch with HiGHS LP and independently verifies its complete interval minimizer family",
        "evidence_limits": [
            "One host, one Release configuration, one fixture, and a numerical binary64 verifier.",
            "Process CPU values sum all process threads during the branch interval; concurrent unrelated process work may contribute and values are not provider-only CPU.",
            "Per-operation CPU measures only the synchronous composing thread and excludes CPU consumed by helper threads.",
            "No comparator, speedup, source-mapped bottleneck, application-scale result, or general scalability claim.",
            "The supported verifier domain is one-step scalar interval systems; continuous multi-stage verification is outside this report.",
        ],
    }
    report_id = "ext07-hybrid-" + sha(encoded(unsigned))[:16]
    record = {**unsigned, "report_id": report_id}
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / report_id
    require(not destination.exists(), "EXT-07 report destination must be new")
    destination.mkdir()
    for name in SOURCE_FILES:
        (destination / name).write_bytes((driver if name == "driver.cpp" else
                                          cpu_header if name == "process_cpu_json.hpp" else
                                          operation_cpu_header if name == "operation_cpu_json.hpp" else
                                          capture / name).read_bytes())
    (destination / "records.json").write_bytes(encoded(record))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.capture, args.source, args.out))

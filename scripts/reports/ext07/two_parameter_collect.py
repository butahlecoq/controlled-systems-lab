"""Validate a two-parameter EXT-07 capture and save versioned raw evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import subprocess

_common_spec = importlib.util.spec_from_file_location(
    "csl_ext07_common_collect", Path(__file__).with_name("ext07_collect.py"))
common = importlib.util.module_from_spec(_common_spec)
assert _common_spec.loader is not None
_common_spec.loader.exec_module(common)
encoded = common.encoded
jsonl = common.jsonl
read_json = common.read_json
require = common.require
sha = common.sha


LEGACY_SOURCE_FILES = (
    "two_parameter_driver.cpp", "smoke.jsonl", "measure.jsonl",
    "smoke.stderr.txt", "measure.stderr.txt", "prebuild.json",
    "postrun.json", "host.json", "configure.log", "build.log",
    "CMakeCXXCompiler.raw.cmake",
)
PROCESS_CPU_SOURCE_FILES = ("two_parameter_driver.cpp", "process_cpu_json.hpp",
                            *LEGACY_SOURCE_FILES[1:])
SOURCE_FILES = ("two_parameter_driver.cpp", "process_cpu_json.hpp",
                "operation_cpu_json.hpp", *LEGACY_SOURCE_FILES[1:])
CAPACITY_SOURCE_FILES = (*SOURCE_FILES, "capacity.jsonl", "capacity.stderr.txt")


def source_files_for_record(record: dict) -> tuple[str, ...]:
    if record.get("schema") == "csl.ext07-hybrid-two-parameter-report/1":
        return LEGACY_SOURCE_FILES
    if record.get("schema") == "csl.ext07-hybrid-two-parameter-report/2":
        return PROCESS_CPU_SOURCE_FILES
    require(record.get("schema") in {"csl.ext07-hybrid-two-parameter-report/3",
                                      "csl.ext07-hybrid-two-parameter-report/4",
                                      "csl.ext07-hybrid-two-parameter-report/5"},
            "Unsupported EXT-07 two-parameter report schema")
    return CAPACITY_SOURCE_FILES if record.get("schema").endswith("/5") else SOURCE_FILES
EXPECTED_PROVIDER = "csl.lp.highs@1.1.0+highs.1.11.0"
SUPPORTED_VERIFIERS = {
    "csl.hybrid.scalar-two-parameter-polytope",
    "csl.hybrid.exact-linear-h",
}
CURRENT_VERIFIER = "csl.hybrid.exact-linear-h"
EXPECTED_PATHS = ["enter-half", "enter-full"]


def validate_run(row: dict, phase: str, repetition: int, calls: int,
                 process_cpu: bool = True, operation_cpu: bool = False,
                 provider_invocation: bool = False) -> None:
    require(row.get("phase") == phase and row.get("repetition") == repetition and
            row.get("calls") == calls and row.get("failures") == 0 and
            row.get("status") == "passed" and row.get("paths") == 2,
            "EXT-07 two-parameter run status or identity differs")
    require(row.get("edge_paths") == EXPECTED_PATHS and
            row.get("relation_rows") == 20 and
            row.get("relation_matrix_elements") == 140,
            "EXT-07 two-parameter path or relation evidence differs")
    require(row.get("provider") == EXPECTED_PROVIDER and
            row.get("verifier") in SUPPORTED_VERIFIERS and
            row.get("feasibility") == row.get("optimality") ==
            row.get("coverage") == "established",
            "EXT-07 two-parameter provider or family result differs")
    if process_cpu:
        common.validate_process_cpu_observations(row, calls, len(EXPECTED_PATHS))
    if operation_cpu:
        common.validate_operation_observations(row, calls, [14, 14])
    if provider_invocation:
        common.validate_provider_invocation_observations(row, calls, len(EXPECTED_PATHS))
    durations = row.get("call_durations_ns")
    require(isinstance(durations, list) and len(durations) == calls and
            all(isinstance(value, int) and value > 0 for value in durations) and
            row.get("end_to_end_total_ns") == sum(durations),
            "EXT-07 two-parameter raw call timings differ")
    require(not row.get("error"), "EXT-07 two-parameter driver recorded an error")


def capacity_summary(rows: list[dict]) -> list[dict]:
    summary = []
    for path_count in (1, 2, 4, 8, 16):
        trials = [row for row in rows if row.get("phase") == "trial" and
                  row.get("paths") == path_count]
        samples = [value for row in trials for value in row["call_durations_ns"]]
        batches = [row["end_to_end_total_ns"] for row in trials]
        summary.append({
            "paths": path_count,
            "repetitions": len(trials),
            "calls_per_repetition": trials[0]["calls"] if trials else 0,
            "measured_calls": len(samples),
            "branch_outcomes": sum(row["paths"] * row["calls"] for row in trials),
            "failures": sum(row["failures"] for row in trials),
            "median_call_ns": int(statistics.median(samples)) if samples else None,
            "min_call_ns": min(samples) if samples else None,
            "max_call_ns": max(samples) if samples else None,
            "median_batch_ns": int(statistics.median(batches)) if batches else None,
            "min_batch_ns": min(batches) if batches else None,
            "max_batch_ns": max(batches) if batches else None,
        })
    return summary


def collect(capture: Path, source: Path, output_root: Path) -> Path:
    capture = capture.resolve(strict=True)
    source = source.resolve(strict=True)
    output_root = output_root.resolve()
    pre = read_json(capture / "prebuild.json")
    post = read_json(capture / "postrun.json")
    commit = pre.get("commit")
    require(pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            isinstance(commit, str) and len(commit) == 40 and
            pre.get("status") == post.get("status") == [] and
            pre.get("tree") == post.get("tree") and
            pre.get("commit") == post.get("commit"),
            "EXT-07 two-parameter source receipts differ")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                    text=True).strip() == commit and
            not subprocess.check_output(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=source, text=True).strip(),
            "EXT-07 two-parameter source checkout is not clean at its receipt")
    require((capture / "smoke.stderr.txt").read_bytes() ==
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "EXT-07 two-parameter driver wrote stderr")
    schema = "csl.ext07-hybrid-two-parameter-report/4"
    capacity_rows: list[dict] | None = None
    if (capture / "capacity.jsonl").is_file():
        require((capture / "capacity.stderr.txt").read_bytes() == b"",
                "EXT-07 capacity sweep wrote stderr")
        capacity_rows = jsonl(capture / "capacity.jsonl", 40)
        expected_counts = (1, 2, 4, 8, 16)
        for count_index, path_count in enumerate(expected_counts):
            rows = capacity_rows[count_index * 8:(count_index + 1) * 8]
            expected_path_ids = (["enter-half", "enter-full"] if path_count == 2 else
                                 [f"enter-{index}" for index in range(path_count)])
            require(rows[0].get("phase") == "warmup" and
                    rows[0].get("paths") == path_count and
                    rows[0].get("calls") == 2 and rows[0].get("failures") == 0 and
                    rows[0].get("edge_paths") == expected_path_ids,
                    "EXT-07 capacity warmup differs")
            for repetition, row in enumerate(rows[1:]):
                require(row.get("phase") == "trial" and
                        row.get("repetition") == repetition and
                        row.get("paths") == path_count and
                        row.get("calls") == 10 and row.get("failures") == 0 and
                        row.get("status") == "passed" and
                        row.get("verifier") == CURRENT_VERIFIER and
                        row.get("feasibility") == row.get("optimality") ==
                        row.get("coverage") == "established" and
                        row.get("edge_paths") == expected_path_ids,
                        "EXT-07 capacity branch or trial evidence differs")
                require(isinstance(row.get("call_durations_ns"), list) and
                        len(row["call_durations_ns"]) == 10 and
                        all(isinstance(value, int) and value > 0
                            for value in row["call_durations_ns"]) and
                        row.get("end_to_end_total_ns") ==
                        sum(row["call_durations_ns"]),
                        "EXT-07 capacity raw timing differs")
                common.validate_process_cpu_observations(row, 10, path_count)
                common.validate_provider_invocation_observations(row, 10, path_count)
                common.validate_operation_observations(row, 10,
                    [14] * path_count)
                branch_observations = row.get("branch_outcome_observations")
                require(isinstance(branch_observations, list) and
                        len(branch_observations) == 10 and
                        all(isinstance(call, list) and len(call) == path_count and
                            [branch.get("path") for branch in call] == expected_path_ids and
                            all(branch.get("optimization") == "optimal" and
                                branch.get("termination") == "completed" and
                                branch.get("feasibility") ==
                                branch.get("optimality") ==
                                branch.get("coverage") == "established"
                                for branch in call)
                            for call in branch_observations),
                        "EXT-07 per-branch solve or verification outcome differs")
        schema = "csl.ext07-hybrid-two-parameter-report/5"
    smoke = jsonl(capture / "smoke.jsonl", 1)
    measure = jsonl(capture / "measure.jsonl", 8)
    validate_run(smoke[0], "smoke", 0, 1, operation_cpu=True, provider_invocation=True)
    validate_run(measure[0], "warmup", 0, 10, operation_cpu=True, provider_invocation=True)
    for repetition, row in enumerate(measure[1:]):
        validate_run(row, "trial", repetition, 20, operation_cpu=True, provider_invocation=True)
    require(all(row.get("verifier") == CURRENT_VERIFIER
                for row in (*smoke, *measure)),
            "Current two-parameter capture did not run the exact linear H verifier")
    driver = source / "benchmarks/reporting/ext07/two_parameter_driver.cpp"
    cpu_header = source / "benchmarks/reporting/ext07/process_cpu_json.hpp"
    operation_cpu_header = source / "benchmarks/reporting/ext07/operation_cpu_json.hpp"
    require(driver.is_file(), "Missing two-parameter measured driver source")
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/two_parameter_driver.cpp"], cwd=source),
        "EXT-07 two-parameter driver differs from its frozen source commit")
    require(cpu_header.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/process_cpu_json.hpp"], cwd=source),
        "EXT-07 CPU JSON helper differs from its frozen source commit")
    require(operation_cpu_header.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext07/operation_cpu_json.hpp"], cwd=source),
        "EXT-07 operation CPU JSON helper differs from its frozen source commit")
    bundle_sources = CAPACITY_SOURCE_FILES if capacity_rows is not None else SOURCE_FILES
    source_hashes = {
        name: sha((driver if name == "two_parameter_driver.cpp" else
                   cpu_header if name == "process_cpu_json.hpp" else
                   operation_cpu_header if name == "operation_cpu_json.hpp" else
                   capture / name).read_bytes()) for name in bundle_sources
    }
    trials = measure[1:]
    host = read_json(capture / "host.json")
    if capacity_rows is not None:
        expected_limit_metadata = {
            "baseline": {"max_horizon": 2, "max_paths": 2},
            "capacity": [{"paths": count, "max_horizon": 2,
                          "max_paths": count} for count in (1, 2, 4, 8, 16)],
        }
        expected_warmup_metadata = {
            "baseline": "One excluded 10-call batch followed by seven measured 20-call batches",
            "capacity": "Two excluded calls per path-count fixture, followed by seven measured batches of 10 calls",
        }
        require(host.get("enumeration_limits") == expected_limit_metadata and
                host.get("warmup_policy") == expected_warmup_metadata,
                "EXT-07 baseline/capacity execution limits or warmups differ")
    cache = (capture / "CMakeCache.raw.txt").read_bytes()
    release_configuration = (
        b"CMAKE_CONFIGURATION_TYPES:STRING=Debug;Release;MinSizeRel;RelWithDebInfo" in cache and
        b"CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache) or (
        b"CMAKE_BUILD_TYPE:STRING=Release" in cache and
        b"CMAKE_GENERATOR:INTERNAL=Unix Makefiles" in cache)
    require(host.get("source_commit") == commit and
            host.get("configuration") == "Release" and
            host.get("cxx_standard") == 20 and
            host.get("absolute_tolerance") == host.get("relative_tolerance") == 1e-8 and
            host.get("cmake_cache_sha256") == sha(cache) and
            release_configuration and
            b"CSL_ENABLE_HIGHS:BOOL=ON" in cache and
            b"CSL_BUILD_EXT07_REPORT:BOOL=ON" in cache and
            b"CSL_ENABLE_QHULL:BOOL=OFF" in cache,
            "EXT-07 two-parameter measurement environment differs")
    scenario = {
        "horizon": 2,
        "modes": ["source", "middle", "terminal"],
        "edges": [
            {"id": "enter-half", "source": "source", "target": "middle",
             "guard": "0 <= x_pre1 <= 0.5"},
            {"id": "enter-full", "source": "source", "target": "middle",
             "guard": "universal"},
            {"id": "finish", "source": "middle", "target": "terminal",
             "guard": "universal"},
        ],
        "state_dimension": 1,
        "control_dimension": 1,
        "initial_state": 0,
        "controls": {"u0": [0, 1], "u1": [0, 1]},
        "dynamics": ["x_pre1 = u0", "x_pre2 = x_post1 + 0*u1",
                      "x_terminal = x_pre2"],
        "resets": "identity on both transitions",
        "terminal_objective": "minimize x_terminal = u0",
        "relation_coordinates": ["x0", "u0", "x_pre1", "x_post1",
                                 "u1", "x_pre2", "x_terminal"],
    }
    analytic = {
        "enter-half": {"feasible_parameter_set":
                       "(u0,u1) in [0,0.5] x [0,1]",
                       "minimizing_face": "u0=0, 0<=u1<=1"},
        "enter-full": {"feasible_parameter_set":
                       "(u0,u1) in [0,1] x [0,1]",
                       "minimizing_face": "u0=0, 0<=u1<=1"},
    }
    unsigned = {
        "schema": schema,
        "source_commit": commit,
        "source_tree": pre["tree"],
        "source_sha256": source_hashes,
        "scenario": scenario,
        "scenario_sha256": sha(encoded(scenario)),
        "analytic": {"paths": analytic, "global_minimum": 0,
                     "tied_paths": EXPECTED_PATHS,
                     "complete_minimizing_families":
                     {path: value["minimizing_face"] for path, value in analytic.items()}},
        "capability_profile": {
            "supported_case": "two-stage scalar system with two bounded non-singleton interval controls; scalar interval invariants/guards; deterministic exactly representable affine resets; scalar linear terminal objective; complete family checked by the exact linear H verifier",
            "dimensions_and_counts": {"horizon": 2, "modes": 3, "edges": 3,
                                      "free_controls": 2, "paths": 2,
                                      "joint_variables": 7},
            "assurance": "numerical binary64 exactness checks; not validated arithmetic",
        },
        "source_receipts": {"prebuild": pre, "postrun": post},
        "environment": host,
        "measurement": {
            "warmup": measure[0], "trials": trials,
            "raw_smoke_sha256": source_hashes["smoke.jsonl"],
            "raw_measure_sha256": source_hashes["measure.jsonl"],
            "measured_calls": sum(row["calls"] for row in trials),
            "failures": sum(row["failures"] for row in trials),
            "median_batch_end_to_end_ns": int(statistics.median(
                row["end_to_end_total_ns"] for row in trials)),
            "min_batch_end_to_end_ns": min(
                row["end_to_end_total_ns"] for row in trials),
            "max_batch_end_to_end_ns": max(
                row["end_to_end_total_ns"] for row in trials),
            "median_call_ns": int(statistics.median(
                value for row in trials for value in row["call_durations_ns"])),
            "process_cpu": common.process_cpu_summary(trials, EXPECTED_PATHS),
            "provider_invocation": common.provider_invocation_summary(trials, EXPECTED_PATHS),
            "operation_thread_cpu": common.operation_cpu_summary(trials),
            "comparison": "one backend and one fixed fixture; descriptive only, no comparator or speedup claim",
        },
        "solver_capacity_profile": None if capacity_rows is None else {
            "fixture": "two-stage scalar fixed-control model with N tied mode paths; each guard admits the common optimum u0=0",
            "path_counts": [1, 2, 4, 8, 16],
            "warmups_excluded": 5,
            "repetitions_per_path_count": 7,
            "calls_per_repetition": 10,
            "measured_calls": 350,
            "branch_outcomes": sum(row["paths"] * row["calls"]
                                    for row in capacity_rows if row["phase"] == "trial"),
            "failures": sum(row["failures"] for row in capacity_rows),
            "results": capacity_summary(capacity_rows),
            "raw_capacity_sha256": sha((capture / "capacity.jsonl").read_bytes()),
            "timing_scope": "per-call setup, path composition, HiGHS solve of every path, candidate-family construction, and ExactLinearHHybridFamilyVerifier coverage of every tied path",
            "claim_limit": "single scalar, two-stage fixture on one host; descriptive capacity evidence only, not a general scalability or solver limit claim",
        },
        "evidence_scope": "140 completed baseline calls; optional capacity sweep adds 350 full public hybrid portfolio calls across 1, 2, 4, 8, and 16 tied paths, with every path solved and every candidate family verified by ExactLinearHHybridFamilyVerifier",
        "evidence_limits": [
            "One host, one Release configuration, and one fixed analytic two-stage fixture.",
            "The controls are independent and bounded; no higher-dimensional parameter polytope is measured.",
            "Provider invocation records use a narrower synchronous wall/CPU interval; process CPU sums all process threads, includes clock sampling, and may include unrelated work.",
            "Provider memory use is unmeasured; the HiGHS adapter refuses finite memory requests rather than claiming enforcement.",
            "No comparator, speedup, source-mapped bottleneck, application-scale result, or scalability claim.",
            "Binary64 checks are numerical assurance and do not establish validated arithmetic.",
            "Per-operation CPU measures only the synchronous composing thread and excludes CPU consumed by helper threads.",
        ],
    }
    report_id = "ext07-hybrid-two-parameter-" + sha(encoded(unsigned))[:16]
    record = {**unsigned, "report_id": report_id}
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / report_id
    require(not destination.exists(), "EXT-07 two-parameter report destination must be new")
    destination.mkdir()
    for name in bundle_sources:
        source_path = (driver if name == "two_parameter_driver.cpp" else
                       cpu_header if name == "process_cpu_json.hpp" else
                       operation_cpu_header if name == "operation_cpu_json.hpp" else capture / name)
        shutil.copyfile(source_path, destination / name)
    (destination / "records.json").write_bytes(encoded(record))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.capture, args.source, args.out))

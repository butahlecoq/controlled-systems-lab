"""Validate a two-parameter EXT-07 capture and save versioned raw evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics

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


SOURCE_FILES = (
    "two_parameter_driver.cpp", "smoke.jsonl", "measure.jsonl",
    "smoke.stderr.txt", "measure.stderr.txt", "prebuild.json",
    "postrun.json", "host.json", "configure.log", "build.log",
    "CMakeCXXCompiler.raw.cmake",
)
EXPECTED_PROVIDER = "csl.lp.highs@1.1.0+highs.1.11.0"
SUPPORTED_VERIFIERS = {
    "csl.hybrid.scalar-two-parameter-polytope",
    "csl.hybrid.exact-linear-h",
}
CURRENT_VERIFIER = "csl.hybrid.exact-linear-h"
EXPECTED_PATHS = ["enter-half", "enter-full"]


def validate_run(row: dict, phase: str, repetition: int, calls: int) -> None:
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
    durations = row.get("call_durations_ns")
    require(isinstance(durations, list) and len(durations) == calls and
            all(isinstance(value, int) and value > 0 for value in durations) and
            row.get("end_to_end_total_ns") == sum(durations),
            "EXT-07 two-parameter raw call timings differ")
    require(not row.get("error"), "EXT-07 two-parameter driver recorded an error")


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
    import subprocess
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                    text=True).strip() == commit and
            not subprocess.check_output(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=source, text=True).strip(),
            "EXT-07 two-parameter source checkout is not clean at its receipt")
    require((capture / "smoke.stderr.txt").read_bytes() ==
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "EXT-07 two-parameter driver wrote stderr")
    smoke = jsonl(capture / "smoke.jsonl", 1)
    measure = jsonl(capture / "measure.jsonl", 8)
    validate_run(smoke[0], "smoke", 0, 1)
    validate_run(measure[0], "warmup", 0, 10)
    for repetition, row in enumerate(measure[1:]):
        validate_run(row, "trial", repetition, 20)
    require(all(row.get("verifier") == CURRENT_VERIFIER
                for row in (*smoke, *measure)),
            "Current two-parameter capture did not run the exact linear H verifier")
    driver = source / "benchmarks/reporting/ext07/two_parameter_driver.cpp"
    require(driver.is_file(), "Missing two-parameter measured driver source")
    source_hashes = {
        name: sha((driver if name == "two_parameter_driver.cpp" else
                   capture / name).read_bytes()) for name in SOURCE_FILES
    }
    trials = measure[1:]
    host = read_json(capture / "host.json")
    cache = (capture / "CMakeCache.raw.txt").read_bytes()
    require(host.get("source_commit") == commit and
            host.get("configuration") == "Release" and
            host.get("cxx_standard") == 20 and
            host.get("absolute_tolerance") == host.get("relative_tolerance") == 1e-8 and
            host.get("cmake_cache_sha256") == sha(cache) and
            b"CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache and
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
        "schema": "csl.ext07-hybrid-two-parameter-report/1",
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
            "comparison": "one backend and one fixed fixture; descriptive only, no comparator or speedup claim",
        },
        "evidence_scope": "140 completed public hybrid portfolio calls; each call assembles both two-stage H relations, solves both branches with registered HiGHS LP, constructs both tied candidate faces, and verifies both complete two-parameter families with ExactLinearHHybridFamilyVerifier",
        "evidence_limits": [
            "One Windows MSVC Release host and one fixed analytic two-stage fixture.",
            "The controls are independent and bounded; no higher-dimensional parameter polytope is measured.",
            "No comparator, speedup, source-mapped bottleneck, application-scale result, or scalability claim.",
            "Binary64 checks are numerical assurance and do not establish validated arithmetic.",
        ],
    }
    report_id = "ext07-hybrid-two-parameter-" + sha(encoded(unsigned))[:16]
    record = {**unsigned, "report_id": report_id}
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / report_id
    require(not destination.exists(), "EXT-07 two-parameter report destination must be new")
    destination.mkdir()
    for name in SOURCE_FILES:
        source_path = driver if name == "two_parameter_driver.cpp" else capture / name
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

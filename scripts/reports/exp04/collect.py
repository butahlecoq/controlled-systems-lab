"""Admit a frozen EXP-04 Release capture; this command never runs the driver."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess

SOURCE = "eb4497e08f1532c732163e677d5d7aa03697c7de"
SOURCE_TREE = "b68a51f8d46cb59c69d4c0add81e1e54d218f19b"
SCHEMA = "csl.exp04-independent-replay/1"
FIELDS = ["phase", "case", "repetition", "calls", "status", "verified",
          "elapsed_ns", "terminal_x", "terminal_y", "objective"]
EXPECTED = {"scalar-endpoint": ("2", "0"), "scalar-even": ("1.5", "0"),
            "plane-forward": ("3", "1"), "plane-reverse": ("2", "1")}
SOURCE_FILES = ("driver.cpp", "smoke.csv", "measure.csv", "smoke.stderr.txt",
                "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json",
                "configure.log", "build.log", "CMakeCache.raw.txt",
                "CMakeCXXCompiler.raw.cmake", "build-provenance.json", "records.json")


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), "expected JSON object: " + path.name)
    return value


def fixture() -> dict:
    scalar = {"plant": "analytic.quadratic-step", "version": "1",
              "source": "EXP-04 declared analytic toy", "state_dimension": 1,
              "parameter": {"name": "quadratic_gain", "value": 1.0, "unit": "dimensionless"},
              "initial_state": [0.0], "physical_times": [0.0, 1.0, 2.0],
              "state_units": ["dimensionless"], "control_units": ["dimensionless"],
              "integration": "exact_discrete_map", "hold": "constant_on_interval",
              "absolute_tolerance": 1e-12, "relative_tolerance": 1e-12,
              "transition": "x[k+1] = x[k] + u[k] + u[k]^2",
              "objective": "terminal state", "objective_unit": "dimensionless"}
    plane = {**scalar, "plant": "analytic.interval-plane",
             "source": "EXP-04 declared two-state toy", "state_dimension": 2,
             "initial_state": [0.0, 0.0], "physical_times": [0.0, 1.0, 3.0],
             "state_units": ["length", "action"], "objective": "terminal length",
             "objective_unit": "length",
             "transition": "x[k+1] = x[k] + (t[k+1]-t[k])*u[k] + u[k]^2; y[k+1] = y[k] + u[k]"}
    cases = {
        "scalar-endpoint": {"plant": scalar, "controls": [[0.0], [1.0]],
                            "expected_states": [[0.0], [0.0], [2.0]], "expected_objective": 2.0},
        "scalar-even": {"plant": scalar, "controls": [[0.5], [0.5]],
                        "expected_states": [[0.0], [0.75], [1.5]], "expected_objective": 1.5},
        "plane-forward": {"plant": plane, "controls": [[0.0], [1.0]],
                          "expected_states": [[0.0, 0.0], [0.0, 0.0], [3.0, 1.0]],
                          "expected_objective": 3.0},
        "plane-reverse": {"plant": plane, "controls": [[1.0], [0.0]],
                          "expected_states": [[0.0, 0.0], [2.0, 1.0], [2.0, 1.0]],
                          "expected_objective": 2.0},
    }
    return {name: {**case, "input_sha256": sha(encoded({"plant": case["plant"],
                                                      "controls": case["controls"]}))}
            for name, case in cases.items()}


def rows(path: Path, purpose: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline=""), strict=True)
    require(reader.fieldnames == FIELDS, "raw driver header differs")
    result = list(reader)
    expected_order = ([("smoke", name, 0, 1) for name in EXPECTED] if purpose == "smoke" else
                      [("warmup", name, 0, 1000) for name in EXPECTED] +
                      [("trial", list(EXPECTED)[(offset + rep) % 4], rep, 1000)
                       for rep in range(7) for offset in range(4)])
    require(len(result) == len(expected_order), "raw driver row count differs")
    for row, (phase, name, rep, calls) in zip(result, expected_order):
        x, y = EXPECTED[name]
        require(None not in row and (row["phase"], row["case"], row["repetition"],
                 row["calls"], row["status"], row["verified"], row["terminal_x"],
                 row["terminal_y"], row["objective"]) ==
                (phase, name, str(rep), str(calls), "complete", "true", x, y, x),
                "unverified or unexpected numerical driver observation")
        require(re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"]) is not None,
                "missing positive replay duration")
    return result


def collect(capture: Path, source: Path, destination: Path) -> Path:
    require(destination.is_dir(), "report collection root missing")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=source, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                                     cwd=source, text=True)
    require(commit == SOURCE and tree == SOURCE_TREE and status == "",
            "collector requires a clean frozen source checkout")
    pre = read_json(capture / "prebuild.json")
    post = read_json(capture / "postrun.json")
    host = read_json(capture / "host.json")
    require(pre.get("schema") == post.get("schema") == "csl.exp04-source-receipt/1" and
            pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("commit") == post.get("commit") == host.get("source_commit") == SOURCE and
            pre.get("tree") == post.get("tree") == host.get("source_tree") == tree and
            pre.get("status") == post.get("status") == host.get("source_status") == [] and
            pre.get("tracked_count") == post.get("tracked_count") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "capture source identity or clean-tree receipts differ")
    driver = source / "benchmarks/reporting/exp04/driver.cpp"
    committed_driver = subprocess.check_output(
        ["git", "show", SOURCE + ":benchmarks/reporting/exp04/driver.cpp"], cwd=source)
    require(driver.read_bytes() == committed_driver,
            "driver source differs from frozen numerical commit")
    executable = capture / "measure-build/Release/csl_exp04_replay_report.exe"
    require(executable.is_file(), "frozen Release executable missing")
    require(sha(executable.read_bytes()) == post.get("executable_sha256"),
            "postrun executable identity differs")
    cache = (capture / "measure-build/CMakeCache.txt").read_text(encoding="utf-8")
    compiler_files = list((capture / "measure-build/CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "one captured C++ compiler identity required")
    compiler = compiler_files[0].read_text(encoding="utf-8")
    require(all(option + ":BOOL=" + value in cache for option, value in
                (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                 ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_EXP04_REPORT", "ON"))) and
            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache and
            'CMAKE_CXX_COMPILER_VERSION "19.44.' in compiler and
            "csl_exp04_replay_report.exe" in (capture / "build.log").read_text(encoding="utf-8-sig"),
            "captured Release build configuration differs")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "driver produced stderr")
    smoke = rows(capture / "smoke.csv", "smoke")
    measured = rows(capture / "measure.csv", "measure")
    require(len(smoke) == 4 and len(measured) == 32, "driver did not execute all cases")
    summary = []
    for name in EXPECTED:
        samples = [int(row["elapsed_ns"]) for row in measured
                   if row["phase"] == "trial" and row["case"] == name]
        require(len(samples) == 7, "seven measured batches required")
        summary.append({"case": name, "batches": 7, "calls_per_batch": 1000,
                        "successes": 7000, "failures": 0,
                        "median_batch_ns": statistics.median(samples),
                        "min_batch_ns": min(samples), "max_batch_ns": max(samples)})
    build = {"configuration": "Release", "compiler": "MSVC 19.44 / Visual Studio 2022",
             "architecture": "x64", "cmake_options": {
                 "BUILD_TESTING": "OFF", "CSL_ENABLE_HIGHS": "OFF",
                 "CSL_ENABLE_QHULL": "OFF", "CSL_BUILD_EXP04_REPORT": "ON"},
             "command": "python -m cmake -S . -B <fresh-build> -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXP04_REPORT=ON; python -m cmake --build <fresh-build> --config Release --target csl_exp04_replay_report",
             "executable_sha256": sha(executable.read_bytes()),
             "driver_source_sha256": sha(driver.read_bytes()),
             "configure_log_sha256": sha((capture / "configure.log").read_bytes()),
             "build_log_sha256": sha((capture / "build.log").read_bytes()),
             "cmake_cache_sha256": sha((capture / "measure-build/CMakeCache.txt").read_bytes()),
             "cmake_compiler_sha256": sha(compiler_files[0].read_bytes()),
             "raw_logs": "Configure/build logs and CMake cache/compiler receipts are saved in the versioned bundle."}
    inputs = fixture()
    record = {"schema": SCHEMA, "source_commit": SOURCE, "source_tree": host["source_tree"],
              "scope": "Independent exact-discrete plant replay for four authored analytic histories",
              "limits": ["No historical B04 plant or complete B04 control history is claimed.",
                         "No nonlinear optimization, feasibility certificate, or optimal family is claimed.",
                         "Descriptive single-adapter timings only; no comparator, speedup, limiter profile, or broad performance inference."],
              "fixtures": inputs, "environment": host, "build": build,
              "source_receipts": {"prebuild": pre, "postrun": post},
              "measurement": {"clock": "std::chrono::steady_clock",
                              "interval": "ReplayRecord.replay_time from entry of public replay to return; per-call durations summed within each 1000-call batch",
                              "excludes": ["driver fixture construction", "post-call literal oracle checks", "CSV serialization", "process launch", "HTML rendering"],
                              "warmup": "one excluded 1000-call batch per case",
                              "measured_order": "seven rotated four-case rounds; 1000 fresh public replay calls per case per round",
                              "workers_requested": 1, "workers_actual": 1,
                              "native_threads_requested": 1, "native_threads_actual": 1,
                              "workspace_reuse": "fresh ReplayRecord for each call; immutable plant and control declarations reused",
                              "internal_counters": "unavailable", "failures": 0,
                              "raw_smoke_sha256": sha((capture / "smoke.csv").read_bytes()),
                              "raw_measure_sha256": sha((capture / "measure.csv").read_bytes()),
                              "trials": measured, "summary": summary}}
    record_id = "exp04-replay-" + sha(encoded(record))[:16]
    record["report_id"] = record_id
    output = destination / record_id
    require(not output.exists(), "immutable report ID already exists")
    output.mkdir(parents=True)
    for name in ("smoke.csv", "measure.csv", "smoke.stderr.txt", "measure.stderr.txt",
                 "host.json", "prebuild.json", "postrun.json", "configure.log", "build.log"):
        shutil.copyfile(capture / name, output / name)
    shutil.copyfile(capture / "measure-build/CMakeCache.txt", output / "CMakeCache.raw.txt")
    shutil.copyfile(compiler_files[0], output / "CMakeCXXCompiler.raw.cmake")
    shutil.copyfile(driver, output / "driver.cpp")
    (output / "build-provenance.json").write_bytes(encoded(build))
    (output / "records.json").write_bytes(encoded(record))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.capture, args.source, args.out))


if __name__ == "__main__":
    main()

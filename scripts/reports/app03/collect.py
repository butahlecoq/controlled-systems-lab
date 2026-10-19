"""Validate a frozen APP-03 capture and save its immutable source records."""
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

SCHEMA = "csl.app03-zonotope-reduction/1"
FIELDS = ["phase", "case", "repetition", "calls", "status", "verified",
          "elapsed_ns", "basis", "output_generators"]
CASES = {
    "diamond-axis-cover": {
        "relation": "outer", "center": [0, 0],
        "input_generators": [[1, 0, 0.5], [0, 1, 0.5]],
        "input_factor_ids": ["x", "y", "diagonal"], "budget": 2,
        "expected_generators": [[1.5, 0], [0, 1.5]],
        "expected_basis": "generator-axis-cover", "expected_count": 2,
        "analytic_support_1_minus_1": {"input": 2, "output": 3}},
    "constrained-axis-cover": {
        "relation": "outer", "center": [0, 0],
        "input_generators": [[2, 0, 0.5, 0.25], [0, 1, 0.5, 0.25]],
        "input_factor_ids": ["shared", "vertical", "diagonal", "small"],
        "input_factor_equality": [[0, 1, 0, 0]], "input_equality_value": [0],
        "budget": 3, "expected_generators": [[2, 0.75, 0], [0, 0, 1.75]],
        "expected_basis": "generator-axis-cover", "expected_count": 3,
        "relaxation": "The input factor equality is omitted by the outer cover."},
    "zero-column-exact": {
        "relation": "equivalent", "center": [1, 2],
        "input_generators": [[2, 0, 0], [0, 0, 3]],
        "input_factor_ids": ["x", "zero", "y"],
        "expected_generators": [[2, 0], [0, 3]],
        "expected_factor_ids": ["x", "y"],
        "expected_basis": "physical-equivalence", "expected_count": 2}}
SOURCE_FILES = ("driver.cpp", "smoke.csv", "measure.csv", "smoke.stderr.txt",
                "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json",
                "configure.log", "build.log", "CMakeCache.raw.txt",
                "CMakeCXXCompiler.raw.cmake", "build-provenance.json", "records.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), "Expected JSON object: " + path.name)
    return value


def fixtures() -> dict:
    return {name: {**value, "input_sha256": sha(encoded({key: item for key, item in
             value.items() if not key.startswith("expected_") and
             key != "analytic_support_1_minus_1"}))}
            for name, value in CASES.items()}


def rows(path: Path, purpose: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"),
                                        newline=""), strict=True)
    require(reader.fieldnames == FIELDS, "Raw APP-03 CSV header differs")
    result = list(reader)
    names = list(CASES)
    expected = ([("smoke", name, 0, 1) for name in names] if purpose == "smoke" else
                [("warmup", name, 0, 100) for name in names] +
                [("trial", names[(offset + rep) % 3], rep, 100)
                 for rep in range(7) for offset in range(3)])
    require(len(result) == len(expected), "APP-03 CSV row count differs")
    for row, (phase, name, rep, calls) in zip(result, expected):
        fixture = CASES[name]
        require(None not in row and
                (row["phase"], row["case"], row["repetition"], row["calls"],
                 row["status"], row["verified"], row["basis"],
                 row["output_generators"]) ==
                (phase, name, str(rep), str(calls), "completed", "true",
                 fixture["expected_basis"], str(fixture["expected_count"])),
                "Unverified APP-03 observation or changed fixture")
        require(re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"]) is not None,
                "Missing positive APP-03 public-call duration")
    return result


def summary(measured: list[dict]) -> list[dict]:
    result = []
    for name in CASES:
        samples = [int(row["elapsed_ns"]) for row in measured
                   if row["phase"] == "trial" and row["case"] == name]
        require(len(samples) == 7, "Seven measured batches required")
        result.append({"case": name, "batches": 7, "calls_per_batch": 100,
                       "successes": 700, "failures": 0,
                       "median_batch_ns": statistics.median(samples),
                       "min_batch_ns": min(samples), "max_batch_ns": max(samples)})
    return result


def collect(capture: Path, source: Path, destination: Path) -> Path:
    capture = capture.resolve(strict=True)
    source = source.resolve(strict=True)
    require(destination.is_dir(), "Report destination root missing")
    pre, post, host = (read_json(capture / name) for name in
                       ("prebuild.json", "postrun.json", "host.json"))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                     text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=source,
                                   text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1",
                                      "--untracked-files=all"], cwd=source, text=True)
    require(commit == pre.get("commit") == post.get("commit") ==
            host.get("source_commit") and tree == pre.get("tree") ==
            post.get("tree") == host.get("source_tree") and status == "" and
            pre.get("status") == post.get("status") == host.get("source_status") == [] and
            pre.get("schema") == post.get("schema") == "csl.app03-source-receipt/1" and
            pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("tracked_count") == post.get("tracked_count") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "Capture does not match a clean frozen source checkout")
    driver = source / "benchmarks/reporting/app03/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/app03/driver.cpp"], cwd=source),
        "APP-03 driver differs from frozen source")
    executable = capture / "measure-build/Release/csl_app03_zonotope_report.exe"
    require(executable.is_file() and sha(executable.read_bytes()) ==
            post.get("executable_sha256"), "Frozen APP-03 executable differs")
    cache = capture / "measure-build/CMakeCache.txt"
    compiler_files = list((capture / "measure-build/CMakeFiles").glob(
        "*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "One C++ compiler receipt required")
    compiler = compiler_files[0]
    cache_text = cache.read_text(encoding="utf-8")
    require(all(option + ":BOOL=" + value in cache_text for option, value in
                (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                 ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP03_REPORT", "ON"))) and
            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache_text,
            "Captured APP-03 Release configuration differs")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "APP-03 driver produced stderr")
    smoke = rows(capture / "smoke.csv", "smoke")
    measured = rows(capture / "measure.csv", "measure")
    require(len(smoke) == 3 and len(measured) == 24,
            "APP-03 capture omitted a case")
    build = {"configuration": "Release", "architecture": "x64",
             "compiler_receipt": compiler.read_text(encoding="utf-8"),
             "cmake_options": {"BUILD_TESTING": "OFF", "CSL_ENABLE_HIGHS": "OFF",
                 "CSL_ENABLE_QHULL": "OFF", "CSL_BUILD_APP03_REPORT": "ON"},
             "executable_sha256": sha(executable.read_bytes()),
             "driver_source_sha256": sha(driver.read_bytes()),
             "configure_log_sha256": sha((capture / "configure.log").read_bytes()),
             "build_log_sha256": sha((capture / "build.log").read_bytes()),
             "cmake_cache_sha256": sha(cache.read_bytes()),
             "cmake_compiler_sha256": sha(compiler.read_bytes())}
    record = {"schema": SCHEMA, "source_commit": commit, "source_tree": tree,
              "module": "CSL::approximation zonotope reduction adapters",
              "backend": "native stored-binary64 generator construction and independent admission",
              "fixtures": fixtures(), "environment": host, "build": build,
              "source_receipts": {"prebuild": pre, "postrun": post},
              "scope": "Two planar outer covers and one planar exact zero-column reduction",
              "limits": ["The outer inclusion check covers stored binary64 generator coefficients.",
                         "Input factor equalities are relaxed for the constrained outer case.",
                         "No finite approximation error bound or validated real-arithmetic guarantee is supplied.",
                         "No optimizer, competitor, speedup, source-mapped limiter or scalability claim is supported."],
              "measurement": {"clock": "std::chrono::steady_clock",
                  "interval": "Each public registered operation, including selection, fresh workspace, construction and independent admission for outer cases; per-call intervals summed within a 100-call batch",
                  "excludes": ["fixture and registry construction", "post-call literal oracle",
                               "CSV serialization", "process launch", "HTML rendering"],
                  "warmup": "one excluded 100-call batch per case",
                  "measured_order": "seven rotated three-case rounds, 100 calls per case per round",
                  "workers_requested": 1, "workers_actual": 1,
                  "native_threads_requested": 1, "native_threads_actual": 1,
                  "workspace_reuse": "fresh provider workspace per call; authored input and registry reused",
                  "internal_counters": "unavailable", "failures": 0,
                  "raw_smoke_sha256": sha((capture / "smoke.csv").read_bytes()),
                  "raw_measure_sha256": sha((capture / "measure.csv").read_bytes()),
                  "trials": measured, "summary": summary(measured)}}
    report_id = "app03-zonotope-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = destination / report_id
    require(not output.exists(), "Immutable APP-03 report ID already exists")
    output.mkdir()
    for name in ("smoke.csv", "measure.csv", "smoke.stderr.txt",
                 "measure.stderr.txt", "host.json", "prebuild.json",
                 "postrun.json", "configure.log", "build.log"):
        shutil.copyfile(capture / name, output / name)
    shutil.copyfile(cache, output / "CMakeCache.raw.txt")
    shutil.copyfile(compiler, output / "CMakeCXXCompiler.raw.cmake")
    shutil.copyfile(driver, output / "driver.cpp")
    (output / "build-provenance.json").write_bytes(encoded(build))
    (output / "records.json").write_bytes(encoded(record))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.capture, args.source, args.out))

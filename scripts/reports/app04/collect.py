"""Validate one clean frozen APP-04 Release capture and save source records."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess

SCHEMA = "csl.app04-directional-ellipsoid/1"
FIELDS = ["phase", "case", "repetition", "calls", "status", "verified",
          "elapsed_ns", "basis", "vertices", "radius_x", "radius_y"]
CASES = {
    "square-axis": {"input_vertices": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
                    "orientation_rows": [[1, 0], [0, 1]], "center": [0, 0],
                    "projected_bounds": [1, 1], "relation": "outer",
                    "budget": 1, "expected_vertices": 4},
    "square-diagonal": {"input_vertices": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
                        "orientation_rows": [[1, 1], [1, -1]], "center": [0, 0],
                        "projected_bounds": [2, 2], "relation": "outer",
                        "budget": 1, "expected_vertices": 4},
    "horizontal-segment": {"input_vertices": [[-1, 0], [1, 0]],
                           "orientation_rows": [[1, 0], [0, 1]], "center": [0, 0],
                           "projected_bounds": [1, 0], "relation": "outer",
                           "budget": 1, "expected_vertices": 2},
}
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
    return {name: {**fixture, "input_sha256": sha(encoded(fixture))}
            for name, fixture in CASES.items()}


def radius_valid(text: str, bound: int) -> bool:
    try:
        radius = float(text)
    except ValueError:
        return False
    if not math.isfinite(radius) or radius < 0 or repr(radius) != repr(float(text)):
        return False
    if bound == 0:
        return radius == 0
    exact = Fraction.from_float(radius)
    required = 2 * bound * bound
    if exact * exact < required:
        return False
    previous = math.nextafter(radius, 0.0)
    return Fraction.from_float(previous) ** 2 < required


def rows(path: Path, purpose: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"),
                                        newline=""), strict=True)
    require(reader.fieldnames == FIELDS, "APP-04 raw header differs")
    result = list(reader)
    names = list(CASES)
    expected = ([('smoke', name, 0, 1) for name in names] if purpose == "smoke" else
                [('warmup', name, 0, 100) for name in names] +
                [('trial', names[(offset + rep) % 3], rep, 100)
                 for rep in range(7) for offset in range(3)])
    require(len(result) == len(expected), "APP-04 raw row count differs")
    for row, (phase, name, rep, calls) in zip(result, expected):
        fixture = CASES[name]
        require(None not in row and
                (row["phase"], row["case"], row["repetition"], row["calls"],
                 row["status"], row["verified"], row["basis"], row["vertices"]) ==
                (phase, name, str(rep), str(calls), "enclosed", "true",
                 "v_ellipsoid", str(fixture["expected_vertices"])),
                "Unverified APP-04 observation or changed fixture")
        require(re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"]) is not None,
                "Missing positive APP-04 public-call duration")
        require(all(radius_valid(row[field], bound) for field, bound in zip(
            ("radius_x", "radius_y"), fixture["projected_bounds"])),
            "APP-04 radius does not meet its exact literal oracle")
    return result


def summary(measured: list[dict]) -> list[dict]:
    result = []
    for name in CASES:
        samples = [int(row["elapsed_ns"]) for row in measured
                   if row["phase"] == "trial" and row["case"] == name]
        require(len(samples) == 7, "Seven measured batches are required")
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
    git = lambda *args: subprocess.check_output(["git", *args], cwd=source, text=True).strip()
    commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    require(commit == pre.get("commit") == post.get("commit") == host.get("source_commit") and
            tree == pre.get("tree") == post.get("tree") == host.get("source_tree") and
            not status and pre.get("status") == post.get("status") ==
            host.get("source_status") == [] and
            pre.get("schema") == post.get("schema") == "csl.app04-source-receipt/1" and
            pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("tracked_count") == post.get("tracked_count") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "Capture does not match a clean frozen source checkout")
    driver = source / "benchmarks/reporting/app04/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/app04/driver.cpp"], cwd=source),
        "APP-04 driver differs from frozen source")
    executable = capture / "measure-build/Release/csl_app04_ellipsoid_report.exe"
    require(executable.is_file() and sha(executable.read_bytes()) ==
            post.get("executable_sha256"), "Frozen APP-04 executable differs")
    cache = capture / "measure-build/CMakeCache.txt"
    compiler_files = list((capture / "measure-build/CMakeFiles").glob(
        "*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "One C++ compiler receipt required")
    compiler = compiler_files[0]
    cache_text = cache.read_text(encoding="utf-8")
    require(all(option + ":BOOL=" + value in cache_text for option, value in
                (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                 ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP04_REPORT", "ON"))) and
            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache_text,
            "Captured APP-04 Release configuration differs")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "APP-04 driver wrote stderr")
    smoke = rows(capture / "smoke.csv", "smoke")
    measured = rows(capture / "measure.csv", "measure")
    build = {"configuration": "Release", "architecture": "x64",
             "compiler_receipt": compiler.read_text(encoding="utf-8"),
             "cmake_options": {"BUILD_TESTING": "OFF", "CSL_ENABLE_HIGHS": "OFF",
                               "CSL_ENABLE_QHULL": "OFF", "CSL_BUILD_APP04_REPORT": "ON"},
             "executable_sha256": sha(executable.read_bytes()),
             "driver_source_sha256": sha(driver.read_bytes()),
             "configure_log_sha256": sha((capture / "configure.log").read_bytes()),
             "build_log_sha256": sha((capture / "build.log").read_bytes()),
             "cmake_cache_sha256": sha(cache.read_bytes()),
             "cmake_compiler_sha256": sha(compiler.read_bytes())}
    record = {"schema": SCHEMA, "source_commit": commit, "source_tree": tree,
              "module": "CSL::approximation directional ellipsoid adapter",
              "backend": "native binary64 construction and exact stored-value policy admission",
              "fixtures": fixtures(), "environment": host, "build": build,
              "source_receipts": {"prebuild": pre, "postrun": post},
              "scope": "Two planar square orientations and one degenerate planar segment",
              "limits": ["The claim concerns exact sets defined by stored binary64 coefficients.",
                         "No finite approximation error bound or validated prior rounding is supplied.",
                         "No MATLAB, ET, optimizer, competitor, speedup, source-mapped limiter or scalability claim is supported."],
              "measurement": {"clock": "std::chrono::steady_clock",
                  "interval": "Each public run_registered call, including registry selection, fresh workspace, construction and independent vertex admission; per-call intervals summed within a 100-call batch",
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
    report_id = "app04-ellipsoid-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = destination / report_id
    require(not output.exists(), "Immutable APP-04 report ID already exists")
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

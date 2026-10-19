"""Admit one clean frozen APP-02 Release capture; never execute the driver."""
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

SOURCE = "8fecba49e34c37e5e01c40218a8f014a179818fd"
TREE = "7754b4c088566225b007c58531a74aae0024d5a1"
SCHEMA = "csl.app02-box-parallelotope/1"
FIELDS = ["phase", "case", "repetition", "calls", "status", "verified",
          "elapsed_ns", "basis", "output_primitives"]
CASES = {
    "interval-box": {"direction": "outer", "input_representation": "V",
                     "input_vertices": [[-1.5], [2.25]], "orientation_rows": [[1]],
                     "expected_h_rows": [[1], [-1]], "expected_h_bounds": [2.25, 1.5],
                     "expected_basis": "v_h", "budget": 2},
    "diamond-axis-outer": {"direction": "outer", "input_representation": "V",
                           "input_vertices": [[0, 2], [2, 0], [0, -2], [-2, 0]],
                           "orientation_rows": [[1, 0], [0, 1]],
                           "expected_h_rows": [[1, 0], [-1, 0], [0, 1], [0, -1]],
                           "expected_h_bounds": [2, 2, 2, 2],
                           "expected_basis": "v_h", "budget": 4},
    "diamond-rotated-outer": {"direction": "outer", "input_representation": "V",
                              "input_vertices": [[0, 2], [2, 0], [0, -2], [-2, 0]],
                              "orientation_rows": [[1, 1], [1, -1]],
                              "expected_h_rows": [[1, 1], [-1, -1], [1, -1], [-1, 1]],
                              "expected_h_bounds": [2, 2, 2, 2],
                              "expected_basis": "v_h", "budget": 4},
    "diamond-axis-inner": {"direction": "inner", "input_representation": "H",
                           "input_h_rows": [[1, 1], [1, -1], [-1, 1], [-1, -1]],
                           "input_h_bounds": [2, 2, 2, 2],
                           "ordered_corners": [[1, 1], [1, -1], [-1, -1], [-1, 1]],
                           "expected_v_vertices": [[1, 1], [1, -1], [-1, -1], [-1, 1]],
                           "expected_basis": "h_v", "budget": 4},
    "square-rotated-inner": {"direction": "inner", "input_representation": "H",
                             "input_h_rows": [[1, 0], [-1, 0], [0, 1], [0, -1]],
                             "input_h_bounds": [2, 2, 2, 2],
                             "ordered_corners": [[0, 1], [1, 0], [0, -1], [-1, 0]],
                             "expected_v_vertices": [[0, 1], [1, 0], [0, -1], [-1, 0]],
                             "expected_basis": "h_v", "budget": 4},
}
SOURCE_FILES = ("driver.cpp", "smoke.csv", "measure.csv", "smoke.stderr.txt",
                "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json",
                "configure.log", "build.log", "CMakeCache.raw.txt",
                "CMakeCXXCompiler.raw.cmake", "build-provenance.json", "records.json")


def fixtures() -> dict:
    return {name: {**case, "input_sha256": sha(encoded({key: value for key, value in case.items()
                            if not key.startswith("expected_")}))} for name, case in CASES.items()}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), "Expected JSON object: " + path.name)
    return value


def rows(path: Path, purpose: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline=""), strict=True)
    require(reader.fieldnames == FIELDS, "Raw driver header differs")
    result = list(reader)
    names = list(CASES)
    expected = ([("smoke", name, 0, 1) for name in names] if purpose == "smoke" else
                [("warmup", name, 0, 100) for name in names] +
                [("trial", names[(offset + rep) % 5], rep, 100)
                 for rep in range(7) for offset in range(5)])
    require(len(result) == len(expected), "Raw driver row count differs")
    for row, (phase, name, rep, calls) in zip(result, expected):
        fixture = CASES[name]
        primitives = fixture["budget"]
        require(None not in row and
                (row["phase"], row["case"], row["repetition"], row["calls"],
                 row["status"], row["verified"], row["basis"], row["output_primitives"]) ==
                (phase, name, str(rep), str(calls), "enclosed", "true",
                 fixture["expected_basis"], str(primitives)),
                "Unverified or unexpected driver observation")
        require(re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"]) is not None,
                "Missing positive public-call duration")
    return result


def summary(rows_: list[dict]) -> list[dict]:
    result = []
    for name in CASES:
        samples = [int(row["elapsed_ns"]) for row in rows_
                   if row["phase"] == "trial" and row["case"] == name]
        require(len(samples) == 7, "Seven measured batches required")
        result.append({"case": name, "batches": 7, "calls_per_batch": 100,
                       "successes": 700, "failures": 0,
                       "median_batch_ns": statistics.median(samples),
                       "min_batch_ns": min(samples), "max_batch_ns": max(samples)})
    return result


def collect(capture: Path, source: Path, destination: Path) -> Path:
    require(destination.is_dir(), "Report collection root missing")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=source, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                                     cwd=source, text=True)
    require((commit, tree, status) == (SOURCE, TREE, ""),
            "Collector requires the clean frozen source checkout")
    pre, post, host = (read_json(capture / name) for name in
                       ("prebuild.json", "postrun.json", "host.json"))
    require(pre.get("schema") == post.get("schema") == "csl.app02-source-receipt/1" and
            pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("commit") == post.get("commit") == host.get("source_commit") == SOURCE and
            pre.get("tree") == post.get("tree") == host.get("source_tree") == TREE and
            pre.get("status") == post.get("status") == host.get("source_status") == [] and
            pre.get("tracked_count") == post.get("tracked_count") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "Capture source identity or receipts differ")
    driver = source / "benchmarks/reporting/app02/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", SOURCE + ":benchmarks/reporting/app02/driver.cpp"], cwd=source),
        "Driver differs from frozen source")
    executable = capture / "measure-build/Release/csl_app02_approximation_report.exe"
    require(executable.is_file() and sha(executable.read_bytes()) == post.get("executable_sha256"),
            "Frozen executable identity differs")
    cache = capture / "measure-build/CMakeCache.txt"
    compiler_files = list((capture / "measure-build/CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "One C++ compiler receipt required")
    compiler = compiler_files[0]
    cache_text = cache.read_text(encoding="utf-8")
    require(all(option + ":BOOL=" + value in cache_text for option, value in
                (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                 ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP02_REPORT", "ON"))) and
            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache_text and
            'CMAKE_CXX_COMPILER_VERSION "19.44.' in compiler.read_text(encoding="utf-8"),
            "Captured Release build configuration differs")
    build_log = (capture / "build.log").read_text(encoding="utf-8-sig")
    require("MSBuild version" in build_log and
            not any("\u0400" <= letter <= "\u04ff" for letter in build_log),
            "English raw build log differs")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "Driver produced stderr")
    smoke = rows(capture / "smoke.csv", "smoke")
    measured = rows(capture / "measure.csv", "measure")
    require(len(smoke) == 5 and len(measured) == 40, "Driver omitted a case")
    build = {"configuration": "Release", "compiler": "MSVC 19.44 / Visual Studio 2022",
             "architecture": "x64", "cmake_options": {"BUILD_TESTING": "OFF",
                 "CSL_ENABLE_HIGHS": "OFF", "CSL_ENABLE_QHULL": "OFF",
                 "CSL_BUILD_APP02_REPORT": "ON"},
             "executable_sha256": sha(executable.read_bytes()),
             "driver_source_sha256": sha(driver.read_bytes()),
             "configure_log_sha256": sha((capture / "configure.log").read_bytes()),
             "build_log_sha256": sha((capture / "build.log").read_bytes()),
             "cmake_cache_sha256": sha(cache.read_bytes()),
             "cmake_compiler_sha256": sha(compiler.read_bytes())}
    record = {"schema": SCHEMA, "source_commit": SOURCE, "source_tree": TREE,
              "module": "CSL::approximation registered box and parallelotope adapters",
              "backend": "native exact stored-binary64 containment check; no external solver",
              "fixtures": fixtures(), "environment": host, "build": build,
              "source_receipts": {"prebuild": pre, "postrun": post},
              "scope": "Five authored interval and 2D polygon fixtures",
              "limits": ["Exact containment applies to stored binary64 vertices, rays and H rows.",
                         "No finite Hausdorff or support-function error bound is claimed.",
                         "No optimizer result, validated real-arithmetic enclosure, comparator, speedup, limiter profile or scalability claim is supported."],
              "measurement": {"clock": "std::chrono::steady_clock",
                 "interval": "Each run_registered public call, including registry selection, provider execution and independent enclosure check; per-call intervals summed into each 100-call batch",
                 "excludes": ["fixture and registry construction", "post-call literal oracle check",
                              "CSV serialization", "process launch", "HTML rendering"],
                 "warmup": "one excluded 100-call batch per case",
                 "measured_order": "seven rotated five-case rounds, 100 calls per case per round",
                 "workers_requested": 1, "workers_actual": 1,
                 "native_threads_requested": 1, "native_threads_actual": 1,
                 "workspace_reuse": "fresh provider workspace per public call; authored input and registry reused",
                 "internal_counters": "unavailable", "failures": 0,
                 "raw_smoke_sha256": sha((capture / "smoke.csv").read_bytes()),
                 "raw_measure_sha256": sha((capture / "measure.csv").read_bytes()),
                 "trials": measured, "summary": summary(measured)}}
    report_id = "app02-box-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = destination / report_id
    require(not output.exists(), "Immutable report ID already exists")
    output.mkdir()
    for name in ("smoke.csv", "measure.csv", "smoke.stderr.txt", "measure.stderr.txt",
                 "host.json", "prebuild.json", "postrun.json", "configure.log", "build.log"):
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

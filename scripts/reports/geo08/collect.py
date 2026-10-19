"""Validate frozen GEO-08 observations and save versioned raw records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import subprocess

SCHEMA = "csl.geo08-lazy-geometry/1"
FIELDS = ["phase", "repetition", "calls", "attempted", "completed",
          "status", "verified", "elapsed_ns",
          "support", "vertices", "rays"]
FIXTURE = {"source_id": "geo08-square", "dimension": 2,
           "vertices": [[0, 0], [1, 0], [0, 1], [1, 1]], "rays": [],
           "affine_map": [[2, 0], [0, 1]], "affine_offset": [1, -1],
           "sum": "independent Minkowski sum of the affine image and source square",
           "support_direction": [1, 1], "expected_support": 5,
           "expected_maximizer": [4, 1], "materialization_budget":
           {"max_vertices": 16, "max_rays": 0},
           "expected_v_rows": {"vertices": 16, "rays": 0}}
SAVED = ("driver.cpp", "smoke.csv", "measure.csv", "smoke.stderr.txt",
         "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json",
         "configure.public.log", "build.public.log", "CMakeCache.public.txt",
         "CMakeCXXCompiler.public.cmake", "build-provenance.json", "records.json")


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


def rows(path: Path, phase: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"),
                                        newline=""), strict=True)
    require(reader.fieldnames == FIELDS, "Raw GEO-08 CSV header differs")
    result = list(reader)
    expected = ([("smoke", 0, 1)] if phase == "smoke" else
                [("warmup", 0, 100)] + [("trial", rep, 100) for rep in range(7)])
    require(len(result) == len(expected), "Raw GEO-08 row count differs")
    for row, (kind, repetition, calls) in zip(result, expected):
        require(None not in row and
                (row["phase"], row["repetition"], row["calls"], row["attempted"],
                 row["completed"], row["status"],
                 row["verified"], row["support"], row["vertices"], row["rays"]) ==
                (kind, str(repetition), str(calls), str(calls), str(calls),
                 "completed", "true", "5", "16", "0"),
                "Unverified GEO-08 observation or changed fixture")
        require(re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"]) is not None,
                "Missing positive GEO-08 public-call duration")
    return result


def public_receipt(path: Path, source: Path, build_dir: Path) -> bytes:
    """Keep compiler/configuration evidence while replacing local checkout paths."""
    value = path.read_text(encoding="utf-8")
    for directory, label in ((build_dir, "<BUILD_DIR>"), (source, "<SOURCE_DIR>")):
        pattern = r"[\\/]".join(re.escape(part) for part in
                                  directory.as_posix().replace("\\", "/").split("/"))
        value = re.sub(pattern, label, value, flags=re.IGNORECASE)
        require(re.search(pattern, value, flags=re.IGNORECASE) is None,
                "Local path remains in public GEO-08 receipt")
    return value.encode("utf-8")


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
            pre.get("schema") == post.get("schema") == "csl.geo08-source-receipt/1" and
            pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("tracked_count") == post.get("tracked_count") and
            pre.get("observed_utc") < post.get("observed_utc") <= host.get("collected_utc"),
            "Capture does not match a clean frozen source checkout")
    driver = source / "benchmarks/reporting/geo08/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/geo08/driver.cpp"], cwd=source),
        "GEO-08 driver differs from frozen source")
    executable = capture / "measure-build/Release/csl_geo08_lazy_report.exe"
    require(executable.is_file() and sha(executable.read_bytes()) ==
            post.get("executable_sha256"), "Frozen GEO-08 executable differs")
    cache = capture / "measure-build/CMakeCache.txt"
    compiler_files = list((capture / "measure-build/CMakeFiles").glob(
        "*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "One C++ compiler receipt required")
    compiler = compiler_files[0]
    cache_text = cache.read_text(encoding="utf-8")
    require(all(option + ":BOOL=" + value in cache_text for option, value in
                (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                 ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_GEO08_REPORT", "ON"))) and
            "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache_text,
            "Captured GEO-08 Release configuration differs")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "GEO-08 driver produced stderr")
    smoke = rows(capture / "smoke.csv", "smoke")
    measured = rows(capture / "measure.csv", "measure")
    trials = [int(row["elapsed_ns"]) for row in measured if row["phase"] == "trial"]
    require(len(smoke) == 1 and len(trials) == 7, "Seven checked GEO-08 trials required")
    public = {"configure.public.log": public_receipt(capture / "configure.log", source,
                                                       capture / "measure-build"),
              "build.public.log": public_receipt(capture / "build.log", source,
                                                   capture / "measure-build"),
              "CMakeCache.public.txt": public_receipt(cache, source,
                                                       capture / "measure-build"),
              "CMakeCXXCompiler.public.cmake": public_receipt(compiler, source,
                                                               capture / "measure-build")}
    build = {"configuration": "Release", "architecture": "x64",
             "provenance_sanitization": "Public receipts replace absolute source and build directories with <SOURCE_DIR> and <BUILD_DIR>; unredacted capture remains local",
             "compiler_receipt": public["CMakeCXXCompiler.public.cmake"].decode("utf-8"),
             "cmake_options": {"BUILD_TESTING": "OFF", "CSL_ENABLE_HIGHS": "OFF",
                 "CSL_ENABLE_QHULL": "OFF", "CSL_BUILD_GEO08_REPORT": "ON"},
             "executable_sha256": sha(executable.read_bytes()),
             "driver_source_sha256": sha(driver.read_bytes()),
             "configure_log_sha256": sha(public["configure.public.log"]),
             "build_log_sha256": sha(public["build.public.log"]),
             "cmake_cache_sha256": sha(public["CMakeCache.public.txt"]),
             "cmake_compiler_sha256": sha(public["CMakeCXXCompiler.public.cmake"])}
    record = {"schema": SCHEMA, "source_commit": commit, "source_tree": tree,
              "module": "CSL::lazy_geometry 1.0.0",
              "backend": "native stored-binary64 expression, support and V enumeration",
              "fixture": {**FIXTURE, "input_sha256": sha(encoded(FIXTURE))},
              "environment": host, "build": build,
              "source_receipts": {"prebuild": pre, "postrun": post},
              "scope": "One planar affine-image plus independent-sum public route",
              "limits": ["The fixture and returned V rows are stored binary64 values.",
                         "Equivalent relation is mathematical; rounding and coverage are unestablished.",
                         "Direction samples do not constitute a complete set or inclusion certificate.",
                         "No comparator, speedup, source-mapped limiter or scalability claim is supported."],
              "measurement": {"clock": "std::chrono::steady_clock",
                  "interval": "Each checked public expression, support and materialization call, including fresh workspaces and literal result checks; per-call intervals summed within a 100-call batch",
                  "excludes": ["fixture and provider registration", "CSV serialization",
                               "process launch", "HTML rendering"],
                  "warmup": "one excluded 100-call batch",
                  "measured_order": "seven sequential 100-call batches",
                  "workers_requested": 1, "workers_actual": 1,
                  "native_threads_requested": "not applicable: no native solver backend",
                  "native_threads_actual": "not applicable: no native solver backend",
                  "random_seed": "not applicable: deterministic fixture and driver",
                  "result_comparison": "literal exact equality for finite binary64 support, evidence, growth and all 16 returned V rows; no numerical tolerance",
                  "workspace_reuse": "fresh expression/support/conversion workspace per call; source and selected providers reused",
                  "internal_counters": "unavailable", "failures": 0,
                  "raw_smoke_sha256": sha((capture / "smoke.csv").read_bytes()),
                  "raw_measure_sha256": sha((capture / "measure.csv").read_bytes()),
                  "trials": measured,
                  "summary": {"batches": 7, "calls_per_batch": 100,
                              "successes": 700, "failures": 0,
                              "median_batch_ns": statistics.median(trials),
                              "min_batch_ns": min(trials), "max_batch_ns": max(trials)}}}
    report_id = "geo08-lazy-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = destination / report_id
    require(not output.exists(), "Immutable GEO-08 report ID already exists")
    output.mkdir()
    for name in ("smoke.csv", "measure.csv", "smoke.stderr.txt",
                 "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json"):
        (output / name).write_bytes((capture / name).read_bytes())
    for name, content in public.items():
        (output / name).write_bytes(content)
    (output / "driver.cpp").write_bytes(driver.read_bytes())
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

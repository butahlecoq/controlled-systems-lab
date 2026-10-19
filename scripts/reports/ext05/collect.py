"""Validate frozen EXT-05 raw observations and save an immutable record."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import statistics
import subprocess


SOURCE_FILES = ("driver.cpp", "smoke.csv", "measure.csv", "smoke.stderr.txt",
                "measure.stderr.txt", "host.json", "prebuild.json", "postrun.json",
                "configure.log", "build.log", "CMakeCache.raw.txt",
                "CMakeCXXCompiler.raw.cmake")
FIELDS = ("phase", "case", "repetition", "calls", "status", "verified",
          "elapsed_ns", "a01", "b0", "b1", "x1_position", "x1_velocity",
          "x2_position", "x2_velocity", "accepted", "rejected", "local_estimate")
EXPECTED = {"a01": 2, "b0": 2, "b1": 2, "x1_position": 1,
            "x1_velocity": 2, "x2_position": 3, "x2_velocity": 0}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "Expected JSON object: " + path.name)
    return value


def rows(path: Path, purpose: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")), strict=True)
    require(tuple(reader.fieldnames or ()) == FIELDS, "EXT-05 raw header differs")
    result = list(reader)
    expected = ([('smoke', 0, 1)] if purpose == "smoke" else
                [('warmup', 0, 100)] + [('trial', i, 100) for i in range(7)])
    require(len(result) == len(expected), "EXT-05 raw row count differs")
    for row, (phase, repetition, calls) in zip(result, expected):
        require(None not in row and
                (row["phase"], row["case"], row["repetition"], row["calls"],
                 row["status"], row["verified"]) ==
                (phase, "double-integrator", str(repetition), str(calls),
                 "success", "true"), "EXT-05 row status or order differs")
        require(int(row["elapsed_ns"]) > 0 and int(row["accepted"]) >= 2 and
                int(row["rejected"]) >= 0, "EXT-05 duration or step count invalid")
        for key, value in EXPECTED.items():
            require(abs(float(row[key]) - value) <= 1e-11,
                    "EXT-05 analytic literal differs: " + key)
        require(float(row["local_estimate"]) >= 0,
                "EXT-05 local estimate invalid")
    return result


def collect(capture: Path, source: Path, output_root: Path) -> Path:
    capture = capture.resolve(strict=True)
    source = source.resolve(strict=True)
    pre, post, host = (read_json(capture / name) for name in
                       ("prebuild.json", "postrun.json", "host.json"))
    commit = pre["commit"]
    require(pre["phase"] == "prebuild" and post["phase"] == "postrun" and
            pre["status"] == post["status"] == [] and
            pre["commit"] == post["commit"] == host["source_commit"] and
            pre["tree"] == post["tree"] == host["source_tree"] and
            pre["observed_utc"] < post["observed_utc"] <= host["collected_utc"],
            "EXT-05 frozen source receipts differ")
    driver = source / "benchmarks/reporting/ext05/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/ext05/driver.cpp"], cwd=source),
        "EXT-05 driver differs from frozen source")
    executable = capture / "build/Release/csl_ext05_discretization_report.exe"
    require(sha(executable.read_bytes()) == post["executable_sha256"],
            "EXT-05 captured executable differs")
    cache = (capture / "CMakeCache.raw.txt").read_text(encoding="utf-8")
    require(all(key + ":BOOL=" + value in cache for key, value in (
        ("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
        ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_EXT05_REPORT", "ON"))) and
        "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache,
        "EXT-05 Release build settings differ")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "EXT-05 driver wrote stderr")
    rows(capture / "smoke.csv", "smoke")
    measure = rows(capture / "measure.csv", "measure")
    durations = [int(row["elapsed_ns"]) for row in measure[1:]]
    source_hashes = {name: sha((driver if name == "driver.cpp" else
                                capture / name).read_bytes()) for name in SOURCE_FILES}
    record = {
        "schema": "csl.ext05-discretization-report/1",
        "source_commit": commit, "source_tree": pre["tree"],
        "source_receipts": {"prebuild": pre, "postrun": post},
        "environment": host, "source_sha256": source_hashes,
        "model": {"time_domain": "continuous", "coefficient_variation": "constant_lti",
                  "hold": "zero_order_hold", "times": [0, 1, 3],
                  "A": [[0, 1], [0, 0]], "B": [[0], [1]],
                  "E_shape": [2, 0], "offset": [0, 0],
                  "controls": [2, -1], "initial_state": [0, 0]},
        "analytic": {"transition_A01": [1, 2], "transition_B0": [0.5, 2],
                     "transition_B1": [1, 2], "trajectory": [[0, 0], [1, 2], [3, 0]]},
        "measurement": {"raw_smoke_sha256": source_hashes["smoke.csv"],
                        "raw_measure_sha256": source_hashes["measure.csv"],
                        "trials": measure[1:], "warmup": measure[0],
                        "median_batch_ns": statistics.median(durations),
                        "min_batch_ns": min(durations),
                        "max_batch_ns": max(durations),
                        "measured_calls": 700, "failures": 0},
        "evidence_scope": {
            "assurance": "ordinary binary64 numerical evaluation",
            "local_error": "RK4 step-doubling difference divided by 15 is an observed local estimate, not a certified global bound",
            "performance": "Single-adapter descriptive durations on one host and one fixed case; no comparator, speedup or limiter attribution",
            "internal_counters": "unavailable"},
    }
    report_id = "ext05-discretization-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = output_root / report_id
    require(not output.exists(), "Immutable EXT-05 report ID already exists")
    output.mkdir(parents=True)
    for name in SOURCE_FILES:
        shutil.copyfile(driver if name == "driver.cpp" else capture / name,
                        output / name)
    (output / "records.json").write_bytes(encoded(record))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.capture, args.source, args.out))

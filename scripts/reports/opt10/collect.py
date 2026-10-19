"""Validate frozen OPT-10 raw observations and save an immutable record."""
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
          "elapsed_ns", "x", "y", "objective", "projected_residual",
          "iterations", "objective_evaluations")
EXPECTED = {"x": 1, "y": -1, "objective": 1, "projected_residual": 0}


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
    require(tuple(reader.fieldnames or ()) == FIELDS, "OPT-10 raw header differs")
    result = list(reader)
    expected = ([('smoke', 0, 1)] if purpose == "smoke" else
                [('warmup', 0, 100)] + [('trial', i, 100) for i in range(7)])
    require(len(result) == len(expected), "OPT-10 raw row count differs")
    for row, (phase, repetition, calls) in zip(result, expected):
        require(None not in row and
                (row["phase"], row["case"], row["repetition"], row["calls"],
                 row["status"], row["verified"]) ==
                (phase, "box-quadratic", str(repetition), str(calls),
                 "success", "true"), "OPT-10 row status or order differs")
        require(int(row["elapsed_ns"]) > 0 and int(row["iterations"]) == 1 and
                int(row["objective_evaluations"]) >= 2,
                "OPT-10 duration or iteration count invalid")
        for key, value in EXPECTED.items():
            require(abs(float(row[key]) - value) <= 1e-11,
                    "OPT-10 analytic literal differs: " + key)
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
            "OPT-10 frozen source receipts differ")
    driver = source / "benchmarks/reporting/opt10/driver.cpp"
    require(driver.read_bytes() == subprocess.check_output(
        ["git", "show", commit + ":benchmarks/reporting/opt10/driver.cpp"], cwd=source),
        "OPT-10 driver differs from frozen source")
    executable = capture / "build/Release/csl_opt10_smooth_report.exe"
    require(sha(executable.read_bytes()) == post["executable_sha256"],
            "OPT-10 captured executable differs")
    cache = (capture / "CMakeCache.raw.txt").read_text(encoding="utf-8")
    require(all(key + ":BOOL=" + value in cache for key, value in (
        ("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "ON"),
        ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_OPT10_REPORT", "ON"))) and
        "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache,
        "OPT-10 Release build settings differ")
    require((capture / "smoke.stderr.txt").read_bytes() == b"" and
            (capture / "measure.stderr.txt").read_bytes() == b"",
            "OPT-10 driver wrote stderr")
    rows(capture / "smoke.csv", "smoke")
    measure = rows(capture / "measure.csv", "measure")
    durations = [int(row["elapsed_ns"]) for row in measure[1:]]
    source_hashes = {name: sha((driver if name == "driver.cpp" else
                                capture / name).read_bytes()) for name in SOURCE_FILES}
    record = {
        "schema": "csl.opt10-smooth-convex-report/1",
        "source_commit": commit, "source_tree": pre["tree"],
        "source_receipts": {"prebuild": pre, "postrun": post},
        "environment": host, "source_sha256": source_hashes,
        "problem": {"variables": [[0, 1], [-1, 1]], "rows": [],
                    "objective": "0.5*((x-2)^2+(y+2)^2)",
                    "gradient": ["x-2", "y+2"], "start": [0, 0],
                    "objective_claim": "caller-declared differentiable convex"},
        "analytic": {"point": [1, -1], "objective": 1,
                     "gradient": [-1, 1], "projected_residual": 0},
        "measurement": {"raw_smoke_sha256": source_hashes["smoke.csv"],
                        "raw_measure_sha256": source_hashes["measure.csv"],
                        "trials": measure[1:], "warmup": measure[0],
                        "median_batch_ns": statistics.median(durations),
                        "min_batch_ns": min(durations),
                        "max_batch_ns": max(durations),
                        "measured_calls": 700, "failures": 0},
        "evidence_scope": {
            "assurance": "ordinary binary64 numerical evaluation",
            "stationarity": "Numerical projected-gradient stationarity conditional on caller-declared convexity; not a validated or global error certificate",
            "performance": "Single-adapter descriptive durations on one host and one fixed case; no comparator, speedup or limiter attribution",
            "internal_counters": "unavailable"},
    }
    report_id = "opt10-smooth-" + sha(encoded(record))[:16]
    record["report_id"] = report_id
    output = output_root / report_id
    require(not output.exists(), "Immutable OPT-10 report ID already exists")
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

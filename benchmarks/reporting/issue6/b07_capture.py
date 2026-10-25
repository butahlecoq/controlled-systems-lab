"""Capture and bind the B07 eight-case Release run to its exact build inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.split(":", 1)[0]] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    build = args.build_dir.resolve()
    output = args.output_dir.resolve()
    executable = build / "csl_issue6_b07_report"
    driver = source / "benchmarks/reporting/issue6/b07_reconstruction.cpp"
    scenario = source / "benchmarks/scenarios/b07-owner-approved-eight-case-v1.json"
    cache_file = build / "CMakeCache.txt"
    if not source.is_dir() or not executable.is_file() or not cache_file.is_file():
        raise SystemExit("source, executable, or CMake cache is missing")
    git = lambda *args: subprocess.run(["git", "-C", str(source), *args], check=True,
        capture_output=True, text=True).stdout.strip()
    commit = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise SystemExit("capture requires a clean source tree")
    driver_hash, scenario_hash, executable_hash = sha256(driver), sha256(scenario), sha256(executable)
    configuration = cache(cache_file)
    if configuration.get("CMAKE_BUILD_TYPE") != "Release" or configuration.get("CSL_BUILD_ISSUE6_B07_REPORT") != "ON":
        raise SystemExit("capture requires the B07 Release target")
    environment = os.environ.copy()
    environment["CSL_ISSUE6_B07_EXECUTABLE_SHA256"] = executable_hash
    run = subprocess.run([str(executable)], check=False, capture_output=True, text=True, env=environment)
    if run.returncode:
        raise SystemExit("B07 executable failed: " + run.stderr.strip())
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    if len(rows) != 8 or len({row.get("case_id") for row in rows}) != 8:
        raise SystemExit("B07 executable did not produce eight unique cases")
    expected = {"source_commit": commit, "driver_sha256": driver_hash,
                "scenario_sha256": scenario_hash, "executable_sha256": executable_hash,
                "build_type": "Release"}
    for row in rows:
        if any(row.get(key) != value for key, value in expected.items()):
            raise SystemExit("run record provenance differs from current source/build")
    output.mkdir(parents=True, exist_ok=True)
    results = output / "results.jsonl"
    results.write_text(run.stdout, encoding="utf-8")
    provenance = {
        "schema": "csl.issue6-b07-capture-provenance/1",
        "source_commit": commit,
        "source_tree_clean": True,
        "driver_sha256": driver_hash,
        "scenario_sha256": scenario_hash,
        "executable_sha256": executable_hash,
        "results_sha256": sha256(results),
        "compiler_id": rows[0]["compiler_id"],
        "compiler_version": rows[0]["compiler_version"],
        "build_type": configuration["CMAKE_BUILD_TYPE"],
        "cmake_generator": configuration.get("CMAKE_GENERATOR", ""),
        "cmake_cache_sha256": sha256(cache_file),
        "cxx_compiler_path": configuration.get("CMAKE_CXX_COMPILER", ""),
        "cxx_flags": configuration.get("CMAKE_CXX_FLAGS", ""),
        "release_flags": configuration.get("CMAKE_CXX_FLAGS_RELEASE", ""),
        "highs_enabled": configuration.get("CSL_ENABLE_HIGHS", ""),
        "qhull_enabled": configuration.get("CSL_ENABLE_QHULL", ""),
        "capture_command": "b07_capture.py --source-root <repo> --build-dir <release-build> --output-dir <bundle>"
    }
    (output / "run-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "source_commit": commit,
        "executable_sha256": executable_hash, "results_sha256": provenance["results_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

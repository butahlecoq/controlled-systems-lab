#!/usr/bin/env python3
"""Capture and independently check a source-bound final #944 pipeline run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools/strategy_a_each_choice_pipeline.cpp"
CHECKER = ROOT / "scripts/catalogue/check_944_each_choice_pipeline.py"
ALGORITHM_SOURCE = ROOT / "src/geometry/conversion/affine_coordinates.cpp"
MANIFEST_SOURCES = (
    ROOT / "CMakeLists.txt",
    ROOT / "src/geometry/conversion/affine_coordinates.cpp",
    ROOT / "src/adapters/polyhedral/qhull.cpp",
    ROOT / "src/adapters/polyhedral/Tests.cmake",
    ROOT / "tests/contract/geometry/qhull_highs_interop_tests.cpp",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_values(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"([^:#]+):[^=]+=([^=]*)$", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("build_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    build = args.build_directory.resolve(strict=True)
    output = args.output_directory.resolve()
    cache = build / "CMakeCache.txt"
    if not cache.is_file():
        parser.error("build directory has no CMakeCache.txt")
    if output.exists():
        parser.error("output directory must be fresh")
    if executable.name != "csl_strategy_a_each_choice_pipeline" or not executable.is_relative_to(
        build
    ):
        parser.error(
            "executable must be the named pipeline target inside the selected build directory"
        )
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
    if dirty:
        parser.error("source worktree must be clean before capture")
    config = cache_values(cache)
    expected = {
        "CMAKE_HOME_DIRECTORY": str(ROOT),
        "CMAKE_BUILD_TYPE": "Release",
        "CSL_ENABLE_HIGHS": "ON",
        "CSL_ENABLE_QHULL": "ON",
    }
    for key, value in expected.items():
        if config.get(key) != value:
            parser.error(f"build cache {key} must be {value!r}, found {config.get(key)!r}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".issue944-capture-", dir=output.parent) as temporary:
        stage = Path(temporary)
        matrix = subprocess.run([str(executable)], capture_output=True)
        regression = subprocess.run(
            [str(executable), "--terminal-membership-indexing-regression"], capture_output=True
        )
        (stage / "records.json").write_bytes(matrix.stdout)
        (stage / "records.stderr.txt").write_bytes(matrix.stderr)
        (stage / "terminal-membership-regression.json").write_bytes(regression.stdout)
        (stage / "terminal-membership-regression.stderr.txt").write_bytes(regression.stderr)
        checker = None
        if matrix.returncode == 0 and regression.returncode == 0:
            checker = subprocess.run(
                [
                    sys.executable,
                    str(CHECKER),
                    "--record-json",
                    str(stage / "records.json"),
                    "--regression-json",
                    str(stage / "terminal-membership-regression.json"),
                    "--expected-numeric-boundaries",
                    "0",
                ],
                capture_output=True,
                text=True,
            )
        (stage / "checker.stdout.txt").write_text(
            checker.stdout if checker else "", encoding="utf-8"
        )
        (stage / "checker.stderr.txt").write_text(
            checker.stderr if checker else "", encoding="utf-8"
        )
        source_commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        compiler = config.get("CMAKE_CXX_COMPILER", "")
        cmake = config.get("CMAKE_COMMAND", "")
        compiler_result = subprocess.run(
            [compiler, "--version"], check=True, capture_output=True, text=True
        )
        cmake_result = subprocess.run(
            [cmake, "--version"], check=True, capture_output=True, text=True
        )
        provenance = {
            "schema": "csl.issue944-final-capture-provenance/1",
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": source_commit,
            "source_tree": {str(path.relative_to(ROOT)): digest(path) for path in MANIFEST_SOURCES},
            "runner_source_sha256": digest(RUNNER),
            "checker_source_sha256": digest(CHECKER),
            "capture_harness_sha256": digest(Path(__file__).resolve()),
            "algorithm_source_sha256": digest(ALGORITHM_SOURCE),
            "executable_sha256": digest(executable),
            "build": {
                "type": config.get("CMAKE_BUILD_TYPE"),
                "generator": config.get("CMAKE_GENERATOR"),
                "compiler_path": compiler,
                "compiler_version": compiler_result.stdout.splitlines()[0],
                "cmake_path": cmake,
                "cmake_version": cmake_result.stdout.splitlines()[0],
                "highs_enabled": config.get("CSL_ENABLE_HIGHS"),
                "qhull_enabled": config.get("CSL_ENABLE_QHULL"),
                "qhull_provider": "Qhull 8.0.2 Qx",
            },
            "record_sha256": digest(stage / "records.json"),
            "regression_sha256": digest(stage / "terminal-membership-regression.json"),
            "runner_exit_codes": {
                "matrix": matrix.returncode,
                "terminal_membership_regression": regression.returncode,
            },
            "checker_result": {
                "status": "passed" if checker and checker.returncode == 0 else "failed_or_not_run",
                "return_code": checker.returncode if checker else None,
                "required_reconciliation": "64 structural exclusions + 64 completed admitted attempts",
            },
            "cmake_cache_sha256": digest(cache),
        }
        (stage / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        names = sorted(path.name for path in stage.iterdir())
        checksum_lines = [f"{digest(stage / name)}  {name}\n" for name in names]
        (stage / "SHA256SUMS").write_text("".join(checksum_lines), encoding="ascii")
        output.mkdir()
        for path in stage.iterdir():
            (output / path.name).write_bytes(path.read_bytes())
    return 0 if checker and checker.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

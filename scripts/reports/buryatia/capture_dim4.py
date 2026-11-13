#!/usr/bin/env python3
"""Capture a Buryatia 4D native run in a fresh, replayable attempt directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


IMPLEMENTATION_SOURCES = (
    "benchmarks/reporting/buryatia/dim4_driver.cpp",
    "benchmarks/scenarios/buryatia-dim4-matlab-literal-affine-v1.json",
    "cmake/OptionalReports.cmake",
    "include/csl/geometry/ellipsoidal.hpp",
    "src/adapters/lp/highs.cpp",
    "src/adapters/polyhedral/qhull.cpp",
    "src/geometry/affine_sum.cpp",
    "src/geometry/approximation/box_parallelotope.cpp",
    "src/geometry/approximation/ellipsoidal.cpp",
    "src/geometry/approximation/ellipsoidal_family.cpp",
    "src/geometry/approximation/ellipsoidal_set.cpp",
    "src/geometry/approximation/policy.cpp",
    "src/geometry/approximation/zonotope.cpp",
    "src/geometry/generators/adapter.cpp",
    "src/geometry/generators/generator_sets.cpp",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(source: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(source), *args], check=False,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def build_receipt(cache: Path) -> dict:
    values: dict[str, str] = {}
    for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("//") or not line or "=" not in line:
            continue
        left, value = line.split("=", 1)
        key = left.split(":", 1)[0]
        if key in {
            "CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_CXX_COMPILER",
            "CMAKE_CXX_FLAGS", "CMAKE_CXX_FLAGS_RELEASE", "CSL_BUILD_BURYATIA_REPORT",
            "CSL_ENABLE_HIGHS", "CSL_ENABLE_QHULL", "BUILD_TESTING",
        }:
            values[key] = Path(value).name if key == "CMAKE_CXX_COMPILER" else value
    compiler_files = sorted(cache.parent.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if compiler_files:
        text = compiler_files[0].read_text(encoding="utf-8", errors="replace")
        for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION", "CMAKE_CXX_COMPILER_FRONTEND_VARIANT"):
            match = re.search(rf'^set\({key} "([^"]*)"\)$', text, re.MULTILINE)
            if match:
                values[key] = match.group(1)
    return values


def capture(command: list[str], source: Path, build_cache: Path,
            destination: Path, mode: str) -> dict:
    source = source.resolve(strict=True)
    build_cache = build_cache.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"capture attempt directory already exists: {destination}")
    missing = [name for name in IMPLEMENTATION_SOURCES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing source receipt files: {missing}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    stdout_path = destination / "stdout.json"
    stderr_path = destination / "stderr.txt"
    metadata_path = destination / "capture.json"
    # Create all durable stream destinations exclusively before starting the
    # child, so a retry can never truncate or relabel an earlier attempt.
    stdout_fd = os.open(stdout_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    stderr_fd = os.open(stderr_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    metadata_fd = os.open(metadata_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    before = {
        "schema": "csl.buryatia.capture/1",
        "attempt_id": destination.name,
        "status": "running",
        "mode": mode,
        "command": [Path(command[0]).name, *command[1:]],
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": git_value(source, "rev-parse", "HEAD"),
        "source_tree": git_value(source, "rev-parse", "HEAD^{tree}"),
        "source_status": git_value(source, "status", "--porcelain=v1", "--untracked-files=all"),
        "source_sha256": {name: sha256(source / name) for name in IMPLEMENTATION_SOURCES},
        "build_cache_sha256": sha256(build_cache),
        "build_configuration": build_receipt(build_cache),
        "executable_sha256": sha256(Path(command[0]).resolve(strict=True)),
        "python": sys.version,
        "platform": platform.platform(),
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
    }
    with os.fdopen(metadata_fd, "w", encoding="utf-8") as metadata:
        json.dump(before, metadata, indent=2, sort_keys=True)
        metadata.write("\n")
        metadata.flush()
        os.fsync(metadata.fileno())

    return_code: int | None = None
    spawn_error: str | None = None
    with os.fdopen(stdout_fd, "wb") as stdout, os.fdopen(stderr_fd, "wb") as stderr:
        try:
            result = subprocess.run(command, cwd=source, stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, check=False)
            return_code = result.returncode
        except OSError as error:
            spawn_error = f"{type(error).__name__}: {error}"
        finally:
            stdout.flush()
            os.fsync(stdout.fileno())
            stderr.flush()
            os.fsync(stderr.fileno())

    after = {
        **before,
        "status": "spawn_error" if spawn_error else "completed" if return_code == 0 else "failed",
        "exit_code": return_code,
        "spawn_error": spawn_error,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_bytes": stderr_path.stat().st_size,
        "stdout_sha256": sha256(stdout_path),
        "stderr_sha256": sha256(stderr_path),
    }
    temporary_metadata = destination / "capture.final.json"
    with temporary_metadata.open("x", encoding="utf-8") as metadata:
        json.dump(after, metadata, indent=2, sort_keys=True)
        metadata.write("\n")
        metadata.flush()
        os.fsync(metadata.fileno())
    os.replace(temporary_metadata, metadata_path)
    if spawn_error:
        raise RuntimeError(f"native report could not start; evidence retained in {destination}: {spawn_error}")
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)
    return after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--build-cache", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True,
                        help="new attempt directory; existing destinations are rejected")
    parser.add_argument("--mode", choices=("--dim4-literal-affine", "--diagnose-v-h"),
                        default="--dim4-literal-affine")
    args = parser.parse_args()
    command = [str(args.executable.resolve(strict=True)), args.mode]
    try:
        result = capture(command, args.source, args.build_cache, args.capture, args.mode)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Invoke the native functional example and retain its exact process evidence.

No model or geometry computation runs in this Python protocol. Build the native
producer separately with the repository toolchain and shared native-build lock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess

SOURCE_FILES = (
    "include/csl/model/flexible_pitch.hpp", "include/csl/model/catalogue.hpp",
    "include/csl/model/contracts.hpp", "include/csl/model/discretization.hpp",
    "include/csl/model/linear_system.hpp", "src/model/flexible_pitch.cpp",
    "src/model/catalogue.cpp", "src/model/linear_system.cpp",
    "src/model/discretization/adapter.cpp", "src/model/discretization/rk4.cpp",
    "src/model/discretization/internal.hpp", "src/geometry/generators/generator_sets.cpp",
    "src/geometry/hull/quickhull_2d.cpp", "examples/native_flexible_pitch.cpp",
    "examples/native_catalogue_projection.hpp", "examples/CMakeLists.txt",
    "tests/unit/model/flexible_pitch_tests.cpp", "tests/unit/model/flexible_pitch_slew_tests.cpp",
    "tests/installed/CMakeLists.txt", "src/model/Module.cmake", "src/model/Tests.cmake",
    "cmake/RunInstalledClient.cmake",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(repository: Path, executable: Path, output: Path, source: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise ValueError("producer source must be an exact full Git commit")
    repository, executable, output = repository.resolve(), executable.resolve(), output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("capture output must be new")
    exported = {}
    for name in SOURCE_FILES:
        content = subprocess.check_output(["git", "show", source + ":" + name], cwd=repository)
        if (repository / name).is_symlink() or (repository / name).read_bytes() != content:
            raise ValueError("producer source differs from captured commit: " + name)
        exported[name] = content
    binary_sha = digest(executable.read_bytes())
    started = datetime.now(timezone.utc).isoformat()
    command = [str(executable), str(output)]
    process = subprocess.run(command, capture_output=True, check=False)
    ended = datetime.now(timezone.utc).isoformat()
    # Failed native output remains inspectable. It is never promoted as success.
    output.mkdir(exist_ok=True)
    (output / "native.stdout").write_bytes(process.stdout)
    (output / "native.stderr").write_bytes(process.stderr)
    receipt = {"schema": "csl.native-functional-process/1", "producer_source_commit": source,
               "executable_sha256": binary_sha, "argv": command, "returncode": process.returncode,
               "started_utc": started, "ended_utc": ended,
               "stdout_sha256": digest(process.stdout), "stderr_sha256": digest(process.stderr),
               "scope": "functional native invocation; no timing or performance claim"}
    (output / "process-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if process.returncode != 0:
        raise RuntimeError("native capture failed; raw process evidence was retained")
    if digest(executable.read_bytes()) != binary_sha:
        raise ValueError("producer binary changed during capture")
    for name, content in exported.items():
        if (repository / name).read_bytes() != content:
            raise ValueError("producer source changed during capture: " + name)
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    return {"producer_source_commit": source, "producer_binary_sha256": binary_sha,
            "producer_source_files_sha256": {name: digest(data) for name, data in exported.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = capture(args.repository, args.executable, args.output, args.source_commit)
    print(json.dumps(result, indent=2))

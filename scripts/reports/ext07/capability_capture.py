"""Capture a clean Release profile of EXT-07 capability admission and enumeration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

if __package__:
    from .capture import (cmake_build_command, receipt, run, save,
                          validate_jobs)
else:
    from capture import (cmake_build_command, receipt, run, save,
                         validate_jobs)


def capture(source: Path, destination: Path, commit: str, cmake: str,
            jobs: int = 4, build_dir: Path | None = None) -> None:
    validate_jobs(jobs)
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Capture directory must be new")
    before = receipt(source, commit, "prebuild")
    destination.mkdir(parents=True)
    save(destination / "prebuild.json", before)
    build = (build_dir.resolve(strict=True) if build_dir is not None else
             destination / "build")
    env = dict(os.environ, VSLANG="1033", PreferredUILang="en-US",
               DOTNET_CLI_UI_LANGUAGE="en-US")
    private_paths = ((build, "<BUILD>"),)
    run([cmake, "-S", str(source), "-B", str(build), "-DBUILD_TESTING=OFF",
         "-DCMAKE_BUILD_TYPE=Release", "-DCSL_ENABLE_HIGHS=ON",
         "-DCSL_ENABLE_QHULL=OFF", "-DCSL_BUILD_EXT07_REPORT=ON"],
        source, destination / "configure.log", env, private_paths)
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    generator_match = re.search(r"^CMAKE_GENERATOR:INTERNAL=(.*)$", cache,
                                re.MULTILINE)
    if not generator_match:
        raise ValueError("CMake cache is missing its generator")
    run(cmake_build_command(cmake, build, "csl_ext07_capability_report", jobs,
                            generator_match.group(1).strip()),
        source, destination / "build.log", env, private_paths)
    if not (destination / "build.log").read_bytes().strip():
        raise ValueError("Release build produced no retained build output")
    executable = build / ("Release/csl_ext07_capability_report.exe" if os.name == "nt"
                          else "csl_ext07_capability_report")
    if not executable.is_file():
        raise FileNotFoundError(executable)
    result = subprocess.run([str(executable), "measure"], cwd=source, env=env,
                            capture_output=True)
    (destination / "measure.jsonl").write_bytes(result.stdout)
    (destination / "measure.stderr.txt").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(f"Capability measurement failed ({result.returncode})")

    after = receipt(source, commit, "postrun")
    after["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    save(destination / "postrun.json", after)
    cache_bytes = (build / "CMakeCache.txt").read_bytes()
    (destination / "CMakeCache.raw.txt").write_bytes(cache_bytes)
    compiler_files = list(build.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("Expected exactly one CMake C++ compiler receipt")
    compiler_receipt = compiler_files[0].read_bytes()
    (destination / "CMakeCXXCompiler.raw.cmake").write_bytes(compiler_receipt)
    cache_text = cache_bytes.decode("utf-8", errors="replace")
    compiler_text = compiler_receipt.decode("utf-8", errors="replace")

    def cache_value(key: str) -> str | None:
        match = re.search(r"^" + re.escape(key) + r"(?::[^=]+)?=(.*)$",
                          cache_text, re.MULTILINE)
        return match.group(1).strip() if match else None

    compiler_id = re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)',
                            compiler_text)
    compiler_version = re.search(
        r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', compiler_text)
    save(destination / "host.json", {
        "source_commit": commit, "source_tree": before["tree"],
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "host": f"{platform.system()} measurement workstation",
        "host_name_sha256": hashlib.sha256(platform.node().encode()).hexdigest(),
        "os": platform.platform(), "processor": platform.processor(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "logical_processors": os.cpu_count(),
        "compiler_receipt": "CMakeCXXCompiler.raw.cmake",
        "compiler_id": compiler_id.group(1) if compiler_id else
                       cache_value("CMAKE_CXX_COMPILER_ID"),
        "compiler_version": compiler_version.group(1) if compiler_version else
                            cache_value("CMAKE_CXX_COMPILER_VERSION"),
        "cmake": subprocess.check_output([cmake, "--version"], text=True).splitlines()[0],
        "configuration": "Release", "cxx_standard": 20,
        "native_threads_requested": 1, "native_threads_configured": 1,
        "outer_workers_requested": 1, "outer_workers_observed": 1,
        "profile_calls_per_batch": 1000, "warmup_batches_excluded": 1,
        "measured_repetitions_per_fixture": 7,
        "fixture_order": "all fixtures are measured in each repetition",
        "timing_scope": "report_hybrid_capability admission and complete path enumeration; fixture construction, build, and JSON output are excluded; no LP provider, relation composer, or optimizer is invoked",
        "raw_configure_log_sha256": hashlib.sha256(
            (destination / "configure.log.raw").read_bytes()).hexdigest(),
        "raw_build_log_sha256": hashlib.sha256(
            (destination / "build.log.raw").read_bytes()).hexdigest(),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--build-dir", type=Path,
                        help="reuse a Release build tree for this exact source checkout")
    args = parser.parse_args()
    capture(args.source, args.capture, args.commit, args.cmake, args.jobs,
            args.build_dir)

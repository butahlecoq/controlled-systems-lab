"""Capture a clean Release measurement of the EXT-07 two-parameter verifier."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

if __package__:
    from .capture import cmake_build_command, receipt, run, save, validate_jobs
else:
    from capture import cmake_build_command, receipt, run, save, validate_jobs


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
    run([cmake, "-S", str(source), "-B", str(build), "-DBUILD_TESTING=OFF",
         "-DCMAKE_BUILD_TYPE=Release",
         "-DCSL_ENABLE_HIGHS=ON", "-DCSL_ENABLE_QHULL=OFF",
         "-DCSL_BUILD_EXT07_REPORT=ON"], source,
        destination / "configure.log", env)
    cache_text = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    generator_match = re.search(r"^CMAKE_GENERATOR:INTERNAL=(.*)$", cache_text, re.MULTILINE)
    if not generator_match:
        raise ValueError("CMake cache is missing its generator")
    run(cmake_build_command(cmake, build, "csl_ext07_two_parameter_report", jobs,
                            generator_match.group(1).strip(),
                            ("/nologo", "/p:PreferredUILang=en-US")),
        source, destination / "build.log", env)
    if not (destination / "build.log").read_bytes().strip():
        raise ValueError("Release build produced no retained build output")
    executable = build / ("Release/csl_ext07_two_parameter_report.exe" if os.name == "nt"
                          else "csl_ext07_two_parameter_report")
    if not executable.is_file():
        raise FileNotFoundError(executable)
    capture_executable = destination / "build" / executable.name
    capture_executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(executable, capture_executable)
    for phase in ("smoke", "measure"):
        result = subprocess.run([str(executable), phase], cwd=source, env=env,
                                capture_output=True)
        (destination / f"{phase}.jsonl").write_bytes(result.stdout)
        (destination / f"{phase}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"Two-parameter {phase} run failed ({result.returncode})")
    after = receipt(source, commit, "postrun")
    after["executable_sha256"] = hashlib.sha256(capture_executable.read_bytes()).hexdigest()
    save(destination / "postrun.json", after)
    cache = (build / "CMakeCache.txt").read_bytes()
    (destination / "CMakeCache.raw.txt").write_bytes(cache)
    compiler_files = list(build.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("Expected exactly one CMake C++ compiler receipt")
    compiler_receipt = compiler_files[0].read_bytes()
    (destination / "CMakeCXXCompiler.raw.cmake").write_bytes(compiler_receipt)
    cache_text = cache.decode("utf-8", errors="replace")
    def cache_value(key: str) -> str | None:
        match = re.search(r"^" + re.escape(key) + r"(?::[^=]+)?=(.*)$",
                          cache_text, re.MULTILINE)
        return match.group(1).strip() if match else None
    compiler_text = compiler_receipt.decode("utf-8", errors="replace")
    compiler_id = re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', compiler_text)
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
        "cmake_cache_sha256": hashlib.sha256(cache).hexdigest(),
        "native_threads_requested": 1, "native_threads_configured": 1,
        "native_threads_observed": None,
        "outer_workers_requested": 1, "outer_workers_observed": 1,
        "workspace_reuse": "none; fresh fixture, provider and workspace per call",
        "absolute_tolerance": 1e-8, "relative_tolerance": 1e-8,
        "enumeration_limits": {"max_horizon": 2, "max_paths": 8},
        "relation_limits": {"max_variables": 64, "max_rows": 4096,
                             "max_matrix_elements": 65536},
        "timing_scope": "One end-to-end call includes fixture/provider setup, complete path relation assembly, LP execution, candidate-face construction, and verification of all allowed path families. Serialization, build, and rendering are excluded.",
        "warmup_policy": "One excluded 10-call batch followed by seven measured 20-call batches",
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
    capture(args.source, args.capture, args.commit, args.cmake, args.jobs, args.build_dir)

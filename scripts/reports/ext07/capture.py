"""Run the public EXT-07 path/optimization/family-verification route in Release."""
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


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=source, text=True).strip()


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def receipt(source: Path, commit: str, phase: str) -> dict:
    status = git(source, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    value = {"phase": phase, "commit": git(source, "rev-parse", "HEAD"),
             "tree": git(source, "rev-parse", "HEAD^{tree}"), "status": status,
             "observed_utc": datetime.now(timezone.utc).isoformat()}
    if value["commit"] != commit or status:
        raise ValueError("Capture requires a clean checkout at the frozen source commit")
    return value


def run(command: list[str], source: Path, output: Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=source, env=env, capture_output=True)
    # Keep diagnostics when a build or run fails so the failed attempt is not lost.
    raw = result.stdout + result.stderr
    raw_path = output.with_suffix(output.suffix + ".raw")
    raw_path.write_bytes(raw)
    redacted = raw
    for private_path, label in ((source, b"<SOURCE>"), (output.parent, b"<CAPTURE>")):
        text = str(private_path).encode()
        redacted = redacted.replace(text, label).replace(text.replace(b"\\", b"/"), label)
    output.write_bytes(redacted)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}")


def capture(source: Path, destination: Path, commit: str, cmake: str) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Capture directory must be new")
    before = receipt(source, commit, "prebuild")
    destination.mkdir(parents=True)
    save(destination / "prebuild.json", before)
    build = destination / "build"
    env = dict(os.environ, VSLANG="1033", PreferredUILang="en-US")
    run([cmake, "-S", str(source), "-B", str(build), "-DBUILD_TESTING=OFF",
         "-DCSL_ENABLE_HIGHS=ON", "-DCSL_ENABLE_QHULL=OFF", "-DCSL_BUILD_EXT07_REPORT=ON"],
        source, destination / "configure.log", env)
    run([cmake, "--build", str(build), "--config", "Release", "--target",
         "csl_ext07_hybrid_report", "--parallel", "4", "--",
         "/p:PreferredUILang=en-US"],
        source, destination / "build.log", env)
    if not (destination / "build.log").read_bytes().strip():
        raise ValueError("Release build produced no retained build output")
    executable = build / ("Release/csl_ext07_hybrid_report.exe" if os.name == "nt"
                          else "csl_ext07_hybrid_report")
    if not executable.is_file():
        raise FileNotFoundError(executable)
    for phase in ("smoke", "measure"):
        result = subprocess.run([str(executable), phase], cwd=source, env=env,
                                capture_output=True)
        (destination / f"{phase}.jsonl").write_bytes(result.stdout)
        (destination / f"{phase}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"EXT-07 {phase} run failed ({result.returncode})")
    after = receipt(source, commit, "postrun")
    after["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
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
        match = re.search(r"^" + re.escape(key) + r"(?::[^=]+)?=(.*)$", cache_text, re.MULTILINE)
        return match.group(1).strip() if match else None
    cmake_version = subprocess.check_output([cmake, "--version"], text=True).splitlines()[0]
    compiler_text = compiler_receipt.decode("utf-8", errors="replace")
    compiler_id = re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', compiler_text)
    compiler_version = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', compiler_text)
    save(destination / "host.json", {
        "source_commit": commit, "source_tree": before["tree"],
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "host": "Windows measurement workstation",
        "host_name_sha256": hashlib.sha256(platform.node().encode()).hexdigest(),
        "os": platform.platform(),
        "processor": platform.processor(), "architecture": platform.machine(),
        "python": platform.python_version(), "logical_processors": os.cpu_count(),
        "compiler_receipt": "CMakeCXXCompiler.raw.cmake",
        "compiler_id": compiler_id.group(1) if compiler_id else cache_value("CMAKE_CXX_COMPILER_ID"),
        "compiler_version": compiler_version.group(1) if compiler_version else cache_value("CMAKE_CXX_COMPILER_VERSION"),
        "cmake": cmake_version,
        "configuration": "Release", "cxx_standard": 20,
        "native_threads_requested": 1, "native_threads_configured": 1,
        "native_threads_observed": None,
        "outer_workers_requested": 1, "outer_workers_observed": 1,
        "seed": 0, "workspace_reuse": "none; fresh registered provider/workspace per call",
        "absolute_tolerance": 1e-8, "relative_tolerance": 1e-8,
        "relation_limits": {"max_variables": 16, "max_rows": 128,
                             "max_matrix_elements": 2048},
        "timing_scope": "Setup constructs the fixture and registered providers; assembly builds the complete path portfolio and H relation; solve executes the registered branch optimizer; verify rebuilds the candidate face and checks the complete path family; end-to-end begins before fixture construction and ends after verification. CSV/JSONL output, rendering and build are excluded.",
        "warmup_policy": "One excluded 10-call batch followed by seven measured 20-call batches",
        "raw_configure_log_sha256": hashlib.sha256((destination / "configure.log.raw").read_bytes()).hexdigest(),
        "raw_build_log_sha256": hashlib.sha256((destination / "build.log.raw").read_bytes()).hexdigest(),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cmake", default="cmake")
    args = parser.parse_args()
    capture(args.source, args.capture, args.commit, args.cmake)

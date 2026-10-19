"""Run the public EXT-05 adapter from a clean, frozen Release source."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=source, text=True).strip()


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def receipt(source: Path, commit: str, phase: str) -> dict:
    value = {"phase": phase, "commit": git(source, "rev-parse", "HEAD"),
             "tree": git(source, "rev-parse", "HEAD^{tree}"),
             "status": git(source, "status", "--porcelain=v1", "--untracked-files=all").splitlines(),
             "observed_utc": datetime.now(timezone.utc).isoformat()}
    if value["commit"] != commit or value["status"]:
        raise ValueError("Capture requires a clean checkout at the frozen commit")
    return value


def run(args: list[str], source: Path, path: Path, env: dict[str, str]) -> None:
    result = subprocess.run(args, cwd=source, env=env, capture_output=True)
    path.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args}")


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
         "-DCSL_ENABLE_HIGHS=OFF", "-DCSL_ENABLE_QHULL=OFF",
         "-DCSL_BUILD_EXT05_REPORT=ON"], source, destination / "configure.log", env)
    run([cmake, "--build", str(build), "--config", "Release", "--target",
         "csl_ext05_discretization_report", "--parallel", "4", "--",
         "/p:PreferredUILang=en-US", "/clp:ErrorsOnly"],
        source, destination / "build.log", env)
    executable = build / "Release/csl_ext05_discretization_report.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    for phase in ("smoke", "measure"):
        result = subprocess.run([str(executable), phase], cwd=source,
                                env=env, capture_output=True)
        (destination / f"{phase}.csv").write_bytes(result.stdout)
        (destination / f"{phase}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"EXT-05 {phase} failed ({result.returncode})")
    after = receipt(source, commit, "postrun")
    after["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    save(destination / "postrun.json", after)
    (destination / "CMakeCache.raw.txt").write_bytes((build / "CMakeCache.txt").read_bytes())
    compiler_files = list(build.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("Expected one CMake compiler receipt")
    (destination / "CMakeCXXCompiler.raw.cmake").write_bytes(compiler_files[0].read_bytes())
    save(destination / "host.json", {
        "source_commit": commit, "source_tree": before["tree"],
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(), "os": platform.platform(),
        "processor": platform.processor(), "architecture": platform.machine(),
        "python": platform.python_version(), "logical_processors": os.cpu_count(),
        "compiler_receipt": "CMakeCXXCompiler.raw.cmake",
        "configuration": "Release", "native_threads_requested": 1,
        "outer_workers_requested": 1, "native_threads_observed": None,
        "seed": None, "workspace_reuse": "none",
        "timing_scope": "One public discretize, snapshot and two step calls, including literal checks; excludes fixture construction, CSV output and rendering",
        "warmup_policy": "One excluded 100-call batch before seven measured 100-call batches",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cmake", default="cmake")
    args = parser.parse_args()
    capture(args.source, args.capture, args.commit, args.cmake)

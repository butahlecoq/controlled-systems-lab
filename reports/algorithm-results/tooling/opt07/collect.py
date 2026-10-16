"""Source-bound collector for later, independently reviewed OPT-07 measurements.

`preflight` runs no timed algorithm call. `measure` is intentionally a separate
explicit subcommand and must only run after fixed-code/harness review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from oracle import FIXTURES, require
from validate import validate_stream


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def cache_values(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line.startswith(("#", "//")) and ":" in line and "=" in line:
            key = line.split(":", 1)[0]
            values[key] = line.split("=", 1)[1]
    return values


def release_project(path: Path) -> dict:
    root = ET.parse(path).getroot()
    ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    groups = root.findall("m:ItemDefinitionGroup", ns)
    selected = [group for group in groups
                if "Release|x64" in group.attrib.get("Condition", "")]
    require(len(selected) == 1, "ambiguous Release x64 project configuration")
    compiler = selected[0].find("m:ClCompile", ns)
    require(compiler is not None, "missing Release compiler settings")
    fields = {child.tag.rsplit("}", 1)[-1]: child.text for child in compiler}
    require(fields.get("LanguageStandard") == "stdcpp20" and
            fields.get("Optimization") == "MaxSpeed" and
            "NDEBUG" in (fields.get("PreprocessorDefinitions") or ""),
            "Release C++20 optimization/NDEBUG settings absent")
    return {key: fields.get(key) for key in
            ("LanguageStandard", "Optimization", "PreprocessorDefinitions")}


def preflight(exe: Path, source_root: Path, source_commit: str,
              build_log: Path, concurrent_work: Path) -> dict:
    source_root = source_root.resolve(strict=True)
    exe = exe.resolve(strict=True)
    build_log = build_log.resolve(strict=True)
    concurrent_work = concurrent_work.resolve(strict=True)
    harness = source_root / "reports/algorithm-results/tooling/opt07"
    require(command("git", "-C", str(source_root), "rev-parse", "HEAD") == source_commit,
            "source HEAD differs from reviewed commit")
    require(not command("git", "-C", str(source_root), "status", "--porcelain",
                        "--untracked-files=all"), "source checkout is dirty")
    require(exe.name == "csl_opt07_measure.exe" and exe.parent.name == "Release",
            "expected the Release OPT-07 harness executable")
    build_root = exe.parent.parent
    cache = cache_values(build_root / "CMakeCache.txt")
    require(Path(cache.get("CMAKE_HOME_DIRECTORY", "")).resolve() == harness.resolve() and
            Path(cache.get("CSL_ROOT", "")).resolve() == source_root and
            cache.get("CMAKE_GENERATOR") == "Visual Studio 17 2022",
            "CMake source/build ownership differs from reviewed checkout")
    release = release_project(build_root / "csl_opt07_measure.vcxproj")
    description = json.loads(command(str(exe), "describe"))
    require(description.get("kind") == "describe" and
            description.get("source_commit") == source_commit and
            description.get("harness_sha256") == sha256(harness / "ordered_hull_driver.cpp") and
            description.get("configuration") == "Release" and
            description.get("ndebug") is True and
            description.get("cxx_standard", 0) >= 202002 and
            description.get("batch_calls") == 100 and
            description.get("repetitions") == 7,
            "executable identity/configuration differs from reviewed source")
    raw_log = build_log.read_text(encoding="utf-8", errors="replace")
    harness_commands = [line for line in raw_log.splitlines()
                        if "CL.exe" in line and "ordered_hull_driver.cpp" in line]
    require(any("/O2" in line and "/std:c++20" in line and
                re.search(r"/D\s+NDEBUG\b", line) for line in harness_commands),
            "verbose clean Release build evidence is incomplete")
    note = concurrent_work.read_text(encoding="utf-8").strip()
    require(bool(note), "concurrent-work note is required")
    source_paths = [
        "src/geometry/hull/ordered_reducer.cpp", "src/geometry/hull_reducer.cpp",
        "src/geometry/exact_convex_combination.hpp",
        "include/csl/geometry/hull_reducer.hpp",
        "reports/algorithm-results/tooling/opt07/ordered_hull_driver.cpp",
        "reports/algorithm-results/tooling/opt07/oracle.py",
        "reports/algorithm-results/tooling/opt07/validate.py",
        "reports/algorithm-results/tooling/opt07/collect.py",
    ]
    fixture_bytes = json.dumps(FIXTURES, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")
    return {
        "source_commit": source_commit,
        "algorithm": {"method": "csl.hull.ordered-membership", "version": "1.0.0",
                      "source": "src/geometry/hull/ordered_reducer.cpp"},
        "backend": {"method": "csl.lp.highs", "adapter_version": "1.0.0+highs.1.11.0",
                    "native_version": "1.11.0", "configured_threads": 1,
                    "presolve": "off", "parallel": "off",
                    "simplex_iteration_limit": None},
        "source_sha256": {relative: sha256(source_root / relative)
                          for relative in source_paths},
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "executable_sha256": sha256(exe),
        "build_log_sha256": sha256(build_log),
        "cmake_cache_sha256": sha256(build_root / "CMakeCache.txt"),
        "generated_release_project_sha256": sha256(build_root / "csl_opt07_measure.vcxproj"),
        "release_project": release,
        "description": description,
        "environment": {"os": platform.platform(), "machine": platform.machine(),
                        "logical_processors": os.cpu_count(), "python": sys.version.split()[0],
                        "concurrent_work_note": note,
                        "native_thread_policy": "HiGHS adapter configured for one thread",
                        "observed_native_threads": None},
        "protocol": {"warmup_batches_per_fixture": 1, "measured_batches_per_fixture": 7,
                     "calls_per_batch": 100, "workspace_policy": "fresh LP and HullReducer workspaces per call, created before timer",
                     "timing_scope": "steady_clock spans the loop of 100 registered HullReducer.run_with calls, lazy native initialization and output vector moves; input/workspace construction, verification, JSON and rendering excluded",
                     "internal_lp_phase_timing": "unavailable",
                     "performance_interpretation": "single adapter; no comparator or speedup claim"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "measure"))
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--concurrent-work-file", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = preflight(args.exe, args.source_root, args.source_commit,
                         args.build_log, args.concurrent_work_file)
    if args.action == "preflight":
        print(json.dumps({"source_commit": evidence["source_commit"],
                          "executable_sha256": evidence["executable_sha256"],
                          "status": "preflight_passed"}, sort_keys=True))
        return
    require(args.out is not None and not args.out.exists(),
            "measurement output must be a fresh directory")
    args.out.mkdir(parents=True)
    result = subprocess.run([str(args.exe.resolve()), "measure"], capture_output=True)
    (args.out / "raw-stdout.jsonl").write_bytes(result.stdout)
    (args.out / "raw-stderr.txt").write_bytes(result.stderr)
    sanitized = args.build_log.read_text(encoding="utf-8", errors="replace")
    sanitized = sanitized.replace(str(args.source_root.resolve()), "$SOURCE_ROOT")
    sanitized = sanitized.replace(str(args.exe.resolve().parent.parent), "$BUILD_ROOT")
    (args.out / "release-build-log-sanitized.txt").write_text(
        sanitized, encoding="utf-8", newline="\n")
    evidence["process_exit_code"] = result.returncode
    (args.out / "collection.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    require(command("git", "-C", str(args.source_root.resolve()), "rev-parse", "HEAD") ==
            args.source_commit and
            not command("git", "-C", str(args.source_root.resolve()), "status",
                        "--porcelain", "--untracked-files=all"),
            "source changed during measurement; raw bytes retained")
    require(result.returncode == 0, "driver failed; all raw bytes retained")
    validation = validate_stream(args.out / "raw-stdout.jsonl", "measurement")
    (args.out / "functional-validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(validation, sort_keys=True))


if __name__ == "__main__":
    main()

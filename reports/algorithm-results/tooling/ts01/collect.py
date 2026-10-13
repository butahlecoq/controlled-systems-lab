"""Build and measure T-S01 from an exact, clean solver source worktree."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET

import report

try:
    import psutil
except ImportError:
    psutil = None


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, *, capture=True):
    result = subprocess.run([str(part) for part in command], capture_output=capture, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-4000:] if capture else ""
        raise SystemExit(f"command failed ({result.returncode}): {command!r}\n{detail}")
    return result


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake", type=Path, required=True, help="CMake executable used to configure and build the pinned source")
    parser.add_argument("--dependency-cache", type=Path, help="optional populated FetchContent cache, for disconnected rebuilds")
    parser.add_argument("--build-root", type=Path, required=True, help="new directory for the clean source worktree and Release build")
    parser.add_argument("--out", type=Path, required=True, help="new directory for raw events and the collection record")
    parser.add_argument("--algorithm-source-commit", default=report.SOURCE_COMMIT)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[4]
    harness_commit = git(root, "rev-parse", "HEAD")
    if git(root, "status", "--porcelain"):
        raise SystemExit("measurement requires a clean, committed harness checkout")
    if args.algorithm_source_commit != report.SOURCE_COMMIT:
        raise SystemExit("requested source SHA differs from the report's pinned solver source")
    cmake = args.cmake.resolve(strict=True)
    if not cmake.is_file():
        raise SystemExit("--cmake must name an executable file")
    build_root = args.build_root.resolve()
    out = args.out.resolve()
    build_root.mkdir(parents=True, exist_ok=False)
    source_checkout = build_root / "solver-source"
    build_dir = build_root / "release-build"
    run(["git", "-C", str(root), "worktree", "add", "--detach", str(source_checkout), report.SOURCE_COMMIT])
    if git(source_checkout, "rev-parse", "HEAD") != report.SOURCE_COMMIT or git(source_checkout, "status", "--porcelain"):
        raise SystemExit("solver worktree is not at the exact pinned clean commit")

    runner = root / "reports" / "algorithm-results" / "tooling" / "ts01" / "runner"
    driver = root / "reports" / "algorithm-results" / "tooling" / "ts01" / "ts01_measure.cpp"
    runner_cmake = runner / "CMakeLists.txt"
    configure_command = [cmake, "-S", runner, "-B", build_dir, "-G", "Visual Studio 17 2022", "-A", "x64",
                         f"-DCSL_SOURCE_ROOT={source_checkout}", "-DBUILD_TESTING=OFF"]
    if args.dependency_cache is not None:
        dependency_cache = args.dependency_cache.resolve(strict=True)
        configure_command.extend([f"-DFETCHCONTENT_BASE_DIR={dependency_cache}", "-DFETCHCONTENT_FULLY_DISCONNECTED=ON"])
    configure = run(configure_command)
    (build_root / "configure.log").write_bytes(configure.stdout + configure.stderr)
    build_command = [cmake, "--build", build_dir, "--config", "Release", "--target", "csl_syn07_ts01_report", "--parallel", "4"]
    build = run(build_command)
    build_log = build.stdout + build.stderr
    (build_root / "build.log").write_bytes(build_log)

    if git(source_checkout, "rev-parse", "HEAD") != report.SOURCE_COMMIT or git(source_checkout, "status", "--porcelain"):
        raise SystemExit("pinned solver worktree changed during configure/build")
    cache = build_dir / "CMakeCache.txt"
    cache_text = cache.read_text(encoding="utf-8", errors="replace")
    if ("CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" not in cache_text or
            "CMAKE_GENERATOR_PLATFORM:INTERNAL=x64" not in cache_text):
        raise SystemExit("unexpected generator in pinned Release build")
    target_project = build_dir / "csl_syn07_ts01_report.vcxproj"
    target_root = ET.parse(target_project).getroot()
    namespace = target_root.tag.partition("}")[0].removeprefix("{")
    qualified = lambda name: "{" + namespace + "}" + name
    groups = target_root.findall(qualified("ItemDefinitionGroup"))
    release = next((group for group in groups if "Release|x64" in group.attrib.get("Condition", "")), None)
    compile_node = release.find(qualified("ClCompile")) if release is not None else None
    props = {node.tag.rsplit("}", 1)[-1]: (node.text or "") for node in compile_node} if compile_node is not None else {}
    if props.get("LanguageStandard") != "stdcpp20" or props.get("Optimization") != "MaxSpeed" or "NDEBUG" not in props.get("PreprocessorDefinitions", ""):
        raise SystemExit("generated target does not prove C++20 Release/NDEBUG settings")
    executable = build_dir / "Release" / "csl_syn07_ts01_report.exe"
    binary = executable.read_bytes()
    cpu_before = psutil.cpu_percent(interval=1.0) if psutil is not None else None
    result = subprocess.run([str(executable)], capture_output=True, check=False)
    cpu_after = psutil.cpu_percent(interval=1.0) if psutil is not None else None
    if result.returncode:
        raise SystemExit(f"measurement executable failed with status {result.returncode}")
    if git(source_checkout, "rev-parse", "HEAD") != report.SOURCE_COMMIT or git(source_checkout, "status", "--porcelain"):
        raise SystemExit("pinned solver worktree changed during measurement")
    if git(root, "status", "--porcelain") or git(root, "rev-parse", "HEAD") != harness_commit:
        raise SystemExit("harness checkout changed during measurement")

    try:
        lines = result.stdout.decode("utf-8", errors="strict").splitlines()
        events = [json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))) for line in lines]
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit("measurement executable emitted invalid JSONL") from error
    if len(events) != 8 or any(event.get("schema") != "csl.syn07-ts01-measurement-event/1" for event in events):
        raise SystemExit("measurement output does not match the expected eight-event schema")
    expected_order = [(0, True), *[(i, False) for i in range(1, 8)]]
    if [(event.get("repetition"), event.get("warmup")) for event in events] != expected_order:
        raise SystemExit("T-S01 warmup/repetition sequence differs")
    if any(event.get("status") != "passed" or type(event.get("elapsed_ns")) is not int or event["elapsed_ns"] < 0 or not event.get("consumed_result_marker") for event in events):
        raise SystemExit("one or more T-S01 attempts failed validation or returned invalid timing")
    measured = [event for event in events if not event["warmup"]]
    values = [event["elapsed_ns"] for event in measured]
    compiler_configs = list((build_dir / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(compiler_configs) != 1:
        raise SystemExit("unable to identify generated C++ compiler configuration")
    compiler_config = compiler_configs[0]
    compiler_text = compiler_config.read_text(encoding="utf-8", errors="replace")
    def cmake_set(name):
        prefix = f'set({name} "'
        line = next((line for line in compiler_text.splitlines() if line.startswith(prefix)), None)
        return line[len(prefix):-2] if line else "unavailable"
    cxx_compiler = cmake_set("CMAKE_CXX_COMPILER")
    cxx_version = cmake_set("CMAKE_CXX_COMPILER_VERSION")
    if cxx_compiler == "unavailable" or cxx_version == "unavailable":
        raise SystemExit("generated CMake compiler identity is incomplete")
    measurement = {
        "schema": "csl.syn07-ts01-measurement-collection/1",
        "algorithm_source_commit": report.SOURCE_COMMIT,
        "algorithm_source_checkout": {"head": git(source_checkout, "rev-parse", "HEAD"),
            "tree_sha": git(source_checkout, "rev-parse", f"{report.SOURCE_COMMIT}^{{tree}}"), "clean_before_build": True, "clean_after_run": True,
            "strategy_source_sha256": sha(run(["git", "-C", source_checkout, "show", f"{report.SOURCE_COMMIT}:src/synthesis/strategy_ts01/analytic_profile.cpp"]).stdout),
            "strategy_header_sha256": sha(run(["git", "-C", source_checkout, "show", f"{report.SOURCE_COMMIT}:include/csl/synthesis/strategy_ts01/analytic_profile.hpp"]).stdout)},
        "harness_commit": harness_commit,
        "harness_sources": {"driver_sha256": sha(driver.read_bytes()), "runner_cmake_sha256": sha(runner_cmake.read_bytes())},
        "scope": "Fresh problem construction and resolution, strategy registration/selection/preparation, exclusive workspace creation, public bound-workspace run, and independent complete-H-relation plus exact-membership validation. Excludes process startup, JSON serialization, build, collection, and rendering.",
        "order": "One excluded warmup, followed by seven measured repetitions in one process. Single strategy only; alternation is inapplicable and no comparator was measured.",
        "counts": {"warmup": 1, "measured": len(measured), "passed": len(measured), "failed": 0, "unique_consumed_result_markers": len({event["consumed_result_marker"] for event in events}), "all_outputs_consumed_and_validated": True},
        "timing_ns": {"observations": values, "median": statistics.median(values), "min": min(values), "max": max(values), "range": max(values)-min(values)},
        "performance_conclusion": "inconclusive",
        "limiter": {"available": False, "reason": "No separate sampling/call-stack profile was collected; this record does not attribute the observed time or establish capacity."},
        "binary": {"path": str(executable.relative_to(build_root)), "sha256": sha(binary), "bytes": len(binary), "configuration": "Release", "ndebug": True, "cxx_standard": "c++20", "release_properties": props},
        "build_provenance": {"cmake_path": str(cmake), "cmake_sha256": sha(cmake.read_bytes()), "cmake_version": (run([cmake, "--version"]).stdout.decode("utf-8", errors="replace").splitlines()[0]),
            "cmake_cache_sha256": sha(cache.read_bytes()), "compiler_config_sha256": sha(compiler_config.read_bytes()), "target_project_sha256": sha(target_project.read_bytes()), "configure_log_sha256": sha((build_root / "configure.log").read_bytes()), "build_log_sha256": sha(build_log),
            "generator": "Visual Studio 17 2022 x64", "compiler": "MSVC", "compiler_path": cxx_compiler, "compiler_version": cxx_version, "configuration": "Release",
            "dependency_cache": str(args.dependency_cache.resolve()) if args.dependency_cache else "CMake source-defined fetches",
            "configure_command": [str(part) for part in configure_command], "build_command": [str(part) for part in build_command]},
        "environment": {"os": platform.platform(), "processor": platform.processor() or "unavailable", "logical_cpu_count": os.cpu_count(), "python": sys.version.split()[0], "clock": "std::chrono::steady_clock; elapsed duration in nanoseconds", "total_cpu_percent_1s_before": cpu_before, "total_cpu_percent_1s_after": cpu_after, "load_policy": "Unrelated processes were left running; the two CPU samples are outside the measured process. This is a single-side observation, so no interleaving or noise cancellation is claimed."},
        "raw_stdout_sha256": sha(result.stdout), "raw_stderr_sha256": sha(result.stderr),
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "events.jsonl").write_bytes(result.stdout)
    (out / "stderr.txt").write_bytes(result.stderr)
    (out / "collection.json").write_text(json.dumps(measurement, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "command.txt").write_text(json.dumps({"configure": configure_command, "build": build_command, "run": [executable]}, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(measurement, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

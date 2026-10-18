#!/usr/bin/env python3
"""Collect paired OPT-12 trials after binding the executable to a clean Release build."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import collector_common as common
from opt12_fixtures import SCENARIOS, fixture_descriptions, validate_driver_fixture_events
import report_data as data


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def cxx_compiler(toolchains: list[dict]) -> dict:
    matches = [item for item in toolchains if item.get("language") == "CXX"]
    if len(matches) != 1 or not isinstance(matches[0].get("compiler"), dict):
        raise ValueError("CMake File API must provide exactly one CXX compiler record")
    compiler = matches[0]["compiler"]
    if not all(isinstance(compiler.get(key), str) and compiler[key]
               for key in ("id", "version", "path")):
        raise ValueError("CMake File API CXX compiler record is incomplete")
    return compiler


def cmake_cache_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("//") or line.startswith("#") or not line:
            continue
        name, separator, value = line.partition("=")
        if separator and ":" in name:
            key = name.split(":", 1)[0]
            values[key] = value
    return values


def cmake_system_processor(build: Path) -> str:
    values = set()
    for path in (build / "CMakeFiles").glob("*/CMakeSystem.cmake"):
        source = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^set\(CMAKE_SYSTEM_PROCESSOR\s+"?([^"\)\s]+)"?\)',
                          source, re.MULTILINE)
        if match:
            values.add(match.group(1))
    if len(values) != 1:
        raise ValueError("generated CMake system processor identity is missing or inconsistent")
    return next(iter(values))


def validate_build_identity(record: dict, *, source_commit: str, build_owner: str,
                            compiler: dict, graph: dict, cache: dict[str, str],
                            system_processor: str) -> None:
    expected_fields = {"schema", "source_commit", "build_owner_sha256", "compiler",
                       "compiler_version", "generator", "architecture", "configured_flags",
                       "release_flags", "configuration", "ndebug"}
    if not isinstance(record, dict) or set(record) != expected_fields:
        raise ValueError("embedded build identity fields differ from csl.opt12-build/1")
    generator = graph["cmake"]["generator"]
    platform = cache["CMAKE_GENERATOR_PLATFORM"]
    expected = {
        "schema": "csl.opt12-build/1", "source_commit": source_commit,
        "build_owner_sha256": build_owner, "compiler": compiler["id"],
        "compiler_version": compiler["version"], "generator": generator,
        "architecture": f'{system_processor}/{platform}',
        "configured_flags": cache["CMAKE_CXX_FLAGS"],
        "release_flags": cache["CMAKE_CXX_FLAGS_RELEASE"],
        "configuration": "Release", "ndebug": True,
    }
    if record != expected:
        raise ValueError("embedded build identity differs from CMake cache and selected Release toolchain")
    target = next(item for item in graph["targets"] if item["name"] == "csl_opt12_warm_start_measure")
    groups = [item for item in target.get("compileGroups", []) if item.get("language") == "CXX"]
    if len(groups) != 1 or groups[0].get("languageStandard", {}).get("standard") != "20":
        raise ValueError("selected Release driver compile group is not C++20")
    flags = " ".join(fragment["fragment"] for group in groups
                      for fragment in group.get("compileCommandFragments", []))
    flags = " ".join(flags.split())
    for key in ("configured_flags", "release_flags"):
        normalized = " ".join(expected[key].split())
        if normalized and normalized not in flags:
            raise ValueError(f"embedded {key} are absent from the selected Release compile group")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error("at least five alternating paired repetitions are required")
    root = Path(__file__).resolve().parents[2]
    exe = args.exe.resolve(strict=True)
    build = args.build.resolve(strict=True)
    build_log = build / "opt12-release-build.log"
    if not build_log.is_file():
        parser.error("release build log must exist inside the selected build directory")
    head = git_value(root, "rev-parse", "HEAD")
    if head != args.source_commit or git_value(root, "status", "--porcelain"):
        parser.error("measurement requires the declared exact, clean source commit")
    try:
        common.validate_build_log(build_log, build, exe, root)
        if exe.stat().st_mtime_ns > build_log.stat().st_mtime_ns:
            raise ValueError("selected Release executable is newer than its retained build log")
        graph = common.release_graph(
            build, exe, root, target_name="csl_opt12_warm_start_measure",
            required={"csl_opt12_warm_start_measure", "csl_highs_lp", "highs",
                      "csl_optimization", "csl_registry", "csl_numeric", "csl_contracts"})
        reply = build / ".cmake" / "api" / "v1" / "reply"
        index_path = sorted(reply.glob("index-*.json"))[-1]
        index = data.parse_json(index_path.read_text(encoding="utf-8"))
        codemodel_path = reply / index["reply"]["codemodel-v2"]["jsonFile"]
        codemodel = data.parse_json(codemodel_path.read_text(encoding="utf-8"))
        paths = codemodel["paths"]
        toolchains = data.parse_json((reply / index["reply"]["toolchains-v1"]["jsonFile"]).read_text(encoding="utf-8"))["toolchains"]
        compiler = cxx_compiler(toolchains)
        build_owner = digest((paths["source"] + "\n" + paths["build"] + "\n" + compiler["path"]).encode())
        cache = cmake_cache_values(build / "CMakeCache.txt")
        system_processor = cmake_system_processor(build)
        for key in ("CMAKE_GENERATOR_PLATFORM",
                    "CMAKE_CXX_FLAGS", "CMAKE_CXX_FLAGS_RELEASE"):
            if not cache.get(key):
                raise ValueError(f"required CMake cache value is missing: {key}")
    except (ValueError, KeyError, OSError, IndexError, StopIteration) as error:
        parser.error(f"measurement executable/build graph validation failed: {type(error).__name__}: {error}")
    if args.out.exists():
        parser.error("output destination must be new")
    args.out.mkdir(parents=True)

    before = common.machine_snapshot()
    timed_out = False
    try:
        run = subprocess.run([str(exe), str(args.repetitions)], capture_output=True, timeout=120)
        raw_stdout, raw_stderr, return_code = run.stdout, run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        raw_stdout, raw_stderr, return_code = error.stdout or b"", error.stderr or b"", None
        if isinstance(raw_stdout, str): raw_stdout = raw_stdout.encode()
        if isinstance(raw_stderr, str): raw_stderr = raw_stderr.encode()
    after = common.machine_snapshot()
    (args.out / "raw-events.jsonl").write_bytes(raw_stdout)
    (args.out / "raw-stderr.txt").write_bytes(raw_stderr)
    build_bytes = common.sanitize(build_log.read_text(encoding="utf-8", errors="replace"), build).encode("utf-8")
    (args.out / "release-build-log.txt").write_bytes(build_bytes)
    common.save_json(args.out / "build-provenance.json", graph)
    executable_hash = digest(exe.read_bytes())
    (args.out / "measurement.exe").write_bytes(exe.read_bytes())
    (args.out / "executable.sha256").write_text(f"{executable_hash}  {exe.name}\n", encoding="ascii")

    build_record = None
    trials = []
    parse_error = None
    try:
        parsed = [data.parse_json(line) for line in raw_stdout.splitlines() if line]
        if parsed and parsed[0].get("schema") == "csl.opt12-build/1":
            build_record = parsed.pop(0)
        if not build_record:
            raise ValueError("embedded build identity event is missing")
        validate_build_identity(build_record, source_commit=head, build_owner=build_owner,
                                compiler=compiler, graph=graph, cache=cache,
                                system_processor=system_processor)
        validate_driver_fixture_events(parsed)
        trials = [row for row in parsed if row.get("schema") == "csl.opt12-cost-trial/1"]
        if len(trials) + len(SCENARIOS) != len(parsed):
            raise ValueError("driver emitted an unknown OPT-12 event")
        if any(row.get("schema") != "csl.opt12-cost-trial/1" for row in trials):
            raise ValueError("unknown trial schema")
        expected_count = args.repetitions * len(SCENARIOS) * 2
        if len(trials) != expected_count:
            raise ValueError(f"expected {expected_count} trial rows, got {len(trials)}")
        if any(row.get("status") != "verified" for row in trials):
            raise ValueError("a trial failed its independent numerical checks")
        for pair in range(args.repetitions):
            for scenario in SCENARIOS:
                members = [row for row in trials if row["pair"] == pair and row["scenario"] == scenario]
                expected_order = ["cold", "warm"] if pair % 2 == 0 else ["warm", "cold"]
                if len(members) != 2 or [row["mode"] for row in sorted(members, key=lambda row: row["order"])] != expected_order:
                    raise ValueError("paired trials are missing or the execution order did not alternate")
        if return_code or timed_out:
            raise ValueError(f"process incomplete: return_code={return_code}, timed_out={timed_out}")
    except (UnicodeDecodeError, ValueError, KeyError) as error:
        parse_error = f"{type(error).__name__}: {error}"

    fixtures = fixture_descriptions()
    metadata = {
        "schema": "csl.opt12-cost-report/1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": head, "adapter": "csl.lp.highs", "adapter_version": "1.1.0+highs.1.11.0",
        "native_solver": "HiGHS 1.11.0", "build_configuration": "Release",
        "build_log_sha256": digest(build_bytes), "executable_sha256": executable_hash,
        "executable_path": "Release/csl_opt12_warm_start_measure.exe",
        "host": {"system": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count()},
        "build_identity": build_record, "build_graph_sha256": digest(json.dumps(graph, sort_keys=True).encode()),
        "policy": {"native_threads": 1, "presolve": "off", "parallel": "off", "seed": 0,
                   "simplex_iteration_limit": None, "repetitions_per_side_per_case": args.repetitions,
                   "warmup": "one unreported source solve in a fresh workspace per warm trial",
                   "order": "alternating cold/warm within each pair",
                   "timing": "steady-clock wall around LPWorkspace.solve; native setup components separately timed"},
        "input_fixtures": fixtures,
        "process": {"return_code": return_code, "timed_out": timed_out, "stderr_sha256": digest(raw_stderr),
                    "stdout_sha256": digest(raw_stdout), "retained_trial_count": len(trials), "parse_error": parse_error},
        "system": common.public_load(before, after),
    }
    common.save_json(args.out / "records.json", {"metadata": metadata, "trials": trials})
    columns = ["scenario", "pair", "order", "mode", "status", "cache_state", "basis_accepted", "expected_objective", "objective", "wall_ns", "model_load_seconds", "basis_transfer_seconds", "solve_seconds", "simplex_iterations"]
    with (args.out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trials)
    (args.out / "measurement-command.txt").write_text(
        f"python scripts/reports/opt12_collect.py --exe build/dev-windows/Release/csl_opt12_warm_start_measure.exe --build build/dev-windows --source-commit {head} --repetitions {args.repetitions} --out <new-output-directory>\n",
        encoding="utf-8")
    print(json.dumps({"output": str(args.out), "record_count": len(trials), "return_code": return_code,
                      "timed_out": timed_out, "parse_error": parse_error}))
    return 1 if parse_error else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Admit a reviewed fixed-source GEO-07 report run; no rendering or publication."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET

SOURCE = "db7906cb33ca40da55e31b9bf6b21cf7ffcc1ee4"
TRIAL_SCHEMA = "csl.geo07-generator-trial/1"
RECORD_SCHEMA = "csl.geo07-generator-records/1"
EXPECTED = {
    "box_image": {"status": "passed", "center": [7.0], "generators": [2.0, 3.0],
                  "factor_ids": ["horizontal", "vertical"],
                  "physical_witnesses": [2, 7, 12, 8], "outside_points": [1, 13]},
    "shared_cancellation": {"status": "passed", "center": [0.0], "generators": [0.0],
                            "factor_ids": ["history.0"],
                            "physical_witnesses": [0, 0, 0], "outside_points": [-1, 1]},
    "constrained_sum": {"status": "passed", "center": [0.0, 0.0],
                        "generators": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
                        "factor_ids": ["u", "v", "w"],
                        "equalities": [1.0, -1.0, 0.0, 1.0, 0.0, 1.0],
                        "physical_witnesses": [[0, 0], [0, 0]],
                        "outside_points": [[0, 1], [0, -1]]},
}
ALLOWED = {
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/geo07/generator_driver.cpp",
    "scripts/reports/geo07/check_smoke.py", "scripts/reports/geo07/collect.py",
    "reports/algorithm-results/tooling/geo07/README.md",
    "tests/reporting/test_geo07_harness.py",
}
RELEASE_FLAGS = {
    "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
    "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG",
    "CMAKE_EXE_LINKER_FLAGS": "/machine:x64",
    "CMAKE_EXE_LINKER_FLAGS_RELEASE": "/INCREMENTAL:NO",
    "CMAKE_STATIC_LINKER_FLAGS": "/machine:x64",
    "CMAKE_STATIC_LINKER_FLAGS_RELEASE": "",
}
INTERVAL = ("fresh public GeneratorSet construction, public affine/dependent operations and "
            "independent-sum rejection control, factor lift, literal physical H, factor identity "
            "and coefficient checks, per-call nlohmann JSON result "
            "construction and assignment; excludes process startup, JSONL serialization, "
            "Python saved-row verification, persistence, rendering")


def matrix(rows: int, cols: int, values: list[float]) -> dict:
    return {"rows": rows, "cols": cols, "values": values}


def generator(id: str, center: list[float], generators: dict, factor_ids: list[str],
              equalities: dict, equality_values: list[float]) -> dict:
    return {"id": id, "center": center, "generators": generators,
            "factor_ids": factor_ids, "equalities": equalities,
            "equality_values": equality_values, "coordinate_labels": [],
            "factor_interval": [-1.0, 1.0]}


INPUTS = {
    "box_image": {
        "operation": "affine_image",
        "source": generator("report-box", [1.0, 2.0], matrix(2, 2, [2.0, 0.0, 0.0, 3.0]),
                            ["horizontal", "vertical"], matrix(0, 2, []), []),
        "affine_map": matrix(1, 2, [1.0, 1.0]), "offset": [4.0], "output_id": "report-image",
        "physical_h": {"inequalities": matrix(2, 1, [1.0, -1.0]), "upper": [12.0, -2.0],
                       "equalities": matrix(0, 1, []), "values": []},
        "feasible_factor_witnesses": [[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0], [-1.0, 1.0]],
        "inside_points": [[2.0], [7.0], [12.0], [8.0]],
        "outside_points": [[1.0], [13.0]],
        "infeasible_inside_factor": [2.0, -1.0],
    },
    "shared_cancellation": {
        "operation": "dependent_sum", "output_id": "report-cancelled",
        "left": generator("report-left", [0.0], matrix(1, 1, [1.0]),
                          ["history.0"], matrix(0, 1, []), []),
        "right": generator("report-right", [0.0], matrix(1, 1, [-1.0]),
                           ["history.0"], matrix(0, 1, []), []),
        "physical_h": {"inequalities": matrix(0, 1, []), "upper": [],
                       "equalities": matrix(1, 1, [1.0]), "values": [0.0]},
        "feasible_factor_witnesses": [[-1.0], [0.0], [1.0]],
        "inside_points": [[0.0], [0.0], [0.0]],
        "outside_points": [[-1.0], [1.0]],
        "independent_sum_rejected": True,
    },
    "constrained_sum": {
        "operation": "dependent_sum", "output_id": "report-constrained-sum",
        "left": generator("report-constrained-left", [0.0, 0.0],
                          matrix(2, 2, [1.0, 0.0, 0.0, 1.0]), ["u", "v"],
                          matrix(1, 2, [1.0, -1.0]), [0.0]),
        "right": generator("report-constrained-right", [0.0, 0.0],
                           matrix(2, 2, [-1.0, 0.0, 0.0, 1.0]), ["u", "w"],
                           matrix(1, 2, [1.0, 1.0]), [0.0]),
        "physical_h": {"inequalities": matrix(0, 2, []), "upper": [],
                       "equalities": matrix(2, 2, [1.0, 0.0, 0.0, 1.0]), "values": [0.0, 0.0]},
        "feasible_factor_witnesses": [[1.0, 1.0, -1.0], [0.0, 0.0, 0.0]],
        "inside_points": [[0.0, 0.0], [0.0, 0.0]],
        "outside_points": [[0.0, 1.0], [0.0, -1.0]],
        "left_only_factor": [1.0, 1.0, 0.0],
        "right_only_factor": [1.0, 0.0, -1.0],
        "infeasible_inside_factor": [1.0, 0.0, 0.0],
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def strict_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_raw(raw: bytes) -> list[dict]:
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("missing or unterminated JSONL")
    rows = []
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=strict_json_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
        if not isinstance(row, dict):
            raise ValueError("driver event is not an object")
        rows.append(row)
    return rows


def admit_description(raw: bytes) -> tuple[bytes, dict[str, str]]:
    description = parse_raw(raw)
    if len(description) != 1:
        raise ValueError("driver description count differs")
    value = description[0]
    if (value.get("schema") != "csl.geo07-generator-driver/1" or
            value.get("source_commit") != SOURCE or
            value.get("module") != "CSL::geometry_generators" or
            value.get("scalar") != "binary64" or
            value.get("fixtures") != list(EXPECTED) or
            value.get("timed_scope") != INTERVAL or
            json_bytes(value.get("inputs")) != json_bytes(INPUTS)):
        raise ValueError("driver source, timing scope, or authored input catalogue differs")
    payload = json_bytes(INPUTS)
    hashes = {name: sha(json_bytes(INPUTS[name])) for name in EXPECTED}
    return payload, hashes


def admit_raw(raw: bytes, *, repetitions: int, batch: int) -> tuple[list[dict], dict]:
    if type(repetitions) is not int or repetitions < 7 or type(batch) is not int or batch < 1:
        raise ValueError("accepted run needs at least seven repetitions and positive batch")
    rows = parse_raw(raw)
    names = list(EXPECTED)
    sequence = [(name, 0, True) for name in names]
    sequence += [(name, index, False) for index in range(repetitions)
                 for name in (names if index % 2 == 0 else names[::-1])]
    if len(rows) != len(sequence):
        raise ValueError("missing or extra trial event")
    for row, (name, index, warmup) in zip(rows, sequence):
        if (row.get("schema") != TRIAL_SCHEMA or row.get("fixture") != name or
                type(row.get("round")) is not int or row["round"] != index or
                row.get("warmup") is not warmup or type(row.get("batch")) is not int or
                row["batch"] != batch or type(row.get("checked_calls")) is not int or
                row["checked_calls"] != batch or row.get("status") != "passed" or
                row.get("error") is not None or json_bytes(row.get("result")) != json_bytes(EXPECTED[name]) or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 20_000_000):
            raise ValueError("trial identity, work count, interval, or literal oracle differs")
    summary = {}
    for name in names:
        values = [row["elapsed_ns"] for row in rows if row["fixture"] == name and not row["warmup"]]
        summary[name] = {"attempts": len(values), "successes": len(values), "failures": 0,
                         "median_batch_ns": statistics.median(values),
                         "min_batch_ns": min(values), "max_batch_ns": max(values)}
    return rows, summary


def save_capture(out: Path, stdout: bytes, stderr: bytes, code: int | None,
                 command: list[str], *, timed_out: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=False)
    for name, payload in (("trials.jsonl", stdout), ("driver.stderr", stderr)):
        with (out / name).open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    (out / "process-capture.json").write_bytes(json_bytes({
        "schema": "csl.geo07-process-capture/1", "command": command,
        "exit_code": code, "timed_out": timed_out,
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)}))


def reject(out: Path, reason: str) -> None:
    (out / "collection-status.json").write_bytes(json_bytes({
        "schema": "csl.geo07-collection-status/1", "publishable": False,
        "reason": reason}))


def manifest(out: Path, report_id: str) -> dict:
    files = {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir())
             if path.is_file() and path.name != "manifest.json"}
    return {"schema": "csl.geo07-manifest/1", "report_id": report_id, "files": files}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def cache_settings(text: str) -> dict[str, str]:
    settings = {}
    for line in text.splitlines():
        if line.startswith(("//", "#")) or "=" not in line or ":" not in line.split("=", 1)[0]:
            continue
        key, value = line.split("=", 1)
        name = key.split(":", 1)[0]
        if name in settings:
            raise ValueError("duplicate CMake cache setting: " + name)
        settings[name] = value
    return settings


def release_project(path: Path) -> dict:
    root = ET.parse(path).getroot()
    ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
    groups = [item for item in root.findall(ns + "ItemDefinitionGroup")
              if item.get("Condition") == "'$(Configuration)|$(Platform)'=='Release|x64'"]
    if len(groups) != 1:
        raise ValueError("unique x64 Release graph missing: " + path.name)
    def fields(name):
        node = groups[0].find(ns + name)
        return {child.tag.removeprefix(ns): (child.text or "") for child in node} if node is not None else {}
    return {"compile": fields("ClCompile"), "link": fields("Link"),
            "archive": fields("Lib"), "project_sha256": sha(path.read_bytes())}


def admit_release(settings: dict, targets: dict, build: Path) -> None:
    for name, expected in RELEASE_FLAGS.items():
        if settings.get(name) != expected:
            raise ValueError("unreviewed Release flag: " + name)
    if (settings.get("CSL_BUILD_GEO07_REPORT") != "ON" or
            settings.get("CMAKE_GENERATOR") != "Visual Studio 17 2022" or
            settings.get("CMAKE_GENERATOR_PLATFORM") != "x64"):
        raise ValueError("configured report target or generator differs")
    for name in ("driver", "generator_library"):
        compile_fields = targets[name]["compile"]
        if (compile_fields.get("Optimization") != "MaxSpeed" or
                compile_fields.get("InlineFunctionExpansion") != "AnySuitable" or
                compile_fields.get("LanguageStandard") != "stdcpp20" or
                compile_fields.get("RuntimeLibrary") != "MultiThreadedDLL" or
                "NDEBUG" not in compile_fields.get("PreprocessorDefinitions", "").split(";")):
            raise ValueError("unreviewed Release compile settings: " + name)
        options = compile_fields.get("AdditionalOptions", "")
        expected = ('%(AdditionalOptions) /external:I "' +
                    (build / "_deps" / "csl_json-src" / "include").as_posix() + '"')
        if options != (expected if name == "driver" else ""):
            raise ValueError("unreviewed Release additional options: " + name)
    link = targets["driver"]["link"]
    if (link.get("GenerateDebugInformation") != "false" or
            link.get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64" or
            "Release\\csl_geometry_generators.lib" not in link.get("AdditionalDependencies", "")):
        raise ValueError("driver Release link graph differs")
    if targets["generator_library"]["archive"].get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64":
        raise ValueError("generator library Release archive differs")


def collect(args) -> str:
    root = Path(__file__).resolve().parents[3]
    if not 7 <= args.repetitions <= 100 or not 1 <= args.batch <= 100000:
        raise ValueError("driver profile must have 7-100 rounds and 1-100000 calls per batch")
    if Path.cwd().resolve() != root:
        raise ValueError("run from harness source root")
    if not re.fullmatch(r"[0-9a-f]{40}", args.harness_commit or "") or git(root, "rev-parse", "HEAD") != args.harness_commit:
        raise ValueError("checkout differs from reviewed harness commit")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("harness source tree must be clean")
    changed = set(git(root, "diff", "--name-only", SOURCE, args.harness_commit).splitlines())
    if not changed <= ALLOWED:
        raise ValueError("algorithm source changed outside report harness: " + repr(sorted(changed - ALLOWED)))
    build = args.build_dir.resolve(strict=True)
    exe = args.exe.resolve(strict=True)
    out = args.out.resolve()
    if (build == root or not build.is_relative_to(root) or exe != build / "Release" / "csl_geo07_generator_report.exe" or
            not out.is_relative_to(build) or out.exists()):
        raise ValueError("build, Release executable, or new output destination differs")
    note = args.concurrent_work.read_text(encoding="utf-8").strip()
    if len(note) < 10 or "TODO" in note or "TBD" in note:
        raise ValueError("observed concurrent-work note required before measurement")
    if any(os.environ.get(name) for name in ("CL", "_CL_", "LINK")):
        raise ValueError("MSVC environment flag overrides are not admitted")
    cache_raw = (build / "CMakeCache.txt").read_bytes()
    settings = cache_settings(cache_raw.decode("utf-8"))
    if Path(settings.get("CSL_SOURCE_DIR", "")).resolve() != root:
        raise ValueError("configured source checkout differs")
    cmake = settings.get("CMAKE_COMMAND")
    if not cmake or not Path(cmake).is_file():
        raise ValueError("configured CMake command missing")
    build_command = [cmake, "--build", str(build), "--config", "Release", "--target",
                     "csl_geo07_generator_report", "--clean-first", "--verbose"]
    build_run = subprocess.run(build_command, cwd=root, capture_output=True, timeout=600)
    build_log = build / "geo07-final-build.stdout.log"
    build_stderr = build / "geo07-final-build.stderr.log"
    build_log.write_bytes(build_run.stdout)
    build_stderr.write_bytes(build_run.stderr)
    if build_run.returncode:
        raise ValueError("fresh Release build failed; logs retained in build directory")
    targets = {"driver": release_project(build / "csl_geo07_generator_report.vcxproj"),
               "generator_library": release_project(build / "csl_geometry_generators.vcxproj")}
    admit_release(settings, targets, build)
    describe = subprocess.run([str(exe), "--describe"], capture_output=True, timeout=30)
    if describe.returncode or describe.stderr:
        raise ValueError("driver description failed")
    input_bytes, input_hashes = admit_description(describe.stdout)
    command = [str(exe), "--measure", str(args.repetitions), "1", str(args.batch)]
    try:
        measured = subprocess.run(command, cwd=root, capture_output=True, timeout=600)
        stdout, stderr, code, timed_out = measured.stdout, measured.stderr, measured.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
    save_capture(out, stdout, stderr, code, command, timed_out=timed_out)
    (out / "driver-description.jsonl").write_bytes(describe.stdout)
    (out / "fixture-inputs.json").write_bytes(input_bytes)
    try:
        if code or stderr or timed_out:
            raise ValueError("driver failed, timed out, or wrote stderr")
        rows, summary = admit_raw(stdout, repetitions=args.repetitions, batch=args.batch)
        if git(root, "rev-parse", "HEAD") != args.harness_commit or git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("source changed during collection")
        compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
        if len(compiler_files) != 1:
            raise ValueError("configured compiler evidence unavailable")
        compiler_raw = compiler_files[0].read_bytes()
        compiler_text = compiler_raw.decode("utf-8")
        match = re.search(r'^set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)$', compiler_text, re.M)
        if not match:
            raise ValueError("compiler version evidence unavailable")
        provenance = {"schema": "csl.geo07-build-provenance/1", "source_commit": SOURCE,
                      "harness_commit": args.harness_commit, "configuration": "Release",
                      "settings": {name: settings[name] for name in RELEASE_FLAGS},
                      "targets": targets, "compiler_version": match.group(1),
                      "compiler_file_sha256": sha(compiler_raw), "cache_sha256": sha(cache_raw),
                      "exe_sha256": sha(exe.read_bytes()),
                      "build_stdout_sha256": sha(build_run.stdout), "build_stderr_sha256": sha(build_run.stderr)}
        (out / "build-provenance.json").write_bytes(json_bytes(provenance))
        (out / "build.stdout.log").write_bytes(build_run.stdout)
        (out / "build.stderr.log").write_bytes(build_run.stderr)
        record = {"schema": RECORD_SCHEMA, "source_commit": SOURCE,
                  "harness_commit": args.harness_commit,
                  "source_tree": git(root, "rev-parse", "HEAD^{tree}"),
                  "created_utc": datetime.now(timezone.utc).isoformat(),
                  "inputs": {"fixtures": INPUTS, "fixture_sha256": input_hashes,
                             "canonical_bytes_sha256": sha(input_bytes),
                             "driver_description_sha256": sha(describe.stdout),
                             "driver_sha256": sha((root / "benchmarks/reporting/geo07/generator_driver.cpp").read_bytes()),
                             "binary64": True, "representation_claim": "exact shared-factor algebra; binary64 numerical evaluation has no validated rounding enclosure"},
                  "timing": {"clock": "steady_clock", "unit": "ns", "scope": INTERVAL,
                             "warmup_rounds": 1, "measured_rounds": args.repetitions,
                             "batch_calls": args.batch, "order": "alternating fixtures",
                             "workspace": "fresh sets and lift each checked call; same process across rounds",
                             "minimum_admitted_batch_ns": 20_000_000,
                             "internal_phase_counters": "unavailable"},
                  "environment": {"os": platform.platform(), "processor": platform.processor(),
                                  "logical_processors": os.cpu_count(), "python": platform.python_version(),
                                  "requested_driver_workers": 1, "observed_native_threads": None,
                                  "observed_native_threads_reason": "no native thread counter in driver",
                                  "concurrent_work_note": note},
                  "process": {"exit_code": code, "stderr_sha256": sha(stderr),
                              "raw_sha256": sha(stdout)},
                  "build_provenance_sha256": sha((out / "build-provenance.json").read_bytes()),
                  "rows": rows, "summary": summary,
                  "performance_conclusion": "exploratory single-adapter batch observations; no comparator, speedup, or attributed limiter"}
        identity = sha(json_bytes(record))
        report_id = "geo07-" + identity[:16]
        record.update({"report_id": report_id, "payload_sha256": identity})
        (out / "records.json").write_bytes(json_bytes(record))
        (out / "collection-status.json").write_bytes(json_bytes({
            "schema": "csl.geo07-collection-status/1", "publishable": False,
            "reason": "scientific review, rendering, registration, and deployment pending",
            "accepted_for_report_review": True, "records_sha256": sha((out / "records.json").read_bytes())}))
        (out / "manifest.json").write_bytes(json_bytes(manifest(out, report_id)))
        return report_id
    except Exception as error:
        reject(out, str(error))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--concurrent-work", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--batch", type=int, default=1000)
    args = parser.parse_args()
    print(collect(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Admit a reviewed fixed-source GEO-07 registered-port run; no publication."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
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

SOURCE = "41b4b58f2ef982e75554519862afdd803e30f717"
SEAL_PATH = "scripts/reports/geo07_port/review-seal.json"
HOST_SCHEMA = "csl.geo07-port-host-observation/1"
DESCRIPTION_SCHEMA = "csl.geo07-port-driver/1"
TRIAL_SCHEMA = "csl.geo07-port-trial/1"
RECORD_SCHEMA = "csl.geo07-port-records/1"
EXPECTED = {
    "affine_box": {"status": "passed", "center": [7.0], "generators": [2.0, 3.0],
                   "factor_ids": ["horizontal", "vertical"],
                   "physical_witnesses": [2.0, 7.0, 12.0, 8.0],
                   "outside_points": [1.0, 13.0], "relation": "equivalent",
                   "support": "symbolic_argument", "error_bound": False,
                   "rejections": {"validated": "generators.assurance"}},
    "constrained_disjoint_sum": {
        "status": "passed", "center": [4.0], "generators": [1.0, 0.0, 0.0, 2.0],
        "factor_ids": ["u", "v", "p", "q"],
        "equalities": [1.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
        "physical_witnesses": [1.0, 4.0, 7.0], "outside_points": [0.0, 8.0],
        "relation": "equivalent", "support": "symbolic_argument", "error_bound": False,
        "rejections": {"shared_id": "generators.minkowski.factor_ids",
                       "intersection": "generators.operation"}},
    "finite_v": {"status": "passed", "vertices": [2.0, 6.0, 8.0, 12.0],
                 "rays": 0, "labels": ["x"], "outside_points": [1.0, 13.0],
                 "relation": "equivalent", "support": "symbolic_argument",
                 "error_bound": False,
                 "rejections": {"cap": "generators.convert.cap",
                                "constrained": "generators.convert.equalities",
                                "validated": "generators.assurance",
                                "h_output": "generators.convert.output"}},
}
ALLOWED = {
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/geo07_port/adapter_driver.cpp",
    "scripts/reports/geo07_port/check_smoke.py",
    "scripts/reports/geo07_port/collect.py",
    SEAL_PATH,
    "reports/algorithm-results/tooling/geo07_port/README.md",
    "tests/reporting/test_geo07_port_harness.py",
    "docs/superpowers/plans/2026-10-16-geo07-port-harness.md",
}
RELEASE_FLAGS = {
    "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
    "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG",
    "CMAKE_EXE_LINKER_FLAGS": "/machine:x64",
    "CMAKE_EXE_LINKER_FLAGS_RELEASE": "/INCREMENTAL:NO",
    "CMAKE_STATIC_LINKER_FLAGS": "/machine:x64",
    "CMAKE_STATIC_LINKER_FLAGS_RELEASE": "",
}
INTERVAL = ("fresh public generator handles and prepared GeometryPort/ConversionPort "
            "registration, admission, workspace execution, literal physical H/V and factor "
            "checks, scoped rejection controls, per-call nlohmann JSON result construction "
            "and assignment; excludes process startup, JSONL serialization, Python saved-row "
            "verification, persistence, rendering")


def matrix(rows: int, cols: int, values: list[float]) -> dict:
    return {"rows": rows, "cols": cols, "values": values}


def generator(id: str, center: list[float], generators: dict, factor_ids: list[str],
              equalities: dict, equality_values: list[float], labels=None) -> dict:
    return {"id": id, "center": center, "generators": generators,
            "factor_ids": factor_ids, "equalities": equalities,
            "equality_values": equality_values, "coordinate_labels": labels or [],
            "factor_interval": [-1.0, 1.0]}


def h(upper: float, lower: float) -> dict:
    return {"inequalities": matrix(2, 1, [1.0, -1.0]),
            "upper": [upper, -lower], "equalities": matrix(0, 1, []), "values": []}


def public_request(request_id: str) -> dict:
    return {"problem_id": "geo07-port", "request_id": request_id,
            "assurance": "numerical", "prepared_scalar": "binary64",
            "prepared_output_relation": "equivalent"}


INPUTS = {
    "affine_box": {
        "operation": "affine_image", "registration": "csl.geometry.generators.operations",
        "public_request": public_request("affine-box"),
        "source": generator("port-box", [1.0, 2.0], matrix(2, 2, [2.0, 0.0, 0.0, 3.0]),
                            ["horizontal", "vertical"], matrix(0, 2, []), []),
        "affine_map": matrix(1, 2, [1.0, 1.0]), "offset": [4.0],
        "output_id": "port-box-image", "output_representation": "csl.zonotope",
        "physical_h": h(12.0, 2.0),
        "feasible_factor_witnesses": [[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0], [-1.0, 1.0]],
        "inside_points": [[2.0], [7.0], [12.0], [8.0]],
        "outside_points": [[1.0], [13.0]],
        "rejection_controls": {"validated_assurance": True}},
    "constrained_disjoint_sum": {
        "operation": "minkowski_sum", "registration": "csl.geometry.generators.operations",
        "public_request": public_request("constrained-sum"),
        "left": generator("port-sum-left", [1.0], matrix(1, 2, [1.0, 0.0]),
                          ["u", "v"], matrix(1, 2, [1.0, -1.0]), [0.0]),
        "right": generator("port-sum-right", [3.0], matrix(1, 2, [0.0, 2.0]),
                           ["p", "q"], matrix(1, 2, [1.0, 1.0]), [0.0]),
        "output_id": "port-constrained-sum",
        "output_representation": "csl.constrained-zonotope",
        "physical_h": h(7.0, 1.0),
        "feasible_factor_witnesses": [[-1.0, -1.0, 1.0, -1.0],
                                      [0.0, 0.0, 0.0, 0.0],
                                      [1.0, 1.0, -1.0, 1.0]],
        "inside_points": [[1.0], [4.0], [7.0]],
        "outside_points": [[0.0], [8.0]],
        "rejection_controls": {"shared_ids": "left used twice", "intersection": True}},
    "finite_v": {
        "operation": "conversion", "registration": "csl.geometry.generators.v-conversion",
        "public_request": public_request("finite-v"),
        "source": generator("port-v-source", [7.0], matrix(1, 2, [2.0, 3.0]),
                            ["a", "b"], matrix(0, 2, []), [], ["x"]),
        "output_id": "port-v", "output_representation": "csl.polyhedron.v",
        "vertex_cap": 4, "physical_h": h(12.0, 2.0),
        "vertices": [[2.0], [6.0], [8.0], [12.0]],
        "outside_points": [[1.0], [13.0]],
        "rejection_controls": {
            "cap": 3,
            "constrained": generator("port-constrained-control", [0.0],
                                     matrix(1, 1, [1.0]), ["r"],
                                     matrix(1, 1, [1.0]), [0.0]),
            "validated_assurance": True, "h_output": "csl.polyhedron.h"}},
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
    if (value.get("schema") != DESCRIPTION_SCHEMA or
            value.get("source_commit") != SOURCE or
            value.get("module") != "CSL::generator_adapter" or
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
                 command: list[str], *, timed_out: bool = False,
                 collection_start_utc: str | None = None,
                 collection_end_utc: str | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (("trials.jsonl", stdout), ("driver.stderr", stderr)):
        with (out / name).open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    (out / "process-capture.json").write_bytes(json_bytes({
        "schema": "csl.geo07-port-process-capture/1", "command": command,
        "exit_code": code, "timed_out": timed_out,
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
        "host_observation_sha256": sha((out / "host-observation.json").read_bytes()),
        "collection_start_utc": collection_start_utc,
        "collection_end_utc": collection_end_utc}))


def save_host_observation(out: Path, raw: bytes, stderr: bytes = b"") -> None:
    out.mkdir(parents=True, exist_ok=False)
    (out / "host-observation.json").write_bytes(raw)
    (out / "host-observation.stderr").write_bytes(stderr)


def reject(out: Path, reason: str) -> None:
    (out / "collection-status.json").write_bytes(json_bytes({
        "schema": "csl.geo07-port-collection-status/1", "publishable": False,
        "reason": reason}))


def manifest(out: Path, report_id: str) -> dict:
    files = {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir())
             if path.is_file() and path.name != "manifest.json"}
    return {"schema": "csl.geo07-port-manifest/1", "report_id": report_id, "files": files}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def admit_changed_paths(changed: set[str]) -> None:
    if not changed <= ALLOWED:
        raise ValueError("algorithm source changed outside report harness: " +
                         repr(sorted(changed - ALLOWED)))


def admit_reviewed_head(actual: str, claimed: str, parent: str, parent_tree: str,
                        last_changed: set[str], seal: dict) -> None:
    if (not all(re.fullmatch(r"[0-9a-f]{40}", value or "")
                for value in (actual, claimed, parent, parent_tree)) or
            actual != claimed or actual == parent or
            last_changed != {SEAL_PATH} or
            seal != {"schema": "csl.geo07-port-review-seal/1", "source_commit": SOURCE,
                     "reviewed_code_commit": parent, "reviewed_code_tree": parent_tree}):
        raise ValueError("actual HEAD is not the metadata-only child of reviewed harness code")


def admit_checkout(root: Path, claimed: str) -> tuple[str, str, bytes]:
    seal_raw = (root / SEAL_PATH).read_bytes()
    seal = json.loads(seal_raw, object_pairs_hook=strict_json_pairs)
    actual_head = git(root, "rev-parse", "HEAD")
    parent_head = git(root, "rev-parse", "HEAD^")
    admit_reviewed_head(actual_head, claimed, parent_head,
                        git(root, "rev-parse", parent_head + "^{tree}"),
                        set(git(root, "diff", "--name-only", "HEAD^", "HEAD").splitlines()), seal)
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("harness source tree must be clean")
    return actual_head, parent_head, seal_raw


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def host_observation() -> tuple[bytes, bytes, int]:
    # Run only after the final clean Release build; the collector owns the observation.
    script = r'''$cpu = @(Get-CimInstance Win32_Processor)
$jobs = @(Get-Process cmake,MSBuild,cl -ErrorAction SilentlyContinue)
[pscustomobject]@{
  schema = 'csl.geo07-port-host-observation/1'
  observed_utc = [DateTimeOffset]::UtcNow.ToString('o')
  cpu_load_percent = [math]::Round(($cpu | Measure-Object LoadPercentage -Average).Average)
  logical_processors = [int](($cpu | Measure-Object NumberOfLogicalProcessors -Sum).Sum)
  build_processes = [pscustomobject]@{
    cmake = @($jobs | Where-Object ProcessName -EQ 'cmake').Count
    MSBuild = @($jobs | Where-Object ProcessName -EQ 'MSBuild').Count
    cl = @($jobs | Where-Object ProcessName -EQ 'cl').Count
  }
} | ConvertTo-Json -Compress -Depth 3'''
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, timeout=30)
    return result.stdout, result.stderr, result.returncode


def admit_host_observation(raw: bytes, build_end: datetime, collection_start: datetime) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=strict_json_pairs)
        observed = datetime.fromisoformat(value["observed_utc"])
    except (ValueError, UnicodeError, KeyError, TypeError) as error:
        raise ValueError("structured host observation unavailable") from error
    if (not isinstance(value, dict) or set(value) != {"schema", "observed_utc", "cpu_load_percent",
                                                      "logical_processors", "build_processes"} or
            value["schema"] != HOST_SCHEMA or observed.tzinfo is None or
            observed.utcoffset() != timedelta(0) or
            not build_end < observed <= collection_start or
            collection_start - observed > timedelta(seconds=30) or
            type(value["cpu_load_percent"]) not in (int, float) or
            not 0 <= value["cpu_load_percent"] <= 25 or
            type(value["logical_processors"]) is not int or value["logical_processors"] < 1 or
            not isinstance(value["build_processes"], dict) or
            set(value["build_processes"]) != {"cmake", "MSBuild", "cl"} or
            any(type(count) is not int or count != 0 for count in value["build_processes"].values())):
        raise ValueError("host observation is stale, busy, or malformed")
    return value


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


def compiler_version(raw: bytes) -> str:
    # CMake writes CRLF on this MSVC host; keep raw bytes for the evidence hash.
    matches = [match.group(1) for line in raw.decode("utf-8").splitlines()
               if (match := re.fullmatch(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', line))]
    if len(matches) != 1:
        raise ValueError("unique CMake compiler version evidence unavailable")
    return matches[0]


def admit_release(settings: dict, targets: dict, build: Path) -> None:
    for name, expected in RELEASE_FLAGS.items():
        if settings.get(name) != expected:
            raise ValueError("unreviewed Release flag: " + name)
    if (settings.get("CSL_BUILD_GEO07_PORT_REPORT") != "ON" or
            settings.get("CSL_ENABLE_HIGHS") != "OFF" or
            settings.get("CSL_ENABLE_QHULL") != "OFF" or
            settings.get("BUILD_TESTING") != "OFF" or
            settings.get("CMAKE_GENERATOR") != "Visual Studio 17 2022" or
            settings.get("CMAKE_GENERATOR_PLATFORM") != "x64"):
        raise ValueError("configured report target or generator differs")
    for name in ("driver", "adapter_library", "generator_library"):
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
    dependencies = link.get("AdditionalDependencies", "").split(";")
    if (link.get("GenerateDebugInformation") != "false" or
            link.get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64" or
            "Release\\csl_generator_adapter.lib" not in dependencies or
            "Release\\csl_geometry_generators.lib" not in dependencies):
        raise ValueError("driver Release link graph differs")
    for name in ("adapter_library", "generator_library"):
        if targets[name]["archive"].get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64":
            raise ValueError("unreviewed Release archive: " + name)


def collect(args) -> str:
    root = Path(__file__).resolve().parents[3]
    if not 7 <= args.repetitions <= 100 or not 1 <= args.batch <= 100000:
        raise ValueError("driver profile must have 7-100 rounds and 1-100000 calls per batch")
    if Path.cwd().resolve() != root:
        raise ValueError("run from harness source root")
    actual_head, parent_head, seal_raw = admit_checkout(root, args.harness_commit)
    admit_changed_paths(set(git(root, "diff", "--name-only", SOURCE, actual_head).splitlines()))
    build = args.build_dir.resolve(strict=True)
    exe = args.exe.resolve(strict=True)
    out = args.out.resolve()
    if (build == root or not build.is_relative_to(root) or exe != build / "Release" / "csl_geo07_port_report.exe" or
            not out.is_relative_to(build) or out.exists()):
        raise ValueError("build, Release executable, or new output destination differs")
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
                     "csl_geo07_port_report", "--clean-first", "--verbose"]
    build_run = subprocess.run(build_command, cwd=root, capture_output=True, timeout=600)
    build_log = build / "geo07-port-final-build.stdout.log"
    build_stderr = build / "geo07-port-final-build.stderr.log"
    build_log.write_bytes(build_run.stdout)
    build_stderr.write_bytes(build_run.stderr)
    if build_run.returncode:
        raise ValueError("fresh Release build failed; logs retained in build directory")
    build_end = utc_now()
    targets = {"driver": release_project(build / "csl_geo07_port_report.vcxproj"),
               "adapter_library": release_project(build / "csl_generator_adapter.vcxproj"),
               "generator_library": release_project(build / "csl_geometry_generators.vcxproj")}
    admit_release(settings, targets, build)
    describe = subprocess.run([str(exe), "--describe"], capture_output=True, timeout=30)
    if describe.returncode or describe.stderr:
        raise ValueError("driver description failed")
    input_bytes, input_hashes = admit_description(describe.stdout)
    command = [str(exe), "--measure", str(args.repetitions), "1", str(args.batch)]
    host_raw, host_stderr, host_code = host_observation()
    save_host_observation(out, host_raw, host_stderr)
    (out / "review-seal.json").write_bytes(seal_raw)
    collection_start = utc_now()
    try:
        if host_code or host_stderr:
            raise ValueError("host observation command failed")
        note = admit_host_observation(host_raw, build_end, collection_start)
    except Exception as error:
        reject(out, str(error))
        raise
    try:
        measured = subprocess.run(command, cwd=root, capture_output=True, timeout=600)
        stdout, stderr, code, timed_out = measured.stdout, measured.stderr, measured.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
    collection_end = utc_now()
    save_capture(out, stdout, stderr, code, command, timed_out=timed_out,
                 collection_start_utc=collection_start.isoformat(),
                 collection_end_utc=collection_end.isoformat())
    (out / "driver-description.jsonl").write_bytes(describe.stdout)
    (out / "fixture-inputs.json").write_bytes(input_bytes)
    try:
        if code or stderr or timed_out:
            raise ValueError("driver failed, timed out, or wrote stderr")
        rows, summary = admit_raw(stdout, repetitions=args.repetitions, batch=args.batch)
        if git(root, "rev-parse", "HEAD") != actual_head or git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("source changed during collection")
        compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
        if len(compiler_files) != 1:
            raise ValueError("configured compiler evidence unavailable")
        compiler_raw = compiler_files[0].read_bytes()
        provenance = {"schema": "csl.geo07-port-build-provenance/1", "source_commit": SOURCE,
                      "harness_commit": actual_head, "review_seal_sha256": sha(seal_raw),
                      "configuration": "Release",
                      "settings": {name: settings[name] for name in RELEASE_FLAGS},
                      "targets": targets, "compiler_version": compiler_version(compiler_raw),
                      "compiler_file_sha256": sha(compiler_raw), "cache_sha256": sha(cache_raw),
                      "exe_sha256": sha(exe.read_bytes()),
                      "build_stdout_sha256": sha(build_run.stdout), "build_stderr_sha256": sha(build_run.stderr)}
        (out / "build-provenance.json").write_bytes(json_bytes(provenance))
        (out / "build.stdout.log").write_bytes(build_run.stdout)
        (out / "build.stderr.log").write_bytes(build_run.stderr)
        record = {"schema": RECORD_SCHEMA, "source_commit": SOURCE,
                  "harness_commit": actual_head,
                  "reviewed_code_commit": parent_head,
                  "review_seal_sha256": sha(seal_raw),
                  "source_tree": git(root, "rev-parse", SOURCE + "^{tree}"),
                  "harness_tree": git(root, "rev-parse", "HEAD^{tree}"),
                  "created_utc": utc_now().isoformat(),
                  "collection_start_utc": collection_start.isoformat(),
                  "collection_end_utc": collection_end.isoformat(),
                  "inputs": {"fixtures": INPUTS, "fixture_sha256": input_hashes,
                             "canonical_bytes_sha256": sha(input_bytes),
                             "driver_description_sha256": sha(describe.stdout),
                             "driver_sha256": sha((root / "benchmarks/reporting/geo07_port/adapter_driver.cpp").read_bytes()),
                             "binary64": True, "representation_claim": "equivalent real-set affine, disjoint-ID sum and bounded V algebra; binary64 evaluation has no validated rounding enclosure"},
                  "timing": {"clock": "steady_clock", "unit": "ns", "scope": INTERVAL,
                             "warmup_rounds": 1, "measured_rounds": args.repetitions,
                             "batch_calls": args.batch, "order": "alternating fixtures",
                             "workspace": "fresh sets, registration, preparation and workspace each checked call; same process across rounds",
                             "minimum_admitted_batch_ns": 20_000_000,
                             "internal_phase_counters": "unavailable"},
                  "environment": {"os": platform.platform(), "processor": platform.processor(),
                                  "logical_processors": os.cpu_count(), "python": platform.python_version(),
                                  "requested_driver_workers": 1, "observed_native_threads": None,
                                  "observed_native_threads_reason": "no native thread counter in driver",
                                  "host_observation": note,
                                  "host_observation_sha256": sha(host_raw)},
                  "process": {"exit_code": code, "stderr_sha256": sha(stderr),
                              "raw_sha256": sha(stdout)},
                  "build_provenance_sha256": sha((out / "build-provenance.json").read_bytes()),
                  "rows": rows, "summary": summary,
                  "performance_conclusion": "exploratory single-adapter batch observations; no comparator, speedup, or attributed limiter"}
        identity = sha(json_bytes(record))
        report_id = "geo07-port-" + identity[:16]
        record.update({"report_id": report_id, "payload_sha256": identity})
        (out / "records.json").write_bytes(json_bytes(record))
        (out / "collection-status.json").write_bytes(json_bytes({
            "schema": "csl.geo07-port-collection-status/1", "publishable": False,
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
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--batch", type=int, default=1000)
    args = parser.parse_args()
    print(collect(args))


if __name__ == "__main__":
    main()

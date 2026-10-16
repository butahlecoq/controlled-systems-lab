#!/usr/bin/env python3
"""Fixed-source registered dependent-sum preflight and reviewed collection."""
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
import xml.etree.ElementTree as ET

SOURCE = "5411e37ad456f0d5b3bf775130f149622ef5ebfa"
SEAL_PATH = "scripts/reports/geo07_dependent/review-seal.json"
SCHEMA = "csl.geo07-dependent"
DESCRIPTION_SCHEMA = SCHEMA + "-driver/1"
TRIAL_SCHEMA = SCHEMA + "-trial/1"
INTERVAL = ("fresh native generator handles and prepared registered GeometryPort, "
            "DependentSum admission and workspace execution, literal factor and physical H "
            "checks, independent Minkowski rejection, evidence verification and per-call JSON "
            "result assignment; excludes process startup, JSONL serialization, Python "
            "saved-row validation, persistence and rendering")
ALLOWED = {
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/geo07_dependent/driver.cpp",
    "scripts/reports/geo07_dependent/collect.py",
    "scripts/reports/geo07_dependent/check_smoke.py",
    "reports/algorithm-results/tooling/geo07_dependent/README.md",
    "tests/reporting/test_geo07_dependent_harness.py", SEAL_PATH,
}
RELEASE_FLAGS = {
    "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
    "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG",
    "CMAKE_EXE_LINKER_FLAGS": "/machine:x64",
    "CMAKE_EXE_LINKER_FLAGS_RELEASE": "/INCREMENTAL:NO",
    "CMAKE_STATIC_LINKER_FLAGS": "/machine:x64",
    "CMAKE_STATIC_LINKER_FLAGS_RELEASE": "",
}


def matrix(rows: int, cols: int, values: list[float]) -> dict:
    return {"rows": rows, "cols": cols, "values": values}


def generator(name: str, center: list[float], columns: dict, factors: list[str],
              equalities: dict, values: list[float]) -> dict:
    return {"id": name, "center": center, "generators": columns, "factor_ids": factors,
            "equalities": equalities, "equality_values": values,
            "coordinate_labels": [], "factor_interval": [-1.0, 1.0]}


def request(name: str) -> dict:
    return {"problem_id": "geo07-dependent", "request_id": name,
            "assurance": "numerical", "prepared_scalar": "binary64",
            "prepared_output_relation": "equivalent", "registration_version": "1.1.0"}


def point_h(dimension: int) -> dict:
    identity = [float(row == col) for row in range(dimension) for col in range(dimension)]
    return {"inequalities": matrix(0, dimension, []), "upper": [],
            "equalities": matrix(dimension, dimension, identity),
            "values": [0.0] * dimension}


INPUTS = {
    "shared_cancellation": {
        "operation": "dependent_sum", "registration": "csl.geometry.generators.operations",
        "public_request": request("shared-cancellation"),
        "left": generator("dependent-cancel-left", [0.0], matrix(1, 1, [1.0]),
                          ["history.0"], matrix(0, 1, []), []),
        "right": generator("dependent-cancel-right", [0.0], matrix(1, 1, [-1.0]),
                           ["history.0"], matrix(0, 1, []), []),
        "output_id": "dependent-cancel-origin", "output_representation": "csl.zonotope",
        "physical_h": point_h(1),
        "feasible_factor_witnesses": [[-1.0], [0.0], [1.0]],
        "inside_points": [[0.0], [0.0], [0.0]],
        "outside_points": [[-1.0], [1.0]],
        "rejection_controls": {"independent_shared_ids": True}},
    "constrained_shared": {
        "operation": "dependent_sum", "registration": "csl.geometry.generators.operations",
        "public_request": request("constrained-shared"),
        "left": generator("dependent-constrained-left", [0.0, 0.0],
                          matrix(2, 2, [1.0, 0.0, 0.0, 1.0]), ["u", "v"],
                          matrix(1, 2, [1.0, -1.0]), [0.0]),
        "right": generator("dependent-constrained-right", [0.0, 0.0],
                           matrix(2, 2, [-1.0, 0.0, 0.0, 1.0]), ["u", "w"],
                           matrix(1, 2, [1.0, 1.0]), [0.0]),
        "output_id": "dependent-constrained-origin",
        "output_representation": "csl.constrained-zonotope",
        "physical_h": point_h(2),
        "feasible_factor_witnesses": [[-1.0, -1.0, 1.0], [0.0, 0.0, 0.0],
                                      [1.0, 1.0, -1.0]],
        "inside_points": [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        "outside_points": [[0.0, 1.0], [1.0, 0.0]],
        "rejection_controls": {"independent_shared_ids": True}},
}
EXPECTED = {
    "shared_cancellation": {
        "status": "passed", "center": [0.0], "generators": [0.0],
        "factor_ids": ["history.0"], "equalities": [],
        "physical_witnesses": [[0.0], [0.0], [0.0]],
        "outside_points": [[-1.0], [1.0]], "relation": "equivalent",
        "support": "symbolic_argument", "error_bound": False,
        "rejections": {"independent_shared_ids": "generators.minkowski.factor_ids"}},
    "constrained_shared": {
        "status": "passed", "center": [0.0, 0.0],
        "generators": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
        "factor_ids": ["u", "v", "w"],
        "equalities": [1.0, -1.0, 0.0, 1.0, 0.0, 1.0],
        "physical_witnesses": [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        "outside_points": [[0.0, 1.0], [1.0, 0.0]], "relation": "equivalent",
        "support": "symbolic_argument", "error_bound": False,
        "rejections": {"independent_shared_ids": "generators.minkowski.factor_ids"}},
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def parse_jsonl(raw: bytes) -> list[dict]:
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("empty or unterminated JSONL")
    values = []
    for line in raw.splitlines():
        item = json.loads(line, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if not isinstance(item, dict):
            raise ValueError("JSONL event is not an object")
        values.append(item)
    return values


def admit_description(raw: bytes) -> tuple[bytes, dict[str, str]]:
    rows = parse_jsonl(raw)
    if len(rows) != 1:
        raise ValueError("driver description count differs")
    value = rows[0]
    if (value.get("schema") != DESCRIPTION_SCHEMA or value.get("source_commit") != SOURCE or
            value.get("module") != "CSL::generator_adapter" or
            value.get("registration") != "csl.geometry.generators.operations@1.1.0" or
            value.get("scalar") != "binary64" or
            value.get("fixtures") != list(EXPECTED) or value.get("timed_scope") != INTERVAL or
            json_bytes(value.get("inputs")) != json_bytes(INPUTS)):
        raise ValueError("driver identity, timing scope, or input catalogue differs")
    payload = json_bytes(INPUTS)
    return payload, {name: sha(json_bytes(INPUTS[name])) for name in EXPECTED}


def admit_rows(raw: bytes, *, repetitions: int, batch: int, smoke: bool = False) -> tuple[list[dict], dict]:
    if not smoke and (type(repetitions) is not int or repetitions < 7 or
                      type(batch) is not int or batch < 1):
        raise ValueError("accepted collection requires seven rounds and positive batch")
    names = list(EXPECTED)
    sequence = [(name, 0, False) for name in names] if smoke else (
        [(name, 0, True) for name in names] +
        [(name, index, False) for index in range(repetitions)
         for name in (names if index % 2 == 0 else names[::-1])])
    rows = parse_jsonl(raw)
    if len(rows) != len(sequence):
        raise ValueError("trial row count differs")
    for row, (name, index, warmup) in zip(rows, sequence):
        if (row.get("schema") != TRIAL_SCHEMA or row.get("fixture") != name or
                type(row.get("round")) is not int or row["round"] != index or
                row.get("warmup") is not warmup or type(row.get("batch")) is not int or
                row["batch"] != batch or type(row.get("checked_calls")) is not int or
                row["checked_calls"] != batch or row.get("status") != "passed" or
                row.get("error") is not None or
                json_bytes(row.get("result")) != json_bytes(EXPECTED[name]) or
                type(row.get("elapsed_ns")) is not int or
                row["elapsed_ns"] < (0 if smoke else 20_000_000)):
            raise ValueError("trial identity, literal result, work count, or interval differs")
    summary = {}
    if not smoke:
        for name in names:
            elapsed = [row["elapsed_ns"] for row in rows if row["fixture"] == name and not row["warmup"]]
            summary[name] = {"attempts": len(elapsed), "successes": len(elapsed),
                             "failures": 0, "median_batch_ns": statistics.median(elapsed),
                             "min_batch_ns": min(elapsed), "max_batch_ns": max(elapsed)}
    return rows, summary


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def admit_source(root: Path, claimed: str, *, sealed: bool) -> dict:
    head = git(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", claimed) or head != claimed:
        raise ValueError("claimed harness commit is not checkout HEAD")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("harness source checkout is dirty")
    if subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, head],
                      cwd=root, check=False).returncode:
        raise ValueError("frozen algorithm source is not an ancestor")
    changed = set(git(root, "diff", "--name-only", SOURCE, head).splitlines())
    if not changed <= ALLOWED:
        raise ValueError("algorithm source changed outside harness: " + repr(sorted(changed - ALLOWED)))
    identity = {"source_commit": SOURCE, "source_tree": git(root, "rev-parse", SOURCE + "^{tree}"),
                "harness_commit": head, "harness_tree": git(root, "rev-parse", "HEAD^{tree}")}
    if sealed:
        parent = git(root, "rev-parse", "HEAD^")
        raw = (root / SEAL_PATH).read_bytes()
        seal = json.loads(raw, object_pairs_hook=unique_pairs)
        if (set(git(root, "diff", "--name-only", "HEAD^", "HEAD").splitlines()) != {SEAL_PATH} or
                seal != {"schema": SCHEMA + "-review-seal/1", "source_commit": SOURCE,
                         "reviewed_code_commit": parent,
                         "reviewed_code_tree": git(root, "rev-parse", parent + "^{tree}")}):
            raise ValueError("HEAD is not the metadata-only child of reviewed harness code")
        identity.update({"reviewed_code_commit": parent, "review_seal_sha256": sha(raw)})
    return identity


def cache_settings(raw: bytes) -> dict[str, str]:
    settings = {}
    for line in raw.decode("utf-8").splitlines():
        if line.startswith(("//", "#")) or "=" not in line or ":" not in line.split("=", 1)[0]:
            continue
        key, value = line.split("=", 1)
        name = key.split(":", 1)[0]
        if name in settings:
            raise ValueError("duplicate CMake cache setting")
        settings[name] = value
    return settings


def release_project(path: Path) -> dict:
    root = ET.parse(path).getroot()
    ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
    groups = [node for node in root.findall(ns + "ItemDefinitionGroup")
              if node.get("Condition") == "'$(Configuration)|$(Platform)'=='Release|x64'"]
    if len(groups) != 1:
        raise ValueError("unique MSVC x64 Release project missing: " + path.name)
    def fields(name):
        node = groups[0].find(ns + name)
        return {child.tag.removeprefix(ns): (child.text or "") for child in node} if node is not None else {}
    return {"compile": fields("ClCompile"), "link": fields("Link"),
            "archive": fields("Lib"), "project_sha256": sha(path.read_bytes())}


def admit_release(settings: dict, projects: dict, build: Path) -> None:
    for name, expected in RELEASE_FLAGS.items():
        if settings.get(name) != expected:
            raise ValueError("unreviewed Release flag: " + name)
    if (settings.get("CSL_BUILD_GEO07_DEPENDENT_REPORT") != "ON" or
            settings.get("CSL_ENABLE_HIGHS") != "OFF" or
            settings.get("CSL_ENABLE_QHULL") != "OFF" or
            settings.get("CMAKE_GENERATOR") != "Visual Studio 17 2022" or
            settings.get("CMAKE_GENERATOR_PLATFORM") != "x64"):
        raise ValueError("configured report target or platform differs")
    for name in ("driver", "adapter_library", "generator_library"):
        compile_fields = projects[name]["compile"]
        if (compile_fields.get("Optimization") != "MaxSpeed" or
                compile_fields.get("InlineFunctionExpansion") != "AnySuitable" or
                compile_fields.get("LanguageStandard") != "stdcpp20" or
                compile_fields.get("RuntimeLibrary") != "MultiThreadedDLL" or
                "NDEBUG" not in compile_fields.get("PreprocessorDefinitions", "").split(";")):
            raise ValueError("unreviewed Release compile settings: " + name)
    links = projects["driver"]["link"].get("AdditionalDependencies", "").split(";")
    if ("Release\\csl_generator_adapter.lib" not in links or
            "Release\\csl_geometry_generators.lib" not in links):
        raise ValueError("registered adapter or native generator missing from link graph")
    for name in ("adapter_library", "generator_library"):
        if projects[name]["archive"].get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64":
            raise ValueError("unreviewed Release archive: " + name)
    expected = ('%(AdditionalOptions) /external:I "' +
                (build / "_deps" / "csl_json-src" / "include").as_posix() + '"')
    if projects["driver"]["compile"].get("AdditionalOptions") != expected:
        raise ValueError("driver JSON header graph differs")


def captured(command: list[str], root: Path, out: Path, stem: str, timeout: int) -> tuple[bytes, bytes, int | None, bool]:
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, timeout=timeout)
        stdout, stderr, code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
    out.mkdir(parents=True, exist_ok=True)
    (out / (stem + ".stdout")).write_bytes(stdout)
    (out / (stem + ".stderr")).write_bytes(stderr)
    (out / (stem + ".capture.json")).write_bytes(json_bytes({
        "command": command, "exit_code": code, "timed_out": timed_out,
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)}))
    return stdout, stderr, code, timed_out


def host_observation() -> tuple[bytes, bytes, int | None, bool]:
    script = r'''$cpu = @(Get-CimInstance Win32_Processor)
$jobs = @(Get-Process cmake,MSBuild,cl -ErrorAction SilentlyContinue)
[pscustomobject]@{
  schema = 'csl.geo07-dependent-host/1'
  observed_utc = [DateTimeOffset]::UtcNow.ToString('o')
  cpu_load_percent = [math]::Round(($cpu | Measure-Object LoadPercentage -Average).Average)
  logical_processors = [int](($cpu | Measure-Object NumberOfLogicalProcessors -Sum).Sum)
  build_processes = [pscustomobject]@{
    cmake = @($jobs | Where-Object ProcessName -EQ 'cmake').Count
    MSBuild = @($jobs | Where-Object ProcessName -EQ 'MSBuild').Count
    cl = @($jobs | Where-Object ProcessName -EQ 'cl').Count
  }
} | ConvertTo-Json -Compress -Depth 3'''
    try:
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                   capture_output=True, timeout=30)
        return completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired as error:
        return error.stdout or b"", error.stderr or b"", None, True


def admit_host(raw: bytes, build_end: datetime, start: datetime) -> dict:
    value = json.loads(raw, object_pairs_hook=unique_pairs)
    observed = datetime.fromisoformat(value["observed_utc"])
    if (value.get("schema") != SCHEMA + "-host/1" or observed.tzinfo is None or
            observed.utcoffset() != timedelta(0) or not build_end < observed <= start or
            start - observed > timedelta(seconds=30) or
            type(value.get("cpu_load_percent")) not in (int, float) or
            not 0 <= value["cpu_load_percent"] <= 25 or
            type(value.get("logical_processors")) is not int or value["logical_processors"] < 1 or
            not isinstance(value.get("build_processes"), dict) or
            set(value["build_processes"]) != {"cmake", "MSBuild", "cl"} or
            any(type(count) is not int or count != 0 for count in value["build_processes"].values())):
        raise ValueError("host observation is stale, busy, or malformed")
    return value


def manifest(out: Path, report_id: str) -> dict:
    return {"schema": SCHEMA + "-manifest/1", "report_id": report_id,
            "files": {file.name: sha(file.read_bytes()) for file in sorted(out.iterdir())
                      if file.is_file() and file.name != "manifest.json"}}


def collect(args) -> str:
    root = Path(__file__).resolve().parents[3]
    if Path.cwd().resolve() != root:
        raise ValueError("run collector from harness checkout root")
    identity = admit_source(root, args.harness_commit, sealed=not args.preflight_only)
    build, exe, out = args.build_dir.resolve(strict=True), args.exe.resolve(strict=True), args.out.resolve()
    if (build == root or not build.is_relative_to(root) or
            exe != build / "Release" / "csl_geo07_dependent_report.exe" or
            not out.is_relative_to(build) or out.exists()):
        raise ValueError("build, Release executable, or fresh output path differs")
    if any(os.environ.get(name) for name in ("CL", "_CL_", "LINK")):
        raise ValueError("MSVC flag overrides are not admitted")
    out.mkdir(parents=True)
    (out / "collection-status.json").write_bytes(json_bytes({
        "schema": SCHEMA + "-collection-status/1", "publishable": False,
        "reason": "preflight or collection incomplete"}))
    try:
        cache_raw = (build / "CMakeCache.txt").read_bytes()
        settings = cache_settings(cache_raw)
        if Path(settings.get("CSL_SOURCE_DIR", "")).resolve() != root:
            raise ValueError("configured source checkout differs")
        cmake = settings.get("CMAKE_COMMAND")
        if not cmake or not Path(cmake).is_file():
            raise ValueError("configured CMake command missing")
        command = [cmake, "--build", str(build), "--config", "Release", "--target",
                   "csl_geo07_dependent_report", "--clean-first", "--verbose"]
        build_stdout, build_stderr, code, timed_out = captured(command, root, out, "build", 600)
        if code or timed_out:
            raise ValueError("fresh Release build failed or timed out; raw logs retained")
        build_end = datetime.now(timezone.utc)
        projects = {"driver": release_project(build / "csl_geo07_dependent_report.vcxproj"),
                    "adapter_library": release_project(build / "csl_generator_adapter.vcxproj"),
                    "generator_library": release_project(build / "csl_geometry_generators.vcxproj")}
        admit_release(settings, projects, build)
        if args.preflight_only and settings.get("BUILD_TESTING") != "ON":
            raise ValueError("smoke preflight requires BUILD_TESTING=ON")
        if not args.preflight_only and settings.get("BUILD_TESTING") != "OFF":
            raise ValueError("measurement collection requires BUILD_TESTING=OFF")
        described, stderr, code, timed_out = captured([str(exe), "--describe"], root, out, "describe", 30)
        if code or timed_out or stderr:
            raise ValueError("driver description failed; raw output retained")
        inputs_raw, fixture_hashes = admit_description(described)
        (out / "fixture-inputs.json").write_bytes(inputs_raw)
        smoke_raw, stderr, code, timed_out = captured([str(exe), "--smoke"], root, out, "smoke", 30)
        if code or timed_out or stderr:
            raise ValueError("driver smoke failed; raw output retained")
        admit_rows(smoke_raw, repetitions=1, batch=1, smoke=True)
        if git(root, "rev-parse", "HEAD") != identity["harness_commit"] or git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("source changed during preflight")
        compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
        if len(compiler_files) != 1:
            raise ValueError("configured compiler evidence missing")
        compiler_raw = compiler_files[0].read_bytes()
        matches = [match.group(1) for line in compiler_raw.decode("utf-8").splitlines()
                   if (match := re.fullmatch(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', line))]
        if len(matches) != 1:
            raise ValueError("unique compiler version evidence missing")
        provenance = {"schema": SCHEMA + "-build/1", **identity,
                      "configuration": "Release", "settings": {name: settings[name] for name in RELEASE_FLAGS},
                      "projects": projects, "compiler_version": matches[0],
                      "compiler_file_sha256": sha(compiler_raw), "cache_sha256": sha(cache_raw),
                      "exe_sha256": sha(exe.read_bytes()),
                      "build_stdout_sha256": sha(build_stdout), "build_stderr_sha256": sha(build_stderr)}
        (out / "build-provenance.json").write_bytes(json_bytes(provenance))
        if args.preflight_only:
            (out / "collection-status.json").write_bytes(json_bytes({
                "schema": SCHEMA + "-collection-status/1", "publishable": False,
                "reason": "clean fixed-source Release smoke preflight only; reviewed seal and measurements pending"}))
            (out / "manifest.json").write_bytes(json_bytes(manifest(out, "preflight")))
            return "preflight passed; nonpublishable"
        if not 7 <= args.repetitions <= 100 or not 1 <= args.batch <= 100000:
            raise ValueError("invalid measured profile")
        host_raw, host_stderr, host_code, host_timeout = host_observation()
        (out / "host-observation.json").write_bytes(host_raw)
        (out / "host-observation.stderr").write_bytes(host_stderr)
        start = datetime.now(timezone.utc)
        if host_code or host_timeout or host_stderr:
            raise ValueError("host observation failed; raw output retained")
        host = admit_host(host_raw, build_end, start)
        command = [str(exe), "--measure", str(args.repetitions), "1", str(args.batch)]
        trials_raw, stderr, code, timed_out = captured(command, root, out, "trials", 600)
        end = datetime.now(timezone.utc)
        if code or timed_out or stderr:
            raise ValueError("driver measurement failed; raw output retained")
        rows, summary = admit_rows(trials_raw, repetitions=args.repetitions, batch=args.batch)
        if git(root, "rev-parse", "HEAD") != identity["harness_commit"] or git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("source changed during measurement")
        record = {"schema": SCHEMA + "-records/1", **identity,
                  "created_utc": datetime.now(timezone.utc).isoformat(),
                  "collection_start_utc": start.isoformat(), "collection_end_utc": end.isoformat(),
                  "inputs": {"fixtures": INPUTS, "fixture_sha256": fixture_hashes,
                             "canonical_bytes_sha256": sha(inputs_raw),
                             "driver_description_sha256": sha(described),
                             "driver_source_sha256": sha((root / "benchmarks/reporting/geo07_dependent/driver.cpp").read_bytes()),
                             "scalar": "binary64", "assurance": "numerical",
                             "representation_claim": "equivalent real-set dependent generator algebra; no validated binary64 rounding enclosure"},
                  "timing": {"clock": "steady_clock", "unit": "ns", "scope": INTERVAL,
                             "warmup_rounds": 1, "measured_rounds": args.repetitions,
                             "batch_calls": args.batch, "order": "alternating fixtures",
                             "minimum_admitted_batch_ns": 20_000_000,
                             "internal_phase_counters": "unavailable"},
                  "environment": {"os": platform.platform(), "processor": platform.processor(),
                                  "logical_processors": os.cpu_count(), "python": platform.python_version(),
                                  "requested_driver_workers": 1, "observed_native_threads": None,
                                  "observed_native_threads_reason": "no native thread counter in driver",
                                  "host_observation": host, "host_observation_sha256": sha(host_raw)},
                  "process": {"exit_code": code, "stderr_sha256": sha(stderr),
                              "raw_sha256": sha(trials_raw)},
                  "build_provenance_sha256": sha((out / "build-provenance.json").read_bytes()),
                  "rows": rows, "summary": summary,
                  "performance_conclusion": "exploratory single-adapter batch observations; no comparator, speedup, or attributed limiter"}
        payload_hash = sha(json_bytes(record))
        report_id = "geo07-dependent-" + payload_hash[:16]
        record.update({"report_id": report_id, "payload_sha256": payload_hash})
        (out / "records.json").write_bytes(json_bytes(record))
        (out / "collection-status.json").write_bytes(json_bytes({
            "schema": SCHEMA + "-collection-status/1", "publishable": False,
            "accepted_for_report_review": True,
            "reason": "independent saved review, rendering, registration and live publication pending",
            "records_sha256": sha((out / "records.json").read_bytes())}))
        (out / "manifest.json").write_bytes(json_bytes(manifest(out, report_id)))
        return report_id
    except Exception as error:
        (out / "collection-status.json").write_bytes(json_bytes({
            "schema": SCHEMA + "-collection-status/1", "publishable": False,
            "reason": str(error)}))
        (out / "manifest.json").write_bytes(json_bytes(manifest(out, "rejected")))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--batch", type=int, default=1000)
    args = parser.parse_args()
    print(collect(args))


if __name__ == "__main__":
    main()

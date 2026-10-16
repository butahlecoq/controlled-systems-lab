#!/usr/bin/env python3
"""Admit one reviewed fixed-source EXT-04 replay measurement; never publish it."""
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
import xml.etree.ElementTree as ET

SOURCE = "c23aaf13c1c1e5480cc22dd5bac5cd3e79562609"
TRIAL_SCHEMA = "csl.ext04-replay-trial/1"
RECORD_SCHEMA = "csl.ext04-replay-records/1"
INTERVAL = ("batch of fresh public LinearSystem snapshots and replay_observed_policy calls, "
            "estimator/controller callbacks, full literal state/history/release/input oracle checks, "
            "and per-call result JSON construction and assignment/replacement; excludes process startup, JSONL serialization, "
            "Python saved-row validation, persistence and rendering")
EXPECTED = {
    "partial_noisy_delayed": {
        "status": "passed", "states": [[1.0, 7.0], [2.0, 7.0], [9.0, 7.0]],
        "observed_values": [[4.0], [7.0]], "observed_channels": [0, 1],
        "measurement_events": ["before(0)", "after(0)"],
        "release_events": ["before(0)", "before(1)"],
        "actions": [[1.0], [7.0]], "estimates": [[4.0, 0.0], [7.0, 0.0]],
        "available_values": [[[4.0]], [[4.0], [7.0]]], "available_counts": [1, 2],
        "decision_stages": [0, 1],
        "released": [
            {"released_index": 0, "channel": 0, "sample": 0, "measured_at": "before(0)",
             "available_at": "before(0)", "released_at": "before(0)", "values": [4.0]},
            {"released_index": 1, "channel": 1, "sample": 0, "measured_at": "after(0)",
             "available_at": "before(1)", "released_at": "before(1)", "values": [7.0]}],
        "available": [
            [{"released_index": 0, "channel": 0, "sample": 0, "measured_at": "before(0)",
              "available_at": "before(0)", "released_at": "before(0)", "values": [4.0]}],
            [{"released_index": 0, "channel": 0, "sample": 0, "measured_at": "before(0)",
              "available_at": "before(0)", "released_at": "before(0)", "values": [4.0]},
             {"released_index": 1, "channel": 1, "sample": 0, "measured_at": "after(0)",
              "available_at": "before(1)", "released_at": "before(1)", "values": [7.0]}]]},
    "post_feedthrough": {
        "status": "passed", "states": [[2.0], [3.0], [10.0]],
        "observed_values": [[7.0]], "observed_channels": [0],
        "measurement_events": ["after(0)"], "release_events": ["after(0)"],
        "actions": [[1.0], [7.0]], "estimates": [[0.0], [7.0]],
        "available_values": [[], [[7.0]]], "available_counts": [0, 1],
        "decision_stages": [0, 1],
        "released": [{"released_index": 0, "channel": 0, "sample": 0,
                      "measured_at": "after(0)", "available_at": "after(0)",
                      "released_at": "after(0)", "values": [7.0]}],
        "available": [[], [{"released_index": 0, "channel": 0, "sample": 0,
                            "measured_at": "after(0)", "available_at": "after(0)",
                            "released_at": "after(0)", "values": [7.0]}]]},
    "no_channel": {
        "status": "passed", "states": [[5.0], [7.0]],
        "observed_values": [], "observed_channels": [],
        "measurement_events": [], "release_events": [],
        "actions": [[2.0]], "estimates": [[0.0]],
        "available_values": [[]], "available_counts": [0],
        "decision_stages": [0], "released": [], "available": [[]]},
}
INPUTS = {
    "partial_noisy_delayed": {
        "dimensions": [2, 1, 0], "horizon": 2,
        "A": [1, 0, 0, 1], "B": [1, 0], "E": [], "offset": [0, 0],
        "times": [0, 1, 2], "initial": [1, 7], "external": [[], []],
        "errors": [[[3]], [[]]],
        "channels": [
            {"C": [1, 0], "Du": [0], "Dw": [], "F": [1], "offset": [0],
             "state_stage": 0, "input_stage": None,
             "measured_at": "before(0)", "available_at": "before(0)"},
            {"C": [0, 1], "Du": [0], "Dw": [], "F": [], "offset": [0],
             "state_stage": 1, "input_stage": None,
             "measured_at": "after(0)", "available_at": "before(1)"}],
        "estimator": "last output in first coordinate, other coordinate zero",
        "controller": "u0=estimate[0]-3; u1=estimate[0]"},
    "post_feedthrough": {
        "dimensions": [1, 1, 0], "horizon": 2,
        "A": [1], "B": [1], "E": [], "offset": [0],
        "times": [0, 1, 2], "initial": [2], "external": [[], []],
        "errors": [[[3]]],
        "channels": [
            {"C": [1], "Du": [2], "Dw": [], "F": [1], "offset": [0],
             "state_stage": 0, "input_stage": 0,
             "measured_at": "after(0)", "available_at": "after(0)"}],
        "estimator": "last output, or zero before any output",
        "controller": "u0=1; u1=estimate[0]"},
    "no_channel": {
        "dimensions": [1, 1, 0], "horizon": 1,
        "A": [1], "B": [1], "E": [], "offset": [0],
        "times": [0, 1], "initial": [5], "external": [[]],
        "errors": [], "channels": [],
        "estimator": "zero with empty history", "controller": "constant u=2"},
}
ALLOWED = {
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/ext04/observed_replay_driver.cpp",
    "scripts/reports/ext04/check_smoke.py", "scripts/reports/ext04/collect.py",
    "reports/algorithm-results/tooling/ext04/README.md",
    "tests/reporting/test_ext04_harness.py",
}
RELEASE_FLAGS = {
    "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
    "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG",
    "CMAKE_EXE_LINKER_FLAGS": "/machine:x64",
    "CMAKE_EXE_LINKER_FLAGS_RELEASE": "/INCREMENTAL:NO",
    "CMAKE_STATIC_LINKER_FLAGS": "/machine:x64",
    "CMAKE_STATIC_LINKER_FLAGS_RELEASE": "",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def parse_raw(raw: bytes) -> list[dict]:
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("empty or unterminated JSONL")
    rows = []
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=_unique,
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
    if (value.get("schema") != "csl.ext04-replay-driver/1" or
            value.get("source_commit") != SOURCE or
            value.get("module") != "CSL::controllers" or
            value.get("scalar") != "binary64" or
            value.get("fixtures") != list(EXPECTED) or
            value.get("timed_scope") != INTERVAL or
            json_bytes(value.get("inputs")) != json_bytes(INPUTS)):
        raise ValueError("driver source, timing scope or authored inputs differ")
    return json_bytes(INPUTS), {name: sha(json_bytes(INPUTS[name])) for name in EXPECTED}


def admit_raw(raw: bytes, *, repetitions: int, batch: int) -> tuple[list[dict], dict]:
    if type(repetitions) is not int or repetitions < 7 or type(batch) is not int or batch < 1:
        raise ValueError("accepted collection requires seven rounds and positive batch")
    rows = parse_raw(raw)
    names = list(EXPECTED)
    sequence = [(name, 0, True) for name in names]
    sequence += [(name, index, False) for index in range(repetitions)
                 for name in (names if index % 2 == 0 else names[::-1])]
    if len(rows) != len(sequence):
        raise ValueError("missing or extra trial")
    for row, (name, index, warmup) in zip(rows, sequence):
        if (set(row) != {"schema", "fixture", "round", "warmup", "batch", "checked_calls",
                         "elapsed_ns", "status", "error", "result"} or
                row["schema"] != TRIAL_SCHEMA or row["fixture"] != name or
                type(row["round"]) is not int or row["round"] != index or
                row["warmup"] is not warmup or type(row["batch"]) is not int or
                row["batch"] != batch or type(row["checked_calls"]) is not int or
                row["checked_calls"] != batch or row["status"] != "passed" or
                row["error"] is not None or json_bytes(row["result"]) != json_bytes(EXPECTED[name]) or
                type(row["elapsed_ns"]) is not int or row["elapsed_ns"] < 20_000_000):
            raise ValueError("trial identity, work count, interval or literal oracle differs")
    summary = {}
    for name in names:
        elapsed = [row["elapsed_ns"] for row in rows if row["fixture"] == name and not row["warmup"]]
        summary[name] = {"attempts": len(elapsed), "successes": len(elapsed), "failures": 0,
                         "median_batch_ns": statistics.median(elapsed),
                         "min_batch_ns": min(elapsed), "max_batch_ns": max(elapsed)}
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
        "schema": "csl.ext04-process-capture/1", "command": ["REPORT_EXE", *command[1:]],
        "exit_code": code, "timed_out": timed_out,
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)}))


def save_build_evidence(out: Path, cache: bytes, compiler: bytes,
                        build_stdout: bytes, build_stderr: bytes) -> None:
    for name, payload in (("CMakeCache.raw.txt", cache),
                          ("CMakeCXXCompiler.raw.cmake", compiler),
                          ("build.stdout.log", build_stdout),
                          ("build.stderr.log", build_stderr)):
        (out / name).write_bytes(payload)


def reject(out: Path, reason: str) -> None:
    (out / "collection-status.json").write_bytes(json_bytes({
        "schema": "csl.ext04-collection-status/1", "publishable": False,
        "reason": reason}))


def manifest(out: Path, report_id: str) -> dict:
    files = {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir())
             if path.is_file() and path.name != "manifest.json"}
    return {"schema": "csl.ext04-manifest/1", "report_id": report_id, "files": files}


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root,
                                   text=True, encoding="utf-8").strip()


def cache_settings(raw: bytes) -> dict[str, str]:
    settings = {}
    for line in raw.decode("utf-8").splitlines():
        if line.startswith(("//", "#")) or "=" not in line or ":" not in line.split("=", 1)[0]:
            continue
        key, value = line.split("=", 1)
        name = key.split(":", 1)[0]
        if name in settings:
            raise ValueError("duplicate CMake setting: " + name)
        settings[name] = value
    return settings


def release_project(path: Path) -> dict:
    root = ET.parse(path).getroot()
    ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
    groups = [item for item in root.findall(ns + "ItemDefinitionGroup")
              if item.get("Condition") == "'$(Configuration)|$(Platform)'=='Release|x64'"]
    if len(groups) != 1:
        raise ValueError("unique x64 Release graph unavailable: " + path.name)
    configurations = [item for item in root.findall(ns + "PropertyGroup")
                      if item.get("Condition") == "'$(Configuration)|$(Platform)'=='Release|x64'"
                      and item.get("Label") == "Configuration"]
    if len(configurations) != 1:
        raise ValueError("unique x64 Release toolset unavailable: " + path.name)
    def fields(name):
        node = groups[0].find(ns + name)
        return {child.tag.removeprefix(ns): (child.text or "") for child in node} if node is not None else {}
    configuration = {child.tag.removeprefix(ns): (child.text or "") for child in configurations[0]}
    return {"configuration": configuration, "compile": fields("ClCompile"), "link": fields("Link"),
            "archive": fields("Lib"), "project_sha256": sha(path.read_bytes())}


def compiler_identity(raw: bytes, settings: dict) -> dict[str, str]:
    lines = raw.decode("utf-8").splitlines()
    # CMake emits quoted paths/identity values and may emit the architecture bare.
    def field(name: str) -> str:
        matches = [match for line in lines
                   if (match := re.fullmatch(r'set\(' + re.escape(name) +
                                             r' (?:"([^"]+)"|([^ )]+))\)', line))]
        if len(matches) != 1:
            raise ValueError("unique compiler evidence unavailable: " + name)
        return matches[0].group(1) or matches[0].group(2)
    compiler_id = field("CMAKE_CXX_COMPILER_ID")
    version = field("CMAKE_CXX_COMPILER_VERSION")
    frontend = field("CMAKE_CXX_COMPILER_FRONTEND_VARIANT")
    architecture = field("CMAKE_CXX_COMPILER_ARCHITECTURE_ID")
    if (compiler_id != "MSVC" or frontend != "MSVC" or architecture != "x64" or
            not re.fullmatch(r"19\.\d+\.\d+(?:\.\d+)?", version)):
        raise ValueError("compiler identity is not x64 MSVC")
    if settings.get("CMAKE_GENERATOR_TOOLSET") not in ("", "v143"):
        raise ValueError("unreviewed generator toolset")
    instance_text = settings.get("CMAKE_GENERATOR_INSTANCE")
    if not instance_text:
        raise ValueError("Visual Studio generator instance unavailable")
    try:
        instance = Path(instance_text).resolve(strict=True)
        compiler = Path(field("CMAKE_CXX_COMPILER")).resolve(strict=True)
    except OSError as error:
        raise ValueError("configured MSVC compiler path unavailable") from error
    try:
        relative = compiler.relative_to(instance)
    except ValueError as error:
        raise ValueError("compiler is outside generator instance") from error
    parts = [part.casefold() for part in relative.parts]
    if (len(parts) != 8 or parts[:3] != ["vc", "tools", "msvc"] or
            not re.fullmatch(r"14\.\d+\.\d+", parts[3]) or
            parts[4:] != ["bin", "hostx64", "x64", "cl.exe"]):
        raise ValueError("compiler path is not the x64 MSVC toolset")
    return {"id": compiler_id, "version": version, "frontend": frontend,
            "architecture": architecture, "toolset": "v143", "path": compiler.as_posix(),
            "generator_instance": instance.as_posix(), "exe_sha256": sha(compiler.read_bytes())}


def admit_release(settings: dict, targets: dict, build: Path) -> None:
    for name, expected in RELEASE_FLAGS.items():
        if settings.get(name) != expected:
            raise ValueError("unreviewed Release flag: " + name)
    if (settings.get("CSL_BUILD_EXT04_REPORT") != "ON" or
            settings.get("CSL_ENABLE_HIGHS") != "OFF" or
            settings.get("CSL_ENABLE_QHULL") != "OFF" or
            settings.get("BUILD_TESTING") != "OFF" or
            settings.get("CMAKE_GENERATOR") != "Visual Studio 17 2022" or
            settings.get("CMAKE_GENERATOR_PLATFORM") != "x64" or
            settings.get("CMAKE_GENERATOR_TOOLSET") not in ("", "v143") or
            not settings.get("CMAKE_GENERATOR_INSTANCE")):
        raise ValueError("configured report profile differs")
    for name in ("driver", "controller_library"):
        if targets[name]["configuration"].get("PlatformToolset") != "v143":
            raise ValueError("unreviewed Release platform toolset: " + name)
        compile_fields = targets[name]["compile"]
        if (compile_fields.get("Optimization") != "MaxSpeed" or
                compile_fields.get("InlineFunctionExpansion") != "AnySuitable" or
                compile_fields.get("LanguageStandard") != "stdcpp20" or
                compile_fields.get("RuntimeLibrary") != "MultiThreadedDLL" or
                "NDEBUG" not in compile_fields.get("PreprocessorDefinitions", "").split(";")):
            raise ValueError("unreviewed Release compile settings: " + name)
        expected = ('%(AdditionalOptions) /external:I "' +
                    (build / "_deps" / "csl_json-src" / "include").as_posix() + '"')
        if compile_fields.get("AdditionalOptions", "") != (expected if name == "driver" else ""):
            raise ValueError("unreviewed compile options: " + name)
    link = targets["driver"]["link"]
    if (link.get("GenerateDebugInformation") != "false" or
            link.get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64" or
            "Release\\csl_controllers.lib" not in link.get("AdditionalDependencies", "")):
        raise ValueError("driver Release link graph differs")
    if targets["controller_library"]["archive"].get("AdditionalOptions") != "%(AdditionalOptions) /machine:x64":
        raise ValueError("controller library Release archive differs")


def collect(args) -> str:
    root = Path(__file__).resolve().parents[3]
    if not 7 <= args.repetitions <= 100 or not 1 <= args.batch <= 100000:
        raise ValueError("profile requires 7-100 rounds and 1-100000 calls per batch")
    if Path.cwd().resolve() != root:
        raise ValueError("run from the harness source root")
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
    if (build == root or not build.is_relative_to(root) or
            exe != build / "Release" / "csl_ext04_observed_replay_report.exe" or
            not out.is_relative_to(build) or out.exists()):
        raise ValueError("build, Release executable, or new output destination differs")
    note = args.concurrent_work.read_text(encoding="utf-8").strip()
    if len(note) < 10 or "TODO" in note or "TBD" in note:
        raise ValueError("observed concurrent-work note required before measurement")
    if any(os.environ.get(name) for name in ("CL", "_CL_", "LINK")):
        raise ValueError("MSVC environment flag overrides are not admitted")
    cache_raw = (build / "CMakeCache.txt").read_bytes()
    settings = cache_settings(cache_raw)
    if Path(settings.get("CSL_SOURCE_DIR", "")).resolve() != root:
        raise ValueError("configured source checkout differs")
    cmake = settings.get("CMAKE_COMMAND")
    if not cmake or not Path(cmake).is_file():
        raise ValueError("configured CMake command missing")
    command_build = [cmake, "--build", str(build), "--config", "Release", "--target",
                     "csl_ext04_observed_replay_report", "--clean-first", "--verbose"]
    built = subprocess.run(command_build, cwd=root, capture_output=True, timeout=600)
    (build / "ext04-final-build.stdout.log").write_bytes(built.stdout)
    (build / "ext04-final-build.stderr.log").write_bytes(built.stderr)
    if built.returncode:
        raise ValueError("fresh Release build failed; exact logs retained")
    if (build / "CMakeCache.txt").read_bytes() != cache_raw:
        raise ValueError("CMake cache changed during fresh build")
    targets = {"driver": release_project(build / "csl_ext04_observed_replay_report.vcxproj"),
               "controller_library": release_project(build / "csl_controllers.vcxproj")}
    admit_release(settings, targets, build)
    compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("configured compiler evidence unavailable")
    compiler_raw = compiler_files[0].read_bytes()
    compiler = compiler_identity(compiler_raw, settings)
    described = subprocess.run([str(exe), "--describe"], capture_output=True, timeout=30)
    (build / "ext04-driver-description.jsonl").write_bytes(described.stdout)
    (build / "ext04-driver-description.stderr").write_bytes(described.stderr)
    if described.returncode or described.stderr:
        raise ValueError("driver description failed; bytes retained")
    input_bytes, input_hashes = admit_description(described.stdout)
    command = [str(exe), "--measure", str(args.repetitions), "1", str(args.batch)]
    try:
        measured = subprocess.run(command, cwd=root, capture_output=True, timeout=600)
        stdout, stderr, code, timed_out = measured.stdout, measured.stderr, measured.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
    save_capture(out, stdout, stderr, code, command, timed_out=timed_out)
    (out / "driver-description.jsonl").write_bytes(described.stdout)
    (out / "fixture-inputs.json").write_bytes(input_bytes)
    save_build_evidence(out, cache_raw, compiler_raw, built.stdout, built.stderr)
    try:
        if code or stderr or timed_out:
            raise ValueError("driver failed, timed out, or wrote stderr")
        rows, summary = admit_raw(stdout, repetitions=args.repetitions, batch=args.batch)
        if (git(root, "rev-parse", "HEAD") != args.harness_commit or
                git(root, "status", "--porcelain=v1", "--untracked-files=all")):
            raise ValueError("source changed during collection")
        if ((build / "CMakeCache.txt").read_bytes() != cache_raw or
                compiler_files[0].read_bytes() != compiler_raw or
                sha(Path(compiler["path"]).read_bytes()) != compiler["exe_sha256"]):
            raise ValueError("build evidence changed during collection")
        provenance = {"schema": "csl.ext04-build-provenance/1", "source_commit": SOURCE,
                      "harness_commit": args.harness_commit, "configuration": "Release",
                      "settings": {name: settings[name] for name in RELEASE_FLAGS},
                      "targets": targets, "compiler": compiler,
                      "compiler_file_sha256": sha(compiler_raw), "cache_sha256": sha(cache_raw),
                      "exe_sha256": sha(exe.read_bytes()),
                      "build_stdout_sha256": sha(built.stdout), "build_stderr_sha256": sha(built.stderr)}
        (out / "build-provenance.json").write_bytes(json_bytes(provenance))
        record = {"schema": RECORD_SCHEMA, "source_commit": SOURCE,
                  "harness_commit": args.harness_commit,
                  "source_tree": git(root, "rev-parse", SOURCE + "^{tree}"),
                  "harness_tree": git(root, "rev-parse", "HEAD^{tree}"),
                  "created_utc": datetime.now(timezone.utc).isoformat(),
                  "inputs": {"fixtures": INPUTS, "fixture_sha256": input_hashes,
                             "canonical_bytes_sha256": sha(input_bytes),
                             "driver_description_sha256": sha(described.stdout),
                             "driver_sha256": sha((root / "benchmarks/reporting/ext04/observed_replay_driver.cpp").read_bytes()),
                             "assurance": "sampled binary64 replay only; no policy or all-disturbance certificate"},
                  "timing": {"clock": "steady_clock", "unit": "ns", "scope": INTERVAL,
                             "warmup_rounds": 1, "measured_rounds": args.repetitions,
                             "batch_calls": args.batch, "order": "alternating fixtures",
                             "workspace": "fresh system snapshot and replay result each checked call; same process across rounds",
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
                  "performance_conclusion": "exploratory single-path batch observations; no comparator, speedup, or attributed limiter"}
        identity = sha(json_bytes(record))
        report_id = "ext04-" + identity[:16]
        record.update({"report_id": report_id, "payload_sha256": identity})
        (out / "records.json").write_bytes(json_bytes(record))
        (out / "collection-status.json").write_bytes(json_bytes({
            "schema": "csl.ext04-collection-status/1", "publishable": False,
            "reason": "scientific review, rendering, registration and deployment pending",
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
    print(collect(parser.parse_args()))


if __name__ == "__main__":
    main()

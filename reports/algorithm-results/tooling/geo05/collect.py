#!/usr/bin/env python3
"""Collect smoke-only checks or versioned GEO-05 measurement records."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import zipfile
from pathlib import Path

from report import (HARNESS_PATH_ALLOWLIST, PHASES, SCENARIOS, bind_fixture_identity, make_record,
                    is_reviewed_artifact_path, reviewed_artifact_path_policy,
                    scenario_order, strict_json_loads, validate_cmake_delta, validate_source_tree_delta)
from smoke import validate_smoke


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def _git_paths(*args: str) -> list[str]:
    output = subprocess.check_output(["git", *args])
    return [path.decode("utf-8", errors="surrogateescape") for path in output.split(b"\0") if path]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_capture(command: list[str], timeout_seconds: int = 600) -> tuple[str, str, int, bool]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds)
        return completed.stdout or "", completed.stderr or "", completed.returncode, False
    except subprocess.TimeoutExpired as timeout:
        decode = lambda value: value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
        return decode(timeout.stdout), decode(timeout.stderr), 124, True


def _redact_paths(value, source_root: Path, build_root: Path):
    if isinstance(value, str):
        for path, token in ((build_root, "BUILD_ROOT"), (source_root, "SOURCE_ROOT"),
                            (Path.home(), "USER_HOME")):
            value = value.replace(str(path), token).replace(str(path).replace("\\", "/"), token)
        return value
    if isinstance(value, list):
        return [_redact_paths(item, source_root, build_root) for item in value]
    if isinstance(value, dict):
        return {key: _redact_paths(item, source_root, build_root) for key, item in value.items()}
    return value


def _release_graph(build: Path, exe: Path, source_root: Path) -> dict:
    reply = build / ".cmake" / "api" / "v1" / "reply"
    indices = sorted(reply.glob("index-*.json"))
    if not indices:
        raise ValueError("CMake File API reply missing; query codemodel-v2 and toolchains-v1 before configuring")
    index = strict_json_loads(indices[-1].read_text(encoding="utf-8"))
    load = lambda name: strict_json_loads((reply / name).read_text(encoding="utf-8"))
    codemodel = load(index["reply"]["codemodel-v2"]["jsonFile"])
    configurations = [item for item in codemodel["configurations"] if item["name"] == "Release"]
    if len(configurations) != 1:
        raise ValueError("actual Release configuration missing from CMake File API")
    targets = {item["id"]: load(item["jsonFile"]) for item in configurations[0]["targets"]}
    roots = [key for key, target in targets.items() if target.get("name") == "csl_geo05_projection_predecessor_report"]
    if len(roots) != 1:
        raise ValueError("GEO-05 executable missing from configured Release graph")
    selected: dict[str, dict] = {}
    def visit(key: str) -> None:
        if key in selected:
            return
        target = targets[key]
        selected[key] = {field: target[field] for field in
                         ("name", "type", "compileGroups", "link", "archive", "artifacts") if field in target}
        for dependency in target.get("dependencies", []):
            visit(dependency["id"])
    visit(roots[0])
    root = targets[roots[0]]
    artifacts = [build / item["path"] for item in root.get("artifacts", [])
                 if Path(item["path"]).name == exe.name]
    if len(artifacts) != 1 or artifacts[0].resolve() != exe.resolve():
        raise ValueError("provided executable is not the configured Release target artifact")
    groups = [group for group in root.get("compileGroups", []) if group.get("language") == "CXX"]
    if len(groups) != 1 or groups[0].get("languageStandard", {}).get("standard") != "20":
        raise ValueError("driver must have a C++20 Release compile group")
    flags = " ".join(fragment["fragment"] for fragment in groups[0].get("compileCommandFragments", []))
    if "/DNDEBUG" not in flags and "-DNDEBUG" not in flags:
        raise ValueError("Release/NDEBUG flag missing from actual driver compile group")
    toolchains = load(index["reply"]["toolchains-v1"]["jsonFile"])["toolchains"]
    compilers = [item for item in toolchains if item.get("language") == "CXX"]
    if len(compilers) != 1:
        raise ValueError("configured C++ compiler missing")
    required = {"csl_geo05_projection_predecessor_report", "csl_polyhedral", "csl_sets",
                "csl_optimization", "csl_registry", "csl_numeric", "csl_contracts"}
    names = {item["name"] for item in selected.values()}
    if not required <= names:
        raise ValueError(f"report dependency graph is incomplete: {sorted(required-names)}")
    paths = codemodel["paths"]
    if not Path(paths["source"]).samefile(source_root) or not Path(paths["build"]).samefile(build):
        raise ValueError("CMake source/build path ownership differs from this collection")
    return {"cmake": {"version": index.get("cmake", {}).get("version"),
                      "generator": index.get("cmake", {}).get("generator", {}).get("name")},
            "compiler": _redact_paths(compilers[0], source_root, build), "dependency_targets": sorted(names),
            "file_api_paths": _redact_paths(paths, source_root, build),
            "targets": _redact_paths(list(selected.values()), source_root, build)}


def _validate_build_log(build_log: Path, build: Path, exe: Path, source_root: Path) -> None:
    if build_log == build or not build_log.is_relative_to(build):
        raise ValueError("build log must resolve inside the configured build directory")
    if build_log == exe or (build_log.is_file() and exe.is_file() and build_log.samefile(exe)):
        raise ValueError("build log must not alias the executable")
    for name in _git_paths("-C", str(source_root), "ls-files", "-z"):
        tracked = source_root / name
        if build_log == tracked.resolve() or (build_log.is_file() and tracked.is_file()
                                             and build_log.samefile(tracked)):
            raise ValueError("build log must not alias a tracked source file")


def build_provenance(build: Path, exe: Path, source_commit: str,
                     harness_commit: str, build_log: Path) -> dict:
    build, exe, build_log = build.resolve(), exe.resolve(), build_log.resolve()
    source_root = Path(_git("rev-parse", "--show-toplevel")).resolve()
    if _git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness commit does not match checked-out HEAD")
    if _git("status", "--porcelain=v1"):
        raise ValueError("source and harness worktree must be clean before collection")
    _validate_build_log(build_log, build, exe, source_root)
    changed = _git_paths("diff", "--name-only", "-z", source_commit, harness_commit)
    validate_source_tree_delta(changed)
    source_cmake = subprocess.check_output(["git", "show", f"{source_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    harness_cmake = subprocess.check_output(["git", "show", f"{harness_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    validate_cmake_delta(source_cmake, harness_cmake)
    _release_graph(build, exe, source_root)
    command = ["cmake", "--build", str(build), "--config", "Release", "--target",
               "csl_geo05_projection_predecessor_report", "--clean-first", "--verbose"]
    try:
        stdout, stderr, return_code, timed_out = _run_capture(command)
    except OSError as error:
        stdout, stderr, return_code, timed_out = "", str(error), 127, False
    fresh_build = _redact_paths({"command": command, "source_commit": source_commit,
                                "harness_commit": harness_commit, "stdout": stdout,
                                "stderr": stderr, "return_code": return_code,
                                "timed_out": timed_out}, source_root, build)
    _validate_build_log(build_log.resolve(), build, exe, source_root)
    build_log.parent.mkdir(parents=True, exist_ok=True)
    build_log.write_text(json.dumps(fresh_build, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if return_code or timed_out:
        reason = "timed out" if timed_out else "failed"
        raise ValueError(f"fresh Release rebuild {reason} (exit {return_code}); diagnostics saved to "
                         f"{_redact_paths(str(build_log), source_root, build)}")
    if _git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness HEAD changed during the fresh Release rebuild")
    if _git("status", "--porcelain=v1"):
        raise ValueError("source and harness worktree must remain clean during the fresh Release rebuild")
    graph = _release_graph(build, exe, source_root)
    if not exe.is_file():
        raise ValueError("fresh Release rebuild did not produce the configured executable")
    return {"source_commit": source_commit, "harness_commit": harness_commit,
            "tracked_clean": True, "tracked_tree_binding": {
                "scope": "complete tracked repository tree",
                "source_tree_oid": _git("rev-parse", f"{source_commit}^{{tree}}"),
                "harness_tree_oid": _git("rev-parse", f"{harness_commit}^{{tree}}"),
                "allowed_harness_delta": sorted(HARNESS_PATH_ALLOWLIST), "actual_changed_paths": changed,
                "reviewed_artifact_path_policy": reviewed_artifact_path_policy(),
                "actual_reviewed_artifact_delta": sorted({path.replace("\\", "/") for path in changed
                                                          if is_reviewed_artifact_path(path)})},
            "executable": {"name": exe.name, "sha256": _sha(exe)},
            "build_log_sha256": _sha(build_log), "fresh_build": fresh_build,
            "configuration": "Release", "cxx_standard": "20",
            **graph}


def _matrix_error(rows: list[dict], repetitions: int) -> None:
    seen: set[tuple[str, int, str]] = set()
    for row in rows:
        purpose = row.get("purpose")
        scenario = row.get("scenario")
        rep = row.get("repetition")
        if purpose not in ("warmup", "measurement") or scenario not in SCENARIOS or not isinstance(rep, int):
            raise ValueError("driver emitted an invalid trial identity")
        key = (scenario, rep, purpose)
        if key in seen:
            raise ValueError("driver emitted a duplicate attempt")
        seen.add(key)
        if row.get("status") not in ("passed", "failed", "unsupported", "cancelled", "oracle_failed"):
            raise ValueError("driver emitted an unknown attempt status")
    required = [("warmup", name, 0) for name in SCENARIOS]
    required.extend(("measurement", name, rep) for rep in range(repetitions) for name in scenario_order(rep))
    emitted = [(row["purpose"], row["scenario"], row["repetition"]) for row in rows]
    positions = [required.index(item) for item in emitted]
    if any(left >= right for left, right in zip(positions, positions[1:])):
        raise ValueError("attempts are duplicated or out of fixed alternating order")


def _durable_text(path: Path, source: str) -> None:
    with path.open("w", encoding="utf-8") as stream:
        stream.write(source)
        stream.flush()
        os.fsync(stream.fileno())


def _write_capture(out: Path, stdout: str, stderr: str, command: list[str],
                   process_return_code: int, timed_out: bool) -> None:
    out.mkdir(parents=True, exist_ok=False)
    _durable_text(out / "stdout.jsonl", stdout)
    _durable_text(out / "stderr.txt", stderr)
    _durable_text(out / "command.json", json.dumps(command, indent=2)+"\n")
    _durable_text(out / "process-capture.json", json.dumps({
        "schema": "csl.geo05-process-capture/1", "process_return_code": process_return_code,
        "timed_out": timed_out, "stdout_file_sha256": _sha(out / "stdout.jsonl"),
        "stderr_file_sha256": _sha(out / "stderr.txt")}, indent=2)+"\n")


def _write_validation_error(out: Path, error: Exception) -> None:
    _durable_text(out / "validation-error.json", json.dumps({
        "schema": "csl.geo05-rejected-capture/1", "error_type": type(error).__name__,
        "error": str(error)}, indent=2)+"\n")


def _finish_collection(out: Path, rows: list[dict], provenance: dict, repetitions: int,
                       process_return_code: int, parse_errors: list[dict], timed_out: bool) -> None:
    try:
        _matrix_error(rows, repetitions)
        warmups = [row for row in rows if row["purpose"] == "warmup"]
        trials = [row for row in rows if row["purpose"] == "measurement"]
        record = make_record(trials, purpose="measurement", provenance=provenance,
                             measured_repetitions=repetitions, warmups=1, warmup_trials=warmups,
                             process_return_code=process_return_code, parse_errors=len(parse_errors), timed_out=timed_out)
    except Exception as error:
        _write_validation_error(out, error)
        raise
    (out / "records.json").write_text(json.dumps(record, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (out / "parse-errors.json").write_text(json.dumps(parse_errors, indent=2)+"\n", encoding="utf-8")
    with (out / "trials.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+"\n")
    fields = ["purpose", "scenario", "repetition", "status", "detail", "predecessor_failure", "oracle_passed", "work_observed", "end_to_end_scope",
              "max_rows", "input_rows", "output_rows", "result_kind", "result_encoding", "input_sha256", "scenario_sha256", "expected_fm_peak_rows", *PHASES]
    with (out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            context = row.get("predecessor_failure")
            writer.writerow({**row, **row.get("durations_ns", {}),
                "predecessor_failure": json.dumps(context, sort_keys=True, allow_nan=False) if context is not None else ""})
    from render import render_html
    (out / "index.html").write_text(render_html(record), encoding="utf-8")
    # The validated record now carries process outcome metadata. Keep the
    # historical successful bundle inventory; rejected captures retain the snapshot.
    (out / "process-capture.json").unlink()
    inventory = {path.name: _sha(path) for path in sorted(out.iterdir()) if path.is_file()}
    (out / "manifest.json").write_text(json.dumps({"schema": "csl.geo05-report-files/1", "files": inventory},
                                                        indent=2, sort_keys=True)+"\n", encoding="utf-8")
    with zipfile.ZipFile(out.with_suffix(".zip"), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.iterdir()):
            archive.write(path, arcname=path.name)


def _write_collection(out: Path, stdout: str, stderr: str, rows: list[dict],
                      provenance: dict, command: list[str], repetitions: int,
                      process_return_code: int, parse_errors: list[dict], timed_out: bool = False) -> None:
    _write_capture(out, stdout, stderr, command, process_return_code, timed_out)
    _finish_collection(out, rows, provenance, repetitions, process_return_code, parse_errors, timed_out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--build-log", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--harness-commit")
    parser.add_argument("--concurrent-work", type=Path)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.smoke == args.measure:
        parser.error("choose exactly one of --smoke or --measure")
    if args.smoke:
        result = subprocess.run([str(args.exe), "--smoke"], text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise SystemExit(f"functional smoke failed with exit {result.returncode}: {result.stderr}")
        validate_smoke(result.stdout)
        print("GEO-05 functional smoke passed; output timings discarded")
        return 0
    if args.repetitions < 7 or args.warmups != 1:
        parser.error("measurement requires at least seven repetitions and exactly one warmup")
    required = (args.build_dir, args.build_log, args.source_commit, args.harness_commit,
                args.concurrent_work, args.out)
    if any(value is None for value in required):
        parser.error("measurement requires build identity/log, source and harness commits, concurrent-work note, and output directory")
    out, build_log = args.out.resolve(), args.build_log.resolve()
    if out.exists() or args.out.is_symlink():
        parser.error("output directory must not already exist")
    if build_log.is_relative_to(out) or out.is_relative_to(build_log):
        parser.error("build log and output directory must not overlap")
    try:
        concurrent_work_note = args.concurrent_work.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        parser.error("concurrent-work note must be readable")
    provenance = build_provenance(args.build_dir.resolve(), args.exe.resolve(),
                                  args.source_commit, args.harness_commit, build_log)
    command = [str(args.exe), "--measure", "--repetitions", str(args.repetitions), "--warmups", "1"]
    before = _sha(args.exe)
    if before != provenance["executable"]["sha256"]:
        raise SystemExit("measurement executable changed after the fresh Release rebuild")
    raw_stdout, raw_stderr, return_code, timed_out = _run_capture(command)
    _write_capture(out, raw_stdout, raw_stderr, command, return_code, timed_out)
    after = _sha(args.exe)
    if before != after:
        error = ValueError("measurement executable changed while collection was running")
        _write_validation_error(out, error)
        raise error
    rows, parse_errors = [], []
    for line_number, line in enumerate(raw_stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(bind_fixture_identity(strict_json_loads(line)))
        except ValueError as error:
            parse_errors.append({"line": line_number, "error": str(error),
                                 "line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest()})
    provenance["executable"]["sha256"] = before
    provenance["environment"] = {"os": platform.platform(), "processor": platform.processor() or "unavailable",
                                  "cpu_count": os.cpu_count(), "python": platform.python_version(),
                                  "arithmetic": "IEEE-754 binary64", "native_backend": "none selected",
                                  "native_threads": {"configured": 0, "observed": {"available": False,
                                      "reason": "this geometry provider exposes no native thread counter"}},
                                  "resources": {"requested_total_threads": 1, "actual_outer_workers": 1,
                                      "threads_per_worker": 1, "memory_bytes": None},
                                  "numeric_context_tolerance": {"absolute": 1e-8, "relative": 1e-8},
                                  "independent_sample_tolerance": 1e-9, "random_seed": None,
                                  "concurrent_work_note": concurrent_work_note,
                                  "collection_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    if return_code:
        provenance["process_exit_code"] = return_code
    if timed_out:
        provenance["timed_out"] = True
    provenance["raw_stdout_sha256"] = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
    provenance["raw_stderr_sha256"] = hashlib.sha256(raw_stderr.encode("utf-8")).hexdigest()
    _finish_collection(out, rows, provenance, args.repetitions, return_code, parse_errors, timed_out)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

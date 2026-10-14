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
sys.path.append(str(Path(__file__).resolve().parents[3] / "scripts" / "reports"))
import collector_common


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


_git_paths = collector_common.git_paths

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_run_capture = collector_common.capture_process
_redact_paths = collector_common.redact_paths


def _release_graph(build: Path, exe: Path, source_root: Path) -> dict:
    return collector_common.release_graph(build, exe, source_root,
        target_name="csl_geo05_projection_predecessor_report",
        required={"csl_geo05_projection_predecessor_report", "csl_polyhedral", "csl_sets",
                  "csl_optimization", "csl_registry", "csl_numeric", "csl_contracts"},
        load_json=strict_json_loads)


def _validate_build_log(build_log: Path, build: Path, exe: Path, source_root: Path) -> None:
    collector_common.validate_build_log(build_log, build, exe, source_root,
        tracked_paths=_git_paths("-C", str(source_root), "ls-files", "-z"))


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
    if source_commit != harness_commit:
        validate_cmake_delta(source_cmake, harness_cmake)
    _release_graph(build, exe, source_root)
    fresh_build = collector_common.fresh_release_build(
        build, "csl_geo05_projection_predecessor_report", build_log, source_root,
        source_commit=source_commit, harness_commit=harness_commit, run=_run_capture,
        validate_log=lambda: _validate_build_log(build_log.resolve(), build, exe, source_root))
    if _git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness HEAD changed during the fresh Release rebuild")
    if _git("status", "--porcelain=v1"):
        raise ValueError("source and harness worktree must remain clean during the fresh Release rebuild")
    if not exe.is_file():
        raise ValueError("fresh Release rebuild did not produce the configured executable")
    graph = _release_graph(build, exe, source_root)
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


_durable_text = collector_common.durable_text


def _write_capture(out: Path, stdout: str, stderr: str, command: list[str],
                   process_return_code: int, timed_out: bool) -> None:
    collector_common.write_capture(out, stdout, stderr, command, process_return_code, timed_out,
                                   schema="csl.geo05-process-capture/1")


def _write_validation_error(out: Path, error: Exception) -> None:
    collector_common.write_validation_error(out, error, schema="csl.geo05-rejected-capture/1")


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

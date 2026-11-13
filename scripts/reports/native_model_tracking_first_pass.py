#!/usr/bin/env python3
"""Capture the native C++ 35-model functional tracking first pass."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_BUILD = pathlib.Path(
    "/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/1012-model-first-pass-build"
)
DEFAULT_SDK_SNAPSHOT = pathlib.Path(
    "/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/1012-current-main-installed-sdk-4ec-snapshot/prefix"
)
SDK_PREFIX = pathlib.Path(
    "/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/1012-history-qp-build/installed-consumer/prefix"
)
QUALIFICATION = pathlib.Path(
    "/home/butahlecoq/.local/state/controlled-systems-lab/working-documents/1012-running-state-design-20261113/candidate-a/qualification-c16-source-binding.json"
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_one(command: list[str], case: pathlib.Path, timeout_s: int) -> dict[str, object]:
    status_path = case / "attempt.json"
    attempt = {
        "status": "started",
        "command": command,
        "timeout_seconds": timeout_s,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    save_json(status_path, attempt)
    stdout_path, stderr_path = case / "stdout.log", case / "stderr.log"
    environment = os.environ.copy()
    environment.update(
        {
            "TMPDIR": "/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/test-tmp",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "HIGHS_THREADS": "1",
        }
    )
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
        try:
            returncode = process.wait(timeout=timeout_s)
            result = "completed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            returncode, result = process.returncode, "timed_out"
    attempt.update(
        {
            "status": result,
            "returncode": returncode,
            "elapsed_seconds": time.monotonic() - started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "stdout_sha256": sha256(stdout_path),
            "stderr_sha256": sha256(stderr_path),
        }
    )
    save_json(status_path, attempt)
    return attempt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=pathlib.Path, default=DEFAULT_BUILD)
    parser.add_argument("--sdk-snapshot", type=pathlib.Path, default=DEFAULT_SDK_SNAPSHOT)
    parser.add_argument("--output-parent", type=pathlib.Path, default=ROOT / "reports/algorithm-results/native-model-tracking-first-pass-v1")
    parser.add_argument("--models", type=int, nargs="+", choices=range(1, 36), default=list(range(1, 36)))
    parser.add_argument("--skip-catalogue", action="store_true")
    parser.add_argument("--catalogue-only", action="store_true")
    args = parser.parse_args()
    build = args.build.resolve()
    sdk_snapshot = args.sdk_snapshot.resolve()
    sdk_inventory = sdk_snapshot.parent / "SHA256SUMS"
    if not sdk_inventory.is_file() or not (sdk_snapshot / "lib/cmake/CSL/CSLConfig.cmake").is_file():
        raise SystemExit("A frozen installed SDK snapshot and its SHA256SUMS inventory are required")
    binaries = {
        "tracking": build / "native_model_tracking",
        "catalogue": build / "native_discrete_models",
        "source21": build / "quadcopter_mpc",
    }
    for name, binary in binaries.items():
        if not binary.is_file():
            raise SystemExit(f"Required built executable is missing: {binary}")
    args.output_parent.mkdir(parents=True, exist_ok=True)
    capture_id = datetime.now(timezone.utc).strftime("capture-%Y%m%dT%H%M%SZ")
    capture = args.output_parent / capture_id
    suffix = 0
    while True:
        candidate = capture if suffix == 0 else args.output_parent / f"{capture_id}-{suffix:02d}"
        try:
            candidate.mkdir()
            capture = candidate
            break
        except FileExistsError:
            suffix += 1

    qualification = json.loads(QUALIFICATION.read_text(encoding="utf-8"))
    sdk_archive = qualification["installed_sdk"]["archive"]["sha256"]
    manifest: dict[str, object] = {
        "schema": "csl.1012-native-model-tracking-capture/1",
        "capture_id": capture.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "functional first native MPC/tracking pass across all 35 source-catalogue records; no performance comparison",
        "capture_mode": "catalogue_metadata_only" if args.catalogue_only else "controller_attempts",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "working_source_sha256": {
            "examples/native_model_tracking.cpp": sha256(ROOT / "examples/native_model_tracking.cpp"),
            "examples/native_discrete_models.cpp": sha256(ROOT / "examples/native_discrete_models.cpp"),
            "examples/quadcopter_mpc.cpp": sha256(ROOT / "examples/quadcopter_mpc.cpp"),
            "examples/quadcopter_mpc_task.cpp": sha256(ROOT / "examples/quadcopter_mpc_task.cpp"),
            "examples/CMakeLists.txt": sha256(ROOT / "examples/CMakeLists.txt"),
            "scripts/reports/native_model_tracking_first_pass.py": sha256(pathlib.Path(__file__).resolve()),
        },
        "executables": {name: {"path": str(path), "sha256": sha256(path)} for name, path in binaries.items()},
        "installed_sdk_component_qualification": {
            "qualification_receipt": str(QUALIFICATION),
            "receipt_sha256": sha256(QUALIFICATION),
            "source_commit": qualification["cpp_source_commit"],
            "source_tree_sha1": qualification["cpp_source_tree_sha1"],
            "archive_sha256": sdk_archive,
            "whole_sdk_qualification_claimed": False,
        },
        "frozen_installed_sdk_snapshot": {
            "prefix": str(sdk_snapshot),
            "inventory_file": str(sdk_inventory),
            "inventory_file_sha256": sha256(sdk_inventory),
            "file_count": sum(1 for path in sdk_snapshot.rglob("*") if path.is_file()),
            "linked_archives_sha256": {
                archive.name: sha256(archive) for archive in sorted((sdk_snapshot / "lib").glob("*.a"))
            },
            "snapshot_identity": "composed current-main 4ec installed package snapshot; this capture does not claim a whole-SDK qualification",
        },
        "native_build_receipt": {
            "cmake_cache_sha256": sha256(build / "CMakeCache.txt"),
            "cmake_version": subprocess.check_output(
                ["/home/butahlecoq/.local/share/mise/installs/cmake/3.31.6/cmake-3.31.6-linux-x86_64/bin/cmake", "--version"], text=True
            ).splitlines()[0],
            "compiler": "GNU C++ 16.2.1",
            "build_type": "Release",
            "generator": "Unix Makefiles",
            "build_targets": ["native_model_tracking", "native_discrete_models", "quadcopter_mpc"],
            "link_command_sha256": {
                name: sha256(build / "CMakeFiles" / f"{binary}.dir" / "link.txt")
                for name, binary in (("tracking", "native_model_tracking"),
                                     ("catalogue", "native_discrete_models"),
                                     ("source21", "quadcopter_mpc"))
            },
        },
        "runtime_limits": {"native_tracking_seconds_per_case": 60, "source21_seconds": 120, "threads": 1},
        "requested_model_indices": args.models,
        "task_profiles": {
            "model21": "source21 literal horizon=10, Q/QN/R and bounds; 15 observed-state replans from existing native C++ source task",
            "other34": "authored zero-target quadratic; horizon=3; three closed-loop replans; state weight_i=1/max(1,abs(initial_i))^2; terminal=5x state weight; R=0.02I; recorded-input bounds [-1,1]; no state bounds",
            "external_policy": "fold printed affine offset plus E*w_nominal when catalogue nominal external exists; otherwise explicitly select fixed external zero and retain original E in catalogue data",
        },
        "outcomes": [],
    }
    save_json(capture / "manifest.json", manifest)

    if not args.skip_catalogue:
        catalogue_dir = capture / "catalogue-data"
        catalogue_dir.mkdir()
        cat_case = capture / "catalogue-attempt"
        cat_case.mkdir()
        catalogue_out = catalogue_dir / "native-output"
        outcome = run_one([str(binaries["catalogue"]), str(catalogue_out)], cat_case, 60)
        manifest["catalogue_capture"] = outcome
        if outcome["status"] != "completed":
            manifest["outcomes"].append({"model": "catalogue-data", **outcome})
        save_json(capture / "manifest.json", manifest)

    if args.catalogue_only:
        manifest["summary"] = {"catalogue_metadata_capture": manifest.get("catalogue_capture", {}).get("status", "not_run")}
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(capture / "manifest.json", manifest)
        print(json.dumps({"capture": str(capture), "summary": manifest["summary"]}, sort_keys=True))
        return 0

    for index in args.models:
        model_id = f"catalogue-2026/model-{index}/1"
        case = capture / f"model-{index:02d}"
        case.mkdir()
        output = case / ("source21-output" if index == 21 else "tracking-output")
        binary = binaries["source21"] if index == 21 else binaries["tracking"]
        command = [str(binary), str(output)] if index == 21 else [str(binary), model_id, str(output)]
        status = run_one(command, case, 120 if index == 21 else 60)
        manifest["outcomes"].append({"model": model_id, **status})
        save_json(capture / "manifest.json", manifest)
        print(f"{model_id} {status['status']} {status.get('elapsed_seconds', 0):.3f}s", flush=True)

    with (capture / "outcomes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["model", "status", "returncode", "elapsed_seconds", "timeout_seconds"])
        writer.writeheader()
        for item in manifest["outcomes"]:
            writer.writerow({key: item.get(key, "") for key in writer.fieldnames})
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["summary"] = {
        "attempted_model_records": len(manifest["outcomes"]),
        "completed_models": sum(item.get("status") == "completed" for item in manifest["outcomes"]),
        "failed_models": sum(item.get("status") == "failed" for item in manifest["outcomes"]),
        "timed_out_models": sum(item.get("status") == "timed_out" for item in manifest["outcomes"]),
    }
    save_json(capture / "manifest.json", manifest)
    print(json.dumps({"capture": str(capture), "summary": manifest["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

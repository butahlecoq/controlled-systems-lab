"""Run the committed native Lotka H-tube producer into a new raw directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from contracts import ROOT, canonical_bytes
from nominal_tube_source import build_request


SOURCE_PATHS = (
    "CMakeLists.txt",
    "include/csl/geometry/polyhedral_intersection.hpp",
    "include/csl/reachability/nominal_forward.hpp",
    "include/csl/reachability/nominal_predecessor.hpp",
    "include/csl/reachability/nominal_tube.hpp",
    "src/geometry/conversion/affine_coordinates.cpp",
    "src/geometry/polyhedral/intersection.cpp",
    "src/geometry/polyhedral/projection.cpp",
    "src/reachability/nominal_forward.cpp",
    "src/reachability/nominal_predecessor.cpp",
    "src/reachability/nominal_tube.cpp",
    "tools/nominal_tube_capture.cpp",
    "benchmarks/reporting/closed_loop/contracts.py",
    "benchmarks/reporting/closed_loop/task_models.py",
    "benchmarks/reporting/closed_loop/nominal_tube_source.py",
    "benchmarks/reporting/closed_loop/nominal_tube_capture.py",
    "docs/contracts/closed-loop/syn-nl-lv-01.json",
    "docs/contracts/closed-loop/syn-nl-lv-01.sha256",
    "benchmarks/reporting/mpc11/affine.py",
    "benchmarks/reporting/mpc11/scenarios/syn-nl-lv-01.json",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(root: Path = ROOT) -> dict:
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
        check=True, capture_output=True, text=True).stdout
    if status:
        raise ValueError("capture requires a committed clean source worktree")
    files = {name: sha256_file(root / name) for name in SOURCE_PATHS}
    return {"commit": revision, "source_files_sha256": files,
        "source_tree_clean_before_capture": True}


def provider_inventory(record: dict | None) -> list[dict]:
    if not record:
        return []
    found = []
    for stage in record.get("stages", []):
        for provider in stage.get("providers", []):
            found.append({"stage": stage.get("stage"), **provider})
    failure = record.get("failure", {})
    for provider in failure.get("forward_providers", []):
        found.append({"stage": failure.get("stage"), **provider})
    return found


def capture(binary: Path, destination: Path, *, max_projection_rows: int,
        deadline_seconds: float, process_timeout_seconds: float, root: Path = ROOT) -> dict:
    binary = binary.resolve()
    destination = destination.resolve()
    if not binary.is_file():
        raise ValueError("native capture executable does not exist")
    if destination.exists():
        raise FileExistsError("raw capture destination already exists; archived outputs are append-only")
    if max_projection_rows <= 0 or deadline_seconds <= 0 or process_timeout_seconds <= deadline_seconds:
        raise ValueError("row capacity must be positive and process timeout must exceed the operation deadline")
    source = source_identity(root)
    request = build_request()
    destination.mkdir(parents=True)
    request_path = destination / "request.json"
    request_path.write_bytes(canonical_bytes(request) + b"\n")
    output_path = destination / "raw-record.json"
    command = [str(binary), "--input", str(request_path), "--output", str(output_path),
        "--max-projection-rows", str(max_projection_rows), "--deadline-seconds", str(deadline_seconds)]
    timed_out = False
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True,
            timeout=process_timeout_seconds, check=False)
        return_code = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as failure:
        timed_out = True
        return_code = None
        stdout = failure.stdout.decode() if isinstance(failure.stdout, bytes) else (failure.stdout or "")
        stderr = failure.stderr.decode() if isinstance(failure.stderr, bytes) else (failure.stderr or "")
    (destination / "stdout.txt").write_text(stdout)
    (destination / "stderr.txt").write_text(stderr)
    (destination / "command.json").write_bytes(canonical_bytes({
        "argv": command, "cwd": str(root), "operation_deadline_seconds": deadline_seconds,
        "process_timeout_seconds": process_timeout_seconds,
    }) + b"\n")
    record = None
    if output_path.exists():
        try:
            record = json.loads(output_path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError):
            record = None
    manifest = {
        "schema": "csl.nominal-h-tube-capture/1",
        "source": source,
        "binary": {"path": str(binary), "sha256": sha256_file(binary)},
        "request": {"path": "request.json", "sha256": sha256_file(request_path)},
        "record": {"path": "raw-record.json", "sha256": sha256_file(output_path) if output_path.exists() else None,
            "completion": record.get("completion") if record else "missing_or_unparseable",
            "providers": provider_inventory(record)},
        "process": {"return_code": return_code, "timed_out": timed_out},
        "resource_profile": {"max_projection_rows": max_projection_rows,
            "operation_deadline_seconds": deadline_seconds,
            "process_timeout_seconds": process_timeout_seconds,
            "memory_limit_enforced": False},
    }
    manifest_path = destination / "capture-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest) + b"\n")
    manifest["capture_manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--max-projection-rows", type=int, required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--process-timeout-seconds", type=float, required=True)
    options = parser.parse_args()
    result = capture(options.binary, options.capture_dir,
        max_projection_rows=options.max_projection_rows,
        deadline_seconds=options.deadline_seconds,
        process_timeout_seconds=options.process_timeout_seconds)
    print(json.dumps(result, indent=2))
    return 0 if result["record"]["completion"] not in {"missing_or_unparseable"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

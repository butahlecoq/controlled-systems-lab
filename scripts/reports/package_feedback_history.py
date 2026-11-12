#!/usr/bin/env python3
"""Archive a completed, independently audited feedback-history episode."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from package_history_functional import archive_attempt, digest


def package(attempt: Path, output: Path, audit: Path, auditor: Path,
            build: Path, sdk: Path, producer_commit: str) -> None:
    sources = (attempt, output, audit, auditor, build, sdk)
    if any(path.is_symlink() for path in sources):
        raise ValueError("source and output paths cannot be symlinks")
    attempt = attempt.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(attempt) or attempt.is_relative_to(output):
        raise ValueError("output must be new and separate from the attempt")
    for item in attempt.rglob("*"):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise ValueError("attempt contains an unsafe member")
    episode = json.loads((attempt / "attempt.json").read_text())
    run = json.loads((attempt / "run-manifest.json").read_text())
    graph = json.loads((attempt / "resolved-graph.json").read_text())
    verified = json.loads(audit.read_text())
    build_record = json.loads(build.read_text())
    task = verified["tasks"]["syn-nl-lv-01"]
    native = episode["preparation_receipt"]["adapter_receipt"]
    if (episode["status"] != "complete" or episode["overall_status"] != "complete"
            or episode["postcheck_status"] != "complete" or episode["render_status"] != "complete"
            or episode["completed_holds"] != 30 or task["audit_status"] != "pass"
            or task["completed_holds"] != 30 or task["expected_holds"] != 30
            or task["errors"] or task["geometry_memberships_checked"] != 1485
            or task["support_certificates_replayed"] != 5940):
        raise ValueError("completed full-horizon independently checked feedback evidence required")
    if (episode["controller_id"] != "native-continuous-history-box-ipopt/1"
            or graph["controller"]["id"] != episode["controller_id"] or native["geometry"] != "box"
            or native["history_solver"] != "casadi-ipopt"
            or run["source_commit"] != verified["source_commit"]
            or run["source_commit"] != build_record["source_commit"]
            or native["executable_sha256"] != build_record["native_binary"]["sha256"]
            or episode["task_sha256"] != run["task_sha256"]
            or episode["task_sha256"] != task["task_sha256"]
            or graph["graph_fingerprint"] != run["graph_fingerprint"]
            or digest(sdk.read_bytes()) != build_record["sdk_manifest_sha256"]):
        raise ValueError("source, provider, graph or build identity differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        inventory = archive_attempt(attempt, stage / "raw.zip")
        for target, source in (("audit.json", audit), ("audit.py", auditor),
                               ("build-receipt.json", build), ("sdk-manifest.json", sdk)):
            if not source.is_file():
                raise ValueError("missing evidence input")
            shutil.copyfile(source, stage / target)
        for name in ("trajectory.png", "controls.png", "phase.png"):
            shutil.copyfile(attempt / name, stage / name)
        receipt = {"schema": "csl.feedback-history-functional/1",
            "producer_commit": producer_commit, "source_commit": run["source_commit"],
            "task_id": episode["task_id"], "task_sha256": episode["task_sha256"],
            "controller_id": episode["controller_id"], "action_profile_id": episode["action_profile_id"],
            "graph_id": graph["graph_id"], "graph_fingerprint": graph["graph_fingerprint"],
            "native_sha256": native["executable_sha256"], "native_binary_source_in_raw": native["binary_source"],
            "original_intervals": 30, "completed_holds": 30, "family": "box",
            "optimizer": "casadi-ipopt", "scope": "one numerical F/B/I affine-history MPC episode",
            "raw_metadata_correction": "The adapter preparation controller_semantics says direct affine-history MPC; the run used box F/B/I memberships as established by the resolved graph and native records.",
            "audit": task, "archive_sha256": digest((stage / "raw.zip").read_bytes()),
            "archive_members": inventory}
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        names = sorted(p.name for p in stage.iterdir() if p.is_file())
        (stage / "SHA256SUMS").write_text("".join(digest((stage / n).read_bytes()) + "  " + n + "\n" for n in names))
        os.rename(stage, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("attempt", "output", "audit", "auditor", "build", "sdk"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--producer-commit", required=True)
    args = parser.parse_args()
    package(args.attempt, args.output, args.audit, args.auditor, args.build, args.sdk, args.producer_commit)


if __name__ == "__main__":
    main()

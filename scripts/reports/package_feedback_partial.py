#!/usr/bin/env python3
"""Archive an independently checked incomplete feedback episode."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
from package_history_functional import archive_attempt, digest


def package(attempt, output, audit, auditor, build, source_receipt, producer_commit):
    paths = (attempt, output, audit, auditor, build, source_receipt)
    if any(path.is_symlink() for path in paths):
        raise ValueError("symlink input or output")
    attempt = attempt.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(attempt) or attempt.is_relative_to(output):
        raise ValueError("output must be new and separate")
    for item in attempt.rglob("*"):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise ValueError("unsafe attempt member")
    episode = json.loads((attempt / "attempt.json").read_text())
    run = json.loads((attempt / "run-manifest.json").read_text())
    checked = json.loads(audit.read_text())
    result = checked["tasks"]["earth-orbit"]
    provenance = json.loads(build.read_text())
    completed = episode["completed_holds"]
    if (episode["status"] != "incomplete" or episode["overall_status"] != "incomplete"
            or episode["postcheck_status"] != "not_run" or episode["render_status"] != "not_run"
            or episode["original_intervals"] != 20 or completed not in (3, 4)
            or result["audit_status"] != "pass-partial" or result["completed_holds"] != completed
            or result["errors"] or result["expected_holds"] != 20
            or episode["task_sha256"] != result["task_sha256"] or run["source_commit"] != checked["source_commit"]
            or episode["controller_id"] != "native-continuous-history-box-ipopt/1"
            or episode["preparation_receipt"]["adapter_receipt"]["executable_sha256"] != provenance["native_binary"]["sha256"]):
        raise ValueError("incomplete, audited orbit box episode identity differs")
    failed = json.loads((attempt / f"stage-{completed:03d}.json").read_text())
    if failed.get("status") != "failed":
        raise ValueError("expected a saved failed controller stage")
    if completed == 3:
        validation = failed["solve_receipt"]["independent_validation"]["checks"]["source_cost"]
        if validation["passed"]:
            raise ValueError("expected rejected source-cost discrepancy")
        stop = {"kind": "source_cost_check_failed", "residual": validation["max_residual"]}
    else:
        solver = failed["solve_receipt"]["solver"]
        if solver["status"] != "solver-error" or "Infeasible_Problem_Detected" not in solver.get("error", ""):
            raise ValueError("expected saved local optimizer failure")
        stop = {"kind": "local_optimizer_failure", "reported_status": "Infeasible_Problem_Detected"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        inventory = archive_attempt(attempt, stage / "raw.zip")
        for name, source in (("audit.json", audit), ("audit.py", auditor), ("build-receipt.json", build),
                             ("run-source-receipt.json", source_receipt)):
            if not source.is_file():
                raise ValueError("missing provenance input")
            shutil.copyfile(source, stage / name)
        receipt = {"schema": "csl.feedback-history-partial/1", "producer_commit": producer_commit,
            "task_id": episode["task_id"], "task_sha256": episode["task_sha256"],
            "source_commit": run["source_commit"], "native_sha256": provenance["native_binary"]["sha256"],
            "original_intervals": 20, "completed_holds": completed, "family": "box",
            "optimizer": "casadi-ipopt", "outcome": "incomplete", "stop": stop,
            "scope": "partial numerical observations; no source infeasibility or full-objective claim",
            "warm_start_protocol": "cold at observed queries; source warm-start contract not implemented",
            "audit": result, "archive_sha256": digest((stage / "raw.zip").read_bytes()),
            "archive_members": inventory}
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        names = sorted(p.name for p in stage.iterdir() if p.is_file())
        (stage / "SHA256SUMS").write_text("".join(digest((stage/n).read_bytes()) + "  " + n + "\n" for n in names))
        os.rename(stage, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("attempt", "output", "audit", "auditor", "build", "source-receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--producer-commit", required=True)
    args = parser.parse_args()
    package(args.attempt, args.output, args.audit, args.auditor, args.build, args.source_receipt, args.producer_commit)


if __name__ == "__main__":
    main()

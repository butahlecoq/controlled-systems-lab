#!/usr/bin/env python3
"""Replay a fixed held-control fixture through the common task adapter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from contracts import load_task, manifest_sha256
from task_models import make_replay_request, objective, prediction_receipt, validate_source_binding


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=["syn-nl-lv-01", "syn-nl-fuel-01", "earth-orbit"])
    parser.add_argument("--control", required=True, help="comma-separated physical input held on every interval")
    parser.add_argument("--bridge", required=True, type=Path, help="built csl_mpc11_nonlinear_replay executable")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    task = load_task(args.task)
    validate_source_binding(task)
    action = [float(value) for value in args.control.split(",")]
    controls = [action[:]] * task["episode"]["intervals"]
    witness = manifest_sha256({"task_sha256": manifest_sha256(task), "controls": controls})
    request = make_replay_request(task, controls, witness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="csl-task-replay-") as directory:
        request_path = Path(directory) / "request.json"
        request_path.write_text(json.dumps(request, allow_nan=False))
        result = json.loads(subprocess.run([str(args.bridge), str(request_path)], check=True, capture_output=True, text=True).stdout)
    if result["status"] != "complete":
        raise RuntimeError(f"independent CSL replay ended with {result['status']}")
    subintervals = request["report_subintervals_per_hold"]
    hold_endpoints = [result["physical_states"][k * subintervals] for k in range(task["episode"]["intervals"] + 1)]
    costs = objective(task, hold_endpoints, controls)
    output = {"schema": "csl.closed-loop.fixture-episode/1", "task_id": task["task_id"],
              "task_sha256": manifest_sha256(task), "source_sha256": task["source"]["sha256"],
              "controls": controls, "prediction_receipt": prediction_receipt(task),
              "independent_replay": result, "physical_objective": costs,
              "claim": "fixed-control trajectory fixture; not a policy, reachable set, controller result, or benchmark"}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"task_id": task["task_id"], "task_sha256": output["task_sha256"],
                      "replay_status": result["status"], "physical_objective": costs, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Save short source-bound affine-history policy and held-step probes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback

import numpy as np

from contracts import load_task, manifest_sha256
from history_policy import create_policy
from run_closed_loop import execute_held_step_bridge, physical_constraints
from task_models import make_held_step_request, validate_held_step_response, validate_source_binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-policy", type=Path, required=True)
    parser.add_argument("--physical-bridge", type=Path, required=True)
    parser.add_argument("--holds", type=int, default=2)
    args = parser.parse_args()
    if args.holds < 1:
        raise ValueError("holds must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["CSL_NATIVE_POLICY_BRIDGE"] = str(args.native_policy.resolve(strict=True))
    physical_bridge = args.physical_bridge.resolve(strict=True)
    root_receipt = {"schema": "csl.closed-loop.history-probe/1", "claims": "short functional probe; no benchmark or global guarantee",
        "native_policy_sha256": hashlib.sha256(args.native_policy.read_bytes()).hexdigest(),
        "native_policy_source": "unknown", "physical_bridge_sha256": hashlib.sha256(physical_bridge.read_bytes()).hexdigest(),
        "physical_bridge_source": "unknown", "tasks": {}}
    (args.output / "receipt.json").write_text(json.dumps(root_receipt, indent=2) + "\n")
    for name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        directory = args.output / name
        directory.mkdir()
        task = load_task(name)
        validate_source_binding(task)
        task_hash = manifest_sha256(task)
        action_id = task["control_domains"]["continuous"]["problem_id"]
        state = [field["initial"] for field in task["model"]["states"]]
        states, controls, records = [state], [], []
        summary = {"task_sha256": task_hash, "action_profile_id": action_id,
                   "source_sha256": task["source"]["sha256"], "status": "running", "records": records}
        policy = None
        try:
            policy = create_policy(task, task_sha256=task_hash, controller_id="native-continuous-affine-history-mpc/1",
                                   action_profile_id=action_id)
            summary["preparation_receipt"] = policy.preparation_receipt
            for stage in range(min(args.holds, task["episode"]["intervals"])):
                record = {"stage": stage, "observed": state}
                records.append(record)
                query = policy.query(task["task_id"], state, stage)
                record["query"] = query
                (directory / "record.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
                if query["status"] != "accepted":
                    raise RuntimeError("policy did not accept the query: " + query.get("reason", query["status"]))
                witness = hashlib.sha256((task_hash + json.dumps(controls, separators=(",", ":"))).encode()).hexdigest()
                held = make_held_step_request(task, state, query["control"], stage, witness, action_profile_id=action_id)
                record["held_request"] = held
                request_path = directory / f"execution-request-{stage:03d}.json"
                request_path.write_text(json.dumps(held["bridge_request"], indent=2) + "\n")
                response = execute_held_step_bridge(physical_bridge, request_path, directory, stage, record)
                execution = validate_held_step_response(held, response)
                record["execution"] = execution
                tighter = make_held_step_request(task, state, query["control"], stage, witness,
                                                 action_profile_id=action_id, sensitivity=True)
                tighter_dir = directory / f"tighter-{stage:03d}"
                tighter_dir.mkdir()
                tighter_path = tighter_dir / "execution-request.json"
                tighter_path.write_text(json.dumps(tighter["bridge_request"], indent=2) + "\n")
                tighter_record = {"held_request": tighter}
                tighter_raw = execute_held_step_bridge(physical_bridge, tighter_path, tighter_dir, stage, tighter_record)
                tighter_execution = validate_held_step_response(tighter, tighter_raw)
                tighter_record["execution"] = tighter_execution
                tighter_record["maximum_endpoint_difference"] = float(np.max(np.abs(
                    np.asarray(execution["physical_states"][-1]) - np.asarray(tighter_execution["physical_states"][-1]))))
                record["independent_tighter_replay"] = tighter_record
                controls.append(query["control"])
                state = execution["physical_states"][-1]
                states.append(state)
                record["sampled_constraints"] = physical_constraints(task, execution["physical_states"], [query["control"]])
                (directory / "record.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
            summary["status"] = "complete"
        except Exception as error:
            summary["status"] = "failed"
            summary["failure"] = {"type": type(error).__name__, "reason": str(error), "traceback": traceback.format_exc()}
            if policy is not None and policy.last_query_capture is not None:
                summary["last_query_capture"] = policy.last_query_capture
        finally:
            if policy is not None:
                try:
                    policy.close()
                except Exception as error:
                    summary["close_error"] = str(error)
            summary["observed_states"] = states
            summary["applied_controls"] = controls
            (directory / "record.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
            root_receipt["tasks"][name] = {"status": summary["status"], "holds": len(controls), "task_sha256": task_hash}
            (args.output / "receipt.json").write_text(json.dumps(root_receipt, indent=2) + "\n")
        print(json.dumps({"task": name, **root_receipt["tasks"][name]}), flush=True)
    return 0 if all(row["status"] == "complete" for row in root_receipt["tasks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

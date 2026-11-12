"""Capture two last-stage source-cost diagnostics through a supplied native bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from contracts import ROOT, load_task, manifest_sha256
from native_graph_policy import NativeGraphPolicy
from task_models import source_scenario
import affine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bridge = args.bridge.resolve(strict=True)
    if not bridge.is_file() or not os.access(bridge, os.X_OK):
        parser.error("--bridge must name an executable file")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    paths = ["benchmarks/reporting/closed_loop/terminal_objective_probe.py",
        "benchmarks/reporting/closed_loop/native_graph_policy.py",
        "benchmarks/reporting/closed_loop/task_models.py",
        "tools/closed_loop_native_policy.cpp", "src/optimization/objective_reformulation.cpp"]
    source_files = []
    for path in paths:
        content = (ROOT / path).read_bytes()
        committed = subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)
        if content != committed:
            parser.error("Capture source differs from committed bytes: " + path)
        source_files.append({"path": path, "sha256": hashlib.sha256(content).hexdigest()})
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CSL_NATIVE_POLICY_BRIDGE"] = str(bridge)
    rows = []
    for name in ("syn-nl-lv-01", "syn-nl-fuel-01"):
        task = load_task(name)
        definition = task["objective"]["source_definition"]
        n = task["episode"]["intervals"]
        target = definition["terminal_target"]
        row = {"task": name, "task_sha256": manifest_sha256(task), "absolute_stage": n - 1,
               "observed_state": target, "source_definition": definition}
        policy = None
        try:
            policy = NativeGraphPolicy(task, manifest_sha256(task),
                "native-exact-polytope-fixed-plan-mpc/1", task["control_domains"]["finite"]["problem_id"])
            response = policy.query(task["task_id"], target, n - 1)
            native = policy.last_query_capture["parsed_response"]
            row.update({"adapter_status": response["status"], "native_status": native["status"]})
            if native["status"] != "accepted":
                raise ValueError("Native diagnostic did not return a selected plan")
            plan = native["selected_plan"]
            point = plan["states"][-1]
            terminal = sum(w * ((x - t) / scale) ** 2 for w, x, t, scale in zip(
                definition["terminal_weights"], point, target, definition["terminal_scale"]))
            references = affine.model(source_scenario(task))["reference_commands"]
            running = definition["running_weight"] / n * sum(
                ((u - reference) / scale) ** 2
                for control, reference_row in zip(plan["controls"], references[n - 1:])
                for u, reference, scale in zip(control, reference_row, definition["running_scale"]))
            expected = {"terminal": terminal, "running": running, "total": terminal + running}
            reported = {"terminal": plan["terminal_objective"], "running": plan["running_objective"],
                        "total": plan["total_objective"]}
            differences = {key: reported[key] - expected[key] for key in expected}
            row.update({"selected_plan": plan, "last_running_reference": references[-1],
                "expected_source_cost": expected, "reported_cost": reported, "differences": differences,
                "parity_passed": all(math.isclose(reported[key], value, rel_tol=1e-10, abs_tol=1e-10)
                                     for key, value in expected.items())})
        except Exception as error:
            row.update({"parity_passed": False, "error": f"{type(error).__name__}: {error}"})
        finally:
            if policy is not None:
                (output / (name + "-capture.json")).write_text(
                    json.dumps(policy.last_query_capture, indent=2, allow_nan=False) + "\n")
                policy.close()
        rows.append(row)
    record = {"schema": "csl.native-terminal-objective-diagnostic/1", "source_commit": revision,
        "source_files": source_files, "binary_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
        "binary_build_source_revision": None,
        "binary_origin": "Caller-supplied existing artifact; build revision is not inferred from its path.",
        "scope": "Two final-stage queries from source target states, not full episodes or performance measurements. "
                 "Running comparisons cover only the remaining decision and keep the original horizon normalization.",
        "rows": rows}
    (output / "record.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"source_commit": revision, "cases": len(rows),
                      "parity_passed": all(row["parity_passed"] for row in rows)}))
    return 0 if all(row["parity_passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

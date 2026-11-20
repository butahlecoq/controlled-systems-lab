"""Cross-check the two matched policies against original-coordinate matrices and constraints."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import sys

import numpy as np

POLICIES = ("open_loop", "closed_loop")


def matrix(row):
    return np.asarray(row["values"], dtype=float).reshape(row["rows"], row["cols"])


def bound_excess(values, bounds):
    result = 0.0
    for value, (lo, hi) in zip(values, bounds, strict=True):
        if lo is not None:
            result = max(result, (lo - value) / max(1, abs(lo)))
        if hi is not None:
            result = max(result, (value - hi) / max(1, abs(hi)))
    return float(result)


def audit_episode(task, policy, dynamics):
    record = task[policy]
    A, B, G = dynamics
    states = np.asarray(record["states"], dtype=float)
    controls = np.asarray(record["controls"], dtype=float)
    external = np.asarray(task["external"], dtype=float)
    offset = np.asarray(task["offset"] or [0] * len(task["initial"]), dtype=float)
    assert len(states) == len(controls) + 1 <= task["horizon"] + 1
    assert np.array_equal(states[0], task["initial"])
    assert np.isfinite(states).all() and np.isfinite(controls).all()
    residual = 0.0
    bounds = task["constraints"]
    violated = 0.0
    for stage, actual in enumerate(controls):
        state = states[stage]
        expected = A @ state + B @ actual + G @ external[stage] + offset
        residual = max(residual, float(np.max(np.abs(expected - states[stage + 1]) / np.maximum(1, np.abs(expected)))))
        violated = max(violated, bound_excess(state, bounds["state"][stage]))
        violated = max(violated, bound_excess(actual, bounds["control"][stage]))
        if bounds["stage"]:
            rows = bounds["stage"][stage]
            applied = matrix(rows["state"]) @ state + matrix(rows["control"]) @ actual + matrix(rows["external"]) @ external[stage]
            violated = max(violated, bound_excess(applied, rows["bounds"]))
        for budget in bounds["positive_part"][stage]:
            use = np.maximum(0, actual[budget["indices"]]).sum()
            violated = max(violated, bound_excess([use], [[None, budget["upper"]]]))
        decision = record["decisions"][stage]
        assert np.array_equal(decision["observed_state"], state)
        should_solve = stage == 0 or policy == "closed_loop"
        assert decision["attempted"] == should_solve and decision["solver_receipt"] == should_solve
    assert residual <= 5e-8 and violated <= 5e-8, (task["model_id"], policy, residual, violated)
    result = {"status": record["status"], "holds": len(controls), "dynamics_residual": residual, "constraint_excess": violated}
    if record["status"] == "complete":
        assert len(controls) == task["horizon"]
        violated = max(violated, bound_excess(states[-1], bounds["state"][-1]))
        for rows in bounds["terminal"]:
            violated = max(violated, bound_excess(matrix(rows["state"]) @ states[-1], rows["bounds"]))
        assert violated <= 5e-8
        delta = states - task["target"]
        scaled = np.einsum("ni,i,ni->n", delta, task["state_weights"], delta)
        effort = np.einsum("ni,i,ni->n", controls, task["control_weights"], controls)
        cost = float(.5 * sum(scaled[:-1]) + .5 * sum(effort) + scaled[-1])
        assert math.isclose(cost, record["realized_cost"], rel_tol=2e-8, abs_tol=1e-9), (task["model_id"], policy, cost, record["realized_cost"])
        result.update(cost=cost, constraint_excess=violated)
    return result


def main(root, source_csv):
    reference = {}
    with source_csv.open() as stream:
        for row in csv.DictReader(stream):
            key = (row["model"], row["kind"])
            reference.setdefault(key, {})[int(row["row"]), int(row["column"])] = float(row["value"])
    outputs = []
    total_coefficients = 0
    for number in range(1, 36):
        raw = root / f"{number}.json"
        exit_code = int((root / f"{number}.exit").read_text())
        result = {"number": number, "exit_code": exit_code,
                  "output_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
        if exit_code:
            result.update(status="execution-stop", stderr=(root / f"{number}.stderr").read_text())
        else:
            task = json.loads(raw.read_bytes())
            assert task["model_id"] == f"catalogue-2026/model-{number}/1"
            result.update(status=task["status"])
            if task["status"] == "attempted":
                values = [matrix(task[kind]) for kind in ("A", "B", "G")]
                for kind, item in zip(("A", "B", "G"), values, strict=True):
                    assert dict(np.ndenumerate(item)) == reference[task["model_id"], kind]
                    total_coefficients += item.size
                for policy in POLICIES:
                    result[policy] = audit_episode(task, policy, values)
                if all(result[p]["status"] == "complete" for p in POLICIES):
                    result["absolute_cost_difference"] = abs(result[POLICIES[0]]["cost"] - result[POLICIES[1]]["cost"])
                    result["maximum_control_difference"] = float(np.max(np.abs(
                        np.asarray(task[POLICIES[0]]["controls"]) - np.asarray(task[POLICIES[1]]["controls"])
                    )))
        outputs.append(result)
    summary = {
        "models": len(outputs), "literal_matrix_entries_checked": total_coefficients,
        "profiles": dict(Counter(row["status"] for row in outputs)),
        "policy_outcomes": {p: dict(Counter(row[p]["status"] for row in outputs if p in row)) for p in POLICIES},
        "paired_completions": sum("absolute_cost_difference" in row for row in outputs),
        "rows": outputs,
    }
    (root / "independent-audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}))


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))

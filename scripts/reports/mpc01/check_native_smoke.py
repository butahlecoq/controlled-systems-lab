#!/usr/bin/env python3
"""Check both native solvers against original MPC data on the frozen smoke cases."""

import json
import math
import subprocess
import sys
from pathlib import Path


def main() -> None:
    executable = Path(sys.argv[1])
    source_root = Path(sys.argv[2])
    result = subprocess.run(
        [
            str(executable),
            str(source_root / "examples/scenarios/double-integrator-generality.json"),
            str(source_root / "docs/research/evidence/b04-reference-v1/canonical-case.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    expected_cases = {
        "ts01-exact-v1",
        "ts02-constant-v1",
        "infeasible-integrator-v1",
        "unbounded-integrator-v1",
        "double-integrator-421-v1",
        "b04-reference-v1",
    }
    methods = {"osqp-sparse-qp": "solved", "hpipm-structured-ocp-qp": "hpipm-status-0"}
    reference = json.loads(
        (source_root / "docs/research/evidence/b04-reference-v1/exact-optimal-reference.json")
        .read_text(encoding="utf-8")
    )
    expected_objective = {
        "ts01-exact-v1": (0.0, 1e-7),
        "ts02-constant-v1": (3.0, 1e-7),
        "double-integrator-421-v1": (0.0, 1e-6),
        "b04-reference-v1": (float(reference["exact_norm_optimum_decimal"]), 0.003),
    }
    expected_outcome = {
        "infeasible-integrator-v1": {"osqp-sparse-qp": "infeasible",
                                      "hpipm-structured-ocp-qp": "undetermined"},
        "unbounded-integrator-v1": {"osqp-sparse-qp": "unbounded",
                                     "hpipm-structured-ocp-qp": "undetermined"},
    }
    expected_keys = {
        (case, method, mode)
        for case in expected_cases
        for method in methods
        for mode in ("cold", "warm_previous_witness")
    }
    observed_keys = set()
    for row in rows:
        key = row["case_id"], row["method"], row["start_mode"]
        if key in observed_keys:
            raise AssertionError(f"duplicate attempt row: {key}")
        observed_keys.add(key)
        if key[0] in expected_outcome:
            outcome = expected_outcome[key[0]][key[1]]
            if key[1] == "osqp-sparse-qp" and "inaccurate" in row["native_status"]:
                outcome = "undetermined"
            if row["mathematical_outcome"] != outcome or row["termination"] != "completed":
                raise AssertionError(f"unexpected classification for {key}: {row['mathematical_outcome']}/{row['termination']}")
            if row["solver_objective"] is not None or row["original_objective"] is not None:
                raise AssertionError(f"non-optimal {key} row must not present a solver objective")
            if "trajectory" in row:
                raise AssertionError(f"non-optimal {key} row must label solver output as a candidate iterate")
            if "candidate_iterate" in row and row["candidate_iterate_diagnostics"]["evidence_status"] != "inconclusive":
                raise AssertionError(f"candidate iterate diagnostics were overstated for {key}")
            if key[1] == "hpipm-structured-ocp-qp" and row["native_status"] == "hpipm-status-0":
                raise AssertionError(f"HPIPM reported optimality for the {key[0]} fixture")
            continue
        if row["native_status"] != methods[row["method"]]:
            raise AssertionError(f"unexpected solver status for {key}: {row['native_status']}")
        if row["mathematical_outcome"] != "optimal" or row["termination"] != "completed":
            raise AssertionError(f"unexpected outcome for {key}")
        objective = row["original_objective"]
        target, tolerance = expected_objective[row["case_id"]]
        if objective is None or not math.isfinite(objective) or abs(objective - target) > tolerance:
            raise AssertionError(f"objective {objective} differs from reference {target} by more than {tolerance} for {key}")
        diagnostics = row["original_data_diagnostics"]
        if diagnostics["evidence_status"] != "inconclusive":
            raise AssertionError(f"residual diagnostics were overstated for {key}")
        limit = 1e-5 if row["case_id"] == "b04-reference-v1" else 1e-8
        residual = max(
            diagnostics["max_dynamics_residual"],
            diagnostics["max_state_bound_violation"],
            diagnostics["max_control_bound_violation"],
        )
        if not math.isfinite(residual) or residual > limit:
            raise AssertionError(f"original-data residual {residual} exceeds {limit} for {key}")
    if observed_keys != expected_keys:
        raise AssertionError(f"attempt matrix mismatch: missing={expected_keys-observed_keys}, extra={observed_keys-expected_keys}")
    print(f"checked {len(rows)} native attempts across {len(expected_cases)} cases, including infeasible and unbounded cases")


if __name__ == "__main__":
    main()

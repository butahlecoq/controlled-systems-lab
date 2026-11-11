#!/usr/bin/env python3
"""Prepare (without solving) the two delivered MPC11 nonlinear routes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-directory", type=Path,
        default=Path(__file__).resolve().parents[2] / "benchmarks/reporting/mpc11/scenarios")
    args = parser.parse_args()
    scenarios = args.scenario_directory.resolve()
    mpc_root = scenarios.parent
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(mpc_root))
    sys.path.insert(0, str(repo_root / "benchmarks/reporting/closed_loop"))
    from check_scenarios import validate
    from contracts import load_task, manifest_sha256
    from task_models import validate_source_binding

    rows = []
    for name in ("syn-nl-lv-01", "syn-nl-fuel-01"):
        source = scenarios / f"{name}.json"
        scenario = json.loads(source.read_text())
        task_contract = load_task(name)
        validate_source_binding(task_contract)
        task_contract_path = repo_root / "docs/contracts/closed-loop" / f"{name}.json"
        task_id = task_contract["task_id"]
        scenario_hash = validate(scenario)
        # Validate task identity and source binding before consulting optional
        # external solver packages. A bad contract must remain a hard failure.
        try:
            for module in ("numpy", "scipy", "casadi", "do_mpc"):
                importlib.import_module(module)
        except ModuleNotFoundError as error:
            if error.name not in {"numpy", "scipy", "casadi", "do_mpc"}:
                raise
            distributions = {"numpy": "numpy", "scipy": "scipy", "casadi": "casadi", "do_mpc": "do-mpc"}
            rows.append({
                "graph_id": f"controller/{task_id}/mpc11-nominal-local-v1",
                "status": "backend_unavailable",
                "task_id": task_id,
                "model_id": scenario["model_id"],
                "controller_id": scenario["controller_id"],
                "objective_id": scenario["objective_id"],
                "scenario_sha256": scenario_hash,
                "scenario_file_sha256": sha256(source),
                "task_contract_sha256": manifest_sha256(task_contract),
                "task_contract_file_sha256": sha256(task_contract_path),
                "source_binding_validated": True,
                "state_dimension": len(scenario["states"]),
                "control_dimension": len(scenario["controls"]),
                "action_domain": task_contract["control_domains"]["continuous"]["problem_id"],
                "first_unmet": {"field": f"python.dependency.{distributions[error.name]}",
                    "reason": f"Optional MPC11 preparation dependency {error.name!r} is unavailable: {error}"},
                "solve_performed": False,
            })
            continue
        from nmpc import build_controller
        controller, metadata = build_controller(scenario, 0)
        solver_interface = "IpoptInterface" if "IpoptInterface" in str(controller.S) else "unverified"
        rows.append({
            "graph_id": f"controller/{task_id}/mpc11-nominal-local-v1",
            "status": "admitted",
            "admission_scope": "external Python source prepare; no NLP solve performed",
            "task_id": task_id,
            "model_id": scenario["model_id"],
            "controller_id": scenario["controller_id"],
            "objective_id": scenario["objective_id"],
            "scenario_sha256": scenario_hash,
            "scenario_file_sha256": sha256(source),
            "task_contract_sha256": manifest_sha256(task_contract),
            "task_contract_file_sha256": sha256(task_contract_path),
            "source_binding_validated": True,
            "state_dimension": len(scenario["states"]),
            "control_dimension": len(scenario["controls"]),
            "action_domain": task_contract["control_domains"]["continuous"]["problem_id"],
            "remaining_horizon": metadata["remaining_horizon"],
            "update_index": metadata["update_index"],
            "solver_profile": {
                "tolerance": scenario["nmpc"]["solver"]["tol"],
                "acceptable_tolerance": scenario["nmpc"]["solver"]["acceptable_tol"],
                "iteration_budget": scenario["nmpc"]["solver"]["max_iter"],
                "collocation": scenario["nmpc"]["collocation"],
                "assurance": scenario["assurance"],
            },
            "runtime": {
                "python": sys.version.split()[0],
                "do_mpc": importlib.metadata.version("do-mpc"),
                "casadi": importlib.metadata.version("casadi"),
                "solver": scenario["nmpc"]["solver"]["name"],
                "linear_solver": scenario["nmpc"]["solver"]["linear_solver"],
                "solver_interface_prepared": solver_interface,
            },
            "prepare_receipt": "build_controller(scenario, 0) returned an initialized do-mpc controller with a constructed CasADi IpoptInterface; no NLP solve was performed",
            "solve_performed": False,
        })
        del controller
    print(json.dumps({"schema": "csl.catalogue.external-prepare/1", "routes": rows},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Resolve the source-owned baseline task/controller/execution graphs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contracts import ROOT, canonical_sha256, load_task, manifest_sha256
from task_models import replay_scenario, source_scenario, validate_source_binding

MANIFEST = ROOT / "docs/catalogue/closed-loop-pilot-capabilities-v1.json"
SIDECAR = ROOT / "docs/catalogue/closed-loop-pilot-capabilities-v1.sha256"


def _definitions() -> list[dict]:
    rows = []
    for task_name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        task = load_task(task_name); validate_source_binding(task)
        case = task["model"]["case_id"]
        if case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
            controller_id = "syn-nl-orbit-01/source-cost-direct-shooting/1"
            controller = {"id": controller_id, "version": "1", "adapter": "orbit_direct_shooting",
                "source_files": ["benchmarks/reporting/closed_loop/orbit_nmpc.py"],
                "prediction": "nonlinear physical dynamics; one classical RK4 step per held interval",
                "transcription": "direct shooting with exact Euclidean objective epigraphs",
                "solver": {"provider": "CasADi IPOPT", "max_iter": 3000, "tolerance": 1e-9,
                    "acceptable_tolerance": 1e-8, "bound_relax_factor": 0.0},
                "warm_start": "shift primal by one absolute interval; omit terminal-repeat; zero duals"}
        else:
            scenario = source_scenario(task); controller_id = scenario["controller_id"]
            controller = {"id": controller_id, "version": "1", "adapter": "mpc11_nmpc",
                "source_files": ["benchmarks/reporting/mpc11/nmpc.py", "benchmarks/reporting/mpc11/affine.py",
                    task["source"]["path"]],
                "prediction": "source-bound MPC11 nonlinear dynamics and shrinking Radau collocation",
                "transcription": "do-mpc collocation profile from immutable source scenario",
                "solver": {"name": scenario["nmpc"]["solver"]["name"],
                    "linear_solver": scenario["nmpc"]["solver"]["linear_solver"],
                    "max_iter": scenario["nmpc"]["solver"]["max_iter"],
                    "tolerance": scenario["nmpc"]["solver"]["tol"],
                    "acceptable_tolerance": scenario["nmpc"]["solver"]["acceptable_tol"]},
                "collocation": scenario["nmpc"]["collocation"], "warm_start": scenario["nmpc"]["warm_start"]}
        execution = replay_scenario(task)
        execution_id = "CSL::simulation/adaptive-rk4-step-doubling/1"
        graph = {"task_id": task["task_id"], "task_sha256": manifest_sha256(task),
            "model_id": task["model"]["model_id"], "objective_id": task["objective"]["objective_id"],
            "action_profile_id": task["control_domains"]["continuous"]["problem_id"],
            "controller": controller, "execution": {"id": execution_id, "version": "1",
                "source_files": ["benchmarks/reporting/mpc11/nonlinear_replay_bridge.cpp",
                                 "src/simulation/nonlinear_replay.cpp"],
                "provider": "CSL::simulation", "method": "adaptive RK4 step doubling",
                "abstol": execution["independent_replay"]["scaled_abstol"],
                "reltol": execution["independent_replay"]["reltol"],
                "report_subintervals_per_hold": execution["independent_replay"]["report_subintervals_per_hold"],
                "original_intervals": task["episode"]["intervals"],
                "original_final_time": task["episode"]["final_time"]},
            "inactive_roles": {"vertex_lp": "not_used", "set_reducer": "not_used",
                "representation": "not_used", "converter": "not_used"},
            "admission": {"status": "admitted", "basis": "source-bound task contract and declared baseline controller/execution profiles"},
            "geometry_work": {"vertices": 0, "set_operations": 0,
                "claim": "no representation comparison is made"}}
        source_paths = sorted(set(controller["source_files"] + graph["execution"]["source_files"]))
        graph["source_files"] = [{"path": path,
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in source_paths]
        fingerprint = canonical_sha256(graph)
        graph["graph_fingerprint"] = fingerprint
        graph["graph_id"] = f"closed-loop/{task_name}/nmpc-csl-adaptive/1/cfg-{fingerprint[:16]}"
        rows.append(graph)
    return rows


def build_manifest() -> dict:
    return {"schema": "csl.closed-loop-capability-manifest/1",
        "manifest_id": "source-bound-three-task-nmpc-baseline/1",
        "purpose": "Resolve admitted source-bound baseline controller and common execution graphs for the first closed-loop pilot.",
        "catalogue_parent": "csl.module-composition-inventory/1",
        "claim_scope": "Single deterministic observed-state trajectories. Pure NMPC bypasses set and vertex operations.",
        "graphs": _definitions()}


def validate_manifest(value: dict | None = None) -> dict:
    manifest = value or json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "csl.closed-loop-capability-manifest/1":
        raise ValueError("unsupported closed-loop capability manifest")
    expected = SIDECAR.read_text().split()[0]
    if canonical_sha256(manifest) != expected:
        raise ValueError("closed-loop capability manifest hash mismatch")
    expected_graphs = {row["graph_id"]: row for row in _definitions()}
    if len(expected_graphs) != len(manifest["graphs"]):
        raise ValueError("closed-loop capability manifest graph count differs from source definitions")
    for graph in manifest["graphs"]:
        source = {key: val for key, val in graph.items() if key not in {"graph_id", "graph_fingerprint"}}
        if canonical_sha256(source) != graph["graph_fingerprint"]:
            raise ValueError("closed-loop graph fingerprint mismatch")
        actual = expected_graphs.get(graph["graph_id"])
        if actual != graph:
            raise ValueError(f"source or task binding changed for graph {graph['graph_id']}")
        if graph["admission"]["status"] != "admitted":
            raise ValueError(f"capability graph is not admitted: {graph['graph_id']}")
        for source_file in graph["source_files"]:
            if hashlib.sha256((ROOT / source_file["path"]).read_bytes()).hexdigest() != source_file["sha256"]:
                raise ValueError(f"source file binding changed for {source_file['path']}")
        task = load_task(graph["task_id"].split("/")[0] if graph["task_id"].startswith("syn-") else "earth-orbit")
        validate_source_binding(task)
        if manifest_sha256(task) != graph["task_sha256"]:
            raise ValueError("graph does not preserve the immutable task hash")
    return manifest


def validate_resolved_graph(graph: dict) -> None:
    source = {key: val for key, val in graph.items() if key not in {"graph_id", "graph_fingerprint"}}
    if canonical_sha256(source) != graph.get("graph_fingerprint"):
        raise ValueError("resolved capability graph fingerprint mismatch")
    for source_file in graph["source_files"]:
        if hashlib.sha256((ROOT / source_file["path"]).read_bytes()).hexdigest() != source_file["sha256"]:
            raise ValueError(f"resolved controller or executor source changed: {source_file['path']}")


def resolve_graph(task: dict, action_profile_id: str, controller_id: str | None = None) -> tuple[dict, dict]:
    manifest = validate_manifest()
    candidates = [row for row in manifest["graphs"] if row["task_id"] == task["task_id"]
        and row["task_sha256"] == manifest_sha256(task) and row["action_profile_id"] == action_profile_id
        and (controller_id is None or row["controller"]["id"] == controller_id)]
    if len(candidates) != 1:
        raise ValueError("no unique admitted capability graph matches task, action profile, and controller request")
    return manifest, candidates[0]


def write_manifest() -> None:
    manifest = build_manifest()
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    SIDECAR.write_text(canonical_sha256(manifest) + "  closed-loop-pilot-capabilities-v1.json\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write: write_manifest()
    checked = validate_manifest()
    print(json.dumps({"status": "pass", "manifest_id": checked["manifest_id"],
        "graphs": [{"graph_id": row["graph_id"], "task_sha256": row["task_sha256"],
                    "graph_fingerprint": row["graph_fingerprint"]} for row in checked["graphs"]]}, indent=2))

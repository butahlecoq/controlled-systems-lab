#!/usr/bin/env python3
"""Combine native component receipts with the finite 941 task-graph universe."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import resource
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limited_process() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))


def registered_record(inventory: dict, module_id: str) -> dict:
    for record in inventory["modules"]:
        if record["identity"].get("id") == module_id:
            return record
    raise AssertionError(f"missing source-backed registration: {module_id}")


def identity_tuple(record: dict) -> dict:
    identity = record["identity"]
    return {"id": identity["id"], "version": identity["version"]}


def controller_variants(route: dict, inventory: dict) -> list[dict]:
    key = route["key"]
    if key == "csl.synthesis.reach-back":
        reducers = [row for row in inventory["modules"] if row["group"] == "vertex_lp_simplex"
            and row.get("role") == "vertex_redundancy"]
        lps = [row for row in inventory["modules"] if row["group"] == "vertex_lp_simplex"
            and row.get("role") == "vertex_lp_provider"]
        projection = identity_tuple(registered_record(inventory, "csl.geometry.projection-materializer"))
        affine_sum = identity_tuple(registered_record(inventory, "csl.geometry.affine-sum"))
        converter = identity_tuple(registered_record(inventory, "csl.conversion.qhull"))
        convex = identity_tuple(registered_record(inventory, "csl.convex.highs"))
        variants = []
        for reducer, hull_lp, converter_lp, control_lp in itertools.product(reducers, lps, lps, lps):
            variants.append({
                "geometry_projection": projection,
                "geometry_affine_sum": affine_sum,
                "vertex_reducer": identity_tuple(reducer),
                "vertex_lp_provider": identity_tuple(hull_lp),
                "converter": converter,
                "converter_lp_provider": identity_tuple(converter_lp),
                "control_lp_provider": identity_tuple(control_lp),
                "control_convex_provider": convex,
                "configured_representation": {"id": "csl.polyhedron.h", "role": "strategy output"},
                "terminal_optimizer": {"symbol": "csl::synthesis::TerminalOptimizer::solve"},
            })
        return variants
    if key == "csl.synthesis.strategy-b":
        lps = [row for row in inventory["modules"] if row["group"] == "vertex_lp_simplex"
            and row.get("role") == "vertex_lp_provider"]
        convex = identity_tuple(registered_record(inventory, "csl.convex.highs"))
        return [{
            "vertex_lp_provider": "not_used",
            "control_lp_provider": identity_tuple(lp),
            "control_convex_provider": convex,
            "configured_representation": {"id": "csl.polyhedron.h", "role": "strategy output"},
            "geometry_projection": "not_used",
            "geometry_affine_sum": "not_used",
            "converter": "not_used",
            "terminal_optimizer": "not_used; direct joint LP/QP strategy",
        } for lp in lps]
    if key == "csl::optimization::finite_action_nominal":
        return [{
            "vertex_lp_provider": "not_used; public planner enumerates finite actions",
            "configured_representation": {"id": representation, "role": "fixed-plan output"},
            "control_lp_provider": "not_used; public planner enumerates finite actions",
            "control_convex_provider": "not_used; public planner enumerates finite actions",
            "geometry_projection": "not_used",
            "geometry_affine_sum": "not_used",
            "converter": "not_used",
            "terminal_optimizer": "finite_action_enumeration",
        } for representation in ("exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid")]
    if key == "csl::reachability::nominal_forward":
        reducers = [row for row in inventory["modules"] if row["group"] == "vertex_lp_simplex"
            and row.get("role") == "vertex_redundancy"]
        lps = [row for row in inventory["modules"] if row["group"] == "vertex_lp_simplex"
            and row.get("role") == "vertex_lp_provider"]
        projection = identity_tuple(registered_record(inventory, "csl.geometry.projection-materializer"))
        affine_sum = identity_tuple(registered_record(inventory, "csl.geometry.affine-sum"))
        converter = identity_tuple(registered_record(inventory, "csl.conversion.qhull"))
        return [{
            "geometry_projection": projection,
            "geometry_affine_sum": affine_sum,
            "vertex_reducer": identity_tuple(reducer),
            "vertex_lp_provider": identity_tuple(affine_lp),
            "affine_sum_converter": converter,
            "affine_sum_converter_lp_provider": identity_tuple(affine_converter_lp),
            "converter": converter,
            "converter_lp_provider": identity_tuple(to_h_lp),
            "configured_representation": {"id": "csl.polyhedron.h", "role": "forward output"},
            "terminal_optimizer": "not_used; forward reachability does not optimize a terminal objective",
        } for reducer, affine_lp, affine_converter_lp, to_h_lp in
            itertools.product(reducers, lps, lps, lps)]
    if key == "csl::reachability::prepare_nominal_predecessor":
        return [{
            "geometry_projection": identity_tuple(registered_record(inventory, "csl.geometry.projection-materializer")),
            "configured_representation": {"id": "csl.polyhedron.h", "role": "predecessor output"},
            "vertex_lp_provider": "not_used; predecessor request prepares a projection operation",
            "vertex_reducer": "not_used; predecessor request prepares a projection operation",
            "converter": "not_used; projection input and output use native H",
            "terminal_optimizer": "not_used; predecessor construction is separate from terminal optimization",
        }]
    return [{
        "vertex_lp_provider": "not_used",
        "configured_representation": "not_used",
        "control_lp_provider": "not_used",
        "control_convex_provider": "not_used",
        "geometry_projection": "not_used",
        "geometry_affine_sum": "not_used",
        "converter": "not_used",
        "terminal_optimizer": "not_used",
    }]


def controller_graphs(root: Path, inventory: dict, receipts: dict, compiled_backends: dict) -> list[dict]:
    route_names = {
        "csl.synthesis.reach-back": "registered reachable-set predecessor strategy",
        "csl.synthesis.strategy-b": "registered joint trajectory strategy",
        "csl.synthesis.ts01-analytic": "registered analytic scalar-integrator strategy",
        "csl::reachability::nominal_forward": "public nominal forward reachable-relation operation",
        "csl::reachability::prepare_nominal_predecessor": "public nominal predecessor and recovery operation",
        "csl::optimization::finite_action_nominal": "public finite-action nominal fixed-plan planner",
        "csl::reachability::finite_feedback::solve": "public finite-table feasibility controller",
        "csl::optimization::finite_causal_minimax::solve": "public finite-table cost controller",
        "benchmarks/reporting/mpc11/run_nmpc.py": "external MPC11 nominal local NMPC",
    }
    routes = []
    for record in inventory["modules"]:
        identity = record["identity"]
        key = identity.get("id", identity.get("symbol"))
        if key in route_names:
            routes.append({"key": key, "name": route_names[key], "record": record})
    assert {route["key"] for route in routes} == set(route_names), "controller route inventory changed; review universe"
    receipt_by_task = {row["task_id"]: row for row in receipts["routes"]}

    tasks = []
    import sys
    sys.path.insert(0, str(root / "benchmarks/reporting/closed_loop"))
    from contracts import load_task, manifest_sha256
    from task_models import validate_source_binding
    for contract_name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        path = root / f"docs/contracts/closed-loop/{contract_name}.json"
        contract = load_task(contract_name)
        validate_source_binding(contract)
        tasks.append({"contract": contract, "path": path,
            "sha256": manifest_sha256(contract), "file_sha256": sha256(path)})

    rows: list[dict] = []
    for task in tasks:
        contract = task["contract"]
        model = contract["model"]
        dimensions = {"state": len(model["states"]), "control": len(model["controls"])}
        for domain_name, domain in contract["control_domains"].items():
            for route in routes:
                key = route["key"]
                for selected_tuple in controller_variants(route, inventory):
                    module_tuple = {"controller": route["record"]["identity"], **selected_tuple}
                    row = {
                        "graph_id": "",
                        "graph_fingerprint": "",
                        "status": "implementation_missing",
                        "task_id": contract["task_id"],
                        "task_contract_sha256": task["sha256"],
                        "model_id": model["model_id"],
                        "model_dimension": dimensions["state"],
                        "control_dimension": dimensions["control"],
                        "action_domain_id": domain["problem_id"],
                        "action_domain_kind": domain_name,
                        "controller_route": key,
                        "controller_route_name": route["name"],
                        "module_tuple": module_tuple,
                        "captured_provider_roles": route["record"].get("captured_provider_roles", []),
                        "route_dependencies": route["record"].get("dependencies", []),
                        "policy_semantics": {
                            "observation": contract["episode"]["closed_loop"]["observation"],
                            "apply": contract["episode"]["closed_loop"]["apply"],
                            "horizon": contract["episode"]["closed_loop"]["optimization_horizon"],
                            "failure": contract["episode"]["closed_loop"]["failure"],
                        },
                        "numerical_assurance": route["record"]["assurance"],
                        "relation": route["record"].get("relation", "not_applicable"),
                        "tolerance_policy": route["record"].get("tolerance_policy", "source profile required"),
                        "budget_policy": route["record"].get("budget_policy", "source profile required"),
                        "first_unmet": None,
                    }

                    if key in ("csl.synthesis.reach-back", "csl::reachability::nominal_forward") and not compiled_backends["qhull"]:
                        row["status"] = "backend_unavailable"
                        row["first_unmet"] = {"field": "build.CSL_ENABLE_QHULL",
                            "reason": "This concrete Strategy A graph selects the Qhull converter, which is absent from the native build."}
                    elif key in ("csl.synthesis.reach-back", "csl.synthesis.strategy-b", "csl::reachability::nominal_forward") and not compiled_backends["highs"]:
                        selects_highs = any(isinstance(value, dict) and value.get("id") in
                            ("csl.lp.highs", "csl.convex.highs") for value in module_tuple.values())
                        if selects_highs:
                            row["status"] = "backend_unavailable"
                            row["first_unmet"] = {"field": "build.CSL_ENABLE_HIGHS",
                                "reason": "This concrete graph selects a HiGHS LP or convex provider omitted from the native build."}

                    if row["status"] == "implementation_missing":
                        if key == "benchmarks/reporting/mpc11/run_nmpc.py":
                            receipt = receipt_by_task.get(contract["task_id"])
                            if receipt is not None and domain_name == "continuous":
                                row["status"] = "admitted"
                                row["module_tuple"].update({
                                    "controller": receipt["controller_id"],
                                    "terminal_optimizer": {
                                        "configured_id": f"{receipt['runtime']['solver']}/{receipt['runtime']['linear_solver']}",
                                        "prepared_interface": receipt["runtime"]["solver_interface_prepared"],
                                    },
                                })
                                row["solver_profile"] = receipt["solver_profile"]
                                row["external_prepare_receipt"] = receipt
                            elif receipt is not None:
                                row["status"] = "incompatible"
                                row["first_unmet"] = {
                                    "field": "controller.action_domain",
                                    "reason": "The prepared MPC11 route consumes a continuous bounded control vector; this finite action identity is a separate task.",
                                }
                            else:
                                row["first_unmet"] = {
                                    "field": "controller.model_adapter",
                                    "reason": "No source-supported MPC11 scenario/controller provider prepares this physical model.",
                                }
                        elif key == "csl.synthesis.ts01-analytic":
                            row["status"] = "incompatible"
                            row["first_unmet"] = {
                                "field": "strategy.model_profile",
                                "reason": "TS01 is pinned to its exact two-step scalar integrator profile, not this source-bound nonlinear plant.",
                            }
                        elif key in ("csl::reachability::nominal_forward", "csl::reachability::prepare_nominal_predecessor"):
                            if domain_name != "continuous":
                                row["status"] = "incompatible"
                                row["first_unmet"] = {
                                    "field": "controller.action_domain",
                                    "reason": "The nominal affine reachability operation requires a continuous native H control family; the finite action identity is a separate task.",
                                }
                            else:
                                row["first_unmet"] = {
                                    "field": "controller.discrete_affine_model_adapter",
                                    "reason": "The public operation accepts a resolved discrete affine nominal problem; this nonlinear physical task has no source-bound affine model adapter.",
                                }
                        elif key == "csl::optimization::finite_action_nominal":
                            if domain_name == "continuous":
                                row["status"] = "incompatible"
                                row["first_unmet"] = {
                                    "field": "controller.action_domain",
                                    "reason": "finite_action_nominal requires a finite action catalogue; the continuous control contract is distinct.",
                                }
                            else:
                                row["first_unmet"] = {
                                    "field": "controller.nonlinear_model_adapter",
                                    "reason": "A nonlinear physical model discretization and cost-preserving nominal fixed-plan adapter are not delivered for this task.",
                                }
                        elif key in ("csl.synthesis.reach-back", "csl.synthesis.strategy-b") and domain_name != "continuous":
                            row["status"] = "incompatible"
                            row["first_unmet"] = {
                                "field": "strategy.controls" if key == "csl.synthesis.reach-back" else "joint.controls",
                                "reason": "The registered strategy requires a continuous native H control domain; a finite action catalogue cannot be convexified into that contract.",
                            }
                        elif key in ("csl::reachability::finite_feedback::solve",
                                     "csl::optimization::finite_causal_minimax::solve"):
                            row["first_unmet"] = {
                                "field": "controller.transition_table_adapter",
                                "reason": "The public controller consumes an explicit finite transition table; this physical-model-to-table adapter and episode bridge are not delivered.",
                            }
                        elif key == "csl.synthesis.strategy-b":
                            row["first_unmet"] = {
                                "field": "controller.model_adapter",
                                "reason": "Strategy B consumes registered affine stage problems; a source-bound nonlinear model and policy/episode adapter is not delivered.",
                            }
                        elif key == "csl.synthesis.reach-back":
                            row["first_unmet"] = {
                                "field": "controller.model_adapter",
                                "reason": "The registered reachable-set strategy has no source-bound nonlinear prediction, predecessor and first-action recovery adapter for this task.",
                            }
                    canonical = {
                        "task_contract_sha256": task["sha256"],
                        "model_id": model["model_id"],
                        "action_domain_id": domain["problem_id"],
                        "module_tuple": row["module_tuple"],
                    }
                    graph_fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True,
                        separators=(",", ":")).encode()).hexdigest()
                    row["graph_fingerprint"] = graph_fingerprint
                    row["graph_id"] = f"{contract['task_id']}/{domain_name}/{key}/cfg-{graph_fingerprint[:16]}"
                    rows.append(row)
    return rows


def predecessor_graphs(controller_rows: list[dict], inventory: dict, compiled_backends: dict) -> list[dict]:
    representation_routes = {
        "polytope.h-v": ("csl::reachability::fixed_plan_disturbance", "general supported affine V trace"),
        "box": ("csl::reachability::finite_plan_box", "general-dimensional affine fixed-plan box trace"),
        "zonotope": ("csl::reachability::finite_plan_zonotope", "general-dimensional affine fixed-plan zonotope trace"),
        "parallelotope": ("csl::reachability::finite_plan_parallelotope", "fixed four-state TwoPoints frame"),
        "ellipsoid": ("csl::reachability::finite_plan_ellipsoid", "general-dimensional affine fixed-plan ellipsoid trace"),
    }
    route_records = {record["identity"].get("symbol"): record
        for record in inventory["modules"] if record["identity"].get("symbol")}
    terminal_provider = identity_tuple(registered_record(inventory, "csl.convex.highs"))
    terminal_lp_providers = [identity_tuple(record) for record in inventory["modules"]
        if record["group"] == "vertex_lp_simplex" and record.get("role") == "vertex_lp_provider"]
    selected_tasks = {}
    for row in controller_rows:
        selected_tasks[row["task_id"]] = row
    output = []
    for task in selected_tasks.values():
        for representation, (route_symbol, dimension_contract) in representation_routes.items():
            for terminal_lp_provider in terminal_lp_providers:
                route_record = route_records[route_symbol]
                parallelotope_incompatible = representation == "parallelotope" and task["model_dimension"] == 2
                module_tuple = {
                    "controller": "reachable-set predecessor and first-action recovery",
                    "reachable_set_representation": representation,
                    "fixed_plan_route": route_symbol,
                    "vertex_lp_provider": "not_used; fixed-plan propagation enumerates affine vertices or propagates the declared enclosure",
                    "converter": "not_used; selected fixed-plan route consumes its declared representation",
                    "terminal_minimizer": {"symbol": "csl::synthesis::TerminalOptimizer::solve"},
                    "terminal_lp_provider": terminal_lp_provider,
                    "terminal_optimizer_provider": terminal_provider,
                    "supporting_operation": route_symbol,
                }
                canonical = {"task_contract_sha256": task["task_contract_sha256"],
                    "model_id": task["model_id"], "module_tuple": module_tuple}
                graph_fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                row = {
                    "graph_id": f"{task['task_id']}/predecessor-recovery/{representation}/cfg-{graph_fingerprint[:16]}",
                    "graph_fingerprint": graph_fingerprint,
                    "status": "implementation_missing",
                    "task_id": task["task_id"],
                    "task_contract_sha256": task["task_contract_sha256"],
                    "model_id": task["model_id"],
                    "model_dimension": task["model_dimension"],
                    "control_dimension": task["control_dimension"],
                    "action_domain_ids": sorted({
                        candidate["action_domain_id"] for candidate in controller_rows
                        if candidate["task_id"] == task["task_id"]
                        and candidate["controller_route"] == "csl.synthesis.reach-back"
                    }),
                    "module_tuple": module_tuple,
                    "fixed_plan_route_dimension_contract": dimension_contract,
                    "fixed_plan_numerical_assurance": route_record.get("assurance"),
                    "fixed_plan_relation": route_record.get("relation"),
                    "tolerance_policy": route_record.get("tolerance_policy"),
                    "budget_policy": route_record.get("budget_policy"),
                    "fixed_plan_propagation_delivered_separately": True,
                    "first_unmet": {
                        "field": "controller.predecessor_and_recovery_adapter",
                        "reason": "This route needs the physical-model predecessor adapter, declared set relation, constrained safe-set semantics and an admissible first-action recovery path.",
                    },
                }
                if parallelotope_incompatible:
                    row["fixed_plan_route_status"] = "incompatible"
                    row["fixed_plan_first_unmet"] = {
                        "field": "request.dimension",
                        "reason": "The delivered fixed-frame parallelotope trace is four-state; the LV task has two states.",
                    }
                else:
                    row["fixed_plan_route_status"] = "implementation_missing"
                    row["fixed_plan_first_unmet"] = {
                        "field": "environment.model_adapter",
                        "reason": "The fixed-plan propagation route consumes its documented discrete affine request; no adapter from this continuous nonlinear task is delivered.",
                    }
                if not compiled_backends["highs"]:
                    row["status"] = "backend_unavailable"
                    row["first_unmet"] = {"field": "build.CSL_ENABLE_HIGHS",
                        "reason": "This graph selects a HiGHS terminal LP or convex optimizer provider, which is absent from the native build."}
                elif parallelotope_incompatible:
                    row["status"] = "incompatible"
                    row["first_unmet"] = row["fixed_plan_first_unmet"]
                row["fixed_plan_source"] = route_record["source"]
                output.append(row)
    return output


def group1_reference_graphs(contracts: dict, task_hashes: dict, inventory: dict) -> list[dict]:
    records = {record["identity"].get("symbol"): record for record in inventory["modules"]
        if record["identity"].get("symbol")}
    legacy = (
        ("csl::geometry::legacy_btulshor::modif", ()),
        ("csl::geometry::legacy_btulshor::kpabep", ("csl::geometry::legacy_btulshor::modif",)),
        ("csl::geometry::legacy_btulshor::reach", (
            "csl::geometry::legacy_btulshor::kpabep", "csl::geometry::legacy_btulshor::modif")),
    )
    output = []
    for task_id, contract in contracts.items():
        dimension = len(contract["model"]["states"])
        for domain_name, domain in contract["control_domains"].items():
            quickhull_record = records["csl::geometry::quickhull_2d"]
            quickhull_status = "implementation_missing" if dimension == 2 else "incompatible"
            quickhull_first = {
                "field": "geometry.reducer_adapter" if dimension == 2 else "points.dimension",
                "reason": "QuickHull2D has no HullReducerPort adapter for controller composition." if dimension == 2 else
                    "QuickHull2D accepts two-dimensional points only; no projection is inserted implicitly.",
            }
            output.append({
                "candidate_id": f"{task_id}/{domain_name}/vertex-reference/quickhull2d",
                "status": quickhull_status,
                "task_id": task_id,
                "task_contract_sha256": task_hashes[task_id],
                "model_id": contract["model"]["model_id"],
                "model_dimension": dimension,
                "action_domain_id": domain["problem_id"],
                "action_domain_kind": domain_name,
                "module_tuple": {"vertex_geometry_reference": quickhull_record["identity"],
                    "registry_hull_reducer": "not_used; public function has no HullReducerPort adapter",
                    "vertex_lp_provider": "not_used; QuickHull2D uses exact orientation predicates"},
                "source": quickhull_record["source"],
                "first_unmet": quickhull_first,
            })
            for route_symbol, dependencies in legacy:
                record = records[route_symbol]
                output.append({
                    "candidate_id": f"{task_id}/{domain_name}/vertex-reference/{route_symbol}",
                    "status": "implementation_missing",
                    "task_id": task_id,
                    "task_contract_sha256": task_hashes[task_id],
                    "model_id": contract["model"]["model_id"],
                    "model_dimension": dimension,
                    "action_domain_id": domain["problem_id"],
                    "action_domain_kind": domain_name,
                    "module_tuple": {"source_faithful_vertex_route": record["identity"],
                        "coupled_source_routes": list(dependencies),
                        "source_owned_simplex_pivot": "csl::geometry::legacy_btulshor::modif"
                            if route_symbol != "csl::geometry::legacy_btulshor::modif" else record["identity"],
                        "registry_hull_reducer": "not_used; public source function has no HullReducerPort adapter"},
                    "source": record["source"],
                    "first_unmet": {"field": "controller.legacy_vertex_adapter",
                        "reason": "The source-faithful legacy route has no adapter from this task's nonlinear physical model and action domain."},
                })
    return output


def group4_function_graphs(contracts: dict, task_hashes: dict, inventory: dict) -> list[dict]:
    records = {record["identity"].get("symbol"): record for record in inventory["modules"]
        if record["identity"].get("symbol")}
    symbols = ("csl::geometry::polyhedral::intersect_h",
        "csl::geometry::polyhedral::remove_redundant_halfspaces")
    rows = []
    for task_id, contract in contracts.items():
        for domain_name, domain in contract["control_domains"].items():
            for symbol in symbols:
                record = records[symbol]
                module_tuple = {"supporting_operation": record["identity"],
                    "vertex_lp_provider": "not_used; public H operation does not select an LP provider",
                    "controller_route": "not_used; no delivered controller registration consumes this function"}
                canonical = {"task_contract_sha256": task_hashes[task_id],
                    "action_domain_id": domain["problem_id"], "module_tuple": module_tuple}
                graph_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                rows.append({
                    "candidate_id": f"{task_id}/{domain_name}/supporting-operation/{graph_hash[:16]}",
                    "graph_fingerprint": graph_hash,
                    "status": "implementation_missing",
                    "task_id": task_id,
                    "task_contract_sha256": task_hashes[task_id],
                    "model_id": contract["model"]["model_id"],
                    "model_dimension": len(contract["model"]["states"]),
                    "action_domain_id": domain["problem_id"],
                    "action_domain_kind": domain_name,
                    "module_tuple": module_tuple,
                    "source": record["source"],
                    "assurance": record["assurance"],
                    "relation": record.get("relation"),
                    "first_unmet": {"field": "controller.set_operation_adapter",
                        "reason": "The public H set operation exists, but no source-bound task/controller route composes it with the task's dynamics and episode policy."},
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-cli", type=Path, required=True)
    parser.add_argument("--mpc11-python", type=Path, required=True,
        help="exact external interpreter that can prepare the pinned MPC11 NLP source")
    parser.add_argument("--inventory", type=Path,
        default=Path(__file__).resolve().parents[2] / "docs/catalogue/module-composition-inventory-v1.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    inventory_path = args.inventory.resolve()
    native_process = subprocess.run([str(args.native_cli.resolve()), "--inventory", str(inventory_path)],
        check=True, capture_output=True, text=True)
    native = json.loads(native_process.stdout)
    inventory = json.loads(inventory_path.read_text())
    environment = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        environment[key] = "1"
    external = subprocess.run([
        str(args.mpc11_python.absolute()), str(root / "scripts/catalogue/qualify_mpc11_routes.py")
    ], check=True, capture_output=True, text=True, env=environment, preexec_fn=limited_process)
    receipts = json.loads(external.stdout)
    assert receipts["schema"] == "csl.catalogue.external-prepare/1"
    expected_receipts = {"syn-nl-lv-01/continuous-receding/1", "syn-nl-fuel-01/continuous-receding/1"}
    assert {row["task_id"] for row in receipts["routes"]} == expected_receipts
    assert all(row["status"] == "admitted" and row["solve_performed"] is False
        and row["runtime"]["solver_interface_prepared"] == "IpoptInterface" for row in receipts["routes"])
    controllers = controller_graphs(root, inventory, receipts, native["compiled_backends"])
    predecessors = predecessor_graphs(controllers, inventory, native["compiled_backends"])
    contract_records = [json.loads((root / f"docs/contracts/closed-loop/{name}.json").read_text())
        for name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")]
    contracts = {contract["task_id"]: contract for contract in contract_records}
    task_hashes = {row["task_id"]: row["task_contract_sha256"] for row in controllers}
    group1_references = group1_reference_graphs(contracts, task_hashes, inventory)
    group4_functions = group4_function_graphs(contracts, task_hashes, inventory)
    assert len(controllers) == 3318
    assert len(predecessors) == 45
    output = {
        "schema": "csl.module-composition-output/2",
        "inventory": inventory,
        "native_component_evidence": native,
        "external_preparation_receipts": receipts,
        "closed_loop_controller_candidates": controllers,
        "closed_loop_predecessor_candidates": predecessors,
        "full_task_group1_reference_candidates": group1_references,
        "full_task_group4_function_candidates": group4_functions,
        "finite_profile_boundaries": {
            "registered_hull_provider": {"dimensions": "profile-specific", "component_input_profile": "2D square with strict interior point",
                "reducers": 10, "vertex_lp_profiles": ["HiGHS default", "Phase-I Bland", "Phase-I priority-tie fixed priorities [0,1,2,3,4]"]},
            "quickhull2d": {"dimension": 2, "component_profile": "square point cloud", "not_a_hull_reducer_port": True},
            "legacy_btulshor": {"component_profile": "source-faithful KPABEP/REACH finite fixtures", "model_dimensions": "public request-specific"},
            "finite_action_nominal": {"state_dimension": 4, "control_dimension": 1, "horizon": 3,
                "action_count": 3, "plan_budget": 27, "representations": ["exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"]},
            "terminal_optimizer": {"component_profile": "TS01 terminal slice [0,1], optimum x=1", "separate_from_vertex_lp": True},
            "generator_operations": {"component_profile": "one-dimensional affine image and V conversion", "vertex_count": 2},
            "polyhedral_functions": {"component_profile": "intersect_h and remove_redundant_halfspaces source routes",
                "task_composition": "not_used; no delivered controller registration consumes these functions"},
            "external_mpc11": {"tasks": ["syn-nl-lv-01", "syn-nl-fuel-01"], "solve_performed": False},
        },
        "scope": "finite source-supported graph universe with captured A and configured B dependencies expanded; no episode solve or benchmark was performed",
    }
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

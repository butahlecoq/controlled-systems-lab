"""Resolve the source-owned baseline task/controller/execution graphs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from contracts import ROOT, canonical_sha256, load_task, manifest_sha256
from task_models import replay_scenario, source_scenario, validate_source_binding

MANIFEST = ROOT / "docs/catalogue/closed-loop-pilot-capabilities-v1.json"
SIDECAR = ROOT / "docs/catalogue/closed-loop-pilot-capabilities-v1.sha256"
NATIVE_MANIFEST = ROOT / "docs/catalogue/closed-loop-native-capabilities-v1.json"
NATIVE_SIDECAR = ROOT / "docs/catalogue/closed-loop-native-capabilities-v1.sha256"
HISTORY_MANIFEST = ROOT / "docs/catalogue/closed-loop-history-capabilities-v1.json"
HISTORY_SIDECAR = ROOT / "docs/catalogue/closed-loop-history-capabilities-v1.sha256"
MODULE_INVENTORY = ROOT / "docs/catalogue/module-composition-inventory-v1.json"

NATIVE_PROFILES = {
    "native-exact-polytope-backward-graph/1": ("exact-polytope", "backward-graph"),
    "native-box-mpc/1": ("box", "backward-graph"),
    "native-zonotope-mpc/1": ("zonotope", "backward-graph"),
    "native-parallelotope-mpc/1": ("parallelotope", "backward-graph"),
    "native-ellipsoid-mpc/1": ("ellipsoid", "backward-graph"),
    "native-exact-polytope-fixed-plan-mpc/1": ("exact-polytope", "fixed-plan-mpc"),
    "native-box-fixed-plan-mpc/1": ("box", "fixed-plan-mpc"),
    "native-zonotope-fixed-plan-mpc/1": ("zonotope", "fixed-plan-mpc"),
    "native-parallelotope-fixed-plan-mpc/1": ("parallelotope", "fixed-plan-mpc"),
    "native-ellipsoid-fixed-plan-mpc/1": ("ellipsoid", "fixed-plan-mpc"),
}


def manifest_digest(manifest: dict) -> str:
    """Hash the selected manifest itself, regardless of its catalogue path."""
    return canonical_sha256(manifest)


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


def _native_factory_options(profile_id: str, representation: str,
                            search: str) -> dict:
    limits = ({"max_beam_width": 8, "max_graph_nodes": 512, "max_plans": 32,
        "max_points_per_stage": 128, "max_score_evaluations": 128,
        "max_generators_per_stage": 64} if search == "backward-graph" else
        {"max_beam_width": 1, "max_graph_nodes": 1, "max_plans": 512, "max_score_evaluations": 100000,
         "max_points_per_stage": 100000, "max_generators_per_stage": 1000})
    options = {"representation": representation, "limits": limits,
        "build_backend_profile": {"build_type": "Release", "CSL_ENABLE_HIGHS": True,
            "CSL_ENABLE_QHULL": True}}
    if search == "backward-graph":
        options.update({"reachable_set_method": {"id": "csl.geometry.affine-sum", "version": "1.0.0"},
            "hull_provider": {"id": "csl.hull.lp-membership", "version": "1.0.0"},
            "vertex_lp_provider": {"id": "phase-one-bland", "version": "1"},
            "conversion_provider": "not_used",
            "checker_budget": {"max_points": 64, "wall_ms": 5000},
            "control_optimizer": {"id": "csl.optimization.finite-action-stage-layered-graph",
                "version": "1.0.0"}})
    return options


def _catalogue_sources(options: dict) -> list[str]:
    """Resolve selected provider source files from the checked-in module catalogue."""
    identities = []
    for key in ("reachable_set_method", "hull_provider", "vertex_lp_provider"):
        value = options.get(key)
        if isinstance(value, dict) and value.get("id"):
            identities.append((value["id"], value.get("version")))
    catalogue = json.loads(MODULE_INVENTORY.read_text())
    sources = {str(MODULE_INVENTORY.relative_to(ROOT))}
    for identity, version in identities:
        entries = [row for row in catalogue["modules"]
            if row.get("identity", {}).get("id") == identity
            and (version is None or row.get("identity", {}).get("version") == version)]
        if len(entries) != 1:
            raise ValueError(f"selected native provider is not uniquely registered in the module catalogue: {identity}@{version}")
        path = entries[0].get("source", {}).get("path")
        if path:
            sources.add(path)
    return sorted(sources)


def _native_definitions() -> list[dict]:
    rows = []
    source_paths = ["benchmarks/reporting/closed_loop/native_graph_policy.py",
        "benchmarks/reporting/closed_loop/task_models.py", "benchmarks/reporting/mpc11/affine.py",
        "tools/closed_loop_native_policy.cpp", "CMakeLists.txt",
        str(MODULE_INVENTORY.relative_to(ROOT)), "src/optimization/running_cost_evaluation.hpp"]
    execution_id = "CSL::simulation/adaptive-rk4-step-doubling/1"
    for task_name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        task = load_task(task_name)
        validate_source_binding(task)
        for profile_id, (representation, search) in NATIVE_PROFILES.items():
            options = _native_factory_options(profile_id, representation, search)
            control_optimizer = options.get("control_optimizer", {
                "module_id": "csl::optimization::finite_action_nominal_profile",
                "provider": "public-function", "operation": f"{representation}-plan-select",
                "profile_id": profile_id})
            representation_modules = {"box": "csl::reachability::finite_plan_box",
                "zonotope": "csl::reachability::finite_plan_zonotope",
                "parallelotope": "csl::reachability::finite_plan_parallelotope",
                "ellipsoid": "csl::reachability::finite_plan_ellipsoid"}
            if search == "backward-graph":
                representation_source = {"box": "src/reachability/finite_plan_box.cpp",
                    "zonotope": "src/reachability/finite_plan_zonotope.cpp",
                    "parallelotope": "src/reachability/finite_plan_parallelotope.cpp",
                    "ellipsoid": "src/reachability/finite_plan_ellipsoid.cpp"}.get(representation)
                representation_header = {"box": "include/csl/reachability/finite_plan_box.hpp",
                    "zonotope": "include/csl/reachability/finite_plan_zonotope.hpp",
                    "parallelotope": "include/csl/reachability/finite_plan_parallelotope.hpp",
                    "ellipsoid": "include/csl/reachability/finite_plan_ellipsoid.hpp"}.get(representation)
                controller_sources = source_paths + ["include/csl/optimization/finite_action_graph.hpp",
                    "src/optimization/finite_action_graph.cpp", "src/geometry/affine_sum.cpp",
                    "include/csl/geometry/polyhedral_intersection.hpp",
                    "src/geometry/polyhedral/intersection.cpp",
                    "include/csl/geometry/polyhedral_projection.hpp",
                    "src/geometry/polyhedral/projection.cpp",
                    "include/csl/reachability/nominal_predecessor.hpp",
                    "src/reachability/nominal_predecessor.cpp"]
                if representation_source:
                    controller_sources.extend([representation_header, representation_source,
                        "src/reachability/fixed_plan_admission.hpp"])
                controller_sources += _catalogue_sources(options)
            else:
                optimizer_sources = {
                    "exact-polytope": ["include/csl/optimization/finite_action_minimax.hpp",
                        "src/optimization/finite_action_minimax.cpp"],
                    "box": ["include/csl/optimization/finite_action_box_minimax.hpp",
                        "src/optimization/finite_action_box_minimax.cpp"],
                    "zonotope": ["include/csl/optimization/finite_action_zonotope_minimax.hpp",
                        "src/optimization/finite_action_zonotope_minimax.cpp"],
                    "parallelotope": ["include/csl/optimization/finite_action_parallelotope_minimax.hpp",
                        "src/optimization/finite_action_parallelotope_minimax.cpp"],
                    "ellipsoid": ["include/csl/optimization/finite_action_ellipsoid_minimax.hpp",
                        "src/optimization/finite_action_ellipsoid_minimax.cpp"]}[representation]
                controller_sources = source_paths + ["include/csl/optimization/finite_action_nominal.hpp",
                    "include/csl/optimization/finite_action_minimax.hpp",
                    "src/optimization/finite_action_nominal.cpp", "src/optimization/finite_action_plans.hpp",
                    "src/optimization/finite_action_replay.hpp", "src/optimization/finite_action_replay.cpp"]
                controller_sources += optimizer_sources
            limit_usage = ({"max_beam_width": "used", "max_graph_nodes": "used",
                "max_generators_per_stage": "used", "max_plans": "not_used_by_graph_search",
                "max_points_per_stage": "not_used_by_graph_search",
                "max_score_evaluations": "not_used_by_graph_search"} if search == "backward-graph" else
                {"max_beam_width": "not_used_by_fixed_plan_search", "max_graph_nodes": "not_used_by_fixed_plan_search",
                 "max_plans": "used_as_candidate_history_budget", "max_points_per_stage": "used",
                 "max_score_evaluations": "used", "max_generators_per_stage": "used"})
            graph = {"task_id": task["task_id"], "task_sha256": manifest_sha256(task),
                "model_id": task["model"]["model_id"], "objective_id": task["objective"]["objective_id"],
                "action_profile_id": task["control_domains"]["finite"]["problem_id"],
                "controller": {"id": profile_id, "version": "1", "adapter": "native_graph_policy",
                    "policy_factory": "native_graph_policy:create_policy", "source_files": controller_sources,
                    "factory_options": options,
                    "prediction": "source-bound affine physical coefficients; exact finite action catalogue",
                    "control_semantics": search, "limit_usage": limit_usage},
                "execution": {"id": execution_id, "version": "1", "provider": "CSL::simulation",
                    "source_files": ["benchmarks/reporting/mpc11/nonlinear_replay_bridge.cpp",
                        "src/simulation/nonlinear_replay.cpp"],
                    "method": "adaptive RK4 step doubling", "original_intervals": task["episode"]["intervals"],
                    "original_final_time": task["episode"]["final_time"]},
                "role_bindings": {"reachable_set_method": options.get("reachable_set_method", "not_used"),
                    "hull_provider": options.get("hull_provider", "not_used"),
                    "vertex_lp": options.get("vertex_lp_provider", "not_used"),
                    "converter": options.get("conversion_provider", "not_used"),
                    "set_reducer": options.get("hull_provider", "not_used"),
                    "geometry_checker": "not_used" if search == "fixed-plan-mpc" else {
                        "status": "budget-declared; not consumed by selected affine-sum profile",
                        "budget": options["checker_budget"]},
                    "representation": {"name": representation,
                        **({"module_id": representation_modules[representation], "status": "selected"}
                           if search == "backward-graph" and representation in representation_modules else
                           {"status": "integrated-h-polytope" if representation == "exact-polytope"
                            else "selected-in-nominal-profile"})},
                    "control_optimizer": control_optimizer,
                    "bellman_solver": ("integrated in selected graph optimizer" if search == "backward-graph" else "not_used"),
                    "terminal_solver": ("direct authored objective evaluation" if search == "backward-graph"
                        else "integrated in selected nominal planner")},
                "operation_roles": {"affine-image": "reachable_set_method", "minkowski-sum": "reachable_set_method",
                    "controller.solve": "control_optimizer"},
                "admission": {"status": "admitted", "basis": "source-bound task, finite action profile, and declared native policy factory"},
                **({"candidate_search_policy": "constant-and-single-switch-full-horizon/1"}
                   if search == "fixed-plan-mpc" else {}),
                "claim_scope": ("Observed-state finite-action receding-horizon backward graph policy; numerical predecessor membership and discrete transition witnesses; no global guarantee"
                    if search == "backward-graph" else
                    "Observed-state finite-action fixed-plan MPC; bounded candidate coverage recorded per query; no adaptive or global optimality guarantee")}
            graph["source_files"] = [{"path": path,
                "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in sorted(set(controller_sources + graph["execution"]["source_files"]))]
            graph["graph_fingerprint"] = canonical_sha256(graph)
            graph["graph_id"] = f"closed-loop/{task_name}/{profile_id}/cfg-{graph['graph_fingerprint'][:16]}"
            rows.append(graph)
    return rows


def build_native_manifest() -> dict:
    return {"schema": "csl.closed-loop-capability-manifest/2",
        "manifest_id": "source-bound-native-finite-action-profiles/1",
        "registration_status": "source-frozen",
        "purpose": "Source-bound native finite-action graph and fixed-plan profiles for the same three closed-loop task contracts.",
        "catalogue_parent": "csl.module-composition-inventory/1",
        "claim_scope": "Observed-state policy trajectories; no global optimality, reachability, safety, or robustness guarantee.",
        "graphs": _native_definitions()}


def _history_definitions() -> list[dict]:
    rows = []
    common_sources = ["benchmarks/reporting/closed_loop/history_policy.py",
        "benchmarks/reporting/closed_loop/history_norm_solver.py",
        "benchmarks/reporting/closed_loop/history_validation.py",
        "benchmarks/reporting/closed_loop/native_graph_policy.py",
        "benchmarks/reporting/closed_loop/task_models.py",
        "tools/closed_loop_native_policy.cpp", "include/csl/optimization/history_cost.hpp",
        "include/csl/optimization/running_control_cost.hpp", "src/optimization/history_cost.cpp",
        "src/optimization/running_control_cost.cpp", "src/optimization/objective_reformulation.cpp",
        "src/optimization/convex_backend.cpp", "src/problem/resolved.cpp", "src/model/linear_system.cpp",
        "src/synthesis/control_recovery.cpp", "src/adapters/convex/highs.cpp", "CMakeLists.txt"]
    for base in _definitions():
        task_name = base["task_id"].split("/")[0] if base["task_id"].startswith("syn-") else "earth-orbit"
        task = load_task(task_name)
        orbit = task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01"
        provider = "casadi-ipopt" if orbit else "csl.convex.highs"
        controller = {"id": "native-continuous-affine-history-mpc/1", "version": "1",
            "adapter": "continuous_history", "policy_factory": "history_policy:create_policy",
            "factory_options": {}, "source_files": common_sources,
            "prediction": "source-bound affine physical predictor over the full remaining horizon",
            "control_semantics": "continuous full-history receding-horizon MPC",
            "solver": {"provider": provider, "assurance": "local numerical" if orbit else "numerical"}}
        source_paths = set(common_sources + base["execution"]["source_files"])
        source_paths.add(task["source"]["path"])
        if task["source"]["kind"] == "mpc11-scenario":
            source_paths.add("benchmarks/reporting/mpc11/affine.py")
        graph = {key: base[key] for key in ("task_id", "task_sha256", "model_id", "objective_id",
                                             "action_profile_id", "execution")}
        graph.update({"controller": controller,
            "role_bindings": {"reachable_set_method": "not_used", "representation": "not_used",
                              "vertex_lp": "not_used", "converter": "not_used",
                              "control_optimizer": {"id": provider}},
            "operation_roles": {"controller.solve": "control_optimizer"},
            "admission": {"status": "admitted", "basis": "source-bound continuous full-history profile"},
            "geometry_work": {"vertices": 0, "set_operations": 0, "claim": "no representation comparison is made"},
            "source_files": [{"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
                             for path in sorted(source_paths)]})
        fingerprint = canonical_sha256(graph)
        graph["graph_fingerprint"] = fingerprint
        graph["graph_id"] = f"closed-loop/{task_name}/continuous-history-mpc/1/cfg-{fingerprint[:16]}"
        rows.append(graph)
        if not orbit:
            alternative = copy.deepcopy(graph)
            alternative.pop("graph_id")
            alternative.pop("graph_fingerprint")
            alternative["controller"]["id"] = "native-continuous-affine-history-ipopt/1"
            alternative["controller"]["solver"] = {"provider": "casadi-ipopt", "assurance": "local numerical"}
            alternative["role_bindings"]["control_optimizer"] = {"id": "casadi-ipopt"}
            alternative["admission"]["basis"] = "source-bound continuous full-history IPOPT profile"
            alternative_fingerprint = canonical_sha256(alternative)
            alternative["graph_fingerprint"] = alternative_fingerprint
            alternative["graph_id"] = f"closed-loop/{task_name}/continuous-history-ipopt/1/cfg-{alternative_fingerprint[:16]}"
            rows.append(alternative)
    return rows


def build_history_manifest() -> dict:
    return {"schema": "csl.closed-loop-capability-manifest/2",
        "manifest_id": "source-bound-continuous-history-profiles/1",
        "registration_status": "source-frozen", "catalogue_parent": "csl.module-composition-inventory/1",
        "purpose": "Continuous full-source-cost affine-history MPC on the three common tasks.",
        "claim_scope": "Numerical observed-state affine MPC; no set-representation, global nonlinear or safety guarantee.",
        "graphs": _history_definitions()}


def validate_manifest(value: dict | None = None, manifest_path: Path | None = None) -> dict:
    selected_path = manifest_path or MANIFEST
    manifest = value or json.loads(selected_path.read_text())
    native = selected_path.resolve() == NATIVE_MANIFEST.resolve()
    history = selected_path.resolve() == HISTORY_MANIFEST.resolve()
    expected_schema = "csl.closed-loop-capability-manifest/2" if native or history else "csl.closed-loop-capability-manifest/1"
    if manifest.get("schema") != expected_schema:
        raise ValueError("unsupported closed-loop capability manifest")
    sidecar = HISTORY_SIDECAR if history else NATIVE_SIDECAR if native else SIDECAR
    expected = sidecar.read_text().split()[0]
    if canonical_sha256(manifest) != expected:
        raise ValueError("closed-loop capability manifest hash mismatch")
    expected_rows = _history_definitions() if history else _native_definitions() if native else _definitions()
    expected_ids = {row["graph_id"] for row in expected_rows}
    graph_ids = [row.get("graph_id") for row in manifest["graphs"]]
    if len(graph_ids) != len(set(graph_ids)):
        raise ValueError("closed-loop capability manifest graph IDs are not unique")
    if set(graph_ids) != expected_ids:
        raise ValueError("closed-loop capability manifest graph IDs differ from source definitions")
    expected_graphs = {row["graph_id"]: row for row in expected_rows}
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


def resolve_graph(task: dict, action_profile_id: str, controller_id: str | None = None,
                  manifest_path: Path | None = None) -> tuple[dict, dict]:
    manifest = validate_manifest(manifest_path=manifest_path)
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


def write_native_manifest() -> None:
    manifest = build_native_manifest()
    NATIVE_MANIFEST.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    NATIVE_SIDECAR.write_text(canonical_sha256(manifest) + "  closed-loop-native-capabilities-v1.json\n")


def write_history_manifest() -> None:
    manifest = build_history_manifest()
    HISTORY_MANIFEST.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    HISTORY_SIDECAR.write_text(canonical_sha256(manifest) + "  closed-loop-history-capabilities-v1.json\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--write-native", action="store_true")
    parser.add_argument("--write-history", action="store_true")
    args = parser.parse_args()
    if args.write: write_manifest()
    if args.write_native: write_native_manifest()
    if args.write_history: write_history_manifest()
    selected = HISTORY_MANIFEST if args.write_history else NATIVE_MANIFEST if args.write_native else MANIFEST
    checked = validate_manifest(manifest_path=selected)
    print(json.dumps({"status": "pass", "manifest_id": checked["manifest_id"],
        "graphs": [{"graph_id": row["graph_id"], "task_sha256": row["task_sha256"],
                    "graph_fingerprint": row["graph_fingerprint"]} for row in checked["graphs"]]}, indent=2))

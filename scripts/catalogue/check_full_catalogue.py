#!/usr/bin/env python3
"""Check the emitted finite graph universe against independent source expectations."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

EXPECTED_TASKS = {
    "syn-nl-lv-01/continuous-receding/1",
    "env717-earth-orbit/continuous-receding/1",
    "syn-nl-fuel-01/continuous-receding/1",
}
EXPECTED_ROUTES = {
    "csl.synthesis.reach-back", "csl.synthesis.strategy-b",
    "csl.synthesis.ts01-analytic", "csl::optimization::finite_action_nominal",
    "csl::reachability::nominal_forward", "csl::reachability::prepare_nominal_predecessor",
    "csl::reachability::finite_feedback::solve",
    "csl::optimization::finite_causal_minimax::solve",
    "benchmarks/reporting/mpc11/run_nmpc.py",
}
LP_IDS = {
    ("csl.lp.highs", "1.1.0+highs.1.11.0"),
    ("phase-one-bland", "1"),
    ("phase-one-priority-tie", "1"),
}
REDUCER_IDS = {
    ("csl.hull.lp-membership", "1.0.0"),
    ("csl.hull.phase-one-basis-bulk", "1.0.0"),
    ("csl.hull.ordered-membership", "1.0.0"),
    ("csl.hull.grouped-membership", "1.0.0"),
    ("csl.hull.recursive-split-merge", "1.0.0"),
    ("csl.hull.itis17.a43-certified-basis-reuse", "1.0.0"),
    ("csl.hull.itis17.a43-artificial-basis", "1.0.0"),
    ("csl.hull.itis17.a43-largest-norm-tie", "1.0.0"),
    ("csl.hull.itis17.a44-incremental-lp", "2.0.0"),
    ("csl.hull.itis17.a44-paper-farthest-incremental-lp", "1.0.0"),
}
REPRESENTATIONS = {"exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"}
PREDECESSOR_REPRESENTATIONS = {"polytope.h-v", "box", "zonotope", "parallelotope", "ellipsoid"}


def identity(value: dict) -> tuple[str, str]:
    return value["id"], value["version"]


def collected_strings(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(item for item in value.values() if isinstance(item, str))
        for nested in value.values():
            found.update(collected_strings(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(collected_strings(nested))
    return found


def task_binding_negative_checks(root: Path) -> None:
    import sys
    sys.path.insert(0, str(root / "benchmarks/reporting/closed_loop"))
    from contracts import canonical_sha256, load_task
    from task_models import validate_source_binding

    original = load_task("syn-nl-lv-01")
    validate_source_binding(original)

    changed_model = copy.deepcopy(original)
    changed_model["model"]["equations"][0] += "; mutated"
    try:
        validate_source_binding(changed_model)
    except ValueError:
        pass
    else:
        raise AssertionError("changed task model was admitted against the original scenario")

    changed_objective = copy.deepcopy(original)
    changed_objective["objective"]["source_definition"]["terms"] = []
    try:
        validate_source_binding(changed_objective)
    except (ValueError, KeyError):
        pass
    else:
        raise AssertionError("changed task objective was admitted against the original scenario")

    scenario_path = root / "benchmarks/reporting/mpc11/scenarios/syn-nl-lv-01.json"
    scenario = json.loads(scenario_path.read_text())
    scenario["equations"][0] += "; mutated"
    with tempfile.TemporaryDirectory(prefix="catalogue942-source-binding-") as temp:
        changed_source = Path(temp) / "scenario.json"
        changed_source.write_text(json.dumps(scenario))
        changed_binding = copy.deepcopy(original)
        changed_binding["source"]["path"] = str(changed_source)
        changed_binding["source"]["sha256"] = canonical_sha256(scenario)
        try:
            validate_source_binding(changed_binding)
        except ValueError:
            pass
        else:
            raise AssertionError("changed source scenario was admitted after its hash was refreshed")


def main() -> int:
    output = json.loads(Path(sys.argv[1]).read_text())
    root = Path(sys.argv[2]).resolve()
    assert output["schema"] == "csl.module-composition-output/2"
    contracts = {}
    for name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        data = json.loads((root / f"docs/contracts/closed-loop/{name}.json").read_text())
        contracts[data["task_id"]] = data
    assert set(contracts) == EXPECTED_TASKS

    controllers = output["closed_loop_controller_candidates"]
    assert len(controllers) == 3318
    assert {row["controller_route"] for row in controllers} == EXPECTED_ROUTES
    assert len({row["graph_id"] for row in controllers}) == len(controllers)
    assert len({row["graph_fingerprint"] for row in controllers}) == len(controllers)
    for row in controllers:
        contract = contracts[row["task_id"]]
        assert row["task_contract_sha256"]
        assert row["model_id"] == contract["model"]["model_id"]
        assert row["model_dimension"] == len(contract["model"]["states"])
        assert row["control_dimension"] == len(contract["model"]["controls"])
        assert row["action_domain_id"] == contract["control_domains"][row["action_domain_kind"]]["problem_id"]
        assert (row["first_unmet"] is None) == (row["status"] == "admitted")
        canonical = {"task_contract_sha256": row["task_contract_sha256"],
            "model_id": row["model_id"], "action_domain_id": row["action_domain_id"],
            "module_tuple": row["module_tuple"]}
        expected_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        assert row["graph_fingerprint"] == expected_hash
        assert row["graph_id"].endswith(f"cfg-{expected_hash[:16]}")

    reach_back = [row for row in controllers if row["controller_route"] == "csl.synthesis.reach-back"]
    expected_reach_back = {
        (task, domain, reducer, hull_lp, converter_lp, control_lp)
        for task, contract in contracts.items() for domain in contract["control_domains"]
        for reducer in REDUCER_IDS for hull_lp in LP_IDS for converter_lp in LP_IDS for control_lp in LP_IDS
    }
    actual_reach_back = set()
    for row in reach_back:
        modules = row["module_tuple"]
        assert modules["geometry_projection"]["id"] == "csl.geometry.projection-materializer"
        assert modules["geometry_affine_sum"]["id"] == "csl.geometry.affine-sum"
        assert modules["converter"]["id"] == "csl.conversion.qhull"
        assert modules["control_convex_provider"]["id"] == "csl.convex.highs"
        assert modules["configured_representation"]["id"] == "csl.polyhedron.h"
        assert modules["terminal_optimizer"]["symbol"] == "csl::synthesis::TerminalOptimizer::solve"
        actual_reach_back.add((row["task_id"], row["action_domain_kind"],
            identity(modules["vertex_reducer"]), identity(modules["vertex_lp_provider"]),
            identity(modules["converter_lp_provider"]), identity(modules["control_lp_provider"])))
    assert len(reach_back) == 1620
    assert actual_reach_back == expected_reach_back

    strategy_b = [row for row in controllers if row["controller_route"] == "csl.synthesis.strategy-b"]
    expected_strategy_b = {(task, domain, lp) for task, contract in contracts.items()
        for domain in contract["control_domains"] for lp in LP_IDS}
    actual_strategy_b = set()
    for row in strategy_b:
        modules = row["module_tuple"]
        assert modules["vertex_lp_provider"].startswith("not_used")
        assert modules["control_convex_provider"]["id"] == "csl.convex.highs"
        assert modules["configured_representation"]["id"] == "csl.polyhedron.h"
        actual_strategy_b.add((row["task_id"], row["action_domain_kind"], identity(modules["control_lp_provider"])))
    assert len(strategy_b) == 18 and actual_strategy_b == expected_strategy_b
    for row in [*reach_back, *strategy_b]:
        if row["action_domain_kind"] == "finite":
            assert row["status"] == "incompatible"
            assert row["first_unmet"]["field"] in {"strategy.controls", "joint.controls"}
        else:
            assert row["status"] == "implementation_missing"
            assert row["first_unmet"]["field"] == "controller.model_adapter"

    nominal = [row for row in controllers if row["controller_route"] == "csl::optimization::finite_action_nominal"]
    assert len(nominal) == 30
    assert {(row["task_id"], row["action_domain_kind"], row["module_tuple"]["configured_representation"]["id"])
        for row in nominal} == {(task, domain, representation) for task, contract in contracts.items()
        for domain in contract["control_domains"] for representation in REPRESENTATIONS}
    assert all(row["module_tuple"]["terminal_optimizer"] == "finite_action_enumeration" for row in nominal)

    forward = [row for row in controllers if row["controller_route"] == "csl::reachability::nominal_forward"]
    expected_forward = {(task, domain, reducer, lp1, lp2, lp3) for task, contract in contracts.items()
        for domain in contract["control_domains"] for reducer in REDUCER_IDS
        for lp1 in LP_IDS for lp2 in LP_IDS for lp3 in LP_IDS}
    actual_forward = set()
    for row in forward:
        modules = row["module_tuple"]
        assert modules["geometry_projection"]["id"] == "csl.geometry.projection-materializer"
        assert modules["geometry_affine_sum"]["id"] == "csl.geometry.affine-sum"
        assert modules["affine_sum_converter"]["id"] == modules["converter"]["id"] == "csl.conversion.qhull"
        assert modules["terminal_optimizer"].startswith("not_used")
        actual_forward.add((row["task_id"], row["action_domain_kind"], identity(modules["vertex_reducer"]),
            identity(modules["vertex_lp_provider"]), identity(modules["affine_sum_converter_lp_provider"]),
            identity(modules["converter_lp_provider"])))
    assert len(forward) == 1620 and actual_forward == expected_forward

    nominal_predecessor = [row for row in controllers
        if row["controller_route"] == "csl::reachability::prepare_nominal_predecessor"]
    assert len(nominal_predecessor) == 6
    assert all(row["module_tuple"]["geometry_projection"]["id"] == "csl.geometry.projection-materializer"
        and row["module_tuple"]["vertex_lp_provider"].startswith("not_used")
        for row in nominal_predecessor)

    mpc11 = [row for row in controllers if row["controller_route"] == "benchmarks/reporting/mpc11/run_nmpc.py"]
    expected_mpc11_admitted = {
        ("syn-nl-lv-01/continuous-receding/1", "continuous"),
        ("syn-nl-fuel-01/continuous-receding/1", "continuous"),
    }
    assert {(row["task_id"], row["action_domain_kind"]) for row in mpc11 if row["status"] == "admitted"} == expected_mpc11_admitted
    receipts = output["external_preparation_receipts"]["routes"]
    assert {row["task_id"] for row in receipts} == {task for task, _ in expected_mpc11_admitted}
    assert all(row["source_binding_validated"] is True and row["solve_performed"] is False
        and row["runtime"]["solver_interface_prepared"] == "IpoptInterface" for row in receipts)
    for row in mpc11:
        if row["status"] == "admitted":
            receipt = row["external_prepare_receipt"]
            assert receipt["task_id"] == row["task_id"]
            assert receipt["model_id"] == row["model_id"]
            assert receipt["controller_id"] == row["module_tuple"]["controller"]
            assert row["module_tuple"]["vertex_lp_provider"].startswith("not_used")
            assert row["module_tuple"]["terminal_optimizer"]["prepared_interface"] == "IpoptInterface"

    status_rows = {status: [row for row in controllers if row["status"] == status]
        for status in ("admitted", "incompatible", "implementation_missing", "backend_unavailable", "excluded")}
    assert len(status_rows["admitted"]) == 2
    assert len(status_rows["backend_unavailable"]) == 0  # This build has HiGHS and Qhull enabled.
    assert all(row["first_unmet"]["field"] and row["first_unmet"]["reason"]
        for row in controllers if row["first_unmet"])

    predecessors = output["closed_loop_predecessor_candidates"]
    expected_predecessors = {(task, representation, lp) for task in EXPECTED_TASKS
        for representation in PREDECESSOR_REPRESENTATIONS for lp in LP_IDS}
    assert len(predecessors) == 45
    actual_predecessors = set()
    for row in predecessors:
        modules = row["module_tuple"]
        actual_predecessors.add((row["task_id"], modules["reachable_set_representation"],
            identity(modules["terminal_lp_provider"])))
        assert modules["vertex_lp_provider"].startswith("not_used")
        assert modules["terminal_minimizer"]["symbol"] == "csl::synthesis::TerminalOptimizer::solve"
        assert modules["terminal_optimizer_provider"] == {"id": "csl.convex.highs", "version": "1.0.0+highs.1.11.0"}
        contract = contracts[row["task_id"]]
        canonical = {"task_contract_sha256": row["task_contract_sha256"],
            "model_id": row["model_id"], "module_tuple": modules}
        expected_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        assert row["graph_fingerprint"] == expected_hash
        assert row["graph_id"].endswith(f"cfg-{expected_hash[:16]}")
        assert row["action_domain_ids"] == sorted(domain["problem_id"]
            for domain in contract["control_domains"].values())
        assert row["fixed_plan_propagation_delivered_separately"]
        assert row["first_unmet"]["reason"]
    assert actual_predecessors == expected_predecessors
    assert any(row["status"] == "incompatible" and row["task_id"] ==
        "syn-nl-lv-01/continuous-receding/1" and row["module_tuple"]["reachable_set_representation"] == "parallelotope"
        and row["first_unmet"]["field"] == "request.dimension" for row in predecessors)
    assert any(row["status"] == "excluded" for row in output["inventory"]["known_candidate_classifications"])

    group1_references = output["full_task_group1_reference_candidates"]
    expected_reference_ids = {f"{task}/{domain}/vertex-reference/{route}"
        for task, contract in contracts.items() for domain in contract["control_domains"]
        for route in ("quickhull2d", "csl::geometry::legacy_btulshor::modif",
            "csl::geometry::legacy_btulshor::kpabep", "csl::geometry::legacy_btulshor::reach")}
    assert len(group1_references) == 24
    assert {row["candidate_id"] for row in group1_references} == expected_reference_ids
    for row in group1_references:
        assert row["task_contract_sha256"] == next(candidate["task_contract_sha256"]
            for candidate in controllers if candidate["task_id"] == row["task_id"])
        symbol = row["module_tuple"].get("vertex_geometry_reference", row["module_tuple"].get("source_faithful_vertex_route"))
        assert symbol and symbol.get("symbol") in {"csl::geometry::quickhull_2d",
            "csl::geometry::legacy_btulshor::modif", "csl::geometry::legacy_btulshor::kpabep",
            "csl::geometry::legacy_btulshor::reach"}
        if row["task_id"] == "syn-nl-lv-01/continuous-receding/1" and symbol.get("symbol") == "csl::geometry::quickhull_2d":
            assert row["status"] == "implementation_missing" and row["first_unmet"]["field"] == "geometry.reducer_adapter"
        if row["model_dimension"] == 4 and symbol.get("symbol") == "csl::geometry::quickhull_2d":
            assert row["status"] == "incompatible" and row["first_unmet"]["field"] == "points.dimension"
    legacy_reach = next(row for row in group1_references if row["module_tuple"].get(
        "source_faithful_vertex_route", {}).get("symbol") == "csl::geometry::legacy_btulshor::reach")
    assert legacy_reach["module_tuple"]["coupled_source_routes"] == [
        "csl::geometry::legacy_btulshor::kpabep", "csl::geometry::legacy_btulshor::modif"]
    assert output["finite_profile_boundaries"]["quickhull2d"]["dimension"] == 2
    assert output["finite_profile_boundaries"]["finite_action_nominal"]["plan_budget"] == 27

    group4_functions = output["full_task_group4_function_candidates"]
    expected_group4 = {(task, domain, symbol) for task, contract in contracts.items()
        for domain in contract["control_domains"] for symbol in (
            "csl::geometry::polyhedral::intersect_h",
            "csl::geometry::polyhedral::remove_redundant_halfspaces")}
    actual_group4 = set()
    for row in group4_functions:
        symbol = row["module_tuple"]["supporting_operation"]["symbol"]
        actual_group4.add((row["task_id"], row["action_domain_kind"], symbol))
        assert row["status"] == "implementation_missing"
        assert row["module_tuple"]["vertex_lp_provider"].startswith("not_used")
        assert row["module_tuple"]["controller_route"].startswith("not_used")
        canonical = {"task_contract_sha256": row["task_contract_sha256"],
            "action_domain_id": row["action_domain_id"], "module_tuple": row["module_tuple"]}
        expected_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        assert row["graph_fingerprint"] == expected_hash
        assert row["candidate_id"].endswith(expected_hash[:16])
        assert row["first_unmet"]["reason"]
    assert len(group4_functions) == 12 and actual_group4 == expected_group4
    source_group4 = [row for row in output["inventory"]["modules"] if row["group"] == "supporting_operations"]
    observed_identities = collected_strings({key: value for key, value in output.items() if key != "inventory"})
    assert all((record["identity"].get("id") or record["identity"].get("symbol")) in observed_identities
        for record in source_group4)
    task_binding_negative_checks(root)
    print("full finite catalogue passed: 3,318 controller tuples, 45 predecessor/representation/terminal-LP tuples, 24 full-task legacy/QuickHull choices, 2 source-bound external prepares")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

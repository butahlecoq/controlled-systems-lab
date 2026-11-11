#!/usr/bin/env python3
"""Exercise the native four-group inventory and compiled hull-provider receipt CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    executable = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    completed = subprocess.run(
        [str(executable), "--inventory", str(root / "docs/catalogue/module-composition-inventory-v1.json")],
        check=True, capture_output=True, text=True,
    )
    output = json.loads(completed.stdout)
    assert output["schema"] == "csl.module-composition-output/1"
    assert set(group["id"] for group in output["inventory"]["groups"]) == {
        "vertex_lp_simplex", "reachable_set_representation", "controller", "supporting_operations"
    }
    rows = output["candidates"]
    expected_rows = 10 * (2 if output["compiled_backends"]["highs"] else 1)
    assert len(rows) == expected_rows, f"candidate universe mismatch: {len(rows)} != {expected_rows}"
    assert all(row["status"] == "admitted" for row in rows)
    assert len({row["graph_id"] for row in rows}) == len(rows)
    for row in rows:
        active = row["active_roles"]
        providers = row["prepared_providers"]
        assert active["terminal_optimizer"] == "not_used"
        assert {provider["actual"] for provider in providers} == {
            active["vertex_reducer"]["id"], active["vertex_lp_provider"]["id"]
        }
        assert all(provider["actual"] == provider["requested"] for provider in providers)
        assert row["attempt"] == "completed", row
        assert row["retained"] == [0, 1, 2, 3], row
        if active["vertex_reducer"]["id"] == "csl.hull.lp-membership":
            assert row["outer_lp_runner_queries"], "LP membership fixture produced no calls"
        for query in row["outer_lp_runner_queries"]:
            assert query["status"] == "completed", query
            assert query["actual"] == active["vertex_lp_provider"]["id"], query
            assert query["version"] == active["vertex_lp_provider"]["version"], query
            assert query["problem"] and query["program"] and query["outcome"], query
            assert query["returned_problem"] and query["returned_program"], query
        child_summary = row["child_lp_port_trace_summary"]
        child_queries = row["child_lp_port_invocations"]
        assert child_summary["captured"] + child_summary["omitted"] == child_summary["total"], row
        assert len(child_queries) == child_summary["captured"], row
        assert child_summary["native_solver_entry_proven"] is False, row
        for query in child_queries:
            assert query["requested_provider"] and query["actual_provider"] and query["actual_version"], query
            assert query["problem"] and query["program"] and query["status"], query
            assert len(query["raw_diagnostics"]) <= 1024, query
    traced_reducers = {row["active_roles"]["vertex_reducer"]["id"] for row in rows
        if row["child_lp_port_trace_summary"]["total"]}
    assert "csl.hull.itis17.a43-certified-basis-reuse" in traced_reducers
    assert "csl.hull.recursive-split-merge" in traced_reducers
    assert "csl.hull.phase-one-basis-bulk" in traced_reducers
    controller_rows = output["controller_candidates"]
    assert len(controller_rows) == 1
    controller = controller_rows[0]
    assert controller["strategy"] == "csl.synthesis.ts01-analytic"
    assert controller["status"] == "admitted"
    assert controller["reprepare"] == "admitted"
    assert controller["prepared_providers"][0]["actual"] == controller["strategy"]
    expected_representation_graphs = {
        f"nominal-two-points-v1/{representation}"
        for representation in ("exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid")
    }
    representation_rows = output["representation_candidates"]
    assert {row["graph_id"] for row in representation_rows} == expected_representation_graphs
    assert all(row["status"] == "admitted" and row["attempt"] == "completed" for row in representation_rows)
    assert all(row["active_roles"]["vertex_lp_provider"] == "not_used" for row in representation_rows)
    assert all(row["active_roles"]["terminal_optimizer"] == "finite_action_enumeration"
        for row in representation_rows)
    assert all(row["profile"]["state_dimension"] == 4 and row["profile"]["control_dimension"] == 1
        and row["profile"]["horizon"] == 3 and row["profile"]["action_count"] == 3
        and row["profile"]["plan_budget"] == 27 for row in representation_rows)
    assert all(row["replay"]["state_count"] == 4 and row["replay"]["control_count"] == 3
        for row in representation_rows)
    priority_rows = output["priority_tie_candidates"]
    assert len(priority_rows) == 10
    assert all(row["active_roles"]["vertex_lp_provider"]["id"] == "phase-one-priority-tie"
        for row in priority_rows)
    assert all(row["status"] == "admitted" or row["first_unmet"] for row in priority_rows)
    incomplete_priority = next(row for row in priority_rows
        if row["active_roles"]["vertex_reducer"]["id"] == "csl.hull.lp-membership")
    assert incomplete_priority["attempt"] == "incomplete"
    failure = incomplete_priority["execution_first_unmet"]
    assert failure["field"] == "phase_one.structural_entering_priorities" and failure["reason"]
    assert failure["module_tuple"] == {"requested": "phase-one-priority-tie", "actual": "phase-one-priority-tie"}
    priority_profile = output["priority_tie_lp_profile"]
    assert priority_profile["status"] == "admitted" and priority_profile["attempt"] == "completed"
    assert priority_profile["provider"] == {
        "id": "phase-one-priority-tie", "version": "1", "actual": "phase-one-priority-tie"}
    assert priority_profile["profile"]["variables"] == len(priority_profile["profile"]["structural_priorities"]) == 5
    operation_rows = output["supporting_operation_candidates"]
    assert len(operation_rows) == 1
    operation = operation_rows[0]
    if output["compiled_backends"]["qhull"] and output["compiled_backends"]["highs"]:
        assert operation["status"] == "admitted" and operation["attempt"] == "completed", operation
        assert operation["active_roles"]["converter"]["id"] == "csl.conversion.qhull"
        assert operation["active_roles"]["vertex_lp_provider"] == "not_used"
        assert operation["output_representation"] == "csl.polyhedron.v" and operation["output_vertices"] == 4
    else:
        assert operation["status"] == "backend_unavailable" and operation["first_unmet"]
    generator_operations = output["generator_operation_candidates"]
    assert {row["graph_id"] for row in generator_operations} == {
        "supporting/generator-affine-image-1d-v1", "supporting/generator-v-conversion-1d-v1"}
    assert all(row["status"] == "admitted" and row["attempt"] == "completed"
        and row["requested"] == row["actual"] for row in generator_operations)
    affine_image = next(row for row in generator_operations if "affine-image" in row["graph_id"])
    assert affine_image["actual"] == {"id": "csl.geometry.generators.operations", "version": "1.1.0"}
    assert affine_image["center"] == [1] and affine_image["generators"] == [2]
    generator_v = next(row for row in generator_operations if "v-conversion" in row["graph_id"])
    assert generator_v["actual"] == {"id": "csl.geometry.generators.v-conversion", "version": "1.0.0"}
    assert generator_v["vertices"] == [-1, 3]
    approximation_rows = output["approximation_candidates"]
    assert len(approximation_rows) == 1
    approximation = approximation_rows[0]
    assert approximation["status"] == "admitted" and approximation["attempt"] == "completed", approximation
    assert approximation["active_roles"]["approximation"] == {"id": "csl.approximation.box", "version": "1"}
    assert approximation["active_roles"]["vertex_lp_provider"] == "not_used"
    assert approximation["input_dimension"] == 2 and approximation["relation"] == "outer"
    references = output["geometric_reference_candidates"]
    assert {row["graph_id"] for row in references} == {
        "geometry/quickhull2d/square-v1",
        "geometry/quickhull2d/point-cloud-dimension-4-v1",
        "legacy-btulshor/kpabep/source-v1",
        "legacy-btulshor/reach/source-v1",
    }
    quickhull = next(row for row in references if row["graph_id"] == "geometry/quickhull2d/square-v1")
    assert quickhull["status"] == "admitted" and quickhull["retained"] == [0, 1, 2, 3]
    dimension_reject = next(row for row in references if "dimension-4" in row["graph_id"])
    assert dimension_reject["status"] == "incompatible" and dimension_reject["first_unmet"]["field"] == "points"
    assert all(row["status"] == "admitted" for row in references if row["graph_id"].startswith("legacy-btulshor/"))
    source_operations = output["source_index_operation_candidates"]
    assert len(source_operations) == 4
    assert {row["source_provider"].split("@")[0] for row in source_operations} == {
        "csl.hull.source.quickhull-2d", "csl.hull.source.btulshor-kpabep"
    }
    assert {row["graph_id"].rsplit("/", 1)[-1] for row in source_operations} == {
        "affine-image", "control-minkowski-sum"
    }
    for row in source_operations:
        assert row["status"] == "admitted" and row["attempt"] == "completed", row
        assert row["active_roles"]["vertex_lp_provider"] == "not_used"
        assert row["active_roles"]["terminal_optimizer"] == "not_used"
        assert row["active_roles"]["h_to_v_converter"] == "not_used"
        assert any("source-index invocation:" in item for item in row["evidence"]), row
        assert any("checker invocation:" in item and "status=verified" in item
            for item in row["evidence"]), row
    optimizers = output["terminal_optimizer_candidates"]
    assert len(optimizers) == 1
    optimizer = optimizers[0]
    if output["compiled_backends"]["highs"]:
        assert optimizer["status"] == "admitted" and optimizer["attempt"] == "completed", optimizer
        assert optimizer["active_roles"]["terminal_minimizer"] == "csl::synthesis::TerminalOptimizer::solve"
        assert optimizer["active_roles"]["terminal_lp_provider"]["id"] == "csl.lp.highs"
        assert optimizer["active_roles"]["terminal_optimizer_provider"]["id"] == "csl.convex.highs"
        assert optimizer["active_roles"]["vertex_lp_provider"] == "not_used"
        assert optimizer["candidate"] == 1 and optimizer["expected_candidate"] == 1
        assert optimizer["optimal_relation_contains_candidate"] is True
    else:
        assert optimizer["status"] == "backend_unavailable" and optimizer["first_unmet"]
    unavailable = output["backend_unavailable_candidates"]
    if not output["compiled_backends"]["highs"]:
        assert sum(row["status"] == "backend_unavailable" and
            row["module_tuple"].get("vertex_lp_provider") == "csl.lp.highs" for row in unavailable) == 10
    if not output["compiled_backends"]["qhull"]:
        assert any(row["status"] == "backend_unavailable" and
            row["module_tuple"].get("converter") == "Qhull" for row in unavailable)
    print(f"native composition catalogue passed: {len(rows)} admitted hull graphs, "
        f"{len(representation_rows)} representation executions, {len(priority_rows)} priority-tie graph probes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

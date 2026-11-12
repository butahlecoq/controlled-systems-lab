#!/usr/bin/env python3
"""Independently check the retained 2D Strategy A choice matrix."""

import json
import subprocess
import sys


def main() -> int:
    result = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
    document = json.loads(result.stdout)
    assert document["schema"] == "csl.strategy-a-each-choice-pipeline/1"
    assert document["scope"].startswith("one-step, two-state, two-control")
    assert document["task"]["state_dimension"] == 2
    assert document["task"]["horizon"] == 1
    inventory = document["choice_inventory"]
    reducers = {
        "csl.hull.lp-membership",
        "csl.hull.phase-one-basis-bulk",
        "csl.hull.ordered-membership",
        "csl.hull.itis17.a43-certified-basis-reuse",
        "csl.hull.itis17.a43-artificial-basis",
        "csl.hull.itis17.a43-largest-norm-tie",
        "csl.hull.itis17.a44-incremental-lp",
        "csl.hull.itis17.a44-paper-farthest-incremental-lp",
        "csl.hull.grouped-membership",
        "csl.hull.recursive-split-merge",
    }
    source_reducers = {
        "csl.hull.source.quickhull-2d",
        "csl.hull.source.btulshor-kpabep",
    }
    lp_profiles = {"csl.lp.highs", "phase-one-bland", "phase-one-priority-tie"}
    assert inventory["hull_reducers"] == len(reducers)
    assert set(inventory["vertex_lp_profiles"]) == lp_profiles
    assert set(inventory["source_index_reducers"]) == source_reducers
    assert inventory["converter"].startswith("csl.conversion.qhull@")
    assert set(inventory["terminal_optimizer_choices"]) == {"csl.lp.highs", "csl.convex.highs"}

    rows = document["attempts"]
    assert len(rows) == 128, len(rows)
    expected = set()
    for vertex_lp in lp_profiles:
        for terminal_lp in lp_profiles:
            expected.update(("linear", reducer, vertex_lp, terminal_lp) for reducer in reducers)
        expected.update(("quadratic", reducer, vertex_lp, "not_used") for reducer in reducers)
    for terminal_lp in lp_profiles:
        expected.update(("linear", reducer, "not_used", terminal_lp) for reducer in source_reducers)
    expected.update(("quadratic", reducer, "not_used", "not_used") for reducer in source_reducers)
    actual = {
        (row["task"], row["vertex_reducer"], row["vertex_lp_provider"], row["terminal_lp_provider"])
        for row in rows
    }
    assert actual == expected
    phase_one_terminal_rejections = [row for row in rows if row["task"] == "linear" and
        row["terminal_lp_provider"] in {"phase-one-bland", "phase-one-priority-tie"}]
    assert len(phase_one_terminal_rejections) == 64
    assert all(row["status"] == "operation_rejected" and "phase_one.objective" in row["first_unmet"]
               for row in phase_one_terminal_rejections)
    numeric_boundaries = [row for row in rows if row["vertex_reducer"] == "csl.hull.source.btulshor-kpabep" and
        row["terminal_optimizer_choice"] in {"csl.lp.highs", "csl.convex.highs"} and
        row.get("first_unmet", "").startswith("highs.")]
    assert len(numeric_boundaries) == 2
    assert all(row["status"] == "operation_rejected" for row in numeric_boundaries)
    for row in numeric_boundaries:
        assert any("MODIF source statuses retained verbatim" in call for call in row["operation_call_evidence"]), row
        assert any("modif_status=2" in call for call in row["operation_call_evidence"]), row
        assert any("checker invocation:" in call and "status=verified" in call
                   for call in row["operation_call_evidence"]), row
        assert any("Qhull 8.0.2 Qx V-to-H conversion output" in item and
                   "upstream=csl.hull.source.btulshor-kpabep@1.0.0" in item and
                   "ordered_V_vertices=" in item and "1.1102230246251565e-16" in item
                   for item in row["program_boundary_observations"]), row
        assert any(("min_nonzero_A=1.1102230246251565e-16" in item and "highs.matrix:" in item) or
                   ("min_nonzero_A=1.1102230246251565e-16" in item and "highs.convex.matrix:" in item)
                   for item in row["program_boundary_observations"]), row

    for row in rows:
        assert row["controller"] == "csl.synthesis.reach-back@1"
        assert row["representation"] == "csl.polyhedron.h"
        assert row["converter"] == "csl.conversion.qhull"
        assert row["converter_lp_provider"] == "csl.lp.highs"
        assert row["terminal_optimizer_choice"] == (
            "csl.lp.highs" if row["task"] == "linear" else "csl.convex.highs"), row
        assert row["status"] in {"completed", "operation_rejected", "contract_rejected", "resource_limit",
                                 "deadline_expired", "cancelled", "numerical_failure", "unsupported"}, row
        counts = row["lp_call_counts"]
        assert counts["converter"] > 0, row
        if row["vertex_reducer"] in source_reducers:
            assert row["vertex_lp_provider"] == "not_used"
            assert counts["vertex"] == 0
            assert any("source-index invocation:" in call for call in row["operation_call_evidence"]), row
            assert any("checker invocation:" in call and "status=verified" in call
                       for call in row["operation_call_evidence"]), row
        else:
            assert row["vertex_lp_provider"] in lp_profiles
            assert counts["vertex"] > 0, row
            assert any(row["vertex_reducer"] in call and "HullReducerPort invocation:" in call
                       for call in row["operation_call_evidence"]), row
            assert any(row["vertex_lp_provider"] in call and
                       ("vertex LP invocation record" in call or "child LPPort invocation" in call)
                       for call in row["operation_call_evidence"]), row

        assert row["conversion_calls"], row
        assert any("csl.polyhedron.h->csl.polyhedron.v" in call for call in row["conversion_calls"]), row
        assert any("csl.polyhedron.v->csl.polyhedron.h" in call for call in row["conversion_calls"]), row
        assert all("csl.conversion.qhull" in call and "lp=csl.lp.highs" in call
                   for call in row["conversion_calls"]), row

        if row["status"] == "completed":
            assert row["independent_check"]["forward_hull_is_unit_square"], row
            assert row["independent_check"]["analytic_control_histories_replay"], row
            assert row["independent_check"]["candidate_relation_returned"], row
            assert set(map(tuple, row["forward_vertices"])) == {(0,0),(0,1),(1,0),(1,1)}, row
            assert row["terminal_point"] == ([[1,0]] if row["task"] == "linear" else [[0,0]]), row
            assert row["lp_call_counts"]["terminal_convex"] > 0 if row["task"] == "quadratic" else row["lp_call_counts"]["terminal_lp"] > 0
            if row["task"] == "quadratic":
                assert row["terminal_lp_provider"] == "not_used", row
                assert row["lp_call_counts"]["terminal_lp"] == 0, row
            assert row["terminal_optimizer_actual"] == (
                "csl.convex.highs" if row["task"] == "quadratic" else "csl.lp.highs"), row
        elif row["task"] == "linear" and row["terminal_lp_provider"] != "csl.lp.highs":
            assert row["first_unmet"] and "phase_one.objective" in row["first_unmet"], row

    print(f"#944 2D Strategy A pipeline: {len(rows)} task/choice tuples checked; "
          f"{sum(row['status'] == 'completed' for row in rows)} completed, "
          f"{len(phase_one_terminal_rejections)} Phase-I/nonzero-objective rejections, "
          f"{len(numeric_boundaries)} Qhull/HiGHS numeric-boundary rejections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

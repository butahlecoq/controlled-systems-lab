#!/usr/bin/env python3
"""Independently check the retained 2D Strategy A choice matrix."""

import json
import math
import subprocess
import sys


def main() -> int:
    result = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
    document = json.loads(result.stdout)
    assert document["schema"] == "csl.strategy-a-each-choice-pipeline/2"
    assert document["scope"].startswith("one-step nominal Strategy A candidate construction")
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
    assert inventory["history_recovery_api"] == "csl.synthesis.recover_joint_history@1"
    assert inventory["history_selection_provider"] == "csl.lp.highs@1"

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
            assert row["independent_check"]["candidate_relation_returned"], row
            assert row["history_recovery_api"] == "csl.synthesis.recover_joint_history@1", row
            assert row["history_recovery_status"] == "completed", row
            assert row["history_selection_provider"] == "csl.lp.highs", row
            assert row["history_selection_program"] == f"issue944-history-selection:{row['task']}", row
            assert row["history_selection_objective"] == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0], row
            assert counts["history_selection"] == 1, row
            assert row["independent_check"]["selected_history_in_returned_family"], row
            assert row["independent_check"]["selected_history_in_terminal_family"], row
            calls = row["operation_call_evidence"]
            assert any("public recovery API invocation" in call and
                       "csl.synthesis.recover_joint_history@1" in call for call in calls), row
            assert any("recovered-history selection LP invocation: role=history_selection; "
                       "provider=csl.lp.highs;" in call and "calls=1" in call for call in calls), row
            assert set(map(tuple, row["forward_vertices"])) == {(0,0),(0,1),(1,0),(1,1)}, row
            assert row["selected_history_coordinates"] == [
                "x0.position", "x0.velocity", "x1.position", "x1.velocity", "u0.0", "u0.1"], row
            history = row["selected_history"]
            assert len(history) == 6 and all(math.isfinite(value) for value in history), row
            x0, endpoint, control = history[:2], history[2:4], history[4:6]
            assert x0 == [0.0, 0.0], row
            assert all(0.0 <= value <= 1.0 for value in control), row
            assert endpoint == [x0[i] + control[i] for i in range(2)], row
            assert all(0.0 <= value <= 1.0 for value in endpoint), row
            optimizer_anchor = row["terminal_point"][0]
            assert len(optimizer_anchor) == 2 and all(math.isfinite(value) for value in optimizer_anchor), row
            assert all(0.0 <= value <= 1.0 for value in optimizer_anchor), row
            if row["task"] == "linear":
                selected_objective = -endpoint[0]
                anchor_objective = -optimizer_anchor[0]
                assert selected_objective == -1.0 and anchor_objective == -1.0, row
            else:
                selected_objective = sum(value * value for value in endpoint)
                anchor_objective = sum(value * value for value in optimizer_anchor)
                assert selected_objective == 0.0 and anchor_objective == 0.0, row
            assert row["lp_call_counts"]["terminal_convex"] > 0 if row["task"] == "quadratic" else row["lp_call_counts"]["terminal_lp"] > 0
            if row["task"] == "quadratic":
                assert row["terminal_lp_provider"] == "not_used", row
                assert row["lp_call_counts"]["terminal_lp"] == 0, row
            assert row["terminal_optimizer_actual"] == (
                "csl.convex.highs" if row["task"] == "quadratic" else "csl.lp.highs"), row
        elif row["task"] == "linear" and row["terminal_lp_provider"] != "csl.lp.highs":
            assert row["first_unmet"] and "phase_one.objective" in row["first_unmet"], row

    regression_result = subprocess.run([sys.argv[1], "--terminal-membership-indexing-regression"],
        check=True, capture_output=True, text=True)
    regression = json.loads(regression_result.stdout)
    assert regression["schema"] == "csl.strategy-a-terminal-membership-indexing-regression/1"
    assert regression["task"] == {
        "dynamics": "x_next=x+u",
        "initial_state": [2, 3],
        "initial_state_box": [[1, 2], [2, 3]],
        "control_box": [[0, 1], [1, 2]],
        "next_state_box": [[2, 3], [4, 5]],
    }
    attempt = regression["attempt"]
    assert attempt["status"] == "completed", attempt
    assert attempt["history_recovery_status"] == "completed", attempt
    assert attempt["history_recovery_api"] == "csl.synthesis.recover_joint_history@1", attempt
    assert attempt["history_selection_provider"] == "csl.lp.highs", attempt
    assert attempt["independent_check"]["selected_history_in_returned_family"], attempt
    assert attempt["independent_check"]["selected_history_in_terminal_family"], attempt
    assert not attempt["independent_check"]["selected_control_in_terminal_family"], attempt
    history = attempt["selected_history"]
    x0, endpoint, control = history[:2], history[2:4], history[4:6]
    assert x0 == [2.0, 3.0], attempt
    assert endpoint != control, attempt
    assert endpoint == [x0[i] + control[i] for i in range(2)], attempt
    assert all(low <= value <= high for (low, high), value in zip([[1, 2], [2, 3]], x0)), attempt
    assert all(low <= value <= high for (low, high), value in zip([[0, 1], [1, 2]], control)), attempt
    assert all(low <= value <= high for (low, high), value in zip([[2, 3], [4, 5]], endpoint)), attempt
    assert any(value < low or value > high for (low, high), value in zip([[2, 3], [4, 5]], control)), attempt

    print(f"#944 2D Strategy A pipeline: {len(rows)} task/choice tuples checked; "
          f"{sum(row['status'] == 'completed' for row in rows)} completed with recovered selected histories, "
          f"{len(phase_one_terminal_rejections)} Phase-I/nonzero-objective rejections, "
          f"{len(numeric_boundaries)} Qhull/HiGHS numeric-boundary rejections; "
          "terminal-state membership indexing regression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

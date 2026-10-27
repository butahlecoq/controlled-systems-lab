"""Hybrid case inputs, analytic constructions, and source evidence."""
from __future__ import annotations

import json
from pathlib import Path

from report_data import require
import stage_ext07 as ext07_reports


def load_examples(catalog):
    catalog = Path(catalog)
    examples = []
    CURRENT_EXT07_TWO_PARAMETER_REPORT = "ext07-hybrid-two-parameter-8ad871b5ea29fc7b"
    ext07_catalog = json.loads((catalog.parent / "ext07-publications.json").read_text(encoding="utf-8"))
    require(ext07_catalog.get("schema") == "csl.ext07-publications/1" and
            isinstance(ext07_catalog.get("reports"), list),
            "gallery needs reviewed EXT-07 reports")
    reports_by_schema = {}
    for entry in ext07_catalog["reports"]:
        bundle = catalog.parent / entry["report_id"]
        require(ext07_reports.catalog_entry(bundle) == entry,
                "EXT-07 publication identity differs")
        reports_by_schema.setdefault(entry["schema"], []).append((entry, bundle))
    one_step = reports_by_schema.get("csl.ext07-hybrid-profile-report/1", [])
    two_parameter = [item for item in reports_by_schema.get(
        "csl.ext07-hybrid-two-parameter-report/1", [])
        if item[0].get("verifier_id") == "csl.hybrid.exact-linear-h" and
        item[0].get("report_id") == CURRENT_EXT07_TWO_PARAMETER_REPORT]
    require(len(one_step) == 1 and len(two_parameter) == 1,
            "gallery needs one one-step report and one exact-H two-control report")
    one_step_entry, one_step_bundle = one_step[0]
    two_parameter_entry, two_parameter_bundle = two_parameter[0]
    inputs = {
        "initial": {"mode": "start", "state": [0]},
        "horizon": 2,
        "state_dimension": 1,
        "control_dimension": 1,
        "allowed_terminal_modes": ["terminal"],
        "modes": [
            {"id": "start", "active_stages_on_path": [0],
             "flow_by_stage": [{"A": 1, "B": 1, "offset": 0}, {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"interval": [0, 1]}, {"singleton": 0}],
             "invariants_by_boundary": ["universal"] * 3},
            {"id": "middle", "active_stages_on_path": [1],
             "flow_by_stage": [{"A": 1, "B": 1, "offset": 0}, {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"singleton": 0}, {"singleton": 0}],
             "invariants_by_boundary": ["universal"] * 3},
            {"id": "terminal", "active_stages_on_path": [2],
             "flow_by_stage": [{"A": 1, "B": 1, "offset": 0}, {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"singleton": 0}, {"singleton": 0}],
             "invariants_by_boundary": ["universal"] * 3},
        ],
        "edges": [
            {"id": "enter", "source": "start", "target": "middle",
             "guards_by_stage": [{"interval": [0, 1]}, {"type": "universal", "dimension": 1}],
             "reset_by_stage": [{"type": "identity", "dimension": 1},
                                {"type": "universal", "dimension": 2}]},
            {"id": "to-terminal", "source": "middle", "target": "terminal",
             "guards_by_stage": [{"type": "universal", "dimension": 1}, {"interval": [0, 0.5]}],
             "reset_by_stage": [{"type": "universal", "dimension": 2},
                                {"type": "identity", "dimension": 1}]},
        ],
        "edge_timing": "guards constrain the stage pre-reset state; reset relations map pre-reset to the next state",
        "terminal_objective": "minimize x[2]",
    }
    analytic = {
        "fixed_path": ["enter", "to-terminal"],
        "joint_relation": "x[0]=0; u[0]=x_pre[0]=x[1]=x_pre[1]=x[2]; u[1]=0; 0<=u[0]<=0.5",
        "feasible_projection": "(u[0], x[2]) = (s, s), 0<=s<=0.5",
        "complete_minimizer": "all joint coordinates are zero",
        "minimum_objective": 0,
    }
    examples.append(dict(
        slug="two_stage_scalar_family", title="A two-stage scalar family",
        vertices=[[0, 0], [0.5, 0.5]], points=[[0, 0], [0.5, 0.5]], indices=[0, 1],
        domain=(0, 0.5), inputs=inputs, analytic=analytic,
        report_id=one_step_entry["report_id"], records_path=one_step_bundle / "records.json",
        source="c6d135c94ee0fe4fece074b455dae18bee0d22b2",
        harness="451d0157109b03ef8fab5a656b487c248b7f29a4", kind="hybrid"))
    two_parameter_inputs = {
        "initial": {"mode": "two-parameter-start", "state": [0]},
        "horizon": 2,
        "state_dimension": 1,
        "control_dimension": 1,
        "allowed_terminal_modes": ["two-parameter-terminal"],
        "modes": [
            {"id": "two-parameter-start", "active_stages_on_path": [0],
             "flow_by_stage": [{"A": 0, "B": 1, "offset": 0},
                               {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"interval": [0, 1]}, {"singleton": 0}],
             "invariants_by_boundary": ["universal", "universal", "universal"]},
            {"id": "two-parameter-middle", "active_stages_on_path": [1],
             "flow_by_stage": [{"A": 0, "B": 1, "offset": 0},
                               {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"singleton": 0}, {"interval": [0, 1]}],
             "invariants_by_boundary": ["universal", "universal", "universal"]},
            {"id": "two-parameter-terminal", "active_stages_on_path": [2],
             "flow_by_stage": [{"A": 0, "B": 1, "offset": 0},
                               {"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"singleton": 0}, {"singleton": 0}],
             "invariants_by_boundary": ["universal", "universal", {"interval": [0, 1]}]},
        ],
        "edges": [
            {"id": "two-parameter-enter-half", "source": "two-parameter-start",
             "target": "two-parameter-middle",
             "guards_by_stage": [{"interval": [0, 0.5]}, {"type": "universal", "dimension": 1}],
             "reset_by_stage": [{"type": "identity", "dimension": 1},
                                {"type": "universal", "dimension": 2}]},
            {"id": "two-parameter-enter-full", "source": "two-parameter-start",
             "target": "two-parameter-middle",
             "guards_by_stage": [{"type": "universal", "dimension": 1},
                                 {"type": "universal", "dimension": 1}],
             "reset_by_stage": [{"type": "identity", "dimension": 1},
                                {"type": "universal", "dimension": 2}]},
            {"id": "two-parameter-finish", "source": "two-parameter-middle",
             "target": "two-parameter-terminal",
             "guards_by_stage": [{"type": "universal", "dimension": 1},
                                 {"type": "universal", "dimension": 1}],
             "reset_by_stage": [{"type": "universal", "dimension": 2},
                                {"type": "identity", "dimension": 1}]},
        ],
        "edge_timing": "guards constrain the stage pre-reset state; reset relations map pre-reset to the next state",
        "terminal_objective": {"type": "linear", "coefficients": [0], "constant": 0},
    }
    two_parameter_paths = [
        {"path": ["two-parameter-enter-half", "two-parameter-finish"],
         "feasible_polygon_in_control_coordinates": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 1]]},
        {"path": ["two-parameter-enter-full", "two-parameter-finish"],
         "feasible_polygon_in_control_coordinates": [[0, 0], [1, 0], [0, 1]]},
    ]
    examples.append(dict(
        slug="two_parameter_scalar_polytopes", title="Two labelled optimal polygons",
        polygons=two_parameter_paths, points=[[0, 0], [0.5, 0], [0.5, 0.5], [0, 1],
                                               [1, 0], [0, 1]],
        indices=[], domain=(0, 1), inputs=two_parameter_inputs,
        analytic={
            "joint_relation": "[x0,u0,x_pre0,x1,u1,x_pre1,x2]=[0,u0,u0,u0,u1,u0+u1,u0+u1]",
            "feasibility": "u0>=0; u1>=0; u0+u1<=1",
            "enter_half_guard": "u0<=0.5",
            "enter_full_guard": "universal",
            "complete_optimal_family": "every point in each labelled feasible polygon; both paths are retained",
            "minimum_objective": 0,
        },
        report_id=two_parameter_entry["report_id"],
        records_path=two_parameter_bundle / "records.json",
        source="eb0645f522c78007e8ffc8a1dab6bff16840e64a",
        harness="eb0645f522c78007e8ffc8a1dab6bff16840e64a", kind="two_parameter"))
    projected_inputs = {
        "initial": {"mode": "projected-source", "state": [0]},
        "horizon": 1,
        "state_dimension": 1,
        "control_dimension": 1,
        "allowed_terminal_modes": ["projected-target"],
        "modes": [
            {"id": "projected-source", "active_stages_on_path": [0],
             "flow_by_stage": [{"A": 1, "B": 1, "offset": 0}],
             "controls_by_stage": [{"interval": [0, 1]}],
             "invariants_by_boundary": ["universal", "universal"]},
            {"id": "projected-target", "active_stages_on_path": [1],
             "flow_by_stage": [{"A": 1, "B": 0, "offset": 0}],
             "controls_by_stage": [{"universal": 0}],
             "invariants_by_boundary": ["universal", "universal"]},
        ],
        "edges": [{"id": "cap-at-half", "source": "projected-source",
                   "target": "projected-target",
                   "guards_by_stage": [{"interval": [0, 0.5]}],
                   "reset_by_stage": [{"type": "identity", "dimension": 1}]}],
        "edge_timing": "the guard constrains the post-flow, pre-reset state; the reset maps it to the next state",
        "terminal_objectives": [{"mode": "projected-target",
                                 "linear": {"coefficients": [1], "constant": 0},
                                 "id": "terminal-cost", "unit": "state"}],
    }
    projected_analytic = {
        "fixed_path": ["cap-at-half"],
        "joint_relation": "x[0]=0; x_pre[0]=x[0]+u[0]; x[1]=x_pre[0]; 0<=u[0]<=1; 0<=x_pre[0]<=0.5",
        "projected_terminal_set": "0<=x[1]<=0.5",
        "feasible_projection": "(u[0], x[1]) = (s, s), 0<=s<=0.5",
    }
    examples.append(dict(
        slug="one_step_projected_hybrid_reachability",
        title="Project a one-step hybrid state set",
        vertices=[[0, 0], [0.5, 0.5]], points=[[0, 0], [0.5, 0.5]],
        indices=[0, 1], domain=(0, 0.5), inputs=projected_inputs,
        analytic=projected_analytic, report_id=one_step_entry["report_id"],
        records_path=one_step_bundle / "records.json",
        source="065de5e45d295dfa099e25265c4014c0c46673f8",
        harness="065de5e45d295dfa099e25265c4014c0c46673f8",
        kind="projected_reachability"))
    return examples


def presentation(example):
    """Return the hybrid case explanation and the source/evidence contract."""
    kind = example["kind"]
    if kind == "two_parameter":
        explanation = ("The enter-half transition constrains the first pre-reset state to [0,0.5], while "
                       "enter-full has a universal guard. Both labelled paths then share the terminal bound "
                       "u₀+u₁≤1. The green quadrilateral lies inside the amber dashed triangle; their overlap "
                       "belongs to both mode paths.")
        result = ("Enter-half path: (0,0), (0.5,0), (0.5,0.5), (0,1). Enter-full path: "
                  "(0,0), (1,0), (0,1). The objective is identically zero, so every point in each complete "
                  "polygon is optimal and both labelled paths are retained.")
        notes = ("This exact rational construction illustrates the bounded two-free-control verifier profile. "
                 "It is an analytic illustration, not a saved solver run, timing result or measured fixture.")
        target, driver = "hybrid_path_program_tests", "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ("<p>The downloadable input record includes both free controls, all mode flows, invariants, "
                 "transition guards and resets, terminal policy and both path polygons.</p>")
        caption = "Amber dashed: enter-full path. Green: enter-half path. The green polygon is contained in the triangle; both retain all optimal points."
        platform_note = "This runs the functional two-parameter polygon oracle test; it creates no timing evidence."
        report_links = (f'<p>Related two-control report: <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                        f'<a href="../{example["report_id"]}/records.json">two-control raw record ↗</a>. '
                        'The measured report uses rectangular parameter sets and minimizes x_terminal=u0; '
                        'this illustration has a coupled triangular/quadrilateral feasible set and a constant-zero objective.</p>')
        raw_record_link = '<p><a href="two_parameter_scalar_polytopes.json">Two-control fixture and analytic raw record ↗</a></p>'
    elif kind == "projected_reachability":
        explanation = ("Start at x₀=0, flow with x_pre₁=x₀+u₀ for u₀∈[0,1], and take the fixed "
                       "transition only when its post-flow guard admits x_pre₁∈[0,0.5]. The identity "
                       "reset carries that state to x₁. Projecting the full labelled relation onto x₁ "
                       "gives the terminal interval shown.")
        result = "Projected terminal set: x₁∈[0,0.5]. The plotted full relation is (u₀,x₁)=(s,s), 0≤s≤0.5."
        notes = ("This exact rational construction illustrates the bounded one-transition scalar projected-state adapter profile. "
                 "It is an analytic illustration, not a saved solver run or a timing result; the independent contract test checks the joint relation and terminal-set bounds.")
        target, driver = "hybrid_path_program_tests", "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ("<p>The adapter retains the path-labelled joint H relation and returns its terminal H "
                 "projection. The request objective is present for contract completeness but does not "
                 "affect reachability.</p>")
        caption = "Green: full feasible control/terminal-state relation. Its terminal-state projection is the interval [0,0.5]."
        platform_note = "This runs the functional projected-state reachability test; it creates no timing evidence."
        report_links = (f'<p>Related one-step verification report (a separate algorithm): <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                        f'<a href="../{example["report_id"]}/records.json">one-step raw record ↗</a>.</p>')
        raw_record_link = '<p><a href="projected_hybrid_reachability.json">Projected reachability fixture and analytic raw record ↗</a></p>'
    else:
        explanation = ("Two scalar stages follow the fixed path start → middle → terminal. The first control is "
                       "free in [0,1] and the second is fixed at zero. The second transition requires its "
                       "pre-reset state x_pre[1] in [0,0.5], then its identity reset sets x[2]=x_pre[1].")
        result = ("Complete feasible family: (u₀, x₂) = (s, s), 0 ≤ s ≤ 0.5. "
                  "The unique minimum of x₂ is (u₀, x₂) = (0, 0).")
        notes = ("This is an exact rational illustration of a supported input, not a saved solver run or a timing "
                 "result. The independent test oracle derives the interval and checks both endpoints and an outside point.")
        target, driver = "hybrid_path_program_tests", "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ('<p>The fixture record contains all mode, flow, control, invariant, transition, guard, reset and objective inputs.</p>')
        caption = "Green: complete feasible relation. Gold: unique minimizer. Both axes show the same scalar system in control and terminal-state coordinates."
        platform_note = "This runs the functional two-stage oracle test; it creates no timing evidence."
        report_links = (f'<p>Related one-step report: <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                        f'<a href="../{example["report_id"]}/records.json">one-step raw record ↗</a>. '
                        'This two-stage illustration is not part of that measured fixture.</p>')
        raw_record_link = '<p><a href="two_stage_scalar_family.json">Two-stage fixture and analytic raw record ↗</a></p>'
    return {
        "explanation": explanation, "result": result, "notes": notes, "caption": caption,
        "example_type": "2D two-control family" if kind == "two_parameter" else
                        "2D projected reachability" if kind == "projected_reachability" else "2D control family",
        "extra": extra,
        "command": "cmake --preset dev\n"
                   f"cmake --build --preset dev --target {target}\n"
                   f"ctest --preset dev -R '^{target}$'",
        "reproduction": '<p>From the repository checkout at the linked fixture commit, configure the development preset and run:</p>',
        "platform_note": platform_note,
        "source_url": "https://github.com/butahlecoq/controlled-systems-lab/blob/" + example["harness"] + "/" + driver,
        "source_provenance": f'<p class="provenance">Algorithm source <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{example["source"]}"><code>{example["source"]}</code></a></p>',
        "raw_record_link": raw_record_link,
        "report_links": report_links,
    }


def inventory_entry(example):
    family = {
        "hybrid": "Hybrid control family",
        "two_parameter": "Hybrid control polytopes",
        "projected_reachability": "Projected hybrid reachability",
    }[example["kind"]]
    return {
        "family": family,
        "title": example["title"],
        "status": "educational-example",
        "anchor": example["slug"],
        "page": "index.html#" + example["slug"],
        "figure": example["slug"] + ".svg",
        "source_page": f'../{example["report_id"]}/index.html',
        "raw_record": f'../{example["report_id"]}/records.json',
    }


def download_records(examples):
    cases = {example["slug"]: example for example in examples}
    records = {
        "two_stage_scalar_family.json": {
            "schema": "csl.visual-example/ext07-two-stage-scalar/1",
            "illustration_only": True,
            "algorithm_source_commit": cases["two_stage_scalar_family"]["source"],
            "oracle_harness_commit": cases["two_stage_scalar_family"]["harness"],
            "inputs": cases["two_stage_scalar_family"]["inputs"],
            "analytic": cases["two_stage_scalar_family"]["analytic"],
        },
        "two_parameter_scalar_polytopes.json": {
            "schema": "csl.visual-example/ext07-two-parameter-scalar/1",
            "illustration_only": True,
            "algorithm_source_commit": cases["two_parameter_scalar_polytopes"]["source"],
            "oracle_harness_commit": cases["two_parameter_scalar_polytopes"]["harness"],
            "inputs": cases["two_parameter_scalar_polytopes"]["inputs"],
            "analytic": {"paths": cases["two_parameter_scalar_polytopes"]["polygons"],
                         **cases["two_parameter_scalar_polytopes"]["analytic"]},
        },
        "projected_hybrid_reachability.json": {
            "schema": "csl.visual-example/ext07-projected-hybrid-reachability/1",
            "illustration_only": True,
            "algorithm_source_commit": cases["one_step_projected_hybrid_reachability"]["source"],
            "oracle_harness_commit": cases["one_step_projected_hybrid_reachability"]["harness"],
            "inputs": cases["one_step_projected_hybrid_reachability"]["inputs"],
            "analytic": cases["one_step_projected_hybrid_reachability"]["analytic"],
        },
    }
    return {name: json.dumps(record, indent=2) + "\n" for name, record in records.items()}

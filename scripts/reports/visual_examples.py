"""Stage educational 2D illustrations from reviewed native records, without solving."""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

import geo04_registered_reports as intersection_reports
import geo06_registered_reports as hull_reports
import report_data
import stage_ext07 as ext07_reports
import visual_illustrations

CURRENT_EXT07_TWO_PARAMETER_REPORT = "ext07-hybrid-two-parameter-8ad871b5ea29fc7b"
SAVED_FIGURES = (
    dict(route="ext04-continuous-ebcf879d07ee9157", image="example-2d.svg", page="index.html",
         family="Continuous feedback · EXT-04", title="A partial observation policy over an initial set",
         alt="Four initial state generators map to four terminal states under a position-only affine policy.",
         summary="A numerical all-joint check over a four-vertex two-state set, with its raw records and reproduction details in the linked report."),
    dict(route="app02-box-8ff979de60ea9d22", image="polygons.svg", page="index.html",
         family="Box approximation", title="Box outer approximation",
         alt="Planar reachable-set polygons and their box approximation."),
    dict(route="app03-zonotope-4522855018fa9b0b", image="zonotope-2d.svg", page="example-2d.html",
         family="Zonotopes", title="A planar zonotope", alt="A planar zonotope and its generator geometry."),
    dict(route="app04-ellipsoid-fd302c34092f8b19", image="ellipsoid-2d.svg", page="example-2d.html",
         family="Ellipsoidal approximation", title="A planar ellipsoid", alt="A planar ellipsoidal approximation."),
    dict(route="exp04-replay-93fe3b87795e1d3a", image="trajectory.svg", page="index.html",
         family="Sampled replay", title="Replay a sampled trajectory",
         alt="Saved sampled nonlinear replay trajectory."),
    dict(route="ext05-discretization-a40ba9647cc023dc", image="trajectory-2d.svg", page="example-2d.html",
         family="Discretization", title="A two-dimensional discretized model",
         alt="Saved two-dimensional discretization example."),
    dict(route="ext07-hybrid-51d9ee2e89d240eb", image="joint-relation-2d.svg", page="example-2d.html",
         family="Hybrid reachability", title="A hybrid joint relation",
         alt="Saved two-dimensional hybrid joint-relation example."),
    dict(route="geo08-lazy-6dbdd6b2f9235837", image="lazy-2d.svg", page="example-2d.html",
         family="Lazy geometry", title="Evaluate a lazy planar set",
         alt="Planar set expression shown before and after materialization."),
    dict(route="opt10-smooth-188130d94d7bf2de", image="feasible-box-2d.svg", page="example-2d.html",
         family="Smooth convex optimization", title="Feasible directions in a box",
         alt="A planar feasible box, objective direction, and selected point."),
    dict(source_report_id="syn04-strategy-b-ts03-20261022-2c0c9210", image="control-projection.svg",
         page="index.html", family="Strategy B control synthesis",
         title="Strategy B on the T-S03 control projection",
         alt="Saved T-S03 control projection from Strategy B.",
         summary="T-S03 has a one-dimensional state, two stages and one scalar control per stage. The plotted axes are u₀ and u₁, showing a projection of the complete optimal relation. The report records exact-profile completeness with numerical assurance; it does not establish generic Strategy B completeness."),
    dict(route="lotka-volterra-sampled-20261023", image="geometry.svg", page="index.html",
         family="Lotka–Volterra reachability samples", title="A sampled Lotka–Volterra orbit",
         alt="Seeded two-state Lotka–Volterra control samples trace an orbit; local panels show sample hulls.",
         summary="512 deterministic control histories illustrate the discrete recurrence. Dots and sample hulls do not certify the full reachable sets or reproduce the historical figure."),
    dict(route="syn03-nominal-exact-2d-8b94095", image="optimal-face.svg", page="index.html",
         family="Strategy A · nominal linear exact profile", title="A complete 2D optimal face",
         alt="The feasible upper triangle in the unit square and its full optimal diagonal segment from (0,1) to (1,0).",
         summary="The installed Strategy A example returned objective 1 and a registry-verified complete face x+y=1, 0<=x,y<=1. The page retains inputs, raw result and the numerical assurance limits."),
    dict(source_report_id="b06-owner-confirmed-7df01ba3af5e4c46", image="terminal-projections.svg",
         page="index.html", family="Fuel minimax reference", title="B06 fuel terminal set: two projections",
         alt="Numerical projections of the four-state terminal reachable set onto flow and stock-balance coordinates; the stock target is outside the projected set.",
         summary="The figure uses all 1,024 disturbance-corner histories for the unique winning fixed plan. The owner-confirmed disturbance box is not printed in L09, so this is a distinct reference case rather than a historical reproduction."),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_examples(catalog):
    """Validate source bundles using their existing publishers before reading data."""
    catalog = Path(catalog)
    entries = json.loads(catalog.read_text(encoding="utf-8"))["reports"]
    selected = {}
    # Pin the educational snapshots, so a later report of the same kind does
    # not silently change an example or make catalogue selection ambiguous.
    for kind, source_id, adapter in (("geo06-quickhull", "geo06-b010fb3df212604b", hull_reports),
                                     ("geo04-intersection", "geo04-20261012T224946Z-c37852bcc80d", intersection_reports)):
        matches = [entry for entry in entries
                   if entry["report_kind"] == kind and entry["source_report_id"] == source_id]
        require(len(matches) == 1, "gallery needs one reviewed " + kind + " report")
        entry = matches[0]
        for key in ("source_report_id", "report_id"):
            require(re.fullmatch(r"[A-Za-z0-9-]+", entry[key]) is not None, "unsafe report route")
        bundle = catalog.parent / entry["source_report_id"]
        publication = adapter.adapt(bundle)
        require(publication.report_id == entry["report_id"], "catalogue publication identity differs")
        records_path = report_data.local_file(bundle, "records.json")
        selected[kind] = (entry, json.loads(records_path.read_text(encoding="utf-8")), records_path)

    entry, record, records_path = selected["geo06-quickhull"]
    examples = []
    for name, title, domain in (("square_duplicates", "Find the convex hull", (-.25, 1.25)),
                                 ("collinear_endpoints", "When the hull is a line", (-.5, 3.5))):
        fixture = record["catalog"][name]
        rows = [row for row in record["rows"] if row["scenario"] == name]
        indices = [int(value) for value in rows[0]["indices"].split(":")]
        examples.append(dict(slug=name, title=title, points=fixture["points"], indices=indices,
                             vertices=[fixture["points"][i] for i in indices], domain=domain,
                             inputs={"points": fixture["points"]}, report_id=entry["report_id"],
                             records_path=records_path, source=record["source_commit"],
                             harness=record["harness_commit"], kind="hull"))

    entry, record, records_path = selected["geo04-intersection"]
    trial = next(row for row in record["trials"] if row["scenario"] == "crossing_octagon")
    vertices = trial["vertices_json"]
    # Separate literal geometric oracle; do not replace native floating outputs
    # by these ideal vertices in the plot, table or downloadable example record.
    expected = {(1,.5),(1,-.5),(-1,.5),(-1,-.5),(.5,1),(-.5,1),(.5,-1),(-.5,-1)}
    require(len(vertices) == 8 and {tuple(round(v, 7) for v in p) for p in vertices} == expected,
            "intersection differs from the eight literal vertices")
    examples.append(dict(slug="crossing_octagon", title="Intersect two sets", vertices=vertices,
                         points=vertices, indices=list(range(8)), domain=(-1.8, 1.8),
                         inputs=record["expected"]["crossing_octagon"]["inputs"],
                         report_id=entry["report_id"], records_path=records_path,
                         source=record["algorithm"]["source_commit"],
                         harness=record["algorithm"]["harness_commit"], kind="intersection"))

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


def plot(example):
    if example["kind"] == "two_parameter":
        def point(p):
            return (80 + p[0] * 400, 440 - p[1] * 400)

        def polygon(points, color, fill, dashed=False):
            coords = " ".join(f"{x:.6f},{y:.6f}" for x, y in map(point, points))
            dash = ' stroke-dasharray="8 6"' if dashed else ""
            return (f'<polygon points="{coords}" fill="{fill}" stroke="{color}" '
                    f'stroke-width="3"{dash}/>')

        elements = []
        for value in (0, 0.5, 1):
            x, y = point((value, value))
            elements += [f'<line x1="{x}" y1="40" x2="{x}" y2="440" stroke="#3c493d"/>',
                         f'<line x1="80" y1="{y}" x2="480" y2="{y}" stroke="#3c493d"/>',
                         f'<text x="{x}" y="470" text-anchor="middle">{value:g}</text>',
                         f'<text x="68" y="{y+5}" text-anchor="end">{value:g}</text>']
        full, half = example["polygons"][1], example["polygons"][0]
        elements += [polygon(full["feasible_polygon_in_control_coordinates"], "#d6af75", "#d6af7518", True),
                     polygon(half["feasible_polygon_in_control_coordinates"], "#b4cda3", "#b4cda333"),
                     '<text x="92" y="132">enter-half path</text>',
                     '<text x="335" y="388">enter-full only</text>',
                     '<text x="290" y="72" text-anchor="middle">objective = 0 everywhere</text>']
        description = ("The amber dashed triangle is the enter-full path. The green quadrilateral is the "
                       "enter-half path and lies within it. Every point on both labelled paths is optimal "
                       "for the constant zero objective.")
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 510" role="img" '
                'aria-labelledby="title desc"><title id="title">' + escape(example["title"]) + '</title>'
                '<desc id="desc">' + description + '</desc><rect width="580" height="510" fill="#172019"/>'
                '<g font-family="monospace" font-size="14" fill="#d1d9cc">' + "".join(elements) +
                '<text x="285" y="502" text-anchor="middle">u₀ (first free control)</text>'
                '<text x="18" y="245" transform="rotate(-90 18 245)" text-anchor="middle">u₁ (second free control)</text>'
                '</g></svg>')
    low, high = example["domain"]

    def point(p):
        return (80 + (p[0]-low)*400/(high-low), 440 - (p[1]-low)*400/(high-low))

    def coordinates(points):
        return " ".join(f"{x:.6f},{y:.6f}" for x, y in map(point, points))

    def boundary(points, color, fill="none", dashed=False):
        tag = "polygon" if len(points) > 2 else "polyline"
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        return (f'<{tag} points="{coordinates(points)}" fill="{fill}" '
                f'stroke="{color}" stroke-width="2.5"{dash}/>')

    elements = []
    for value in sorted({low, 0, high}):
        x, y = point((value, value))
        elements += [f'<line x1="{x}" y1="40" x2="{x}" y2="440" stroke="#3c493d"/>',
                     f'<line x1="80" y1="{y}" x2="480" y2="{y}" stroke="#3c493d"/>',
                     f'<text x="{x}" y="470" text-anchor="middle">{value:g}</text>',
                     f'<text x="68" y="{y+5}" text-anchor="end">{value:g}</text>']
    if example["kind"] == "intersection":
        elements.append(boundary([[-1,-1],[1,-1],[1,1],[-1,1]], "#91a9c7", dashed=True))
        elements.append(boundary([[-1.5,0],[0,-1.5],[1.5,0],[0,1.5]], "#d6af75", dashed=True))
        vertices = sorted(example["vertices"], key=lambda p: math.atan2(p[1], p[0]))
    else:
        vertices = example["vertices"]
    elements.append(boundary(vertices, "#b4cda3", "#b4cda31c" if len(vertices) > 2 else "none"))
    if example["kind"] in {"hybrid", "projected_reachability"}:
        labels = (("unique minimum", "feasible endpoint") if example["kind"] == "hybrid"
                  else ("projected endpoint", "projected endpoint"))
        colors = (("#d6af75", "#b4cda3") if example["kind"] == "hybrid"
                  else ("#b4cda3", "#b4cda3"))
        for index, (p, label, color) in enumerate(zip(example["points"],
                labels, colors)):
            x, y = point(p)
            elements.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>')
            elements.append(f'<text x="{x+9}" y="{y-10}">{label}</text>')
    else:
        groups = {}
        for index, p in enumerate(example["points"]):
            groups.setdefault(tuple(p), []).append(index)
        for p, ids in groups.items():
            x, y = point(p)
            retained = any(index in example["indices"] for index in ids)
            color = "#b4cda3" if retained else "#d6af75"
            label = "/".join(str(index) for index in ids)
            elements.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
            elements.append(f'<text x="{x+9}" y="{y-10}">{label}</text>')
    description = ("Original point IDs label each location; slash-separated IDs coincide. Green points are hull vertices."
                   if example["kind"] == "hull" else
                   "Blue dashed square and amber dashed diamond overlap in the green eight-vertex intersection. Labels are saved output row IDs."
                   if example["kind"] == "intersection" else
                   "The green segment is the projected terminal state set x1 in [0, 0.5]; the axes show the feasible control and terminal-state relation."
                   if example["kind"] == "projected_reachability" else
                   "The feasible two-stage relation is the green segment x2 equals u0 from zero to one half; the gold point is its unique minimum.")
    x_label, y_label = (("u₀ (free control)", "x₂ (terminal state)") if example["kind"] == "hybrid"
                        else ("u₀ (free control)", "x₁ (terminal state)") if example["kind"] == "projected_reachability"
                        else ("x (dimensionless)", "y (dimensionless)"))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 510" role="img" '
            'aria-labelledby="title desc"><title id="title">' + escape(example["title"]) + '</title>'
            '<desc id="desc">' + description + '</desc><rect width="580" height="510" fill="#172019"/>'
            '<g font-family="monospace" font-size="14" fill="#d1d9cc">' + "".join(elements) +
            '<text x="285" y="502" text-anchor="middle">' + escape(x_label) + '</text>'
            '<text x="18" y="245" transform="rotate(-90 18 245)" text-anchor="middle">' + escape(y_label) + '</text>'
            '</g></svg>')


def point_table(example):
    rows = []
    seen = {}
    for index, p in enumerate(example["points"]):
        if example["kind"] in {"hybrid", "projected_reachability"}:
            role = ("unique minimum" if index == 0 else "feasible interval endpoint") \
                if example["kind"] == "hybrid" else "projected terminal endpoint"
        elif example["kind"] == "two_parameter":
            role = "feasible polygon vertex; shared vertices preserve separate path labels"
        elif example["kind"] == "intersection":
            role = "intersection vertex"
        elif tuple(p) in seen:
            role = "duplicate of point " + str(seen[tuple(p)])
        else:
            role = "hull vertex" if index in example["indices"] else "interior / omitted"
        seen.setdefault(tuple(p), index)
        rows.append(f'<tr><td>{index}</td><td>{p[0]:.6g}</td><td>{p[1]:.6g}</td><td>{role}</td></tr>')
    heading = ("Original point ID" if example["kind"] == "hull" else
               "Fixture point" if example["kind"] == "hybrid" else
               "Projected endpoint" if example["kind"] == "projected_reachability" else
               "Polygon vertex" if example["kind"] == "two_parameter" else "Saved output row ID")
    caption = ("Exact illustrative values; the continuous feasible set is the full segment."
               if example["kind"] == "hybrid" else
               "Exact endpoints of the projected terminal interval; the plotted relation is the complete line segment."
               if example["kind"] == "projected_reachability" else
               "Exact polygon vertices; identical locations belong to separately labelled path branches."
               if example["kind"] == "two_parameter" else
               "Coordinates (rounded to six significant digits; raw JSON retains binary64 values)")
    x_label, y_label = (("u₀", "x₂") if example["kind"] == "hybrid" else
                        ("u₀", "x₁") if example["kind"] == "projected_reachability" else
                        ("u₀", "u₁") if example["kind"] == "two_parameter" else ("x", "y"))
    return ('<div class="scroll" tabindex="0" role="region" aria-label="Point coordinates"><table>'
            f'<caption>{caption}</caption>'
            f'<thead><tr><th scope="col">{heading}</th><th scope="col">{x_label}</th><th scope="col">{y_label}</th>'
            '<th scope="col">Role</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def section(example, number):
    if example["kind"] == "hull":
        explanation = ("Stretch a rubber band around these points. The band touches only the extreme vertices; "
                       "the center point does not change the hull. Coincident input rows share one location.")
        if example["slug"] == "collinear_endpoints":
            explanation = ("All points lie on y = x. The convex hull is the segment from (0, 0) to (3, 3), "
                           "so only its two endpoints are retained. Intermediate collinear points are omitted.")
        result = "Returned original vertex IDs: " + json.dumps(example["indices"]) + "."
        notes = ("The first input ID wins for coincident points. Polygon vertices start at the lexicographically "
                 "smallest point and continue counterclockwise, without repeating the closing vertex. "
                 "QuickHull uses exact orientation for the supplied binary64 coordinates; these small cases do not establish general performance.")
        option, target = "GEO06", "csl_geo06_quickhull_report"
        flags = " -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF"
        driver = "benchmarks/reporting/geo06/quickhull_driver.cpp"
        extra = ('<details><summary>Minimal public C++ call</summary><pre><code>' + escape(
            '#include <csl/geometry/quickhull_2d.hpp>\n#include <iostream>\n#include <vector>\n\n'
            'int main() {\n    const std::vector<csl::Vector> points = ' +
            json.dumps(example["points"]).replace("[", "{").replace("]", "}") + ';\n'
            '    auto result = csl::geometry::quickhull_2d(points);\n'
            '    const auto* hull = std::get_if<csl::geometry::QuickHull2D>(&result);\n'
            '    if (!hull) return 1;\n'
            '    for (auto id : hull->vertex_indices) std::cout << id << " ";\n}\n'
            '// Link the installed target CSL::quickhull_2d (C++20).\n') + '</code></pre></details>')
    elif example["kind"] == "intersection":
        explanation = ("Keep points that satisfy both shapes: the square −1 ≤ x,y ≤ 1 and the diamond "
                       "|x| + |y| ≤ 1.5. Each shape cuts off four corners of the other. The shared region is an octagon.")
        result = "Expected vertices: (±1, ±0.5) and (±0.5, ±1), all sign combinations."
        notes = ("The plot uses the saved native vertex coordinates, not idealized oracle replacements. "
                 "Qhull/HiGHS outputs match this fixture within absolute tolerance 1e−7; they are numerical geometry, "
                 "not a validated exact enclosure. Vertex row order is not a promised cyclic boundary order.")
        option, target = "GEO04", "csl_geo04_intersection_report"
        # This frozen harness predates optional-adapter flags and the later
        # move to benchmarks/reporting. Reproduce its actual historical tree.
        flags = ""
        driver = "reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp"
        extra = "<p>The complete inputs below use A·[x,y] ≤ b for each shape. The driver links CSL::polyhedral, CSL::qhull_conversion and CSL::highs_lp.</p>"
    elif example["kind"] == "two_parameter":
        explanation = ("The enter-half transition constrains the first pre-reset state to [0,0.5], while "
                       "enter-full has a universal guard. Both labelled paths then share the terminal bound "
                       "u₀+u₁≤1. The green quadrilateral lies inside the amber dashed triangle; their overlap "
                       "belongs to both mode paths.")
        result = ("Enter-half path: (0,0), (0.5,0), (0.5,0.5), (0,1). Enter-full path: "
                  "(0,0), (1,0), (0,1). The objective is identically zero, so every point in each complete "
                  "polygon is optimal and both labelled paths are retained.")
        notes = ("This exact rational construction illustrates the bounded two-free-control verifier profile. "
                 "It is an analytic illustration, not a saved solver run, timing result or measured fixture.")
        option, target = "", "hybrid_path_program_tests"
        flags = ""
        driver = "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ("<p>The downloadable input record includes both free controls, all mode flows, invariants, "
                 "transition guards and resets, terminal policy and both path polygons.</p>")
    elif example["kind"] == "projected_reachability":
        explanation = ("Start at x₀=0, flow with x_pre₁=x₀+u₀ for u₀∈[0,1], and take the fixed "
                       "transition only when its post-flow guard admits x_pre₁∈[0,0.5]. The identity "
                       "reset carries that state to x₁. Projecting the full labelled relation onto x₁ "
                       "gives the terminal interval shown.")
        result = ("Projected terminal set: x₁∈[0,0.5]. The plotted full relation is "
                  "(u₀,x₁)=(s,s), 0≤s≤0.5.")
        notes = ("This exact rational construction illustrates the bounded one-transition scalar "
                 "projected-state adapter profile. It is an analytic illustration, not a saved solver "
                 "run or a timing result; the independent contract test checks the joint relation and "
                 "terminal-set bounds.")
        option, target = "", "hybrid_path_program_tests"
        flags = ""
        driver = "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ("<p>The adapter retains the path-labelled joint H relation and returns its terminal H "
                 "projection. The request objective is present for contract completeness but does not "
                 "affect reachability.</p>")
    else:
        explanation = ("Two scalar stages follow the fixed path start → middle → terminal. The first control is "
                       "free in [0,1] and the second is fixed at zero. The second transition requires its "
                       "pre-reset state x_pre[1] in [0,0.5], then its identity reset sets x[2]=x_pre[1].")
        result = ("Complete feasible family: (u₀, x₂) = (s, s), 0 ≤ s ≤ 0.5. "
                  "The unique minimum of x₂ is (u₀, x₂) = (0, 0).")
        notes = ("This is an exact rational illustration of a supported input, not a saved solver run or a timing "
                 "result. The independent test oracle derives the interval and checks both endpoints and an outside point.")
        option, target = "", "hybrid_path_program_tests"
        flags = ""
        driver = "tests/unit/synthesis/hybrid_path_program_tests.cpp"
        extra = ('<p>The fixture record contains all mode, flow, control, invariant, transition, guard, reset and objective inputs.</p>')
    command = ("cmake --preset dev\n"
               f"cmake --build --preset dev --target {target}\n"
               f"ctest --preset dev -R '^{target}$'") if example["kind"] in {"hybrid", "two_parameter", "projected_reachability"} else (
        f'cmake -S . -B build/visual-{option.lower()} -DCMAKE_BUILD_TYPE=Release '
        f'-DBUILD_TESTING=OFF -DCSL_BUILD_{option}_REPORT=ON{flags}\n'
        f'cmake --build build/visual-{option.lower()} --config Release --target {target} --parallel 2\n'
        f'./build/visual-{option.lower()}/{target} --smoke')
    source_url = "https://github.com/butahlecoq/controlled-systems-lab/blob/" + example["harness"] + "/" + driver
    caption = ("Green: hull boundary; amber: omitted points. Slash-separated original IDs coincide. Equal x/y scale."
               if example["kind"] == "hull" else
               "Green: returned intersection. Blue: input square; amber: input diamond. Labels are saved output row IDs. Equal x/y scale."
               if example["kind"] == "intersection" else
               "Amber dashed: enter-full path. Green: enter-half path. The green polygon is contained in the triangle; both retain all optimal points."
               if example["kind"] == "two_parameter" else
                "Green: full feasible control/terminal-state relation. Its terminal-state projection is the interval [0,0.5]."
                if example["kind"] == "projected_reachability" else
               "Green: complete feasible relation. Gold: unique minimizer. Both axes show the same scalar system in control and terminal-state coordinates.")
    example_type = ("2D two-control family" if example["kind"] == "two_parameter" else
                    "2D projected reachability" if example["kind"] == "projected_reachability" else
                    "2D control family" if example["kind"] == "hybrid" else "2D geometry")
    reproduction = ('<p>From the repository checkout at the linked fixture commit, configure the development preset and run:</p>'
                    if example["kind"] in {"hybrid", "two_parameter", "projected_reachability"} else
                    f'<p>From a checkout of harness commit <code>{example["harness"]}</code>, using CMake 3.31+ and a C++20 compiler:</p>')
    platform_note = ("This runs the functional two-stage oracle test; it creates no timing evidence."
                     if example["kind"] == "hybrid" else
                     "This runs the functional two-parameter polygon oracle test; it creates no timing evidence."
                     if example["kind"] == "two_parameter" else
                      "This runs the functional projected-state reachability test; it creates no timing evidence."
                      if example["kind"] == "projected_reachability" else
                     'For Visual Studio, use its developer shell, configure with its generator, and run '
                     '<code>Release/' + target + '.exe --smoke</code> in the build directory. '
                     'This is a functional smoke, not a new benchmark; discard smoke timing values.')
    report_links = (f'<p>Related one-step report: <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                    f'<a href="../{example["report_id"]}/records.json">one-step raw record ↗</a>. '
                    'This two-stage illustration is not part of that measured fixture.</p>'
                    if example["kind"] == "hybrid" else
                    f'<p>Related two-control report: <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                    f'<a href="../{example["report_id"]}/records.json">two-control raw record ↗</a>. '
                    'The measured report uses rectangular parameter sets and minimizes x_terminal=u0; '
                    'this illustration has a coupled triangular/quadrilateral feasible set and a '
                    'constant-zero objective.</p>'
                    if example["kind"] == "two_parameter" else
                     f'<p>Related one-step verification report (a separate algorithm): <a href="../{example["report_id"]}/index.html">saved numerical evidence ↗</a> · '
                     f'<a href="../{example["report_id"]}/records.json">one-step raw record ↗</a>.</p>'
                     if example["kind"] == "projected_reachability" else
                    f'<p><a href="../{example["report_id"]}/index.html">Reviewed numerical report ↗</a> · '
                    f'<a href="../{example["report_id"]}/records.json">Full saved native records ↗</a></p>')
    raw_record_link = ('<p><a href="two_stage_scalar_family.json">Two-stage fixture and analytic raw record ↗</a></p>'
                       if example["kind"] == "hybrid" else "")
    if example["kind"] == "two_parameter":
        raw_record_link = '<p><a href="two_parameter_scalar_polytopes.json">Two-control fixture and analytic raw record ↗</a></p>'
    if example["kind"] == "projected_reachability":
        raw_record_link = '<p><a href="projected_hybrid_reachability.json">Projected reachability fixture and analytic raw record ↗</a></p>'
    source_provenance = (f'<p class="provenance">Algorithm source <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{example["source"]}"><code>{example["source"]}</code></a></p>'
                         if example["kind"] in {"hybrid", "two_parameter", "projected_reachability"} else
                         f'<p class="provenance">Algorithm source <code>{example["source"]}</code></p>')
    return (f'<section id="{example["slug"]}"><p class="eyebrow">Example {number:02d} / {example_type}</p>'
            f'<h2>{example["title"]}</h2><p>{explanation}</p>'
            f'<figure><img src="{example["slug"]}.svg" alt="{escape(explanation, quote=True)}">'
            f'<figcaption>{caption}</figcaption></figure>'
            f'<p class="answer">{result}</p>{point_table(example)}'
            '<details><summary>Complete minimal input</summary><pre><code>' + escape(json.dumps(example["inputs"], indent=2)) + '</code></pre></details>'
            + extra + '<details><summary>Reproduce the functional example</summary>' + reproduction +
            '<pre><code>' + escape(command) + '</code></pre>'
            '<p>' + platform_note + '</p>'
            f'<p><a href="{source_url}">Complete native fixture/driver ↗</a></p></details>'
            f'<p class="limits">{notes}</p>' + source_provenance +
            raw_record_link + report_links + '</section>')


def saved_figure_sections(catalog, site):
    entries = json.loads(Path(catalog).read_text(encoding="utf-8"))["reports"]
    by_source = {entry["source_report_id"]: entry for entry in entries if "source_report_id" in entry}
    cards = []
    inventory = []
    for number, entry in enumerate(SAVED_FIGURES, start=1):
        report_id = entry.get("route")
        if "source_report_id" in entry:
            published = by_source.get(entry["source_report_id"])
            require(published is not None, "missing catalogued visual report: " + entry["source_report_id"])
            report_id = published["report_id"]
        require(re.fullmatch(r"[A-Za-z0-9-]+", report_id or "") is not None, "unsafe visual report route")
        route = Path(site) / report_id
        image_path = route / entry["image"]
        require(not route.is_symlink() and image_path.is_file() and not image_path.is_symlink(),
                "missing staged visual figure: " + report_id + "/" + entry["image"])
        require((route / entry["page"]).is_file() and (route / "records.json").is_file(),
                "saved visual needs a report page and raw records: " + report_id)
        image = f"../{report_id}/{entry['image']}"
        page = f"../{report_id}/{entry['page']}"
        records = f"../{report_id}/records.json"
        cards.append(
            f'<article id="saved-figure-{number}" class="saved-figure"><p class="eyebrow">' + escape(entry["family"]) +
            '</p><h3><a href="' + escape(page, quote=True) + '">' + escape(entry["title"]) +
            '</a></h3><a href="' + escape(page, quote=True) + '"><img src="' +
            escape(image, quote=True) + '" alt="' + escape(entry["alt"], quote=True) +
            '"></a><p>' + escape(entry.get("summary", "Figure from the immutable saved report; no solver was rerun for this gallery.")) + '</p>'
            '<p><a href="' + escape(page, quote=True) + '">Inputs, answer and reproduction details ↗</a> · '
            '<a href="' + escape(records, quote=True) + '">Raw record ↗</a></p></article>')
        inventory.append({"family": entry["family"], "title": entry["title"], "report_id": report_id,
                          "figure": entry["image"], "page": entry["page"], "records": "records.json"})
    return ''.join(cards), inventory


def validate_gallery_inventory(out, entries):
    page = (out / "index.html").read_text(encoding="utf-8")
    site_root = out.parent.resolve()
    require(page.count('id="saved-report-figures"') == 1,
            "saved report figures need one gallery section")
    anchors = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', page))
    require(len(anchors) == len(re.findall(r'\bid="', page)), "duplicate/unsafe gallery anchor")
    require(len({entry["anchor"] for entry in entries}) == len(entries),
            "visual inventory anchors must be unique")
    rendered = set(re.findall(r'<section id="([A-Za-z0-9_-]+)"', page)) - {
        "saved-report-figures", "analytic-illustrations", "algorithm-coverage"}
    rendered.update(re.findall(r'<article id="(saved-figure-[0-9]+)"', page))
    rendered.update(re.findall(r'<article class="saved-figure" id="(visual-[A-Za-z0-9_-]+)"', page))
    listed = {entry["anchor"] for entry in entries}
    require(rendered == listed, "every rendered gallery example must appear in the visual inventory")
    for entry in entries:
        required = ("family", "title", "status", "anchor", "page", "figure", "source_page", "raw_record")
        require(all(isinstance(entry.get(field), str) and entry[field] for field in required),
                "visual inventory entry is missing required metadata or provenance")
        require(entry["status"] in {"educational-example", "saved-report-figure", "analytic-illustration"},
                "unknown visual inventory status")
        require(entry["anchor"] in anchors, "visual inventory target is missing from gallery")
        page_ref, _, page_anchor = entry["page"].partition("#")
        page_target = (out / page_ref).resolve()
        require(page_target.is_relative_to(site_root) and page_target.is_file() and
                (not page_anchor or page_anchor in anchors),
                "visual inventory page or anchor is missing or escaping")
        raw_path = (out / entry["raw_record"]).resolve()
        require(raw_path.is_relative_to(site_root) and raw_path.is_file(),
                "visual inventory raw record is missing or escaping")
        try:
            raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("visual inventory raw record must be readable JSON") from None
        require(isinstance(raw_data, dict), "visual inventory raw record must be a JSON object")
        if entry["status"] == "analytic-illustration":
            require(all(field in raw_data for field in
                        ("inputs", "answer", "reproduction_command", "evidence")) and
                    ("related_saved_report" in raw_data or "source_path" in raw_data),
                    "analytic visual record needs inputs, answer, reproduction and source provenance")
        for field in ("figure", "source_page", "raw_record", "report_records"):
            if field not in entry:
                continue
            if field == "source_page" and urlsplit(entry[field]).scheme:
                continue
            target = (out / entry[field]).resolve()
            require(target.is_relative_to(site_root) and target.is_file(),
                    "visual inventory links to a missing or escaping file: " + field)


def algorithm_coverage(catalog, site, gallery_inventory):
    source = Path(__file__).with_name("algorithm_visual_coverage.json")
    result = json.loads(source.read_text(encoding="utf-8"))
    require(result.get("schema") == "csl.algorithm-visual-coverage/1",
            "unsupported algorithm coverage schema")
    architecture = Path(__file__).parents[2] / result["source"]
    require(architecture.is_file(),
            "algorithm coverage architecture source is missing")
    architecture_text = architecture.read_text(encoding="utf-8")
    reports = json.loads(Path(catalog).read_text(encoding="utf-8"))["reports"]
    require(Path(catalog).resolve() == Path(__file__).parents[2] / result["catalog_source"],
            "algorithm coverage was built from an unexpected report catalog")
    kinds = {entry["report_kind"] for entry in reports}
    mapped_kinds = {kind for family in result["families"] for kind in family["catalog_kinds"]}
    require(kinds <= mapped_kinds, "algorithm coverage omits catalog report kinds: " +
            ", ".join(sorted(kinds - mapped_kinds)))
    require(all(kind in kinds for family in result["families"] for kind in family["catalog_kinds"]),
            "algorithm coverage refers to an unknown catalog report kind")
    for report in reports:
        route = Path(site) / report["report_id"]
        require((route / "index.html").is_file() and (route / "records.json").is_file(),
                "algorithm coverage catalog report is not staged: " + report["report_id"])
    gallery = {entry["anchor"]: entry for entry in gallery_inventory}
    for family in result["families"]:
        require(all(module in architecture_text for module in family["modules"]),
                "algorithm family module is absent from its architecture source: " + family["id"])
        require(family["implementation_issues"],
                "algorithm family needs a linked implementation issue: " + family["id"])
        require(family["support"].startswith("supported-") or family["limit"],
                "unsupported 2D family needs a support limit: " + family["id"])
        require(not family["support"].startswith("supported-") or family["examples"],
                "supported 2D family needs a gallery example: " + family["id"])
        for example in family["examples"]:
            require(example in gallery, "algorithm coverage points to a missing gallery example: " + example)
        family["gallery_examples"] = [gallery[name] for name in family["examples"]]
        family["catalog_reports"] = [
            {"report_kind": entry["report_kind"], "report_id": entry["report_id"],
             "page": "../" + entry["report_id"] + "/index.html",
             "raw_record": "../" + entry["report_id"] + "/records.json"}
            for entry in reports if entry["report_kind"] in family["catalog_kinds"]]
        for route in family["report_routes"]:
            target = Path(site) / route
            require((target / "index.html").is_file() and (target / "records.json").is_file(),
                    "algorithm coverage report route is not staged: " + route)
        family["additional_reports"] = [
            {"report_id": route, "page": "../" + route + "/index.html",
             "raw_record": "../" + route + "/records.json"}
            for route in family["report_routes"]]
        family["implementation_issues"] = [
            {"number": number,
             "url": f"https://github.com/butahlecoq/controlled-systems-lab/issues/{number}"}
            for number in family["implementation_issues"]]
    return result


def coverage_html(coverage):
    rows = []
    for family in coverage["families"]:
        examples = " · ".join(
            f'<a href="#{escape(entry["anchor"], quote=True)}">{escape(entry["title"])}</a>'
            for entry in family["gallery_examples"]) or "No 2D example currently published"
        issues = " · ".join(
            f'<a href="{escape(issue["url"], quote=True)}">Issue #{issue["number"]}</a>'
            for issue in family["implementation_issues"])
        reports = family["catalog_reports"] + family["additional_reports"]
        report_links = " · ".join(
            f'<a href="{escape(report["page"], quote=True)}">{escape(report["report_id"])}</a>'
            for report in reports)
        rows.append('<article class="coverage-row"><h3>' + escape(family["name"]) + '</h3>'
                    '<p class="eyebrow">' + escape(family["composition"]) + ' · ' +
                    escape(family["support"]) + '</p><p>' + escape(family["limit"]) +
                    '</p><p>Examples: ' + examples + '</p><p>Saved reports: ' +
                    (report_links or "No saved report") + '</p><p>Related work: ' + issues + '</p></article>')
    return ''.join(rows)


def build(catalog, site):
    examples = load_examples(catalog)
    site = Path(site).resolve(strict=True)
    saved_figures, saved_inventory = saved_figure_sections(catalog, site)
    last_topic_anchor = f"saved-figure-{len(SAVED_FIGURES)}"
    last_topic_title = SAVED_FIGURES[-1]["title"]
    analytic_files, analytic_inventory = visual_illustrations.build(Path(catalog))
    index = report_data.local_file(site, "index.html")
    original = index.read_text(encoding="utf-8")
    require(original.count("</body>") == 1 and len(re.findall(r"<body\b[^>]*>", original)) == 1,
            "staged report index has no unique body")
    # Validate every input/link before making any output visible. The publisher
    # already validated full report artifacts; never rewrite those artifacts here.
    for example in examples:
        route = site / example["report_id"]
        require(not route.is_symlink() and (route / "index.html").is_file(), "missing staged report route")
        report_data.local_file(route, "index.html")
        require(report_data.local_file(route, "records.json").read_bytes() == example["records_path"].read_bytes(),
                "staged records differ from reviewed source")
    out = site / "examples"
    require(not out.is_symlink(), "gallery output must not be a symlink")
    out.mkdir(exist_ok=True)
    outputs = {e["slug"] + ".svg": plot(e) for e in examples}
    outputs.update(analytic_files)
    gallery_inventory = []
    for example in examples:
        source_page = f"../{example['report_id']}/index.html"
        raw_record = f"../{example['report_id']}/records.json"
        family = {"hull": "Polytope hull construction", "intersection": "Polytope intersection",
                  "hybrid": "Hybrid control family", "two_parameter": "Hybrid control polytopes",
                  "projected_reachability": "Projected hybrid reachability"}[example["kind"]]
        gallery_inventory.append({"family": family, "title": example["title"],
                                  "status": "educational-example",
                                  "anchor": example["slug"], "page": "index.html#" + example["slug"],
                                  "figure": example["slug"] + ".svg", "source_page": source_page,
                                  "raw_record": raw_record})
    gallery_inventory.extend(analytic_inventory)
    for figure_index, entry in enumerate(saved_inventory):
        report_page = entry["page"]
        report_figure = entry["figure"]
        report_record = entry["records"]
        entry["anchor"] = f"saved-figure-{figure_index+1}"
        entry["page"] = "index.html#saved-report-figures"
        entry["figure"] = f"../{entry['report_id']}/{report_figure}"
        entry["source_page"] = f"../{entry['report_id']}/{report_page}"
        entry["raw_record"] = f"../{entry['report_id']}/{report_record}"
        entry["status"] = "saved-report-figure"
        gallery_inventory.append(entry)
    coverage_data = algorithm_coverage(catalog, site, gallery_inventory)
    navigation = "".join(f'<a href="#{e["slug"]}">{e["title"]}</a>' for e in examples)
    navigation += '<a href="#analytic-illustrations">Analytic geometry and optimization</a>'
    navigation += '<a href="#algorithm-coverage">Algorithm coverage map</a>'
    navigation += '<a href="#saved-report-figures">More saved algorithm figures</a>'
    body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Visual examples · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css"></head>'
            '<body><a class="skip" href="#main">Skip to examples</a><div class="shell"><aside>'
            '<a class="brand" href="../index.html">[ csl ]<br>Controlled Systems Lab</a>'
            '<p class="eyebrow">Learn by looking</p>'
            f'<a class="nav-shortcut" href="#{last_topic_anchor}">Jump to final example: {escape(last_topic_title)} ↓</a>'
            '<nav aria-label="Examples" tabindex="0">' + navigation +
            '<a href="../index.html">All numerical reports ↗</a></nav></aside><main id="main">'
            '<header><p class="eyebrow">Small inputs / visible answers</p><h1>Algorithms,<br><em>in two dimensions.</em></h1>'
            '<p>See what goes in, what comes out, and why. Explore hull vertices, set intersections, hybrid control families, and projected reachability.</p>'
            '<p class="limits">These educational pages show reviewed saved outputs or explicit analytic constructions; '
            'they are not new performance measurements. Each page states whether it replays saved output or illustrates a literal fixture.</p>'
            '<p><a href="minimal-inputs.json" download>Download inputs and displayed outputs (JSON)</a> · '
            '<a href="visual-coverage.json" download>Download current gallery inventory (JSON)</a> · '
            '<a href="algorithm-coverage.json" download>Download algorithm-family coverage (JSON)</a></p>'
            '<p class="limits">This inventory describes figures currently linked here; it does not imply that every implemented algorithm already has a 2D example. '
            'The full algorithm-coverage gap is tracked in <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/563">issue #563</a>.</p></header>'
            + "".join(section(e, i+1) for i, e in enumerate(examples)) +
            '<section id="analytic-illustrations"><p class="eyebrow">Hand-derived examples</p>'
            '<h2>Analytic geometry and optimization</h2><p>These exact low-dimensional examples explain the operations with literal inputs and answers. They are not solver traces or performance evidence.</p>'
            '<div class="saved-grid">' + visual_illustrations.cards(analytic_inventory) + '</div></section>' +
            '<section id="algorithm-coverage"><p class="eyebrow">Implementation map</p>'
            '<h2>Algorithm families and 2D limits</h2><p>This map follows the current framework composition document and published report catalog. '
            'It separates the nominal synthesis path from installed modules outside that path and records where this gallery has no supported 2D case.</p>'
            '<div class="coverage-grid">' + coverage_html(coverage_data) + '</div></section>' +
            '<section id="saved-report-figures"><p class="eyebrow">Reviewed report figures</p>'
            '<h2>More algorithms, from saved evidence</h2><p>These figures are published with their original reports. '
            'Open a report for its exact inputs, answers, reproduction commands, provenance and evidence limits.</p>'
            '<div class="saved-grid">' + saved_figures + '</div></section>' +
            '<footer>Controlled Systems Lab · Saved evidence, visible geometry.</footer></main></div>'
            '<script>document.querySelector(".nav-shortcut").addEventListener("click",event=>{'
            'const target=document.querySelector(event.currentTarget.hash);if(!target)return;'
            'event.preventDefault();history.pushState(null,"",event.currentTarget.hash);'
            'target.scrollIntoView({behavior:"instant",block:"start"});});</script></body></html>')
    outputs["index.html"] = body
    export = [{key: value for key, value in e.items() if key not in {"records_path", "domain"}} for e in examples]
    outputs["minimal-inputs.json"] = json.dumps({"schema": "csl.visual-examples/1", "examples": export}, indent=2) + "\n"
    outputs["visual-coverage.json"] = json.dumps(
        {"schema": "csl.visual-gallery-inventory/1", "entries": gallery_inventory}, indent=2) + "\n"
    outputs["algorithm-coverage.json"] = json.dumps(coverage_data, indent=2, ensure_ascii=False) + "\n"
    hybrid = next(example for example in examples if example["kind"] == "hybrid")
    outputs["two_stage_scalar_family.json"] = json.dumps({
        "schema": "csl.visual-example/ext07-two-stage-scalar/1",
        "illustration_only": True,
        "algorithm_source_commit": hybrid["source"],
        "oracle_harness_commit": hybrid["harness"],
        "inputs": hybrid["inputs"],
        "analytic": hybrid["analytic"],
    }, indent=2) + "\n"
    two_parameter = next(example for example in examples if example["kind"] == "two_parameter")
    outputs["two_parameter_scalar_polytopes.json"] = json.dumps({
        "schema": "csl.visual-example/ext07-two-parameter-scalar/1",
        "illustration_only": True,
        "algorithm_source_commit": two_parameter["source"],
        "oracle_harness_commit": two_parameter["harness"],
        "inputs": two_parameter["inputs"],
        "analytic": {"paths": two_parameter["polygons"], **two_parameter["analytic"]},
    }, indent=2) + "\n"
    projected = next(example for example in examples if example["kind"] == "projected_reachability")
    outputs["projected_hybrid_reachability.json"] = json.dumps({
        "schema": "csl.visual-example/ext07-projected-hybrid-reachability/1",
        "illustration_only": True,
        "algorithm_source_commit": projected["source"],
        "oracle_harness_commit": projected["harness"],
        "inputs": projected["inputs"],
        "analytic": projected["analytic"],
    }, indent=2) + "\n"
    for name, content in outputs.items():
        require(not (out / name).is_symlink(), "gallery file must not be a symlink")
        (out / name).write_text(content, encoding="utf-8")
    validate_gallery_inventory(out, gallery_inventory)
    require(not (out / "examples.css").is_symlink(), "gallery stylesheet must not be a symlink")
    shutil.copyfile(Path(__file__).with_name("visual_examples.css"), out / "examples.css")
    link = '<p id="visual-examples-link"><a href="examples/index.html">Visual examples: minimal 2D inputs, hull vertices and plots →</a></p>'
    if 'id="visual-examples-link"' not in original:
        index.write_text(re.sub(r"(<body\b[^>]*>)", lambda match: match[1] + link, original, count=1), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    build(args.catalog, args.site)


if __name__ == "__main__":
    main()

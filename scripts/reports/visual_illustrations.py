"""Small, hand-derived analytic geometry examples for the visual gallery."""
from html import escape
import json
from pathlib import Path


CASES = (
    {
        "id": "geo02-minkowski-triangles",
        "family": "Affine maps and Minkowski sums · GEO-02",
        "title": "Add two planar polytopes",
        "summary": "For A=conv{(0,0),(2,0),(0,1)} and B=conv{(0,0),(1,0),(0,1)}, the Minkowski sum A+B is the pentagon shown. This is a hand-derived exact illustration, separate from the saved GEO-02 measurement.",
        "figure": "geo02-minkowski.svg",
        "record": "geo02-minkowski.json",
        "kind": "analytic-illustration",
        "report_kind": "geo02-affine-sum",
        "inputs": {"A_vertices": [[0, 0], [2, 0], [0, 1]], "B_vertices": [[0, 0], [1, 0], [0, 1]], "operation": "A + B = {a+b | a in A, b in B}", "coordinates": "unitless Cartesian (x,y)"},
        "answer": {"vertices_ccw": [[0, 0], [3, 0], [2, 1], [0, 2]], "exact": True},
        "svg": "minkowski",
    },
    {
        "id": "geo03-hv-square",
        "family": "H/V conversion · GEO-03",
        "title": "Describe one square in two ways",
        "summary": "The four half-space inequalities and four corner vertices describe the same unit square. This analytic illustration shows the representation change; the linked report contains the independent saved GEO-03 checks.",
        "figure": "geo03-hv-square.svg",
        "record": "geo03-hv-square.json",
        "kind": "analytic-illustration",
        "report_kind": "geo03-hv",
        "inputs": {"H_inequalities": ["x >= 0", "x <= 1", "y >= 0", "y <= 1"], "coordinates": "unitless (x,y)"},
        "answer": {"V_vertices_ccw": [[0, 0], [1, 0], [1, 1], [0, 1]], "exact": True},
        "svg": "square",
    },
    {
        "id": "geo05-predecessor-boxes",
        "family": "Projection and predecessor · GEO-05",
        "title": "Project a two-state predecessor set",
        "summary": "For x⁺=x+u, X=[−2,2]², U=[−1,1]² and target S=[1,3]², the predecessor is X∩(S−U)=[0,2]². This exact box calculation is an analytic illustration, not a 2D solver result; the saved GEO-05 report is scalar.",
        "figure": "geo05-predecessor.svg",
        "record": "geo05-predecessor.json",
        "kind": "analytic-illustration",
        "report_kind": "geo05-projection-predecessor",
        "inputs": {"transition": "x_plus = x + u", "state_set_X": [[-2, 2], [-2, 2]], "control_set_U": [[-1, 1], [-1, 1]], "target_set_S": [[1, 3], [1, 3]], "coordinates": "unitless (x0,x1); one transition"},
        "answer": {"predecessor_X_intersect_S_minus_U": [[0, 2], [0, 2]], "exact": True},
        "svg": "predecessor",
    },
    {
        "id": "lp-triangle-objective",
        "family": "Linear programming · LP",
        "title": "Optimize a linear objective on a triangle",
        "summary": "On x≥0, y≥0, x+y≤1, minimizing −x−2y selects (0,1) with value −2. The contour lines show why the top vertex wins; this is a hand-derived analytic fixture.",
        "figure": "lp-triangle.svg",
        "record": "lp-triangle.json",
        "kind": "analytic-illustration",
        "report_kind": "lp",
        "inputs": {"constraints": ["x >= 0", "y >= 0", "x + y <= 1"], "objective": "minimize -x - 2y", "coordinates": "unitless (x,y)"},
        "answer": {"optimizer": [0, 1], "objective_value": -2, "exact": True},
        "svg": "lp",
    },
    {
        "id": "opt04-phase-one-simplex",
        "family": "Phase-I feasibility · OPT-04",
        "title": "Find a feasible point in a simplex",
        "summary": "In barycentric coordinates λ₀+λ₁+λ₂=1 with λᵢ≥0, imposing λ₁=λ₂=1/4 leaves λ=(1/2,1/4,1/4). The marked point is an exact analytic illustration of a feasible simplex slice, not a solver trace.",
        "figure": "opt04-phase-one.svg",
        "record": "opt04-phase-one.json",
        "kind": "analytic-illustration",
        "report_kind": "opt04-phase-one",
        "inputs": {"simplex": ["lambda0 >= 0", "lambda1 >= 0", "lambda2 >= 0", "lambda0 + lambda1 + lambda2 = 1"], "equalities": ["lambda1 = 1/4", "lambda2 = 1/4"], "coordinates": "dimensionless barycentric coordinates"},
        "answer": {"lambda": [0.5, 0.25, 0.25], "phase_one_violation": 0, "exact": True},
        "svg": "phase-one",
    },
    {
        "id": "mpc01-b04-reference-projection",
        "family": "Nominal open-loop optimization · MPC-01",
        "title": "Project a four-state fuel trajectory into two planes",
        "summary": "One exact optimal witness from the separate b04-reference-v1 case is projected onto oxidizer/fuel flow and working-stock planes. It is not a historical B04 reconstruction or an external-solver comparison.",
        "figure": "mpc01-b04-reference-projection.svg",
        "record": "mpc01-b04-reference-projection.json",
        "kind": "analytic-illustration",
        "source_path": "docs/research/evidence/b04-reference-v1/canonical-case.json",
        "source_commit": "23b0d912236386860ad036894af138bf9f78a9db",
        "source_files": ["docs/research/evidence/b04-reference-v1/canonical-case.json",
                         "docs/research/evidence/b04-reference-v1/exact-optimal-reference.json"],
        "source_file_labels": ["canonical case JSON", "exact witness JSON"],
        "source_label": "Pinned input and exact witness",
        "example_page": "b04-reference-trajectory-projections.html",
        "inputs": {"case": "b04-reference-v1", "state_dimension": 4, "horizon": 16,
                   "state_order": ["oxidizer_flow", "oxidizer_working_stock", "fuel_flow", "fuel_working_stock"],
                   "projections": [["oxidizer_flow", "fuel_flow"], ["oxidizer_working_stock", "fuel_working_stock"]],
                   "source_case": "docs/research/evidence/b04-reference-v1/canonical-case.json",
                   "source_witness": "docs/research/evidence/b04-reference-v1/exact-optimal-reference.json"},
        "answer": {"one_exact_optimal_witness": True, "checked_states": 17,
                   "checked_dynamics": "exact rational recurrence", "flow_constraints": "satisfied at stages 0 through 16",
                   "historical_reproduction": False, "external_solver_comparison": False},
        "reproduction_command": "python3 scripts/reports/mpc01/b04_projection_example.py",
        "evidence": "Exact saved b04-reference-v1 witness; renderer checks rational dynamics, control bounds and flow constraints.",
        "svg": "mpc01-b04-reference-projection",
    },
    {
        "id": "issue3-validated-minimax-2d",
        "family": "Validated finite-action minimax · issue #3",
        "title": "Separate a feasible action from a strict violation",
        "summary": "For x⁺=x+u+w from x₀=(0,0), the action u=(0,0) keeps all four disturbance corners inside the safe square and has worst terminal norm √(1/8). The action u=(1,0) has a strict stage-1 violation at x₁=(3/4,−1/4), with x≤1/2 residual 1/4. This is an exact analytic teaching fixture, not a replay of the API or benchmark.",
        "figure": "issue3-validated-minimax.svg",
        "record": "issue3-validated-minimax.json",
        "kind": "analytic-illustration",
        "report_kind": "issue3-validated-minimax",
        "source_commit": "a2c0736f43e4ff15d9a9323a51296e1b416d8809",
        "source_files": ["include/csl/optimization/validated_finite_action_minimax.hpp",
                         "src/optimization/validated_finite_action_minimax.cpp"],
        "inputs": {"system": "x1 = x0 + u0 + w0", "initial": [[0, 0]], "ordered_actions": [[0, 0], [1, 0]], "disturbance_vertices": [[-0.25, -0.25], [-0.25, 0.25], [0.25, -0.25], [0.25, 0.25]], "safe_set_each_stage": ["-1/2 <= x <= 1/2", "-1/2 <= y <= 1/2"], "objective": "maximize terminal ||x||₂", "coordinates": "state coordinates (x,y), one transition"},
        "answer": {"action_0": {"status": "proven feasible analytically", "worst_objective": "sqrt(1/8)"}, "action_1": {"status": "proven infeasible analytically", "witness": {"stage": 1, "disturbance_vertex": 0, "state": [0.75, -0.25], "constraint": "x <= 1/2", "residual": "1/4"}}, "exact": True},
        "svg": "validated-minimax",
    },
    {
        "id": "ext03-slew-memory",
        "family": "Temporal control constraints · EXT-03",
        "title": "Add a slew limit to a two-stage integrator",
        "summary": "For x[t+1]=x[t]+u[t], u₀,u₁∈[−1,1] and |u₁−u₀|≤1/4, the green hexagon is the complete feasible control relation. The exact minimum of x₂² is zero on the marked segment; this is an analytic illustration, not a Strategy A/B solver trace.",
        "figure": "ext03-slew-memory.svg",
        "record": "ext03-slew-memory.json",
        "kind": "analytic-illustration",
        "source_path": "examples/scenarios/temporal-slew-integrator.json",
        "inputs": {"scenario": "csl.scenario/2", "state_dimension": 1, "control_dimension": 1,
                   "horizon": 2, "dynamics": "x[t+1]=x[t]+u[t]", "initial_state": 0,
                   "absolute_controls": "u0,u1 in [-1,1]", "temporal_constraint": "|u1-u0|<=1/4",
                   "objective": "minimize x2^2", "coordinates": "(u0,u1)"},
        "answer": {"feasible_polygon_ccw": [[-1,-1],[-.75,-1],[1,.75],[1,1],[.75,1],[-1,-.75]],
                   "minimum_objective": 0, "complete_minimizer_segment": [[-.125,.125],[.125,-.125]],
                   "exact": True},
        "svg": "slew",
    },
)


def _xy(point, low, high):
    return 70 + (point[0] - low) * 330 / (high - low), 300 - (point[1] - low) * 250 / (high - low)


def _polygon(points, low, high, color, fill, opacity="0.3"):
    coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in (_xy(p, low, high) for p in points))
    return f'<polygon points="{coords}" fill="{fill}" fill-opacity="{opacity}" stroke="{color}" stroke-width="3"/>'


def _base(title, low, high, shapes, notes=(), xlabel="x", ylabel="y"):
    grid = []
    for value in range(low, high + 1):
        x, y = _xy((value, value), low, high)
        grid.append(f'<line x1="{x:.2f}" y1="35" x2="{x:.2f}" y2="300" stroke="#354337"/><line x1="70" y1="{y:.2f}" x2="400" y2="{y:.2f}" stroke="#354337"/>')
        grid.append(f'<text x="{x:.2f}" y="323" text-anchor="middle">{value}</text><text x="58" y="{y+4:.2f}" text-anchor="end">{value}</text>')
    note_svg = "".join(f'<text x="430" y="{85 + 34*i}" fill="#d1d9cc" font-size="13">{escape(note)}</text>' for i, note in enumerate(notes))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 590 360" role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(title)}</title><desc id="desc">Planar analytic geometry illustration.</desc>'
            '<rect width="590" height="360" fill="#172019"/>'
            '<g font-family="monospace" font-size="12" fill="#b9c4b4">' + "".join(grid) +
            '<line x1="70" y1="300" x2="405" y2="300" stroke="#91a88b"/><line x1="70" y1="305" x2="70" y2="35" stroke="#91a88b"/>' +
            "".join(shapes) + note_svg +
            f'<text x="235" y="348" text-anchor="middle">{escape(xlabel)}</text><text x="22" y="170" transform="rotate(-90 22 170)" text-anchor="middle">{escape(ylabel)}</text></g></svg>')


def svg(case):
    kind = case["svg"]
    if kind == "mpc01-b04-reference-projection":
        source = Path(__file__).parents[2] / "docs/examples/b04-reference-trajectory-projections.svg"
        return source.read_text(encoding="utf-8")
    if kind == "minkowski":
        shape = [_polygon([[0, 0], [3, 0], [2, 1], [0, 2]], -1, 4, "#b4cda3", "#7b9b70")]
        return _base("Minkowski sum A+B", -1, 4, shape, ("A+B", "vertices: (0,0)", "(3,0), (2,1)", "(0,2)"))
    if kind == "square":
        shape = [_polygon([[0, 0], [1, 0], [1, 1], [0, 1]], -1, 2, "#b4cda3", "#7b9b70")]
        return _base("H and V representations of the unit square", -1, 2, shape,
                     ("H: 0≤x≤1", "   0≤y≤1", "V: four corners", "same feasible set"))
    if kind == "predecessor":
        shapes = [_polygon([[-2, -2], [2, -2], [2, 2], [-2, 2]], -3, 4, "#93a08b", "#899989", "0.08"),
                  _polygon([[1, 1], [3, 1], [3, 3], [1, 3]], -3, 4, "#e79a78", "#e79a78", "0.25"),
                  _polygon([[0, 0], [2, 0], [2, 2], [0, 2]], -3, 4, "#b4cda3", "#7b9b70", "0.5")]
        return _base("Two-state predecessor", -3, 4, shapes, ("X: gray", "target S: orange", "Pre(X,S): green"))
    if kind == "lp":
        tri = _polygon([[0, 0], [1, 0], [0, 1]], -1, 2, "#b4cda3", "#7b9b70", "0.35")
        contour = '<line x1="140" y1="201" x2="360" y2="284" stroke="#e79a78" stroke-width="2"/><line x1="140" y1="159" x2="360" y2="242" stroke="#e79a78" stroke-width="2" opacity=".65"/>'
        px, py = _xy((0, 1), -1, 2)
        dot = f'<circle cx="{px:.2f}" cy="{py:.2f}" r="7" fill="#f0f7e9" stroke="#b4cda3" stroke-width="3"/>'
        return _base("Linear objective on a triangle", -1, 2, [tri, contour, dot], ("feasible triangle", "objective contours", "minimum at (0,1)", "value = −2"))
    if kind == "validated-minimax":
        safe = _polygon([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]],
                        -1, 2, "#b4cda3", "#7b9b70", "0.18")
        feasible = _polygon([[-0.25, -0.25], [0.25, -0.25], [0.25, 0.25], [-0.25, 0.25]],
                             -1, 2, "#b4cda3", "#7b9b70", "0.34")
        violating = _polygon([[0.75, -0.25], [1.25, -0.25], [1.25, 0.25], [0.75, 0.25]],
                             -1, 2, "#e79a78", "#e79a78", "0.28")
        return _base("Validated finite-action minimax in the state plane", -1, 2,
                     [safe, feasible, violating],
                     ("safe: ±1/2", "u=0: safe", "max=√(1/8)",
                      "u=(1,0): bad", "w₀=(-¼,-¼)", "gap=¼"))
    if kind == "slew":
        polygon = _polygon([[-1,-1],[-.75,-1],[1,.75],[1,1],[.75,1],[-1,-.75]],
                           -1, 1, "#b4cda3", "#7b9b70", "0.28")
        segment = '<line x1="214" y1="159" x2="256" y2="191" stroke="#e79a78" stroke-width="5"/><circle cx="214" cy="159" r="5" fill="#f0f7e9"/><circle cx="256" cy="191" r="5" fill="#f0f7e9"/>'
        return _base("Slew-limited two-stage integrator", -1, 1, [polygon, segment],
                     ("feasible controls", "|u₁−u₀| ≤ 1/4", "green: feasible set",
                      "gold: x₂=0, cost=0"), xlabel="u₀ (stage 0)", ylabel="u₁ (stage 1)")
    tri = _polygon([[0, 0], [1, 0], [0, 1]], -1, 2, "#b4cda3", "#7b9b70", "0.35")
    px, py = _xy((0.25, 0.25), -1, 2)
    dot = f'<circle cx="{px:.2f}" cy="{py:.2f}" r="7" fill="#f0f7e9" stroke="#b4cda3" stroke-width="3"/>'
    return _base("Phase-I feasible point in a simplex", -1, 2, [tri, dot],
                 ("λ₀+λ₁+λ₂=1", "λ₁=λ₂=1/4", "λ=(1/2,1/4,1/4)", "violation = 0"),
                 xlabel="λ₁", ylabel="λ₂")


def build(catalog):
    reports = json.loads(catalog.read_text(encoding="utf-8"))["reports"]
    output = {}
    rendered = []
    for case in CASES:
        svg_name = case["figure"]
        record_name = case["record"]
        report = next((r for r in reports if r["report_kind"] == case["report_kind"]), None) if "report_kind" in case else None
        if "report_kind" in case and report is None:
            raise ValueError("missing catalog report for analytic illustration: " + case["report_kind"])
        entry = {**{k: v for k, v in case.items() if k not in {"svg", "inputs", "answer"}},
                 "status": "analytic-illustration", "anchor": "visual-" + case["id"],
                 "page": "index.html#visual-" + case["id"], "figure": svg_name,
                 "raw_record": record_name,
                 "provenance": {"type": "complete-analytic-input-and-answer"}}
        if report:
            entry.update(report_id=report["report_id"], source_page="../" + report["report_id"] + "/index.html",
                         report_records="../" + report["report_id"] + "/records.json")
        else:
            source_commit = case.get("source_commit", "main")
            entry["source_page"] = "https://github.com/butahlecoq/controlled-systems-lab/blob/" + source_commit + "/" + case["source_path"]
        rendered.append(entry)
        output[svg_name] = svg(case)
        raw = {"schema": "csl.analytic-visual-example/1", "id": case["id"],
               "kind": case["kind"], "inputs": case["inputs"], "answer": case["answer"],
               "reproduction_command": case.get("reproduction_command", "python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site"),
               "evidence": case.get("evidence", "Hand-derived analytic illustration; not a replay or measurement.")}
        if report:
            raw["related_saved_report"] = {"report_kind": report["report_kind"],
                                            "report_id": report["report_id"],
                                            "page": "../" + report["report_id"] + "/index.html",
                                            "raw_record": "../" + report["report_id"] + "/records.json"}
        else:
            raw["source_path"] = case["source_path"]
            raw["source_page"] = entry["source_page"]
        if "source_commit" in case:
            raw["source_commit"] = case["source_commit"]
            raw["source_urls"] = ["https://github.com/butahlecoq/controlled-systems-lab/blob/" + case["source_commit"] + "/" + path
                                  for path in case["source_files"]]
        output[record_name] = json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
    return output, rendered


def cards(cases):
    rendered = []
    for case in cases:
        if "report_id" in case:
            source = (f'<a href="../{escape(case["report_id"], quote=True)}/index.html">'
                      f'Saved {escape(case["report_kind"])} report ↗</a> · '
                      f'<a href="../{escape(case["report_id"], quote=True)}/records.json">Raw report record ↗</a>')
        else:
            source = f'<a href="{escape(case["source_page"], quote=True)}">{escape(case.get("source_label", "Scenario source"))} ↗</a>'
        rendered.append(
            f'<article class="saved-figure" id="visual-{escape(case["id"], quote=True)}">'
            f'<p class="eyebrow">{escape(case["family"])}</p><h3>'
            + (f'<a href="{escape(case["example_page"], quote=True)}">' if "example_page" in case else "")
            + escape(case["title"])
            + ("</a>" if "example_page" in case else "") + "</h3>"
            + (f'<a href="{escape(case["example_page"], quote=True)}">' if "example_page" in case else "")
            + f'<img src="{escape(case["figure"], quote=True)}" alt="{escape(case["title"], quote=True)}">'
            + ("</a>" if "example_page" in case else "")
            + f'<p>{escape(case["summary"])}</p><p><a href="{escape(case["record"], quote=True)}">Exact analytic inputs and answer (JSON) ↗</a> · '
            + source + '</p>'
            + (f'<p>Pinned source files: <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{escape(case["source_commit"], quote=True)}/{escape(case["source_files"][0], quote=True)}">{escape(case.get("source_file_labels", ["public header", "implementation"])[0])}</a> · '
               f'<a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{escape(case["source_commit"], quote=True)}/{escape(case["source_files"][1], quote=True)}">{escape(case.get("source_file_labels", ["public header", "implementation"])[1])}</a></p>'
               if "source_commit" in case else "")
            + ('<p><a href="issue3-control-walkthrough.html">Open the saved-data end-to-end control walkthrough ↗</a></p>'
               if case["id"] == "issue3-validated-minimax-2d" else "")
            + '<p class="provenance">Reproduce gallery from the repository root after staging the reports:<br>'
            '<code>python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site</code></p></article>')
    return "".join(rendered)

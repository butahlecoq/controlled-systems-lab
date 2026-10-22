"""Small, hand-derived analytic geometry examples for the visual gallery."""
from html import escape
import json


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
        report = next((r for r in reports if r["report_kind"] == case["report_kind"]), None)
        if report is None:
            raise ValueError("missing catalog report for analytic illustration: " + case["report_kind"])
        rendered.append({**{k: v for k, v in case.items() if k not in {"svg", "inputs", "answer"}},
                         "report_id": report["report_id"], "status": "analytic-illustration",
                         "anchor": "visual-" + case["id"], "page": "index.html#visual-" + case["id"],
                         "figure": svg_name, "source_page": "../" + report["report_id"] + "/index.html",
                         "report_records": "../" + report["report_id"] + "/records.json",
                         "raw_record": record_name,
                         "provenance": {"type": "complete-analytic-input-and-answer"}})
        output[svg_name] = svg(case)
        output[record_name] = json.dumps({"schema": "csl.analytic-visual-example/1",
                                          "id": case["id"], "kind": case["kind"],
                                          "inputs": case["inputs"], "answer": case["answer"],
                                          "reproduction_command": "python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site",
                                          "related_saved_report": {"report_kind": report["report_kind"],
                                                                    "report_id": report["report_id"],
                                                                    "page": "../" + report["report_id"] + "/index.html",
                                                                    "raw_record": "../" + report["report_id"] + "/records.json"},
                                          "evidence": "Hand-derived analytic illustration; not a replay or measurement."},
                                         indent=2, ensure_ascii=False) + "\n"
    return output, rendered


def cards(cases):
    return "".join(
        f'<article class="saved-figure" id="visual-{escape(c["id"], quote=True)}">'
        f'<p class="eyebrow">{escape(c["family"])}</p><h3>{escape(c["title"])}</h3>'
        f'<img src="{escape(c["figure"], quote=True)}" alt="{escape(c["title"], quote=True)}">'
        f'<p>{escape(c["summary"])}</p><p><a href="{escape(c["record"], quote=True)}">Exact analytic inputs and answer (JSON) ↗</a> · '
        f'<a href="../{escape(c["report_id"], quote=True)}/index.html">Saved {escape(c["report_kind"])} report ↗</a> · '
        f'<a href="../{escape(c["report_id"], quote=True)}/records.json">Raw report record ↗</a></p>'
        '<p class="provenance">Reproduce gallery from the repository root after staging the reports:<br>'
        '<code>python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site</code></p></article>'
        for c in cases)

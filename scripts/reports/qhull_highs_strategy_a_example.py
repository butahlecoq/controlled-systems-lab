"""Render the saved Qhull and Strategy A example for the Pages gallery."""
from __future__ import annotations

import html
import hashlib
import json
from pathlib import Path

import site_design
from mathematical_notation import matrix_html

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "docs/examples/qhull-highs-strategy-a-2d-record.json"
PAGE_NAME = "qhull-highs-strategy-a-2d.html"
FIGURE_NAME = "qhull-highs-strategy-a-2d.svg"
RECORD_NAME = "qhull-highs-strategy-a-2d-record.json"
PLOT = {"left": 165, "right": 525, "top": 130, "bottom": 310}


def load_record() -> dict:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if record.get("schema") != "csl.qhull-highs-strategy-a-example/1":
        raise ValueError("unsupported Qhull and Strategy A example record")
    if record.get("problem", {}).get("state_dimension") != 2:
        raise ValueError("the example must describe a two-state system")
    if record.get("problem", {}).get("control_dimension") != 2:
        raise ValueError("the example must describe two control coordinates")
    if len(record.get("terminal_cases", [])) != 2:
        raise ValueError("the example must retain both terminal optimizer cases")
    renderer = record.get("illustration_source", {})
    renderer_path = renderer.get("source_path")
    if renderer_path != "scripts/reports/qhull_highs_strategy_a_example.py":
        raise ValueError("the illustration producer source path is missing or unexpected")
    renderer_source = ROOT / renderer_path
    if hashlib.sha256(renderer_source.read_bytes()).hexdigest() != renderer.get("source_sha256"):
        raise ValueError("the illustration producer source hash does not match this renderer")
    if renderer.get("commit") == record.get("source_commit"):
        raise ValueError("the numerical capture and illustration producer must be distinct")
    vertices = record["original_ordered_conversion_input"]["vertices"]
    matrix = record["post_fix_conversion"]["matrix_A"]
    bounds = record["post_fix_conversion"]["vector_b"]
    for point in vertices:
        if any(sum(coefficient * value for coefficient, value in zip(row, point)) > bound
               for row, bound in zip(matrix, bounds)):
            raise ValueError("a source vertex violates the saved post-fix H constraints")
    for case in record["terminal_cases"]:
        if case.get("control_role") != "checked feasible witness in returned joint relation; not extracted from optimizer":
            raise ValueError("the control role must remain a checked witness, not an optimizer result")
        state = case["terminal_state"]
        witness = case["checked_control_witness"]
        if state != witness:
            raise ValueError("the saved control witness differs from its identity-dynamics state")
        if case["id"] == "linear":
            value = -state[0]
        elif case["id"] == "quadratic":
            value = state[0] ** 2 + state[1] ** 2
        else:
            raise ValueError("unknown terminal objective case")
        if value != case["expected_objective"]:
            raise ValueError("the saved objective differs from direct arithmetic")
    old_small = abs(record["pre_fix_failure"]["conversion_matrix_A"][0][1])
    if not 0 < old_small <= record["pre_fix_failure"]["hiGHS_removal_threshold"]:
        raise ValueError("the preserved pre-fix coefficient is outside the refusal threshold")
    return record


def plot_point(point: list[float | int]) -> tuple[int, int]:
    """Map unit-square state coordinates to the SVG plot frame."""
    if len(point) != 2 or any(not 0 <= value <= 1 for value in point):
        raise ValueError("the plotted state must lie in the unit square")
    return (round(PLOT["left"] + (PLOT["right"] - PLOT["left"]) * point[0]),
            round(PLOT["bottom"] - (PLOT["bottom"] - PLOT["top"]) * point[1]))


def figure(record: dict) -> str:
    linear, quadratic = record["terminal_cases"]
    lp_x, lp_y = plot_point(linear["terminal_state"])
    qp_x, qp_y = plot_point(quadratic["terminal_state"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 470" role="img" aria-labelledby="title desc">
<title id="title">Unit-square H constraints and Strategy A terminal points</title>
<desc id="desc">Four unit-square vertices satisfy the returned Qhull constraints. The LP terminal point is one, zero. The QP terminal point is zero, zero, at the axes intersection. State and control coordinates agree because the initial state is zero and x one equals x zero plus u zero.</desc>
<rect width="760" height="470" fill="#172019"/>
<g stroke="#354337" stroke-width="1">
<path d="M105 370H585 M105 310H585 M105 250H585 M105 190H585 M105 130H585 M105 70H585"/>
<path d="M105 70V370 M165 70V370 M225 70V370 M285 70V370 M345 70V370 M405 70V370 M465 70V370 M525 70V370 M585 70V370"/>
</g>
<g stroke="#dce5d5" stroke-width="2"><path d="M105 310H610 M165 390V55"/></g>
<path d="M165 310L525 310L525 130L165 130Z" fill="#dce8f5" stroke="#32658f" stroke-width="4"/>
<g fill="#32658f"><circle cx="165" cy="310" r="6"/><circle cx="525" cy="310" r="6"/><circle cx="525" cy="130" r="6"/><circle cx="165" cy="130" r="6"/></g>
<circle cx="{lp_x}" cy="{lp_y}" r="10" fill="#bd6c22" stroke="#fff" stroke-width="3"/>
<circle cx="{qp_x}" cy="{qp_y}" r="8" fill="#7657a6" stroke="#fff" stroke-width="3"/>
<g font-family="system-ui,sans-serif" fill="#dce5d5">
<text x="165" y="338" text-anchor="middle" font-size="14">0</text><text x="525" y="338" text-anchor="middle" font-size="14">1</text>
<text x="150" y="315" text-anchor="end" font-size="14">0</text><text x="150" y="136" text-anchor="end" font-size="14">1</text>
<text x="245" y="428" font-size="17">x1.position</text><text x="23" y="223" font-size="17" transform="rotate(-90 23 223)">x1.velocity</text>
<text x="118" y="44" font-size="19">V hull / returned H region</text>
<text x="540" y="303" font-size="15" fill="#f0c674">LP (1,0)</text>
<text x="177" y="298" font-size="15" fill="#d2b9fa">QP (0,0)</text>
<text x="105" y="458" font-size="13" fill="#dce5d5">Original V order: (0,1), (1,1), (0,0), (1,0)</text>
</g>
</svg>'''


def page(record: dict) -> str:
    source = record["source_commit"]
    cases = record["terminal_cases"]
    reproduction = record["reproduction"]
    rendering = record.get("illustration_source", {})
    failure = record["pre_fix_failure"]
    failure_source = record["original_ordered_conversion_input"]["source_record"]
    linear, quadratic = cases
    vertices = record["original_ordered_conversion_input"]["vertices"]
    vertex_matrix = [[point[coordinate] for point in vertices] for coordinate in range(2)]
    dynamics = record["problem"]["dynamics"]
    conversion = record["post_fix_conversion"]
    initial_column = [[value] for value in record["problem"]["initial_state"]]
    bound_column = [[value] for value in conversion["vector_b"]]
    old_bound_column = [[value] for value in failure["conversion_vector_b"]]
    inputs = (
        '<div class="scroll" tabindex="0" role="region" aria-label="Input and returned mathematical matrices">'
        '<p><var>A</var> = ' + matrix_html(dynamics["A"], "State matrix A")
        + ' &nbsp; <var>B</var> = ' + matrix_html(dynamics["B"], "Control matrix B") + '</p>'
        + '<p>Initial state <var>x</var><sub>0</sub> = '
        + matrix_html(initial_column, "Initial state column vector") + '</p>'
        + '<p>Ordered V points as columns = ' + matrix_html(vertex_matrix, "Ordered V point matrix") + '</p>'
        + '<p>Returned H relation <var>A</var><sub>H</sub><var>x</var> ≤ <var>b</var>: '
        + matrix_html(conversion["matrix_A"], "Returned H matrix") + ' &nbsp; <var>b</var> = '
        + matrix_html(bound_column, "Returned H bound column vector") + '</p></div>')
    old_matrices = (
        '<div class="scroll" tabindex="0" role="region" aria-label="Preserved pre-fix matrix and vector"><p>Pre-fix H matrix = '
        + matrix_html(failure["conversion_matrix_A"], "Pre-fix H matrix") + ' &nbsp; <var>b</var> = '
        + matrix_html(old_bound_column, "Pre-fix H bound column vector") + '</p></div>')
    start = site_design.page_start(
        "Qhull and Strategy A on a 2D control problem", stylesheet_href="examples.css",
        crumbs=(("Learn", "../index.html"), ("Examples", "index.html"),
                ("Algorithm coverage", "index.html#algorithm-coverage"),
                ("Qhull and Strategy A", PAGE_NAME)),
        main_class="page-content walkthrough", current_href=PAGE_NAME)
    body = f'''<header><p class="eyebrow">Saved numerical example · Issue #974</p><h1>Qhull and Strategy A on a 2D control problem</h1>
<p>The original #944 diagnostic records the ordered square input and both HiGHS refusals. The direct Qhull regression replays those rows. A separate public Strategy A regression reconstructs the same one-step control problem and checks its source hull, bounded checker, Qhull, and both HiGHS terminal optimizer paths.</p></header>
<section><h2>Input and returned geometry</h2>
<p>The system has two state coordinates, two control coordinates, and one discrete transition. It uses <code>x₁ = Ax₀ + Bu₀</code>, <code>x₀=(0,0)</code>, and the identity matrices below. The stage-zero state factor is <code>[−1,1]²</code>, the control box is <code>[0,1]²</code>, and the next-state box is <code>[0,1]²</code>. The original diagnostic used the four ordered V columns below and no rays.</p>
{inputs}
<figure><img src="{FIGURE_NAME}" alt="The unit square and two labeled terminal states in position and velocity coordinates"><figcaption>The state plot shows the returned square region and terminal points. The control point has the same coordinates because the initial state is zero and the dynamics are <code>x₁=x₀+u₀</code>.</figcaption></figure>
<p>Each source vertex satisfies all four returned H inequalities. The row order does not affect the represented square.</p></section>
<section><h2>Terminal optimizer results and checked witnesses</h2><p>The optimizer selects a terminal state. The controls shown are checked feasible witnesses in the returned joint relation; they are not extracted from the optimizer.</p><div class="saved-grid" aria-label="Terminal objective results">
<article class="saved-figure"><h3>Linear objective</h3><p><strong>Objective:</strong> <code>{html.escape(linear["objective"])}</code></p><p><strong>Provider:</strong> <code>{html.escape(linear["optimizer"])}</code></p><p><strong>Terminal state:</strong> {matrix_html([[value] for value in linear["terminal_state"]], "LP terminal state column vector")}</p><p><strong>Checked feasible control witness:</strong> {matrix_html([[value] for value in linear["checked_control_witness"]], "LP checked feasible control witness column vector")}</p><p><strong>Objective value:</strong> <code>{linear["expected_objective"]}</code></p></article>
<article class="saved-figure"><h3>Quadratic objective</h3><p><strong>Objective:</strong> <code>{html.escape(quadratic["objective"])}</code></p><p><strong>Provider:</strong> <code>{html.escape(quadratic["optimizer"])}</code></p><p><strong>Terminal state:</strong> {matrix_html([[value] for value in quadratic["terminal_state"]], "QP terminal state column vector")}</p><p><strong>Checked feasible control witness:</strong> {matrix_html([[value] for value in quadratic["checked_control_witness"]], "QP checked feasible control witness column vector")}</p><p><strong>Objective value:</strong> <code>{quadratic["expected_objective"]}</code></p></article>
</div>
<p>For the LP, <code>−x₁.position=−1</code> at terminal state <code>(1,0)</code>. For the QP, the Hessian is {matrix_html(quadratic["quadratic_matrix"], "Quadratic objective Hessian")} with center <code>(0,0)</code>, so <code>x₁.position²+x₁.velocity²=0</code> at state <code>(0,0)</code>. The test checks each terminal state with its resolved objective and checks each six-coordinate history, using the listed control witness, against the returned candidate relation.</p></section>
<section><h2>What failed before the coordinate-frame fix</h2>
<p>The original rows produced two artificial coefficients of magnitude <code>1.1102230246251565e-16</code> after a full-rank SVD frame was projected back into world coordinates. The HiGHS LP and convex adapters preserve their declared <code>1e-12</code> removal threshold and refused the matrix.</p>
{old_matrices}<p>LP refusal: <code>{html.escape(failure['linear_refusal'])}</code><br>QP refusal: <code>{html.escape(failure['quadratic_refusal'])}</code></p>
<p>The preserved #944 diagnostic artifact has SHA-256 <code>{failure_source['diagnostic_artifact_sha256']}</code>. Its runner hash is <code>{failure_source['runner_sha256']}</code>, and its pre-fix library source tree was based on <code>{failure_source['pre_fix_library_source_commit']}</code>. The <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/944">original issue discussion</a> retains the previous outcome and source-provider identity.</p>
<p>The fix uses the identity basis after full ambient rank is established and keeps the existing first-point translation. The lower-rank SVD path remains unchanged. The regression also retains the genuine <code>5e-13</code> shear coefficient and confirms that the LP adapter still refuses it.</p></section>
<section><h2>Reproduce and inspect</h2>
<p>Source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source}"><code>{source}</code></a>. The test source runs the public Strategy A pipeline and independently checks state, control-witness feasibility, and objective values.</p>
{('<p>Illustration producer: <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/' + html.escape(rendering['commit']) + '/' + html.escape(rendering['source_path']) + '">renderer source at its distinct commit</a>.</p>') if rendering else ''}
<p><a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{source}/{reproduction["source_test"]}">Strategy A pipeline regression</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{source}/{reproduction["conversion_test"]}">Qhull and HiGHS conversion regression</a> · <a href="{RECORD_NAME}">Raw inputs and outputs</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/974">Issue #974</a></p>
<pre>{html.escape(reproduction["configure"])}
{html.escape(reproduction["build"])}
{html.escape(reproduction["run"])}</pre>
<p class="note">This is binary64 numerical evidence for the stated fixture. It is not validated arithmetic, a global error bound, or a hull minimality proof. The figure explains saved inputs and results; it does not replay MODIF pivots. No performance claim is made.</p></section>
'''
    return start + site_design.focusable_code_blocks(body) + site_design.page_end()


def build() -> dict[str, str]:
    record = load_record()
    return {
        PAGE_NAME: page(record),
        FIGURE_NAME: figure(record),
        RECORD_NAME: json.dumps(record, indent=2, ensure_ascii=False) + "\n",
    }

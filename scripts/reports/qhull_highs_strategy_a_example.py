"""Render the saved Qhull and Strategy A example for the Pages gallery."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "docs/examples/qhull-highs-strategy-a-2d-record.json"
PAGE_NAME = "qhull-highs-strategy-a-2d.html"
FIGURE_NAME = "qhull-highs-strategy-a-2d.svg"
RECORD_NAME = "qhull-highs-strategy-a-2d-record.json"


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
    vertices = record["original_ordered_conversion_input"]["vertices"]
    matrix = record["post_fix_conversion"]["matrix_A"]
    bounds = record["post_fix_conversion"]["vector_b"]
    for point in vertices:
        if any(sum(coefficient * value for coefficient, value in zip(row, point)) > bound
               for row, bound in zip(matrix, bounds)):
            raise ValueError("a source vertex violates the saved post-fix H constraints")
    for case in record["terminal_cases"]:
        state = case["terminal_state"]
        control = case["control"]
        if state != control:
            raise ValueError("the saved control differs from its identity-dynamics state")
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


def figure(record: dict) -> str:
    linear, quadratic = record["terminal_cases"]
    lp_x = 525 if linear["terminal_state"][0] == 1 else 165
    lp_y = 310 if linear["terminal_state"][1] == 0 else 130
    qp_x = 165 if quadratic["terminal_state"][0] == 0 else 525
    qp_y = 310 if quadratic["terminal_state"][1] == 0 else 130
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 470" role="img" aria-labelledby="title desc">
<title id="title">Unit-square H constraints and Strategy A terminal points</title>
<desc id="desc">Four unit-square vertices satisfy the returned Qhull constraints. The LP terminal point is one, zero. The QP terminal point is zero, zero. State and control coordinates agree because the initial state is zero and x one equals x zero plus u zero.</desc>
<rect width="760" height="470" fill="#fbfcfe"/>
<g stroke="#dce3ea" stroke-width="1">
<path d="M105 370H585 M105 310H585 M105 250H585 M105 190H585 M105 130H585 M105 70H585"/>
<path d="M105 70V370 M165 70V370 M225 70V370 M285 70V370 M345 70V370 M405 70V370 M465 70V370 M525 70V370 M585 70V370"/>
</g>
<g stroke="#405366" stroke-width="2"><path d="M105 370H610 M105 390V55"/></g>
<path d="M165 310L525 310L525 130L165 130Z" fill="#dce8f5" stroke="#32658f" stroke-width="4"/>
<g fill="#32658f"><circle cx="165" cy="310" r="6"/><circle cx="525" cy="310" r="6"/><circle cx="525" cy="130" r="6"/><circle cx="165" cy="130" r="6"/></g>
<circle cx="{lp_x}" cy="{lp_y}" r="10" fill="#bd6c22" stroke="#fff" stroke-width="3"/>
<circle cx="{qp_x}" cy="{qp_y}" r="8" fill="#7657a6" stroke="#fff" stroke-width="3"/>
<g font-family="system-ui,sans-serif" fill="#18212b">
<text x="92" y="392" font-size="14">0</text><text x="519" y="392" font-size="14">1</text>
<text x="78" y="375" font-size="14">0</text><text x="78" y="136" font-size="14">1</text>
<text x="245" y="428" font-size="17">x1.position</text><text x="23" y="223" font-size="17" transform="rotate(-90 23 223)">x1.velocity</text>
<text x="118" y="44" font-size="19">V hull / returned H region</text>
<text x="540" y="303" font-size="15" fill="#8a4a12">LP (1,0)</text>
<text x="177" y="298" font-size="15" fill="#604080">QP (0,0)</text>
<text x="105" y="458" font-size="13" fill="#405366">Original V order: (0,1), (1,1), (0,0), (1,0)</text>
</g>
</svg>'''


def page(record: dict) -> str:
    source = record["source_commit"]
    cases = record["terminal_cases"]
    reproduction = record["reproduction"]
    ordered_vertices = html.escape(json.dumps(
        record["original_ordered_conversion_input"]["vertices"], separators=(",", ":")))
    matrix = html.escape(json.dumps(
        record["post_fix_conversion"]["matrix_A"], separators=(",", ":")))
    bounds = html.escape(json.dumps(
        record["post_fix_conversion"]["vector_b"], separators=(",", ":")))
    failure = record["pre_fix_failure"]
    failure_source = record["original_ordered_conversion_input"]["source_record"]
    linear, quadratic = cases
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qhull and Strategy A on a 2D control problem</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#18212b}}
svg{{display:block;width:min(100%,760px);height:auto;border:1px solid #ccd5df;background:#fbfcfe}}
section{{margin:1.5rem 0}} code{{background:#eef2f5;padding:.1rem .3rem;border-radius:3px;overflow-wrap:anywhere}}
pre{{overflow:auto;background:#f4f6f8;padding:1rem;white-space:pre-wrap}} table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccd5df;padding:.45rem;text-align:left;vertical-align:top}} .note{{border-left:4px solid #bd6c22;padding-left:1rem}}
a{{color:#165f86}}
</style></head><body>
<header><p>Controlled Systems Lab · Geometry and control</p><h1>Qhull and Strategy A on a 2D control problem</h1>
<p>The original #944 diagnostic records the ordered square input and both HiGHS refusals. The direct Qhull regression replays those rows. A separate public Strategy A regression reconstructs the same one-step control problem and checks its source hull, bounded checker, Qhull, and both HiGHS terminal optimizer paths.</p></header>
<section><h2>Input and returned geometry</h2>
<p>The system has two state coordinates, two control coordinates, and one discrete transition. It uses <code>A=I₂</code>, <code>B=I₂</code>, <code>x0=(0,0)</code>, and <code>x1=x0+u0</code>. The stage-zero state factor is <code>[-1,1]²</code>, the control box is <code>[0,1]²</code>, and the next-state box is <code>[0,1]²</code>. The original diagnostic's Qhull input had ordered V rows <code>{ordered_vertices}</code> and no rays.</p>
<figure><img src="{FIGURE_NAME}" alt="The unit square and two labeled terminal states in position and velocity coordinates"><figcaption>The state plot shows the returned square region and terminal points. The control point has the same coordinates because the initial state is zero and the dynamics are <code>x1=x0+u0</code>.</figcaption></figure>
<p>The post-fix H rows are <code>A={matrix}</code> and <code>b={bounds}</code>. Each source vertex satisfies all four inequalities. The row order does not affect the represented square.</p></section>
<section><h2>Terminal optimizer results</h2><table><thead><tr><th>Objective</th><th>Provider</th><th>Terminal state</th><th>Control</th><th>Objective value</th></tr></thead><tbody>
<tr><td>{html.escape(linear["objective"])}</td><td><code>{html.escape(linear["optimizer"])}</code></td><td><code>{linear["terminal_state"]}</code></td><td><code>{linear["control"]}</code></td><td><code>{linear["expected_objective"]}</code></td></tr>
<tr><td>{html.escape(quadratic["objective"])}</td><td><code>{html.escape(quadratic["optimizer"])}</code></td><td><code>{quadratic["terminal_state"]}</code></td><td><code>{quadratic["control"]}</code></td><td><code>{quadratic["expected_objective"]}</code></td></tr>
</tbody></table>
<p>For the LP, <code>-x1.position=-1</code> at state and control <code>(1,0)</code>. For the QP, the Hessian is <code>2I₂</code> with center <code>(0,0)</code>, so <code>x1.position²+x1.velocity²=0</code> at state and control <code>(0,0)</code>. The test checks each terminal state with the resolved objective and checks each six-coordinate history against the returned candidate relation.</p></section>
<section><h2>What failed before the coordinate-frame fix</h2>
<p>The original rows produced two artificial coefficients of magnitude <code>1.1102230246251565e-16</code> after a full-rank SVD frame was projected back into world coordinates. The HiGHS LP and convex adapters preserve their declared <code>1e-12</code> removal threshold and refused the matrix.</p>
<pre>A = [[1, -1.1102230246251565e-16], [0, 1], [1.1102230246251565e-16, -1], [-1, 0]]
b = [0.99999999999999989, 1, 0, 0]
LP: {html.escape(failure['linear_refusal'])}
QP: {html.escape(failure['quadratic_refusal'])}</pre>
<p>The preserved #944 diagnostic artifact has SHA-256 <code>{failure_source['diagnostic_artifact_sha256']}</code>. Its runner hash is <code>{failure_source['runner_sha256']}</code>, and its pre-fix library source tree was based on <code>{failure_source['pre_fix_library_source_commit']}</code>. The <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/944">original issue discussion</a> retains the previous outcome and source-provider identity.</p>
<p>The fix uses the identity basis after full ambient rank is established and keeps the existing first-point translation. The lower-rank SVD path remains unchanged. The regression also retains the genuine <code>5e-13</code> shear coefficient and confirms that the LP adapter still refuses it.</p></section>
<section><h2>Reproduce and inspect</h2>
<p>Source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source}"><code>{source}</code></a>. The test source runs the public Strategy A pipeline and independently checks state, control, and objective values.</p>
<p><a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{source}/{reproduction["source_test"]}">Strategy A pipeline regression</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{source}/{reproduction["conversion_test"]}">Qhull and HiGHS conversion regression</a> · <a href="{RECORD_NAME}">Raw inputs and outputs</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/974">Issue #974</a></p>
<pre>{html.escape(reproduction["configure"])}
{html.escape(reproduction["build"])}
{html.escape(reproduction["run"])}</pre>
<p class="note">This is binary64 numerical evidence for the stated fixture. It is not validated arithmetic, a global error bound, or a hull minimality proof. The figure explains saved inputs and results; it does not replay MODIF pivots. No performance claim is made.</p></section>
</body></html>'''


def build() -> dict[str, str]:
    record = load_record()
    return {
        PAGE_NAME: page(record),
        FIGURE_NAME: figure(record),
        RECORD_NAME: json.dumps(record, indent=2, ensure_ascii=False) + "\n",
    }


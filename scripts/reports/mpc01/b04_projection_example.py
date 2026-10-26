#!/usr/bin/env python3
"""Render exact saved B04 reference states as two 2D projections."""

from fractions import Fraction
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "docs/research/evidence/b04-reference-v1/canonical-case.json"
REFERENCE = ROOT / "docs/research/evidence/b04-reference-v1/exact-optimal-reference.json"
SVG = ROOT / "docs/examples/b04-reference-trajectory-projections.svg"
PAGE = ROOT / "docs/examples/b04-reference-trajectory-projections.html"


def fraction(value: str) -> Fraction:
    return Fraction(value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_saved_trajectory(case: dict, reference: dict) -> list[list[Fraction]]:
    expected_coordinates = ["oxidizer_flow", "oxidizer_working_stock", "fuel_flow", "fuel_working_stock"]
    require(case["case_id"] == "b04-reference-v1", "unexpected case identity")
    require(case["state_dimension"] == len(expected_coordinates) == 4, "unexpected state dimension")
    require(case["control_dimension"] == 1, "unexpected control dimension")
    require(case["horizon"] == 16, "unexpected horizon")
    require(case["state_coordinates"] == expected_coordinates, "state coordinate order changed")
    require(case["state_units"] == ["kg/s", "kg", "kg/s", "kg"], "state units changed")
    require(case["state_bound_stages"] == [0, 16], "flow bound stages changed")
    states = [[fraction(v) for v in row] for row in reference["exact_optimal_states_one_solution"]]
    controls = [fraction(v) for v in reference["exact_optimal_controls_one_solution"]]
    require(len(states) == case["horizon"] + 1, "witness state count does not match the horizon")
    require(len(controls) == case["horizon"], "witness control count does not match the horizon")
    initial = [fraction(v) for v in case["initial_state"]]
    require(states[0] == initial, "witness does not begin at the declared initial state")
    a = [fraction(v) for v in case["dynamics"]["A_row_major"]]
    b = [fraction(v) for v in case["dynamics"]["B"]]
    affine = [fraction(v) for v in case["dynamics"]["affine"]]
    lo, hi = (fraction(v) for v in (case["control_bounds_each_stage"]["lower"],
                                      case["control_bounds_each_stage"]["upper"]))
    for k, control in enumerate(controls):
        require(lo <= control <= hi, f"control at stage {k} is outside its bounds")
        expected = [sum(a[i * 4 + j] * states[k][j] for j in range(4)) + b[i] * control + affine[i]
                    for i in range(4)]
        require(expected == states[k + 1], f"exact dynamics mismatch at stage {k}")
    bounds = {item["coordinate"]: (fraction(item["lower"]), fraction(item["upper"]))
              for item in case["state_bounds_each_stage"]}
    require(set(bounds) == {0, 2} and len(case["state_bounds_each_stage"]) == 2,
            "expected exactly the two declared flow bounds")
    for state in states:
        for coordinate, (lower, upper) in bounds.items():
            require(lower <= state[coordinate] <= upper,
                    f"state coordinate {coordinate} is outside bounds at a declared stage")
    return states


def svg_text(x: float, y: float, value: str, *, size: int = 14, anchor: str = "middle") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}">{html.escape(value)}</text>'


def panel(states: list[list[Fraction]], x_index: int, y_index: int, title: str,
          x_label: str, y_label: str, left: int, bounds=None) -> str:
    top, width, height = 120, 370, 340
    xs = [float(s[x_index]) for s in states]
    ys = [float(s[y_index]) for s in states]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if bounds is not None:
        (xlo, xhi), (ylo, yhi) = bounds
        xmin, xmax = min(xmin, float(xlo)), max(xmax, float(xhi))
        ymin, ymax = min(ymin, float(ylo)), max(ymax, float(yhi))
    xpad = max((xmax - xmin) * 0.06, 1.0)
    ypad = max((ymax - ymin) * 0.06, 1.0)
    xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad
    sx = lambda v: left + (v - xmin) / (xmax - xmin) * width
    sy = lambda v: top + height - (v - ymin) / (ymax - ymin) * height
    parts = [svg_text(left + width / 2, 88, title, size=18),
             f'<path d="M{left} {top + height}H{left + width} M{left} {top}V{top + height}" class="axis"/>']
    if bounds is not None:
        (xlo, xhi), (ylo, yhi) = bounds
        rx, ry = sx(float(xlo)), sy(float(yhi))
        rw, rh = sx(float(xhi)) - rx, sy(float(ylo)) - ry
        parts.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" class="feasible"/>')
        parts.append(svg_text(left + width / 2, top + 34, "stage constraints", size=12))
    points = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
    parts.append(f'<polyline points="{points}" class="trajectory"/>')
    for k, (x, y) in enumerate(zip(xs, ys)):
        parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4" class="point"/>')
        if k in (0, 4, 8, 12, 16):
            offsets = {0: (10, -10), 4: (-42, -29), 8: (-42, 0), 12: (-42, 29), 16: (10, 15)}
            dx, dy = offsets[k]
            parts.append(f'<path d="M{sx(x):.1f},{sy(y):.1f} L{sx(x)+dx*.72:.1f},{sy(y)+dy*.72:.1f}" class="leader"/>')
            parts.append(svg_text(sx(x) + dx, sy(y) + dy, str(k), size=11, anchor="start" if dx > 0 else "end"))
    parts += [svg_text(left + width / 2, top + height + 48, x_label, size=14),
              f'<text transform="translate({left - 53} {top + height / 2}) rotate(-90)" text-anchor="middle">{html.escape(y_label)}</text>']
    for i in range(5):
        xv = xmin + (xmax - xmin) * i / 4
        yv = ymin + (ymax - ymin) * i / 4
        precision = 1 if xmax - xmin < 1000 else 0
        parts.append(svg_text(sx(xv), top + height + 20, f"{xv:.{precision}f}", size=11))
        parts.append(svg_text(left - 10, sy(yv) + 4, f"{yv:.{precision}f}", size=11, anchor="end"))
    return "\n".join(parts)


def main() -> None:
    case = json.loads(CASE.read_bytes().decode("utf-8"))
    reference = json.loads(REFERENCE.read_bytes().decode("utf-8"))
    states = check_saved_trajectory(case, reference)
    coordinates = {name: index for index, name in enumerate(case["state_coordinates"])}
    units = dict(zip(case["state_coordinates"], case["state_units"]))
    bounds = {case["state_coordinates"][item["coordinate"]]:
              (fraction(item["lower"]), fraction(item["upper"]))
              for item in case["state_bounds_each_stage"]}
    flow_bounds = (bounds["oxidizer_flow"], bounds["fuel_flow"])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 590" role="img" aria-labelledby="title desc">
<title id="title">B04 reference trajectory projected from four states into two planes</title>
<desc id="desc">A selected exact optimal trajectory from the separate b04-reference-v1 case. One panel plots oxidizer flow against fuel flow and marks their stage constraints. The other plots the two working stocks. Stage labels mark 0, 4, 8, 12, and 16. This is not historical B04 data.</desc>
<rect width="1000" height="590" fill="#172019"/>
<style>svg{{background:#172019;font-family:system-ui,sans-serif;color:#dce5d5}} text{{fill:#dce5d5}} .axis{{stroke:#a9b7a0;stroke-width:2}} .trajectory{{fill:none;stroke:#f2b880;stroke-width:3}} .point{{fill:#f2b880;stroke:#172019;stroke-width:1}} .leader{{stroke:#dce5d5;stroke-width:1}} .feasible{{fill:#76966d;fill-opacity:.12;stroke:#b4cda3;stroke-dasharray:6 4;stroke-width:2}}</style>
<text x="500" y="34" text-anchor="middle" font-size="22">Fuel reference trajectory: two projections of the 4D state</text>
<text x="500" y="59" text-anchor="middle" font-size="13">b04-reference-v1 · exact saved witness · stages 0–16 · not a historical B04 reconstruction</text>
{panel(states, coordinates["oxidizer_flow"], coordinates["fuel_flow"], "Flow plane", f"Oxidizer flow ({units['oxidizer_flow']})", f"Fuel flow ({units['fuel_flow']})", 95, flow_bounds)}
{panel(states, coordinates["oxidizer_working_stock"], coordinates["fuel_working_stock"], "Working-stock plane", f"Oxidizer working stock ({units['oxidizer_working_stock']})", f"Fuel working stock ({units['fuel_working_stock']})", 535)}
<text x="500" y="555" text-anchor="middle" font-size="12">State order: oxidizer flow, oxidizer stock, fuel flow, fuel stock. Labels show selected stages.</text>
<text x="500" y="576" text-anchor="middle" font-size="12">No stock constraints are specified; negative stocks appear in this exact reference witness.</text>
</svg>'''
    SVG.write_bytes((svg + "\n").encode("utf-8"))
    PAGE.write_bytes(('''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B04 reference fuel trajectory projections</title>
<style>body{margin:0;background:#0b1020;color:#e2e8f0;font:16px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:2rem}h1{line-height:1.15}a{color:#7dd3fc}code{color:#fde68a}img{width:100%;height:auto}.scope{border-left:4px solid #fb7185;padding:.7rem 1rem;background:#171d30}</style></head>
<body><main><p><a href="index.html#visual-mpc01-b04-reference-projection">← Visual examples</a></p><p>Exact saved reference data, shown as an illustration</p>
<h1>Projecting a four-state fuel trajectory into two planes</h1>
<p>The state is <code>(oxidizer flow, oxidizer working stock, fuel flow, fuel working stock)</code>. The left panel projects each four-dimensional state onto the two flow coordinates; the right projects onto the two working-stock coordinates. Stage labels show 0, 4, 8, 12, and 16.</p>
<img src="b04-reference-trajectory-projections.svg" alt="A selected exact optimal B04 reference trajectory projected into flow and working-stock planes">
<p class="scope"><strong>Evidence scope.</strong> This plots one exact optimal witness from the separate <code>b04-reference-v1</code> article-derived reference input. It is not a reconstruction of historical B04, not a complete optimal-control family, and not an OSQP or HPIPM comparison. The plotted flow box shows the declared stage constraints. The stock coordinates can become negative because the source specifies no stock bounds.</p>
<h2>Reproduce</h2><pre><code>python3 scripts/reports/mpc01/b04_projection_example.py</code></pre>
<p><strong>Oracle method.</strong> The witness comes from exact rational minimization over the affine terminal plane, followed by exact feasibility checks for the selected control history. That construction establishes one global optimum for this frozen reference variant. It is not Strategy A, Strategy B, or an external QP solver. See the <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/23b0d912236386860ad036894af138bf9f78a9db/docs/research/evidence/b04-reference-v1/canonical-case.json">pinned input case</a>, <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/23b0d912236386860ad036894af138bf9f78a9db/docs/research/evidence/b04-reference-v1/exact-optimal-reference.json">exact witness</a>, <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/23b0d912236386860ad036894af138bf9f78a9db/docs/research/evidence/b04-reference-v1/exact_check.py">oracle source</a>, and <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/23b0d912236386860ad036894af138bf9f78a9db/docs/research/evidence/b04-reference-v1/exact-check-report.json">independent exact-check report</a>.</p>
</main></body></html>\n''').encode("utf-8"))
    print(f"wrote {SVG.relative_to(ROOT)} and {PAGE.relative_to(ROOT)}; checked {len(states)} exact states")


if __name__ == "__main__":
    main()

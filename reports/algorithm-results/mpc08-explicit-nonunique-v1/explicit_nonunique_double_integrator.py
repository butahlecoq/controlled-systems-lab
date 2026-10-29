#!/usr/bin/env python3
"""Exact rational two-step double-integrator reference with a nonunique optimum."""
from __future__ import annotations

from fractions import Fraction as F
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated"


def fmt(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def optimal_u0_interval(v: F) -> tuple[F, F]:
    """u0 range subject to u0,u1 in [-1,1] and v+u0+u1=0."""
    return max(F(-1), -v - 1), min(F(1), -v + 1)


def selector(v: F) -> tuple[F, F]:
    """Minimum-Euclidean-norm element of the exact optimal control family."""
    return -v / 2, -v / 2


def verify() -> tuple[list[dict], list[dict]]:
    domain_p = (F(-3), F(3))
    domain_v = (F(-2), F(2))
    states: list[dict] = []
    queries: list[dict] = []
    count = 0
    for p in (F(-3), F(0), F(3)):
        for v in (F(-2), F(-1), F(0), F(1), F(2)):
            lower, upper = optimal_u0_interval(v)
            if lower > upper:
                raise AssertionError("declared domain contains an infeasible initial velocity")
            u0_selector, u1_selector = selector(v)
            if not lower <= u0_selector <= upper or u0_selector + u1_selector != -v:
                raise AssertionError("minimum-norm selector is outside the optimal face")
            p1, v1 = p + v, v + u0_selector
            p2, v2 = p1 + v1, v1 + u1_selector
            if v2 != 0:
                raise AssertionError("selector does not attain the exact minimum value")
            states.append({
                "initial_exact": [fmt(p), fmt(v)],
                "u0_interval_exact": [fmt(lower), fmt(upper)],
                "first_action_set_width_exact": fmt(upper - lower),
                "minimum_norm_selector_exact": [fmt(u0_selector), fmt(u1_selector)],
                "terminal_exact": [fmt(p2), fmt(v2)],
                "optimal_value_exact": "0",
            })
            # Endpoints and midpoint expose the complete one-dimensional control fiber.
            for index, u0 in enumerate((lower, (lower + upper) / 2, upper)):
                u1 = -v - u0
                if not (F(-1) <= u0 <= F(1) and F(-1) <= u1 <= F(1)):
                    raise AssertionError("sampled optimal history violates the control box")
                terminal_p = p + 2 * v + u0
                terminal_v = v + u0 + u1
                if terminal_v != 0:
                    raise AssertionError("sampled history is not optimal")
                queries.append({
                    "query_id": f"N{count + 1:03d}",
                    "p_exact": fmt(p), "v_exact": fmt(v),
                    "u0_exact": fmt(u0), "u1_exact": fmt(u1),
                    "value_exact": "0", "terminal_p_exact": fmt(terminal_p),
                    "terminal_v_exact": "0", "fiber_sample": index,
                })
                count += 1
    return states, queries


def svg() -> str:
    # Left panel: every point in X is feasible; color varies with selector u0=-v/2.
    # Right panel: the full optimizer fiber for (p0,v0)=(0,0) and its selector.
    width, height = 1000, 520
    left = (310, 310)
    sx, sy = 72, 78
    x0, y0 = left
    x_left, x_right = x0 - 3 * sx, x0 + 3 * sx
    y_top, y_bottom = y0 - 2 * sy, y0 + 2 * sy
    gradient = []
    for row in range(80):
        v = F(2) - F(row, 20)
        fraction = max(0.0, min(1.0, float((v + 2) / 4)))
        red, blue = int(44 + 80 * fraction), int(120 + 90 * (1 - fraction))
        y = y_top + row * (y_bottom - y_top) / 80
        gradient.append(f'<rect x="{x_left}" y="{y:.2f}" width="{x_right-x_left}" height="5.0" fill="rgb({red},110,{blue})"/>')
    # Optimizer fiber at v0=0: u1=-u0, a segment with selector at the origin.
    right_origin = (720, 280)
    cx, cy = right_origin
    control_scale = 155
    line = f'<line x1="{cx-control_scale}" y1="{cy-control_scale}" x2="{cx+control_scale}" y2="{cy+control_scale}" stroke="#bd3b32" stroke-width="7" stroke-linecap="round"/>'
    points = ''.join(f'<circle cx="{cx + control_scale * u}" cy="{cy + control_scale * u}" r="7" fill="#1b4f8a"/>' for u in (-1, 1))
    selector_point = f'<circle cx="{cx}" cy="{cy}" r="9" fill="#fabd2f" stroke="#282828" stroke-width="2"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Nonunique optimal family and tie-broken explicit selector</title>
<desc id="desc">The feasible initial state rectangle is on the left. The right panel shows all optimal two-stage controls for initial velocity zero as a line segment; the minimum-norm selector chooses its center.</desc>
<rect width="100%" height="100%" fill="#fff"/>
<text x="325" y="38" font-family="sans-serif" font-size="22" font-weight="700" text-anchor="middle">Feasible initial-state domain F₂</text>
<text x="325" y="65" font-family="sans-serif" font-size="14" text-anchor="middle">X=[−3,3]×[−2,2], V₂(p,v)=0 throughout</text>
<g>{''.join(gradient)}</g><rect x="{x_left}" y="{y_top}" width="{x_right-x_left}" height="{y_bottom-y_top}" fill="none" stroke="#262626" stroke-width="3"/>
<text x="{x_left+8}" y="{y_top+20}" font-family="sans-serif" font-size="13">fill color encodes selector u₀=−v₀/2</text>
<line x1="{x_left}" y1="{y0}" x2="{x_right}" y2="{y0}" stroke="#555"/><line x1="{x0}" y1="{y_top}" x2="{x0}" y2="{y_bottom}" stroke="#555"/>
<text x="{x_right+6}" y="{y0+5}" font-family="sans-serif" font-size="13">p₀</text><text x="{x0+5}" y="{y_top-8}" font-family="sans-serif" font-size="13">v₀</text>
<text x="720" y="38" font-family="sans-serif" font-size="22" font-weight="700" text-anchor="middle">Full optimal control fiber</text>
<text x="720" y="65" font-family="sans-serif" font-size="14" text-anchor="middle">initial state (p₀,v₀)=(0,0); u₀+u₁=0</text>
<line x1="565" y1="280" x2="875" y2="280" stroke="#555"/><line x1="720" y1="115" x2="720" y2="445" stroke="#555"/>
{line}{points}{selector_point}<text x="{cx+control_scale+12}" y="{cy+control_scale+5}" font-family="sans-serif" font-size="13">(1,-1)</text>
<text x="{cx-control_scale-62}" y="{cy-control_scale-10}" font-family="sans-serif" font-size="13">(-1,1)</text>
<text x="885" y="285" font-family="sans-serif" font-size="13">u₀</text><text x="725" y="112" font-family="sans-serif" font-size="13">u₁</text>
<text x="720" y="505" font-family="sans-serif" font-size="14" text-anchor="middle">Red segment: complete optimizer fiber · gold point: minimum-norm selector</text>
</svg>\n'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    states, queries = verify()
    record = {
        "schema": "csl.mpc08-nonunique-double-integrator/1",
        "problem": "two-step discrete double integrator, terminal velocity-squared objective",
        "dynamics": {"p_next": "p+v", "v_next": "v+u"},
        "horizon": 2,
        "initial_domain_exact": {"p": ["-3", "3"], "v": ["-2", "2"]},
        "control_domain_exact": {"u0": ["-1", "1"], "u1": ["-1", "1"]},
        "objective_exact": "(v0+u0+u1)^2",
        "feasible_initial_set": "X itself; every v0 in [-2,2] can reach v2=0",
        "optimal_value_exact": "0 on X",
        "complete_optimal_relation": "u0 in [-1,1] intersect [-v0-1,-v0+1], u1=-v0-u0",
        "explicit_tie_break": "minimize u0^2+u1^2 over the optimal fiber; u0=u1=-v0/2",
        "states": states,
        "sampled_histories": queries,
        "state_sample_count": len(states), "history_sample_count": len(queries),
        "coverage_claim": "Exact symbolic formulas on the full declared rectangle; samples check representative histories only.",
    }
    (OUT / "explicit-nonunique-double-integrator.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (OUT / "explicit-nonunique-queries.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("query_id", "p_exact", "v_exact", "u0_exact", "u1_exact", "value_exact", "p", "v", "u0", "u1"))
        for query in queries:
            writer.writerow((query["query_id"], query["p_exact"], query["v_exact"], query["u0_exact"], query["u1_exact"], query["value_exact"],
                             float(F(query["p_exact"])), float(F(query["v_exact"])), float(F(query["u0_exact"])), float(F(query["u1_exact"]))))
    (OUT / "explicit-nonunique-double-integrator.svg").write_text(svg(), encoding="utf-8")
    print(f"verified {len(states)} state products and {len(queries)} exact optimal histories")


if __name__ == "__main__":
    main()

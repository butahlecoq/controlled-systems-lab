#!/usr/bin/env python3
"""Exact, dependency-free one-step explicit MPC reference for issue #604.

The reference enumerates the critical regions of a scalar terminal-only QP
using rational half-space clipping. It is a fixture-specific analytic oracle,
not a general multiparametric-QP package or an MPT3 port.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import csv
import time


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated"
Point = tuple[F, F]
# a*p + b*v <= c
Halfspace = tuple[F, F, F]


def q(value: int | str) -> F:
    return F(value)


def area(poly: list[Point]) -> F:
    if len(poly) < 3:
        return F(0)
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                    - poly[(i + 1) % len(poly)][0] * poly[i][1]
                    for i in range(len(poly))) / 2)


def clip(poly: list[Point], h: Halfspace) -> list[Point]:
    if not poly:
        return []
    a, b, c = h
    out: list[Point] = []
    prev = poly[-1]
    prev_value = a * prev[0] + b * prev[1] - c
    for cur in poly:
        cur_value = a * cur[0] + b * cur[1] - c
        if (prev_value <= 0) != (cur_value <= 0):
            t = prev_value / (prev_value - cur_value)
            out.append((prev[0] + t * (cur[0] - prev[0]),
                        prev[1] + t * (cur[1] - prev[1])))
        if cur_value <= 0:
            out.append(cur)
        prev, prev_value = cur, cur_value
    compact: list[Point] = []
    for point in out:
        if not compact or point != compact[-1]:
            compact.append(point)
    if len(compact) > 1 and compact[0] == compact[-1]:
        compact.pop()
    return compact


def intersect(box: list[Point], halfspaces: list[Halfspace]) -> list[Point]:
    poly = box
    for h in halfspaces:
        poly = clip(poly, h)
        if not poly:
            break
    return poly


def holds(h: Halfspace, x: Point) -> bool:
    return h[0] * x[0] + h[1] * x[1] <= h[2]


@dataclass(frozen=True)
class Affine:
    p: F
    v: F
    c: F

    def at(self, x: Point) -> F:
        return self.p * x[0] + self.v * x[1] + self.c

    def le(self, other: "Affine") -> Halfspace:
        return self.p - other.p, self.v - other.v, other.c - self.c


LOWER = (Affine(0, 0, -1), Affine(-1, -2, -1), Affine(F(-1, 2), F(-3, 2), F(-1, 2)))
UPPER = (Affine(0, 0, 1), Affine(-1, -2, 1), Affine(F(-1, 2), F(-3, 2), F(1, 2)))
BOX = [(-3, -2), (3, -2), (3, 2), (-3, 2)]
BOX = [(F(p), F(v)) for p, v in BOX]


@dataclass
class Region:
    lower: int
    upper: int
    mode: str
    constraints: list[Halfspace]
    polygon: list[Point]
    control: Affine


def problem_halfspaces() -> list[Halfspace]:
    domain = [(F(1), F(0), F(3)), (F(-1), F(0), F(3)),
              (F(0), F(1), F(2)), (F(0), F(-1), F(2))]
    # max(lower) <= min(upper) iff every lower candidate is <= every upper.
    return domain + [lower.le(upper) for lower in LOWER for upper in UPPER]


def region_constraints(i: int, j: int, mode: str) -> tuple[list[Halfspace], Affine]:
    li, uj = LOWER[i], UPPER[j]
    constraints = problem_halfspaces()
    constraints += [lower.le(li) for lower in LOWER]   # li is the active max
    constraints += [uj.le(upper) for upper in UPPER]   # uj is the active min
    if mode == "lower":       # -v <= li, so u*=li
        constraints.append((-li.p, -1 - li.v, li.c))
        control = li
    elif mode == "free":      # li <= -v <= uj, so u*=-v
        constraints.append((li.p, li.v + 1, -li.c))
        constraints.append((-uj.p, -1 - uj.v, uj.c))
        control = Affine(0, -1, 0)
    elif mode == "upper":     # uj <= -v, so u*=uj
        constraints.append((uj.p, uj.v + 1, -uj.c))
        control = uj
    else:
        raise ValueError(mode)
    return constraints, control


def build_regions() -> tuple[list[Point], list[Region]]:
    feasible = intersect(BOX, problem_halfspaces())
    regions = []
    for i in range(len(LOWER)):
        for j in range(len(UPPER)):
            for mode in ("lower", "free", "upper"):
                constraints, control = region_constraints(i, j, mode)
                poly = intersect(BOX, constraints)
                if area(poly) > 0:
                    regions.append(Region(i, j, mode, constraints, poly, control))
    return feasible, regions


def terminal_set() -> list[Point]:
    # T = {|p+2v| <= 1, |p+v| <= 1}.
    hs = [(F(1), F(2), F(1)), (F(-1), F(-2), F(1)),
          (F(1), F(1), F(1)), (F(-1), F(-1), F(1))]
    return intersect([(F(-4), F(-4)), (F(4), F(-4)),
                      (F(4), F(4)), (F(-4), F(4))], hs)


def feedback(x: Point) -> F:
    return -x[0] - 2 * x[1]


def terminal(x: Point, u: F) -> Point:
    return x[0] + x[1], x[1] + u


def verify_invariance(t: list[Point]) -> None:
    # K=[-1,-2] gives A+BK=[[1,1],[-1,-1]], whose square is zero.
    for x in t:
        u = feedback(x)
        if abs(u) > 1:
            raise AssertionError("terminal feedback violates input bounds")
        nxt = terminal(x, u)
        if abs(nxt[0] + 2 * nxt[1]) > 1 or abs(nxt[0] + nxt[1]) > 1:
            raise AssertionError("terminal feedback leaves T")


def verify_partition(feasible: list[Point], regions: list[Region]) -> None:
    if not feasible or not regions:
        raise AssertionError("empty feasible set or critical-region partition")
    if sum((area(r.polygon) for r in regions), F(0)) != area(feasible):
        raise AssertionError("critical-region areas do not cover feasible domain")
    for i, left in enumerate(regions):
        for right in regions[i + 1:]:
            overlap = intersect(BOX, left.constraints + right.constraints)
            if area(overlap) > 0:
                raise AssertionError("critical-region interiors overlap")
    # Every exact region vertex (including shared boundaries) must be covered,
    # and all active formulas at a boundary must return the same input.
    points = {p for region in regions for p in region.polygon} | set(feasible)
    for x in points:
        candidates = [r.control.at(x) for r in regions if all(holds(h, x) for h in r.constraints)]
        if not candidates or len(set(candidates)) != 1:
            raise AssertionError("region boundary has a coverage gap or inconsistent selector")


def locate(regions: list[Region], x: Point) -> F:
    candidates = [r.control.at(x) for r in regions if all(holds(h, x) for h in r.constraints)]
    if not candidates or len(set(candidates)) != 1:
        raise ValueError("point outside partition or boundary policy disagreement")
    return candidates[0]


def fmt(x: F) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def square_affine(coefficients: tuple[F, F, F]) -> tuple[F, F, F, F, F, F]:
    a, b, c = coefficients
    return a*a, 2*a*b, b*b, 2*a*c, 2*b*c, c*c


def add_quadratics(left: tuple[F, ...], right: tuple[F, ...]) -> tuple[F, ...]:
    return tuple(a+b for a, b in zip(left, right))


def svg(feasible: list[Point], regions: list[Region], invariant: list[Point]) -> str:
    colors = ("#cfe8ff", "#acd6fb", "#81c1ed", "#d8f0cc", "#b8e3a8", "#98d47f",
              "#fff0b8", "#ffdd84", "#ffc85b", "#efb2c8", "#df8eac", "#cf6d91")
    def xy(x: Point, origin: tuple[int, int], scale: int) -> tuple[float, float]:
        return origin[0] + float(x[0]) * scale, origin[1] - float(x[1]) * scale
    def points(poly: list[Point], origin: tuple[int, int], scale: int) -> str:
        return " ".join(f"{px:.2f},{py:.2f}" for px, py in (xy(x, origin, scale) for x in poly))
    left_origin, left_scale = (340, 400), 85
    x_box = [(F(-3), F(-2)), (F(3), F(-2)), (F(3), F(2)), (F(-3), F(2))]
    shapes = [f'<polygon points="{points(x_box,left_origin,left_scale)}" fill="#f3f4f6" stroke="#6b7280" stroke-width="2"/>',
              '<text x="100" y="245" font-size="13" font-weight="bold">X</text>']
    for index, region in enumerate(regions):
        shapes.append(f'<polygon points="{points(region.polygon,left_origin,left_scale)}" fill="{colors[index%len(colors)]}" stroke="#263544" stroke-width="1"/>')
        cx = sum((p[0] for p in region.polygon), F(0)) / len(region.polygon)
        cy = sum((p[1] for p in region.polygon), F(0)) / len(region.polygon)
        label_x, label_y = xy((cx, cy), left_origin, left_scale)
        shapes.append(f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" font-size="10">R{index+1}</text>')
    shapes.append(f'<polygon points="{points(feasible,left_origin,left_scale)}" fill="none" stroke="#111827" stroke-width="3"/>')
    xx, xy_top = xy((F(-2.8), F(1.8)), left_origin, left_scale)
    shapes.append(f'<text x="{xx:.2f}" y="{xy_top:.2f}" font-size="14" font-weight="bold">X</text>')
    right_origin, right_scale = (800, 300), 55
    shapes.append(f'<polygon points="{points(invariant,right_origin,right_scale)}" fill="#f9d976" stroke="#8a5410" stroke-width="3"/>')
    fx, fy = xy((F(0), F(0)), left_origin, left_scale)
    shapes.append(f'<text x="{fx+9:.2f}" y="{fy-10:.2f}" font-size="15" font-weight="bold">F</text>')
    for p in (-3,-2,-1,0,1,2,3):
        x, y = xy((F(p),F(0)), left_origin, left_scale)
        shapes.append(f'<line x1="{x:.2f}" y1="85" x2="{x:.2f}" y2="725" stroke="#d1d5db" stroke-width=".5"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 800" role="img" aria-labelledby="title desc">
<title id="title">Explicit MPC feasibility, critical regions, and invariant terminal set</title>
<desc id="desc">Left: exact feasible initial domain and disjoint critical regions for a one-step double-integrator terminal quadratic program. Right: a separate invariant terminal set in terminal coordinates.</desc>
<rect width="1040" height="800" fill="#ffffff"/><text x="340" y="42" text-anchor="middle" font-size="22" font-weight="bold">Initial-state parameter plane</text>
<text x="340" y="68" text-anchor="middle" font-size="14">feasible domain F and critical regions R1–R{len(regions)}</text>
<text x="800" y="42" text-anchor="middle" font-size="22" font-weight="bold">Terminal invariant set T</text>
<text x="800" y="68" text-anchor="middle" font-size="14">terminal-state coordinates (p1, v1)</text>
<line x1="85" y1="400" x2="595" y2="400" stroke="#374151"/><line x1="340" y1="60" x2="340" y2="740" stroke="#374151"/>
<line x1="610" y1="90" x2="610" y2="500" stroke="#777"/>
{''.join(shapes)}
<text x="590" y="423" font-size="13">p0</text><text x="348" y="88" font-size="13">v0</text>
<text x="970" y="305" font-size="13">p1</text><text x="805" y="180" font-size="13">v1</text>
<text x="340" y="770" text-anchor="middle" font-size="13">Rk labels are local to this partition; borders are shared only where affine selectors agree.</text>
</svg>'''


def main() -> None:
    started = time.perf_counter_ns()
    feasible, regions = build_regions()
    terminal_poly = terminal_set()
    verify_partition(feasible, regions)
    verify_invariance(terminal_poly)
    offline_ns = time.perf_counter_ns() - started

    # Measure point location separately from offline region construction and
    # from the online QP solved by a conventional optimizer.
    queries = []
    for ix in range(21):
        for iy in range(21):
            x = (F(-3) + F(6 * ix, 20), F(-2) + F(4 * iy, 20))
            if all(holds(h, x) for h in problem_halfspaces()):
                queries.append(x)
    rounds = []
    for _ in range(7):
        t0 = time.perf_counter_ns()
        outputs = [locate(regions, x) for x in queries]
        rounds.append(time.perf_counter_ns() - t0)
        if len(outputs) != len(queries):
            raise AssertionError("point-location query count changed")

    # Solver queries include one interior point per region, every region
    # vertex, and every region-edge midpoint. Exact formulas agree on shared
    # faces; the CSL runs check that its fixed-initial candidate contains the
    # analytically selected unique history at these points.
    validation_points = set()
    for region in regions:
        poly = region.polygon
        validation_points.add((sum((p[0] for p in poly), F(0)) / len(poly),
                               sum((p[1] for p in poly), F(0)) / len(poly)))
        validation_points.update(poly)
        validation_points.update(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                                 for a, b in zip(poly, poly[1:] + poly[:1]))

    region_records = []
    for n, region in enumerate(regions, 1):
        # On each cell x1=(p+v, v+u*) and J=x1'x1.
        terminal_velocity = Affine(region.control.p, region.control.v + 1, region.control.c)
        a, b, c = terminal_velocity.p, terminal_velocity.v, terminal_velocity.c
        region_records.append({
            "id": f"R{n}", "active_lower": region.lower,
            "active_upper": region.upper, "clamp_case": region.mode,
            "control_affine_p_v_constant": [fmt(region.control.p), fmt(region.control.v), fmt(region.control.c)],
            "terminal_position_affine_p_v_constant": ["1", "1", "0"],
            "terminal_velocity_affine_p_v_constant": [fmt(a), fmt(b), fmt(c)],
            "value_polynomial_coefficients_p2_pv_v2_p_v_constant": [
                fmt(1+a*a), fmt(2+2*a*b), fmt(1+b*b), fmt(2*a*c), fmt(2*b*c), fmt(c*c)],
            "area": fmt(area(region.polygon)),
            "vertices": [[fmt(p), fmt(v)] for p, v in region.polygon],
        })
        expected_value_poly = add_quadratics(square_affine((F(1), F(1), F(0))),
                                             square_affine((a, b, c)))
        actual_value_poly = tuple(F(value) for value in region_records[-1][
            "value_polynomial_coefficients_p2_pv_v2_p_v_constant"])
        if actual_value_poly != expected_value_poly:
            raise AssertionError(f"{region_records[-1]['id']} value polynomial differs from terminal cost")
    query_records = []
    for index, x in enumerate(sorted(validation_points), 1):
        u = locate(regions, x)
        value = (x[0] + x[1]) ** 2 + (x[1] + u) ** 2
        query_records.append({"id": f"Q{index:03d}", "p": fmt(x[0]), "v": fmt(x[1]),
                              "u_star": fmt(u), "value": fmt(value)})
    record = {
        "schema": "csl.mpc08-explicit-double-integrator/1",
        "model": {"A": [[1, 1], [0, 1]], "B": [[0], [1]], "horizon": 1,
                  "state_parameter_box": [[-3, 3], [-2, 2]], "control_box": [-1, 1]},
        "terminal_set": {"coordinates": ["p1", "v1"], "inequalities": ["|p1+2v1|<=1", "|p1+v1|<=1"],
                         "vertices": [[fmt(p), fmt(v)] for p, v in terminal_poly],
                         "invariant_feedback": ["-1", "-2"],
                         "closed_loop_matrix": [["1", "1"], ["-1", "-1"]],
                         "closed_loop_matrix_square": [["0", "0"], ["0", "0"]],
                         "invariant_verified_at_all_vertices": True},
        "objective": "minimize p1^2 + v1^2 (terminal-only; no control regularizer)",
        "explicit_solution": {"lower_u": ["-1", "-1-p-2v", "(-1-p-3v)/2"],
                              "upper_u": ["1", "1-p-2v", "(1-p-3v)/2"],
                              "u_star": "clamp(-v, max(lower_u), min(upper_u))",
                              "feasible_initial_polygon": [[fmt(p), fmt(v)] for p, v in feasible],
                              "feasible_area": fmt(area(feasible)), "critical_region_count": len(regions),
                              "region_area_sum": fmt(sum((area(r.polygon) for r in regions), F(0))),
                              "interior_overlaps": 0, "coverage_check": "exact rational half-space partition"},
        "measurement": {"offline_region_construction_ns": offline_ns,
                        "point_location_queries": len(queries), "point_location_rounds_ns": rounds,
                        "scope": "Python exact-rational region construction; point-location only, excludes optimizer and CSL workspaces"},
        "regions": region_records,
        "solver_validation_query_count": len(query_records),
        "solver_validation_queries": query_records,
        "limitations": ["fixture-specific one-step reference, not a general mpQP implementation",
                        "online values/first action are explicit maps; CSL returns a fixed-initial joint relation",
                        "performance timings are descriptive Python point-location/region-generation timings, not compared to C++ solver timings"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    json_path, svg_path = OUT / "explicit-double-integrator.json", OUT / "explicit-double-integrator.svg"
    queries_path = OUT / "explicit-double-integrator-queries.csv"
    json_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    svg_path.write_text(svg(feasible, regions, terminal_poly), encoding="utf-8")
    with queries_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("id", "p_exact", "v_exact", "u_exact", "value_exact", "p", "v"),
                                lineterminator="\n")
        writer.writeheader()
        for item in query_records:
            p, v, u, value = (F(item[key]) for key in ("p", "v", "u_star", "value"))
            writer.writerow({"id": item["id"], "p_exact": item["p"], "v_exact": item["v"],
                             "u_exact": item["u_star"], "value_exact": item["value"],
                             "p": format(float(p), ".17g"), "v": format(float(v), ".17g")})
    digest = hashlib.sha256(json_path.read_bytes()).hexdigest()
    print(json.dumps({"json": str(json_path), "svg": str(svg_path), "queries": str(queries_path), "json_sha256": digest,
                      "feasible_area": fmt(area(feasible)), "regions": len(regions), "queries": len(queries)}))


if __name__ == "__main__":
    main()

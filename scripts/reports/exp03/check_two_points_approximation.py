#!/usr/bin/env python3
"""Independently check EXP-03 phase-plane set relations and areas."""

from __future__ import annotations

import argparse
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path


def q(value):
    """Interpret a JSON number as its exact stored binary64 value."""
    return Fraction.from_float(float(value))


def cross(origin, left, right):
    return ((left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0]))


def hull(points):
    ordered = sorted(set(points))
    if len(ordered) <= 1:
        return ordered
    lower = []
    for point in ordered:
        while len(lower) > 1 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(ordered):
        while len(upper) > 1 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def contains_convex(point, vertices):
    if len(vertices) == 1:
        return point == vertices[0]
    if len(vertices) == 2:
        return (cross(vertices[0], vertices[1], point) == 0
                and min(vertices[0][0], vertices[1][0]) <= point[0] <= max(vertices[0][0], vertices[1][0])
                and min(vertices[0][1], vertices[1][1]) <= point[1] <= max(vertices[0][1], vertices[1][1]))
    return all(cross(vertices[i], vertices[(i + 1) % len(vertices)], point) >= 0
               for i in range(len(vertices)))


def polygon_area(vertices):
    if len(vertices) < 3:
        return Fraction(0)
    return abs(sum(
        vertices[i][0] * vertices[(i + 1) % len(vertices)][1]
        - vertices[(i + 1) % len(vertices)][0] * vertices[i][1]
        for i in range(len(vertices))) / 2)


def source_points(reference, projection_index, stage):
    return [tuple(q(value) for value in point)
            for point in reference["layers"][stage]["projected_vertices"][projection_index]]


def exact_lattice_points(reference, projection_index, stage):
    layer = reference["layers"][stage]
    scale = reference["finite_game"]["state_scale"]
    coordinates = reference["projection_pairs"][projection_index]
    return {tuple(Fraction(state[index], scale) for index in coordinates)
            for state in layer["finite_states_scaled"]}


def h_vertices(shape):
    rows = [[q(value) for value in row] for row in shape["inequality_rows"]]
    bounds = [q(value) for value in shape["inequality_bounds"]]
    if shape["equality_rows"] or len(rows) < 3:
        raise ValueError("Only bounded inequality-only planar H sets are supported")
    normals_hull = hull([tuple(row) for row in rows if row != [0, 0]])
    origin = (Fraction(0), Fraction(0))
    if len(normals_hull) < 3 or any(
            cross(normals_hull[i], normals_hull[(i + 1) % len(normals_hull)], origin) <= 0
            for i in range(len(normals_hull))):
        raise ValueError("H output has a nontrivial recession direction and is unbounded")
    vertices = set()
    for i, j in itertools.combinations(range(len(rows)), 2):
        a, b = rows[i]
        c, d = rows[j]
        determinant = a * d - b * c
        if determinant == 0:
            continue
        x = (bounds[i] * d - b * bounds[j]) / determinant
        y = (a * bounds[j] - bounds[i] * c) / determinant
        if all(row[0] * x + row[1] * y <= bound
               for row, bound in zip(rows, bounds)):
            vertices.add((x, y))
    result = hull(vertices)
    if len(result) < 3:
        raise ValueError("H output did not define a bounded polygon")
    return result


def ellipse_contains(point, shape):
    center = [q(value) for value in shape["center"]]
    orientation = [[q(value) for value in row] for row in shape["orientation"]]
    radii = [q(value) for value in shape["radii"]]
    squared = Fraction(0)
    for row in range(2):
        projection = sum(orientation[row][column] * (point[column] - center[column])
                         for column in range(2))
        if radii[row] == 0:
            if projection != 0:
                return False
        else:
            squared += projection * projection / (radii[row] * radii[row])
    return squared <= 1


def zonotope_vertices(shape):
    center = [q(value) for value in shape["center"]]
    rows = [[q(value) for value in row] for row in shape["generators"]]
    if len(rows) != 2 or len(shape["factors"]) != len(rows[0]):
        raise ValueError("Malformed planar zonotope output")
    points = set()
    for signs in itertools.product((-1, 1), repeat=len(rows[0])):
        points.add(tuple(center[row] + sum(signs[column] * rows[row][column]
                  for column in range(len(signs))) for row in range(2)))
    return hull(points)


def output_area(shape, vertices):
    kind = shape["kind"]
    if kind in {"v_polytope", "h_polytope", "zonotope"}:
        return float(polygon_area(vertices)), "exact_fraction"
    if kind == "directional_ellipsoid":
        orientation = [[float(value) for value in row] for row in shape["orientation"]]
        determinant = orientation[0][0] * orientation[1][1] - orientation[0][1] * orientation[1][0]
        if determinant == 0:
            return 0.0, "degenerate"
        return (math.pi * float(shape["radii"][0]) * float(shape["radii"][1])
                / abs(determinant), "floating_formula")
    raise ValueError(f"Unknown output representation: {kind}")


def sampled_support(shape, vertices, direction):
    kind = shape["kind"]
    if kind in {"v_polytope", "h_polytope"}:
        return max(float(direction[0] * point[0] + direction[1] * point[1])
                   for point in vertices)
    if kind == "zonotope":
        center = [q(value) for value in shape["center"]]
        rows = [[q(value) for value in row] for row in shape["generators"]]
        return float(direction[0] * center[0] + direction[1] * center[1]
            + sum(abs(direction[0] * rows[0][column] + direction[1] * rows[1][column])
                  for column in range(len(rows[0]))))
    if kind == "directional_ellipsoid":
        orientation = [[float(value) for value in row] for row in shape["orientation"]]
        radii = [float(value) for value in shape["radii"]]
        center = [float(value) for value in shape["center"]]
        det = orientation[0][0] * orientation[1][1] - orientation[0][1] * orientation[1][0]
        if det == 0:
            return float("nan")
        # Solve B^T y=d; then h_E(d)=d.c+sqrt(sum((r_i*y_i)^2)).
        y0 = (orientation[1][1] * float(direction[0])
              - orientation[1][0] * float(direction[1])) / det
        y1 = (-orientation[0][1] * float(direction[0])
              + orientation[0][0] * float(direction[1])) / det
        return (float(direction[0]) * center[0] + float(direction[1]) * center[1]
                + math.hypot(radii[0] * y0, radii[1] * y1))
    raise ValueError(f"Unknown support representation: {kind}")


def support_diagnostics(points, shape, vertices):
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (1, -1), (2, 1), (1, 2))
    gaps = []
    for direction in directions:
        exact = max(float(direction[0] * point[0] + direction[1] * point[1])
                    for point in points)
        approximate = sampled_support(shape, vertices, direction)
        gaps.append({"direction": list(direction), "support_gap": approximate - exact})
    return gaps


def exact_lattice_inclusion(reference, stage, projection_index, shape, kind,
                            source_zonotope=None):
    points = exact_lattice_points(reference, projection_index, stage)
    exact_hull = hull(points)
    if kind == "v_polytope":
        output_vertices = hull([tuple(q(value) for value in point)
                                for point in shape["vertices"]])
        contained = [contains_convex(point, output_vertices) for point in points]
    elif kind == "h_polytope":
        rows = [[q(value) for value in row] for row in shape["inequality_rows"]]
        bounds = [q(value) for value in shape["inequality_bounds"]]
        contained = [all(row[0] * point[0] + row[1] * point[1] <= bound
                         for row, bound in zip(rows, bounds)) for point in points]
    elif kind == "directional_ellipsoid":
        contained = [ellipse_contains(point, shape) for point in points]
    elif kind == "zonotope":
        output_vertices = zonotope_vertices(shape)
        contained = [contains_convex(point, output_vertices) for point in points]
    else:
        raise ValueError(f"Unsupported exact-lattice output kind: {kind}")
    excluded = sum(not item for item in contained)
    result = {
        "reference": "exact rational projections of scale-2000 integer lattice states",
        "projected_finite_points": len(points),
        "exact_lattice_hull_vertices": len(exact_hull),
        "excluded_finite_points": excluded,
        "outer_inclusion": excluded == 0,
    }
    if source_zonotope is not None:
        source_vertices = zonotope_vertices(source_zonotope)
        source_excluded = sum(not contains_convex(point, source_vertices) for point in points)
        result["padded_source_excluded_points"] = source_excluded
        result["padded_source_contains_exact_lattice"] = source_excluded == 0
    return result


def verify_result(reference, stage, projection_index, method_result):
    points = source_points(reference, projection_index, stage)
    outcome = method_result["result"]
    if outcome.get("status") != "completed":
        raise ValueError(f"Method {method_result['method']} did not complete")
    shape = outcome["shape"]
    kind = shape["kind"]
    expected_shapes = {
        "exact-polytope-quickhull": ("v_polytope", "equivalent"),
        "axis-box": ("h_polytope", "outer"),
        "rotated-parallelotope": ("h_polytope", "outer"),
        "directional-ellipsoid": ("directional_ellipsoid", "outer"),
        "zonotope-axis-cover": ("zonotope", "outer"),
    }
    if method_result["method"] not in expected_shapes:
        raise ValueError(f"Unrecognized comparison method: {method_result['method']}")
    expected_kind, expected_direction = expected_shapes[method_result["method"]]
    if kind != expected_kind or outcome.get("direction") != expected_direction:
        raise ValueError("Method output representation or set direction contradicts its record")
    if kind == "v_polytope":
        output_vertices = hull([tuple(q(value) for value in point)
                                for point in shape["vertices"]])
        if not output_vertices or not all(contains_convex(point, output_vertices) for point in points):
            raise ValueError("Exact QuickHull output omitted a reference point")
        if any(point not in points for point in output_vertices):
            raise ValueError("Exact QuickHull introduced a point outside its input vertices")
        relation = "equivalent"
    elif kind == "h_polytope":
        if outcome.get("direction") != "outer":
            raise ValueError("H outer enclosure direction was mislabeled")
        output_vertices = h_vertices(shape)
        if not all(all(row[0] * point[0] + row[1] * point[1] <= bound
                       for row, bound in zip(
                           [[q(value) for value in row] for row in shape["inequality_rows"]],
                           [q(value) for value in shape["inequality_bounds"]]))
                   for point in points):
            raise ValueError("A reference vertex is outside the H outer enclosure")
        relation = "outer"
    elif kind == "directional_ellipsoid":
        if outcome.get("direction") != "outer":
            raise ValueError("Ellipsoid outer enclosure direction was mislabeled")
        if not all(ellipse_contains(point, shape) for point in points):
            raise ValueError("A reference vertex is outside the ellipsoid")
        output_vertices = []
        relation = "outer"
    elif kind == "zonotope":
        if outcome.get("direction") != "outer":
            raise ValueError("Zonotope outer enclosure direction was mislabeled")
        output_vertices = zonotope_vertices(shape)
        if not all(contains_convex(point, output_vertices) for point in points):
            raise ValueError("A reference vertex is outside the zonotope")
        source = outcome.get("source_zonotope")
        if source is None or source.get("outer_padding_factor", 1.0) <= 1.0:
            raise ValueError("Zonotope cover omitted its outward-rounded source proof data")
        source_vertices = zonotope_vertices(source)
        if not all(contains_convex(point, source_vertices) for point in points):
            raise ValueError("A reference vertex is outside the padded source zonotope")
        if not all(contains_convex(vertex, output_vertices) for vertex in source_vertices):
            raise ValueError("The axis-cover output omitted a source-zonotope corner")
        relation = "outer"
    else:
        raise ValueError(f"Unsupported shape kind: {kind}")
    area, area_assurance = output_area(shape, output_vertices)
    reference_area = float(polygon_area(hull(points)))
    support_gaps = support_diagnostics(points, shape, output_vertices)
    lattice_check = exact_lattice_inclusion(reference, stage, projection_index, shape, kind,
        outcome.get("source_zonotope"))
    if kind == "h_polytope":
        representation_size = len(shape["inequality_rows"]) + len(shape["equality_rows"])
    elif kind == "zonotope":
        representation_size = len(shape["factors"])
    elif kind == "v_polytope":
        representation_size = len(output_vertices)
    else:
        representation_size = 1
    return {
        "method": method_result["method"],
        "status": "verified",
        "relation": relation,
        "reference_vertices_checked": len(points),
        "output_size_primitives": representation_size,
        "reference_area": reference_area,
        "output_area": area,
        "area_ratio": area / reference_area if reference_area else None,
        "area_assurance": area_assurance,
        "exact_lattice_diagnostic": lattice_check,
        "support_diagnostics": support_gaps,
        "elapsed_ns": method_result.get("elapsed_ns"),
        "independent_oracle": "exact dyadic arithmetic over stored binary64 points and output coefficients",
    }


def checked_attempt(reference, stage, projection_index, method_result):
    try:
        return verify_result(reference, stage, projection_index, method_result)
    except (KeyError, TypeError, ValueError) as error:
        return {
            "method": method_result.get("method", "unknown"),
            "status": "verification_failed",
            "claimed_direction": method_result.get("result", {}).get("direction"),
            "reason": str(error),
        }


def check(reference, run):
    if run.get("schema") != "csl.exp03-two-points-approximation-run/1":
        raise ValueError("Unexpected approximation run schema")
    if run["reference_source_figure_data_sha256"] != reference["source_figure_data_sha256"]:
        raise ValueError("Approximation run is bound to a different source figure record")
    stage = run["stage"]
    if stage != len(reference["layers"]) - 1:
        raise ValueError("Run does not use the final saved forward layer")
    expected_pairs = reference["projection_pairs"]
    if len(run["projections"]) != len(expected_pairs):
        raise ValueError("Run omitted a requested projection")
    checked = []
    method_names = {"exact-polytope-quickhull", "axis-box", "rotated-parallelotope",
                    "directional-ellipsoid", "zonotope-axis-cover"}
    for index, projection in enumerate(run["projections"]):
        if projection["coordinate_indices"] != expected_pairs[index]:
            raise ValueError("Projection coordinates changed from the input manifest")
        expected_count = len(source_points(reference, index, stage))
        if projection["input_point_count"] != expected_count:
            raise ValueError("Registered projection did not preserve the reference point count")
        observed_points = {tuple(q(value) for value in point)
                           for point in projection["input_points"]}
        if observed_points != set(source_points(reference, index, stage)):
            raise ValueError("Registered projection changed a projected source coordinate")
        methods = projection["methods"]
        names = [item["method"] for item in methods]
        expected_methods = {"exact-polytope-quickhull", "axis-box", "rotated-parallelotope",
                            "directional-ellipsoid", "zonotope-axis-cover"}
        if len(names) != len(expected_methods) or set(names) != expected_methods:
            raise ValueError("Comparison output omitted or duplicated a method")
        checked.extend(checked_attempt(reference, stage, index, item) for item in methods)
    if run.get("inner_methods") is None:
        raise ValueError("Run must state whether inner methods were requested")
    measurement_checks = []
    measurement_coverage = {"status": "not_measured", "expected_calls": 0,
                            "observed_calls": 0, "count_mismatches": []}
    if run["measurement_policy"].get("measured_repetitions_per_method"):
        expected_call_count = len(expected_pairs) * len(method_names) * 8
        measurement_coverage = {
            "status": "complete" if len(run["measurements"]) == expected_call_count else "incomplete",
            "expected_calls": expected_call_count,
            "observed_calls": len(run["measurements"]),
            "count_mismatches": [],
        }
        counts = {}
        for measurement in run["measurements"]:
            projection_index = measurement["projection_index"]
            method = measurement["method"]
            phase = measurement["phase"]
            key = (projection_index, method, phase)
            counts[key] = counts.get(key, 0) + 1
            attempt = {"method": method, "result": measurement.get("result", {})}
            if measurement.get("status") != "completed" or "result" not in measurement:
                reason = measurement.get("result", {}).get("reason")
                verified = {"status": "call_failed",
                    "reason": reason or json.dumps(measurement.get("result", {}), sort_keys=True)}
            else:
                verified = checked_attempt(reference, stage, projection_index, attempt)
            valid_time = phase != "measured" or measurement.get("elapsed_ns", -1) >= 0
            measurement_checks.append({
                "projection_index": projection_index, "method": method,
                "phase": phase, "status": verified["status"],
                "relation": verified.get("relation"),
                "reference_vertices_checked": verified.get("reference_vertices_checked"),
                "exact_lattice_excluded_points": verified.get("exact_lattice_diagnostic", {}).get("excluded_finite_points"),
                "exact_lattice_source_excluded_points": verified.get("exact_lattice_diagnostic", {}).get("padded_source_excluded_points"),
                "elapsed_ns_valid": valid_time,
                "reason": verified.get("reason") or (None if valid_time else "invalid elapsed_ns"),
                "call_outcome": (measurement.get("result")
                    if measurement.get("status") != "completed" else None),
            })
        for projection_index in range(len(expected_pairs)):
            for method in method_names:
                observed_warmups = counts.get((projection_index, method, "warmup"), 0)
                observed_measured = counts.get((projection_index, method, "measured"), 0)
                if observed_warmups != 1 or observed_measured != 7:
                    measurement_coverage["count_mismatches"].append({
                        "projection_index": projection_index, "method": method,
                        "expected_warmups": 1, "observed_warmups": observed_warmups,
                        "expected_measured": 7, "observed_measured": observed_measured,
                    })
        if measurement_coverage["count_mismatches"]:
            measurement_coverage["status"] = "incomplete"
    verification_complete = (
        all(item["status"] == "verified" for item in checked)
        and all(item["status"] == "verified" and item["elapsed_ns_valid"]
                for item in measurement_checks)
        and measurement_coverage["status"] in {"complete", "not_measured"}
    )
    return {"schema": "csl.exp03-two-points-approximation-check/1",
        "status": "verified" if verification_complete else "incomplete",
        "case_id": run["case_id"], "stage": stage,
        "reference_source_figure_data_sha256": run["reference_source_figure_data_sha256"],
        "oracle": ("complete inclusion against the stored binary64 projected reference, "
            "exact rational checks against every scale-2000 lattice point"),
        "results": checked, "measurement_call_checks": measurement_checks,
        "measurement_coverage": measurement_coverage}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(json.loads(args.reference.read_text()), json.loads(args.run.read_text()))
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if result["status"] != "verified":
        raise SystemExit("Independent checks found failed or incomplete comparison outcomes")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently check EXP-03 phase-plane set relations and areas."""

from __future__ import annotations

import argparse
from fractions import Fraction
import itertools
import json
import math
from math import isqrt
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


def verify_finite_minimax(reference):
    game = reference["finite_game"]
    scale = game["state_scale"]
    horizon = game["horizon_steps"]
    codes = tuple(game["control_codes"])
    initial = (9_000, 0, 0, 0)

    def terminal(sequence, control_component):
        state = initial
        for code in sequence:
            if control_component:
                p1, _, p2, v2 = state
                state = (p1 + state[1] // 100 + 450 * code, 5_000 * code,
                         p2 + v2 // 10, v2)
            else:
                p1, v1, p2, v2 = state
                state = (p1 + v1 // 100, v1,
                         p2 + v2 // 10 + 9 * code, v2 + 200 * code)
        return state

    sequences = list(itertools.product(codes, repeat=horizon))
    controls = [{"codes": list(sequence), "terminal_state_scaled": list(terminal(sequence, True))}
                for sequence in sequences]
    disturbances = [{"codes": list(sequence), "terminal_state_scaled": list(terminal(sequence, False))}
                    for sequence in sequences]
    if controls != game["control_terminal_outcomes"] or disturbances != game["disturbance_terminal_outcomes"]:
        raise ValueError("Stored control/disturbance outcomes differ from independent finite replay")
    scored = []
    for control in controls:
        p1 = control["terminal_state_scaled"][0]
        worst = max((p1 - disturbance["terminal_state_scaled"][2]) ** 2
                    for disturbance in disturbances)
        scored.append((worst, control["codes"]))
    value = min(score for score, _ in scored)
    expected_sequences = [sequence for score, sequence in scored if score == value]
    claim = game["finite_minimax_reference"]
    if (claim["value_numerator"] != value or claim["value_denominator"] != scale * scale or
            claim["minimizing_control_sequences_codes"] != expected_sequences):
        raise ValueError("Saved finite minimax value or minimizing controls differ from exhaustive oracle")
    selected_control = expected_sequences[0]
    control_position = next(item["terminal_state_scaled"][0] for item in controls
                            if item["codes"] == selected_control)
    worst_sequences = [item["codes"] for item in disturbances
                       if (control_position - item["terminal_state_scaled"][2]) ** 2 == value]
    selected_disturbance = worst_sequences[0]
    state = initial
    path = [list(initial)]
    for control, disturbance in zip(selected_control, selected_disturbance):
        p1, v1, p2, v2 = state
        state = (p1 + v1 // 100 + 450 * control, 5_000 * control,
                 p2 + v2 // 10 + 9 * disturbance, v2 + 200 * disturbance)
        path.append(list(state))
    witness = claim["achievable_policy_witness"]
    if (witness.get("control_sequence_codes") != selected_control or
            witness.get("control_sequence") != [2.5 * code for code in selected_control] or
            witness.get("worst_disturbance_sequences_codes") != worst_sequences or
            witness.get("selected_worst_disturbance_sequence_codes") != selected_disturbance or
            witness.get("state_path_scaled") != path or
            witness.get("terminal_gap_numerator") != path[-1][0] - path[-1][2] or
            witness.get("objective_value_numerator") != value or
            witness.get("objective_value_denominator") != scale * scale):
        raise ValueError("Stored realizable minimax control/disturbance witness failed exact replay")
    return claim


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


def ellipsoid_x_bounds(shape, precision_bits=64):
    center = [q(value) for value in shape["center"]]
    orientation = [[q(value) for value in row] for row in shape["orientation"]]
    radii = [q(value) for value in shape["radii"]]
    determinant = orientation[0][0] * orientation[1][1] - orientation[0][1] * orientation[1][0]
    if determinant == 0:
        raise ValueError("Cannot bound x projection of singular ellipsoid orientation")
    # Solve B^T y=e_x and evaluate sqrt(sum((r_i*y_i)^2)) exactly.
    y0 = orientation[1][1] / determinant
    y1 = -orientation[0][1] / determinant
    squared_radius = (radii[0] * y0) ** 2 + (radii[1] * y1) ** 2
    if squared_radius < 0:
        raise ValueError("Ellipsoid x support radius is invalid")
    scale = 1 << precision_bits
    scaled_square = squared_radius.numerator * scale * scale // squared_radius.denominator
    root_floor = isqrt(scaled_square)
    exact = Fraction(root_floor * root_floor, scale * scale) == squared_radius
    root_upper = Fraction(root_floor if exact else root_floor + 1, scale)
    return center[0] - root_upper, center[0] + root_upper


def shape_x_bounds(shape):
    kind = shape["kind"]
    if kind == "h_polytope":
        vertices = h_vertices(shape)
        return min(point[0] for point in vertices), max(point[0] for point in vertices)
    if kind == "v_polytope":
        vertices = hull([tuple(q(value) for value in point) for point in shape["vertices"]])
        if not vertices:
            raise ValueError("V output has no vertices")
        return min(point[0] for point in vertices), max(point[0] for point in vertices)
    if kind == "zonotope":
        vertices = zonotope_vertices(shape)
        return min(point[0] for point in vertices), max(point[0] for point in vertices)
    if kind == "directional_ellipsoid":
        return ellipsoid_x_bounds(shape)
    raise ValueError(f"Cannot bound objective from representation: {kind}")


def objective_bounds_for_method(method, control_result, disturbance_result, finite_game):
    control_outer_verified = (control_result.get("status") == "verified" and
        control_result.get("exact_lattice_diagnostic", {}).get("outer_inclusion") is True)
    disturbance_outer_verified = (disturbance_result.get("status") == "verified" and
        disturbance_result.get("exact_lattice_diagnostic", {}).get("outer_inclusion") is True)
    scale = finite_game["state_scale"]
    disturbance_positions = [Fraction(item["terminal_state_scaled"][2], scale)
                             for item in finite_game["disturbance_terminal_outcomes"]]
    if not disturbance_positions:
        raise ValueError("No exact finite disturbance outcomes are available")
    minimum_disturbance = min(disturbance_positions)
    maximum_disturbance = max(disturbance_positions)
    reference = finite_game["finite_minimax_reference"]
    exact_value = Fraction(reference["value_numerator"], reference["value_denominator"])
    results = {"method": method, "exact_finite_minimax_value": float(exact_value),
               "arithmetic": "exact fractions; ellipsoid projection uses a rational outward square-root enclosure"}

    if control_outer_verified:
        control_lower, control_upper = shape_x_bounds(control_result["_shape"])
        midpoint = (minimum_disturbance + maximum_disturbance) / 2
        relaxed_control = min(max(midpoint, control_lower), control_upper)
        relaxed_worst = max(abs(relaxed_control - minimum_disturbance),
                            abs(relaxed_control - maximum_disturbance))
        lower = relaxed_worst * relaxed_worst
        results["lower_bound"] = {
            "status": "verified" if lower <= exact_value else "incorrect",
            "value": float(lower), "value_fraction": f"{lower.numerator}/{lower.denominator}",
            "basis": "relax all finite control terminal positions to the checked outer x projection; keep the complete exact finite disturbance catalogue",
            "relaxed_control_position": float(relaxed_control),
            "control_outer_x_interval": [float(control_lower), float(control_upper)],
        }
    else:
        results["lower_bound"] = {
            "status": "inconclusive",
            "reason": ("this method's control-plane output excludes one or more exact finite-game lattice states"
                       if control_result.get("status") == "verified" else
                       "the control-plane approximation did not pass its independent set check"),
        }

    if disturbance_outer_verified:
        _, disturbance_upper = shape_x_bounds(disturbance_result["_shape"])
        disturbance_lower, _ = shape_x_bounds(disturbance_result["_shape"])
        minimizing_codes = reference["minimizing_control_sequences_codes"][0]
        control_outcome = next(item for item in finite_game["control_terminal_outcomes"]
                               if item["codes"] == minimizing_codes)
        control_position = Fraction(control_outcome["terminal_state_scaled"][0], scale)
        worst = max(abs(control_position - disturbance_lower),
                    abs(control_position - disturbance_upper))
        upper = worst * worst
        results["upper_bound"] = {
            "status": "verified" if upper >= exact_value else "incorrect",
            "value": float(upper), "value_fraction": f"{upper.numerator}/{upper.denominator}",
            "basis": "use an exactly enumerated feasible minimizing control sequence and maximize over the checked outer disturbance x projection",
            "control_sequence_codes": minimizing_codes,
            "control_sequence": [2.5 * code for code in minimizing_codes],
            "control_position": float(control_position),
            "disturbance_outer_x_interval": [float(disturbance_lower), float(disturbance_upper)],
            "realizable_policy_witness": reference["achievable_policy_witness"],
        }
    else:
        results["upper_bound"] = {
            "status": "inconclusive",
            "reason": ("this method's disturbance-plane output excludes one or more exact finite-game lattice states"
                       if disturbance_result.get("status") == "verified" else
                       "the disturbance-plane approximation did not pass its independent set check"),
        }
    if (results["lower_bound"]["status"] == "verified" and
            results["upper_bound"]["status"] == "verified" and
            results["lower_bound"]["value"] > results["upper_bound"]["value"]):
        raise ValueError(f"{method} objective bounds are inconsistent")
    return results


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
    checked_by_projection = []
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
        projection_checks = [checked_attempt(reference, stage, index, item) for item in methods]
        for check_result, method_result in zip(projection_checks, methods):
            if check_result.get("status") == "verified":
                check_result["_shape"] = method_result["result"]["shape"]
        checked_by_projection.append({item["method"]: item for item in projection_checks})
        checked.extend(projection_checks)
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
    finite_game = reference["finite_game"]
    exact_reference = verify_finite_minimax(reference)
    objective_bounds = [objective_bounds_for_method(
        method, checked_by_projection[0][method], checked_by_projection[1][method], finite_game)
        for method in sorted(method_names)]
    objective_bounds_verified = all(
        bound["lower_bound"]["status"] in {"verified", "inconclusive"} and
        bound["upper_bound"]["status"] in {"verified", "inconclusive"}
        for bound in objective_bounds)
    verification_complete = (
        all(item["status"] == "verified" for item in checked)
        and all(item["status"] == "verified" and item["elapsed_ns_valid"]
                for item in measurement_checks)
        and measurement_coverage["status"] in {"complete", "not_measured"}
        and objective_bounds_verified
    )
    return {"schema": "csl.exp03-two-points-approximation-check/1",
        "status": "verified" if verification_complete else "incomplete",
        "case_id": run["case_id"], "stage": stage,
        "reference_source_figure_data_sha256": run["reference_source_figure_data_sha256"],
        "oracle": ("complete inclusion against the stored binary64 projected reference, "
            "exact rational checks against every scale-2000 lattice point"),
        "results": checked, "finite_minimax_reference": exact_reference,
        "objective_bounds": objective_bounds,
        "objective_bounds_scope": (
            "bounds are for the finite open-loop min-control/max-disturbance terminal squared position gap; "
            "the state dynamics separate control and disturbance components, and both phase-plane exact-lattice "
            "inclusions are checked independently; inconclusive means the approximation is not an outer set "
            "for the exact source lattice"
        ),
        "objective_bounds_checks_complete": objective_bounds_verified,
        "measurement_call_checks": measurement_checks,
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

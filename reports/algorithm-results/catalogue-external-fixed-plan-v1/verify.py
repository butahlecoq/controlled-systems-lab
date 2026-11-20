"""Independently replay the finite disturbance words using exact stored binary64 inputs."""
import argparse
from collections import Counter
from fractions import Fraction as F
from itertools import combinations, product
import json
from math import sqrt
from pathlib import Path


def rational(vector):
    return list(map(F, vector))


def dot(left, right):
    return sum((a * b for a, b in zip(left, right, strict=True)), F(0))


def matrix(record):
    values = rational(record["row_major"])
    cols = record["columns"]
    assert len(values) == record["rows"] * cols
    return [values[i * cols : (i + 1) * cols] for i in range(record["rows"])]


def reference(record):
    state = rational(record["x0"])
    a = matrix(record["A"])
    b = matrix(record["B"])
    e = matrix(record["E"])
    offset = rational(record["offset"])
    disturbances = list(map(rational, record["disturbance_vertices"]))
    center = record["external_center"]
    active = [
        j for j in range(len(center)) if any(row[j] for row in e)
    ][:2]
    assert record["active_axes"] == active
    axes = active or [0]
    assert record["perturbed_axes"] == axes
    authored = [center]
    for j in axes:
        delta = 0.1 * max(1, abs(center[j]))
        for sign in (-1, 1):
            point = center.copy()
            point[j] += sign * delta
            authored.append(point)
    assert record["disturbance_vertices"] == authored

    stages = [[state]]
    for control in map(rational, record["controls"]):
        assert not any(control)
        stages.append([
            [
                dot(a_i, current) + dot(b_i, control) + dot(e_i, w) + c
                for a_i, b_i, e_i, c in zip(a, b, e, offset, strict=True)
            ]
            for current, w in product(stages[-1], disturbances)
        ])
    return stages


def directions(initial):
    n = len(initial)
    scale = [max(F(1), abs(F(x))) for x in initial]
    for i in range(n):
        for sign in (-1, 1):
            direction = [F(0)] * n
            direction[i] = sign / scale[i]
            yield direction
    for i, j in combinations(range(min(n, 4)), 2):
        for left, right in product((-1, 1), repeat=2):
            direction = [F(0)] * n
            direction[i] = left / scale[i]
            direction[j] = right / scale[j]
            yield direction


def support(family, stage, frame, direction):
    if family in {"box", "parallelotope"}:
        if family == "parallelotope":
            direction = [dot(column, direction) for column in zip(*frame, strict=True)]
        return sum(
            d * F(hi if d >= 0 else lo)
            for d, lo, hi in zip(direction, stage["lower"], stage["upper"], strict=True)
        ), F(0)
    base = dot(rational(stage["center"]), direction)
    if family == "ellipsoid":
        radius_square = sum((F(r) * d) ** 2 for r, d in zip(stage["radii"], direction, strict=True))
        return base, radius_square
    generators = matrix(stage["generators"])
    column_support = [abs(dot(column, direction)) for column in zip(*generators, strict=True)]
    return base + sum(column_support), F(0)



def inside(family, stage, frame, point):
    if family == "ellipsoid":
        square = F(0)
        for x, center, radius in zip(point, stage["center"], stage["radii"], strict=True):
            assert radius >= 0
            delta = x - F(center)
            if radius:
                square += (delta / F(radius)) ** 2
            elif delta:
                return False
        return square <= 1
    if family == "parallelotope":
        coordinates = point.copy()
        for i in reversed(range(len(point))):
            row = frame[i]
            assert not any(row[:i]) and row[i] != 0
            coordinates[i] = (
                coordinates[i] - dot(row[i + 1 :], coordinates[i + 1 :])
            ) / row[i]
        point = coordinates
    return all(F(lo) <= x <= F(hi) for x, lo, hi in
               zip(point, stage["lower"], stage["upper"], strict=True))


def relative_error(a, b):
    return float(abs(F(a) - b) / max(F(1), abs(b)))


def verify(path, prior):
    rows = list(map(json.loads, path.read_text().splitlines()))
    assert len(rows) == len({row["model_id"] for row in rows}) == 35
    baselines = json.loads(prior.read_text())["models"]
    prior_by_id = {record["model_id"]: record for record in baselines}
    assert len(baselines) == len(prior_by_id) == 35
    coverage = Counter()
    zero_external = []
    audit = []
    for row in rows:
        model = row["model_id"]
        before = prior_by_id[model]
        for key in ("x0", "A", "B", "E", "source_sha256", "dt"):
            assert before[key] == row[key], (model, key)
        assert before["c"] == row["offset"]
        assert before["external"] == row["external_center"]
        expected = reference(row)
        if not row["active_axes"]:
            zero_external.append(model)
            assert all(x == stage[0] for stage in expected for x in stage)
        reference_result = row["outcomes"]["polytope"]
        families = {}
        for family, outcome in row["outcomes"].items():
            status = outcome["status"]
            coverage[family, status] += 1
            if status != "complete":
                families[family] = outcome
                continue
            assert len(outcome["stages"]) == len(expected)
            if family == "polytope":
                error = max(
                    relative_error(value, check)
                    for stage, oracle in zip(reference_result["stages"], expected, strict=True)
                    for vertex, wanted in zip(stage["points"], oracle, strict=True)
                    for value, check in zip(vertex, wanted, strict=True)
                )
                assert error < 1e-12, (model, error)
                families[family] = {"status": status, "max_scaled_point_error": error}
                continue

            frame = matrix(outcome["frame"]) if family == "parallelotope" else None
            queries = 0
            misses = 0
            max_scaled_deficit = 0.0
            vertex_checks = 0
            exterior_vertices = 0

            for stage, oracle in zip(outcome["stages"], expected, strict=True):
                if family != "zonotope":
                    vertex_checks += len(oracle)
                    exterior_vertices += sum(not inside(family, stage, frame, v) for v in oracle)
                for direction in directions(row["x0"]):
                    queries += 1
                    exact = max(dot(v, direction) for v in oracle)
                    bound, radius_square = support(family, stage, frame, direction)
                    difference = exact - bound
                    if difference > 0 and difference**2 > radius_square:
                        misses += 1
                        if radius_square:
                            deficit = float(difference) - sqrt(float(radius_square))
                            max_scaled_deficit = max(max_scaled_deficit, deficit / float(max(1, abs(exact))))
                        else:
                            max_scaled_deficit = max(max_scaled_deficit, float(difference / max(1, abs(exact))))
            families[family] = {
                "status": status,

                "all_vertex_checks": vertex_checks,
                "exterior_vertices": exterior_vertices,
                "sampled_direction_checks": queries,
                "exact_support_deficits": misses,
                "max_scaled_support_deficit": max_scaled_deficit,
            }
        audit.append({"model_id": model, "families": families})
    return {
        "schema": "csl.catalogue-external-fixed-plan-audit/1",
        "coverage": {f"{family}/{status}": count for (family, status), count in sorted(coverage.items())},
        "zero_external_maps": zero_external,
        "models": audit,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("prior_inputs", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.records, args.prior_inputs), indent=2, sort_keys=True))

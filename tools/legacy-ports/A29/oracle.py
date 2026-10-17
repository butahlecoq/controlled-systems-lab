"""Independent exact binary64 2D source-hull quality check for bounded fixtures.

This enumerates segments and triangles using Fraction arithmetic. It does not
use the A30 tableau helper or a modern hull implementation.
"""

from __future__ import annotations

import hashlib
import math
import struct
from fractions import Fraction


def manifest_digest(points: list[list[float]]) -> str:
    payload = bytearray(b"A29-row-wise-binary64-le/1")
    payload.extend(struct.pack("<Q", len(points)))
    for point in points:
        payload.extend(struct.pack("<Q", len(point)))
        for coordinate in point:
            payload.extend(struct.pack("<d", float(coordinate)))
    return hashlib.sha256(payload).hexdigest()


def _orientation(a: tuple, b: tuple, c: tuple) -> Fraction:
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _segment(point: tuple, a: tuple, b: tuple) -> bool:
    return (_orientation(a, b, point) == 0
            and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))


def _triangle(point: tuple, a: tuple, b: tuple, c: tuple) -> bool:
    area = _orientation(a, b, c)
    if area == 0:
        return False
    signs = (_orientation(a, b, point), _orientation(b, c, point),
             _orientation(c, a, point))
    return all(value >= 0 for value in signs) if area > 0 else all(value <= 0 for value in signs)


def _covered(point: tuple, vertices: list[tuple]) -> bool:
    for i, a in enumerate(vertices):
        if point == a:
            return True
        for j in range(i + 1, len(vertices)):
            b = vertices[j]
            if _segment(point, a, b):
                return True
            for k in range(j + 1, len(vertices)):
                if _triangle(point, a, b, vertices[k]):
                    return True
    return False


def check(input_points: list[list[float]], output_points: list[list[float]] | None,
          max_points: int = 64) -> dict:
    record = {"status": "inconclusive", "scope": "exact represented binary64 2D finite hull",
              "input_digest": None, "source_indices": None, "counterexample_index": None,
              "reason": ""}
    if output_points is None:
        record["reason"] = "algorithm did not produce a hull"
        return record
    if len(input_points) > max_points or len(output_points) > max_points:
        record["reason"] = "oracle point capacity exceeded"
        return record
    if any(len(point) != 2 or not all(math.isfinite(float(x)) for x in point)
           for point in input_points + output_points):
        record["reason"] = "unsupported dimension or nonfinite coordinate"
        return record
    record["input_digest"] = manifest_digest(input_points)
    source = {tuple(float(x) for x in point): i for i, point in reversed(list(enumerate(input_points)))}
    indices = []
    for point in output_points:
        key = tuple(float(x) for x in point)
        if key not in source:
            record.update(status="incorrect", reason="output point is absent from source manifest")
            return record
        index = source[key]
        if index in indices:
            record.update(status="incorrect", reason="duplicate source index",
                          counterexample_index=index)
            return record
        indices.append(index)
    record["source_indices"] = indices
    input_exact = [tuple(Fraction.from_float(float(x)) for x in point) for point in input_points]
    output_exact = [input_exact[index] for index in indices]
    for index, point in enumerate(input_exact):
        if not _covered(point, output_exact):
            record.update(status="incorrect", reason="input point lies outside reported convex hull",
                          counterexample_index=index)
            return record
    record.update(status="verified", reason="all input points covered by exact source hull")
    return record

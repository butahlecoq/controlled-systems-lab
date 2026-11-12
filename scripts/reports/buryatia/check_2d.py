#!/usr/bin/env python3
"""Check the source-qualified native 2D report and its independent reference."""

import argparse
import json
import math
import subprocess
from pathlib import Path


FAMILIES = {
    "exact_affine_polytope", "unreduced_zonotope", "reduced_zonotope",
    "parallelotope", "box", "ellipsoid",
}
SOURCE_SHA256 = "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"
REFERENCE_AREA = 4.619042908487405


def polygon_area(points):
    return abs(sum(points[i][0] * points[(i + 1) % len(points)][1]
                   - points[i][1] * points[(i + 1) % len(points)][0]
                   for i in range(len(points))) / 2.0) if len(points) > 2 else 0.0


def validate(record):
    assert record["schema"] == "csl.buryatia.recursive-approximation/1"
    assert record["case_id"] == "buryatia-volterra-matlab-literal-affine/1"
    assert record["source_sha256"] == SOURCE_SHA256
    assert record["intervals"] == 60
    assert record["source_index_checker_budget"] == {"wall_ms": 30000, "max_points": 4096}
    rows = record["records"]
    assert len(rows) == 61 * len(FAMILIES)
    assert {row["family"] for row in rows} == FAMILIES
    assert {row["stage"] for row in rows} == set(range(61))
    assert all(row["status"] == "completed" for row in rows)
    for row in rows:
        assert len(row["rendering_vertices"]) > 0
        assert math.isfinite(row["area"])
        assert math.isfinite(row["max_abs_support_error_8_directions"])
    terminal = {row["family"]: row for row in rows if row["stage"] == 60}
    exact = terminal["exact_affine_polytope"]
    exact_area = polygon_area(exact["rendering_vertices"])
    assert exact["vertex_count"] == 120
    assert abs(exact_area - REFERENCE_AREA) <= 1e-9
    assert abs(exact["area"] - exact_area) <= 1e-10
    assert terminal["unreduced_zonotope"]["generator_count"] == 60
    assert terminal["reduced_zonotope"]["generator_count"] <= 8
    for family in ("box", "parallelotope", "reduced_zonotope"):
        assert all("registered" in row["containment_check"]
                   for row in rows if row["family"] == family and row["stage"] > 0)
    assert all(any(call.get("operation") == "factor-outer-minkowski-sum" and
                   call.get("implementation") == "csl.geometry.ellipsoidal.factor-minkowski/1"
                   for call in row["module_invocations"])
               for row in rows if row["family"] == "ellipsoid" and row["stage"] > 0)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--record-out", type=Path)
    args = parser.parse_args()
    if bool(args.exe) == bool(args.raw):
        raise SystemExit("provide exactly one of --exe or --raw")
    if args.exe:
        try:
            completed = subprocess.run([str(args.exe), "--volterra-2d"], check=True,
                                       capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            raise SystemExit(f"native report refused: {error.stderr.strip()}") from error
        record = json.loads(completed.stdout)
    else:
        record = json.loads(args.raw.read_text(encoding="utf-8"))
    record = validate(record)
    if args.record_out:
        args.record_out.parent.mkdir(parents=True, exist_ok=True)
        args.record_out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("validated 61 stages × six native tracks; terminal affine hull: 120 vertices, area 4.619042908487405")


if __name__ == "__main__":
    main()

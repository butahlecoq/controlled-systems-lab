#!/usr/bin/env python3
"""Check the source-qualified native 2D report and its independent reference."""

import argparse
import hashlib
import json
import math
import platform
import re
import subprocess
from pathlib import Path


FAMILIES = {
    "exact_affine_polytope", "unreduced_zonotope", "reduced_zonotope",
    "parallelotope", "box", "ellipsoid",
}
SOURCE_SHA256 = "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"
REFERENCE_AREA = 4.619042908487405
ROOT = Path(__file__).resolve().parents[3]
IMPLEMENTATION_SOURCES = (
    "benchmarks/reporting/buryatia/driver.cpp",
    "benchmarks/reporting/buryatia/ellipse_boundary.hpp",
    "scripts/reports/buryatia/check_2d.py",
    "scripts/reports/buryatia/render_2d.py",
    "include/csl/geometry/ellipsoidal.hpp",
    "src/geometry/approximation/ellipsoidal_set.cpp",
    "src/geometry/approximation/ellipsoidal.cpp",
    "src/geometry/approximation/policy.cpp",
    "src/geometry/affine_sum.cpp",
    "src/geometry/source_index_hull.cpp",
    "src/geometry/bounded_hull_checker.cpp",
    "src/geometry/hull/quickhull_2d.cpp",
    "src/geometry/generators/generator_sets.cpp",
    "src/geometry/generators/adapter.cpp",
    "src/geometry/approximation/box_parallelotope.cpp",
    "src/geometry/approximation/zonotope.cpp",
)


def polygon_area(points):
    return abs(sum(points[i][0] * points[(i + 1) % len(points)][1]
                   - points[i][1] * points[(i + 1) % len(points)][0]
                   for i in range(len(points))) / 2.0) if len(points) > 2 else 0.0


def ellipse_contains(ellipse, point):
    center = ellipse["center"]
    columns = ellipse["factor_columns"]
    values = ellipse["factor_row_major"]
    assert ellipse["kind"] == "factor_ellipsoid"
    assert ellipse["factor_rows"] == 2
    assert len(center) == 2 and len(values) == 2 * columns
    q00 = sum(values[column] ** 2 for column in range(columns))
    q01 = sum(values[column] * values[columns + column] for column in range(columns))
    q11 = sum(values[columns + column] ** 2 for column in range(columns))
    spread = math.hypot(q00 - q11, 2 * q01)
    major2 = max(0.0, (q00 + q11 + spread) / 2)
    minor2 = max(0.0, (q00 + q11 - spread) / 2)
    angle = 0.5 * math.atan2(2 * q01, q00 - q11)
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - center[0], point[1] - center[1]
    along_major = dx * c + dy * s
    along_minor = -dx * s + dy * c
    scale = max(1.0, math.sqrt(major2))
    if minor2 <= 1e-24 * scale * scale:
        return (abs(along_minor) <= 1e-9 * scale and
                along_major * along_major <= major2 + 1e-9 * scale * scale)
    return along_major * along_major / major2 + along_minor * along_minor / minor2 <= 1 + 1e-9


def native_receipt(exe, cmake_cache):
    cache = {}
    if cmake_cache:
        for line in cmake_cache.read_text(encoding="utf-8").splitlines():
            if line.startswith(("CMAKE_CXX_COMPILER:", "CMAKE_CXX_COMPILER_ID:",
                                "CMAKE_CXX_COMPILER_VERSION:", "CMAKE_BUILD_TYPE:",
                                "CMAKE_GENERATOR:", "CMAKE_CXX_FLAGS:", "CMAKE_CXX_FLAGS_RELEASE:")):
                key, value = line.split("=", 1)
                cache[key.split(":", 1)[0]] = value
        compiler_files = sorted(cmake_cache.parent.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
        if compiler_files:
            compiler_text = compiler_files[0].read_text(encoding="utf-8")
            for name in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION"):
                found = re.search(rf'^set\({name} "([^"]*)"\)$', compiler_text, re.MULTILINE)
                if found:
                    cache[name] = found.group(1)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    return {
        "git_revision": revision,
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "platform": platform.platform(),
        "compiler_and_configuration": cache,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in IMPLEMENTATION_SOURCES
        },
    }


def validate(record, *, require_current_sources=False):
    """Check declared producer blobs; fresh captures must also match current HEAD."""
    assert record["schema"] == "csl.buryatia.recursive-approximation/2"
    assert record["case_id"] == "buryatia-volterra-matlab-literal-affine/1"
    assert record["source_sha256"] == SOURCE_SHA256
    superseded = record["supersedes"]
    assert superseded["schema"] == "csl.buryatia.recursive-approximation/1"
    old_path = ROOT / "docs/examples/buryatia-volterra-affine-2d-records-superseded-v1.json"
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == superseded["records_sha256"]
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
        if row["family"] == "ellipsoid":
            ellipse = row["represented_set"]
            assert ellipse is not None
            assert ellipse["factor_columns"] == row["generator_count"]
            assert all(ellipse_contains(ellipse, point) for point in row["rendering_vertices"])
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
    ellipse_terminal = terminal["ellipsoid"]
    ellipse = ellipse_terminal["represented_set"]
    direction = (1.0, 1.0)
    factor_support = math.sqrt(sum(
        (direction[0] * ellipse["factor_row_major"][column] +
         direction[1] * ellipse["factor_row_major"][ellipse["factor_columns"] + column]) ** 2
        for column in range(ellipse["factor_columns"])))
    actual_support = sum(direction[i] * ellipse["center"][i] for i in range(2)) + factor_support
    drawn_support = max(sum(direction[i] * point[i] for i in range(2))
                        for point in ellipse_terminal["rendering_vertices"])
    assert abs(actual_support - 6.1446607192856675) <= 1e-9
    assert drawn_support <= actual_support + 1e-9
    assert record.get("native_build", {}).get("source_sha256")
    assert record["native_build"].get("executable_sha256")
    assert set(record["native_build"]["source_sha256"]) == set(IMPLEMENTATION_SOURCES)
    receipt = record["native_build"]
    revision = receipt["git_revision"]
    for name, digest in receipt["source_sha256"].items():
        committed = subprocess.run(["git", "show", f"{revision}:{name}"], cwd=ROOT,
                                   check=True, capture_output=True).stdout
        assert hashlib.sha256(committed).hexdigest() == digest
    if require_current_sources:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
        assert revision == head
        current_hashes = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in IMPLEMENTATION_SOURCES
        }
        assert receipt["source_sha256"] == current_hashes
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--record-out", type=Path)
    parser.add_argument("--cmake-cache", type=Path)
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
        record["native_build"] = native_receipt(args.exe, args.cmake_cache)
    else:
        record = json.loads(args.raw.read_text(encoding="utf-8"))
    record = validate(record, require_current_sources=bool(args.exe))
    if args.record_out:
        args.record_out.parent.mkdir(parents=True, exist_ok=True)
        args.record_out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("validated 61 stages × six native tracks; terminal affine hull: 120 vertices, area 4.619042908487405")


if __name__ == "__main__":
    main()

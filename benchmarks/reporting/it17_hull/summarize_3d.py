#!/usr/bin/env python3
"""Validate and render the bounded EXP-02 3D hull pilot."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
from fractions import Fraction
from pathlib import Path

METHODS = [
    "lp-membership-baseline",
    "basis-reuse-related-to-A43",
    "ordered-membership-related-to-A44",
    "A43-certificate-safe-basis-adaptation",
    "A44-incremental-LP-farthest-seed",
    "geometric-quickhull",
]
SCHEMA = "csl.exp02-hull-3d-row/1"


def halton(index: int, base: int) -> float:
    value, fraction = 0.0, 1.0 / base
    while index:
        value += (index % base) * fraction
        index //= base
        fraction /= base
    return value


def fixture_points() -> list[tuple[float, float, float]]:
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
              (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    index = 1
    while len(points) < 250:
        weights = [1 + math.floor(5 * halton(index, base)) for base in (2, 3, 5)]
        index += 1
        if sum(weights) <= 7:
            points.append(tuple(weight / 8.0 for weight in weights))
    return points


def read_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("raw input has no observations")
    if any(row.get("schema") != SCHEMA or row.get("dimension") != 3 or
           row.get("fixture") != "exp02-simplex-halton-interior-3d-n250" or
           row.get("input_points") != 250 for row in rows):
        raise ValueError("schema, dimension, or fixture size mismatch")
    commits = {row["source_commit"] for row in rows}
    hashes = {row["input_sha256"] for row in rows}
    if len(commits) != 1 or len(hashes) != 1:
        raise ValueError("rows do not share one source commit and input")
    methods = {row["method"] for row in rows}
    if methods != set(METHODS):
        raise ValueError(f"method coverage mismatch: {sorted(methods)}")
    if any(row["method"] == "geometric-quickhull" and
           (row["outcome"] != "unsupported_dimension" or row["elapsed_ns"] != 0)
           for row in rows):
        raise ValueError("3D QuickHull rows must remain unsupported and untimed")
    points = fixture_points()
    for row in rows:
        if row["method"] == "geometric-quickhull":
            row["independent_hull_check"] = None
            continue
        row["independent_hull_check"] = exact_hull_certificate(row, points)
        row["outcome"] = "verified" if row["independent_hull_check"] else "invalid_certificate_chain"
    for method in METHODS[:-1]:
        attempts = [row for row in rows if row["method"] == method]
        warmups = [row for row in attempts if row["warmup"]]
        measured = [row for row in attempts if not row["warmup"]]
        if len(warmups) != 1 or len(measured) < 5:
            raise ValueError(f"{method}: expected one warmup and at least five measured attempts")
    return rows


def exact_hull_certificate(row: dict, points: list[tuple[float, float, float]]) -> bool:
    retained = row.get("retained_ids")
    certificates = row.get("removal_certificates")
    if not isinstance(retained, list) or not isinstance(certificates, list):
        return False
    if len(retained) != row.get("retained") or len(certificates) != row.get("removed"):
        return False
    if not retained or len(set(retained)) != len(retained) or any(not isinstance(i, int) or not 0 <= i < len(points) for i in retained):
        return False
    retained_set = set(retained)
    if not set(range(4)).issubset(retained_set):
        return False
    positions: dict[int, int] = {}
    for index, certificate in enumerate(certificates):
        point = certificate.get("removed")
        if not isinstance(point, int) or not 0 <= point < len(points) or point in retained_set or point in positions:
            return False
        positions[point] = index
    if retained_set | set(positions) != set(range(len(points))) or retained_set & set(positions):
        return False
    for index, certificate in enumerate(certificates):
        target_id = certificate["removed"]
        terms = certificate.get("terms")
        if not isinstance(terms, list) or not terms:
            return False
        weight_sum = Fraction(0)
        reconstructed = [Fraction(0), Fraction(0), Fraction(0)]
        for term in terms:
            if not isinstance(term, list) or len(term) != 2:
                return False
            support_id, weight_text = term
            if not isinstance(support_id, int) or not 0 <= support_id < len(points) or support_id == target_id:
                return False
            if support_id in positions and positions[support_id] <= index:
                return False
            try:
                weight_float = float.fromhex(weight_text)
            except (TypeError, ValueError):
                return False
            if not math.isfinite(weight_float) or weight_float < 0.0:
                return False
            weight = Fraction.from_float(weight_float)
            weight_sum += weight
            for coordinate in range(3):
                reconstructed[coordinate] += weight * Fraction.from_float(points[support_id][coordinate])
        if weight_sum != 1 or reconstructed != [Fraction.from_float(x) for x in points[target_id]]:
            return False
    return True


def plot_svg() -> str:
    pts = fixture_points()
    planes = [(0, 1, "x₁", "x₂"), (0, 2, "x₁", "x₃"), (1, 2, "x₂", "x₃")]
    width, height, panel_w, panel_h = 960, 350, 290, 270
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
             '<title>250-point tetrahedron with Halton-generated dyadic interior points in three projections</title>',
             '<desc>Scatter plots show input points only; no projected hull boundary is implied.</desc>',
             '<style>text{font:13px system-ui,sans-serif;fill:#172438}.axis{stroke:#56657a;stroke-width:1}.pt{fill:#4f65b5;fill-opacity:.52}.corner{fill:#c74b42;stroke:white;stroke-width:1}</style>']
    for p, (a, b, xlabel, ylabel) in enumerate(planes):
        ox, oy, plot_w, plot_h = 30 + p * 315, 36, panel_w - 45, panel_h - 48
        parts.append(f'<text x="{ox}" y="20">Projection {xlabel}–{ylabel}</text>')
        parts.append(f'<path class="axis" d="M{ox},{oy + plot_h}H{ox + plot_w} M{ox},{oy}V{oy + plot_h}"/>')
        parts.append(f'<text x="{ox + plot_w / 2}" y="{oy + plot_h + 30}" text-anchor="middle">{xlabel}</text>')
        parts.append(f'<text x="{ox}" y="{oy + plot_h + 44}">0</text><text x="{ox + plot_w}" y="{oy + plot_h + 44}" text-anchor="end">1</text>')
        for point_id, point in enumerate(pts):
            xx = ox + point[a] * plot_w
            yy = oy + (1 - point[b]) * plot_h
            marker = "corner" if point_id < 4 else "pt"
            parts.append(f'<circle class="{marker}" cx="{xx:.2f}" cy="{yy:.2f}" r="{4 if point_id < 4 else 2}"/>')
    parts.append('<text x="480" y="340" text-anchor="middle">Tetrahedron corners plus dyadic interior points from Halton bases 2, 3, 5; input projections only.</text>')
    parts.append('</svg>')
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows(args.raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "validated-rows.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    with (args.output_dir / "summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["method", "warmups", "measured", "independently_verified", "reducer_complete", "retained_median", "elapsed_median_ms", "elapsed_min_ms", "elapsed_max_ms", "performance_verdict"])
        for method in METHODS:
            group = [r for r in rows if r["method"] == method]
            measured = [r for r in group if not r["warmup"]]
            if method == "geometric-quickhull":
                writer.writerow([method, len(group), 0, 0, "n/a", "n/a", "", "", "", "unsupported in 3D"])
                continue
            valid = (len(measured) >= 5 and
                     all(r["outcome"] == "verified" and r["reducer_status_complete"] is True
                         for r in measured))
            values = [r["elapsed_ns"] / 1e6 for r in measured] if valid else []
            complete = sum(r["reducer_status_complete"] is True for r in measured)
            verified = sum(r["outcome"] == "verified" for r in measured)
            verdict = ("descriptive only; no speedup claim; source limiter not profiled" if valid
                       else "timing withheld: incomplete or failed reducer; no performance comparison")
            writer.writerow([method, sum(r["warmup"] for r in group), len(measured), f"{verified}/{len(measured)}", f"{complete}/{len(measured)}", f"{statistics.median(r['retained'] for r in measured):g}" if valid else "", f"{statistics.median(values):.6f}" if valid else "", f"{min(values):.6f}" if valid else "", f"{max(values):.6f}" if valid else "", verdict])
    (args.output_dir / "input-projections.svg").write_text(plot_svg())
    tables = []
    for row in csv.DictReader((args.output_dir / "summary.csv").open()):
        tables.append("<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row.values()) + "</tr>")
    headers = "".join(f"<th>{html.escape(value)}</th>" for value in next(csv.reader((args.output_dir / "summary.csv").open())))
    page = f'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>EXP-02 3D hull pilot</title>
<style>
body {{ font:16px/1.5 system-ui,sans-serif; max-width:1100px; margin:2rem auto; padding:0 1rem; color:#172438 }}
table {{ border-collapse:collapse; width:100%; font-size:.9rem }}
th,td {{ border:1px solid #ccd3df; padding:.45rem; text-align:left }}
th {{ background:#eef1f7 }}
img {{ max-width:100% }}
</style>
<h1>EXP-02: first 3D hull-ladder cell</h1>
<p>The workload has four tetrahedron corners and 246 dyadic interior points. Halton bases 2, 3, and 5 deterministically select strictly positive barycentric weights in multiples of 1/8, making interior-point removal certificates exactly representable. Five LP reducers ran with one warmup and five measured calls each. An independent exact-rational validator verifies each removal certificate and its acyclic expansion to the retained source points. This proves equality of the finite input hull and returned hull even when a reducer conservatively retains some redundant points.</p>
<p>QuickHull is recorded as unsupported because the registered geometric implementation is 2D-only. The plotted projections show input points only; red markers identify the tetrahedron corners. The earlier pure Halton cloud retained every point and is preserved in the <a href="../exp02-it17-hull-3d-halton-cloud-20261028-r1/index.html">initial exploratory attempt</a>.</p>
<figure><img src="input-projections.svg" alt="Input points projected into coordinate planes x1-x2, x1-x3, and x2-x3"><figcaption>Three coordinate projections of the same 3D input; no projected hull boundary is implied.</figcaption></figure>
<table><thead><tr>{headers}</tr></thead><tbody>{''.join(tables)}</tbody></table>
<h2>Scope limits</h2>
<ul>
<li>One deterministic 250-point fixture; this is the first ladder cell, not the EXP-02 matrix.</li>
<li>These reducers are implementation variants; A43/A44 are paper-informed adaptations, not faithful ports.</li>
<li>Workspace creation and independent checking are outside reducer timing. HiGHS is pinned; native solver threading is disabled.</li>
<li>Timing is descriptive. No comparative speedup is claimed because no source-mapped limiter profile is available.</li>
<li>Raw JSONL preserves every attempt and unsupported outcome. See <a href="validated-rows.jsonl">validated rows</a> and <a href="summary.csv">CSV</a>.</li>
</ul>
</html>'''

    (args.output_dir / "index.html").write_text(page)


if __name__ == "__main__":
    main()

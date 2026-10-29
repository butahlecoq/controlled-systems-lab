#!/usr/bin/env python3
"""Validate and render the 250-point EXP-02 QuickHull/ITIS17 comparison."""
from __future__ import annotations

import csv
import html
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPORT_ID = "exp02-it17-dyadic-250-20261029-r1"
METHODS = (
    "geometric-quickhull", "lp-membership-baseline",
    "basis-reuse-related-to-A43", "ordered-membership-related-to-A44",
    "A43-certificate-safe-basis-adaptation", "A44-incremental-LP-farthest-seed",
)


def main() -> None:
    source, target = map(Path, sys.argv[1:3])
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 48 or sum(row["warmup"] for row in rows) != 6:
        raise ValueError("expected one warmup and seven measured rows per method")
    if {row["schema"] for row in rows} != {"csl.it17-hull-paper-adaptation-row/4"}:
        raise ValueError("unexpected raw row schema")
    if {row["source_commit"] for row in rows} != {"9b53f24e9d2e4f1d7c1ec82150589a4bbb50387a"}:
        raise ValueError("unexpected source commit")
    if {row["fixture"] for row in rows} != {"dyadic-square-n250"}:
        raise ValueError("unexpected fixture")
    if len({row["input_sha256"] for row in rows}) != 1:
        raise ValueError("input hash changed between attempts")
    if any(not row["passed"] or not row["accounting_valid"] or
           not row["expected_vertices_retained"] or row["checker"] is None or
           row["checker"]["status"] != "verified" for row in rows):
        raise ValueError("a row failed accounting, expected vertices, or hull verification")
    if any(row["checker"]["budget_max_points"] != 250 or
           row["checker"]["budget_wall_ns"] != 5_000_000_000 for row in rows):
        raise ValueError("checker budget differs from the declared bounded check")
    measured = [row for row in rows if not row["warmup"]]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in measured:
        groups[row["method"]].append(row)
    if set(groups) != set(METHODS) or any(len(group) != 7 for group in groups.values()):
        raise ValueError("measurement matrix is incomplete")
    target.mkdir(parents=True, exist_ok=True)
    (target / "raw").mkdir(exist_ok=True)
    (target / "raw/raw-rows.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    with (target / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("method", "attempts", "median_ns", "min_ns", "max_ns",
                         "reducer_complete"))
        for method in METHODS:
            group = groups[method]
            times = [row["elapsed_ns"] for row in group]
            complete = sum(row["reducer_status_complete"] is True for row in group)
            state = "n/a" if all(row["reducer_status_complete"] is None for row in group) else f"{complete}/7"
            writer.writerow((method, len(group), int(statistics.median(times)), min(times), max(times), state))
    render_fixture(target / "fixture-geometry.svg")
    render_html(target / "index.html", rows, groups)
    print(f"validated {len(rows)} rows: 6 warmups, 42 measured; all hull checks verified")


def render_fixture(path: Path) -> None:
    points = []
    state = 0x6D2B79F5
    used = set()
    while len(points) < 246:
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        x = 1 + state % 31
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        y = 1 + state % 31
        if (x, y) not in used:
            used.add((x, y))
            points.append((x / 32, y / 32))
    width = 760
    left, top, scale = 72, 548, 480
    circles = "\n".join(
        f'<circle cx="{left+x*scale:.2f}" cy="{top-y*scale:.2f}" r="2.6" class="point"><title>dyadic interior point {i+1}</title></circle>'
        for i, (x, y) in enumerate(points))
    path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 620" role="img" aria-labelledby="t d">
<title id="t">250-point dyadic square hull fixture</title>
<desc id="d">The unit square hull has four corners and 246 unique exact dyadic interior points generated from seed 0x6d2b79f5.</desc>
<style>text{{font:14px system-ui,sans-serif;fill:#172033}}.grid{{stroke:#dce3ea;stroke-width:1}}.hull{{fill:#7158bd;fill-opacity:.08;stroke:#59469e;stroke-width:3}}.point{{fill:#1d8b78;stroke:#fff;stroke-width:.6}}.vertex{{fill:#d75b32;stroke:#fff;stroke-width:1.5}}</style>
<rect width="100%" height="100%" fill="white"/><text x="320" y="30" text-anchor="middle" font-weight="700">Dyadic square, 250 points</text>
<g>{''.join(f'<line x1="{left}" y1="{top-i*scale/4}" x2="{left+scale}" y2="{top-i*scale/4}" class="grid"/><line x1="{left+i*scale/4}" y1="{top}" x2="{left+i*scale/4}" y2="{top-scale}" class="grid"/>' for i in range(5))}</g>
<rect x="{left}" y="{top-scale}" width="{scale}" height="{scale}" class="hull"/>{circles}
{''.join(f'<circle cx="{left+x*scale}" cy="{top-y*scale}" r="6" class="vertex"><title>unit-square hull corner ({x},{y})</title></circle>' for x,y in ((0,0),(1,0),(1,1),(0,1)))}
<text x="{left+scale/2}" y="590" text-anchor="middle">x</text><text x="25" y="{top-scale/2}" transform="rotate(-90 25 {top-scale/2})" text-anchor="middle">y</text>
<circle cx="485" cy="585" r="4" class="point"/><text x="495" y="590">interior point</text><circle cx="580" cy="585" r="6" class="vertex"/><text x="590" y="590">hull corner</text></svg>\n''', encoding="utf-8")


def render_html(path: Path, rows: list[dict], groups: dict[str, list[dict]]) -> None:
    source_commit = html.escape(rows[0]["source_commit"])
    table = []
    for method, group in groups.items():
        values = [row["elapsed_ns"] for row in group]
        complete = sum(row["reducer_status_complete"] is True for row in group)
        status = "n/a" if group[0]["reducer_status_complete"] is None else f"{complete}/7"
        table.append(f"<tr><td>{html.escape(method)}</td><td>{len(group)}</td><td>{statistics.median(values)/1e6:.3f} ms</td><td>{min(values)/1e6:.3f}–{max(values)/1e6:.3f} ms</td><td>{status}</td></tr>")
    path.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXP-02 250-point hull pilot</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#172033}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:.5rem;border-bottom:1px solid #dce3ea}}.note{{background:#fff7e7;border-left:4px solid #c28b2c;padding:.8rem}}img{{max-width:100%;height:auto}}</style>
<h1>QuickHull and ITIS17-related reducers on a 250-point cloud</h1><p>EXP-02 exploratory continuation · source commit <code>{source_commit}</code></p>
<p class="note"><strong>Performance conclusion: inconclusive.</strong> The methods were interleaved for seven measured rounds, but no source-mapped limiter profile is available and this is one small 2D fixture. These timings do not establish a general winner or scalability.</p>
<h2>Fixture</h2><p>Four unit-square corners plus 246 unique dyadic interior points from LCG seed <code>0x6d2b79f5</code>. All methods receive identical input SHA256 <code>{rows[0]['input_sha256']}</code>.</p><figure><img src="fixture-geometry.svg" alt="250-point dyadic cloud inside a square hull"><figcaption>Red vertices define the common unit-square hull; teal dots are interior points.</figcaption></figure>
<h2>Results</h2><table><thead><tr><th>Method</th><th>n</th><th>Median call</th><th>Range</th><th>Reducer complete</th></tr></thead><tbody>{''.join(table)}</tbody></table>
<p>Each method had one warmup and seven measured calls. Timing excludes workspace creation, independent checking, and JSON output. All 48 captured attempts passed accounting, retained all four expected corners, and received an independent exact represented-binary64 2D finite-hull checker status of <code>verified</code> (5 s, up to 250 points). Incomplete reducer status remains separate from hull validity. A43/A44 are paper-informed adaptations; no faithful Pascal implementation was found.</p>
<p>Host: AMD Ryzen 5 3550H, 8 logical CPUs, Linux x86_64; Release, GCC 16.2.1, C++20, CMake 3.31.6, HiGHS 1.11.0. No source profile was available (<code>perf</code>/<code>strace</code> absent); LP call counts are not a source-function profile. This one fixture does not complete issue #94.</p>
<p><a href="summary.csv">Summary CSV</a> · <a href="raw/raw-rows.jsonl">Raw rows</a> · <a href="raw/build.log">Clean Release build log</a> · <a href="raw/build-record.txt">Build record</a></p></html>\n''', encoding="utf-8")


if __name__ == "__main__":
    main()

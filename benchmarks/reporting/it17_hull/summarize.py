#!/usr/bin/env python3
"""Validate and summarize the saved preliminary ITIS17 hull pilot rows."""

import csv
import json
import statistics
import sys
from html import escape
from collections import defaultdict
from pathlib import Path


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    expected = 12 + 3 * 4 * 7
    if len(rows) != expected or any(row["passed"] is not True for row in rows):
        raise SystemExit(f"expected {expected} successful rows, got {len(rows)}")
    warmups = [row for row in rows if row["warmup"]]
    measured = [row for row in rows if not row["warmup"]]
    if len(warmups) != 12 or len(measured) != 84:
        raise SystemExit("unexpected warmup or measurement count")
    groups = defaultdict(list)
    for row in measured:
        groups[(row["fixture"], row["method"])].append(row["elapsed_ns"])
    if len(groups) != 12 or any(len(values) != 7 for values in groups.values()):
        raise SystemExit("expected seven measured repetitions per fixture and method")
    source_commits = {row["source_commit"] for row in rows}
    if len(source_commits) != 1:
        raise SystemExit("rows must share one measured source commit")
    target.mkdir(parents=True, exist_ok=True)
    with (target / "raw-rows.jsonl").open("w") as output:
        for row in rows:
            output.write(json.dumps(row, sort_keys=True) + "\n")
    with (target / "summary.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("fixture", "method", "repetitions", "median_ns", "min_ns", "max_ns"))
        for (fixture, method), values in sorted(groups.items()):
            writer.writerow((fixture, method, len(values), int(statistics.median(values)), min(values), max(values)))
    render_geometry(target / "fixture-geometry.svg")
    render_report(target / "index.html", rows, groups, source_commits.pop())
    print(f"validated {len(rows)} rows: {len(warmups)} warmups, {len(measured)} measured")
    return 0


FIXTURES = {
    "permuted": [(0,0),(1,1),(2,0),(0,2),(2,2),(1,0),(1,2),(0,1),(2,1),(1,1.5)],
    "degenerate": [(0,0),(2,0),(2,2),(0,2),(0,0),(1,0),(1,2)],
    "interior-basis": [(1,1),(0,0),(2,0),(2,2),(0,2)],
}
METHODS = (
    "geometric-quickhull", "lp-membership-baseline",
    "basis-reuse-related-to-A43", "ordered-membership-related-to-A44",
)


def render_geometry(path: Path) -> None:
    width, height, panel_width, panel_height = 780, 310, 240, 260
    panels = []
    for index, (fixture, points) in enumerate(FIXTURES.items()):
        left = 20 + index * panel_width
        top = 30
        scale = 94
        x0, y0 = left + 18, top + 205
        corners = [(0,0),(2,0),(2,2),(0,2)]
        hull = " ".join(f"{x0+x*scale},{y0-y*scale}" for x,y in corners) + f" {x0},{y0}"
        panels.append(f'<g><text x="{left+105}" y="20" text-anchor="middle" class="title">{escape(fixture)}</text>')
        for tick in range(3):
            x, y = x0 + tick*scale, y0 - tick*scale
            panels.append(f'<line x1="{x0}" y1="{y}" x2="{x0+2*scale}" y2="{y}" class="grid"/>')
            panels.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0-2*scale}" class="grid"/>')
            panels.append(f'<text x="{x}" y="{y0+18}" text-anchor="middle" class="tick">{tick}</text>')
            panels.append(f'<text x="{x0-10}" y="{y+4}" text-anchor="end" class="tick">{tick}</text>')
        panels.append(f'<polyline points="{hull}" class="hull"/>')
        for point_index, (x, y) in enumerate(points):
            px, py = x0+x*scale, y0-y*scale
            is_corner = (x,y) in corners
            klass = "corner" if is_corner else "redundant"
            panels.append(f'<circle cx="{px}" cy="{py}" r="{6 if is_corner else 4.5}" class="{klass}"/>')
            panels.append(f'<title>input point {point_index}: ({x}, {y})</title>')
        panels.append('</g>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Three exact square hull fixtures</title><desc id="desc">Each panel plots its actual input points within the square from zero to two. The purple outline marks the four expected extreme corners. Teal points are redundant interior or edge points.</desc>
<style>text{{font-family:system-ui,sans-serif;fill:#192336}}.title{{font-size:15px;font-weight:700}}.tick{{font-size:11px;fill:#586579}}.grid{{stroke:#d9e0e8;stroke-width:1}}.hull{{fill:#7869c4;fill-opacity:.08;stroke:#5848a8;stroke-width:2.5}}.corner{{fill:#5848a8;stroke:white;stroke-width:1.5}}.redundant{{fill:#1a9b8a;stroke:white;stroke-width:1.2}}</style>
{''.join(panels)}
<g transform="translate(74 292)"><circle cx="0" cy="0" r="5" class="corner"/><text x="10" y="4" class="tick">expected extreme corner</text><circle cx="190" cy="0" r="4.5" class="redundant"/><text x="200" y="4" class="tick">redundant input point</text></g></svg>'''
    path.write_text(svg + "\n")


def render_report(path: Path, rows: list[dict], groups: dict, source_commit: str) -> None:
    measured = [row for row in rows if not row["warmup"]]
    table_rows = []
    for (fixture, method), values in sorted(groups.items()):
        table_rows.append(
            f"<tr><td>{escape(fixture)}</td><td>{escape(method)}</td>"
            f"<td>7</td><td>{int(statistics.median(values)):,}</td>"
            f"<td>{min(values):,}–{max(values):,}</td></tr>"
        )
    table = "\n".join(table_rows)
    path.write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuickHull and ITIS17-related hull pilot — preliminary</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1.2rem;color:#172033;background:#fff}}
h1,h2{{line-height:1.2}}.status{{padding:1rem;border-left:5px solid #b7791f;background:#fff8e8}}
figure{{margin:1.5rem 0}}figure img{{display:block;width:min(100%,780px);height:auto}}figcaption,small{{color:#526174}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border-bottom:1px solid #dce2e9;padding:.55rem;text-align:left}}th{{background:#f3f6f9}}
code{{overflow-wrap:anywhere}}.links{{display:flex;gap:1rem;flex-wrap:wrap}}
</style></head><body>
<h1>QuickHull and ITIS17-related LP hull pilot</h1>
<p><strong>Preliminary exploratory result · source commit <code>{escape(source_commit)}</code></strong></p>
<section class="status"><strong>Performance conclusion: inconclusive.</strong> This run used three tiny 2D square clouds. It has no source-mapped limiter profile or representative end-to-end workload, so the measurements do not support a speed ranking or scalability claim.</section>
<h2>Fixture geometry</h2><figure><img src="fixture-geometry.svg" alt="Three panels showing the permuted, degenerate, and interior-basis point clouds and their shared square hull"><figcaption>The purple outline marks the four expected extreme corners. Teal marks redundant input points. Exact integer coordinates make these fixture hull checks direct.</figcaption></figure>
<h2>Algorithms and timing scope</h2>
<p>QuickHull is compared with three existing LP reducers. The A43 basis-reuse and A44 ordered reducers are related variants, not faithful implementations of either paper. Timing covers each public reducer call; LP workspace creation and output validation are outside the interval. Each row below summarizes seven interleaved measured calls per fixture and method. Values are nanoseconds; raw trials and warmups remain in the linked JSONL.</p>
<table><thead><tr><th>Fixture</th><th>Method</th><th>Trials</th><th>Median (ns)</th><th>Range (ns)</th></tr></thead><tbody>{table}</tbody></table>
<p>All {len(rows)} calls ({len(rows)-len(measured)} warmups and {len(measured)} measured calls) passed the fixture checks. Passing these small cases does not establish general correctness for arbitrary point clouds. The reducers can retain different numbers of redundant points while representing the same hull.</p>
<h2>Evidence and limits</h2>
<ul><li>Three literal clouds contain 5–10 points each.</li><li>The oracle checks point accounting, exact-binary64 convex-combination evidence for deleted points, rectangle containment, and retention of all four expected corners.</li><li>All algorithms ran in Release on GCC 16.2.1, C++20, HiGHS 1.11.0, Linux x86_64.</li><li>No original Pascal source for the ITIS17 methods was found. The separate <code>btulshor.pas</code> method was not run.</li><li>This is an exploratory, unregistered bundle. It does not complete issue #423 or establish a paper-faithful comparison. It is not deployed to GitHub Pages.</li></ul>
<p class="links"><a href="summary.csv">Download summary CSV</a><a href="raw-rows.jsonl">Download all raw rows</a><a href="fixture-geometry.svg">Open fixture SVG</a></p>
</body></html>\n''')


if __name__ == "__main__":
    raise SystemExit(main())

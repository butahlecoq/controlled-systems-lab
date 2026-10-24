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
    expected = 18 + 3 * 6 * 7
    if len(rows) != expected or any(row["passed"] is not True for row in rows):
        raise SystemExit(f"expected {expected} successful rows, got {len(rows)}")
    warmups = [row for row in rows if row["warmup"]]
    measured = [row for row in rows if not row["warmup"]]
    if len(warmups) != 18 or len(measured) != 126:
        raise SystemExit("unexpected warmup or measurement count")
    groups = defaultdict(list)
    input_hashes = defaultdict(set)
    identities = defaultdict(set)
    for row in measured:
        groups[(row["fixture"], row["method"])].append(row["elapsed_ns"])
        input_hashes[row["fixture"]].add(row["input_sha256"])
        identities[row["method"]].add(row["method_identity"])
    if len(groups) != 18 or any(len(values) != 7 for values in groups.values()):
        raise SystemExit("expected seven measured repetitions per fixture and method")
    expected_groups = {(fixture, method) for fixture in FIXTURES for method in METHODS}
    if set(groups) != expected_groups:
        raise SystemExit("measurement matrix has a missing or unexpected method/fixture pair")
    if any(len(values) != 1 for values in input_hashes.values()) or any(
            len(values) != 1 for values in identities.values()):
        raise SystemExit("paired rows must share fixture hashes and method identities")
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
    "A43-certificate-safe-basis-adaptation", "A44-incremental-LP-paper-adaptation",
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
        seen = set()
        for point_index, (x, y) in enumerate(points):
            px, py = x0+x*scale, y0-y*scale
            if (x, y) in seen:
                marker = f'<circle cx="{px}" cy="{py}" r="9" class="duplicate"/>'
                category = "duplicate point"
            elif (x, y) in corners:
                marker, category = f'<circle cx="{px}" cy="{py}" r="6" class="corner"/>', "hull vertex"
            elif x in {0, 2} or y in {0, 2}:
                marker, category = f'<circle cx="{px}" cy="{py}" r="5" class="edge"/>', "edge point"
            else:
                marker, category = f'<circle cx="{px}" cy="{py}" r="5" class="interior"/>', "interior point"
            panels.append(f'<g><title>input point {point_index}: ({x}, {y}), {category}</title>{marker}</g>')
            seen.add((x, y))
        panels.append('</g>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Three exact square hull fixtures</title><desc id="desc">Each panel plots original input point IDs in the square from zero to two. Symbols distinguish expected hull vertices, edge points, interior points, and duplicates.</desc>
<style>text{{font-family:system-ui,sans-serif;fill:#192336}}.title{{font-size:15px;font-weight:700}}.tick{{font-size:11px;fill:#586579}}.grid{{stroke:#d9e0e8;stroke-width:1}}.hull{{fill:#7869c4;fill-opacity:.08;stroke:#5848a8;stroke-width:2.5}}.corner{{fill:#5848a8;stroke:white;stroke-width:1.5}}.edge{{fill:#e18a2d;stroke:white;stroke-width:1.2}}.interior{{fill:#1a9b8a;stroke:white;stroke-width:1.2}}.duplicate{{fill:none;stroke:#d13c4b;stroke-width:2.5}}</style>
<rect width="100%" height="100%" fill="white"/>
{''.join(panels)}
<g transform="translate(22 292)"><circle cx="0" cy="0" r="5" class="corner"/><text x="9" y="4" class="tick">hull vertex</text><circle cx="112" cy="0" r="5" class="edge"/><text x="121" y="4" class="tick">edge</text><circle cx="185" cy="0" r="5" class="interior"/><text x="194" y="4" class="tick">interior</text><circle cx="278" cy="0" r="8" class="duplicate"/><text x="289" y="4" class="tick">duplicate</text></g></svg>'''
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
<div class="status"><strong>Performance conclusion: inconclusive.</strong> This run used three tiny 2D square clouds. It has no source-mapped limiter profile or representative end-to-end workload, so the measurements do not support a speed ranking or scalability claim.</div>
<h2>Fixture geometry</h2><figure><img src="fixture-geometry.svg" alt="Three panels showing original point IDs, with distinct symbols for hull vertices, edge points, interior points, and duplicates"><figcaption>Point IDs appear in each point's SVG title. Color and symbol distinguish hull vertices, edge points, interior points, and duplicates. Exact dyadic coordinates make these fixture hull checks direct.</figcaption></figure>
<h2>Algorithms and timing scope</h2>
<p>QuickHull is compared with five LP reducer variants. The related OPT-06 basis-reuse and OPT-07 ordered reducers retain their original identities. The new A43 safe adaptation wraps certificate-safe basis reuse with a mandatory full recheck; it does not implement the paper's per-candidate artificial-basis sequence or largest-norm tie rule. The A44 adaptation performs farthest-first incremental LP membership using normalized Chebyshev distance, then a mandatory full LP recheck. A44's paper ordering prose is ambiguous, and this report records the farthest-first interpretation. Neither is a Pascal reproduction. Timing covers each public reducer call; LP workspace creation and output validation are outside the interval. Each row below summarizes seven interleaved measured calls per fixture and method. Values are nanoseconds; raw trials and warmups remain in the linked JSONL.</p>
<table><thead><tr><th>Fixture</th><th>Method</th><th>Trials</th><th>Median (ns)</th><th>Range (ns)</th></tr></thead><tbody>{table}</tbody></table>
<p>All {len(rows)} calls ({len(rows)-len(measured)} warmups and {len(measured)} measured calls) passed the fixture checks. All coordinates are exact dyadic rationals. Passing these small cases does not establish general correctness for arbitrary point clouds. The reducers can retain different numbers of redundant points while representing the same hull.</p>
<h2>Evidence and limits</h2>
<ul><li>Three literal clouds contain 5–10 points each.</li><li>The bounded independent exact 2D checker establishes all-input hull coverage for every output; LP deletions also retain exact-binary64 convex-combination certificates.</li><li>All algorithms ran in Release on GCC 16.2.1, C++20, HiGHS 1.11.0, Linux x86_64.</li><li>No original Pascal source for the ITIS17 methods was found. The separate <code>btulshor.pas</code> method was not run.</li><li>This exploratory bundle does not complete the EXP-02 issue or establish faithful reproduction of either paper.</li></ul>
<p class="links"><a href="summary.csv">Download summary CSV</a><a href="raw-rows.jsonl">Download all raw rows</a><a href="fixture-geometry.svg">Open fixture SVG</a></p>
</body></html>\n''')


if __name__ == "__main__":
    raise SystemExit(main())

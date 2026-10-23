#!/usr/bin/env python3
"""Validate and render the saved same-input approximation pilot capture."""

import csv
import hashlib
import html
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED = {
    "exact-polygon-quickhull": (8.0, 1.0),
    "axis-box": (16.0, 2.0),
    "rotated-parallelotope": (8.0, 1.0),
    "zonotope-axis-cover": (16.0, 2.0),
    "directional-ellipsoid": (8.0 * math.pi, math.pi),
}
INPUT_DESCRIPTOR_SHA256 = "bf23229be76bfeaa7bb6a9965c90a53a32580eeba6a7cdb07be905152dac3d9c"
REQUEST_IDENTITIES = {
    "exact-polygon-quickhull": {
        "request_identity": "approx-pilot/quickhull/diamond/exact-polygon/v1",
        "source_representation": "diamond-v",
        "requested_relation": "exact",
        "output_budget": "four hull vertices",
        "assurance": "exact-literal-hull",
    },
    "axis-box": {
        "request_identity": "approx-pilot/box/diamond",
        "source_representation": "diamond-v",
        "requested_relation": "outer",
        "output_budget": "four H inequalities",
        "assurance": "numerical",
    },
    "rotated-parallelotope": {
        "request_identity": "approx-pilot/parallelotope/diamond",
        "source_representation": "diamond-v",
        "requested_relation": "outer",
        "output_budget": "four H inequalities",
        "assurance": "numerical",
    },
    "zonotope-axis-cover": {
        "request_identity": "approx-pilot/zonotope-cover/diamond",
        "source_representation": "diamond-zonotope-equivalent",
        "requested_relation": "outer",
        "output_budget": "two generators",
        "assurance": "numerical",
    },
    "directional-ellipsoid": {
        "request_identity": "approx-pilot/ellipsoid/diamond",
        "source_representation": "diamond-v",
        "requested_relation": "outer",
        "output_budget": "one ellipsoid",
        "assurance": "numerical",
    },
}
COLORS = {
    "exact-polygon-quickhull": "#355c7d",
    "axis-box": "#d95f02",
    "rotated-parallelotope": "#1b9e77",
    "zonotope-axis-cover": "#7570b3",
    "directional-ellipsoid": "#e7298a",
}


def read_rows(path: Path):
    input_path = path.parent / "input.txt"
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != INPUT_DESCRIPTOR_SHA256:
        raise SystemExit("input descriptor hash differs from the request identity map")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if len(rows) != 40 or any(row["passed"] is not True for row in rows):
        raise SystemExit("capture must contain 40 successful rows")
    if any(row["schema"] != "csl.approximation-matched-pilot-row/1" or
           row["fixture"] != "diamond" for row in rows):
        raise SystemExit("capture contains an unexpected row schema or fixture")
    if sum(row["warmup"] for row in rows) != 5:
        raise SystemExit("capture must contain five excluded warmups")
    if len({row["source_commit"] for row in rows}) != 1:
        raise SystemExit("capture mixes source commits")
    groups = defaultdict(list)
    for row in rows:
        groups[row["method"]].append(row)
        area, ratio = EXPECTED[row["method"]]
        if not math.isclose(row["area"], area, rel_tol=1e-14, abs_tol=1e-14):
            raise SystemExit(f"unexpected output area for {row['method']}")
        if not math.isclose(row["area_ratio"], ratio, rel_tol=1e-14, abs_tol=1e-14):
            raise SystemExit(f"unexpected area ratio for {row['method']}")
    if set(groups) != set(EXPECTED):
        raise SystemExit("unexpected method set")
    if set(groups) != set(REQUEST_IDENTITIES):
        raise SystemExit("request identities do not cover the captured method set")
    for method, group in groups.items():
        if len(group) != 8 or sum(not row["warmup"] for row in group) != 7 or \
           sum(row["warmup"] and row["round"] == 0 for row in group) != 1 or \
           sorted(row["round"] for row in group if not row["warmup"]) != list(range(1, 8)):
            raise SystemExit(f"expected one warmup and seven measured rows for {method}")
    for round_number in range(1, 8):
        round_rows = [row for row in rows if not row["warmup"] and row["round"] == round_number]
        if {row["method"] for row in round_rows} != set(EXPECTED) or len(round_rows) != 5:
            raise SystemExit(f"measurement round {round_number} is incomplete")
    return rows


def make_svg(path: Path):
    methods = list(EXPECTED)
    labels = {
        "exact-polygon-quickhull": "Exact polygon",
        "axis-box": "Axis box",
        "rotated-parallelotope": "Rotated parallelotope",
        "zonotope-axis-cover": "Zonotope axis cover",
        "directional-ellipsoid": "Directional ellipsoid",
    }
    width, panel_width, height = 1250, 250, 390
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Approximation areas on one exact diamond</title>',
        '<desc id="desc">Each panel overlays one output with the exact input diamond. Ratios are output area divided by the exact input area.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="625" y="30" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">Same diamond input: output area and enclosure shape</text>',
    ]
    for index, method in enumerate(methods):
        x0 = index * panel_width
        cx, cy, scale = x0 + panel_width / 2, 200, 36
        px = lambda x: cx + x * scale
        py = lambda y: cy - y * scale
        pieces.extend([
            f'<text x="{cx}" y="62" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="bold">{labels[method]}</text>',
            f'<line x1="{x0+25}" y1="{cy}" x2="{x0+225}" y2="{cy}" stroke="#9ca3af"/>',
            f'<line x1="{cx}" y1="100" x2="{cx}" y2="300" stroke="#9ca3af"/>',
            f'<text x="{x0+222}" y="{cy+14}" font-family="sans-serif" font-size="10">x</text>',
            f'<text x="{cx+5}" y="106" font-family="sans-serif" font-size="10">y</text>',
        ])
        for coordinate, label in ((-2, "−2"), (2, "2")):
            pieces.extend([
                f'<line x1="{px(coordinate)}" y1="{cy-4}" x2="{px(coordinate)}" y2="{cy+4}" stroke="#6b7280"/>',
                f'<text x="{px(coordinate)}" y="{cy+17}" text-anchor="middle" font-family="sans-serif" font-size="9">{label}</text>',
                f'<line x1="{cx-4}" y1="{py(coordinate)}" x2="{cx+4}" y2="{py(coordinate)}" stroke="#6b7280"/>',
                f'<text x="{cx+8}" y="{py(coordinate)+3}" font-family="sans-serif" font-size="9">{label}</text>',
            ])
        input_diamond = f"{px(0)},{py(2)} {px(2)},{py(0)} {px(0)},{py(-2)} {px(-2)},{py(0)}"
        pieces.append(f'<polygon points="{input_diamond}" fill="#355c7d" fill-opacity="0.10" stroke="#355c7d" stroke-width="2"/>')
        color = COLORS[method]
        if method in ("exact-polygon-quickhull", "rotated-parallelotope"):
            pieces.append(f'<polygon points="{input_diamond}" fill="none" stroke="{color}" stroke-width="3"/>')
        elif method in ("axis-box", "zonotope-axis-cover"):
            points = f"{px(-2)},{py(2)} {px(2)},{py(2)} {px(2)},{py(-2)} {px(-2)},{py(-2)}"
            pieces.append(f'<polygon points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        else:
            radius = math.sqrt(EXPECTED[method][0] / math.pi)
            pieces.append(f'<circle cx="{cx}" cy="{cy}" r="{radius*scale:.6f}" fill="none" stroke="{color}" stroke-width="3"/>')
        pieces.append(f'<text x="{cx}" y="330" text-anchor="middle" font-family="sans-serif" font-size="13">area ratio: {EXPECTED[method][1]:.6g}</text>')
        pieces.append(f'<text x="{cx}" y="350" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#4b5563">blue outline/fill = exact reference</text>')
        if index:
            pieces.append(f'<line x1="{x0}" y1="48" x2="{x0}" y2="366" stroke="#e5e7eb"/>')
    pieces.append('<text x="625" y="378" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#374151">Stored binary64 fixture; the area ratios describe this single example only.</text>')
    pieces.append('</svg>')
    path.write_text("\n".join(pieces) + "\n")


def main() -> int:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    rows = read_rows(source)
    target.mkdir(parents=True, exist_ok=True)
    with (target / "raw-rows.jsonl").open("w") as output:
        for row in rows:
            output.write(json.dumps(row, sort_keys=True) + "\n")
    request_map = {
        "schema": "csl.approximation-pilot-request-map/1",
        "fixture": "diamond",
        "input_descriptor": "input.txt",
        "input_descriptor_sha256": INPUT_DESCRIPTOR_SHA256,
        "mapping_status": "proposed-migration; not registered or imported",
        "requests": REQUEST_IDENTITIES,
    }
    (target / "request-identities.json").write_text(
        json.dumps(request_map, indent=2, sort_keys=True) + "\n")
    grouped = defaultdict(list)
    for row in rows:
        if not row["warmup"]:
            grouped[row["method"]].append(row)
    with (target / "summary.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("method", "request_identity", "requested_relation", "source_representation", "repetitions", "median_ns", "min_ns", "max_ns", "area", "area_ratio", "evidence"))
        for method in EXPECTED:
            group = grouped[method]
            durations = [row["elapsed_ns"] for row in group]
            identity = REQUEST_IDENTITIES[method]
            writer.writerow((method, identity["request_identity"], identity["requested_relation"], identity["source_representation"], len(group), int(statistics.median(durations)), min(durations), max(durations), group[-1]["area"], group[-1]["area_ratio"], group[-1]["evidence"]))
    make_svg(target / "comparison.svg")
    table_rows = []
    for method in EXPECTED:
        group = grouped[method]
        durations = [row["elapsed_ns"] for row in group]
        identity = REQUEST_IDENTITIES[method]
        table_rows.append(
            "<tr><th scope=\"row\">{}</th><td><code>{}</code></td><td>{}</td>"
            "<td>{}</td><td>{:,}</td><td>{:,}–{:,}</td><td>{:.15g}</td>"
            "<td>{:.15g}</td><td>{}</td></tr>".format(
                html.escape(method), html.escape(identity["request_identity"]),
                html.escape(identity["requested_relation"]),
                html.escape(identity["source_representation"]),
                int(statistics.median(durations)), min(durations), max(durations),
                group[-1]["area"], group[-1]["area_ratio"],
                html.escape(group[-1]["evidence"]))
        )
    document = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matched 2D approximation pilot</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#18212b}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:.55rem;border:1px solid #ccd3da;text-align:left}th{background:#f2f5f7}img{width:100%;height:auto}code{overflow-wrap:anywhere}.note{background:#fff7e6;padding:1rem;border-left:4px solid #e2a500}</style>
<h1>Matched 2D approximation pilot</h1>
<p>One stored-binary64 diamond input, with exact polygon, axis box, rotated parallelotope, zonotope axis cover, and directional ellipsoid outputs.</p>
<p class="note"><strong>Scope:</strong> this single-fixture geometry pilot gives no general approximation guarantee or performance winner. Areas and ratios are specific to this diamond. Call timings use different API paths and are descriptive only; no source-mapped limiter profile was collected.</p>
<figure><img src="comparison.svg" alt="Five output outlines compared with the exact diamond reference"><figcaption>Area ratio is output area divided by the exact diamond area 8.</figcaption></figure>
<h2>Measurements and geometric diagnostics</h2>
<p>Times are the median and range of seven interleaved single calls per method, after one excluded warmup. Units are nanoseconds. Workspace/preparation is included inside each registered approximation call; input construction and validation are outside the timer. The QuickHull method times its public function only.</p>
<table><thead><tr><th>Method</th><th>Request identity</th><th>Relation</th><th>Source representation</th><th>Median (ns)</th><th>Range (ns)</th><th>Area</th><th>Area ratio</th><th>Fixture check</th></tr></thead><tbody>__ROWS__</tbody></table>
<h2>Reproduction and saved data</h2>
<p>Release build, compiler, host snapshots, executable hash, and smoke output are in this directory. Raw per-call rows are in <a href="raw-rows.jsonl">raw-rows.jsonl</a>; the table is in <a href="summary.csv">summary.csv</a>. The proposed method/request/input mapping is in <a href="request-identities.json">request-identities.json</a>, and its future-record field mapping is documented in <a href="comparison-record-migration.md">comparison-record-migration.md</a>. Rebuild with the CMake project under <code>benchmarks/reporting/approximation_pilot/</code> and regenerate with its <code>summarize.py</code>.</p>
<p>Source commit: <code>__COMMIT__</code>. This is preliminary evidence, not a registered comparison-program result and not a Pages publication.</p>
</html>
""".replace("__ROWS__", "\n".join(table_rows)).replace(
        "__COMMIT__", html.escape(rows[0]["source_commit"]))
    (target / "index.html").write_text(document)
    print(f"validated {len(rows)} successful rows across {len(EXPECTED)} methods")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

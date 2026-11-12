"""Render the source-index 2D geometry figure from its saved vertex records."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "docs/examples/source-index-geometry-2d-records.json"
HTML_PAGE = ROOT / "docs/examples/source-index-geometry-2d.html"
SVG_PAGE = ROOT / "docs/examples/source-index-geometry-2d.svg"


def _points(records: dict, method: str, operation: str) -> list[tuple[float, float]]:
    results = records[method]["results"]
    match = next(item for item in results if item["operation"] == operation)
    return [(float(x), float(y)) for x, y in match["vertices"]]


def _fmt(value: float) -> str:
    return f"{value:g}"


def _panel(x: float, title: str, points: list[tuple[float, float]],
           limits: tuple[float, float, float, float], color: str,
           extras: list[tuple[float, float, str]] | None = None) -> str:
    width, height, top, bottom = 250.0, 260.0, 74.0, 334.0
    xmin, xmax, ymin, ymax = limits

    def screen(px: float, py: float) -> tuple[float, float]:
        sx = x + (px - xmin) / (xmax - xmin) * width
        sy = bottom - (py - ymin) / (ymax - ymin) * height
        return sx, sy

    pieces = [f'<g class="plot" aria-label="{html.escape(title, quote=True)}">',
              f'<text class="title" x="{x:g}" y="34">{html.escape(title)}</text>']
    for tick in range(math.ceil(xmin * 2), math.floor(xmax * 2) + 1):
        value = tick / 2
        sx, _ = screen(value, 0)
        pieces.append(f'<path class="grid" d="M{sx:.2f} {top:g}V{bottom:g}"/>')
        pieces.append(f'<text class="tick" x="{sx:.2f}" y="354">{_fmt(value)}</text>')
    for tick in range(math.ceil(ymin * 2), math.floor(ymax * 2) + 1):
        value = tick / 2
        _, sy = screen(0, value)
        pieces.append(f'<path class="grid" d="M{x:g} {sy:.2f}H{x + width:g}"/>')
        pieces.append(f'<text class="tick ytick" x="{x - 8:g}" y="{sy + 4:.2f}">{_fmt(value)}</text>')
    ax0, ax_bottom = screen(0, 0)
    _, ay0 = screen(0, 0)
    pieces.extend([
        f'<path class="axis" d="M{x:g} {ay0:.2f}H{x + width:g}"/>',
        f'<path class="axis" d="M{ax0:.2f} {top:g}V{bottom:g}"/>',
        f'<text class="axis-label" x="{x + width - 8:g}" y="{ay0 - 8:.2f}">x</text>',
        f'<text class="axis-label" x="{ax0 + 7:.2f}" y="{top + 12:g}">y</text>',
    ])
    screen_points = [screen(px, py) for px, py in points]
    path = " ".join(("M" if index == 0 else "L") + f"{sx:.2f},{sy:.2f}"
                     for index, (sx, sy) in enumerate(screen_points)) + " Z"
    pieces.append(f'<path class="shape {color}" d="{path}"/>')
    for px, py in points:
        sx, sy = screen(px, py)
        pieces.append(f'<circle class="vertex" cx="{sx:.2f}" cy="{sy:.2f}" r="4"/>')
    for px, py, label in extras or []:
        sx, sy = screen(px, py)
        pieces.append(f'<circle class="{label}" cx="{sx:.2f}" cy="{sy:.2f}" r="4"/>')
    pieces.extend([f'<text class="axis-name" x="{x + width / 2:g}" y="376">x coordinate</text>',
                   f'<text class="axis-name" transform="translate({x - 28:g} {top + height / 2:g}) rotate(-90)">y coordinate</text>',
                   '</g>'])
    return "\n".join(pieces)


def render_svg(records: dict) -> str:
    if records.get("schema") != "csl.example.source-index-geometry-2d-records/1":
        raise ValueError("unsupported source-index record schema")
    image = _points(records, "quickhull", "affine_image")
    image_bt = _points(records, "btulshor", "affine_image")
    control_sum = _points(records, "quickhull", "control_minkowski_sum")
    sum_bt = _points(records, "btulshor", "control_minkowski_sum")
    if sorted(image) != sorted(image_bt) or sorted(control_sum) != sorted(sum_bt):
        raise ValueError("QuickHull and BTULSHOR records disagree on displayed geometry")
    input_points = [(0, 0), (1, 0), (1, 1), (0, 1)]
    extras = [(0.5, 0, "edge"), (0, 0, "duplicate"), (1 / 3, 1 / 3, "interior")]
    content = [
        _panel(68, "Input cloud", input_points, (-0.25, 1.25, -0.25, 1.25), "hull", extras),
        _panel(385, "Affine image from records", image, (-0.25, 1.5, -0.75, 1.25), "image"),
        _panel(702, "One-step control sum", control_sum,
               (-0.25, 1.5, -0.25, 1.75), "sum"),
    ]
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1020 405" role="img" aria-labelledby="title desc">
<title id="title">Source-index input, affine image, and one-step control sum in data coordinates</title>
<desc id="desc">Each panel labels x and y in data coordinates and shows the zero axes. The affine image vertices and control-sum vertices come from the saved QuickHull record. They match the saved BTULSHOR record. Negative y coordinates appear below the horizontal zero axis.</desc>
<style>text{font:14px system-ui,sans-serif;fill:#18212b}.title{font-weight:650;font-size:16px}.tick{font-size:11px;text-anchor:middle}.ytick{text-anchor:end}.grid{stroke:#e1e6eb;stroke-width:1}.axis{stroke:#405366;stroke-width:2}.axis-label,.axis-name{font-size:12px;font-weight:600}.shape{stroke-width:3;fill-opacity:.4}.hull{fill:#91c8aa;stroke:#287357}.image{fill:#e9c76d;stroke:#9b6c13}.sum{fill:#9cbfdf;stroke:#32658f}.vertex{fill:#153f2f}.edge{fill:#bd6c22}.duplicate{fill:#7657a6}.interior{fill:#bd3f36}</style>
<rect width="1020" height="405" fill="#fbfcfe"/>
''' + "\n".join(content) + "\n</svg>\n"


def render_html(svg: str) -> str:
    body = HTML_PAGE.read_text(encoding="utf-8") if HTML_PAGE.exists() else ""
    if body and "<svg " in body:
        body = re.sub(r'<svg\b.*?</svg>', svg.rstrip(), body, flags=re.S)
        body = body.replace("blob/main/", "blob/2c612c64600b5ae10906809a9147571cd9237b79/")
        body = re.sub(
            r"The pictured geometry is an explanation of the fixture; consult the saved raw records to inspect\s+the actual provider traces\.",
            "The input hull uses the declared square corners. The affine image and control sum are plotted from the saved QuickHull vertices. The saved BTULSHOR vertices match both plots. Tick labels show data coordinates, and the axes mark x=0 and y=0.",
            body)
        body = body.replace("two source-index methods inside the same 2D geometry", "source-index methods inside the same 2D geometry")
        return body
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = json.loads(RECORDS.read_text(encoding="utf-8"))
    svg = render_svg(records)
    page = render_html(svg)
    if not page:
        raise SystemExit("source-index HTML figure template has no inline SVG")
    if args.check:
        if SVG_PAGE.read_text(encoding="utf-8") != svg or HTML_PAGE.read_text(encoding="utf-8") != page:
            raise SystemExit("source-index figure is stale; run source_index_figure.py")
    else:
        SVG_PAGE.write_text(svg, encoding="utf-8")
        HTML_PAGE.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()

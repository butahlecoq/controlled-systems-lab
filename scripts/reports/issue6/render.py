#!/usr/bin/env python3
"""Render B06 plots and a small HTML report only from captured result files."""
import html
import json
import sys
from pathlib import Path


def hull(points):
    points = sorted(set((float(p[0]), float(p[1])) for p in points))
    if len(points) <= 1:
        return points
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def figure(record):
    panels = [
        ("Terminal flows", 0, 2, "Oxidizer flow x₁ (kg/s)", "Fuel flow x₃ (kg/s)", (30.0, 20.0)),
        ("Terminal stock balances", 1, 3, "Oxidizer balance x₂ (kg)", "Fuel balance x₄ (kg)", (0.0, 0.0)),
    ]
    width, height = 1120, 500
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<rect width="100%" height="100%" fill="white"/>',
              '<style>text{font:15px sans-serif;fill:#17212b}.title{font-size:20px;font-weight:600}.poly{fill:#64a8d6;fill-opacity:.34;stroke:#155d89;stroke-width:2}.target{fill:#d23b32;stroke:white;stroke-width:1.5}</style>',
              '<text x="560" y="30" text-anchor="middle" class="title">B06 reference: exact 2D projections of the computed terminal V-set</text>']
    for panel, (title, ix, iy, xlabel, ylabel, target) in enumerate(panels):
        x0, y0, pw, ph = 65 + panel*550, 75, 470, 350
        points = [(v[ix], v[iy]) for v in record["winner_terminal_vertices"]]
        polygon = hull(points)
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        dx, dy = max(max(xs)-min(xs), 1e-8), max(max(ys)-min(ys), 1e-8)
        xmin, xmax = min(xs)-.12*dx, max(xs)+.12*dx
        ymin, ymax = min(ys)-.12*dy, max(ys)+.12*dy
        def sx(x): return x0+(x-xmin)/(xmax-xmin)*pw
        def sy(y): return y0+ph-(y-ymin)/(ymax-ymin)*ph
        coordinates = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in polygon)
        pieces.extend([f'<text x="{x0+pw/2}" y="58" text-anchor="middle" class="title">{title}</text>',
            f'<line x1="{x0}" y1="{y0+ph}" x2="{x0+pw}" y2="{y0+ph}" stroke="#334"/>',
            f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+ph}" stroke="#334"/>',
            f'<polygon class="poly" points="{coordinates}"/>',
            f'<circle class="target" cx="{sx(target[0]):.2f}" cy="{sy(target[1]):.2f}" r="6"/>',
            f'<text x="{sx(target[0])+9:.2f}" y="{sy(target[1])-7:.2f}">target</text>',
            f'<text x="{x0+pw/2}" y="{y0+ph+45}" text-anchor="middle">{html.escape(xlabel)}</text>',
            f'<text transform="translate({x0-48},{y0+ph/2}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>',
            f'<text x="{x0+pw/2}" y="{y0+ph+20}" text-anchor="middle" font-size="12">x: {xmin:.5g} … {xmax:.5g}</text>',
            f'<text transform="translate({x0+12},{y0+ph/2}) rotate(-90)" text-anchor="middle" font-size="12">y: {ymin:.5g} … {ymax:.5g}</text>'])
    pieces.append('<text x="560" y="490" text-anchor="middle" font-size="13">Winning fixed plan (-0.3, 1, 0, 0, 0.3); all 1,024 corner histories, numeric V-representation</text>')
    pieces.append('</svg>')
    return "\n".join(pieces)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: render.py RESULT_DIRECTORY")
    root = Path(sys.argv[1])
    geometry = json.loads((root / "geometry.json").read_text())
    runs = [json.loads(line) for line in (root / "raw-runs.jsonl").read_text().splitlines()]
    exact = json.loads((root / "exact-oracle.json").read_text())
    (root / "terminal-projections.svg").write_text(figure(geometry))
    measured = [row["elapsed_ns"] for row in runs[1:]]
    ordered = sorted(measured)
    median = ordered[len(ordered)//2]
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>B06 owner-confirmed reference</title>
<style>body{{font:16px/1.55 system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#17212b}}img{{max-width:100%}}table{{border-collapse:collapse}}td,th{{border:1px solid #aaa;padding:.4rem .7rem}}</style>
<h1>B06 owner-confirmed disturbance reference</h1>
<p>This is a distinct reference case for the displayed L09 dynamics plus the owner's 2026-10-25 disturbance decision. It is not a reproduction of the paper's run or its reported 10.11 value.</p>
<p>The finite-action solver examined 3,125 control plans and 1,024 disturbance-corner histories per plan. An independent integer-scaled exhaustive oracle found the unique minimax plan (-0.3, 1, 0, 0, 0.3), matching the printed L09 plan. The exact squared objective is {exact['minimum_objective_squared_numerator']}/9,000,000 = {exact['minimum_objective_squared_numerator']/9_000_000:.12f}; its norm is {exact['objective_norm']:.12f}. The paper reports 10.11 for different, unrecovered uncertainty/run details.</p>
<figure><img src="terminal-projections.svg" alt="Two projections of the terminal set reached by the winning B06 fixed plan"><figcaption>Terminal flow and stock-balance projections. The polygon uses the full set of generated disturbance vertices; no sampled histories are shown. Coordinates use the source's units.</figcaption></figure>
<h2>Measurement</h2><p>Seven single-call Release observations after one excluded warmup. Median {median:,} ns; range {min(measured):,}–{max(measured):,} ns. Each interval includes request construction and the public finite-action minimax call, and excludes process startup, JSON serialization, the independent exact oracle and rendering. The result is a single-adapter timing on this host; no comparator or source-mapped limiter was collected, so it supports no speedup claim.</p>
<p>Assumptions and provenance are in <a href="scenario.json">the scenario manifest</a>. Raw rows: <a href="raw-runs.jsonl">measurement capture</a>; <a href="exact-oracle.json">independent exact oracle</a>; <a href="geometry.json">projected-set source vertices</a>; <a href="environment.txt">host and build environment</a>.</p>
</html>'''
    (root / "index.html").write_text(report)
    print(f"wrote {root/'index.html'} and terminal-projections.svg")


if __name__ == "__main__":
    main()

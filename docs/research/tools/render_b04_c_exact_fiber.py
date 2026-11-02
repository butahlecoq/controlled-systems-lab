"""Render the certified B04-C witness in its two physical state projections."""
from __future__ import annotations

from fractions import Fraction as F
import html
import json
from pathlib import Path

from check_b04_c_exact_fiber import DEFAULT_RECORD, check

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "docs/research/evidence/b04-c-exact-dyadic-v1/trajectory.svg"


def main() -> None:
    check(DEFAULT_RECORD)
    record = json.loads(DEFAULT_RECORD.read_text(encoding="utf-8"))
    states = [[float(F(value)) for value in row]
              for row in record["optimality"]["replay_states"]]
    target = [1200.7, -22.929, 450.2, -7.709]
    panels = [
        {"title": "Oxidizer phase plane", "x": 0, "y": 1,
         "xlabel": "x1 — oxidizer flow (kg/s)", "ylabel": "x2 — oxidizer stock balance (kg)",
         "xmin": 1176.0, "xmax": 1224.0, "target": (target[0], target[1])},
        {"title": "Fuel phase plane", "x": 2, "y": 3,
         "xlabel": "x3 — fuel flow (kg/s)", "ylabel": "x4 — fuel stock balance (kg)",
         "xmin": 432.0, "xmax": 468.0, "target": (target[2], target[3])},
    ]
    width, height = 1120, 620
    panel_width, plot_top, plot_height = 500, 112, 400
    fragments = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 620" role="img" aria-labelledby="title desc">',
        '<title id="title">B04-C exact optimal history in oxidizer and fuel phase planes</title>',
        '<desc id="desc">One exactly certified optimal history is plotted from stage zero to sixteen in both state phase planes. The terminal optimum is unique; the full family of controls is represented by a sixteen-dimensional exact H-polytope and is not visualized as a single curve.</desc>',
        '<rect width="100%" height="100%" fill="#101923"/>',
        '<text x="32" y="42" fill="#f1f5f9" font-family="sans-serif" font-size="24" font-weight="700">B04-C corrected-track optimal history</text>',
        '<text x="32" y="70" fill="#a9bac8" font-family="sans-serif" font-size="14">Exact dyadic profile · representative full-history witness · terminal optimum is a singleton</text>',
    ]
    for index, panel in enumerate(panels):
        left = 48 + index * 540
        plot_left, plot_width = left + 76, panel_width - 94
        ymin = min(row[panel["y"]] for row in states)
        ymax = max(row[panel["y"]] for row in states)
        margin = max((ymax - ymin) * 0.035, 0.01)
        ymin, ymax = ymin - margin, ymax + margin

        def point(x_value: float, y_value: float) -> tuple[float, float]:
            sx = plot_left + (x_value - panel["xmin"]) / (panel["xmax"] - panel["xmin"]) * plot_width
            sy = plot_top + plot_height - (y_value - ymin) / (ymax - ymin) * plot_height
            return sx, sy

        fragments.append(f'<text x="{left+8}" y="98" fill="#e5edf4" font-family="sans-serif" font-size="17" font-weight="600">{html.escape(panel["title"])}</text>')
        for tick in range(5):
            yv = ymin + (ymax - ymin) * tick / 4
            _, sy = point(panel["xmin"], yv)
            fragments.append(f'<line x1="{plot_left}" y1="{sy:.2f}" x2="{plot_left+plot_width}" y2="{sy:.2f}" stroke="#263645" stroke-width="1"/>')
            fragments.append(f'<text x="{plot_left-10}" y="{sy+4:.2f}" text-anchor="end" fill="#91a4b5" font-family="sans-serif" font-size="10">{yv:.4g}</text>')
        for tick in range(5):
            xv = panel["xmin"] + (panel["xmax"] - panel["xmin"]) * tick / 4
            sx, _ = point(xv, ymin)
            fragments.append(f'<line x1="{sx:.2f}" y1="{plot_top}" x2="{sx:.2f}" y2="{plot_top+plot_height}" stroke="#263645" stroke-width="1"/>')
            fragments.append(f'<text x="{sx:.2f}" y="{plot_top+plot_height+18}" text-anchor="middle" fill="#91a4b5" font-family="sans-serif" font-size="10">{xv:.5g}</text>')
        fragments.append(f'<rect x="{plot_left}" y="{plot_top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#718394"/>')
        path = " ".join(("M" if stage == 0 else "L") + f"{point(row[panel['x']], row[panel['y']])[0]:.2f},{point(row[panel['x']], row[panel['y']])[1]:.2f}"
                         for stage, row in enumerate(states))
        fragments.append(f'<path d="{path}" fill="none" stroke="#60c5e8" stroke-width="2.5"/>')
        for stage in (0, 4, 8, 12, 16):
            sx, sy = point(states[stage][panel["x"]], states[stage][panel["y"]])
            fragments.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="4" fill="#60c5e8" stroke="#0c1720" stroke-width="1.5"/>')
            fragments.append(f'<text x="{sx+6:.2f}" y="{sy-6:.2f}" fill="#d3e4ed" font-family="sans-serif" font-size="10">{stage}</text>')
        start = point(states[0][panel["x"]], states[0][panel["y"]])
        end = point(states[-1][panel["x"]], states[-1][panel["y"]])
        published = point(*panel["target"])
        fragments.append(f'<rect x="{start[0]-4:.2f}" y="{start[1]-4:.2f}" width="8" height="8" fill="#f3c969"/>')
        fragments.append(f'<path d="M {published[0]:.2f} {published[1]-6:.2f} L {published[0]+6:.2f} {published[1]:.2f} L {published[0]:.2f} {published[1]+6:.2f} L {published[0]-6:.2f} {published[1]:.2f} Z" fill="#f28c8c" stroke="#101923" stroke-width="1.5"/>')
        fragments.append(f'<circle cx="{end[0]:.2f}" cy="{end[1]:.2f}" r="4" fill="#6ce0a2" stroke="#101923" stroke-width="1.5"/>')
        fragments.append(f'<text x="{plot_left+plot_width/2:.2f}" y="{plot_top+plot_height+44}" text-anchor="middle" fill="#c6d3dd" font-family="sans-serif" font-size="12">{html.escape(panel["xlabel"])}</text>')
        fragments.append(f'<text transform="translate({left+16} {plot_top+plot_height/2}) rotate(-90)" text-anchor="middle" fill="#c6d3dd" font-family="sans-serif" font-size="12">{html.escape(panel["ylabel"])}</text>')
    fragments.extend([
        '<rect x="52" y="570" width="10" height="10" fill="#f3c969"/><text x="68" y="579" fill="#c6d3dd" font-family="sans-serif" font-size="12">initial state</text>',
        '<line x1="187" y1="575" x2="207" y2="575" stroke="#60c5e8" stroke-width="2.5"/><text x="214" y="579" fill="#c6d3dd" font-family="sans-serif" font-size="12">stages 0–16</text>',
        '<circle cx="336" cy="575" r="5" fill="#6ce0a2"/><text x="347" y="579" fill="#c6d3dd" font-family="sans-serif" font-size="12">certified optimal terminal</text>',
        '<path d="M 529 569 L 535 575 L 529 581 L 523 575 Z" fill="#f28c8c"/><text x="542" y="579" fill="#c6d3dd" font-family="sans-serif" font-size="12">published rounded terminal point</text>',
        '<text x="52" y="605" fill="#8fa3b3" font-family="sans-serif" font-size="11">The plotted curve is one member of the full optimal-history fiber; other optimal controls can produce different intermediate trajectories.</text>',
        '</svg>',
    ])
    OUTPUT.write_text("\n".join(fragments) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()

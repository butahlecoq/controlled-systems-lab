#!/usr/bin/env python3
"""Render the labelled 2D example from a saved #944 pipeline record."""

import json
import math
import re
import sys
from pathlib import Path


def theme_tokens():
    stylesheet = Path(__file__).resolve().parents[2] / "docs/examples/examples.css"
    text = stylesheet.read_text(encoding="utf-8")
    root = re.search(r":root\s*\{([^}]+)\}", text)
    print_root = re.search(r"@media\s+print\s*\{\s*:root\s*\{([^}]+)\}", text)
    if root is None or print_root is None:
        raise ValueError("shared examples screen/print themes are required")
    parse = lambda block: dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+)\s*;", block))
    values, printed = parse(root.group(1)), parse(print_root.group(1))
    required = {
        "--page",
        "--surface",
        "--text",
        "--text-muted",
        "--accent",
        "--link",
        "--warm",
        "--line",
    }
    if not required <= values.keys() or not required - {"--link"} <= printed.keys():
        raise ValueError("shared examples screen/print theme tokens are incomplete")
    return values, printed


def main() -> int:
    record_path, output_path = map(Path, sys.argv[1:3])
    print_mode = sys.argv[3:] == ["--print"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    rows = [
        next(
            row
            for row in record["attempts"]
            if row["task"] == task
            and row["vertex_reducer"] == "csl.hull.lp-membership"
            and row["vertex_lp_provider"] == "csl.lp.highs"
            and row["status"] == "completed"
        )
        for task in ("linear", "quadratic")
    ]
    for row in rows:
        assert row["independent_check"]["forward_hull_is_unit_square"]
        assert row["history_recovery_status"] == "completed"
        assert row["independent_check"]["selected_history_in_returned_family"]
    width, height = 900, 620
    left, top, plot_w, plot_h = 110, 100, 520, 400

    def xy(point):
        return left + point[0] * plot_w, top + (1 - point[1]) * plot_h

    vertices = rows[0]["forward_vertices"]
    center = (
        sum(point[0] for point in vertices) / len(vertices),
        sum(point[1] for point in vertices) / len(vertices),
    )
    vertices.sort(key=lambda point: math.atan2(point[1] - center[1], point[0] - center[0]))
    hull = [xy(point) for point in vertices]
    polygon = " ".join(f"{x},{y}" for x, y in hull)
    screen_theme, print_theme = theme_tokens()
    theme = print_theme if print_mode else screen_theme
    first_history_color = theme["--accent"] if print_mode else theme["--link"]
    colors = [first_history_color, theme["--warm"]]
    trajectories = []
    terminal_marks = []
    for index, row in enumerate(rows):
        witness = row["selected_history"]
        initial = xy(witness[:2])
        final = xy(witness[2:4])
        control = witness[4:6]
        x1, y1 = initial
        x2, y2 = final
        trajectories.append(
            f'<line class="history-{index}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{colors[index]}" stroke-width="4" opacity="0.8"/>'
            f'<circle class="history-{index}" cx="{x1}" cy="{y1}" r="5" fill="{colors[index]}"/>'
            f'<text x="{x1 + 10}" y="{y1 - 12 - index * 14}" class="small">u=({control[0]:g},{control[1]:g})</text>'
        )
        terminal_marks.append(
            f'<circle class="terminal" cx="{x2}" cy="{y2}" r="8" fill="{colors[index]}" stroke="{theme["--page"]}" stroke-width="2"/>'
        )

    screen_css = (
        "text{font-family:Inter,system-ui,sans-serif;fill:"
        + theme["--text"]
        + "}"
        + ".title{font-size:24px;font-weight:bold}.label{font-size:16px}.small{font-size:13px}"
        + ".muted{fill:"
        + theme["--text-muted"]
        + "}.svg-bg{fill:"
        + theme["--page"]
        + "}"
        + ".plot{fill:"
        + theme["--surface"]
        + ";stroke:"
        + theme["--line"]
        + "}"
        + ".grid{stroke:"
        + theme["--line"]
        + "}.hull{fill:"
        + theme["--accent"]
        + ";stroke:"
        + theme["--accent"]
        + "}"
    )

    markup = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>{screen_css}</style>
<rect class="svg-bg" width="100%" height="100%" fill="{theme["--page"]}"/>
<text x="40" y="42" class="title">Two-state reachable set and selected control history</text>
<text x="40" y="70" class="label muted">Strategy A, x_next = x + u, x0 = (0,0), u in [0,1]^2</text>
<rect class="plot" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="{theme["--surface"]}" stroke="{theme["--line"]}"/>
<line class="grid" x1="{left}" y1="{top + plot_h / 2}" x2="{left + plot_w}" y2="{top + plot_h / 2}" stroke="{theme["--line"]}"/>
<line class="grid" x1="{left + plot_w / 2}" y1="{top}" x2="{left + plot_w / 2}" y2="{top + plot_h}" stroke="{theme["--line"]}"/>
<polygon class="hull" points="{polygon}" fill="{theme["--accent"]}" fill-opacity="0.2" stroke="{theme["--accent"]}" stroke-width="3"/>
{"".join(trajectories)}{"".join(terminal_marks)}
<text x="{left + plot_w / 2 - 18}" y="{top + plot_h + 34}" class="label">position</text>
<text x="24" y="{top + plot_h / 2}" class="label" transform="rotate(-90 24 {top + plot_h / 2})">velocity</text>
<text x="{left - 18}" y="{top + plot_h + 18}" class="small">0</text><text x="{left + plot_w - 5}" y="{top + plot_h + 18}" class="small">1</text>
<text x="{left - 28}" y="{top + plot_h + 4}" class="small">0</text><text x="{left - 28}" y="{top + 12}" class="small">1</text>
<text x="680" y="145" class="label">Independent checks</text>
<text x="680" y="178" class="small">Reachable hull = unit square</text>
<text x="680" y="203" class="small">Both recovered histories replay</text>
<text x="680" y="228" class="small">LP optimum: (1,0); convex: (0,0)</text>
<text x="680" y="260" class="small">Reducer: csl.hull.lp-membership</text>
<text x="680" y="285" class="small">Vertex LP: csl.lp.highs</text>
<text x="680" y="310" class="small">Converter: Qhull, both directions</text>
<text x="40" y="570" class="small muted">Histories use public recovery and LP selection from the returned terminal-optimal family.</text>
<text x="40" y="592" class="small muted">No complete-family or feedback-optimality claim is made.</text>
</svg>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markup, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

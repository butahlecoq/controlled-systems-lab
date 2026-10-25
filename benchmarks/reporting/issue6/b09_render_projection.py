"""Render saved B09 finite-action results and nonlinear open-loop replays."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ACTIONS = (1.0, 0.75, 0.5, 0.25, 0.0, -0.25, -0.5, -0.75, -1.0)


def nonlinear_replay(action_indices: list[int]) -> list[list[float]]:
    k, p, inv, c1, c2, c3, c4, c5 = 2.5, 30240.0, 360.0, 0.1, -6700.0, 900.0, -15.0, -12.0

    def flows(total_control: float) -> tuple[float, float]:
        km = k - 0.03 * k + c1 * total_control
        delta = km - k
        pp = p + c2 * delta**2 + c3 * delta
        iu = inv + c4 * delta**2 + c5 * delta
        fuel = pp / iu / (1.0 + km)
        return fuel * km, fuel

    oxidizer, fuel = flows(0.0)
    state = [oxidizer, 18100.0, fuel, 7150.0]
    track = [state.copy()]
    accumulated = 0.0
    for action_index in action_indices:
        accumulated += ACTIONS[action_index]
        next_oxidizer, next_fuel = flows(accumulated)
        state = [next_oxidizer, state[1] - 75.0 * state[0],
                 next_fuel, state[3] - 75.0 * state[2]]
        track.append(state.copy())
    return track


def projected_boundary(points: list[list[float]], columns: tuple[int, int]):
    projected = sorted({(point[columns[0]], point[columns[1]]) for point in points})
    if len(projected) < 3:
        return projected

    def cross(origin, left, right):
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower = []
    for point in projected:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(projected):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def render(row: dict, output: Path) -> None:
    vertices = row["winner_terminal_vertices_x1_x2_x3_x4"]
    replay = nonlinear_replay(row["winner_action_indices"])
    width, height = 1240, 760
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#fbfcfd"/>',
             '<style>text{font-family:system-ui,sans-serif;fill:#17212b}.grid{stroke:#dce3e8;stroke-width:1}.axis{stroke:#596a76;stroke-width:1.3}.boundary{fill:#4ba3a7;fill-opacity:.23;stroke:#147d83;stroke-width:2}.vertex{fill:#147d83;fill-opacity:.45}.replay{fill:none;stroke:#d1495b;stroke-width:2.5}.tick{font-size:12px}.label{font-size:14px}.title{font-size:18px;font-weight:650}</style>',
             f'<text x="620" y="28" text-anchor="middle" class="title">A08 source reference, lambda={row["lambda"]}: projections of a 4D model</text>']
    panels = ((0, (0, 2), "Oxidizer flow x1", "Fuel flow x3", "Flow projection"),
              (1, (1, 3), "Oxidizer stock x2", "Fuel stock x4", "Stock projection"))
    for panel_index, columns, xlabel, ylabel, title in panels:
        px = 65 + panel_index * 610
        py, pw, ph = 92, 520, 325
        projected = [(point[columns[0]], point[columns[1]]) for point in vertices]
        path = [(point[columns[0]], point[columns[1]]) for point in replay]
        boundary = projected_boundary(vertices, columns)
        display_path = path if panel_index == 0 else [path[-1]]
        all_x = [p[0] for p in projected + display_path]
        all_y = [p[1] for p in projected + display_path]
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)
        xpad = max((xmax-xmin)*0.08, 1e-6)
        ypad = max((ymax-ymin)*0.08, 1e-6)
        xmin, xmax, ymin, ymax = xmin-xpad, xmax+xpad, ymin-ypad, ymax+ypad

        def point_xy(point):
            return (px + (point[0]-xmin)/(xmax-xmin)*pw,
                    py + ph - (point[1]-ymin)/(ymax-ymin)*ph)

        parts.append(f'<text x="{px+pw/2}" y="66" text-anchor="middle" class="title">{title}</text>')
        for tick in range(6):
            xvalue = xmin + (xmax-xmin)*tick/5
            yvalue = ymin + (ymax-ymin)*tick/5
            sx = px + pw*tick/5
            sy = py + ph - ph*tick/5
            parts.append(f'<line x1="{sx:.2f}" y1="{py}" x2="{sx:.2f}" y2="{py+ph}" class="grid"/>')
            parts.append(f'<line x1="{px}" y1="{sy:.2f}" x2="{px+pw}" y2="{sy:.2f}" class="grid"/>')
            parts.append(f'<text x="{sx:.2f}" y="{py+ph+20}" text-anchor="middle" class="tick">{xvalue:.3g}</text>')
            parts.append(f'<text x="{px-8}" y="{sy+4:.2f}" text-anchor="end" class="tick">{yvalue:.3g}</text>')
        parts.append(f'<line x1="{px}" y1="{py+ph}" x2="{px+pw}" y2="{py+ph}" class="axis"/>')
        parts.append(f'<line x1="{px}" y1="{py}" x2="{px}" y2="{py+ph}" class="axis"/>')
        hull_xy = [point_xy(point) for point in boundary]
        if hull_xy:
            parts.append('<polygon class="boundary" points="' + ' '.join(f'{x:.2f},{y:.2f}' for x,y in hull_xy) + '"/>')
        for point in projected:
            x, y = point_xy(point)
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.2" class="vertex"/>')
        replay_xy = [point_xy(point) for point in display_path]
        if panel_index == 0:
            parts.append('<polyline class="replay" points="' + ' '.join(f'{x:.2f},{y:.2f}' for x,y in replay_xy) + '"/>')
        for point, color in ((path[0], '#1d3557'), (path[-1], '#d1495b')) if panel_index == 0 else ((path[-1], '#d1495b'),):
            x, y = point_xy(point)
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{px+pw/2}" y="{py+ph+40}" text-anchor="middle" class="label">{xlabel}</text>')
        parts.append(f'<text x="{px-48}" y="{py+ph/2}" transform="rotate(-90 {px-48} {py+ph/2})" text-anchor="middle" class="label">{ylabel}</text>')
    parts.extend(['<rect x="105" y="472" width="14" height="14" class="boundary"/>',
                  '<text x="126" y="484" class="label">Projected terminal reachable-set boundary and vertices</text>',
                  '<line x1="685" y1="479" x2="720" y2="479" class="replay"/>',
                  '<text x="728" y="484" class="label">Nonlinear open-loop replay in the flow projection; terminal point in the stock projection</text>',
                  '<text x="620" y="520" text-anchor="middle" class="title">Nonlinear plant stock trajectory over the four 75-second stages</text>'])
    chart_x, chart_y, chart_w, chart_h = 105, 540, 1030, 145
    for tick in range(5):
        x = chart_x + chart_w*tick/4
        parts.append(f'<line x1="{x:.2f}" y1="{chart_y}" x2="{x:.2f}" y2="{chart_y+chart_h}" class="grid"/>')
        parts.append(f'<text x="{x:.2f}" y="{chart_y+chart_h+18}" text-anchor="middle" class="tick">{tick}</text>')
    parts.append(f'<line x1="{chart_x}" y1="{chart_y+chart_h}" x2="{chart_x+chart_w}" y2="{chart_y+chart_h}" class="axis"/>')
    max_stock = max(point[1] for point in replay)
    min_stock = min(point[1] for point in replay)
    max_stock = max(max_stock, max(point[3] for point in replay))
    min_stock = min(min_stock, min(point[3] for point in replay))
    padding = (max_stock-min_stock)*0.06
    min_stock, max_stock = min_stock-padding, max_stock+padding
    for index, color, label in ((1, '#6a4c93', 'Oxidizer stock x2'), (3, '#2a9d8f', 'Fuel stock x4')):
        coords = [(chart_x + (i/(len(replay)-1))*chart_w,
                   chart_y + chart_h - (point[index]-min_stock)/(max_stock-min_stock)*chart_h)
                  for i, point in enumerate(replay)]
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="' +
                     ' '.join(f'{x:.2f},{y:.2f}' for x,y in coords) + '"/>')
        parts.append(f'<line x1="1000" y1="{544 + (index == 3)*22}" x2="1022" y2="{544 + (index == 3)*22}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="1028" y="{548 + (index == 3)*22}" class="tick">{label}</text>')
    parts.append(f'<text x="620" y="{chart_y+chart_h+40}" text-anchor="middle" class="label">Stage (75-second model interval)</text>')
    parts.append('<text x="620" y="746" text-anchor="middle" class="tick">Shaded geometry: uncertain linear model. Curves: deterministic nonlinear replay. One representative plan is shown from the tied optimum family.</text></svg>')
    output.with_suffix('.svg').write_text('\n'.join(parts), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    row = json.loads(args.result.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(row, args.output)


if __name__ == "__main__":
    main()

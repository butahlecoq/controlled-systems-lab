#!/usr/bin/env python3
"""Run the bounded EXP-824 pilot and render its saved record."""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import platform
import subprocess
from pathlib import Path

import check_two_points_box

ROOT = Path(__file__).resolve().parents[3]
MPC05_FIGURE = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2/figure-data.json"
SOURCE_FILES = (
    "include/csl/reachability/finite_plan_box.hpp",
    "src/reachability/finite_plan_box.cpp",
    "include/csl/reachability/finite_plan_zonotope.hpp",
    "src/reachability/finite_plan_zonotope.cpp",
    "include/csl/reachability/finite_plan_parallelotope.hpp",
    "src/reachability/finite_plan_parallelotope.cpp",
    "tests/unit/reachability/finite_plan_parallelotope_tests.cpp",
    "tests/installed/finite_plan_parallelotope_client.cpp",
    "src/reachability/Module.cmake",
    "src/reachability/Tests.cmake",
    "cmake/OptionalReports.cmake",
    "cmake/RunInstalledClient.cmake",
    "tests/contract/public_headers_client.cpp",
    "tests/installed/CMakeLists.txt",
    "tests/installed/finite_plan_zonotope_client.cpp",
    "include/csl/optimization/finite_action_box_minimax.hpp",
    "src/optimization/finite_action_box_minimax.cpp",
    "src/optimization/finite_action_plans.hpp",
    "src/optimization/finite_action_minimax.cpp",
    "benchmarks/reporting/exp824/two_points_box.cpp",
    "benchmarks/reporting/exp824/two_points_fixture.hpp",
    "tests/unit/reachability/finite_plan_zonotope_tests.cpp",
    "scripts/reports/exp824/check_two_points_box.py",
    "scripts/reports/exp824/make_report.py",
    "scripts/reports/stage_issue824_zonotope.py",
    "scripts/reports/visual_examples.py",
    "tests/reporting/test_issue824_zonotope_publication.py",
    ".github/workflows/algorithm-reports.yml",
)
COLORS = ("#458588", "#689d6a", "#d79921", "#b16286")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

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


def zonotope_box(stage: dict, xcoord: int, ycoord: int) -> list[tuple[float, float]]:
    center = stage["center"]
    matrix = stage["generators"]
    radii = [sum(abs(matrix["values"][coordinate * matrix["cols"] + column])
                  for column in range(matrix["cols"])) for coordinate in (xcoord, ycoord)]
    return [(center[xcoord] + sx * radii[0], center[ycoord] + sy * radii[1])
            for sx in (-1, 1) for sy in (-1, 1)]


def projected_zonotope(stage: dict, xcoord: int, ycoord: int) -> list[tuple[float, float]]:
    center = stage["center"]
    matrix = stage["generators"]
    segments = []
    for column in range(matrix["cols"]):
        vector = (matrix["values"][xcoord * matrix["cols"] + column],
                  matrix["values"][ycoord * matrix["cols"] + column])
        if vector == (0.0, 0.0):
            continue
        if vector[1] < 0 or (vector[1] == 0 and vector[0] < 0):
            vector = (-vector[0], -vector[1])
        segments.append(vector)
    segments.sort(key=lambda vector: math.atan2(vector[1], vector[0]))
    point = [center[xcoord] - sum(vector[0] for vector in segments),
             center[ycoord] - sum(vector[1] for vector in segments)]
    vertices = [tuple(point)]
    for vector in segments:
        point[0] += 2 * vector[0]
        point[1] += 2 * vector[1]
        vertices.append(tuple(point))
    for vector in segments:
        point[0] -= 2 * vector[0]
        point[1] -= 2 * vector[1]
        vertices.append(tuple(point))
    return hull(vertices)


def projected_parallelotope(method: dict, stage_index: int,
                            xcoord: int, ycoord: int) -> list[tuple[float, float]]:
    trace=method["stages"]
    stage = trace["stages"][stage_index]
    frame = trace["frame"]
    n = frame["rows"]
    q = frame["values"]
    center_y = [(lo + hi) / 2 for lo, hi in zip(stage["lower"], stage["upper"])]
    radius_y = [(hi - lo) / 2 for lo, hi in zip(stage["lower"], stage["upper"])]
    center = [sum(q[row*n+col] * center_y[col] for col in range(n)) for row in range(n)]
    generators = [(q[xcoord*n+col] * radius_y[col], q[ycoord*n+col] * radius_y[col])
                  for col in range(n)]
    points = []
    for signs in itertools.product((-1, 1), repeat=n):
        points.append((center[xcoord] + sum(sign*g[0] for sign, g in zip(signs, generators)),
                       center[ycoord] + sum(sign*g[1] for sign, g in zip(signs, generators))))
    return hull(points)


def svg_figure(result: dict, check: dict, mpc_figure: dict) -> str:
    geometry = mpc_figure["reachability_geometry"]
    forward = geometry["forward_layers"]
    backward = geometry["robust_backward_layers"]
    boxes = result["box_method"]["stages"]
    zonotope_tracks = [(result["zonotope_method"]["stages"], "#458588")]
    parallelotope_method = result.get("parallelotope_method")
    trajectories = {
        "Exact finite minimax replay": (check["exact_reference_state_path"], "#076678", ""),
        "Box selected plan replay": (check["selected_plan_state_path"], "#af3a03", "9 5"),
    }
    if "zonotope_minimax_method" in result:
        selection = result["zonotope_minimax_method"]
        selected_trace = selection["plan_attempts"][selection["selected_candidate_attempt_index"]]["stages"]
        zonotope_tracks.append((selected_trace, "#b16286"))
        trajectories["Zonotope-selected plan replay"] = (
            selection["selected_replay"]["path"], "#b16286", "2 4")
    panels = ((0, 1, "Player 1 phase plane", "x1 position (m)", "x2 velocity (m/s)"),
              (2, 3, "Player 2 phase plane", "x3 position (m)", "x4 velocity (m/s)"))
    width, height = 1440, 820
    panel_boxes = ((68, 118, 620, 540), (752, 118, 620, 540))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">TwoPoints stagewise outer boxes, zonotopes, and minimax geometry</title>',
           '<desc id="desc">Two player phase-plane plots show exact forward sets, finite backward-winning states, intersections, stagewise interval boxes and actual zonotope projections, plus replayed minimax trajectories.</desc>',
           '<rect width="100%" height="100%" fill="#fbf1c7"/>',
           '<text x="720" y="38" text-anchor="middle" font-family="sans-serif" font-size="23" font-weight="700" fill="#282828">TwoPointsOnParallelLines · 3-stage finite adaptation</text>',
           '<text x="720" y="67" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#504945">Exact finite-game geometry and stagewise 4D outer boxes, zonotopes, and parallelotopes in each player&apos;s phase plane</text>']

    for panel_index, ((xcoord, ycoord, title, xlabel, ylabel), (left, top, plot_width, plot_height)) in enumerate(zip(panels, panel_boxes)):
        points_for_bounds = []
        for layer in forward + backward:
            points_for_bounds.extend((state[xcoord], state[ycoord]) for state in layer)
        for stage in boxes:
            points_for_bounds.extend(((stage["lower"][xcoord], stage["lower"][ycoord]),
                                      (stage["upper"][xcoord], stage["upper"][ycoord])))
        for stages, _ in zonotope_tracks:
            for stage in stages:
                points_for_bounds.extend(zonotope_box(stage, xcoord, ycoord))
        if parallelotope_method:
            for stage_index in range(len(parallelotope_method["stages"]["stages"])):
                points_for_bounds.extend(projected_parallelotope(parallelotope_method, stage_index, xcoord, ycoord))
        for path, _, _ in trajectories.values():
            points_for_bounds.extend((state[xcoord], state[ycoord]) for state in path)
        xmin = min(point[0] for point in points_for_bounds)
        xmax = max(point[0] for point in points_for_bounds)
        ymin = min(point[1] for point in points_for_bounds)
        ymax = max(point[1] for point in points_for_bounds)
        xpad = max((xmax - xmin) * 0.08, 0.05)
        ypad = max((ymax - ymin) * 0.10, 0.05)
        xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad

        def xy(point):
            px = left + (point[0] - xmin) / (xmax - xmin) * plot_width
            py = top + plot_height - (point[1] - ymin) / (ymax - ymin) * plot_height
            return px, py

        out.append(f'<text x="{left + plot_width / 2}" y="{top - 26}" text-anchor="middle" font-family="sans-serif" font-size="18" font-weight="700" fill="#282828">{html.escape(title)}</text>')
        out.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f9f5d7" stroke="#665c54"/>')
        for tick in range(5):
            gx = left + plot_width * tick / 4
            gy = top + plot_height * tick / 4
            xv = xmin + (xmax - xmin) * tick / 4
            yv = ymax - (ymax - ymin) * tick / 4
            out.append(f'<path d="M {gx:.2f} {top} V {top + plot_height} M {left} {gy:.2f} H {left + plot_width}" stroke="#d5c4a1" stroke-width="1"/>')
            fmt_tick = lambda value: "0" if abs(value) < 1e-10 else f"{value:.3g}"
            out.append(f'<text x="{gx:.2f}" y="{top + plot_height + 18}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#665c54">{fmt_tick(xv)}</text>')
            out.append(f'<text x="{left - 8}" y="{gy + 4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#665c54">{fmt_tick(yv)}</text>')
        out.append(f'<text x="{left + plot_width / 2}" y="{top + plot_height + 43}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#282828">{html.escape(xlabel)}</text>')
        out.append(f'<text transform="translate({left - 48} {top + plot_height / 2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#282828">{html.escape(ylabel)}</text>')

        for stage_index, layer in enumerate(forward):
            projected = [(state[xcoord], state[ycoord]) for state in layer]
            boundary = hull(projected)
            if len(boundary) >= 3:
                path_string = " ".join(("M" if index == 0 else "L") + f" {xy(point)[0]:.2f} {xy(point)[1]:.2f}" for index, point in enumerate(boundary)) + " Z"
                out.append(f'<path d="{path_string}" fill="{COLORS[stage_index]}" fill-opacity="0.10" stroke="{COLORS[stage_index]}" stroke-width="1.4"/>')
            elif boundary:
                px, py = xy(boundary[0])
                out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="{COLORS[stage_index]}"/>')

        for stage_index, (f_layer, b_layer) in enumerate(zip(forward, backward)):
            intersection = set(map(tuple, f_layer)) & set(map(tuple, b_layer))
            for state in b_layer:
                px, py = xy((state[xcoord], state[ycoord]))
                out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.2" fill="#8f3f71" fill-opacity="0.42"/>')
            for state in intersection:
                px, py = xy((state[xcoord], state[ycoord]))
                out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4.2" fill="#282828" stroke="#fbf1c7" stroke-width="1"/>')

        for stages, color in zonotope_tracks:
            for stage in stages:
                boundary = projected_zonotope(stage, xcoord, ycoord)
                if len(boundary) >= 3:
                    path_string = " ".join(("M" if index == 0 else "L") +
                        f" {xy(point)[0]:.2f} {xy(point)[1]:.2f}" for index, point in enumerate(boundary)) + " Z"
                    out.append(f'<path d="{path_string}" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="2"/>')
                elif boundary:
                    px, py = xy(boundary[0])
                    out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3" fill="{color}"/>')

        if parallelotope_method:
            for stage_index in range(len(parallelotope_method["stages"]["stages"])):
                boundary=projected_parallelotope(parallelotope_method,stage_index,xcoord,ycoord)
                if len(boundary)>=3:
                    path_string=" ".join(("M" if index==0 else "L")+
                        f" {xy(point)[0]:.2f} {xy(point)[1]:.2f}" for index,point in enumerate(boundary))+" Z"
                    out.append(f'<path d="{path_string}" fill="#d3869b" fill-opacity="0.10" stroke="#8f3f71" stroke-width="2" stroke-dasharray="3 3"/>')

        for stage_index, stage in enumerate(boxes):
            p1 = xy((stage["lower"][xcoord], stage["lower"][ycoord]))
            p2 = xy((stage["upper"][xcoord], stage["upper"][ycoord]))
            rx, ry = min(p1[0],p2[0]), min(p1[1],p2[1])
            rw, rh = max(abs(p2[0]-p1[0]),1), max(abs(p2[1]-p1[1]),1)
            out.append(f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{rw:.2f}" height="{rh:.2f}" fill="#fe8019" fill-opacity="0.08" stroke="#af3a03" stroke-width="2" stroke-dasharray="7 4"/>')

        for _, (path, color, dash) in trajectories.items():
            projected = [xy((state[xcoord], state[ycoord])) for state in path]
            coords = " ".join(("M" if index == 0 else "L") + f" {point[0]:.2f} {point[1]:.2f}" for index, point in enumerate(projected))
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(f'<path d="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash_attr}/>')
            for px, py in projected:
                out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.4" fill="{color}"/>')

    legend = [("Exact forward reachable hulls", COLORS[1], "fill"),
              ("Robust backward-winning states", "#8f3f71", "dot"),
              ("Forward/backward intersection", "#282828", "dot"),
              ("Stagewise outer interval box", "#af3a03", "dash"),
              ("Stagewise outer zonotope projection", "#458588", "fill"),
              ("Exact finite minimax replay", "#076678", "line"),
              ("Box-selected plan replay", "#af3a03", "line-dash")]
    if "zonotope_minimax_method" in result:
        legend.insert(5, ("Zonotope-selected plan zonotope", "#b16286", "fill"))
        legend.append(("Zonotope-selected plan replay", "#b16286", "line-dash"))
    if parallelotope_method:
        legend.insert(5,("Fixed-frame outer parallelotope", "#8f3f71", "fill"))
    x_positions = (50, 400, 750, 1100)
    for index, (label, color, kind) in enumerate(legend):
        x = x_positions[index % len(x_positions)]
        y = 730 + 28 * (index // len(x_positions))
        if kind == "dot":
            out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
        else:
            dash = ' stroke-dasharray="6 4"' if kind in ("dash", "line-dash") else ""
            fill = color if kind == "fill" else "none"
            out.append(f'<path d="M {x-10} {y} H {x+10}" stroke="{color}" stroke-width="3" fill="{fill}"{dash}/>')
        out.append(f'<text x="{x+14}" y="{y+4}" font-family="sans-serif" font-size="11" fill="#282828">{html.escape(label)}</text>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def planar_svg(result: dict) -> str:
    example = result["planar_example"]
    width, height = 760, 500
    left, right, top, bottom = 88, 716, 72, 410

    def project(point):
        return (left + (point[0] + 2.5) / 5.0 * (right - left),
                bottom - (point[1] + 1.5) / 3.0 * (bottom - top))

    def path(points):
        coords = [project(point) for point in points]
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in coords) + " Z"

    initial = example["initial_vertices"]
    reachable = example["exact_reachable_vertices"]
    zone = projected_zonotope(example["stages"][1], 0, 1)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Planar zonotope propagation for a diagonal linear map</title>',
           '<desc id="desc">The square [-1,1] squared maps under diag(2,1) to the exact rectangle [-2,2] by [-1,1], enclosed by the saved zonotope propagation result.</desc>',
           '<rect width="100%" height="100%" fill="#fbf1c7"/>',
           '<text x="380" y="30" text-anchor="middle" font-family="sans-serif" font-size="20" fill="#282828">A 2D linear image enclosed by zonotope propagation</text>']
    for tick in (-2, -1, 0, 1, 2):
        x, _ = project((tick, 0))
        out.extend((f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#d5c4a1"/>',
                    f'<text x="{x:.2f}" y="{bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#504945">{tick}</text>'))
    for tick in (-1, 0, 1):
        _, y = project((0, tick))
        out.extend((f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#d5c4a1"/>',
                    f'<text x="{left-14}" y="{y+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#504945">{tick}</text>'))
    out.extend((f'<path d="{path(zone)}" fill="#458588" fill-opacity="0.24" stroke="#076678" stroke-width="3"/>',
                f'<path d="{path(initial)}" fill="#d5c4a1" fill-opacity="0.38" stroke="#665c54" stroke-width="2" stroke-dasharray="7 4"/>'))
    for point in reachable:
        x, y = project(point)
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#282828" stroke="#fbf1c7" stroke-width="1"/>')
    out.extend((f'<text x="{(left+right)/2}" y="{bottom+54}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#282828">x₁</text>',
                f'<text x="24" y="{(top+bottom)/2}" transform="rotate(-90 24 {(top+bottom)/2})" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#282828">x₂</text>',
                '<rect x="92" y="456" width="20" height="12" fill="#d5c4a1" fill-opacity="0.38" stroke="#665c54" stroke-dasharray="5 3"/>',
                '<text x="118" y="467" font-family="sans-serif" font-size="12" fill="#282828">Initial square</text>',
                '<rect x="300" y="456" width="20" height="12" fill="#458588" fill-opacity="0.24" stroke="#076678" stroke-width="2"/>',
                '<text x="326" y="467" font-family="sans-serif" font-size="12" fill="#282828">Propagated outer zonotope</text>',
                '<circle cx="575" cy="462" r="5" fill="#282828"/><text x="588" y="467" font-family="sans-serif" font-size="12" fill="#282828">Exact reachable corners</text>',
                '</svg>'))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {output}")
    completed = subprocess.run([str(args.executable.resolve())], check=True,
                               capture_output=True, text=True)
    result = json.loads(completed.stdout)
    build_dir = args.build_dir.resolve()
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER") or "unknown"
    compiler_version = subprocess.run([compiler, "--version"], check=True,
                                      capture_output=True, text=True).stdout.splitlines()[0]
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout
    capture = {
        "schema": "csl.issue824-two-points-box-capture/2",
        "source_commit": commit,
        "source_tree_clean_before_report_generation": not bool(status),
        "source_status_before_report_generation": status.splitlines(),
        "source_files_sha256": {name: sha256(ROOT / name) for name in SOURCE_FILES},
        "exact_geometry_reference": {
            "report_id": "mpc05-causal-tree-pilot-v2",
            "figure_data_sha256": sha256(MPC05_FIGURE),
        },
        "build": {
            "directory": str(build_dir),
            "configuration": cache_value(cache, "CMAKE_BUILD_TYPE"),
            "compiler": compiler,
            "compiler_version": compiler_version,
            "generator": cache_value(cache, "CMAKE_GENERATOR"),
            "highs": cache_value(cache, "CSL_ENABLE_HIGHS"),
            "qhull": cache_value(cache, "CSL_ENABLE_QHULL"),
        },
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine()},
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "capture.json").write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    check = check_two_points_box.main(result_path)
    (output / "check.json").write_text(json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_figure = json.loads(MPC05_FIGURE.read_text(encoding="utf-8"))
    figure = {"schema":"csl.issue824-two-points-box-figure/2",
              "source_geometry_report":"mpc05-causal-tree-pilot-v2",
              "geometry":source_figure["reachability_geometry"],
              "exact_check":check,
              "box_stages":result["box_method"]["stages"],
              "zonotope_stages":result["zonotope_method"]["stages"],
              "planar_example":result["planar_example"]}
    (output / "figure-data.json").write_text(json.dumps(figure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    svg = svg_figure(result, check, source_figure)
    (output / "projections.svg").write_text(svg, encoding="utf-8")
    planar_figure = planar_svg(result)
    (output / "planar-example.svg").write_text(planar_figure, encoding="utf-8")
    exact_value = result["exact_reference"]["finite_minimax_value"]
    approx_value = result["box_method"]["full_catalogue_replay_value"]
    planar_html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Planar zonotope propagation example · Issue 824</title>
<style>body{{max-width:960px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.55 system-ui}}h1,h2{{color:#3c3836}}svg{{width:100%;height:auto}}code,pre{{background:#f9f5d7;padding:.15rem .3rem}}a{{color:#076678}}</style>
<h1>A planar linear image enclosed by zonotope propagation</h1><p>This supported two-state example starts with the square <code>[-1,1] × [-1,1]</code>, applies one stage <code>x⁺ = diag(2,1)x</code>, with zero control and zero disturbance, and uses universal safe sets. The output set is the axis-aligned rectangle <code>[-2,2] × [-1,1]</code>.</p>
{planar_figure}<p><strong>Checked result:</strong> the independently reconstructed four exact image vertices are <code>{result['planar_example']['exact_reachable_vertices']}</code>. The saved propagation trace has center <code>{result['planar_example']['stages'][1]['center']}</code> and outward-rounded coordinate generator radii at least <code>[2,1]</code>. Its axis-aligned generators form an outer rectangle containing all exact image vertices. This inclusion check applies to this simple planar fixture; the four-state TwoPoints trace has only coordinate-bound checks and no full-dimensional membership proof.</p>
<h2>Complete minimal input</h2><pre>State dimension: 2; one discrete stage from t=0 to t=1
A = [[2, 0], [0, 1]]; B = [[0], [0]]; E = [[0, 0], [0, 0]]; offset = [0, 0]
Initial vertices: {result['planar_example']['initial_vertices']}
Control: [0]; disturbance: singleton [0, 0]; safe sets: universal</pre>
<h2>Reproduce</h2><pre>cmake --preset dev -DCSL_BUILD_ISSUE824_BOX_REPORT=ON
cmake --build build/dev --target csl_issue824_box_minimax_report --parallel 4
python3 scripts/reports/exp824/make_report.py --executable build/dev/csl_issue824_box_minimax_report \\
  --build-dir build/dev --output reports/algorithm-results/issue824-two-points-zonotope-pilot-v2</pre>
<p>Algorithm source commit: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{commit}"><code>{commit}</code></a>. See the <a href="result.json">raw saved result</a>, <a href="check.json">independent checker record</a>, <a href="README.md">complete report and limits</a>, <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{commit}/src/reachability/finite_plan_zonotope.cpp">propagation source</a>, and <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{commit}/tests/unit/reachability/finite_plan_zonotope_tests.cpp">analytic fixture test</a>.</p></html>'''
    (output / "planar-example.html").write_text(planar_html, encoding="utf-8")
    html_page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · TwoPoints box and zonotope pilot</title>
<style>body{{max-width:1200px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.5 system-ui}}h1,h2{{color:#3c3836}}.metric{{display:inline-block;margin:.4rem 1rem .4rem 0;padding:.7rem;background:#f9f5d7;border:1px solid #d5c4a1;border-radius:6px}}svg{{width:100%;height:auto}}code{{background:#f9f5d7;padding:.1rem .3rem}}a{{color:#076678}}</style>
<h1>TwoPointsOnParallelLines: stagewise approximation pilot</h1><p>This is a three-stage finite adaptation of the source differential-game environment. It compares the box-selected fixed-plan minimax run with an outer zonotope recurrence of that same plan and the exact finite-catalog reference. The upstream continuous-action RL problem is not reproduced.</p>
<p><span class="metric">Exact finite minimax: <b>{exact_value:.8f}</b></span><span class="metric">Box-selected plan replay: <b>{approx_value:.8f}</b></span><span class="metric">Box terminal score: <b>{result['box_method']['terminal_box_maximum']:.8f}</b></span></p>
{svg}
<h2>Evidence and limits</h2><p>The independent checker reconstructs the exact rational finite game, verifies every selected-plan state is within the recorded box and within the zonotope coordinate bounds, and replays all disturbance histories to check the worst-case witness. The coordinate checks do not prove full four-dimensional zonotope membership. A separate <a href="planar-example.html">complete planar zonotope example</a> checks all exact vertices of an axis-aligned linear image. The box objective score is diagnostic, not a validated global optimality certificate. The figure also overlays exact forward hulls, backward-winning nodes, and intersections from the pinned MPC-05 geometry report.</p>
<p><a href="result.json">Raw result</a> · <a href="check.json">Independent check</a> · <a href="figure-data.json">Figure data</a> · <a href="planar-example.html">Supported 2D example</a></p></html>'''
    (output / "index.html").write_text(html_page, encoding="utf-8")
    readme = f'''# EXP-824 TwoPoints box and zonotope pilot

This exploratory bundle compares a stagewise four-dimensional interval-box fixed-plan selector with an outer zonotope recurrence of the same selected plan, alongside the exhaustive finite-catalog fixed-plan minimax reference for `TwoPointsOnParallelLines`. The adaptation has three 0.1-second stages, controls `(-2.5, 0, 2.5)`, disturbances `(-1, 0, 1)`, initial state `(4.5, 0, 0, 0)`, and terminal squared position gap.

The exact finite minimax value is `{exact_value:.8f}`. The box-selected plan is `{result['box_method']['selected_controls']}`; its full-catalogue replay is `{approx_value:.8f}`, and its terminal box maximum is `{result['box_method']['terminal_box_maximum']:.14f}`. The zonotope recurrence propagates that same fixed plan and records center and generator matrices at all four state stages. The independent checker verifies every exact finite-catalogue state lies within the zonotope coordinate bounds; it does not certify full zonotope membership in four dimensions.

The box maximum is a numerical diagnostic over terminal box corners. The zonotope recurrence includes outward rounding slack and is a numerical outer enclosure. The companion planar example checks complete inclusion for a two-dimensional axis-aligned image. This pilot does not claim validated objective bounds, continuous RL reproduction, zonotope-based minimax selection, feedback optimality, or ellipsoid and non-box parallelotope propagation. No performance measurement was collected. The figure combines this run's box and zonotope projections and replay with exact forward/backward geometry from the separate MPC-05 finite adaptation report.

## Supported representation and cost

The implementation accepts bounded V-representation or singleton initial/disturbance sets and universal state constraints. For state dimension `n`, control dimension `m`, disturbance dimension `q`, horizon `H`, `A` actions per stage, and `P=A^H` plans, interval propagation costs `O(H n(n+m+q))` per plan. The terminal score enumerates `2^n` box corners and evaluates the objective at each; for quadratic objectives each evaluation costs `O(n^2)`. The selected plan is replayed over `R=|I|∏|D_k|` initial/disturbance histories at `O(R H n(n+m+q))` arithmetic cost. Overall work is `O(P[Hn(n+m+q)+2^n C_obj]+RHn(n+m+q))`, where `C_obj` is the cost of one objective evaluation.

Memory is `O(PH + Hn + 2^n n + K H n + ∑|D_k|q)` for saved plan scores, stage boxes, terminal corners, exact replay stages, and disturbance catalogues, where `K` is the per-stage exact-point limit. The witness search retains one path of length `H`; its history-count limit `R` bounds work rather than stored histories. Explicit caller limits bound plan count, exact points per stage, full replay histories, and terminal corners. Both action-plan and corner enumeration are exponential in horizon and state dimension, respectively; this four-state, three-stage example does not establish practical scaling beyond this fixture.

The zonotope recurrence itself keeps `G_k` state generators, `W_k` disturbance generators, and adds at most `n` outward-rounding generators at each `n`-state stage. One step costs `O(n²G_k + nqW_k + n(n+m+q))` arithmetic operations and stores `O(n(G_k+W_k+n))` generator values; the full trace stores `O(HnK)` values under the caller's per-stage generator cap `K`. No generator reduction is performed: a stage that would exceed `K` returns `Unsupported`. These are operation-count estimates, not measured performance claims.

## Reproduce

From the repository root, configure and build the Release report driver:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_BOX_REPORT=ON
cmake --build build/dev --target csl_issue824_box_minimax_report --parallel 4
python3 scripts/reports/exp824/make_report.py \\
  --executable build/dev/csl_issue824_box_minimax_report \\
  --build-dir build/dev \\
  --output reports/algorithm-results/issue824-two-points-zonotope-pilot-v2
```

Run the independent smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_box_minimax_report_smoke$' --output-on-failure
```

`capture.json` identifies the solver source commit, source hashes, build profile, and exact geometry reference. `check.json` records independent rational transitions, objective replay, and stage coordinate checks. `result.json` stores every finite-plan score, the selected plan's worst-case disturbance path, the TwoPoints zonotope stages, and the planar fixture. `projections.svg` shows exact reachable and backward-winning sets, intersections, boxes, true zonotope projections, and trajectories in both player phase planes `(x1,x2)` and `(x3,x4)`. `planar-example.svg` and `planar-example.html` provide the complete supported 2D example and analytic inclusion check.

This pilot is not the complete acceptance scope of issue #824. The report workflow stages the versioned bundle and its 2D companion in the published Pages gallery; check the PR and issue discussion for the verified live URL after main-only deployment.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in manifest.items()), encoding="ascii")


if __name__ == "__main__":
    main()

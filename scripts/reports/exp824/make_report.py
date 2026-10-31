#!/usr/bin/env python3
"""Run the bounded EXP-824 pilot and render its saved record."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import subprocess
from pathlib import Path

import check_two_points_box

ROOT = Path(__file__).resolve().parents[3]
MPC05_FIGURE = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2/figure-data.json"
SOURCE_FILES = (
    "include/csl/reachability/finite_plan_box.hpp",
    "src/reachability/finite_plan_box.cpp",
    "include/csl/optimization/finite_action_box_minimax.hpp",
    "src/optimization/finite_action_box_minimax.cpp",
    "src/optimization/finite_action_plans.hpp",
    "src/optimization/finite_action_minimax.cpp",
    "benchmarks/reporting/exp824/two_points_box.cpp",
    "benchmarks/reporting/exp824/two_points_fixture.hpp",
    "scripts/reports/exp824/check_two_points_box.py",
    "scripts/reports/exp824/make_report.py",
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


def svg_figure(result: dict, check: dict, mpc_figure: dict) -> str:
    geometry = mpc_figure["reachability_geometry"]
    forward = geometry["forward_layers"]
    backward = geometry["robust_backward_layers"]
    boxes = result["box_method"]["stages"]
    trajectories = {
        "Exact finite minimax replay": (check["exact_reference_state_path"], "#076678", ""),
        "Box selected plan replay": (check["selected_plan_state_path"], "#af3a03", "9 5"),
    }
    panels = ((0, 1, "Player 1 phase plane", "x1 position (m)", "x2 velocity (m/s)"),
              (2, 3, "Player 2 phase plane", "x3 position (m)", "x4 velocity (m/s)"))
    width, height = 1440, 760
    panel_boxes = ((68, 118, 620, 540), (752, 118, 620, 540))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">TwoPoints stagewise outer boxes and minimax geometry</title>',
           '<desc id="desc">Two player phase-plane plots show exact forward sets, finite backward-winning states, their intersections, stagewise interval boxes, and replayed minimax trajectories.</desc>',
           '<rect width="100%" height="100%" fill="#fbf1c7"/>',
           '<text x="720" y="38" text-anchor="middle" font-family="sans-serif" font-size="23" font-weight="700" fill="#282828">TwoPointsOnParallelLines · 3-stage finite adaptation</text>',
           '<text x="720" y="67" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#504945">Exact finite-game geometry and stagewise 4D outer boxes, projected into each player&apos;s phase plane</text>']

    for panel_index, ((xcoord, ycoord, title, xlabel, ylabel), (left, top, plot_width, plot_height)) in enumerate(zip(panels, panel_boxes)):
        points_for_bounds = []
        for layer in forward + backward:
            points_for_bounds.extend((state[xcoord], state[ycoord]) for state in layer)
        for stage in boxes:
            points_for_bounds.extend(((stage["lower"][xcoord], stage["lower"][ycoord]),
                                      (stage["upper"][xcoord], stage["upper"][ycoord])))
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
              ("Exact finite minimax replay", "#076678", "line"),
              ("Box-selected plan replay", "#af3a03", "line-dash")]
    y = 720
    x_positions = (45, 285, 525, 765, 1005, 1220)
    for (label, color, kind), x in zip(legend, x_positions):
        if kind == "dot":
            out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
        else:
            dash = ' stroke-dasharray="6 4"' if kind in ("dash", "line-dash") else ""
            fill = color if kind == "fill" else "none"
            out.append(f'<path d="M {x-10} {y} H {x+10}" stroke="{color}" stroke-width="3" fill="{fill}"{dash}/>')
        out.append(f'<text x="{x+14}" y="{y+4}" font-family="sans-serif" font-size="11" fill="#282828">{html.escape(label)}</text>')
    out.append('</svg>')
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
        "schema": "csl.issue824-two-points-box-capture/1",
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
    figure = {"schema":"csl.issue824-two-points-box-figure/1",
              "source_geometry_report":"mpc05-causal-tree-pilot-v2",
              "geometry":source_figure["reachability_geometry"],
              "exact_check":check,
              "box_stages":result["box_method"]["stages"]}
    (output / "figure-data.json").write_text(json.dumps(figure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    svg = svg_figure(result, check, source_figure)
    (output / "projections.svg").write_text(svg, encoding="utf-8")
    exact_value = result["exact_reference"]["finite_minimax_value"]
    approx_value = result["box_method"]["full_catalogue_replay_value"]
    html_page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · TwoPoints interval-box minimax pilot</title>
<style>body{{max-width:1200px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.5 system-ui}}h1,h2{{color:#3c3836}}.metric{{display:inline-block;margin:.4rem 1rem .4rem 0;padding:.7rem;background:#f9f5d7;border:1px solid #d5c4a1;border-radius:6px}}svg{{width:100%;height:auto}}code{{background:#f9f5d7;padding:.1rem .3rem}}a{{color:#076678}}</style>
<h1>TwoPointsOnParallelLines: stagewise box minimax pilot</h1><p>This is a three-stage finite adaptation of the source differential-game environment. It compares full-state stagewise outer interval boxes with the exact finite-catalog fixed-plan minimax reference. The upstream continuous-action RL problem is not reproduced.</p>
<p><span class="metric">Exact finite minimax: <b>{exact_value:.8f}</b></span><span class="metric">Box-selected plan replay: <b>{approx_value:.8f}</b></span><span class="metric">Box terminal score: <b>{result['box_method']['terminal_box_maximum']:.8f}</b></span></p>
{svg}
<h2>Evidence and limits</h2><p>The independent checker reconstructs the exact rational finite game from integer transitions, verifies every selected-plan stage state is inside the recorded four-dimensional box, and replays all disturbance histories to check the reported worst-case witness. The box objective score is a numerical maximum over terminal box corners; it is diagnostic and is not a validated global optimality certificate. The figure overlays exact forward hulls and finite backward-winning nodes from the pinned MPC-05 geometry report; intersection markers are exact finite state matches.</p>
<p><a href="result.json">Raw result</a> · <a href="check.json">Independent check</a> · <a href="figure-data.json">Figure data</a></p></html>'''
    (output / "index.html").write_text(html_page, encoding="utf-8")
    readme = f'''# EXP-824 TwoPoints box minimax pilot

This exploratory bundle compares a stagewise four-dimensional interval-box selector with the exhaustive finite-catalog fixed-plan minimax reference for `TwoPointsOnParallelLines`. The adaptation has three 0.1-second stages, controls `(-2.5, 0, 2.5)`, disturbances `(-1, 0, 1)`, initial state `(4.5, 0, 0, 0)`, and terminal squared position gap.

The exact finite minimax value is `{exact_value:.8f}`. The box-selected plan is `{result['box_method']['selected_controls']}`; its full-catalogue replay is `{approx_value:.8f}`, and its terminal box maximum is `{result['box_method']['terminal_box_maximum']:.14f}`. The selected box trace contains every exact finite-catalogue state at every stage according to the independent rational checker.

The box maximum is a numerical diagnostic over terminal box corners. This pilot does not claim validated objective bounds, continuous RL reproduction, feedback optimality, or support for ellipsoids, parallelotopes, and zonotopes. No performance measurement was collected. The figure combines this run's boxes and replay with exact forward/backward geometry from the separate MPC-05 finite adaptation report.

## Supported representation and cost

The implementation accepts bounded V-representation or singleton initial/disturbance sets and universal state constraints. For state dimension `n`, control dimension `m`, disturbance dimension `q`, horizon `H`, `A` actions per stage, and `P=A^H` plans, interval propagation costs `O(H n(n+m+q))` per plan. The terminal score enumerates `2^n` box corners and evaluates the objective at each; for quadratic objectives each evaluation costs `O(n^2)`. The selected plan is replayed over `R=|I|∏|D_k|` initial/disturbance histories at `O(R H n(n+m+q))` arithmetic cost. Overall work is `O(P[Hn(n+m+q)+2^n C_obj]+RHn(n+m+q))`, where `C_obj` is the cost of one objective evaluation.

Memory is `O(PH + Hn + 2^n n + K H n + ∑|D_k|q)` for saved plan scores, stage boxes, terminal corners, exact replay stages, and disturbance catalogues, where `K` is the per-stage exact-point limit. The witness search retains one path of length `H`; its history-count limit `R` bounds work rather than stored histories. Explicit caller limits bound plan count, exact points per stage, full replay histories, and terminal corners. Both action-plan and corner enumeration are exponential in horizon and state dimension, respectively; this four-state, three-stage example does not establish practical scaling beyond this fixture.

## Reproduce

From the repository root, configure and build the Release report driver:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_BOX_REPORT=ON
cmake --build build/dev --target csl_issue824_box_minimax_report --parallel 4
python3 scripts/reports/exp824/make_report.py \\
  --executable build/dev/csl_issue824_box_minimax_report \\
  --build-dir build/dev \\
  --output reports/algorithm-results/issue824-two-points-box-pilot-v2
```

Run the independent smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_box_minimax_report_smoke$' --output-on-failure
```

`capture.json` identifies the clean solver source commit, source hashes, build profile, and exact geometry reference. `check.json` records independent rational transitions, objective replay, and stage enclosure results. `result.json` stores every finite-plan score and the selected plan's worst-case disturbance path. `projections.svg` shows both player phase planes `(x1,x2)` and `(x3,x4)`.

This pilot is not the complete acceptance scope of issue #824. Publication through the site and a live URL check remain pending.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in manifest.items()), encoding="ascii")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Capture and render the issue #824 zonotope minimax selection pilot."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_zonotope_minimax
shared_spec = importlib.util.spec_from_file_location(
    "issue824_shared_make_report", Path(__file__).with_name("make_report.py"))
if shared_spec is None or shared_spec.loader is None:
    raise RuntimeError("cannot load the shared issue 824 report renderer")
shared = importlib.util.module_from_spec(shared_spec)
shared_spec.loader.exec_module(shared)

ROOT = Path(__file__).resolve().parents[3]
MPC05_FIGURE = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2/figure-data.json"
SOURCE_FILES = (
    "CMakeLists.txt",
    "cmake/OptionalReports.cmake",
    "cmake/RunInstalledClient.cmake",
    "include/csl/optimization/finite_action_zonotope_minimax.hpp",
    "src/optimization/finite_action_box_minimax.cpp",
    "src/optimization/finite_action_replay.cpp",
    "src/optimization/finite_action_replay.hpp",
    "src/optimization/finite_action_zonotope_minimax.cpp",
    "src/optimization/finite_action_plans.hpp",
    "src/optimization/Module.cmake",
    "src/optimization/Tests.cmake",
    "include/csl/reachability/finite_plan_zonotope.hpp",
    "src/reachability/finite_plan_zonotope.cpp",
    "include/csl/reachability/finite_plan_parallelotope.hpp",
    "src/reachability/finite_plan_parallelotope.cpp",
    "tests/installed/finite_plan_parallelotope_client.cpp",
    "src/reachability/Module.cmake",
    "src/reachability/Tests.cmake",
    "benchmarks/reporting/exp824/two_points_fixture.hpp",
    "benchmarks/reporting/exp824/two_points_zonotope_minimax.cpp",
    "tests/unit/optimization/finite_action_zonotope_minimax_tests.cpp",
    "tests/installed/finite_action_zonotope_minimax_client.cpp",
    "tests/installed/CMakeLists.txt",
    "tests/contract/public_headers_client.cpp",
    "scripts/reports/exp824/check_two_points_box.py",
    "scripts/reports/exp824/check_zonotope_minimax.py",
    "scripts/reports/exp824/make_report.py",
        "tests/unit/reachability/finite_plan_parallelotope_tests.cpp",
    "scripts/reports/exp824/make_zonotope_minimax_report.py",
    "scripts/reports/exp824/check_zonotope_minimax_smoke.py",
    "scripts/reports/audit_visual_routes.py",
    "scripts/reports/report_source_identity.py",
    "scripts/reports/stage_issue824_zonotope.py",
    "scripts/reports/stage_issue824_zonotope_minimax.py",
    "scripts/reports/visual_examples.py",
    "tests/reporting/test_issue824_zonotope_publication.py",
    "tests/reporting/test_issue824_zonotope_minimax_publication.py",
    "tests/reporting/test_visual_route_inventory.py",
    ".github/workflows/algorithm-reports.yml",
    "docs/architecture/issue824-zonotope-minimax-selection.md",
    "docs/architecture/issue824-parallelotope-propagation.md",
)
COLORS = ("#458588", "#689d6a", "#d79921")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cpu_model() -> str:
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.is_file():
        for line in cpu_info.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.partition(":")[2].strip()
    return platform.processor() or "unavailable"


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def planar_selector_svg(example: dict) -> str:
    width, height = 900, 560
    left, right, top, bottom = 110, 850, 65, 430
    xmin, xmax, ymin, ymax = -1.5, 1.5, -1.5, 1.5

    def project(point: tuple[float, float]) -> tuple[float, float]:
        return (left + (point[0] - xmin) / (xmax - xmin) * (right - left),
                bottom - (point[1] - ymin) / (ymax - ymin) * (bottom - top))

    def polygon(points: list[tuple[float, float]], color: str) -> str:
        if len(points) < 3:
            return ""
        coords = " ".join(f"{project(point)[0]:.3f},{project(point)[1]:.3f}" for point in points)
        return f'<polygon points="{coords}" fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="2"/>'

    selected = example["selected_candidate_attempt_index"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Planar zonotope minimax candidate scores</title>',
           '<desc id="desc">Three fixed controls produce finite terminal points and outer zonotopes in state coordinates x1 and x2. The zero-control candidate has the smallest corner score and its worst disturbance replay is shown.</desc>',
           '<rect width="100%" height="100%" fill="#fbf1c7"/>',
           '<text x="450" y="30" text-anchor="middle" font-family="sans-serif" font-size="21" fill="#282828">One-stage 2D fixed-plan minimax selector</text>',
           f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="#f9f5d7" stroke="#665c54"/>']
    for tick in range(-1, 2):
        gx, _ = project((float(tick), 0.0))
        _, gy = project((0.0, float(tick)))
        out.append(f'<path d="M {gx:.2f} {top} V {bottom} M {left} {gy:.2f} H {right}" stroke="#d5c4a1"/>')
        out.append(f'<text x="{gx:.2f}" y="{bottom+20}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#665c54">{tick}</text>')
        out.append(f'<text x="{left-14}" y="{gy+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#665c54">{tick}</text>')
    for index, plan in enumerate(example["plans"]):
        color = COLORS[index]
        stage = plan["stages"][-1]
        out.append(polygon(shared.projected_zonotope(stage, 0, 1), color))
        control = plan["control"]
        source = project((0.0, 0.0))
        for point in example["terminal_catalogue_by_control"][index]:
            target = project((point[0], point[1]))
            out.append(f'<path d="M {source[0]:.2f} {source[1]:.2f} L {target[0]:.2f} {target[1]:.2f}" stroke="{color}" stroke-opacity="0.28" stroke-width="1"/>')
            out.append(f'<circle cx="{target[0]:.2f}" cy="{target[1]:.2f}" r="4.3" fill="{color}" stroke="#282828" stroke-width=".8"/>')
        if index == selected:
            out.append(f'<text x="{project((control, 1.28))[0]:.2f}" y="{project((control, 1.28))[1]:.2f}" text-anchor="middle" font-family="sans-serif" font-size="13" font-weight="700" fill="{color}">selected u={control:g}</text>')
    replay = example["selected_replay_path"]
    replay_points = [project((state[0], state[1])) for state in replay]
    replay_path = " ".join(("M" if index == 0 else "L") + f" {point[0]:.2f} {point[1]:.2f}"
                            for index, point in enumerate(replay_points))
    out.append(f'<path d="{replay_path}" fill="none" stroke="#282828" stroke-width="3" stroke-dasharray="7 4"/>')
    for x, y in replay_points:
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#282828"/>')
    out.extend((f'<text x="{(left+right)/2}" y="{bottom+48}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#282828">x₁</text>',
                f'<text x="26" y="{(top+bottom)/2}" transform="rotate(-90 26 {(top+bottom)/2})" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#282828">x₂</text>'))
    for index, plan in enumerate(example["plans"]):
        y = 474 + index * 22
        out.append(f'<rect x="104" y="{y-11}" width="18" height="12" fill="{COLORS[index]}" fill-opacity=".3" stroke="{COLORS[index]}"/>')
        out.append(f'<text x="132" y="{y}" font-family="sans-serif" font-size="13" fill="#282828">u={plan["control"]:g}. Zonotope factor-corner score {plan["candidate_score"]:.8f}</text>')
    out.append(f'<path d="M 540 470 h 22" stroke="#282828" stroke-width="3" stroke-dasharray="7 4"/>')
    out.append('<text x="568" y="474" font-family="sans-serif" font-size="12" fill="#282828">selected plan worst-history replay</text>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: make_zonotope_minimax_report.py EXECUTABLE BUILD_DIR OUTPUT")
    executable, build_dir, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    executable = executable.resolve(strict=True)
    build_dir = build_dir.resolve(strict=True)
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {output}")
    load_before_timing = os.getloadavg() if hasattr(os, "getloadavg") else None
    completed = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER") or "unknown"
    compiler_version = subprocess.run([compiler, "--version"], check=True,
        capture_output=True, text=True).stdout.splitlines()[0]
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], check=True,
        capture_output=True, text=True).stdout
    mpc_figure = json.loads(MPC05_FIGURE.read_text(encoding="utf-8"))
    capture = {
        "schema": "csl.issue824-two-points-zonotope-minimax-capture/1",
        "source_commit": commit,
        "source_tree_clean_before_report_generation": not bool(status),
        "source_status_before_report_generation": status.splitlines(),
        "source_files_sha256": {name: sha256(ROOT / name) for name in SOURCE_FILES},
        "exact_geometry_reference": {"report_id": "mpc05-causal-tree-pilot-v2",
            "figure_data_sha256": sha256(MPC05_FIGURE)},
        "build": {"directory": str(build_dir),
            "configuration": cache_value(cache, "CMAKE_BUILD_TYPE"),
            "cxx_standard": "C++20",
            "compiler": compiler, "compiler_version": compiler_version,
            "generator": cache_value(cache, "CMAKE_GENERATOR"),
            "cxx_flags": cache_value(cache, "CMAKE_CXX_FLAGS"),
            "cxx_flags_release": cache_value(cache, "CMAKE_CXX_FLAGS_RELEASE"),
            "highs": cache_value(cache, "CSL_ENABLE_HIGHS"),
            "qhull": cache_value(cache, "CSL_ENABLE_QHULL")},
        "host": {"system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "cpu_model": cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "load_average_before_timing": load_before_timing,
            "load_average_after_timing": os.getloadavg() if hasattr(os, "getloadavg") else None},
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "capture.json").write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    check = check_zonotope_minimax.main(result_path)
    (output / "check.json").write_text(json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    figure = {"schema": "csl.issue824-two-points-zonotope-minimax-figure/1",
        "source_geometry_report": "mpc05-causal-tree-pilot-v2",
        "geometry": mpc_figure["reachability_geometry"],
        "independent_check": check,
        "timing": result["timing"],
        "box_stages": result["box_method"]["stages"],
        "box_selected_zonotope_stages": result["zonotope_method"]["stages"],
        "parallelotope_method": result["parallelotope_method"],
        "zonotope_candidate_plans": result["zonotope_minimax_method"]["plan_attempts"],
        "planar_selector_example": result["planar_selector_example"]}
    (output / "figure-data.json").write_text(json.dumps(figure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "projections.svg").write_text(shared.svg_figure(result, check, mpc_figure), encoding="utf-8")
    (output / "planar-example.svg").write_text(
        planar_selector_svg(result["planar_selector_example"]), encoding="utf-8")
    selected = result["zonotope_minimax_method"]
    exact_value = result["exact_reference"]["finite_minimax_value"]
    box_value = result["box_method"]["full_catalogue_replay_value"]
    zonotope_value = selected["selected_replay"]["worst_value"]
    candidate_value = selected["selected_candidate_score"]
    timing = result["timing"]
    timing_rows = "".join(
        f'<tr><td>{row["method"].replace("_", " ")}</td><td>{row["repetitions"]}</td>'
        f'<td>{row["median_ns"]:,}</td><td>{row["minimum_ns"]:,}–{row["maximum_ns"]:,}</td></tr>'
        for row in timing["summaries"])
    commit_link = f"https://github.com/butahlecoq/controlled-systems-lab/commit/{commit}"
    planar_html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · Planar zonotope minimax selection</title>
<style>body{{max-width:980px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.5 system-ui}}h1,h2{{color:#3c3836}}svg{{width:100%;height:auto}}code{{background:#f9f5d7;padding:.1rem .3rem}}a{{color:#076678}}table{{border-collapse:collapse}}th,td{{border:1px solid #bdae93;padding:.4rem .7rem;text-align:left}}</style>
<h1>Plan fixed controls by terminal zonotope scores</h1><p>The two-state fixture starts at <code>(0,0)</code>. One fixed control from <code>{{-1,0,1}}</code> and one disturbance from <code>{{-1,0,1}}</code> produce the terminal set. The objective is <code>x1²+x2²</code>.</p>
{planar_selector_svg(result['planar_selector_example'])}
<table><caption>Every fixed control candidate</caption><thead><tr><th>Control</th><th>Numerical factor-corner score</th><th>Finite-catalog replay</th></tr></thead><tbody>{''.join(f'<tr><td>{plan["control"]:g}</td><td>{plan["candidate_score"]:.8f}</td><td>{result["planar_selector_example"]["selected_replay_value"]:.8f}</td></tr>' if plan["action_indices"] == result["planar_selector_example"]["selected_action_indices"] else f'<tr><td>{plan["control"]:g}</td><td>{plan["candidate_score"]:.8f}</td><td>not replayed</td></tr>' for plan in result['planar_selector_example']['plans'])}</tbody></table>
<p>The checker confirms that every exact finite terminal point lies in its axis-aligned outer zonotope and recomputes every factor-corner score. The score is numerical evidence for candidate ranking, not a validated objective bound. The selected plan's replay covers every declared disturbance history.</p>
<p><a href="result.json">Raw record</a> · <a href="check.json">Independent check</a> · <a href="{commit_link}">Source commit</a> · <a href="README.md">Reproduction and limits</a></p></html>'''
    (output / "planar-example.html").write_text(planar_html, encoding="utf-8")
    html_page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · Zonotope minimax candidate selection</title>
<style>body{{max-width:1280px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.5 system-ui}}h1,h2{{color:#3c3836}}.metric{{display:inline-block;margin:.4rem 1rem .4rem 0;padding:.7rem;background:#f9f5d7;border:1px solid #d5c4a1;border-radius:6px}}svg{{width:100%;height:auto}}a{{color:#076678}}</style>
<h1>TwoPointsOnParallelLines: outer-set candidate selection</h1><p>This is a three-stage finite-catalog adaptation of the source differential-game environment. The selector ranks each fixed open-loop plan by its terminal zonotope factor-corner score, then replays only the selected plan through every finite disturbance history. A fixed-frame parallelotope trace propagates the selected plan and is checked against every exact finite-history state. It does not reproduce the upstream continuous-action RL problem.</p>
<p><span class="metric">Exact finite minimax: <b>{exact_value:.8f}</b></span><span class="metric">Box-selected replay: <b>{box_value:.8f}</b></span><span class="metric">Zonotope-selected replay: <b>{zonotope_value:.8f}</b></span><span class="metric">Selected zonotope candidate score: <b>{candidate_value:.8f}</b></span></p>
{shared.svg_figure(result, check, mpc_figure)}
<h2>Descriptive API-call timings</h2><p>One excluded warmup and seven order-rotated repetitions per method. Times cover the complete algorithm call; request setup and JSON serialization are excluded. These descriptive timings do not establish a performance winner or speedup. No separate limiter profile was collected.</p><table><thead><tr><th>Method</th><th>Runs</th><th>Median (ns)</th><th>Range (ns)</th></tr></thead><tbody>{timing_rows}</tbody></table>
<h2>Evidence and limits</h2><p>The independent checker reconstructs the exact finite game, verifies all 27 candidate score rows by evaluating their stored terminal factor corners, checks the selected plan's exact worst disturbance history, and transforms every finite-history state into the fixed parallelotope frame at each stage. The parallelotope orientation is fixed and is not optimized. Zonotope coordinate checks do not prove full four-dimensional zonotope membership, and candidate scores are not validated objective bounds. The separate two-dimensional example checks complete inclusion of all finite terminal points in each axis-aligned zonotope.</p>
<p>The figure shows exact forward reachable sets, robust backward-winning states, their intersections, the box-selected and zonotope-selected outer set projections, and exact replay paths in both player phase planes. The fixed-plan policies use finite catalogs only; they make no continuous feedback optimality claim. The zonotope calls evaluate 884,736 factor corners each (27 plans × 32,768 corners). `perf` and `strace` were unavailable, so this is a known work count, not a profiler-confirmed CPU bottleneck.</p>
<p><a href="result.json">Raw scores, traces and timing samples</a> · <a href="check.json">Independent check</a> · <a href="capture.json">Build and host capture</a> · <a href="figure-data.json">Figure data</a> · <a href="planar-example.html">Complete planar selector example</a> · <a href="{commit_link}">Source commit</a></p></html>'''
    (output / "index.html").write_text(html_page, encoding="utf-8")
    readme = f'''# Issue 824 TwoPoints zonotope minimax pilot

This bundle compares exact finite-catalog fixed-plan minimax, the existing outer-box selector, candidate selection using stagewise outer zonotopes, and a fixed-frame stagewise parallelotope trace on the three-stage `TwoPointsOnParallelLines` adaptation. The model has state `(x1,x2,x3,x4)`, initial state `(4.5,0,0,0)`, controls `(-2.5,0,2.5)`, disturbances `(-1,0,1)`, and terminal squared position gap.

The exact finite minimax value is `{exact_value:.8f}`. The box-selected plan replay is `{box_value:.8f}`. The zonotope-selected plan replay is `{zonotope_value:.8f}`. The selected terminal zonotope's numerical factor-corner candidate score is `{candidate_value:.14f}`. The selector scored all 27 fixed plans. It evaluates every one of the 32,768 terminal factor corners for each plan under the explicit caller limit.

Candidate scores are numerical maxima over stored binary64 factor corners. They are not validated objective bounds. The selected finite plan has a separate exact finite-catalog replay score and worst-history witness. The checker reconstructs every exact state with integer transitions and rational costs. In four dimensions it checks every state coordinate against each candidate zonotope's coordinate bounds. It does not prove full four-dimensional zonotope membership. The planar companion has axis-aligned generators; its complete finite terminal-set inclusion follows from the independently checked coordinate bounds.

This is a fixed open-loop finite-catalog comparison. The fixed-frame parallelotope is a selected orientation, not an orientation optimizer. The report does not claim global minimax optimizer completeness, continuous-action RL reproduction, feedback optimality, ellipsoid support, or a performance winner/speedup. The stagewise geometry figure also overlays exact forward/backward sets and intersections from the separate MPC-05 finite adaptation report.

## Descriptive timings

The result contains one excluded warmup and seven order-rotated API-call measurements per method, including raw per-repetition durations and returned values. Fixture/request construction and JSON serialization are outside the measured interval; no algorithm workspace is reused. The same immutable request is used for all arms. The timing driver is single-threaded and deterministic, uses binary64 with the default absolute and relative tolerances of `1e-8`, and has no random seed. Timings are descriptive for this host and build only; no performance winner is claimed. `perf` and `strace` were unavailable, so the 884,736 factor-corner evaluations per zonotope call are reported as a known work count rather than a profiler-confirmed CPU limiter.

| Method | Median (ns) | Range (ns) |
| --- | ---: | ---: |
{''.join(f'| {row["method"]} | {row["median_ns"]:,} | {row["minimum_ns"]:,}–{row["maximum_ns"]:,} |\n' for row in timing["summaries"])}

`capture.json` records host CPU/model/load, OS, Release compiler and flags, build generator and optional backend settings. The source commit is recorded separately from this measurement commit.

## Reproduce

Configure and build the Release driver from the repository root:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_ZONOTOPE_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_zonotope_minimax_report --parallel 4
python3 scripts/reports/exp824/make_zonotope_minimax_report.py \\
  build/dev/csl_issue824_zonotope_minimax_report build/dev \\
  reports/algorithm-results/issue824-two-points-zonotope-minimax-v1
```

Run the driver and its functional smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_zonotope_minimax_report_smoke$' --output-on-failure
```

`capture.json` records the clean source commit, source hashes, Release compiler, and exact geometry reference. `result.json` stores all candidate scores and traces, the selected plan replay, the box baseline, the exact reference, and the 2D fixture. `check.json` preserves the exact replay checks and the limits of the 4D zonotope evidence. `projections.svg` shows both player phase planes. `planar-example.html` includes the minimal input, all candidate scores, the selected witness, and its independently checked 2D inclusion.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items()), encoding="ascii")


if __name__ == "__main__":
    main()

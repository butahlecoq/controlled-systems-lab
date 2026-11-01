#!/usr/bin/env python3
"""Capture five matched fixed-plan minimax runs and render their report."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_matched_minimax

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = "issue824-two-points-matched-minimax-v1"
ELLIPSOID_FIGURE = ROOT / "reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v2/projections.svg"
PARALLELOTOPE_FIGURE = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-minimax-v2/projections.svg"
SOURCE_FILES = (
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "include/csl/optimization/finite_action_minimax.hpp",
    "include/csl/optimization/finite_action_box_minimax.hpp",
    "include/csl/optimization/finite_action_zonotope_minimax.hpp",
    "include/csl/optimization/finite_action_parallelotope_minimax.hpp",
    "include/csl/optimization/finite_action_ellipsoid_minimax.hpp",
    "src/optimization/finite_action_minimax.cpp",
    "src/optimization/finite_action_box_minimax.cpp",
    "src/optimization/finite_action_zonotope_minimax.cpp",
    "src/optimization/finite_action_parallelotope_minimax.cpp",
    "src/optimization/finite_action_ellipsoid_minimax.cpp",
    "src/optimization/finite_action_replay.cpp",
    "src/reachability/finite_plan_box.cpp",
    "src/reachability/finite_plan_zonotope.cpp",
    "src/reachability/finite_plan_parallelotope.cpp",
    "src/reachability/finite_plan_ellipsoid.cpp",
    "benchmarks/reporting/exp824/two_points_fixture.hpp",
    "benchmarks/reporting/exp824/two_points_matched_minimax.cpp",
    "scripts/reports/exp824/check_matched_minimax.py",
    "scripts/reports/exp824/check_matched_minimax_smoke.py",
    "scripts/reports/exp824/make_matched_minimax_report.py",
)
METHOD_LABELS = {
    "exact_polytope": "Exact finite polytope",
    "box": "Outer box",
    "zonotope": "Outer zonotope",
    "parallelotope": "Fixed-frame parallelotope",
    "ellipsoid": "Axis-aligned ellipsoid",
}
FILES = (
    "README.md", "capture.json", "check.json", "e2e-timing.json",
    "geometry-reference-ellipsoid.svg", "geometry-reference-parallelotope.svg",
    "index.html", "limiter-profile.json", "result.json", "SHA256SUMS",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cpu_model() -> str:
    info = Path("/proc/cpuinfo")
    if info.is_file():
        for line in info.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.partition(":")[2].strip()
    return platform.processor() or "unavailable"


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def render(result: dict[str, Any], check: dict[str, Any], e2e: list[dict[str, Any]],
           limiter: dict[str, Any], commit: str) -> tuple[str, str]:
    score_profile = next(row for row in limiter["hotspots"] if "score_corners(" in row["function"])
    rows = []
    for summary in result["summaries"]:
        method = summary["method"]
        rows.append(
            f"<tr><td>{html.escape(METHOD_LABELS[method])}</td>"
            f"<td>{summary['successful_repetitions']}/5</td>"
            f"<td>{summary.get('median_ns', 0) / 1e6:.3f} ms</td>"
            f"<td>{summary.get('minimum_ns', 0) / 1e6:.3f}–{summary.get('maximum_ns', 0) / 1e6:.3f} ms</td>"
            "<td>27 plans; full-history replay</td></tr>")
    end_to_end_ns = [row["elapsed_ns"] for row in e2e]
    end_to_end_sorted = sorted(end_to_end_ns)
    e2e_median = end_to_end_sorted[len(end_to_end_sorted) // 2] / 1e9
    e2e_range = f"{min(end_to_end_ns) / 1e9:.3f}–{max(end_to_end_ns) / 1e9:.3f} s"
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · Matched fixed-plan minimax</title>
<style>body{{max-width:1100px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.55 system-ui}}h1,h2{{color:#3c3836}}a{{color:#076678}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bdae93;padding:.45rem .65rem;text-align:left}}img{{max-width:100%;height:auto;border:1px solid #d5c4a1;background:#fff}}.note{{background:#f9f5d7;border-left:4px solid #d79921;padding:.7rem 1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:1rem}}code{{background:#f9f5d7;padding:.1rem .3rem}}</style>
<h1>Five matched tracks on TwoPointsOnParallelLines</h1>
<p>This is a finite-catalog adaptation of the upstream differential game, not a reproduction of its continuous-action 10-second RL task. The state order is <code>(x1,x2,x3,x4)</code>; there are three stages, controls <code>{-2.5,0,2.5}</code>, disturbances <code>{-1,0,1}</code>, initial state <code>(4.5,0,0,0)</code>, and terminal squared player-position gap. Re-expressing the pinned source's ten Euler substeps gives <code>x1'=x1+0.01x2+0.09u</code>, <code>x2'=u</code>, <code>x3'=x3+0.1x4+0.0045v</code>, <code>x4'=x4+0.1v</code>; in particular, damping in the first player's velocity equation resets its velocity to the current input each outer step.</p>
<p>The methods use identical inputs and each scores all 27 fixed control plans. Every selected approximate plan is replayed across all 27 disturbance histories. An independent exact rational checker verified all 25 timed outcomes and the exact finite minimax optimum, <code>{check['exact_finite_minimax_value']:.8f}</code>.</p>
<h2>Release call timings</h2><table><thead><tr><th>Track</th><th>Runs</th><th>Median</th><th>Range</th><th>Work checked</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="note">These are descriptive times for one four-state, three-stage fixture. The methods use different candidate scoring rules: approximate enclosure corner/support scores are numerical ranking estimates, not certified objective bounds. The replay values are feasible finite-catalog witnesses, not proof that an approximate selector found the global minimizer. The timing table does not establish a general winner.</p>
<h2>Limiter profile</h2><p>A separate instrumented Release profile ran {limiter['profile_calls']} zonotope calls. GNU gprof sampled {limiter['sampled_total_seconds']:.2f} s; <code>score_corners</code> accounted for {score_profile['sampled_self_percent']:.2f}% of sampled self CPU ({score_profile['self_seconds']:.2f} s). This identifies the dominant work in this zonotope fixture; the profile build is excluded from the timing table. Its 10 ms sample resolution and single fixture limit the conclusion.</p>
<h2>Report-generation path</h2><p>Five separate Release report-data generation, rational checking, serialization and checksum trials had median {e2e_median:.3f} s (range {e2e_range}).</p>
<h2>Reachability geometry</h2><p>These saved projections show the two requested player phase planes: <code>(x1,x2)</code> and <code>(x3,x4)</code>, with stage-labelled forward/backward geometry, intersections and replayed paths. The tracks are split across two checked source result bundles; both use the same frozen geometry reference and finite-game fixture.</p>
<div class="grid"><figure><img src="geometry-reference-ellipsoid.svg" alt="TwoPoints player phase-plane reachable sets and selected paths"><figcaption>Ellipsoid comparison geometry; <a href="../issue824-two-points-ellipsoid-minimax-v2/index.html">saved result bundle</a>.</figcaption></figure><figure><img src="geometry-reference-parallelotope.svg" alt="TwoPoints player phase-plane geometry with parallelotope sets"><figcaption>Parallelotope comparison geometry; <a href="../issue824-two-points-zonotope-minimax-v2/index.html">saved result bundle</a>.</figcaption></figure></div>
<p><a href="result.json">Raw run record</a> · <a href="check.json">Independent check</a> · <a href="limiter-profile.json">Limiter profile</a> · <a href="README.md">Reproduction notes</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{commit}">source commit</a></p>
</html>'''
    summaries = "\n".join(
        f"| {METHOD_LABELS[row['method']]} | {row['successful_repetitions']}/5 | "
        f"{row.get('median_ns', 0) / 1e6:.3f} ms | "
        f"{row.get('minimum_ns', 0) / 1e6:.3f}–{row.get('maximum_ns', 0) / 1e6:.3f} ms |"
        for row in result["summaries"])
    readme = f'''# Matched TwoPoints fixed-plan minimax run

This report compares the exact finite-polytope search and outer box, zonotope, fixed-frame parallelotope, and axis-aligned ellipsoid selectors on the pinned `TwoPointsOnParallelLines` source adaptation. It uses state `(x1,x2,x3,x4)`, initial `(4.5,0,0,0)`, horizon 3, control catalog `{-2.5,0,2.5}`, disturbance catalog `{-1,0,1}`, and terminal squared position gap. Re-expressing the pinned source's ten Euler substeps gives `x1'=x1+0.01x2+0.09u`, `x2'=u`, `x3'=x3+0.1x4+0.0045v`, and `x4'=x4+0.1v`; first-player damping resets its velocity to the selected input each outer step.

All methods received the same immutable request. Each scored all 27 action plans, and every selected plan was replayed across all 27 disturbance histories. Independent rational enumeration verified the exact minimax value and each replay. Approximation scores are numerical ranking estimates; no objective bound or global optimizer-family completeness is claimed.

## Timings

Release build, one warmup and five order-rotated measurements per method. The timed interval covers the public call and extraction/checking of its selected result. Fixture construction, serialization, independent rational checking, and plotting are excluded.

| Track | Runs | Median | Range |
| --- | ---: | ---: | ---: |
{summaries}

The differences describe this one small fixture only. The methods do not use the same candidate-score representation, so these numbers do not establish a general performance winner. The zonotope limiter profile is separate from the reported timing build and identifies `score_corners` as the main sampled CPU path for this workload. Profiling used GNU gprof 2.47, Release `-O3 -DNDEBUG -pg`, ten calls, and 10 ms sampling. See `limiter-profile.json`.

Five end-to-end report-data trials (solver run, exact rational checker, JSON serialization and SHA-256 verification) took median {e2e_median:.3f} s, range {e2e_range}. Raw trials and output hashes are in `e2e-timing.json`.

The two phase-plane SVGs reuse the independently checked geometry figures from the [ellipsoid v2 bundle](../issue824-two-points-ellipsoid-minimax-v2/index.html) and [zonotope/parallelotope v2 bundle](../issue824-two-points-zonotope-minimax-v2/index.html). Those source records preserve forward/backward sets, intersections, selected plan replays and the finite RL adaptation limits.

## Reproduce

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_MATCHED_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_matched_minimax_report --parallel 4
python3 scripts/reports/exp824/make_matched_minimax_report.py \\
  build/dev/csl_issue824_matched_minimax_report build/dev \\
  reports/algorithm-results/{BUNDLE}
ctest --test-dir build/dev -R '^issue824_matched_minimax_report_smoke$' --output-on-failure
```

The input follows pinned upstream commit `f4d76c60f4003f50954174e96eafd8e514bd5441`. This report is a finite-action three-stage adaptation, not a reproduction of the continuous-action 10-second RL task.
'''
    return page, readme


def make_files(executable: Path, build_dir: Path, limiter_json: dict[str, Any],
               profile_build: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    e2e: list[dict[str, Any]] = []
    chosen: tuple[dict[str, Any], dict[str, Any]] | None = None
    load_before_e2e = os.getloadavg()
    for trial in range(1, 6):
        trial_load_before = os.getloadavg()
        start = time.perf_counter_ns()
        completed = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
        result = json.loads(completed.stdout)
        check = check_matched_minimax.check(result)
        result_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
        check_bytes = (json.dumps(check, indent=2, sort_keys=True) + "\n").encode()
        artifact_hash = sha(result_bytes + check_bytes)
        with tempfile.TemporaryDirectory(prefix="issue824-matched-e2e-") as temporary:
            directory = Path(temporary)
            (directory / "result.json").write_bytes(result_bytes)
            (directory / "check.json").write_bytes(check_bytes)
            if sha((directory / "result.json").read_bytes() + (directory / "check.json").read_bytes()) != artifact_hash:
                raise ValueError("end-to-end serialized run hash changed")
        elapsed = time.perf_counter_ns() - start
        e2e.append({"trial": trial, "elapsed_ns": elapsed, "status": "completed",
            "result_sha256": sha(result_bytes), "check_sha256": sha(check_bytes),
            "sample_count": len(result["samples"]), "failures": check["failures"],
            "load_average_before": trial_load_before, "load_average_after": os.getloadavg()})
        if chosen is None:
            chosen = (result, check)
    assert chosen is not None
    result, check = chosen
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], check=True,
        capture_output=True, text=True).stdout
    cache_text = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = cache_value(cache_text, "CMAKE_CXX_COMPILER") or "unknown"
    compiler_version = subprocess.run([compiler, "--version"], check=True,
        capture_output=True, text=True).stdout.splitlines()[0]
    sources = {name: sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    figure_sources = {
        "ellipsoid": {"bundle": "issue824-two-points-ellipsoid-minimax-v2",
            "path": "reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v2/projections.svg",
            "sha256": sha(ELLIPSOID_FIGURE.read_bytes())},
        "parallelotope": {"bundle": "issue824-two-points-zonotope-minimax-v2",
            "path": "reports/algorithm-results/issue824-two-points-zonotope-minimax-v2/projections.svg",
            "sha256": sha(PARALLELOTOPE_FIGURE.read_bytes())}}
    e2e_json = {"schema": "csl.issue824.matched-minimax-e2e/1", "trials": e2e,
        "median_ns": sorted(row["elapsed_ns"] for row in e2e)[2],
        "range_ns": [min(row["elapsed_ns"] for row in e2e), max(row["elapsed_ns"] for row in e2e)],
        "path_scope": "Release solver run, exact rational check, serialization and hash verification"}
    page, readme = render(result, check, e2e, limiter_json, commit)
    capture = {"schema": "csl.issue824.matched-minimax-capture/1", "source_commit": commit,
        "source_tree_clean_before_report_generation": not bool(status),
        "source_status_before_report_generation": status.splitlines(),
        "source_files_sha256": sources, "source_fixture": result["fixture"],
        "figure_sources": figure_sources,
        "measurement_build": {"configuration": cache_value(cache_text, "CMAKE_BUILD_TYPE"),
            "compiler": compiler, "compiler_version": compiler_version,
            "generator": cache_value(cache_text, "CMAKE_GENERATOR"),
            "cxx_flags": cache_value(cache_text, "CMAKE_CXX_FLAGS"),
            "cxx_flags_release": cache_value(cache_text, "CMAKE_CXX_FLAGS_RELEASE"),
            "highs": cache_value(cache_text, "CSL_ENABLE_HIGHS"),
            "qhull": cache_value(cache_text, "CSL_ENABLE_QHULL")},
        "limiter_profile_build": profile_build,
        "host": {"system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "cpu_model": cpu_model(),
            "logical_cpu_count": os.cpu_count(), "load_average_before_e2e": load_before_e2e,
            "load_average_after_e2e": os.getloadavg()}}
    files = {
        "README.md": readme.encode(), "capture.json": (json.dumps(capture, indent=2, sort_keys=True) + "\n").encode(),
        "check.json": (json.dumps(check, indent=2, sort_keys=True) + "\n").encode(),
        "e2e-timing.json": (json.dumps(e2e_json, indent=2, sort_keys=True) + "\n").encode(),
        "geometry-reference-ellipsoid.svg": ELLIPSOID_FIGURE.read_bytes(),
        "geometry-reference-parallelotope.svg": PARALLELOTOPE_FIGURE.read_bytes(),
        "index.html": page.encode(),
        "limiter-profile.json": (json.dumps(limiter_json, indent=2, sort_keys=True) + "\n").encode(),
        "result.json": (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
    }
    lines = [f"{sha(content)}  {name}" for name, content in sorted(files.items())]
    files["SHA256SUMS"] = ("\n".join(lines) + "\n").encode()
    return files, capture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limiter-profile", type=Path, required=True)
    parser.add_argument("--profile-build", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    build_dir = args.build_dir.resolve(strict=True)
    profile_path = args.limiter_profile.resolve(strict=True)
    profile_build = args.profile_build.resolve(strict=True)
    limiter = json.loads(profile_path.read_text(encoding="utf-8"))
    files, _ = make_files(executable, build_dir, limiter, {
        "configuration": "Release", "compiler_flags": "-O3 -DNDEBUG -pg",
        "profiler": "GNU gprof 2.47", "sample_interval_ms": 10,
        "profile_executable_sha256": sha((profile_build / "csl_issue824_matched_minimax_report").read_bytes()),
        "limiter_profile_sha256": sha(profile_path.read_bytes())})
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output / name).write_bytes(content)
    print(f"wrote {len(files)} files to {output}")


if __name__ == "__main__":
    main()

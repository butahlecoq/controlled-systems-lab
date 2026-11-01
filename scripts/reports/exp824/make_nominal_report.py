#!/usr/bin/env python3
"""Capture and render the classic nominal comparison for issue #824."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_nominal

shared_spec = importlib.util.spec_from_file_location("issue824_shared_report", HERE / "make_report.py")
if shared_spec is None or shared_spec.loader is None:
    raise RuntimeError("cannot load the shared issue 824 figure renderer")
shared = importlib.util.module_from_spec(shared_spec)
shared_spec.loader.exec_module(shared)

REFERENCE = ROOT / "reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v1"
GEOMETRY_REFERENCE = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2/figure-data.json"
SOURCE_FILES = (
    ".github/workflows/algorithm-reports.yml",
    "CMakeLists.txt", "cmake/OptionalReports.cmake", "cmake/RunInstalledClient.cmake",
    "src/optimization/Module.cmake", "src/optimization/Tests.cmake",
    "include/csl/optimization/finite_action_nominal.hpp",
    "src/optimization/finite_action_nominal.cpp",
    "benchmarks/reporting/exp824/two_points_fixture.hpp",
    "benchmarks/reporting/exp824/two_points_nominal.cpp",
    "tests/unit/optimization/finite_action_nominal_tests.cpp",
    "tests/installed/finite_action_nominal_client.cpp", "tests/installed/CMakeLists.txt",
    "scripts/reports/exp824/check_nominal.py", "scripts/reports/exp824/check_nominal_smoke.py",
    "scripts/reports/exp824/make_nominal_report.py",
    "scripts/reports/exp824/make_report.py", "scripts/reports/stage_issue824_nominal.py",
    "scripts/reports/audit_visual_routes.py",
    "scripts/reports/visual_examples.py", "tests/reporting/test_issue824_nominal_publication.py",
    "docs/architecture/issue824-nominal-control.md",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.partition("=")[2]
    return None


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: make_nominal_report.py EXECUTABLE BUILD_DIR OUTPUT_DIR")
    executable, build_dir, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    if not executable.is_absolute():
        executable = ROOT / executable
    if not build_dir.is_absolute():
        build_dir = ROOT / build_dir
    if not output.is_absolute():
        output = ROOT / output

    run = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    native = json.loads(run.stdout)
    check = check_nominal.check(native)
    measurement_host = {"system": platform.system(), "release": platform.release(),
        "machine": platform.machine(), "python": platform.python_version(),
        "logical_processors": os.cpu_count(),
        "load_average_1_5_15_before_measurement": list(os.getloadavg()) if hasattr(os, "getloadavg") else None}
    measured = subprocess.run([str(executable), "--measure"], check=True,
        capture_output=True, text=True)
    measurement = json.loads(measured.stdout)
    if measurement["failures"] != 0 or measurement["completed_calls"] != 70:
        raise RuntimeError("nominal measurement did not complete all 70 measured calls")
    durations = [batch["api_duration_ns"] / batch["calls"] for batch in measurement["batches"]]
    reference_result_path = REFERENCE / "result.json"
    reference_check_path = REFERENCE / "check.json"
    reference_figure_path = REFERENCE / "figure-data.json"
    geometry_figure = json.loads(GEOMETRY_REFERENCE.read_text(encoding="utf-8"))
    reference_result = json.loads(reference_result_path.read_text(encoding="utf-8"))
    reference_check = json.loads(reference_check_path.read_text(encoding="utf-8"))
    reference_figure = json.loads(reference_figure_path.read_text(encoding="utf-8"))
    exact_track = next(track for track in native["nominal_tracks"]
                       if track["representation"] == "exact_polytope")
    selected_attempt = exact_track["attempts"][exact_track["selected_attempt"]]
    reference_result["nominal_method"] = {
        "replay": exact_track["replay"],
        "selected_action_indices": selected_attempt["action_indices"],
        "candidate_score": exact_track["candidate_score"],
    }
    svg = shared.svg_figure(reference_result, reference_check, geometry_figure)

    output.mkdir(parents=True, exist_ok=True)
    git_commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()
    git_status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
        check=True, capture_output=True, text=True).stdout.splitlines()
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER") or "unavailable"
    compiler_output = subprocess.run([compiler, "--version"], check=False,
        capture_output=True, text=True).stdout.splitlines()
    try:
        build_reference = build_dir.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        build_reference = "external"
    result = {
        "schema": "csl.issue824-two-points-nominal-bundle/1",
        "source_commit": git_commit,
        "source_worktree_clean": not bool(git_status),
        "nominal_result": native,
        "independent_check": check,
        "minimax_reference": {
            "report_id": REFERENCE.name,
            "result_sha256": sha256(reference_result_path),
            "check_sha256": sha256(reference_check_path),
            "figure_data_sha256": sha256(reference_figure_path),
            "geometry_report_id": "mpc05-causal-tree-pilot-v2",
            "geometry_figure_data_sha256": sha256(GEOMETRY_REFERENCE),
            "exact_finite_minimax_value": native["exact_finite_minimax"]["value"],
        },
        "measurement": {**measurement,
            "per_call_batch_ns": durations,
            "median_ns_per_call": statistics.median(durations),
            "min_ns_per_call": min(durations), "max_ns_per_call": max(durations),
            "limiter_profile": {"performed": False,
                "reason": "No profiler or syscall trace was collected; this descriptive single-adapter measurement makes no bottleneck or performance-winner claim."}},
        "figure": {"file": "projections.svg",
            "description": "Existing forward/backward/intersection and approximation geometry in both player phase planes, with the classic nominal trajectory overlaid."},
    }
    capture = {
        "schema": "csl.issue824-two-points-nominal-capture/1",
        "source_commit": git_commit,
        "source_worktree_clean": not bool(git_status),
        "source_status": git_status,
        "source_files_sha256": {name: sha256(ROOT / name) for name in SOURCE_FILES},
        "build": {"directory": build_reference,
            "configuration": cache_value(cache, "CMAKE_BUILD_TYPE"),
            "compiler": compiler, "compiler_version": compiler_output[0] if compiler_output else "unavailable",
            "generator": cache_value(cache, "CMAKE_GENERATOR"),
            "cxx_flags_release": cache_value(cache, "CMAKE_CXX_FLAGS_RELEASE")},
        "host": measurement_host,
    }
    figure = {"schema": "csl.issue824-two-points-nominal-figure/1",
        "geometry_report_id": "mpc05-causal-tree-pilot-v2",
        "geometry": reference_figure["geometry"],
        "nominal_tracks": native["nominal_tracks"],
        "nominal_independent_check": check,
        "minimax_reference": result["minimax_reference"]}
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "capture.json").write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "check.json").write_text(json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "figure-data.json").write_text(json.dumps(figure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "projections.svg").write_text(svg, encoding="utf-8")

    rows = "".join(
        f'<tr><td>{track["representation"]}</td><td>{track["candidate_score"]:.12f}</td>'
        f'<td>{"finite-catalog minimum (binary64)" if track["objective_bound_direction"] == "finite_catalogue_minimum_under_binary64" else "none certified"}</td>'
        f'<td>{track["replay"]["terminal_objective"]:.12f}</td>'
        f'<td>{", ".join(map(str, track["attempts"][track["selected_attempt"]]["action_indices"]))}</td></tr>'
        for track in native["nominal_tracks"])
    nominal_value = exact_track["replay"]["terminal_objective"]
    minimax_value = native["exact_finite_minimax"]["value"]
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Issue 824 · Classic nominal TwoPoints comparison</title>
<style>body{{max-width:1320px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.55 system-ui}}h1,h2{{color:#3c3836}}svg{{width:100%;height:auto}}a{{color:#076678}}table{{border-collapse:collapse}}th,td{{border:1px solid #bdae93;padding:.4rem .7rem;text-align:left}}code{{background:#f9f5d7;padding:.1rem .3rem}}</style>
<h1>TwoPointsOnParallelLines: classic nominal versus finite minimax</h1>
<p>This finite three-stage adaptation of the differential-game RL environment uses state <code>(x1,x2,x3,x4)=(position₁,velocity₁,position₂,velocity₂)</code>, initial state <code>(4.5,0,0,0)</code>, and controls <code>{{-2.5,0,2.5}}</code>. Classic nominal control fixes the opponent input to <code>v=+1</code> at every stage. It is not a reproduction of the source continuous-action, 10-second RL task.</p>
<p>The exact nominal finite-catalog objective is <b>{nominal_value:.8f}</b>. The separately computed exact finite minimax value is <b>{minimax_value:.8f}</b>, under opponent disturbances <code>{{-1,0,+1}}</code> at each stage. These use different disturbance semantics and are not a direct performance or robustness comparison.</p>
<img src="projections.svg" alt="Forward and backward game geometry and approximation projections in both player phase planes, with nominal and minimax trajectories">
<table><caption>All 27 nominal control plans were scored in each track</caption><thead><tr><th>Track</th><th>Candidate score</th><th>Objective-bound evidence</th><th>Selected replay objective</th><th>Selected action indices</th></tr></thead><tbody>{rows}</tbody></table>
<p>The exact track selects the lowest numerical deterministic objective among the enumerated finite catalog; this is a numerical finite-catalog result, not a validated real-arithmetic certificate. Approximation tracks rank plans using floating-point outer-enclosure scores. These scores are ranking estimates only: they provide no certified lower or upper objective bound. Each selected action sequence is separately replayed from the authored state and fixed opponent inputs. The independent checker uses exact rational arithmetic to reconstruct all nominal plans, verify all five score tables and selected traces, and recompute all 27×27 finite minimax histories.</p>
<p>One excluded warmup followed by seven batches of ten API calls measured all five nominal tracks at once. Median call time was {statistics.median(durations) / 1e6:.3f} ms (range {min(durations) / 1e6:.3f}–{max(durations) / 1e6:.3f} ms; 70 measured calls, zero failures). Each timer surrounds one native nominal API call, including all five tracks and selected-path replays; caller status checks and score consumption happen after timing. Fixture setup, finite-minimax reference, serialization, independent checking, build, and rendering are excluded. This is descriptive for one fixture and host. No limiter profile or comparative performance claim is made.</p>
<p>The figure overlays the nominal trajectory on saved minimax forward/backward sets, intersections, outer approximations, and selected minimax paths in <code>(x1,x2)</code> and <code>(x3,x4)</code>. <a href="result.json">Raw result</a> · <a href="check.json">Independent check</a> · <a href="capture.json">Source/build capture</a> · <a href="figure-data.json">Figure data</a> · <a href="README.md">Reproduction and limits</a></p></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    readme = f'''# Issue 824 classic nominal TwoPoints pilot

This report adds a distinct classic nominal open-loop comparison to the existing `TwoPointsOnParallelLines` differential-game pilot. It uses the pinned source re-expression and current three-stage finite action catalog. The known opponent signal is `v=(+1,+1,+1)`. The comparison enumerates 27 minimizing-control plans for exact polytopes, boxes, zonotopes, parallelotopes and ellipsoids. The selected exact nominal objective is `{nominal_value:.8f}`; its selected action indices are `{selected_attempt["action_indices"]}`.

The separate exact finite minimax reference has value `{minimax_value:.8f}` with the opponent selecting from `{-1,0,+1}` at each stage. These values use different opponent information and disturbance assumptions. They are shown as adjacent context, not as directly comparable claims.

The source task uses continuous actions and a 10-second horizon. This is an explicit three-stage adaptation. The objective is squared terminal position gap, monotone-equivalent for minimizers to the source negative absolute-gap reward. All values are numerical, not validated arithmetic certificates. Approximation scores are ranking estimates only and establish no certified lower or upper bound on the objective; the saved selected replay is a feasible finite-catalog witness.

The two-panel figure uses player phase planes `(x1,x2)` and `(x3,x4)`. It overlays the nominal replay on the prior report's forward/backward game geometry, intersections, representation projections, and finite minimax trajectories. The geometry is identified by its frozen report hashes in `result.json`.

## Reproduce

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_NOMINAL_REPORT=ON
cmake --build build/dev --target csl_issue824_nominal_report --parallel 4
python3 scripts/reports/exp824/make_nominal_report.py \\
  build/dev/csl_issue824_nominal_report build/dev \\
  reports/algorithm-results/issue824-two-points-nominal-v1
python3 scripts/reports/exp824/check_nominal.py \\
  reports/algorithm-results/issue824-two-points-nominal-v1/result.json
```

One warmup and seven batches of ten calls record descriptive API timings for all five nominal tracks together. Caller-side status checks and score consumption occur after each timed interval. The interval excludes fixture construction, the separate minimax reference, serialization, independent checking, build and rendering. The report makes no speedup, scalability or bottleneck claim; no separate limiter profile was performed.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    sums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sums.items()), encoding="ascii")


if __name__ == "__main__":
    main()

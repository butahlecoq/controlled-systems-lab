#!/usr/bin/env python3
"""Capture and render the saved MPC-05 finite causal minimax pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

import reference

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "scripts/reports/mpc05/check_smoke.py"
SOURCES = (
    "include/csl/optimization/finite_causal_minimax.hpp",
    "src/optimization/finite_causal_minimax.cpp",
    "benchmarks/reporting/mpc05/causal_tree_driver.cpp",
    "scripts/reports/mpc05/check_smoke.py",
    "scripts/reports/mpc05/reference.py",
    "scripts/reports/mpc05/make_report.py",
    "scripts/reports/stage_mpc05_causal_tree.py",
    "reports/algorithm-results/env717-two-points-pilot-v1/figure-data.json",
    "reports/algorithm-results/env717-two-points-pilot-v1/projections.svg",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    build_dir = args.build_dir.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty report directory: {output}")

    completed = subprocess.run([str(executable), "--smoke"], check=True,
                               capture_output=True, text=True)
    result = json.loads(completed.stdout)
    subprocess.run(["python3", str(CHECKER), str(executable)], check=True)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reference.render(result_path, output)
    if not args.build_log.is_file() or args.build_log.stat().st_size == 0:
        raise SystemExit("a nonempty build log is required for the saved evidence bundle")
    shutil.copyfile(args.build_log, output / "build.log")

    cache_path = build_dir / "CMakeCache.txt"
    cache = cache_path.read_text(encoding="utf-8")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER") or "unknown"
    compiler_version = subprocess.run([compiler, "--version"], check=True,
                                      capture_output=True, text=True).stdout.splitlines()[0]
    source_hashes = {name: sha256(ROOT / name) for name in SOURCES}
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout
    try:
        output_relative = output.relative_to(ROOT).as_posix().rstrip("/")
    except ValueError:
        output_relative = None
    status_entries = [line for line in status.splitlines()
                      if not (output_relative and line[3:].split(" -> ")[-1].startswith(output_relative))]
    two = result["two_points"]
    capture = {
        "schema": "csl.mpc05-causal-tree-capture/1",
        "source_commit": commit,
        "working_tree_clean": not bool(status_entries),
        "compiler": compiler_version,
        "cmake_build_type": cache_value(cache, "CMAKE_BUILD_TYPE"),
        "highs_version": two["causal_tree"]["solver"],
        "report_executable_sha256": sha256(executable),
        "source_sha256": source_hashes,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpus": __import__("os").cpu_count(),
        "measurement": "No performance timings collected; this run compares numerical values and policy witnesses.",
        "run": [str(executable), "--smoke"],
    }
    (output / "capture.json").write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
    readme = f'''# MPC-05 finite causal minimax pilot

This saved run compares the dependency-free finite Bellman solver with an independent HiGHS extensive-form scenario-tree model on correctness fixtures and the `TwoPointsOnParallelLines` differential-game adaptation.

The applied example has three 0.1-second stages, finite controls `{-2.5, 0, 2.5}`, finite disturbances `{-1, 0, 1}`, exact full-state observation, and terminal squared position gap. The two figure panels are the players' phase planes `(x1,x2)` and `(x3,x4)`. They show forward reachable polytopes, the terminal reachable sets, robust backward-winning nodes, forward/backward intersections, and the replayed worst-case trajectory. The plotted path was checked against the causal policy replay for this run.

The upstream environment uses continuous controls over 10 seconds. This three-stage finite adaptation is not an RL reproduction and does not establish a continuous-control or continuous-disturbance guarantee. The original source code is not copied.

The causal value is `{two['causal_bellman_value']:.8f}`, the open-loop fixed-plan value is `{two['open_loop_fixed_plan_value']:.8f}`, and the executed fixed-plan re-planning value is `{two['executed_replanning_value']:.8f}`. These values coincide for this adaptation. The separate strict-gap fixture gives fixed-plan 2, executed re-planning 2, and causal value 1. No runtime or comparative performance claim is made.

The stock do-mpc multi-stage formulation is not used as a worst-case baseline: its documented objective is a weighted scenario sum and its robust horizon may truncate branching. A worst-leaf epigraph and full-horizon branching are required for this finite exact comparison. We use an explicit complete HiGHS tree. The report does not claim that a custom do-mpc extension is impossible and does not run a do-mpc performance comparison. The [official formulation](https://www.do-mpc.com/en/latest/theory_mpc.html) also distinguishes finite scenarios from continuous uncertainty guarantees. The existing [adaptive-policy proof audit](../../../docs/research/adaptive-policy-proof-audit.md) exhibits an interior worst disturbance, so finite vertices alone do not certify the continuous case.

Reproduce from the repository root with the recorded CMake Release build:

```sh
cmake --preset dev -DCSL_BUILD_MPC05_REPORT=ON
cmake --build build/dev --target csl_mpc05_causal_tree_report --parallel 2 2>&1 | tee /tmp/mpc05-build.log
python3 scripts/reports/mpc05/make_report.py \\
  --executable build/dev/csl_mpc05_causal_tree_report \\
  --build-dir build/dev \\
  --build-log /tmp/mpc05-build.log \\
  --output /tmp/mpc05-causal-tree
```

`capture.json` records source fingerprints, compiler, solver version, and host. `build.log` records the native driver build. `result.json` contains raw solver output; `figure-data.json` contains the independently reconstructed finite sets and policy witness; `projections.svg` is the two-panel figure. `index.html` is a standalone readable report.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")

    names = sorted(path.name for path in output.iterdir() if path.is_file())
    sums = "".join(f"{sha256(output / name)}  {name}\n" for name in names)
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

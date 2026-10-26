#!/usr/bin/env python3
"""Measure saved-row coordinate selection used by the VIZ-10 fuel plots.

This is a data-projection microbenchmark. It excludes solving, file loading,
matplotlib, image export, and report rendering.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import viz10_plot_companions as renderer

B07_PATH = ROOT / "reports/algorithm-results/b07-owner-approved-eight-case-v1/results.jsonl"
B09_PATH = ROOT / "reports/algorithm-results/b09-a08-source-reference-4818ddde/results.jsonl"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_datasets() -> dict[str, list[tuple[list[list[float]], tuple[tuple[int, int], ...]]]]:
    b07 = [
        (row["winner_terminal_vertices_x1_x3_x2_x4"], ((0, 1), (2, 3)))
        for row in renderer.load_jsonl(B07_PATH)
    ]
    b09 = [
        (row["winner_terminal_vertices_x1_x2_x3_x4"], ((0, 2), (1, 3)))
        for row in renderer.load_jsonl(B09_PATH)
    ]
    return {"b07": b07, "b09": b09}


def project_batch(
    dataset: list[tuple[list[list[float]], tuple[tuple[int, int], ...]]],
    iterations: int,
) -> list[list[list[tuple[float, float]]]]:
    projected = []
    for _ in range(iterations):
        projected = [
            [renderer.project_coordinates(vertices, first, second) for first, second in pairs]
            for vertices, pairs in dataset
        ]
    return projected


def validate(dataset, projected) -> None:
    expected = [
        [[(row[first], row[second]) for row in vertices] for first, second in pairs]
        for vertices, pairs in dataset
    ]
    if projected != expected:
        raise RuntimeError("projected coordinates differ from literal saved-row selection")


def percentile_summary(values: list[int]) -> dict[str, int | list[int]]:
    return {"count": len(values), "median_ns": int(statistics.median(values)),
            "range_ns": [min(values), max(values)], "samples_ns": values}


def cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--profile-output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    datasets = load_datasets()
    try:
        load_before = os.getloadavg()
    except OSError:
        load_before = None
    counts = {name: {"cases": len(data), "vertices_per_case": [len(v) for v, _ in data],
                     "projected_pairs_per_case": [len(pairs) for _, pairs in data]}
              for name, data in datasets.items()}

    # One excluded warmup for each workload; validate outputs before measuring.
    for dataset in datasets.values():
        validate(dataset, project_batch(dataset, args.iterations))

    raw: dict[str, list[int]] = {name: [] for name in datasets}
    order = []
    for pair_index in range(7):
        pair = ("b07", "b09") if pair_index % 2 == 0 else ("b09", "b07")
        for name in pair:
            start = time.perf_counter_ns()
            projected = project_batch(datasets[name], args.iterations)
            elapsed = time.perf_counter_ns() - start
            validate(datasets[name], projected)
            raw[name].append(elapsed)
            order.append({"pair": pair_index + 1, "dataset": name, "elapsed_ns": elapsed,
                          "validation": "passed"})

    # Separate profiler runs; profiler timings are not included in samples above.
    profiler = cProfile.Profile()
    for dataset in datasets.values():
        profiler.enable()
        projected = project_batch(dataset, args.iterations)
        profiler.disable()
        validate(dataset, projected)
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    with args.profile_output.open("w", encoding="utf-8") as output:
        pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("tottime").print_stats(20)

    source = Path(renderer.__file__)
    probe_source = Path(__file__).resolve()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    result = {
        "schema": "csl.review07-fuel-projection-probe/1",
        "claim": "coordinate-selection wall time only; excludes solving, input loading, plotting, and rendering",
        "source_commit": commit,
        "probe_source_sha256": digest(probe_source),
        "renderer_source_sha256": digest(source),
        "input_sha256": {"b07_results": digest(B07_PATH), "b09_results": digest(B09_PATH)},
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
                        "cpu_model": cpu_model(),
                        "load_average_before": list(load_before) if load_before else None},
        "iterations_per_sample": args.iterations,
        "warmups_per_dataset": 1,
        "alternating_pairs": 7,
        "dataset_shape": counts,
        "raw_order": order,
        "summary": {name: percentile_summary(samples) for name, samples in raw.items()},
        "all_projection_checks_passed": True,
        "profile_file": str(args.profile_output.name),
        "profile_sha256": digest(args.profile_output),
        "limitations": ["microbenchmark only", "no solver or geometry-query timing",
                        "no figure/image export timing", "no speedup or scalability claim"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

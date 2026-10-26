#!/usr/bin/env python3
"""Measure B07/B09 saved-data figure export without running the solvers."""
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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import figure_style
import viz10_plot_companions as renderer

STYLE_PATH = ROOT / "scripts/reports/styles/control-v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def render_one(kind: str, style: dict, temporary_root: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"review07-{kind}-", dir=temporary_root) as tmp:
        out = Path(tmp) / "figures"
        out.mkdir()
        receipts = []
        start = time.perf_counter_ns()
        if kind == "b07":
            figures = renderer.render_b07(out, style, receipts)
            expected_count = 8
        else:
            figures = renderer.render_b09(out, style, receipts)
            expected_count = 2
        elapsed = time.perf_counter_ns() - start

        if len(figures) != expected_count or len(receipts) != expected_count:
            raise RuntimeError(f"{kind}: unexpected figure/receipt count")
        generated = list(out.iterdir())
        if len(generated) != expected_count * 3:
            raise RuntimeError(f"{kind}: expected one SVG, PNG and export receipt per figure")
        for receipt in receipts:
            for filename, expected_hash in receipt["files"].items():
                target = out / filename
                if digest(target) != expected_hash:
                    raise RuntimeError(f"{kind}: output digest mismatch: {filename}")
        return {"elapsed_ns": elapsed, "figure_count": expected_count,
                "svg_png_receipt_count": len(generated),
                "output_bytes": sum(path.stat().st_size for path in generated),
                "validation": "passed"}


def summarize(samples: list[dict]) -> dict:
    durations = [sample["elapsed_ns"] for sample in samples]
    return {"count": len(durations), "median_ns": int(statistics.median(durations)),
            "range_ns": [min(durations), max(durations)], "samples": samples}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    parser.add_argument("--temporary-root", type=Path, default=Path(tempfile.gettempdir()))
    args = parser.parse_args()
    temporary_root = args.temporary_root.resolve()
    if not temporary_root.is_dir():
        parser.error("--temporary-root must be an existing directory")

    style = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
    if style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("wrong quantitative-axis style")
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "csl-viz10-mpl-config"))
    import matplotlib
    if matplotlib.__version__ != style["matplotlib_version"]:
        raise ValueError("Matplotlib version differs from the pinned report style")
    matplotlib.use("Agg")
    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    try:
        load_before = os.getloadavg()
    except OSError:
        load_before = None

    samples = {"b07": [], "b09": []}
    with matplotlib.rc_context(rc):
        # One excluded warmup per exporter.
        for kind in ("b07", "b09"):
            render_one(kind, style, temporary_root)
        for pair_index in range(7):
            order = ("b07", "b09") if pair_index % 2 == 0 else ("b09", "b07")
            for kind in order:
                sample = render_one(kind, style, temporary_root)
                sample["pair"] = pair_index + 1
                samples[kind].append(sample)

    # Separate profiler capture; this is not included in the wall-time samples.
    profiler = cProfile.Profile()
    with matplotlib.rc_context(rc):
        for kind in ("b07", "b09"):
            profiler.enable()
            render_one(kind, style, temporary_root)
            profiler.disable()
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    with args.profile_output.open("w", encoding="utf-8") as output:
        pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("tottime").print_stats(30)

    source = Path(renderer.__file__)
    probe_source = Path(__file__).resolve()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    result = {
        "schema": "csl.review07-fuel-plot-export-probe/1",
        "claim": "wall time for saved-data B07/B09 figure generation and SVG/PNG/export-receipt writes; no solver or geometry query",
        "source_commit": commit,
        "probe_source_sha256": digest(probe_source),
        "renderer_source_sha256": digest(source),
        "style_sha256": digest(STYLE_PATH),
        "environment": {"python": sys.version, "matplotlib": matplotlib.__version__,
                        "platform": platform.platform(), "cpu_model": cpu_model(),
                        "logical_cpus": os.cpu_count(),
                        "load_average_before": list(load_before) if load_before else None},
        "warmups_per_exporter": 1,
        "alternating_pairs": 7,
        "order": "B07 then B09 for odd-numbered pairs; B09 then B07 for even-numbered pairs",
        "summary": {kind: summarize(values) for kind, values in samples.items()},
        "profile_file": args.profile_output.name,
        "profile_sha256": digest(args.profile_output),
        "scope_limits": ["saved input loading and hashing are included in each renderer call",
                         "SVG, PNG and per-figure JSON receipt writes are included",
                         "gallery index and manifest generation are excluded",
                         "solver, geometry query and materialization are excluded",
                         "one warm Python process; no cold-start claim",
                         "no speedup, solver latency or scalability claim"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

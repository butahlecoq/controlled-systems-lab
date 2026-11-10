#!/usr/bin/env python3
"""Render verified exact B04 stage data as stable two-panel scientific figures."""

from __future__ import annotations

import argparse
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import geometry  # noqa: E402
REPORTS_DIR = ROOT / "scripts/reports"
if str(REPORTS_DIR) not in sys.path:
    sys.path.insert(0, str(REPORTS_DIR))
from figure_style import STYLE_ID, configure_numeric_axis  # noqa: E402

STAGE_PATH = ROOT / "docs/research/evidence/b04-source-moment-stage-sets.json"
OUTPUT_DIR = ROOT / "docs/research/evidence/b04-source-moment-figures"
COLORS = {"forward": "#3274a1", "backward": "#d47720", "corridor": "#2d9c66"}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _xy(values, pair):
    return [[float(Q(point[index])) for point in values] for index in pair]


def _draw(axis, values, pair, kind):
    x, y = _xy(values, pair)
    color = COLORS[kind]
    if len(x) > 2:
        if kind != "backward":
            axis.fill(x, y, color=color,
                      alpha=.16 if kind == "corridor" else .045,
                      zorder=2 if kind == "corridor" else 0)
        axis.plot(x + [x[0]], y + [y[0]], color=color,
                  linewidth=1.05 if kind == "corridor" else .8,
                  linestyle="--" if kind == "backward" else "-",
                  alpha=.85, zorder=2)
    elif len(x) == 2:
        axis.plot(x, y, color=color, linewidth=1.8, zorder=3)
    elif x:
        axis.scatter(x, y, color=color, s=14, zorder=4)


def render(stage_data: dict, output_dir: Path = OUTPUT_DIR) -> dict:
    certificate = json.loads(geometry.CERTIFICATE_PATH.read_text(encoding="utf-8"))
    geometry.verify_stage_sets(stage_data, certificate)
    stages = stage_data["stages"]
    if len(stages) != 17 or [item["stage"] for item in stages] != list(range(17)):
        raise ValueError("figure input must contain exactly stages 0 through 16")
    output_dir.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({
        "font.size": 10, "axes.titlesize": 12, "axes.labelsize": 11,
        "figure.facecolor": "white", "axes.facecolor": "white", "svg.fonttype": "none",
        "svg.hashsalt": "csl-b04-source-moment-figures-v1",
    }):
        fig, axes = plt.subplots(1, 2, figsize=(14.5, 9.5))
        panels = [
            ((0, 1), "Oxidizer projection: x1-x2",
             ("oxidizer flow x1 (kg/s)", "oxidizer stock x2 (kg)"), (1200, 0)),
            ((2, 3), "Fuel projection: x3-x4",
             ("fuel flow x3 (kg/s)", "fuel stock x4 (kg)"), (450, 0)),
        ]
        for axis, (pair, title, labels, target) in zip(axes, panels):
            for stage in stages:
                for kind in ("forward", "backward", "corridor"):
                    _draw(axis, stage["physical_sets"][kind], pair, kind)
            states = [item["physical_witness"] for item in stages]
            x, y = _xy(states, pair)
            axis.plot(x, y, "o-", color="#17212b", markersize=3,
                      linewidth=1.45, zorder=5)
            axis.scatter(x[0], y[0], s=100, marker="o", edgecolor="#17212b",
                         facecolor="white", linewidth=1.8, zorder=7)
            axis.scatter(x[-1], y[-1], s=100, marker="X", color="#c53535", zorder=7)
            axis.scatter(*target, s=130, marker="*", color="#a12e8d", zorder=6)
            for stage_index, (x_value, y_value) in enumerate(zip(x, y)):
                axis.annotate(str(stage_index), (x_value, y_value), xytext=(5, 3),
                              textcoords="offset points", fontsize=8, color="#17212b")
            axis.set(title=title, xlabel=labels[0], ylabel=labels[1])
            configure_numeric_axis(axis, bins=6)
            axis.margins(x=.1, y=.04)

        legend = [
            Patch(facecolor=COLORS["forward"], alpha=.2, edgecolor=COLORS["forward"], label="forward reachable F[k]"),
            Line2D([0], [0], color=COLORS["backward"], linestyle="--", label="backward-to-optimum B[k]"),
            Patch(facecolor=COLORS["corridor"], alpha=.3, edgecolor=COLORS["corridor"], label="intersection F[k] ∩ B[k]"),
            Line2D([0], [0], color="#17212b", marker="o", label="one exact optimal trajectory"),
            Line2D([0], [0], color="#17212b", marker="o", markerfacecolor="white", linestyle="none", label="initial point"),
            Line2D([0], [0], color="#c53535", marker="X", linestyle="none", label="optimal terminal singleton"),
            Line2D([0], [0], color="#a12e8d", marker="*", linestyle="none", label="objective target reference"),
        ]
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .045),
                   ncol=3, frameon=False, fontsize=10)
        fig.suptitle(
            "B04 source candidate: all 17 times on the same phase plots\n"
            "Nominal exact sets and one member of the complete 14-dimensional optimal family",
            fontsize=15, y=.98)
        fig.text(.5, .015,
                 "Labels are stage k=0…16, time t=6.25k seconds. Each outline is one time slice; no hull across times.\n"
                 "Exact commented initial data; J*=30.8991360300… . Source reconstruction, not an attribution of the historical generating run.",
                 ha="center", va="bottom", fontsize=9)
        fig.subplots_adjust(top=.88, bottom=.19, wspace=.25, left=.075, right=.975)
        svg = output_dir / "b04-all-stage-reachability.svg"
        png = output_dir / "b04-all-stage-reachability.png"
        fig.savefig(svg, metadata={"Date": None, "Creator": f"Matplotlib {matplotlib.__version__}"})
        fig.savefig(png, dpi=190, metadata={"Software": f"Matplotlib {matplotlib.__version__}"})
        plt.close(fig)

    data_hash = hashlib.sha256(json.dumps(stage_data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    certificate_hash = _hash(geometry.CERTIFICATE_PATH)
    style_path = REPORTS_DIR / "figure_style.py"
    manifest = {
        "schema": "b04.source-candidate.figure-export/1",
        "source_relation": {
            "source_model_sha256": stage_data["source_model_sha256"],
            "certificate_sha256": certificate_hash,
            "stage_sets_path": str(STAGE_PATH.relative_to(ROOT)),
            "stage_sets_sha256": _hash(STAGE_PATH),
            "verified_stage_data_canonical_sha256": data_hash,
            "scope": stage_data["scope"],
        },
        "producer_sha256": _hash(Path(__file__)),
        "geometry_sha256": _hash(Path(geometry.__file__)),
        "checker_sha256": _hash(ROOT / "docs/research/tools/check_b04_source_moments.py"),
        "helper": {"path": str(style_path.relative_to(ROOT)), "sha256": _hash(style_path), "style_id": STYLE_ID},
        "matplotlib_version": matplotlib.__version__,
        "float_conversion": "renderer only; stage data remains rational strings",
        "outputs": [
            {"path": svg.name, "sha256": _hash(svg), "bytes": svg.stat().st_size},
            {"path": png.name, "sha256": _hash(png), "bytes": png.stat().st_size},
        ],
    }
    export_path = output_dir / "figure-export.json"
    export_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=STAGE_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    try:
        stage_data = json.loads(args.input.read_text(encoding="utf-8"))
        result = render(stage_data, args.output_dir)
        print(json.dumps({"status": "rendered-verified", "outputs": result["outputs"],
                          "matplotlib_version": result["matplotlib_version"]}, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())

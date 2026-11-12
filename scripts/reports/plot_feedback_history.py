#!/usr/bin/env python3
"""Plot every saved box-feedback stage from one observed-state query."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from contracts import load_task
from figure_style import STYLE_ID, configure_numeric_axis
from stage_projection_figures import PALETTE, BACKGROUND, FOREGROUND

PLANES = {"syn-nl-lv-01": [(0, 1)], "earth-orbit": [(0, 3)],
          "syn-nl-fuel-01": [(2, 0), (3, 1)]}


def axis_bounds(member, dimension):
    lower = [float("-inf")] * dimension
    upper = [float("inf")] * dimension
    for rows, bounds, equality in ((member["inequalities"], member["upper_bounds"], False),
                                   (member["equalities"], member["equality_values"], True)):
        if len(rows) != len(bounds):
            raise ValueError("box row count differs from bounds")
        for row, bound in zip(rows, bounds):
            active = [i for i, value in enumerate(row) if value != 0]
            if len(row) != dimension or len(active) != 1:
                raise ValueError("box membership is not axis-aligned in full state space")
            i = active[0]
            value = bound / row[i]
            if row[i] > 0 or equality:
                upper[i] = min(upper[i], value)
            if row[i] < 0 or equality:
                lower[i] = max(lower[i], value)
    import math
    if any(not math.isfinite(v) for v in lower + upper) or any(a > b for a,b in zip(lower, upper)):
        raise ValueError("box does not have finite ordered bounds")
    return lower, upper


def render(task_name, response, attempt_path, destination, capture_source, renderer_source):
    if destination.exists() or destination.is_symlink():
        raise ValueError("output directory must be new")
    task = load_task(task_name)
    raw = response.read_bytes()
    data = json.loads(raw)
    attempt_bytes = attempt_path.read_bytes()
    attempt = json.loads(attempt_bytes)
    if (attempt.get("status") != "complete" or attempt.get("completed_holds") != task["episode"]["intervals"]
            or attempt.get("task_id") != task["task_id"]):
        raise ValueError("complete matching observed trajectory required")
    stage0 = json.loads((attempt_path.parent / "stage-000.json").read_text())
    reference = stage0["native_query_capture"]
    metadata_bytes = (attempt_path.parent / reference["path"]).read_bytes()
    if hashlib.sha256(metadata_bytes).hexdigest() != reference["sha256"]:
        raise ValueError("saved stage capture metadata differs")
    metadata = json.loads(metadata_bytes)
    if hashlib.sha256(raw).hexdigest() != metadata["response"]["sha256"]:
        raise ValueError("response differs from the saved first query")
    geometry = data["geometry"]
    n = len(task["model"]["states"])
    horizon = data["coordinates"]["horizon"]
    if (geometry["status"] != "complete" or geometry["family"] != "box"
            or len(geometry["stages"]) != horizon + 1):
        raise ValueError("complete all-stage box geometry required")
    protocol = "cold at each query; known warm-start protocol gap"
    initialization_sources = []
    first_request = json.loads((attempt_path.parent / metadata["request"]["path"]).read_bytes())
    if "warm_start" in first_request:
        stage1 = json.loads((attempt_path.parent / "stage-001.json").read_bytes())
        next_ref = stage1["native_query_capture"]
        next_metadata_bytes = (attempt_path.parent / next_ref["path"]).read_bytes()
        if hashlib.sha256(next_metadata_bytes).hexdigest() != next_ref["sha256"]:
            raise ValueError("next query metadata differs")
        next_metadata = json.loads(next_metadata_bytes)
        next_request_bytes = (attempt_path.parent / next_metadata["request"]["path"]).read_bytes()
        if hashlib.sha256(next_request_bytes).hexdigest() != next_metadata["request"]["sha256"]:
            raise ValueError("next query request differs")
        next_request = json.loads(next_request_bytes)
        if (first_request["warm_start"]["policy"] != "initial-zero-control-rollout"
                or next_request["warm_start"]["policy"] != "shift-prior-primal-drop-applied-stage-no-terminal-repeat"
                or next_request["warm_start"]["dual_policy"] != "zero-every-solve"):
            raise ValueError("unexpected recorded initialization protocol")
        protocol = "initial observed-state rollout; subsequent shifted history primal and zero supplied duals"
        initialization_sources = [metadata["request"], next_metadata["request"]]
    protocol_label = ("Shifted primal; supplied zero duals; composite SDK build."
                      if initialization_sources else "Cold starts; composite SDK build.")
    all_sets = []
    for k, stage in enumerate(geometry["stages"]):
        if stage["stage"] != k or stage["coordinates"] != list(range(n)) or "intersection_h" not in stage:
            raise ValueError("missing full-state intersection, stage or state coordinates")
        members = {member["role"]: member for member in stage["memberships"]}
        if set(members) != {"forward", "backward", "intersection"}:
            raise ValueError("missing F/B/I membership")
        all_sets.append({role: axis_bounds(members[role], n) for role in members})
    trajectory = attempt["physical_states"]
    if len(trajectory) != horizon + 1 or any(len(state) != n for state in trajectory):
        raise ValueError("observed trajectory dimensions differ")
    target = task["objective"]["source_definition"]["terminal_target"]
    bounds = [row.get("bounds") for row in task["model"]["states"]]
    destination.mkdir(parents=True)
    output = []
    cmap = LinearSegmentedColormap.from_list("csl-omarchy-stages", [PALETTE[1], PALETTE[0], PALETTE[2]])
    norm = Normalize(0, max(horizon, 1))
    roles = (("forward", "-", "Forward F"), ("backward", "--", "Forward-relevant backward B"),
             ("intersection", ":", "Intersection I"))
    for first, second in PLANES[task_name]:
        if bounds[first] is None or bounds[second] is None:
            raise ValueError("terminal physical state bounds unavailable for this projection")
        for variant in ("screen", "print"):
            dark = variant == "screen"
            background = BACKGROUND if dark else "white"
            foreground = FOREGROUND if dark else "#202124"
            fig, axis = plt.subplots(figsize=(7.2, 8.8))
            fig.subplots_adjust(left=0.14, right=0.83, top=0.89, bottom=0.33)
            fig.patch.set_facecolor(background)
            axis.set_facecolor(background)
            for role, linestyle, _ in roles:
                for k, stage in enumerate(all_sets):
                    lower, upper = stage[role]
                    axis.add_patch(Rectangle((lower[first], lower[second]),
                        upper[first]-lower[first], upper[second]-lower[second],
                        fill=False, edgecolor=cmap(norm(k)), linestyle=linestyle,
                        linewidth=0.85, alpha=0.72 if dark else 0.9))
            lo1, hi1 = bounds[first]
            lo2, hi2 = bounds[second]
            axis.add_patch(Rectangle((lo1, lo2), hi1-lo1, hi2-lo2, fill=False,
                edgecolor=PALETTE[3] if dark else "#9e3157", linestyle="-.", linewidth=1.3))
            axis.plot([x[first] for x in trajectory], [x[second] for x in trajectory],
                      color=foreground, linewidth=2.1, zorder=6)
            axis.scatter([trajectory[0][first]], [trajectory[0][second]], marker="o",
                         s=46, c=[PALETTE[4] if dark else "#25683a"], edgecolors=foreground, zorder=7)
            axis.scatter([target[first]], [target[second]], marker="*", s=120,
                         c=[PALETTE[2] if dark else "#935500"], edgecolors=foreground, zorder=8)
            axis.autoscale_view()
            first_state, second_state = task["model"]["states"][first], task["model"]["states"][second]
            axis.set_xlabel(f"{first_state['name']} ({first_state['unit']})", color=foreground)
            axis.set_ylabel(f"{second_state['name']} ({second_state['unit']})", color=foreground)
            axis.set_title("All box F/B/I stages and observed trajectory", color=foreground)
            axis.tick_params(colors=foreground)
            for spine in axis.spines.values():
                spine.set_color(foreground)
            configure_numeric_axis(axis)
            handles = [Line2D([0], [0], color=foreground, linestyle=style, label=label) for _,style,label in roles]
            handles += [Line2D([0], [0], color=foreground, linewidth=2, label="Observed nonlinear plant"),
                Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE[4] if dark else "#25683a",
                       markeredgecolor=foreground, label="Initial state"),
                Line2D([0], [0], marker="*", color="none", markerfacecolor=PALETTE[2] if dark else "#935500",
                       markeredgecolor=foreground, markersize=10, label="Soft terminal reference"),
                Line2D([0], [0], color=PALETTE[3] if dark else "#9e3157", linestyle="-.", label="Terminal state bounds")]
            legend = axis.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.25),
                                 ncol=2, fontsize=9, frameon=False)
            for text in legend.get_texts():
                text.set_color(foreground)
            colorbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axis, label="Local predicted stage")
            colorbar.ax.yaxis.label.set_color(foreground)
            colorbar.ax.tick_params(colors=foreground)
            fig.suptitle(f"{task_name} · first observed query, stages 0–{horizon}", color=foreground, y=0.97)
            fig.text(0.5, 0.035, "Outer affine-predictor sets; observed nonlinear plant.\n" + protocol_label,
                     ha="center", color=foreground, fontsize=8)
            path = destination / f"all-stages-{first}-{second}-{variant}.png"
            fig.savefig(path, dpi=150, facecolor=background)
            vector = path.with_suffix(".svg")
            fig.savefig(vector, facecolor=background)
            vector.write_text("".join(line.rstrip() + chr(10) for line in vector.read_text().splitlines()))
            plt.close(fig)
            for rendered in (path, vector):
                output.append({"path": rendered.name, "sha256": hashlib.sha256(rendered.read_bytes()).hexdigest(),
                               "raw_state_indices": [first, second], "variant": variant})
    receipt = {"schema": "csl.feedback-history-stage-figure/1", "task_id": task["task_id"],
        "input_response_sha256": hashlib.sha256(raw).hexdigest(),
        "input_attempt_sha256": hashlib.sha256(attempt_bytes).hexdigest(), "capture_source_commit": capture_source,
        "renderer_source_commit": renderer_source,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "query_scope": "first observed-state query; all predicted stages, not all replans",
        "trajectory_scope": "observed nonlinear plant across full episode",
        "terminal_feasibility": "projected physical terminal state bounds; source terminal set otherwise universal",
        "terminal_reference": "soft objective reference, not a terminal constraint",
        "full_state_before_projection": True, "family": "box", "stages": horizon+1,
        "quantitative_style": STYLE_ID, "palette": "shared Omarchy stage palette",
        "execution_protocol": protocol, "initialization_sources": initialization_sources,
        "build_scope": "composite current compiled sources and f4 installed SDK",
        "figures": output}
    (destination / "render-receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=PLANES, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--capture-source", required=True)
    parser.add_argument("--renderer-source", required=True)
    args = parser.parse_args()
    render(args.task, args.response, args.attempt, args.output, args.capture_source, args.renderer_source)


if __name__ == "__main__":
    main()

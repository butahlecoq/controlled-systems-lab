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
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from contracts import load_task
from figure_style import STYLE_ID, configure_numeric_axis

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


def render(task_name, response, destination, capture_source, renderer_source):
    if destination.exists() or destination.is_symlink():
        raise ValueError("output directory must be new")
    task = load_task(task_name)
    raw = response.read_bytes()
    data = json.loads(raw)
    geometry = data["geometry"]
    n = len(task["model"]["states"])
    horizon = data["coordinates"]["horizon"]
    if (geometry["status"] != "complete" or geometry["family"] != "box"
            or len(geometry["stages"]) != horizon + 1):
        raise ValueError("complete all-stage box geometry required")
    all_sets = []
    for k, stage in enumerate(geometry["stages"]):
        if stage["stage"] != k or stage["coordinates"] != list(range(n)):
            raise ValueError("unexpected stage or state coordinates")
        members = {member["role"]: member for member in stage["memberships"]}
        if set(members) != {"forward", "backward", "intersection"}:
            raise ValueError("missing F/B/I membership")
        all_sets.append({role: axis_bounds(members[role], n) for role in members})
    destination.mkdir(parents=True)
    output = []
    cmap = plt.get_cmap("viridis")
    norm = Normalize(0, max(horizon, 1))
    for first, second in PLANES[task_name]:
        fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
        for axis, role, title in zip(axes, ("forward", "backward", "intersection"),
                                     ("Forward F", "Forward-relevant backward B", "Intersection I")):
            for k, stage in enumerate(all_sets):
                lower, upper = stage[role]
                axis.add_patch(Rectangle((lower[first], lower[second]),
                    upper[first]-lower[first], upper[second]-lower[second],
                    fill=False, edgecolor=cmap(norm(k)), linewidth=0.8, alpha=0.75))
            axis.autoscale_view()
            first_state, second_state = task["model"]["states"][first], task["model"]["states"][second]
            axis.set_xlabel(f"{first_state['name']} ({first_state['unit']})")
            axis.set_ylabel(f"{second_state['name']} ({second_state['unit']})")
            axis.set_title(title)
            configure_numeric_axis(axis)
        fig.suptitle(f"{task_name}: box F/B/I at every predicted stage, first observed query")
        fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axes, label="Local predicted stage")
        path = destination / f"all-stages-{first}-{second}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        output.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "raw_state_indices": [first, second]})
    receipt = {"schema": "csl.feedback-history-stage-figure/1", "task_id": task["task_id"],
        "input_response_sha256": hashlib.sha256(raw).hexdigest(), "capture_source_commit": capture_source,
        "renderer_source_commit": renderer_source,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "query_scope": "first observed-state query; all predicted stages, not all replans",
        "full_state_before_projection": True, "family": "box", "stages": horizon+1,
        "quantitative_style": STYLE_ID, "colormap": "viridis", "figures": output}
    (destination / "render-receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=PLANES, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture-source", required=True)
    parser.add_argument("--renderer-source", required=True)
    args = parser.parse_args()
    render(args.task, args.response, args.output, args.capture_source, args.renderer_source)


if __name__ == "__main__":
    main()

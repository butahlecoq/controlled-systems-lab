#!/usr/bin/env python3
"""Render the analytic MPC-02 slew projections from rational source data."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import geometry_figures


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/examples/mpc02-slew-analytic-source.json"
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
OUTPUT = ROOT / "docs/examples"
TEMP_ROOT = ROOT / "build/mpc02-tests"


def point(values: list[str]) -> list[float]:
    return [float(Fraction(value)) for value in values]


def render(name: str, title: str, description: str, axes: dict, series: list[dict],
           source_hash: str) -> None:
    document = {"schema": "csl.saved-geometric-plot/1", "title": title,
                "description": description, "axes": axes, "aspect": "equal",
                "series": series}
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpc02-figure-", dir=TEMP_ROOT) as temp:
        generated = Path(temp)
        receipt = geometry_figures.render(document, STYLE, generated)
        for suffix in ("svg", "png"):
            shutil.copyfile(generated / f"geometry.{suffix}", OUTPUT / f"{name}.{suffix}")
        provenance = {"schema": "csl.mpc02-analytic-figure-export/1",
                      "scenario_id": "mpc02-slew-2d-v1",
                      "source_json": "mpc02-slew-analytic-source.json",
                      "source_sha256": source_hash,
                      "plot": document, "renderer_receipt": receipt}
        (OUTPUT / f"{name}-export.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    if source.get("schema") != "csl.mpc02-analytic-projection-source/1":
        raise ValueError("unexpected MPC-02 analytic source schema")
    os.environ.setdefault("MPLCONFIGDIR", str(TEMP_ROOT / "mpl-config"))
    projection = source["projection"]
    controls = [point(vertex) for vertex in projection["control_vertices_rational"]]
    states = [point(vertex) for vertex in projection["terminal_state_vertices_rational"]]
    target = point(source["model"]["terminal_target"])
    stage_optimum = point(projection["stage_box_optimum_control_rational"])
    slew_optimum = point(projection["slew_optimum_control_rational"])
    terminal_optimum = point(projection["slew_optimum_terminal_state_rational"])
    source_hash = hashlib.sha256(source_bytes).hexdigest()

    render("mpc02-slew-terminal-state-projection",
        "MPC-02 exact terminal-state projection under a slew limit",
        "Exact linear image of the bounded control polygon for scenario mpc02-slew-2d-v1. "
        "The target and unique analytic slew-constrained minimizer are marked separately; "
        "this is not a solver trace or a sampled trajectory.",
        {"x": {"label": "terminal state x1(2) (dimensionless)"},
         "y": {"label": "terminal state x2(2) (dimensionless)"}},
        [{"kind": "polygon", "label": "Exact terminal-state projection", "color": "#2367a8",
          "points": states, "fill": True, "alpha": 0.18},
         {"kind": "points", "label": "Objective target (1/2, 0)", "color": "#555555",
          "points": [target], "size": 48},
         {"kind": "points", "label": "Unique slew optimum (3/8, 1/8)", "color": "#b23b33",
          "points": [terminal_optimum], "size": 48}], source_hash)

    render("mpc02-slew-memory-projection",
        "MPC-02 exact projection onto the lifted memory coordinates",
        "The memory plane keeps p1=u0 and p2=u1 and omits the physical state coordinates. "
        "The stage-box optimum lies outside the slew strip; the red point is the unique "
        "analytic slew-constrained minimizer.",
        {"x": {"label": "lifted memory p1 = u0 (dimensionless)"},
         "y": {"label": "lifted memory p2 = u1 (dimensionless)"}},
        [{"kind": "polygon", "label": "Exact feasible memory projection", "color": "#2367a8",
          "points": controls, "fill": True, "alpha": 0.18},
         {"kind": "points", "label": "Stage-box optimum (1/2, 0), slew-infeasible", "color": "#777777",
          "points": [stage_optimum], "size": 48},
         {"kind": "points", "label": "Unique slew optimum (3/8, 1/8)", "color": "#b23b33",
          "points": [slew_optimum], "size": 48}], source_hash)


if __name__ == "__main__":
    main()

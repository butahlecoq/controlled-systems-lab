"""Render selected 4D replay trajectories from a saved VIZ-04 artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMAS = {"csl.viz04-replay-comparison/1", "csl.viz04-replay-comparison/2",
           "csl.viz04-replay-comparison/3"}
PAIRS = ((0, 2), (1, 3))


def set_coordinate_aspect(axis, x_coord: dict, y_coord: dict) -> str:
    if x_coord["unit"] == y_coord["unit"]:
        axis.set_aspect("equal", adjustable="box")
        return "Equal x/y scale because paired coordinates share units."
    return "Independent x/y scales because paired coordinates use different units."


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") not in SCHEMAS:
        raise ValueError(f"expected one of {', '.join(sorted(SCHEMAS))}")
    coordinates = value.get("state_coordinates", [])
    witnesses = value.get("witnesses", [])
    if len(coordinates) != 4 or len(witnesses) != 2:
        raise ValueError("the visual example requires four state coordinates and two witnesses")
    for witness in witnesses:
        if witness.get("policy_class") != "selected_linear_witness":
            raise ValueError("the visual example must preserve the selected-witness policy class")
        claims = witness.get("claims", {})
        if any(claims.get(name) != "not_checked" for name in (
                "nonlinear_feasibility", "nonlinear_objective_quality", "nonlinear_global_optimality")):
            raise ValueError("this renderer cannot present unchecked replay claims as verified")
        replay = witness["replay"]
        if replay["status"] != "complete" or len(replay["states"]) != len(replay["times"]):
            raise ValueError("the visual example requires complete replay states on every time point")
        if len(replay["states"][0]) != 4:
            raise ValueError("replay states must be four-dimensional")
    objectives = [witness["linear_objective"] for witness in witnesses]
    replay_objectives = [witness["replay"]["original_objective"] for witness in witnesses]
    if objectives[0] != objectives[1] or replay_objectives[0] == replay_objectives[1]:
        raise ValueError("fixture must have tied linear objectives and distinct replay objectives")
    return value


def render(value: dict, output: Path) -> None:
    import matplotlib

    if matplotlib.__version__ != "3.11.2":
        raise RuntimeError("Matplotlib 3.11.2 is required; use scripts/reports/requirements.txt")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    colors = ("#225b92", "#b14d28")
    markers = ("o", "s")
    labels = ("Linear witness 1", "Linear witness 2")
    aspect_notes = []
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                                "svg.hashsalt": "csl-viz04-replay-v1", "svg.fonttype": "path"}):
        fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.7))
        for axis, (x_index, y_index), title in zip(
                axes, PAIRS, ("Flow projection", "Stock projection")):
            x_coord, y_coord = (value["state_coordinates"][i] for i in (x_index, y_index))
            for index, witness in enumerate(value["witnesses"]):
                replay = witness["replay"]
                x_values = [state[x_index] for state in replay["states"]]
                y_values = [state[y_index] for state in replay["states"]]
                axis.plot(x_values, y_values, color=colors[index], marker=markers[index],
                          linewidth=2.2, markersize=7, label=labels[index])
            axis.set_title(title)
            axis.set_xlabel(f"{x_coord['label']} ({x_coord['unit']})")
            axis.set_ylabel(f"{y_coord['label']} ({y_coord['unit']})")
            aspect_notes.append(set_coordinate_aspect(axis, x_coord, y_coord))
            axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
            axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
            axis.grid(True, which="major", color="#aeb8c2", linewidth=0.7, alpha=0.45)
            axis.set_axisbelow(True)
            axis.legend(frameon=False, loc="best")
        fig.suptitle("Selected witness replays projected from four state coordinates", fontsize=13)
        fig.tight_layout(rect=(0, 0.13, 1, 0.94))
        notes = (
            " ".join(dict.fromkeys(aspect_notes)),
            "Analytic VIZ-04 toy fixture. Paths are selected trajectories, not reachable-set boundaries.",
            "Not a B04 replay or a historical fuel result.",
        )
        for y, note in zip((0.075, 0.045, 0.015), notes):
            fig.text(0.5, y, note, ha="center", va="bottom", fontsize=8.5, color="#35414c")
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, format="svg", metadata={"Date": None, "Creator": None})
        plt.close(fig)
    output.write_text("\n".join(line.rstrip() for line in output.read_text(encoding="utf-8").splitlines()) + "\n",
                      encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(load(args.artifact), args.output)


if __name__ == "__main__":
    main()

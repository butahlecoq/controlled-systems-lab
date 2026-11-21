"""Render the paired ten-car platoon outcomes from checked saved records."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path(sys.argv[1])
data = json.loads((root / "26.json").read_bytes())
audit = json.loads((root / "independent-audit.json").read_bytes())["rows"][25]
assert audit["number"] == 26 and data["constraints"]["stage"][0]["state"]["rows"] == 9
assert all(audit[policy]["status"] == "complete" for policy in ("open_loop", "closed_loop"))
plt.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "catalogue26"})
fig, (phase, margins) = plt.subplots(1, 2, figsize=(11.2, 4.0), layout="constrained")
line_colors = ("#23689D", "#AF542B")
for j, (key, label, linestyle) in enumerate((
    ("open_loop", "Open loop", "-"), ("closed_loop", "Observed-state MPC", "--")
)):
    states = np.asarray(data[key]["states"])
    phase.plot(states[:, -3], states[:, -2], color=line_colors[j], label=label,
               linestyle=linestyle, marker="o" if j == 0 else "x", markersize=4)
    values = []
    for i, state in enumerate(states):
        row = data["constraints"]["stage"][i] if i < data["horizon"] else data["constraints"]["terminal"][0]
        lhs = np.asarray(row["state"]["values"]).reshape(-1, states.shape[1]) @ state
        if i < data["horizon"]:
            for matrix_key, vector in (("control", data[key]["controls"][i]), ("external", data["external"][i])):
                payload = row[matrix_key]
                lhs += np.asarray(payload["values"]).reshape(payload["rows"], payload["cols"]) @ vector
        values.append(float(np.min(lhs - [bound[0] for bound in row["bounds"]])))
    margins.plot(range(len(states)), values, label=label, color=line_colors[j],
                 linestyle=linestyle, marker="o" if j == 0 else "x", markersize=4)
phase.set(xlabel="Position (m)", ylabel="Velocity (m/s)", title="Last vehicle")
phase.ticklabel_format(axis="y", style="plain", useOffset=False)
margins.axhline(0, linewidth=1, color="#333333", label="Headway limit")
margins.set(xlabel="Transition stage", ylabel="Minimum headway margin (m)", title="All nine following vehicles",
            xticks=list(range(data["horizon"] + 1)))
for ax in (phase, margins):
    ax.grid(alpha=.2)
    ax.legend(frameon=False)
fig.suptitle("Ten-car platoon · matched deterministic three-step task", fontsize=15)
fig.savefig(root / "platoon.svg", metadata={"Date": None})
fig.savefig(root / "platoon.png", dpi=150)
plt.close(fig)

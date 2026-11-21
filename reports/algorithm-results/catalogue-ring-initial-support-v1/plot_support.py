"""Render the projected feasible witness and its stage-zero supporting line."""

import argparse
import json
from fractions import Fraction
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
args = parser.parse_args()

root = Path(__file__).resolve().parent
data = json.loads((root / "certificate.json").read_bytes())
i, j = data["projection_zero_based"]
path = [(float(Fraction(state[i])), float(Fraction(state[j]))) for state in data["witness_states"]]
x, y = zip(*path, strict=True)
mpl.rcParams["svg.hashsalt"] = "catalogue-ring-initial-support-v1"
fig, ax = plt.subplots(figsize=(6.2, 4.2), layout="constrained")
line_x = (x[0] - 0.004, x[0] + 0.012)
ax.plot(
    line_x,
    [-data["support_decimal"] - value for value in line_x],
    linestyle="--",
    color="#a44023",
    label="Stage-zero support line",
)
ax.plot(x, y, "o-", color="#176f8c", label="Zero-control witness")
for stage, point in enumerate(path):
    ax.annotate(str(stage), point, xytext=(4, 7), textcoords="offset points")
ax.set(xlabel=r"First state coordinate, $x_1$", ylabel=r"Second state coordinate, $x_2$")
ax.set_aspect("equal", adjustable="datalim")
ax.xaxis.set_major_locator(MaxNLocator(5))
ax.yaxis.set_major_locator(MaxNLocator(5))
ax.grid(alpha=0.2)
ax.legend(loc="upper left", frameon=False)
fig.savefig(args.output, metadata={"Date": None})

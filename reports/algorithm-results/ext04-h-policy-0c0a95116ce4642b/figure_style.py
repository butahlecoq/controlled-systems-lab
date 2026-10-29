"""Versioned tick and grid policy for static quantitative report figures."""
from __future__ import annotations

import math


STYLE_ID = "csl-report-quantitative-v1"


def format_tick(value: float, locations: list[float]) -> str:
    """Format a tick with enough precision to keep neighboring ticks distinct."""
    finite = sorted({float(item) for item in locations if math.isfinite(float(item))})
    gaps = [right - left for left, right in zip(finite, finite[1:]) if right > left]
    spacing = min(gaps) if gaps else 1.0
    scale = max((abs(item) for item in finite), default=abs(float(value)))
    scale = max(scale, abs(float(value)))
    ratio = scale / spacing if spacing else math.inf

    if ratio >= 1e10:
        significant = min(17, max(7, math.ceil(math.log10(ratio)) + 1))
        label = f"{value:.{significant - 1}e}"
    else:
        decimals = min(17, max(0, math.ceil(-math.log10(spacing)) + 1))
        label = f"{value:.{decimals}f}"
    if label.startswith("-") and float(label) == 0.0:
        return label[1:]
    return label


def configure_numeric_axis(axis, direction: str = "both", bins: int = 5) -> None:
    """Set positioned numeric ticks, distinct labels, and quiet major grids."""
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    directions = ("x", "y") if direction == "both" else (direction,)
    for name in directions:
        dimension = getattr(axis, name + "axis")
        dimension.set_major_locator(MaxNLocator(nbins=bins, min_n_ticks=3))
        dimension.set_major_formatter(
            FuncFormatter(lambda value, _position, a=axis, d=name:
                          format_tick(value, getattr(a, d + "axis").get_majorticklocs()))
        )
    axis.set_axisbelow(True)
    axis.grid(True, which="major", axis=direction, color="#8290a3", alpha=.22, linewidth=.65)

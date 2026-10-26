"""Render saved planar geometry with the shared quantitative axis policy."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import figure_style


def render(document: dict, style_path: Path, out: Path) -> dict:
    """Render polygons, curves, points and circles without computing geometry."""
    if document.get("schema") != "csl.saved-geometric-plot/1":
        raise ValueError("expected csl.saved-geometric-plot/1")
    if not document.get("title") or not document.get("description"):
        raise ValueError("geometric plots need a title and evidence description")
    axes = document.get("axes", {})
    if any(not isinstance(axes.get(axis), dict) or not axes[axis].get("label")
           for axis in ("x", "y")):
        raise ValueError("both coordinate axes need visible labels")
    if document.get("aspect") not in {"equal", "independent"}:
        raise ValueError("aspect must be explicit")
    series = document.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("at least one saved geometry series is required")
    extent_x, extent_y = [], []
    for item in series:
        kind = item.get("kind")
        if not item.get("label") or not item.get("color"):
            raise ValueError("geometry series need a label and color")
        if kind == "circle":
            center, radius = item.get("center"), item.get("radius")
            if not isinstance(center, list) or len(center) != 2 or not isinstance(radius, (int, float)) or radius <= 0:
                raise ValueError("circle series need a two-coordinate center and positive saved radius")
            extent_x.extend((center[0] - radius, center[0] + radius))
            extent_y.extend((center[1] - radius, center[1] + radius))
        elif kind in {"polygon", "path", "points"}:
            points = item.get("points")
            if not isinstance(points, list) or not points or any(not isinstance(point, list) or len(point) != 2 for point in points):
                raise ValueError("geometry series need saved two-coordinate points")
            if kind == "polygon" and len(points) < 3:
                raise ValueError("polygon series need at least three saved vertices")
            extent_x.extend(point[0] for point in points)
            extent_y.extend(point[1] for point in points)
        else:
            raise ValueError("unknown geometry series kind: " + str(kind))

    style_bytes = Path(style_path).read_bytes()
    style = json.loads(style_bytes)
    if style.get("schema") != "csl.figure-style/1" or style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("expected the versioned csl-report-quantitative-v1 style")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("MPLCONFIGDIR", str(out.parent / "mpl-config"))
    import matplotlib
    if matplotlib.__version__ != style.get("matplotlib_version"):
        raise ValueError("Matplotlib version differs from the pinned figure style")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon

    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    with matplotlib.rc_context(rc):
        fig, axis = plt.subplots(figsize=tuple(style["projection_size"]))
        try:
            for item in series:
                kind, color = item["kind"], item["color"]
                if kind == "polygon":
                    axis.add_patch(Polygon(item["points"], closed=True,
                                           facecolor=color if item.get("fill", False) else "none",
                                           edgecolor=color, alpha=item.get("alpha", .2) if item.get("fill", False) else 1,
                                           linewidth=item.get("linewidth", 1.8),
                                           linestyle=item.get("linestyle", "-"), label=item["label"]))
                elif kind == "circle":
                    axis.add_patch(Circle(item["center"], item["radius"], fill=False,
                                          edgecolor=color, linewidth=item.get("linewidth", 1.8),
                                          linestyle=item.get("linestyle", "-"), label=item["label"]))
                elif kind == "path":
                    points = item["points"]
                    axis.plot([point[0] for point in points], [point[1] for point in points],
                              color=color, linewidth=item.get("linewidth", 1.8),
                              marker=item.get("marker"), label=item["label"])
                else:
                    points = item["points"]
                    axis.scatter([point[0] for point in points], [point[1] for point in points],
                                 s=item.get("size", style["point_size"]), color=color,
                                 alpha=item.get("alpha", style["point_alpha"]), label=item["label"])
            span_x, span_y = max(extent_x) - min(extent_x), max(extent_y) - min(extent_y)
            margin_x = .08 * span_x if span_x else max(abs(extent_x[0]) * .08, .5)
            margin_y = .08 * span_y if span_y else max(abs(extent_y[0]) * .08, .5)
            axis.set_xlim(min(extent_x) - margin_x, max(extent_x) + margin_x)
            axis.set_ylim(min(extent_y) - margin_y, max(extent_y) + margin_y)
            axis.set(xlabel=axes["x"]["label"], ylabel=axes["y"]["label"])
            if document["aspect"] == "equal":
                axis.set_aspect("equal", adjustable="box")
                scale_note = "Equal data scaling on both axes."
            else:
                scale_note = "Independent data scaling on the two axes."
            figure_style.configure_numeric_axis(axis)
            handles, labels = axis.get_legend_handles_labels()
            fig.suptitle(document["title"], fontsize=10, y=.98, wrap=True)
            fig.legend(handles, labels, fontsize="small", loc="upper center",
                       bbox_to_anchor=(.5, .9), ncol=1, framealpha=.94)
            fig.subplots_adjust(left=.2, right=.92, bottom=.18, top=.66)
            for suffix, save_args in (("svg", {"metadata": {"Date": None, "Creator": "CSL saved geometry exporter"}}),
                                      ("png", {"dpi": style["png_dpi"], "metadata": {"Software": style["style_id"]}})):
                fig.savefig(out / ("geometry." + suffix), **save_args)
            svg_path = out / "geometry.svg"
            tree = ET.parse(svg_path)
            root = tree.getroot()
            root.set("role", "img")
            root.set("aria-labelledby", "geometry-title geometry-description")
            title = ET.Element("{http://www.w3.org/2000/svg}title", {"id": "geometry-title"})
            title.text = document["title"]
            description = ET.Element("{http://www.w3.org/2000/svg}desc", {"id": "geometry-description"})
            description.text = (f"{axes['x']['label']}; {axes['y']['label']}. Numeric ticks and major gridlines follow "
                                f"{figure_style.STYLE_ID}. "
                                f"{scale_note} {document['description']} Read the adjacent page for exact saved values and evidence limits.")
            root.insert(0, description)
            root.insert(0, title)
            tree.write(svg_path, encoding="utf-8", xml_declaration=True)
        finally:
            plt.close(fig)
    receipt = {"schema": "csl.figure-export/1", "style_id": style["style_id"],
               "quantitative_axis_policy": figure_style.STYLE_ID,
               "style_sha256": hashlib.sha256(style_bytes).hexdigest(),
               "matplotlib": matplotlib.__version__,
               "files": {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                         for name in ("geometry.svg", "geometry.png")}}
    (out / "export.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt

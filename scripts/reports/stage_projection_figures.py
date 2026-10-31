"""Render only validated saved stage-projection geometry to offline figures."""
from __future__ import annotations

import hashlib
from html import escape
import importlib.metadata
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.reports import figure_style
from scripts.reports.stage_projection_data import read_stage_projection_batch


PALETTE = ("#9ccfd8", "#c4a7e7", "#f6c177", "#eb6f92", "#a6da95", "#e0def4")
BACKGROUND = "#16161e"
FOREGROUND = "#e0def4"
MUTED = "#908caa"


def _coordinate(batch: dict, index: int) -> dict:
    return batch["coordinates"][index]


def _value_label(coordinate: dict) -> str:
    unit = coordinate.get("unit")
    return coordinate["name"] + (f" ({unit})" if unit else " (unit unavailable)")


def _record_by_stage(batch: dict, pair_index: int) -> list[dict]:
    return [row for row in batch["records"] if row["pair_index"] == pair_index]


def _trajectory_points(trajectory: dict, first_id: str, second_id: str) -> list[list[float]] | None:
    if trajectory["coordinate_ids"] == [first_id, second_id]:
        return trajectory["points"]
    if trajectory["coordinate_ids"] == [second_id, first_id]:
        return [[point[1], point[0]] for point in trajectory["points"]]
    return None


def _limits(values: list[float]) -> tuple[float, float]:
    if not values:
        return -1.0, 1.0
    low, high = min(values), max(values)
    span = high - low
    margin = max(span * 0.12, max(abs(low), abs(high), 1.0) * 0.06)
    return low - margin, high + margin


def _render_pair(batch: dict, pair_index: int, stage_rows: list[dict], trajectories: list[dict],
                 style: dict, output: Path) -> tuple[Path, Path, str, str]:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch
    from matplotlib.ticker import FuncFormatter

    pair = batch["requested_pairs"][pair_index]
    first, second = (_coordinate(batch, index) for index in pair)
    axis = batch["stage_axis"]
    stage_points = axis["points"]
    cols = min(4, len(stage_rows))
    rows = math.ceil(len(stage_rows) / cols)
    width, height = style["projection_size"]
    fig, axes = plt.subplots(rows, cols, figsize=(width * cols, height * rows), squeeze=False)
    fig.patch.set_facecolor(BACKGROUND)
    title = f"Stage projection · {first['name']} × {second['name']}"
    stage_descriptions = []

    for slot, stage_record in enumerate(stage_rows):
        ax = axes[slot // cols][slot % cols]
        ax.set_facecolor(BACKGROUND)
        ax.tick_params(colors=FOREGROUND, labelsize=style["font_size"] - 2)
        for spine in ax.spines.values():
            spine.set_color(MUTED)
        stage = stage_record["stage"]
        stage_label = f"R{stage}"
        if stage == 0:
            stage_label += " · initial"
        if stage == len(stage_points) - 1:
            stage_label += " · final"
        physical_time = stage_record["physical_time"]
        if physical_time is not None:
            time_unit = axis.get("unit") or "time unit unavailable"
            stage_label += f" · t={physical_time:g} {time_unit}"
        ax.set_title(stage_label, color=FOREGROUND, fontsize=style["font_size"] - 1)
        ax.set_xlabel(_value_label(first), color=FOREGROUND)
        ax.set_ylabel(_value_label(second), color=FOREGROUND)
        figure_style.configure_numeric_axis(ax)
        def tick(value: float, locations: list[float]) -> str:
            if abs(value) >= 1e6:
                return f"{value:.7g}"
            return figure_style.format_tick(value, locations)
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda value, _position, a=ax: tick(value, a.xaxis.get_majorticklocs())))
        ax.yaxis.set_major_formatter(FuncFormatter(
            lambda value, _position, a=ax: tick(value, a.yaxis.get_majorticklocs())))
        ax.xaxis.label.set_color(FOREGROUND)
        ax.yaxis.label.set_color(FOREGROUND)

        outcome = stage_record["outcome"]
        stage_x: list[float] = []
        stage_y: list[float] = []
        outcome_label = outcome.get("kind", outcome.get("relation", "geometry"))
        description_parts = [f"{stage_label}: {outcome['status']} / {outcome_label}"]
        if outcome["status"] == "success":
            evidence_scopes = ", ".join(item["scope"] for item in outcome["evidence"])
            provider = outcome["provider"]
            description_parts.append(
                f"relation {outcome['relation']}; assurance {outcome['assurance']}; "
                f"provider {provider['id']} version {provider['version']}; "
                f"source sets {stage_record['source_set_ids']}; evidence scopes {evidence_scopes}")
            for component_index, component in enumerate(outcome["components"]):
                color = PALETTE[component_index % len(PALETTE)]
                vertices = component.get("vertices", [])
                if component["kind"] == "empty":
                    ax.text(.5, .72, "EMPTY SET", transform=ax.transAxes, ha="center",
                            color=color, fontsize=style["font_size"], weight="bold")
                if vertices:
                    stage_x.extend(float(point[0]) for point in vertices)
                    stage_y.extend(float(point[1]) for point in vertices)
                    role = component.get("role")
                    label_prefix = {"forward": "forward", "backward_winning": "backward-winning",
                                    "intersection": "forward ∩ backward"}.get(role, role)
                    label = f"{label_prefix} · " if label_prefix else ""
                    branch = component.get("branch_id")
                    if branch:
                        label += f"{branch} · "
                    ax.scatter([point[0] for point in vertices], [point[1] for point in vertices],
                               s=style["point_size"] * 1.7, alpha=.9, color=color,
                               edgecolors=BACKGROUND, linewidths=.35,
                               label=f"{label}{component['component_id']} · V generators")
                rays = component.get("rays", [])
                for ray_index, ray in enumerate(rays):
                    if component["kind"] == "empty":
                        description_parts.append(
                            f"empty component retains source ray data {ray}, not drawn as geometry")
                        continue
                    if ray[0] == 0 and ray[1] == 0:
                        continue
                    description_parts.append(f"ray {ray_index + 1} direction {ray}")
                role = component.get("role")
                role_text = f" ({role} overlay)" if role else ""
                branch_text = f", branch {component['branch_id']}" if component.get("branch_id") else ""
                description_parts.append(
                    f"component {component['component_id']}{role_text}{branch_text}: {component['kind']}, "
                    f"{len(vertices)} stored V generators, {len(rays)} rays")
        else:
            explanation = outcome.get("explanation", "No geometric boundary is available.")
            ax.text(.5, .5, f"{outcome['status'].upper()}\n{outcome['kind']}\n{explanation}",
                    transform=ax.transAxes, ha="center", va="center", wrap=True,
                    color=FOREGROUND, fontsize=style["font_size"] - 1)
            description_parts.append(explanation)

        # Trajectories are separate sampled histories, never set boundaries.
        stage_trajectory_values: list[list[float]] = []
        for trajectory_index, trajectory in enumerate(trajectories):
            points = _trajectory_points(trajectory, first["id"], second["id"])
            if points is None:
                continue
            color = PALETTE[(trajectory_index + len(PALETTE) // 2) % len(PALETTE)]
            if stage < len(points):
                point = points[stage]
                stage_trajectory_values.append(point)
                ax.scatter([point[0]], [point[1]], marker="x", s=style["target_size"] / 3,
                           color=color, zorder=5,
                           label=f"selected trajectory {trajectory_index + 1} · R{stage}")
            if stage + 1 < len(points):
                start, end = points[stage], points[stage + 1]
                stage_trajectory_values.append(end)
                ax.annotate("", xy=end, xytext=start,
                            arrowprops={"arrowstyle": "->", "color": color,
                                        "linestyle": "--", "linewidth": 1.8})
            description_parts.append(
                f"selected trajectory {trajectory_index + 1} at {stage_label}; "
                f"evidence: {trajectory['evidence']}; separate from set geometry")
        for point in stage_trajectory_values:
            stage_x.append(float(point[0])); stage_y.append(float(point[1]))
        x_limits, y_limits = _limits(stage_x), _limits(stage_y)
        ax.set_xlim(x_limits); ax.set_ylim(y_limits)
        if x_limits[0] <= 0 <= x_limits[1]:
            ax.axvline(0, color=MUTED, linewidth=.65, alpha=.65)
        if y_limits[0] <= 0 <= y_limits[1]:
            ax.axhline(0, color=MUTED, linewidth=.65, alpha=.65)
        if outcome["status"] == "success":
            for component_index, component in enumerate(outcome["components"]):
                if component["kind"] == "empty":
                    continue
                color = PALETTE[component_index % len(PALETTE)]
                vertices = component.get("vertices", [])
                bases = vertices or [[0.0, 0.0]]
                x_span = x_limits[1] - x_limits[0]
                y_span = y_limits[1] - y_limits[0]
                for ray in component.get("rays", []):
                    if ray[0] == 0 and ray[1] == 0:
                        continue
                    scale_candidates = []
                    if ray[0] != 0:
                        scale_candidates.append(x_span / abs(ray[0]))
                    if ray[1] != 0:
                        scale_candidates.append(y_span / abs(ray[1]))
                    ray_scale = .12 * min(scale_candidates)
                    for base in bases:
                        ax.add_patch(FancyArrowPatch(
                            posA=(base[0], base[1]),
                            posB=(base[0] + ray_scale * ray[0], base[1] + ray_scale * ray[1]),
                            arrowstyle="-|>", mutation_scale=9, color=color, linewidth=1.0,
                            alpha=.7, shrinkA=1, shrinkB=1))
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, fontsize=6, facecolor=BACKGROUND,
                      edgecolor=MUTED, labelcolor=FOREGROUND, loc="best")
        stage_descriptions.append(". ".join(description_parts))

    for slot in range(len(stage_rows), rows * cols):
        axes[slot // cols][slot % cols].set_visible(False)
    fig.suptitle(title, color=FOREGROUND, fontsize=style["font_size"] + 1, y=.99)
    fig.text(.5, .925, "Independent stage scales · stored V generators and ray directions · no set boundary reconstructed",
             ha="center", color=FOREGROUND, fontsize=style["font_size"] - 1)
    fig.tight_layout(rect=(0, 0, 1, .88))
    base = output / f"projection-{pair_index + 1:02d}-{first['id']}-{second['id']}"
    svg, png = base.with_suffix(".svg"), base.with_suffix(".png")
    fig.savefig(svg, metadata={"Date": None, "Creator": figure_style.STYLE_ID})
    fig.savefig(png, dpi=style["png_dpi"], metadata={"Software": figure_style.STYLE_ID})
    plt.close(fig)

    tree = ET.parse(svg)
    root = tree.getroot()
    root.set("role", "img")
    root.set("aria-labelledby", "figure-title figure-description")
    title_element = ET.Element("{http://www.w3.org/2000/svg}title", {"id": "figure-title"})
    title_element.text = title
    description = ET.Element("{http://www.w3.org/2000/svg}desc", {"id": "figure-description"})
    description.text = ("Independent scales are used for each stage. " + "; ".join(stage_descriptions) +
                        ". The figure plots saved V generators and ray directions. It does not reconstruct "
                        "set boundaries or perform geometry conversion.")
    root.insert(0, description); root.insert(0, title_element)
    tree.write(svg, encoding="utf-8", xml_declaration=True)
    return svg, png, title, description.text


def render_batch(input_path: Path, output_directory: Path, *, expected_identity: dict[str, str],
                 style_path: Path) -> list[dict]:
    """Validate a saved batch, then write figures and an offline responsive index."""
    import os

    os.environ.setdefault("MPLCONFIGDIR", str(output_directory.parent / "mpl-config"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    batch = read_stage_projection_batch(input_path, **expected_identity)
    style = json.loads(style_path.read_text(encoding="utf-8"))
    if style.get("schema") != "csl.figure-style/1" or \
            style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("style must declare csl-report-quantitative-v1")
    if importlib.metadata.version("matplotlib") != style.get("matplotlib_version"):
        raise ValueError(f"Matplotlib {style.get('matplotlib_version')} required by the selected figure style")
    output_directory.mkdir(parents=True)
    output = output_directory.resolve(strict=True)
    outputs = []
    trajectories = batch["trajectory_series"]
    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    with matplotlib.rc_context(rc):
        for pair_index in range(len(batch["requested_pairs"])):
            svg, png, title, description = _render_pair(
                batch, pair_index, _record_by_stage(batch, pair_index), trajectories, style, output)
            outputs.append({"title": title, "description": description,
                            "svg": svg.name, "png": png.name})

    cards = "\n".join(
        f'<section><h2>{escape(item["title"])}</h2>'
        f'<p>{escape(item["description"])}</p>'
        f'<figure><a href="{escape(item["svg"])}"><img src="{escape(item["png"])}" '
        f'alt="{escape(item["description"])}"></a>'
        f'<figcaption><a href="{escape(item["svg"])}">Open standalone SVG</a> · '
        f'<a href="{escape(item["png"])}">Open PNG</a></figcaption></figure></section>'
        for item in outputs)
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Saved stage projections</title>
<style>
:root{{color-scheme:dark}}body{{max-width:1200px;margin:auto;padding:1.5rem;background:{BACKGROUND};color:{FOREGROUND};font:16px/1.5 system-ui,sans-serif}}
a{{color:#9ccfd8}}h1,h2{{color:#c4a7e7}}figure{{margin:1rem 0}}img{{display:block;width:100%;height:auto}}
section{{border-top:1px solid {MUTED};padding:1rem 0;break-inside:avoid}}.path{{overflow-wrap:anywhere;font-family:monospace}}
@media(max-width:640px){{body{{padding:.75rem}}h1{{font-size:1.4rem}}}}
@media print{{:root{{color-scheme:light}}body{{background:white;color:black;max-width:none}}a{{color:black}}h1,h2{{color:black}}section{{break-inside:avoid}}figure{{margin:.3rem 0}}}}
</style></head><body><header><p>Controlled Systems Lab · Offline renderer</p>
<h1>Saved stage projections</h1><p>Validated batch <code>{escape(batch['schema'])}</code>;
route <code>{escape(batch['route_id'])}</code>; problem <code>{escape(batch['problem_id'])}</code>.</p>
<p>Output directory: <code class="path">{escape(str(output))}</code></p>
<p>Each panel is a saved stage outcome using independent scales. Stored V generators are shown as markers; no boundary is reconstructed.
Trajectory overlays are selected histories, separate from reachable-set geometry and evidence.</p></header>
<main>{cards}</main></body></html>'''
    (output / "index.html").write_text(html + "\n", encoding="utf-8")
    generated = sorted(path for path in output.iterdir() if path.is_file())
    receipt = {
        "schema": "csl.stage-projection-figure-export/1",
        "input_content_sha256": batch["content_sha256"],
        "style_id": style["style_id"],
        "quantitative_axis_policy": figure_style.STYLE_ID,
        "output_directory": str(output),
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in generated},
    }
    (output / "render-manifest.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return outputs

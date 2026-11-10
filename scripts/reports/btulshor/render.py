#!/usr/bin/env python3
"""Render saved BTULSHOR comparison records and a quantitative 2D projection."""
from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS = next((candidate for candidate in (SCRIPT_DIR, SCRIPT_DIR.parent, ROOT / "scripts/reports")
                if (candidate / "figure_style.py").is_file()), None)
if REPORTS is None:
    raise RuntimeError("the shared figure_style.py snapshot is unavailable")
if str(REPORTS) not in sys.path:
    sys.path.insert(0, str(REPORTS))
import figure_style  # noqa: E402

def make_projection(document: dict) -> tuple[bytes, dict]:
    """Render one numeric 2D point projection with the shared figure policy."""
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "csl-btulshor-mplconfig"))
    import matplotlib

    if matplotlib.__version__ != "3.11.2":
        raise RuntimeError("Matplotlib 3.11.2 is required; use the pinned report venv")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if document.get("dimension") != 2:
        raise ValueError("point projection is defined only for 2D inputs")
    points = document.get("input_points", [])
    if not points:
        raise ValueError("cannot plot an empty point cloud")
    if any(len(point) != 2 or not all(math.isfinite(float(v)) for v in point) for point in points):
        raise ValueError("2D input points must be finite coordinate pairs")
    raw = next((provider for provider in document.get("providers", [])
                if provider.get("method_id") == "csl.legacy.btulshor.kpabep.source-v1"), None)
    classes = document.get("point_classes")
    valid_classes = (isinstance(classes, list) and len(classes) == len(points) and
                     all(value in {"vertex", "interior", "edge", "duplicate"} for value in classes))
    if not valid_classes:
        classes = ["unclassified"] * len(points)
    retained_ids = raw.get("retained_indices", []) if raw else []
    selected = [index for index in retained_ids
                if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(points)]
    boundary_ids = raw.get("display_boundary_indices", []) if raw else []
    boundary_ids_valid = (isinstance(boundary_ids, list) and len(boundary_ids) >= 2 and
                          all(isinstance(index, int) and not isinstance(index, bool) and
                              0 <= index < len(points) for index in boundary_ids))
    settings = {"font.family": "DejaVu Sans", "font.size": 10,
                "axes.titlesize": 12, "axes.labelsize": 10,
                "figure.facecolor": "white", "axes.facecolor": "white",
                "svg.fonttype": "none", "svg.hashsalt": "csl-btulshor-report-v1"}
    with matplotlib.rc_context(settings):
        figure, axis = plt.subplots(figsize=(7.4, 6.2), layout="constrained")
        try:
            all_x = [float(point[0]) for point in points]
            all_y = [float(point[1]) for point in points]
            styles = {
                "vertex": ("o", "#3274a1", "Extreme vertex"),
                "interior": ("s", "#2d9c66", "Interior point"),
                "edge": ("^", "#d47720", "Edge point"),
                "duplicate": ("D", "#c53535", "Duplicate point"),
                "unclassified": ("o", "#3274a1", "Input point"),
            }
            axis.scatter(all_x, all_y, s=18, color="#6b7280", alpha=.45, zorder=2)
            for point_class in dict.fromkeys(classes):
                indices = [index for index, value in enumerate(classes) if value == point_class]
                marker, color, _label = styles[point_class]
                axis.scatter([all_x[index] for index in indices],
                             [all_y[index] for index in indices],
                             s=64 if point_class != "duplicate" else 90,
                             marker=marker,
                             facecolors="none" if point_class == "duplicate" else color,
                             edgecolors=color, zorder=3 + (point_class == "duplicate"))
            grouped = {}
            for index, point in enumerate(points):
                grouped.setdefault((float(point[0]), float(point[1])), []).append(index)
            for index, point in enumerate(points):
                group = grouped[(float(point[0]), float(point[1]))]
                occurrence = group.index(index)
                label_offset = (5 + (occurrence % 2) * 12, 4 + (occurrence // 2) * 11)
                axis.annotate(str(index), (float(point[0]), float(point[1])),
                              xytext=label_offset, textcoords="offset points", fontsize=8,
                              color="#17212b", zorder=5)
            if selected:
                axis.scatter([float(points[index][0]) for index in selected],
                             [float(points[index][1]) for index in selected],
                             s=88, facecolors="none", edgecolors="#c53535",
                             linewidths=1.5, zorder=4)
            if boundary_ids_valid:
                boundary = [points[index] for index in boundary_ids]
                if len(boundary) >= 3:
                    boundary = boundary + [boundary[0]]
                axis.plot([float(point[0]) for point in boundary],
                          [float(point[1]) for point in boundary],
                          color="#c53535", linewidth=1.2, linestyle="--", zorder=2)
            axis.set(title=f"{document.get('fixture_id', 'Input cloud')}: 2D point projection",
                     xlabel="Coordinate 1", ylabel="Coordinate 2")
            axis.set_aspect("equal", adjustable="datalim")
            figure_style.configure_numeric_axis(axis, "both", bins=6)
            axis.margins(x=.16, y=.16)
            legend = [Line2D([], [], marker="o", linestyle="none", color="#6b7280",
                             label="Input points; labels are original IDs")]
            legend.extend(Line2D([], [], marker=styles[point_class][0], linestyle="none",
                markerfacecolor="none" if point_class == "duplicate" else styles[point_class][1],
                markeredgecolor=styles[point_class][1], label=styles[point_class][2])
                for point_class in dict.fromkeys(classes))
            legend.extend([
                Line2D([], [], marker="o", linestyle="none", markerfacecolor="none",
                       markeredgecolor="#c53535", color="#c53535",
                       label="BTULSHOR retained source IDs"),
            ])
            if boundary_ids_valid:
                legend.append(Line2D([], [], color="#c53535", linestyle="--",
                    label="Saved display-only boundary; not source execution order"))
            axis.legend(handles=legend, loc="best", frameon=True, fontsize=8)
            figure.suptitle("Raw method result with an independent display boundary")
            from io import StringIO
            output = StringIO()
            figure.savefig(output, format="svg", metadata={"Date": None, "Format": None,
                "Type": None, "Creator": None})
            svg_text = output.getvalue()
            svg = svg_text[svg_text.index("<svg"):].encode("utf-8")
        finally:
            plt.close(figure)
    return svg, {"matplotlib": matplotlib.__version__,
                 "quantitative_axis_policy": figure_style.STYLE_ID,
                 "aspect": "equal",
                 "point_classes_used": valid_classes,
                 "point_classes": classes,
                 "coincident_input_ids": [indices for indices in grouped.values() if len(indices) > 1],
                 "retained_ids_drawn": retained_ids,
                 "display_boundary_ids": boundary_ids if boundary_ids_valid else None,
                 "boundary_semantics": "saved display-only boundary IDs; not source order"
                    if boundary_ids_valid else "no saved display boundary; only raw points are drawn"}


def _timing(provider: dict) -> str:
    samples = provider.get("elapsed_ns_samples")
    if isinstance(samples, list) and samples:
        values = [value for value in samples if isinstance(value, int) and
                  not isinstance(value, bool) and value >= 0]
        if len(values) != len(samples):
            return "invalid timing record"
        ordered = sorted(values)
        middle = len(ordered) // 2
        median = (ordered[middle] if len(ordered) % 2 else
                  (ordered[middle - 1] + ordered[middle]) / 2)
        shown = f"{median:g} ns median (n={len(values)}, range {min(values)}–{max(values)} ns)"
        return shown
    value = provider.get("elapsed_ns")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return f"single call: {value} ns"
    if provider.get("status") == "unsupported_dimension":
        return "not applicable (unsupported dimension)"
    return "pending / unavailable"


def _exact_check(document: dict, provider: dict) -> dict:
    saved = provider.get("exact_check")
    if not isinstance(saved, dict):
        return {"status": "pending", "reason": "independent check not yet recorded"}
    return saved


def _provider_row(document: dict, provider: dict) -> str:
    exact = _exact_check(document, provider)
    retained_ids = provider.get("retained_indices", [])
    counts = f"{provider.get('input_count', document.get('input_count', len(document.get('input_points', []))))} / {provider.get('retained_count', len(retained_ids) if isinstance(retained_ids, list) else '—')}"
    counters = {key: provider[key] for key in (
        "pivot_count", "modif_calls", "kpabep_calls", "lp_calls", "attempt_count", "a43_metrics")
        if key in provider}
    exact_summary = {"status": exact.get("status"), "hull_equal": exact.get("hull_equal"),
                     "irredundancy": exact.get("irredundancy"), "reason": exact.get("reason"),
                     "extra_indices": exact.get("extra_indices", [])}
    elapsed = _timing(provider)
    interval = provider.get("interval")
    if interval:
        elapsed += "; scope: " + str(interval)
    cells = [provider.get("method_id", "unknown"), provider.get("status", "missing"), counts,
             json.dumps(retained_ids, ensure_ascii=False), json.dumps(counters, ensure_ascii=False),
             elapsed, json.dumps(exact_summary, ensure_ascii=False)]
    return "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in cells) + "</tr>"


def _provider_table(document: dict) -> str:
    rows = "".join(_provider_row(document, provider)
                   for provider in document.get("providers", []))
    return ("<table><thead><tr><th>Method ID</th><th>Raw status</th><th>Input / retained count</th>"
            "<th>Original retained IDs</th><th>Work counters</th><th>Elapsed interval</th>"
            "<th>Independent exact hull check</th></tr></thead><tbody>" + rows + "</tbody></table>")


def _raw_link(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parsed = urlsplit(value)
    path = Path(value)
    if parsed.scheme or parsed.netloc or path.is_absolute() or ".." in path.parts:
        return ""
    escaped = html.escape(value, quote=True)
    return f' · <a href="{escaped}">Raw JSON: {escaped}</a>'


def _zip_link(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.name != value or path.suffix.lower() != ".zip" or value in {".", ".."}:
        raise ValueError("offline_zip_name must be a ZIP filename without a path")
    escaped = html.escape(value, quote=True)
    return f'<p><a href="{escaped}" download>Download offline report bundle ({html.escape(value)})</a></p>'


def _additional_section(document: dict, index: int, primary_fixture: str) -> str:
    fixture = html.escape(str(document.get("fixture_id", f"additional-{index}")))
    dimension = html.escape(str(document.get("dimension", "unknown")))
    input_count = document.get("input_count", len(document.get("input_points", [])))
    provenance = document.get("provenance", {})
    source = " · ".join(f"{html.escape(key.replace('_', ' '))}: {html.escape(str(provenance[key]))}"
                        for key in ("source_commit", "compiler_id", "compiler_version", "build_config")
                        if key in provenance)
    source_markup = f"<p><small>{source}</small></p>" if source else ""
    return (f'<section><h2>Fixture: {fixture}</h2>'
            f'<p><strong>Dimension:</strong> {dimension} · <strong>Input points:</strong> {html.escape(str(input_count))}'
            f'{_raw_link(document.get("raw_file"))}</p>{source_markup}'
            f'<p>Provider results are shown without a second figure; the primary visual projection is for '
            f'{html.escape(primary_fixture)}.</p>{_provider_table(document)}</section>')


def render(document: dict, output_dir: Path | None = None,
           additional_comparisons: list[dict] | None = None,
           offline_zip_name: str | None = None) -> str:
    """Render HTML; when output_dir is given, also save the 2D SVG asset."""
    providers = document.get("providers", [])
    table = _provider_table(document)
    dimension = document.get("dimension")
    primary_fixture = str(document.get("fixture_id", "unnamed"))
    figure_html = ""
    figure_manifest = {"status": "not_applicable", "reason": "2D projection is unavailable outside dimension 2"}
    if dimension == 2 and document.get("input_points"):
        figure_manifest = {"status": "pending", "reason": "figure generation deferred"}
        source_provider = next((provider for provider in providers if provider.get("method_id") ==
                                "csl.legacy.btulshor.kpabep.source-v1"), {})
        boundary_ids = source_provider.get("display_boundary_indices")
        has_boundary = (isinstance(boundary_ids, list) and len(boundary_ids) >= 2 and
                        all(isinstance(index, int) and not isinstance(index, bool) and
                            0 <= index < len(document.get("input_points", []))
                            for index in boundary_ids))
        alt_text = "2D input points labelled by original ID with raw BTULSHOR retained IDs"
        caption = ("The dashed boundary follows separately saved display-only IDs; it does not represent "
                   "BTULSHOR execution order. Raw retained IDs remain unchanged." if has_boundary else
                   "No boundary is drawn because saved display-boundary IDs are unavailable.")
        caption = f"Primary figure for {primary_fixture}. " + caption
        figure_html = ('<figure><img src="point-projections.svg" alt="{}"><figcaption>{}</figcaption></figure>'
                       .format(html.escape(alt_text), html.escape(caption)))
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            svg, figure_manifest = make_projection(document)
            (output_dir / "point-projections.svg").write_bytes(svg)

    provenance = document.get("provenance", {})
    provenance_rows = []
    for key in ("source_commit", "compiler_id", "compiler_version", "build_config", "driver_id"):
        if key in provenance:
            provenance_rows.append("<dt>{}</dt><dd><code>{}</code></dd>".format(
                html.escape(key.replace("_", " ")), html.escape(str(provenance[key]))))
    extra = {key: value for key, value in provenance.items()
             if key not in {"source_commit", "compiler_id", "compiler_version", "build_config", "driver_id"}}
    if extra:
        provenance_rows.append("<dt>Additional capture metadata</dt><dd><pre>{}</pre></dd>".format(
            html.escape(json.dumps(extra, indent=2, ensure_ascii=False, sort_keys=True))))
    capture_metadata = document.get("capture_metadata")
    capture_markup = ("<h2>Capture protocol and environment</h2><p><a href=\"raw/summary.json\">Complete capture summary and process memory readings</a></p><pre>" +
                      html.escape(json.dumps(capture_metadata, indent=2, ensure_ascii=False, sort_keys=True)) + "</pre>") if capture_metadata else ""
    figure_note = (f"Matplotlib {figure_manifest['matplotlib']} · {figure_manifest['quantitative_axis_policy']}"
                   if "matplotlib" in figure_manifest else
                   "Static 2D asset is generated when rendered to a report directory."
                   if dimension == 2 else "No 2D plot is generated for this input dimension.")
    additional_markup = "".join(_additional_section(item, index, primary_fixture)
                                for index, item in enumerate(additional_comparisons or [], start=2))
    zip_markup = _zip_link(offline_zip_name)
    template = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BTULSHOR source comparison</title>
<style>:root{color-scheme:dark}body{font:16px/1.5 system-ui,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1rem;color:#ebdbb2;background:#1d2021}h1{line-height:1.2;color:#fabd2f}h2{color:#fe8019;margin-top:2rem}table{display:block;max-width:100%;overflow-x:auto;border-collapse:collapse;width:100%;margin:1rem 0;background:#282828}th,td{min-width:8rem;border:1px solid #504945;padding:.55rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}th:first-child,td:first-child{min-width:17rem}th:last-child,td:last-child{min-width:16rem}th{background:#3c3836;color:#fe8019}figure{margin:1rem 0}figure img{display:block;width:min(100%,800px);height:auto;background:#fff;border:1px solid #504945}figcaption,small{font-size:.9rem;color:#a89984}pre{padding:1rem;background:#282828;overflow:auto;border:1px solid #504945}dl{display:grid;grid-template-columns:minmax(9rem,auto) 1fr;gap:.25rem .8rem}dt{color:#a89984}dd{margin:0;min-width:0}code{overflow-wrap:anywhere}</style></head><body>
<main><h1>BTULSHOR source comparison</h1><p>This report preserves raw outcomes from the source-faithful A06 BTULSHOR port, generic LP hull reduction, geometric QuickHull 2D, and separately identified ITIS17 paper adaptations. Their guarantees and work differ; elapsed intervals are reported per method and are not used to rank methods. The independent exact checker runs after each method and does not alter its raw result.</p>
<p><strong>Primary input:</strong> %%FIXTURE%% · dimension %%DIMENSION%% · %%INPUTCOUNT%% points. <strong>Figure policy:</strong> %%FIGURENOTE%%</p>%%FIGURE%%
<h2>Fixture: %%FIXTURE%%</h2><p>Primary comparison records.%%RAWLINK%%</p>%%TABLE%%
%%ADDITIONAL%%
%%CAPTURE%%<h2>Provenance</h2><dl>%%PROVENANCE%%</dl><p>Exact-check irredundancy is shown separately from hull equality. An inconclusive result does not establish equality or failure. The display-only boundary is not a repair of source output.</p>%%ZIPLINK%%</main></body></html>"""
    replacements = {
        "%%FIXTURE%%": html.escape(str(document.get("fixture_id", "unnamed"))),
        "%%DIMENSION%%": html.escape(str(dimension if dimension is not None else "unknown")),
        "%%INPUTCOUNT%%": str(document.get("input_count", len(document.get("input_points", [])))),
        "%%FIGURENOTE%%": html.escape(figure_note), "%%FIGURE%%": figure_html,
        "%%RAWLINK%%": _raw_link(document.get("raw_file")), "%%TABLE%%": table,
        "%%ADDITIONAL%%": additional_markup, "%%ZIPLINK%%": zip_markup,
        "%%CAPTURE%%": capture_markup,
        "%%PROVENANCE%%": "".join(provenance_rows) or "<dt>Status</dt><dd>pending</dd>",
    }
    page = template
    for marker, value in replacements.items():
        page = page.replace(marker, value)
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="HTML output path")
    parser.add_argument("--additional", action="append", type=Path, default=[],
                        help="additional saved comparison JSON; may be repeated")
    parser.add_argument("--offline-zip-name", help="optional colocated offline ZIP filename")
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    additional = [json.loads(path.read_text(encoding="utf-8")) for path in args.additional]
    output_dir = args.output.parent
    page = render(document, output_dir, additional, args.offline_zip_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()

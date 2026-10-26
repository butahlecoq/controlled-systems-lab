"""Render readable companions from saved geometry/optimization report records."""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import statistics
import tempfile
import xml.etree.ElementTree as ET

import figure_style
import geometry_figures


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "reports/algorithm-results"
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
POLICY = figure_style.STYLE_ID
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

TIMING_REPORTS = (
    ("geo02", "geo02-20261013T061151Z-338ff7d1d63c", "GEO-02 affine-sum adapter",
     "Median total time by saved analytic fixture; the report's phase table retains setup, operation, oracle and total values."),
    ("geo03", "geo03-20261012-3c12ca125831", "GEO-03 H/V conversion",
     "Median total time by saved fixture and conversion direction; only four bounded 2D fixtures are represented."),
    ("geo04", "geo04-20261012T224946Z-c37852bcc80d", "GEO-04 intersection and reduction",
     "Median saved phase durations by fixture. Zero-duration phases are inactive in the saved record and are listed as not plotted."),
    ("geo05", "geo05-7fddaba0c7698f72", "GEO-05 numerical fixtures",
     "Median saved end-to-end durations by fixture; the page and raw record retain failed, missing and warmup attempts."),
    ("geo07", "geo07-9ef0d347291774da", "GEO-07 generator geometry",
     "Seven saved measured batch durations per fixture, shown as median and observed minimum-to-maximum range."),
    ("geo07-dependent", "geo07-dependent-4dcc5a8fe36f17ed", "GEO-07 dependent geometry",
     "Seven saved measured batch durations per fixture, shown as median and observed minimum-to-maximum range."),
    ("geo07-port", "geo07-port-4dee19cde3d50259", "GEO-07 faithful port",
     "Seven saved measured batch durations per fixture, shown as median and observed minimum-to-maximum range."),
    ("opt04", "opt04-20261013T172839Z-6451c4b89d3b", "OPT-04 phase-I simplex",
     "Saved public-run and end-to-end timing medians by fixture and implementation side. No speedup is inferred."),
    ("opt12", "opt12-7b732a53716c", "OPT-12 warm-start adapter",
     "Median saved wall time by fixture and cold/warm mode. The original report retains native work, attempts and solver evidence."),
)

GEOMETRY_REPORTS = (
    ("geo08", "geo08-lazy-6dbdd6b2f9235837", "GEO-08 lazy geometry",
     "A planar source square, its affine image, their independent Minkowski sum, and the saved support maximizer. This is an illustration of the saved fixture, not an execution trace."),
    ("opt10", "opt10-smooth-188130d94d7bf2de", "OPT-10 smooth convex fixture",
     "The saved feasible box, start point, and analytic minimizer. The dashed segment is an illustration, not a solver iteration path."),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _phase_row(label: str, series: str, values: dict) -> dict:
    median, low, high = (values.get(key) for key in ("median", "min", "max"))
    if any(type(value) not in (int, float) for value in (median, low, high)):
        raise ValueError("timing row needs finite median/min/max values")
    if not low <= median <= high or low < 0:
        raise ValueError("timing row has inconsistent bounds")
    return {"label": label, "series": series, "median": median, "min": low, "max": high}


def timing_rows(slug: str, record: dict) -> list[dict]:
    if slug == "geo02":
        return [_phase_row(name, "total trial", group["phases"]["total_ns"])
                for name, group in record["summary"].items()]
    if slug == "geo03":
        payload = record["payload"]
        return [_phase_row(f"{row['fixture']} / {row['direction']}", "total conversion", row["total_ns"])
                for row in payload["summary"]]
    if slug == "geo04":
        rows = []
        for scenario, summary in record["summary"].items():
            for phase, values in summary["phases"].items():
                rows.append(_phase_row(f"{scenario} / {phase.removesuffix('_ns')}",
                                       phase.removesuffix("_ns"), values))
        return rows
    if slug == "geo05":
        scenarios = record["catalog"]["scenarios"]
        names = [item["id"] for item in scenarios] if scenarios and isinstance(scenarios[0], dict) else scenarios
        rows = []
        for name in names:
            values = [trial["durations_ns"]["end_to_end_ns"] for trial in record["trials"]
                      if trial["scenario"] == name and trial["status"] == "passed"
                      and trial["durations_ns"].get("end_to_end_ns") is not None]
            if not values:
                continue
            rows.append(_phase_row(name, "end-to-end", {
                "median": statistics.median(values), "min": min(values), "max": max(values)}))
        return rows
    if slug in {"geo07", "geo07-dependent", "geo07-port"}:
        return [_phase_row(name, "measured batch", {
                    "median": row["median_batch_ns"], "min": row["min_batch_ns"],
                    "max": row["max_batch_ns"]})
                for name, row in record["summary"].items()]
    if slug == "opt04":
        if record["summary"].get("valid") is not True:
            raise ValueError("OPT-04 saved timing aggregates are ineligible")
        return [_phase_row(f"{row['fixture']} / {row['side']} / {row['phase']}",
                           f"{row['side']} / {row['phase']}", {
                               "median": row["median_ns"], "min": row["min_ns"], "max": row["max_ns"]})
                for row in record["summary"]["rows"]
                if row["phase"] in {"public_run", "end_to_end"}]
    if slug == "opt12":
        groups = {}
        for trial in record["trials"]:
            if trial.get("status") != "verified":
                continue
            groups.setdefault((trial["scenario"], trial["mode"]), []).append(trial["wall_ns"])
        return [_phase_row(f"{scenario} / {mode}", mode, {
                    "median": statistics.median(values), "min": min(values), "max": max(values)})
                for (scenario, mode), values in sorted(groups.items())]
    raise ValueError("unknown timing report: " + slug)


def _svg_with_accessibility(svg: bytes, title: str, description: str) -> bytes:
    root = ET.fromstring(svg)
    root.set("role", "img")
    root.set("aria-labelledby", "figure-title figure-description")
    title_node = ET.Element(f"{{{SVG_NS}}}title", {"id": "figure-title"})
    title_node.text = title
    description_node = ET.Element(f"{{{SVG_NS}}}desc", {"id": "figure-description"})
    description_node.text = description
    root.insert(0, description_node)
    root.insert(0, title_node)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_timing(rows: list[dict], title: str, description: str, out: Path) -> dict:
    if not rows:
        raise ValueError("timing companion needs at least one saved row")
    style_bytes = STYLE.read_bytes()
    style = json.loads(style_bytes)
    if style.get("quantitative_axis_policy") != POLICY:
        raise ValueError("report plot style is not the shared quantitative policy")
    os.environ.setdefault("MPLCONFIGDIR", str(out.parent / "mpl-config"))
    import matplotlib
    if matplotlib.__version__ != style.get("matplotlib_version"):
        raise ValueError("Matplotlib version differs from the pinned figure style")
    matplotlib.use("Agg")
    from matplotlib.ticker import FuncFormatter, LogLocator
    import matplotlib.pyplot as plt

    plotted = [row for row in rows if row["median"] > 0]
    omitted = [row for row in rows if row["median"] == 0]
    if not plotted:
        raise ValueError("timing companion has no positive durations to plot")
    labels = [row["label"] for row in plotted]
    if len(set(labels)) != len(labels):
        raise ValueError("timing category labels must be unique")
    colors = {name: f"C{index % 10}" for index, name in enumerate(sorted({row["series"] for row in plotted}))}
    height = max(3.6, 0.38 * len(plotted) + 1.6)
    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    out.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context(rc):
        fig, axis = plt.subplots(figsize=(11, height))
        try:
            for index, row in enumerate(plotted):
                axis.errorbar(row["median"], index,
                              xerr=[[row["median"] - row["min"]], [row["max"] - row["median"]]],
                              fmt="D", markersize=4.5, capsize=2.5, linewidth=1.2,
                              color=colors[row["series"]], label=row["series"] if row["series"] not in
                              {item["series"] for item in plotted[:index]} else None)
            axis.set_yticks(range(len(plotted)), labels)
            axis.invert_yaxis()
            axis.set_xscale("log")
            axis.set_xlabel("Inclusive duration (ns), logarithmic scale")
            axis.set_title(title, loc="left", fontsize=11, pad=14)
            axis.set_axisbelow(True)
            axis.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0,)))
            axis.xaxis.set_minor_locator(LogLocator(base=10, subs=(2.0, 5.0)))
            axis.xaxis.set_major_formatter(FuncFormatter(
                lambda value, _position, a=axis: figure_style.format_tick(value, a.xaxis.get_majorticklocs())))
            axis.grid(True, which="major", axis="x", color="#8290a3", alpha=.28, linewidth=.65)
            axis.grid(True, which="minor", axis="x", color="#8290a3", alpha=.10, linewidth=.4)
            axis.set_xlim(min(row["min"] for row in plotted) * .65,
                          max(row["max"] for row in plotted) * 1.7)
            fig.subplots_adjust(left=.48, right=.97, top=.91, bottom=.16)
            svg_buffer = __import__("io").BytesIO()
            png_buffer = __import__("io").BytesIO()
            fig.savefig(svg_buffer, format="svg", metadata={"Date": None, "Creator": "CSL saved timing companion"})
            fig.savefig(png_buffer, format="png", dpi=style["png_dpi"],
                        metadata={"Software": POLICY})
        finally:
            plt.close(fig)
    description += " Numeric ticks and major gridlines follow " + POLICY + ". "
    description += "The x axis uses logarithmic scaling; each marker is a saved median and each whisker is its saved min-to-max range."
    if omitted:
        description += " Zero-valued phases are inactive and omitted from logarithmic axes: " + ", ".join(row["label"] for row in omitted) + "."
    svg = _svg_with_accessibility(svg_buffer.getvalue(), title, description)
    (out / "figure.svg").write_bytes(svg)
    (out / "figure.png").write_bytes(png_buffer.getvalue())
    return {"schema": "csl.figure-export/1", "style_id": style["style_id"],
            "quantitative_axis_policy": POLICY, "matplotlib": matplotlib.__version__,
            "scale": "logarithmic x; equal categorical spacing", "title": title,
            "description": description, "rows": rows,
            "omitted_zero_rows": [row["label"] for row in omitted],
            "style_sha256": sha(style_bytes),
            "files": {name: sha((out / name).read_bytes()) for name in ("figure.svg", "figure.png")}}


def geometry_document(slug: str, record: dict) -> dict:
    if slug == "geo08":
        return {
            "schema": "csl.saved-geometric-plot/1",
            "title": "GEO-08 planar square, affine image, and independent sum",
            "description": ("Illustrative plot of the saved GEO-08 fixture. The source is [0,1]², its affine image is "
                            "[1,3] × [-1,0], and their independent Minkowski sum is [1,4] × [-1,1]. "
                            "The marked point (4,1) is the saved support maximizer for direction (1,1). "
                            "This shows mathematical shapes, not execution steps or a certified enclosure."),
            "axes": {"x": {"label": "x (unitless fixture coordinate)"},
                     "y": {"label": "y (unitless fixture coordinate)"}},
            "aspect": "equal",
            "series": [
                {"kind": "polygon", "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                 "label": "Source square [0,1]²", "color": "#168aad"},
                {"kind": "polygon", "points": [[1, -1], [3, -1], [3, 0], [1, 0]],
                 "label": "Affine image [1,3] × [-1,0]", "color": "#e07a21"},
                {"kind": "polygon", "points": [[1, -1], [4, -1], [4, 1], [1, 1]],
                 "label": "Independent sum [1,4] × [-1,1]", "color": "#4f772d"},
                {"kind": "points", "points": [record["fixture"]["expected_maximizer"]],
                 "label": "Support maximizer (4,1), value 5", "color": "#c1121f", "size": 48, "alpha": 1.0},
            ],
        }
    if slug == "opt10":
        problem, analytic = record["problem"], record["analytic"]
        bounds = problem["variables"]
        return {
            "schema": "csl.saved-geometric-plot/1",
            "title": "OPT-10 feasible box and analytic minimizer",
            "description": ("Illustration of the saved two-dimensional box, supplied start, and analytic minimizer. "
                            "The dashed segment indicates feasible points and is not an optimizer iteration trace. "
                            "The minimizer and objective are the values saved in the record."),
            "axes": {"x": {"label": "x (unitless)"},
                     "y": {"label": "y (unitless)"}},
            "aspect": "equal",
            "tick_bins": 3,
            "series": [
                {"kind": "polygon", "points": [[bounds[0][0], bounds[1][0]],
                                                     [bounds[0][1], bounds[1][0]],
                                                     [bounds[0][1], bounds[1][1]],
                                                     [bounds[0][0], bounds[1][1]]],
                 "label": "Feasible box", "color": "#168aad", "fill": True, "alpha": .10},
                {"kind": "path", "points": [problem["start"], analytic["point"]],
                 "label": "Illustrative feasible segment", "color": "#e07a21", "linestyle": "--"},
                {"kind": "points", "points": [problem["start"]], "label": "Supplied start (0,0)",
                 "color": "#e07a21", "size": 38, "alpha": 1.0},
                {"kind": "points", "points": [analytic["point"]],
                 "label": f"Analytic minimizer {tuple(analytic['point'])}; f={analytic['objective']}",
                 "color": "#c1121f", "size": 48, "alpha": 1.0},
            ],
        }
    raise ValueError("unknown geometry report: " + slug)


def _median_range(row: dict, median_key: str, low_key: str, high_key: str) -> dict:
    return {"median": row[median_key], "min": row[low_key], "max": row[high_key]}


def _load_report(report_id: str) -> tuple[dict, bytes]:
    path = RESULTS / report_id / "records.json"
    raw = path.read_bytes()
    return json.loads(raw), raw


def _timing_page_section(slug: str, title: str, description: str, report_id: str,
                         rows: list[dict], raw: bytes, output: Path) -> dict:
    image_dir = output / "geometry-opt"
    image_dir.mkdir(parents=True, exist_ok=True)
    plot_dir = image_dir / slug
    metadata = render_timing(rows, title, description + " Source report " + report_id + ".", plot_dir)
    svg_name, png_name = f"geometry-opt/{slug}/figure.svg", f"geometry-opt/{slug}/figure.png"
    export_name = f"geometry-opt/{slug}/export.json"
    raw_name = f"geometry-opt/data/{report_id}.json"
    data_path = output / raw_name
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(raw)
    timing_rows_html = "".join(
        "<tr><th scope=\"row\">" + html.escape(row["label"]) + "</th><td>" + html.escape(row["series"]) +
        "</td><td>" + html.escape(f"{row['median']:g}") + "</td><td>" +
        html.escape(f"{row['min']:g}–{row['max']:g}") + "</td></tr>" for row in rows)
    zero_note = (" Zero-valued phases remain available in the raw report record and are omitted from the logarithmic plot."
                 if metadata["omitted_zero_rows"] else "")
    section = (f'<section id="{slug}"><h2>{html.escape(title)}</h2><p>{html.escape(description)}'
               f' Report identity <code>{html.escape(report_id)}</code>. This companion reads saved records only; '
               f'it does not invoke a solver, geometry operation, or benchmark.</p>'
               f'<figure><a href="{html.escape(png_name, quote=True)}"><img src="{html.escape(svg_name, quote=True)}" '
               f'alt="{html.escape(description, quote=True)}"></a><figcaption>Median with observed min-to-max whisker. '
               f'Logarithmic x scale; exact values remain in the table and raw JSON.{html.escape(zero_note)}</figcaption></figure>'
               f'<p><a href="{html.escape(png_name, quote=True)}">PNG</a> · '
               f'<a href="{html.escape(svg_name, quote=True)}">SVG</a> · '
               f'<a href="{html.escape(export_name, quote=True)}">export metadata</a> · '
               f'<a href="{html.escape(raw_name, quote=True)}">raw saved record</a></p>'
               f'<div class="scroll" role="region" tabindex="0" aria-label="Timing values for {html.escape(title, quote=True)}">'
               '<table><thead><tr><th>Fixture / phase</th><th>Series</th><th>Median (ns)</th>'
               f'<th>Min–max (ns)</th></tr></thead><tbody>{timing_rows_html}</tbody></table></div></section>')
    (output / export_name).write_text(json.dumps({**metadata, "report_id": report_id,
        "raw_record_sha256": sha((RESULTS / report_id / "records.json").read_bytes())}, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    return {"section": section, "figure": svg_name, "page": "geometry-optimization-v1.html#" + slug,
            "records": raw_name, "export": export_name, "png": png_name}


def build(output: Path) -> tuple[list[str], list[dict], list[str]]:
    """Render the 11 saved-data companions under a separate gallery route."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "geometry-opt/data").mkdir(parents=True, exist_ok=True)
    sections, inventory, assets = [], [], []
    for slug, report_id, title, description in TIMING_REPORTS:
        record, raw = _load_report(report_id)
        rows = timing_rows(slug, record)
        rendered = _timing_page_section(slug, title, description, report_id, rows, raw, output)
        sections.append(rendered["section"])
        assets.extend((rendered["figure"], rendered["png"], rendered["export"], rendered["records"]))
        inventory.append({"family": "Geometry and optimization", "title": title,
                          "report_id": report_id, "figure": rendered["figure"],
                          "page": rendered["page"], "records": rendered["records"]})
    for slug, report_id, title, description in GEOMETRY_REPORTS:
        record, raw = _load_report(report_id)
        render_dir = output / "geometry-opt" / slug
        with tempfile.TemporaryDirectory(prefix="geometry-opt-") as temporary:
            geometry_figures.render(geometry_document(slug, record), STYLE, Path(temporary))
            render_dir.mkdir(parents=True, exist_ok=True)
            for name in ("geometry.svg", "geometry.png", "export.json"):
                shutil.copyfile(Path(temporary) / name, render_dir / name)
        raw_name = f"geometry-opt/data/{report_id}.json"
        (output / raw_name).write_bytes(raw)
        svg_name, png_name = f"geometry-opt/{slug}/geometry.svg", f"geometry-opt/{slug}/geometry.png"
        export_name = f"geometry-opt/{slug}/export.json"
        export = json.loads((render_dir / "export.json").read_text(encoding="utf-8"))
        export.update({"report_id": report_id, "raw_record_sha256": sha(raw),
                       "description": description, "no_solver_or_geometry_query": True})
        (render_dir / "export.json").write_text(json.dumps(export, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        figure = (f'<section id="{slug}"><h2>{html.escape(title)}</h2><p>{html.escape(description)} '
                  f'Report identity <code>{html.escape(report_id)}</code>. This companion uses only saved inputs and '
                  'answers and performs no solver or geometry query.</p>'
                  f'<figure><a href="{html.escape(png_name, quote=True)}"><img src="{html.escape(svg_name, quote=True)}" '
                  f'alt="{html.escape(description, quote=True)}"></a><figcaption>Numeric ticks and major grids follow '
                  f'{POLICY}. Equal scale on x and y; coordinate units are stated on each axis.</figcaption></figure>'
                  f'<p><a href="{html.escape(png_name, quote=True)}">PNG</a> · '
                  f'<a href="{html.escape(svg_name, quote=True)}">SVG</a> · '
                  f'<a href="geometry-opt/{slug}/export.json">export metadata</a> · '
                  f'<a href="{html.escape(raw_name, quote=True)}">raw saved record</a></p></section>')
        sections.append(figure)
        assets.extend((svg_name, png_name, f"geometry-opt/{slug}/export.json", raw_name))
        inventory.append({"family": "Geometry and optimization", "title": title,
                          "report_id": report_id, "figure": svg_name,
                          "page": "geometry-optimization-v1.html#" + slug, "records": raw_name})
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Geometry and optimization report plots</title><link rel="stylesheet" href="examples.css">'
            '<style>body{max-width:1150px;margin:2rem auto;padding:0 1rem;font:16px/1.55 system-ui,sans-serif;color:#182532}'
            'section{border-top:1px solid #cbd5de;padding:1.4rem 0}figure{margin:1rem 0}figure img{display:block;width:100%;height:auto}'
            '.scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}'
            'th,td{border:1px solid #cbd5de;padding:.45rem;text-align:left}code{overflow-wrap:anywhere}'
            '@media print{body{max-width:none;margin:0;padding:0}section{break-inside:avoid}figure img{max-height:8in;object-fit:contain}}</style>'
            '</head><body><main><p><a href="index.html#saved-report-figures">← Saved report figures</a></p>'
            '<h1>Geometry and optimization report plots</h1><p>Presentation companions rendered from immutable saved report records. '
            'Original report bundles, manifests, checksums and versioned URLs remain unchanged. Timing values use a logarithmic axis; '
            'exact values and their evidence limits remain in each table and raw record. Geometry illustrations state their aspect and units.</p>'
            + "".join(sections) + '</main></body></html>')
    (output / "geometry-optimization-v1.html").write_text(page, encoding="utf-8")
    assets.extend(["geometry-optimization-v1.html"])
    return sections, inventory, sorted(assets)

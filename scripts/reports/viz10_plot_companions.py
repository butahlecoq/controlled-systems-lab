"""Render quantitative companions from immutable historical report records.

This module only reads saved records and draws their existing coordinates. It
does not invoke solvers, hull algorithms, numerical experiments, or benchmarks.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import figure_style

ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
REPORTS = ROOT / "reports/algorithm-results"
FUEL_PAIRS = ((0, 2, "Oxidizer flow x₁ (kg/s)", "Fuel flow x₃ (kg/s)"),
              (1, 3, "Oxidizer stock balance x₂ (kg)", "Fuel stock balance x₄ (kg)"))
B07_PAIRS = ((0, 1, FUEL_PAIRS[0][2], FUEL_PAIRS[0][3]),
             (2, 3, FUEL_PAIRS[1][2], FUEL_PAIRS[1][3]))
COLORS = {"stored": "#2367a8", "target": "#b23b33", "open": "#d97706", "closed": "#257a5a"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def project_coordinates(vertices: list[list[float]], first: int, second: int) -> list[tuple[float, float]]:
    return [(vertex[first], vertex[second]) for vertex in vertices]


def add_svg_description(path: Path, title: str, description: str) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    root.set("role", "img")
    root.set("aria-labelledby", "viz10-title viz10-description")
    ns = "{http://www.w3.org/2000/svg}"
    title_node = ET.Element(ns + "title", {"id": "viz10-title"})
    title_node.text = title
    desc_node = ET.Element(ns + "desc", {"id": "viz10-description"})
    desc_node.text = description
    root.insert(0, desc_node)
    root.insert(0, title_node)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def save(fig, name: str, title: str, description: str, sources: dict[str, str], out: Path, style: dict):
    svg_path, png_path = out / f"{name}.svg", out / f"{name}.png"
    fig.savefig(svg_path, metadata={"Date": None, "Creator": "CSL VIZ-10 saved-record companion"})
    fig.savefig(png_path, dpi=style["png_dpi"], metadata={"Software": style["style_id"]})
    add_svg_description(svg_path, title, description + " Numeric ticks and major gridlines follow " + figure_style.STYLE_ID + ".")
    receipt = {"schema": "csl.viz10-figure-export/1", "title": title,
               "description": description, "quantitative_axis_policy": figure_style.STYLE_ID,
               "style_sha256": sha(STYLE.read_bytes()), "matplotlib": __import__("matplotlib").__version__,
               "sources": sources,
               "files": {svg_path.name: sha(svg_path.read_bytes()), png_path.name: sha(png_path.read_bytes())}}
    (out / f"{name}-export.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def style_axis(axis, xlabel: str, ylabel: str, title: str, equal: bool = False,
               direction: str = "both", bins: int = 6):
    axis.set(xlabel=xlabel, ylabel=ylabel, title=title)
    if equal:
        axis.set_aspect("equal", adjustable="box")
    figure_style.configure_numeric_axis(axis, direction=direction, bins=bins)


def render_b07(out: Path, style: dict, receipts: list[dict]) -> list[tuple[str, str, str]]:
    path = REPORTS / "b07-owner-approved-eight-case-v1/results.jsonl"
    readme = path.parent / "README.md"
    source_hashes = {str(path.relative_to(ROOT)): sha(path.read_bytes()),
                     str(readme.relative_to(ROOT)): sha(readme.read_bytes())}
    figures = []
    for row in load_jsonl(path):
        vertices = row["winner_terminal_vertices_x1_x3_x2_x4"]
        case = row["case_id"]
        slug = "b07-" + case.lower().replace("_", "-")
        fig, axes = __import__("matplotlib.pyplot", fromlist=["subplots"]).subplots(1, 2, figsize=(11, 5.4))
        try:
            for axis, (first, second, xlabel, ylabel), title in zip(axes, B07_PAIRS, ("Flow projection", "Stock projection")):
                projected = project_coordinates(vertices, first, second)
                axis.scatter([point[0] for point in projected], [point[1] for point in projected],
                             s=style["point_size"], alpha=style["point_alpha"], color=COLORS["stored"],
                             label=f"Stored terminal V rows ({len(vertices)})")
                target = (30.0, 20.0) if first == 0 else (0.0, 0.0)
                axis.scatter([target[0]], [target[1]], marker="*", s=style["target_size"],
                             color=COLORS["target"], label="Authored target")
                style_axis(axis, xlabel, ylabel, title, equal=True, bins=4)
            fig.suptitle(f"B07 fuel case · {case} · λ={row['terminal_lambda']} · J={row['value_norm']:.6g}", fontsize=11)
            handles, labels = axes[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", ncol=2, fontsize="small")
            fig.tight_layout(rect=(0, .1, 1, .92))
            desc = ("Two coordinate projections from the recorded four-state terminal rows: x1/x3 flow and x2/x4 stock. "
                    "Markers are the saved terminal V rows, not a filled enclosure or nonlinear replay. Equal data scaling is used within each same-unit pair.")
            receipt = save(fig, slug, f"B07 four-state fuel projections: {case}", desc,
                           source_hashes, out, style)
            receipts.append(receipt)
            figures.append((slug, f"B07 · {case}", desc))
        finally:
            __import__("matplotlib.pyplot", fromlist=["close"]).close(fig)
    return figures


def render_b09(out: Path, style: dict, receipts: list[dict]) -> list[tuple[str, str, str]]:
    path = REPORTS / "b09-a08-source-reference-4818ddde/results.jsonl"
    scenario_path = path.parent / "scenario.json"
    source_hashes = {str(path.relative_to(ROOT)): sha(path.read_bytes()),
                     str(scenario_path.relative_to(ROOT)): sha(scenario_path.read_bytes())}
    figures = []
    for row in load_jsonl(path):
        vertices = row["winner_terminal_vertices_x1_x2_x3_x4"]
        slug = f"b09-lambda-{int(row['lambda'])}"
        fig, axes = __import__("matplotlib.pyplot", fromlist=["subplots"]).subplots(1, 2, figsize=(11, 5.4))
        for axis, (first, second, xlabel, ylabel), title in zip(axes, FUEL_PAIRS, ("Flow projection", "Stock projection")):
            projected = project_coordinates(vertices, first, second)
            axis.scatter([point[0] for point in projected], [point[1] for point in projected],
                         s=style["point_size"], alpha=style["point_alpha"], color=COLORS["stored"],
                         label=f"Stored terminal V rows ({len(vertices)})")
            for state, label, key in ((row["open_loop_replay_terminal_state"], "Open-loop replay terminal state", "open"),
                                      (row["closed_loop_replay_terminal_state"], "Receding-horizon replay terminal state", "closed")):
                axis.scatter([state[first]], [state[second]], marker="X", s=style["target_size"],
                             color=COLORS[key], label=label)
            style_axis(axis, xlabel, ylabel, title, equal=True, bins=4)
        fig.suptitle(f"B09 A08 source-reference projections · λ={row['lambda']} · robust J={row['objective_norm']:.6g}", fontsize=11)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3, fontsize="small")
        fig.tight_layout(rect=(0, .12, 1, .92))
        desc = ("Coordinate projections of the saved four-state terminal V rows, with open-loop and receding-horizon nonlinear replay endpoints marked separately. "
                "The V rows are plotted as points; no projected hull is recomputed. Equal data scaling is used within each same-unit coordinate pair.")
        receipt = save(fig, slug, f"B09 four-state fuel projections at lambda {row['lambda']}", desc,
                       source_hashes, out, style)
        receipts.append(receipt)
        figures.append((slug, f"B09 · λ={row['lambda']}", desc))
        __import__("matplotlib.pyplot", fromlist=["close"]).close(fig)
    return figures


def render_timing(path: Path, name: str, title: str, rows: list[tuple[str, list[int], int]], out: Path, style: dict, receipts: list[dict]):
    plt = __import__("matplotlib.pyplot", fromlist=["subplots"])
    fig, axis = plt.subplots(figsize=tuple(style["timing_size"]))
    labels = []
    for index, (label, values, median) in enumerate(rows):
        labels.append(label)
        offsets = [(i - (len(values)-1)/2) * .12 for i in range(len(values))]
        axis.scatter(values, [index + d for d in offsets], s=style["point_size"] * 3,
                     alpha=.75, label="saved attempts" if index == 0 else None)
        if median is not None:
            axis.scatter([median], [index], marker="D", s=style["target_size"] * .4,
                         color=COLORS["target"], label="saved median" if index == 0 else None, zorder=3)
    axis.set_yticks(range(len(labels)), labels)
    axis.invert_yaxis()
    style_axis(axis, "Duration (ns)", "Saved case", title, direction="x")
    axis.legend(fontsize="small")
    fig.tight_layout()
    source_hash = sha(path.read_bytes())
    desc = "Every plotted point and median is read from the immutable saved report record; no timing run is performed."
    receipt = save(fig, name, title, desc, {str(path.relative_to(ROOT)): source_hash}, out, style)
    receipts.append(receipt)
    plt.close(fig)
    return (name, title, desc)


def render_exp04(out: Path, style: dict, receipts: list[dict]):
    path = REPORTS / "exp04-replay-93fe3b87795e1d3a/records.json"
    record = load_json(path)
    cases = [record["fixtures"][key] for key in ("plane-forward", "plane-reverse")]
    fig, axis = __import__("matplotlib.pyplot", fromlist=["subplots"]).subplots(figsize=tuple(style["projection_size"]))
    for case, label, color in zip(cases, ("Forward replay", "Reverse replay"), (COLORS["stored"], COLORS["open"])):
        states = case["expected_states"]
        axis.plot([state[0] for state in states], [state[1] for state in states], marker="o", color=color,
                  label=f"{label}; controls={case['controls']}; J={case['expected_objective']}")
    style_axis(axis, "Position x (length)", "Action state y (action)", "EXP-04 saved two-state replay paths")
    axis.legend(fontsize="small")
    fig.tight_layout()
    desc = "The paths are the two literal saved replay fixtures in physical state coordinates; x and y have different units, so axis scaling is independent."
    receipt = save(fig, "exp04-two-state-paths", "EXP-04 two-state replay paths", desc,
                   {str(path.relative_to(ROOT)): sha(path.read_bytes())}, out, style)
    receipts.append(receipt)
    __import__("matplotlib.pyplot", fromlist=["close"]).close(fig)
    return ("exp04-two-state-paths", "EXP-04 · saved replay paths", desc)


def render_analytic_fixture(out: Path, style: dict, receipts: list[dict]):
    path = REPORTS / "issue3-validated-minimax-20261023-r1/records.json"
    record = load_json(path)
    # The immutable source record's analytic_2d input is x0=(0,0), A=B=I,
    # E=I, w=(0,0), and controls (0,0)/(1,0); its checked target is (1,0).
    rows = [row for row in record["rows"] if row["fixture"] == "analytic_2d"]
    if not rows:
        raise ValueError("saved validated report has no analytic_2d fixture")
    source_hash = sha(path.read_bytes())
    fig, axis = __import__("matplotlib.pyplot", fromlist=["subplots"]).subplots(figsize=tuple(style["projection_size"]))
    axis.scatter([0, 1], [0, 0], color=COLORS["stored"], label="Saved plan terminal states")
    axis.scatter([1], [0], marker="*", s=style["target_size"], color=COLORS["target"], label="Saved objective target")
    style_axis(axis, "Terminal state x₁", "Terminal state x₂", "Issue #3 analytic two-dimensional fixture")
    axis.legend(fontsize="small")
    fig.tight_layout()
    desc = "Two authored plans reach the displayed terminal states; the target and exact zero residual are recorded in the validated report. This is a fixture diagram, not a solver trace."
    receipt = save(fig, "issue3-analytic-fixture", "Issue #3 analytic two-dimensional fixture", desc,
                   {str(path.relative_to(ROOT)): source_hash}, out, style)
    receipts.append(receipt)
    __import__("matplotlib.pyplot", fromlist=["close"]).close(fig)
    return ("issue3-analytic-fixture", "Issue #3 · analytic fixture", desc)


def render_volterra(out: Path, style: dict, receipts: list[dict]):
    path = REPORTS / "issue4-volterra-7dce05b47c50c27a/records.json"
    record = load_json(path)
    fig, axis = __import__("matplotlib.pyplot", fromlist=["subplots"]).subplots(figsize=tuple(style["projection_size"]))
    colors = {1: "#7651a8", 20: "#2878a5", 40: "#d08a18", 60: "#b23b33"}
    from matplotlib.patches import Rectangle
    for stage in (1, 20, 40, 60):
        bounds = record["rows"][stage-1]["same_control_error"]
        lower, upper = bounds
        axis.add_patch(Rectangle((float(lower[0]), float(lower[1])),
                                 float(upper[0])-float(lower[0]), float(upper[1])-float(lower[1]),
                                 fill=False, edgecolor=colors[stage], linewidth=2,
                                 label=f"Saved same-control error interval · stage {stage}"))
    style_axis(axis, "Error in state x₁", "Error in state x₂", "Issue #4 saved Volterra error boxes")
    axis.legend(fontsize="small")
    fig.tight_layout()
    desc = "Axis-aligned boxes use the saved interval endpoints at stages 1, 20, 40 and 60. The plotted rectangles are illustrative binary64 coordinates; decimal endpoints remain in the immutable record and CSV."
    receipt = save(fig, "issue4-volterra-error-boxes", "Issue #4 saved Volterra error boxes", desc,
                   {str(path.relative_to(ROOT)): sha(path.read_bytes())}, out, style)
    receipts.append(receipt)
    __import__("matplotlib.pyplot", fromlist=["close"]).close(fig)
    return ("issue4-volterra-error-boxes", "Issue #4 · saved error boxes", desc)


def build(out: Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    style_bytes = STYLE.read_bytes()
    style = json.loads(style_bytes)
    if style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("wrong quantitative-axis style")
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "csl-viz10-mpl-config"))
    import matplotlib
    if matplotlib.__version__ != style["matplotlib_version"]:
        raise ValueError(f"Matplotlib {style['matplotlib_version']} required")
    matplotlib.use("Agg")
    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    receipts: list[dict] = []
    figures: list[tuple[str, str, str]] = []
    with matplotlib.rc_context(rc):
        figures.extend(render_b07(out, style, receipts))
        figures.extend(render_b09(out, style, receipts))

        b08_path = REPORTS / "b08-exact-b0d0e85d4d338f56/records.json"
        b08 = load_json(b08_path)
        b08_rows = [("Excluded warmup", [r["duration_ns"] for r in b08["rows"] if r["warmup"]], None),
                    ("Measured child processes", [r["duration_ns"] for r in b08["rows"] if not r["warmup"]], b08["summary"]["median_ns"])]
        figures.append(render_timing(b08_path, "b08-exact-timings", "B08 saved fresh-process timings", b08_rows, out, style, receipts))

        issue3_path = REPORTS / "issue3-finite-catalogue-b4632ce76510aa4f/records.json"
        issue3 = load_json(issue3_path)
        timing_rows = [(r["fixture"], [r["min_batch_ns"], r["median_batch_ns"], r["max_batch_ns"]], r["median_batch_ns"]) for r in issue3["summary"] if r["status"] == "numerical_optimal"]
        figures.append(render_timing(issue3_path, "issue3-finite-catalogue-timings", "Issue #3 saved finite-catalogue batch timings", timing_rows, out, style, receipts))
        figures.append(render_exp04(out, style, receipts))
        figures.append(render_analytic_fixture(out, style, receipts))
        figures.append(render_volterra(out, style, receipts))
    catalog = load_json(REPORTS / "catalog.json")
    report_routes = {report["source_report_id"]: report["report_id"]
                     for report in catalog["reports"] if report.get("source_report_id")}
    report_prefixes = {
        "b07-": "b07-owner-approved-eight-case-v1",
        "b09-": "b09-a08-source-reference-4818ddde",
        "b08-": "b08-exact-b0d0e85d4d338f56",
        "exp04-": "exp04-replay-93fe3b87795e1d3a",
        "issue3-finite-": "issue3-finite-catalogue-b4632ce76510aa4f",
        "issue3-analytic-": "issue3-validated-minimax-20261023-r1",
        "issue4-": "issue4-volterra-7dce05b47c50c27a",
    }
    cards = []
    for name, title, desc in figures:
        source_id = next((source_id for prefix, source_id in report_prefixes.items()
                          if name.startswith(prefix)), None)
        report_route = report_routes.get(source_id) if source_id else None
        report_link = (f'<a href="../../{report_route}/index.html">Open immutable source report</a> · '
                       if report_route else "")
        cards.append(f'<section><h2>{html.escape(title)}</h2><p>{html.escape(desc)}</p>'
                     f'<figure><a href="{name}.svg"><img src="{name}.png" alt="{html.escape(title)}; {html.escape(desc)}"></a>'
                     f'<figcaption>{report_link}<a href="{name}.svg">SVG</a> · <a href="{name}.png" download>PNG</a> · '
                     f'<a href="{name}-export.json">source and export hashes</a></figcaption></figure></section>')
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>VIZ-10 saved-data plot companions</title><style>body{font:16px/1.55 system-ui,sans-serif;max-width:1120px;margin:auto;padding:1rem;color:#17212b}'
            'img{display:block;width:100%;height:auto}figure{margin:1rem 0}section{border-bottom:1px solid #ccd4de;padding:1rem 0}'
            '.limit{background:#f3f5f7;padding:1rem}@media(max-width:40rem){body{padding:.75rem}h1{font-size:1.6rem}figcaption{overflow-wrap:anywhere}}'
            '@media print{body{max-width:none;margin:0;padding:0;color:#000;font-size:11pt}.limit{background:#fff;border:1px solid #777}section{break-inside:avoid;padding:.35rem 0}figure{margin:.35rem 0}a{color:#000;text-decoration:none}img{max-height:8.5in;object-fit:contain}h1,h2{break-after:avoid}}</style></head><body><main>'
            '<h1>VIZ-10: saved-data plot companions</h1>'
            '<p>Every chart below is rendered from the versioned records named in its export receipt. Existing report bundles, manifests, checksums and URLs remain unchanged.</p>'
            '<p class="limit">Fuel charts show 2D coordinate projections of recorded four-state terminal rows. They preserve the selected state coordinates and units. A point cloud does not assert a filled reachable-set enclosure, and the B09 replay endpoints remain distinct from its robust terminal rows. No solver, hull query, numerical experiment or benchmark ran during rendering.</p>'
            + ''.join(cards) + '<p><a href="../fuel-b06-viz06.html">B06 saved-data companion, including x₁/x₃ flow and x₂/x₄ stock projections</a></p>'
            '</main></body></html>')
    (out / "index.html").write_text(page, encoding="utf-8")
    manifest = {"schema": "csl.viz10-gallery/1", "style_sha256": sha(style_bytes),
                "quantitative_axis_policy": figure_style.STYLE_ID,
                "inputs": {k: v for receipt in receipts for k, v in receipt["sources"].items()},
                "figures": {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir()) if path.is_file() and path.suffix in {".svg", ".png", ".json"}},
                "index_sha256": sha((out / "index.html").read_bytes())}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/examples/viz10")
    args = parser.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render the immutable #944 Strategy A choice-pipeline result bundle."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "issue944-strategy-a-each-choice-v1"
SOURCE_COMMIT = "5a4730c517a875400ec7b69e4c8e2c265e49016c"
RUNNER_SHA256 = "34cdaa1a6d85902b5188797e11a31b976ebb87ce8327a6bea012aef80ae23c8a"
CHECKER_SHA256 = "30b2ae4c28bac51c914526fa59373da3ed350176489a95dfe76b38d20fe7a6d3"
BINARY_SHA256 = "1c52ab404b11398b0d7ae45aaae1934047dac9a1af77840f06d56307438ee032"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def theme_tokens():
    css = (ROOT / "docs/examples/examples.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{([^}]+)\}", css)
    print_root = re.search(r"@media\s+print\s*\{\s*:root\s*\{([^}]+)\}", css)
    if root is None or print_root is None:
        raise ValueError("shared examples screen/print themes are required")
    parse = lambda block: dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+)\s*;", block))
    screen, printed = parse(root.group(1)), parse(print_root.group(1))
    required = {"--page", "--surface", "--text", "--text-muted", "--accent", "--warm", "--line"}
    if not required <= screen.keys() or not required <= printed.keys():
        raise ValueError("shared examples screen/print tokens are incomplete")
    return screen, printed


def regression_svg(record: dict, print_mode: bool = False, mobile_mode: bool = False) -> str:
    task, row = record["task"], record["attempt"]
    history = row["selected_history"]
    assert row["independent_check"]["selected_history_in_returned_family"]
    assert row["independent_check"]["selected_history_in_terminal_family"]
    assert not row["independent_check"]["selected_control_in_terminal_family"]
    x0, x1, u = history[:2], history[2:4], history[4:6]

    def panel(x, title, bounds, point, label, shift, top=95):
        left, width, height = shift, 330, 250
        xlo, xhi = bounds[0]
        ylo, yhi = bounds[1]
        pad_x, pad_y = 36, 22
        sx = lambda value: left + pad_x + (value - xlo) / (xhi - xlo) * (width - 2 * pad_x)
        sy = lambda value: top + height - pad_y - (value - ylo) / (yhi - ylo) * (height - 2 * pad_y)
        corners = [(xlo,ylo),(xhi,ylo),(xhi,yhi),(xlo,yhi)]
        poly = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a,b in corners)
        return (f'<text x="{left}" y="{top-27}" class="panel">{html.escape(title)}</text>'
                f'<rect x="{left+pad_x}" y="{top+pad_y}" width="{width-2*pad_x}" height="{height-2*pad_y}" class="frame"/>'
                f'<polygon points="{poly}" class="domain"/>'
                f'<circle cx="{sx(point[0]):.1f}" cy="{sy(point[1]):.1f}" r="7" class="point"/>'
                f'<text x="{sx(point[0])+9:.1f}" y="{sy(point[1])-8:.1f}" class="label">{html.escape(label)}</text>'
                f'<text x="{left+width/2}" y="{top+height+22}" class="axis" text-anchor="middle">coordinate 1</text>'
                f'<text x="{left+pad_x}" y="{top+height-2}" class="tick">{xlo:g}</text>'
                f'<text x="{left+width-pad_x-12}" y="{top+height-2}" class="tick">{xhi:g}</text>'
                f'<text x="{left+3}" y="{top+height-pad_y+4}" class="tick">{ylo:g}</text>'
                f'<text x="{left+3}" y="{top+pad_y+4}" class="tick">{yhi:g}</text>')

    initial_bounds = [axis for axis in task["initial_state_box"]]
    terminal_bounds = [axis for axis in task["next_state_box"]]
    control_bounds = task["control_box"]
    # Separate state and input coordinate spaces so the terminal test cannot use u0 by mistake.
    if mobile_mode:
        content = panel("", "Initial state x₀", initial_bounds, x0, "x₀=(2,3)", 42, 112)
        content += panel("", "Terminal state x₁", terminal_bounds, x1, "x₁=(3,4)", 42, 422)
        content += panel("", "Control u₀", control_bounds, u, "u₀=(1,1)", 42, 732)
        view_box, figure_height, footer_y = "0 0 420 1080", 1080, 1040
        title = "Recovered witness"
    else:
        content = panel("", "Initial state x₀", initial_bounds, x0, "x₀=(2,3)", 42)
        content += panel("", "Terminal state x₁", terminal_bounds, x1, "x₁=(3,4)", 430)
        content += panel("", "Control u₀", control_bounds, u, "u₀=(1,1)", 818)
        view_box, figure_height, footer_y = "0 0 1200 440", 440, 420
        title = "A recovered witness distinguishes terminal state from control"
    screen, printed = theme_tokens()
    theme = printed if print_mode else screen
    screen_css = ("text{font-family:Inter,system-ui,sans-serif;fill:" + theme["--text"] + "}" +
        ".title{font-size:22px;font-weight:650}.panel{font-size:18px;font-weight:600}" +
        ".frame{fill:" + theme["--surface"] + ";stroke:" + theme["--line"] + "}" +
        ".domain{fill:" + theme["--accent"] + ";fill-opacity:.2;stroke:" + theme["--accent"] + ";stroke-width:2}" +
        ".point{fill:" + theme["--warm"] + ";stroke:" + theme["--page"] + ";stroke-width:2}" +
        ".label{font-size:14px}.axis,.tick{fill:" + theme["--text-muted"] + ";font-size:12px}")
    footer = ("<text x=\"42\" y=\"1040\" class=\"axis\">x₁=x₀+u₀ · all points satisfy their domains.</text>"
              "<text x=\"42\" y=\"1060\" class=\"axis\">Endpoint belongs to the returned terminal family.</text>"
              if mobile_mode else "x₁=x₀+u₀ · points lie in their domains · endpoint belongs to the returned terminal family.")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" role="img" aria-labelledby="title desc">
<title id="title">Nonzero-origin terminal membership regression</title><desc id="desc">Separate initial state, terminal state, and control domains. The recovered history is x0=(2,3), x1=(3,4), u0=(1,1), so terminal state coordinates differ from control coordinates.</desc>
<style>{screen_css}</style>
<rect width="{view_box.split()[2]}" height="{figure_height}" fill="{theme["--page"]}"/><text x="42" y="42" class="title">{title}</text>
{content}{footer if mobile_mode else f'<text x="42" y="{footer_y}" class="axis">{footer}</text>'}
</svg>'''


def mobile_pipeline_svg(record: dict) -> str:
    rows = [next(row for row in record["attempts"] if row["task"] == task and
        row["vertex_reducer"] == "csl.hull.lp-membership" and
        row["vertex_lp_provider"] == "csl.lp.highs" and row["status"] == "completed")
        for task in ("linear", "quadratic")]
    theme, printed = theme_tokens()
    left, top, size = 55, 120, 370
    xy = lambda point: (left + point[0] * size, top + (1 - point[1]) * size)
    vertices = rows[0]["forward_vertices"]
    center = (sum(point[0] for point in vertices) / len(vertices),
              sum(point[1] for point in vertices) / len(vertices))
    vertices.sort(key=lambda point: math.atan2(point[1] - center[1], point[0] - center[0]))
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x,y in map(xy, vertices))
    trajectories = []
    marks = []
    for index, row in enumerate(rows):
        history = row["selected_history"]
        x0, x1, control = history[:2], history[2:4], history[4:6]
        sx0, sy0 = xy(x0)
        sx1, sy1 = xy(x1)
        color = theme["--link"] if index == 0 else theme["--warm"]
        trajectories.append(f'<line x1="{sx0}" y1="{sy0}" x2="{sx1}" y2="{sy1}" stroke="{color}" stroke-width="5" opacity=".9"/>')
        marks.append(f'<circle cx="{sx1}" cy="{sy1}" r="9" fill="{color}" stroke="{theme["--page"]}" stroke-width="2"/>')
        name = "LP" if index == 0 else "QP"
        trajectories.append(f'<text x="55" y="{555+index*36}" class="legend" fill="{color}">{name}: x₀=(0,0), x₁=({x1[0]:g},{x1[1]:g}), u₀=({control[0]:g},{control[1]:g})</text>')
    screen_css = ("text{font-family:Inter,system-ui,sans-serif;fill:" + theme["--text"] + "}" +
        ".title{font-size:24px;font-weight:650}.axis,.tick{font-size:16px;fill:" + theme["--text-muted"] + "}" +
        ".legend{font-size:16px;font-weight:600}")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 700" role="img" aria-labelledby="title desc">
<title id="title">Returned unit-square terminal family and recovered histories</title><desc id="desc">A square terminal family with the recovered linear history from zero to (1,0) under control (1,0), and quadratic history at zero under control (0,0).</desc>
<style>{screen_css}</style>
<rect width="480" height="700" fill="{theme["--page"]}"/><text x="28" y="46" class="title">Returned terminal family</text><text x="28" y="76" class="axis">x₁=x₀+u₀, x₀=(0,0), u₀∈[0,1]²</text>
<rect x="{left}" y="{top}" width="{size}" height="{size}" fill="{theme["--surface"]}" stroke="{theme["--line"]}" stroke-width="2"/><line x1="{left}" y1="{top+size/2}" x2="{left+size}" y2="{top+size/2}" stroke="{theme["--line"]}"/><line x1="{left+size/2}" y1="{top}" x2="{left+size/2}" y2="{top+size}" stroke="{theme["--line"]}"/>
<polygon points="{polygon}" fill="{theme["--accent"]}" fill-opacity=".18" stroke="{theme["--accent"]}" stroke-width="3"/>{''.join(trajectories)}{''.join(marks)}
<text x="{left}" y="{top+size+25}" class="tick">0</text><text x="{left+size-8}" y="{top+size+25}" class="tick">1</text><text x="{left-25}" y="{top+size}" class="tick">0</text><text x="{left-25}" y="{top+12}" class="tick">1</text>
<text x="55" y="652" class="axis">Both histories were recovered from the returned family.</text>
</svg>'''


def csv_rows(record: dict):
    fields = ["task", "controller", "representation", "vertex_reducer", "vertex_lp_provider",
              "converter", "converter_lp_provider", "terminal_lp_provider",
              "terminal_optimizer_choice", "terminal_optimizer_actual", "history_recovery_api",
              "history_recovery_status", "history_selection_provider", "status", "outcome_class", "first_unmet"]
    for row in record["attempts"]:
        yield {key: (outcome_class(row) if key == "outcome_class" else row.get(key, "")) for key in fields}


def outcome_class(row: dict) -> str:
    first_unmet = row.get("first_unmet", "")
    if first_unmet.startswith("phase_one.objective:"):
        return "structural-contract-exclusion"
    if first_unmet.startswith(("highs.matrix:", "highs.convex.matrix:")):
        return "numeric-refusal"
    return "completed" if row["status"] == "completed" else "other-refusal"


def page(record: dict, regression: dict, file_hashes: dict) -> str:
    counts = {}
    for row in record["attempts"]:
        category = outcome_class(row)
        counts[category] = counts.get(category, 0) + 1
    completed = counts.get("completed", 0)
    refused = counts.get("numeric-refusal", 0)
    structural = counts.get("structural-contract-exclusion", 0)
    groups = {}
    for row in record["attempts"]:
        key = (row["vertex_reducer"], row["vertex_lp_provider"], row["terminal_optimizer_choice"])
        category = outcome_class(row)
        slot = groups.setdefault(key, {"attempts": 0, "completed": 0, "numeric-refusal": 0})
        slot["attempts"] += 1
        slot[category] = slot.get(category, 0) + 1
    group_rows = "".join(f"<tr><td>{html.escape(r)}</td><td>{html.escape(lp)}</td><td>{html.escape(opt)}</td><td>{d['attempts']}</td><td>{d.get('completed',0)}</td><td>{d.get('numeric-refusal',0)}</td></tr>"
                         for (r,lp,opt),d in sorted(groups.items()))
    sum_html = "".join(f"<li><strong>{value}</strong> {html.escape(key.replace('_',' '))}</li>" for key,value in sorted(counts.items()))
    provenance = json.dumps(file_hashes, indent=2, sort_keys=True)
    shared_style = (ROOT / "docs/examples/examples.css").read_text(encoding="utf-8")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Strategy A choice pipeline · #944</title><style>{shared_style}
.issue944-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr));gap:.75rem;margin:1rem 0}}.issue944-stat{{min-width:0;border:1px solid var(--line);background:var(--surface);padding:.8rem}}.issue944-stat strong{{display:block;font-size:1.8rem;color:var(--accent)}}.issue944-table-scroll{{max-width:100%;overflow:auto;overscroll-behavior-x:contain;border:1px solid var(--line)}}.issue944-narrow,.issue944-print{{display:none}}@media(max-width:600px){{.issue944-wide{{display:none}}.issue944-narrow{{display:block}}}}@media print{{.issue944-wide,.issue944-narrow{{display:none!important}}.issue944-print{{display:block!important}}.issue944-table-scroll{{overflow:visible}}}}
</style></head><body><main><div class="page-content"><p class="eyebrow">Saved numerical example · issue #944 · source commit {SOURCE_COMMIT[:12]}</p><h1>Run every admitted Strategy A choice through one small control task</h1><p>This publication records one-step nominal open-loop candidate-family construction in the public Strategy A pipeline. It exercises admitted reducer, vertex-LP, converter, terminal optimizer and witness-recovery roles. It is not completed feedback/MPC work, a full-family proof, or a global optimality claim.</p>
<section><h2>Declared task</h2><p>One transition with <span class="matrix">x₁ = A x₀ + B u₀</span>:</p><p class="matrix">A = [[1, 0], [0, 1]] &nbsp; B = [[1, 0], [0, 1]] &nbsp; c = [0, 0]</p><p class="matrix">x₀ = [0, 0] &nbsp; X₀ = [−1,1] × [−1,1] &nbsp; U = [0,1] × [0,1] &nbsp; X₁ = [0,1] × [0,1]</p><p class="matrix">linear terminal: c = [−1,0], constant = 0; quadratic terminal: H = [[2,0],[0,2]], center = [0,0], constant = 0</p><p>The optimizer's recovered history is stored in the result record and independently replayed by the checker.</p><div class="issue944-wide"><figure><img src="pipeline-2d.svg" alt="Returned unit-square terminal family with public recovered linear and quadratic histories"><figcaption>The plot shows the returned terminal family and histories selected through public recovery. It illustrates these saved outcomes; it does not claim complete-family verification.</figcaption></figure></div><div class="issue944-narrow"><figure><img src="pipeline-2d-mobile.svg" alt="Returned unit-square terminal family and labeled linear and quadratic recovered histories"><figcaption>Mobile layout of the same saved terminal family and histories.</figcaption></figure></div><div class="issue944-print"><figure><img src="pipeline-2d-print.svg" alt="Printed-color unit-square terminal family with recovered linear and quadratic histories"><figcaption>Figure colors use the shared report print palette.</figcaption></figure></div></section>
<section><h2>Full admitted-choice accounting</h2><div class="issue944-stats"><div class="issue944-stat"><strong>128</strong>role tuples</div><div class="issue944-stat"><strong>{structural}</strong>structural contract exclusions</div><div class="issue944-stat"><strong>{completed}</strong>completed attempts</div><div class="issue944-stat"><strong>{refused}</strong>numeric refusals</div></div><ul>{sum_html}</ul><p>The {structural} exclusions are Phase-I profiles paired with nonzero terminal objectives, which the declared contracts disallow. Of 64 admitted attempts, {completed} completed and {refused} reached value-level numeric refusal. The refusals are retained attempts, not structural incompatibilities.</p><p><a href="role-matrix.csv" download>Download all 128 tuples with provider roles and statuses (CSV)</a> · <a href="records.json" download>Download complete raw execution record (JSON)</a></p><div class="scroll issue944-table-scroll"><table><thead><tr><th>Reducer</th><th>Vertex LP</th><th>Terminal optimizer</th><th>Attempts</th><th>Complete</th><th>Numeric refusal</th></tr></thead><tbody>{group_rows}</tbody></table></div></section>
<section><h2>Observed converter boundary</h2><p>The faithful KPABEP provider produced ordered V input [(0,1),(1,1),(0,0),(1,0)]. Qhull returned these H rows and bounds:</p><pre><code>H = [[1,-1.1102230246251565e-16], [0,1], [1.1102230246251565e-16,-1], [-1,0]]; b = [0.99999999999999989,1,0,0]</code></pre><p>Separate HiGHS LP and convex checks refused those matrices under the 10⁻¹² removal threshold. The exact requests and diagnostics are in the raw record and linked follow-up <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/974">issue #974</a>. Coefficients were not rounded or dropped.</p></section>
<section><h2>Recovered-history indexing regression</h2><p>This separate fixture has nonzero origin and distinct state/control domains. The returned witness is x₀=(2,3), x₁=(3,4), u₀=(1,1). Since x₁ and u₀ differ, checking the terminal family against control coordinates would fail the public membership check. The saved independent record confirms initial membership, dynamics, control bounds, endpoint membership, and returned-family recovery; it does not assert an arbitrary LP tie-break.</p><div class="issue944-wide"><figure><img src="terminal-membership-regression.svg" alt="Distinct initial state, terminal state, and control boxes with recovered witness points"><figcaption>Separate coordinate panels make the terminal state and control vectors visibly distinct.</figcaption></figure></div><div class="issue944-narrow"><figure><img src="terminal-membership-regression-mobile.svg" alt="Stacked initial state, terminal state, and control coordinate panels with recovered witness points"><figcaption>Stacked coordinate panels keep the state and control domains distinct on narrow screens.</figcaption></figure></div><div class="issue944-print"><figure><img src="terminal-membership-regression-print.svg" alt="Printed-color distinct initial state, terminal state, and control boxes with recovered witness points"><figcaption>The print variant uses the shared report print palette.</figcaption></figure></div><p><a href="terminal-membership-regression.json" download>Download the independent regression record</a></p></section>
<section><h2>Reproduction and source identity</h2><p>Rebuild target: <code>csl_strategy_a_each_choice_pipeline</code> with CMake Release, HiGHS and Qhull enabled. Run <code>ctest --test-dir &lt;build&gt; -C Release --output-on-failure -R '^strategy_a_each_choice_pipeline_contract$'</code>, then run the native executable and <code>scripts/catalogue/check_944_each_choice_pipeline.py</code> against the emitted JSON. These are functional checks; elapsed times in the record are not performance results.</p><p>Solver source commit: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{SOURCE_COMMIT}">{SOURCE_COMMIT}</a>. The matrix and regression records below are checksummed in <code>SHA256SUMS</code>. Implementation source and executable hashes are retained in provenance:</p><pre>{html.escape(provenance)}</pre><p><a href="SHA256SUMS">Checksums</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{SOURCE_COMMIT}">Runner and checker source commit</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/pull/976">Related #976 Qhull follow-up and public Strategy A example</a></p></section>
<footer>Controlled Systems Lab · Saved execution record · #944 remains open while two admitted KPABEP→HiGHS outcomes await the #974 conversion fix.</footer></div></main></body></html>'''


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: render_issue944_each_choice.py BUNDLE_DIRECTORY")
    bundle = Path(sys.argv[1])
    run = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    regression = json.loads((bundle / "terminal-membership-regression.json").read_text(encoding="utf-8"))
    assert run["schema"] == "csl.strategy-a-each-choice-pipeline/2" and len(run["attempts"]) == 128
    assert regression["schema"] == "csl.strategy-a-terminal-membership-indexing-regression/1"
    assert run["task"]["dynamics"] == regression["task"]["dynamics"] == "x_next=x+u"
    # Keep the existing reviewed renderer as the source for the main pipeline plot.
    import importlib.util
    renderer_path = ROOT / "scripts/catalogue/render_944_each_choice_example.py"
    spec = importlib.util.spec_from_file_location("render_944_example", renderer_path)
    renderer = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(renderer)
    # Existing renderer takes paths through argv; render to the current bundle.
    old_argv = sys.argv
    try:
        sys.argv = [str(renderer_path), str(bundle / "records.json"), str(bundle / "pipeline-2d.svg")]
        assert renderer.main() == 0
        sys.argv = [str(renderer_path), str(bundle / "records.json"), str(bundle / "pipeline-2d-print.svg"), "--print"]
        assert renderer.main() == 0
    finally:
        sys.argv = old_argv
    (bundle / "terminal-membership-regression.svg").write_text(regression_svg(regression), encoding="utf-8")
    (bundle / "terminal-membership-regression-mobile.svg").write_text(regression_svg(regression, mobile_mode=True), encoding="utf-8")
    (bundle / "terminal-membership-regression-print.svg").write_text(regression_svg(regression, print_mode=True), encoding="utf-8")
    (bundle / "pipeline-2d-mobile.svg").write_text(mobile_pipeline_svg(run), encoding="utf-8")
    with (bundle / "role-matrix.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = list(csv_rows(run))
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    file_hashes = {
        "solver_source_commit": SOURCE_COMMIT,
        "runner_source_sha256": digest(ROOT / "tools/strategy_a_each_choice_pipeline.cpp"),
        "checker_source_sha256": digest(ROOT / "scripts/catalogue/check_944_each_choice_pipeline.py"),
        "publication_renderer_sha256": digest(Path(__file__).resolve()),
        "plot_renderer_sha256": digest(ROOT / "scripts/catalogue/render_944_each_choice_example.py"),
        "shared_stylesheet_sha256": digest(ROOT / "docs/examples/examples.css"),
        "runner_sha256": RUNNER_SHA256,
        "checker_sha256": CHECKER_SHA256,
        "binary_sha256": BINARY_SHA256,
        "records.json": digest(bundle / "records.json"),
        "terminal-membership-regression.json": digest(bundle / "terminal-membership-regression.json"),
    }
    (bundle / "provenance.json").write_text(json.dumps({"schema":"csl.issue944-publication-provenance/1",**file_hashes},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (bundle / "index.html").write_text(page(run, regression, file_hashes), encoding="utf-8")
    names = ["index.html", "pipeline-2d.svg", "pipeline-2d-mobile.svg", "pipeline-2d-print.svg",
             "terminal-membership-regression.svg", "terminal-membership-regression-mobile.svg",
             "terminal-membership-regression-print.svg", "records.json",
             "terminal-membership-regression.json", "role-matrix.csv", "provenance.json"]
    (bundle / "SHA256SUMS").write_text("".join(f"{digest(bundle/name)}  {name}\n" for name in names),encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

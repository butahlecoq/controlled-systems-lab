#!/usr/bin/env python3
"""Render the source-bound post-correction #944 Strategy A run."""
from __future__ import annotations

import csv
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
ROUTE = "issue944-strategy-a-each-choice-postfix-v1"
PLOT = ROOT / "scripts/catalogue/render_944_each_choice_example.py"
PLOT_HELPER = ROOT / "scripts/reports/render_issue944_each_choice.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def regression_svg(record: dict, mobile: bool = False, print_mode: bool = False) -> str:
    task, attempt = record["task"], record["attempt"]
    history = attempt["selected_history"]
    x0, x1, u = history[:2], history[2:4], history[4:6]
    initial = task["initial_state_box"]
    terminal = task["next_state_box"]
    control = task["control_box"]
    screen, printed = load_module(PLOT_HELPER, "issue944_postfix_plot_helper").theme_tokens()
    theme = printed if print_mode else screen

    def point_text(values):
        return "(" + ",".join(f"{value:g}" for value in values) + ")"

    def panel(title, bounds, point, coordinates, left, top):
        width, height, padx, pady = 330, 250, 36, 22
        (xlo, xhi), (ylo, yhi) = bounds
        sx = lambda value: left + padx + (value - xlo) / (xhi - xlo) * (width - 2 * padx)
        sy = lambda value: top + height - pady - (value - ylo) / (yhi - ylo) * (height - 2 * pady)
        corners = [(xlo, ylo), (xhi, ylo), (xhi, yhi), (xlo, yhi)]
        polygon = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in corners)
        return (
            f'<text x="{left}" y="{top-27}" class="panel">{html.escape(title)}</text>'
            f'<rect x="{left+padx}" y="{top+pady}" width="{width-2*padx}" height="{height-2*pady}" class="frame"/>'
            f'<polygon points="{polygon}" class="domain"/>'
            f'<circle cx="{sx(point[0]):.1f}" cy="{sy(point[1]):.1f}" r="7" class="point"/>'
            f'<text x="{sx(point[0])+9:.1f}" y="{sy(point[1])-8:.1f}" class="label">{html.escape(title[0:2] + "=" + point_text(point))}</text>'
            f'<text x="{left+width/2}" y="{top+height+22}" class="axis" text-anchor="middle">coordinate 1</text>'
            f'<text x="{left+padx}" y="{top+height-2}" class="tick">{xlo:g}</text>'
            f'<text x="{left+width-padx-12}" y="{top+height-2}" class="tick">{xhi:g}</text>'
            f'<text x="{left+3}" y="{top+height-pady+4}" class="tick">{ylo:g}</text>'
            f'<text x="{left+3}" y="{top+pady+4}" class="tick">{yhi:g}</text>')

    if mobile:
        content = panel("Initial state x₀", initial, x0, (), 42, 112)
        content += panel("Terminal state x₁", terminal, x1, (), 42, 422)
        content += panel("Control u₀", control, u, (), 42, 732)
        view_box, height, title = "0 0 420 1080", 1080, "Recovered witness"
        footer = ('<text x="42" y="1040" class="axis">Dynamics: x₁=x₀+u₀; each vector satisfies its declared domain.</text>'
                  '<text x="42" y="1060" class="axis">The endpoint belongs to the returned terminal family.</text>')
    else:
        content = panel("Initial state x₀", initial, x0, (), 42, 95)
        content += panel("Terminal state x₁", terminal, x1, (), 430, 95)
        content += panel("Control u₀", control, u, (), 818, 95)
        view_box, height, title = "0 0 1200 440", 440, "A recovered witness distinguishes terminal state from control"
        footer = ('<text x="42" y="420" class="axis">Dynamics: x₁=x₀+u₀; each vector satisfies its declared domain; endpoint is in the returned family.</text>')
    css = (
        "text{font-family:Inter,system-ui,sans-serif;fill:" + theme["--text"] + "}"
        ".title{font-size:22px;font-weight:650}.panel{font-size:18px;font-weight:600}"
        ".frame{fill:" + theme["--surface"] + ";stroke:" + theme["--line"] + "}"
        ".domain{fill:" + theme["--accent"] + ";fill-opacity:.2;stroke:" + theme["--accent"] + ";stroke-width:2}"
        ".point{fill:" + theme["--warm"] + ";stroke:" + theme["--page"] + ";stroke-width:2}"
        ".label{font-size:14px}.axis,.tick{fill:" + theme["--text-muted"] + ";font-size:12px}")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" role="img" aria-labelledby="title desc">
<title id="title">Nonzero-origin terminal membership regression</title>
<desc id="desc">Three separate coordinate domains show the saved recovered initial state, terminal state, and control. Terminal and control values are distinct.</desc>
<style>{css}</style>
<rect width="{view_box.split()[2]}" height="{height}" fill="{theme["--page"]}"/>
<text x="42" y="42" class="title">{html.escape(title)}</text>{content}{footer}
</svg>'''


def render_plot(record: dict, bundle: Path) -> None:
    helper = load_module(PLOT, "issue944_postfix_pipeline_plot")
    old_argv = sys.argv
    try:
        sys.argv = [str(PLOT), str(bundle / "records.json"), str(bundle / "pipeline-2d.svg")]
        assert helper.main() == 0
        sys.argv = [str(PLOT), str(bundle / "records.json"), str(bundle / "pipeline-2d-print.svg"), "--print"]
        assert helper.main() == 0
    finally:
        sys.argv = old_argv
    linear = next(row for row in record["attempts"] if row["task"] == "linear" and row["status"] == "completed")
    quadratic = next(row for row in record["attempts"] if row["task"] == "quadratic" and row["status"] == "completed")
    lp_endpoint, qp_endpoint = linear["selected_history"][2:4], quadratic["selected_history"][2:4]
    replacement = ("LP x₁=" + point_text(lp_endpoint) + "; QP x₁=" + point_text(qp_endpoint))
    for name in ("pipeline-2d.svg", "pipeline-2d-print.svg"):
        path = bundle / name
        text = path.read_text(encoding="utf-8")
        text = text.replace("LP optimum: (1,0); convex: (0,0)", replacement)
        text = text.replace("returned terminal-optimal family", "returned terminal candidate family")
        path.write_text(text, encoding="utf-8")
    plot_helper = load_module(PLOT_HELPER, "issue944_postfix_report_plot_helper")
    (bundle / "pipeline-2d-mobile.svg").write_text(
        plot_helper.mobile_pipeline_svg(record), encoding="utf-8")


def point_text(values):
    return "(" + ",".join(f"{value:g}" for value in values) + ")"


def outcome_class(row: dict) -> str:
    if row.get("first_unmet", "").startswith("phase_one.objective:"):
        return "structural-contract-exclusion"
    if row.get("first_unmet", "").startswith(("highs.matrix:", "highs.convex.matrix:")):
        return "numeric-refusal"
    return "completed" if row["status"] == "completed" else "other-refusal"


def page(record: dict, regression: dict, capture_provenance: dict, publication_provenance: dict,
         stylesheet: str) -> str:
    counts = {}
    for row in record["attempts"]:
        label = outcome_class(row)
        counts[label] = counts.get(label, 0) + 1
    completed = counts.get("completed", 0)
    structural = counts.get("structural-contract-exclusion", 0)
    refused = counts.get("numeric-refusal", 0)
    groups = {}
    for row in record["attempts"]:
        key = (row["vertex_reducer"], row["vertex_lp_provider"], row["terminal_optimizer_choice"])
        slot = groups.setdefault(key, {"attempts": 0, "completed": 0, "numeric-refusal": 0})
        slot["attempts"] += 1
        slot[outcome_class(row)] = slot.get(outcome_class(row), 0) + 1
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            reducer, vertex_lp, terminal, values["attempts"], values.get("completed", 0),
            values.get("numeric-refusal", 0))) + "</tr>"
        for (reducer, vertex_lp, terminal), values in sorted(groups.items()))
    trace = next(item for row in record["attempts"]
                 if row["vertex_reducer"] == "csl.hull.source.btulshor-kpabep" and row["status"] == "completed"
                 for item in row["program_boundary_observations"]
                 if item.startswith("Qhull 8.0.2 Qx V-to-H conversion output:")
                 and "ordered_V_vertices=[0,1;1,1;0,0;1,0]" in item)
    history = regression["attempt"]["selected_history"]
    initial, terminal, control = history[:2], history[2:4], history[4:6]
    if completed == 64 and structural == 64 and refused == 0:
        summary = "All 64 admitted attempts completed through their declared pipeline roles. The other 64 tuples are Phase-I/nonzero-objective contract exclusions."
    else:
        summary = f"Observed {completed} completions, {refused} numerical refusals, and {structural} structural exclusions; inspect the full status table and retained traces."
    source_commit = capture_provenance["source_commit"]
    prov_html = html.escape(json.dumps(publication_provenance, indent=2, sort_keys=True))
    sum_list = "".join(f"<li><strong>{count}</strong> {html.escape(label.replace('-', ' '))}</li>"
                       for label, count in sorted(counts.items()))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Strategy A post-fix candidate pipeline · #944</title><style>{stylesheet}
.issue944-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr));gap:.75rem;margin:1rem 0}}.issue944-stat{{min-width:0;border:1px solid var(--line);background:var(--surface);padding:.8rem}}.issue944-stat strong{{display:block;font-size:1.8rem;color:var(--accent)}}.issue944-table-scroll{{max-width:100%;overflow:auto;overscroll-behavior-x:contain;border:1px solid var(--line)}}.issue944-narrow,.issue944-print{{display:none}}@media(max-width:600px){{.issue944-wide{{display:none}}.issue944-narrow{{display:block}}}}@media print{{.issue944-wide,.issue944-narrow{{display:none!important}}.issue944-print{{display:block!important}}.issue944-table-scroll{{overflow:visible}}}}
</style></head><body><main><div class="page-content">
<p class="eyebrow">Source-qualified follow-up · issue #944 · capture commit {source_commit[:12]}</p>
<h1>Run the admitted Strategy A choices through one small control task</h1>
<p>This is a one-step nominal open-loop candidate-family construction through the public Strategy A API, with public joint-history recovery and a separate numerical history-selection LP. It is not feedback/MPC completion, a full-family proof, or a global optimality claim.</p>
<section><h2>Declared task</h2><p>One transition with <span class="matrix">x₁ = A x₀ + B u₀</span>:</p>
<p class="matrix">A = [[1, 0], [0, 1]] &nbsp; B = [[1, 0], [0, 1]] &nbsp; c = [0, 0]</p>
<p class="matrix">x₀ = [0, 0] &nbsp; X₀ = [−1,1] × [−1,1] &nbsp; U = [0,1] × [0,1] &nbsp; X₁ = [0,1] × [0,1]</p>
<p class="matrix">linear terminal objective c = [−1,0]; quadratic objective H = [[2,0],[0,2]], center = [0,0]</p>
<p>The selected histories are recovered from returned terminal candidate families and checked from the saved numeric values.</p>
<div class="issue944-wide"><figure><img src="pipeline-2d.svg" alt="Returned unit-square terminal family with saved public recovered linear and quadratic histories"><figcaption>Saved candidate-family construction and selected histories. No complete-family, feedback, or optimality claim is made.</figcaption></figure></div><div class="issue944-narrow"><figure><img src="pipeline-2d-mobile.svg" alt="Mobile view of returned terminal family and recovered histories"><figcaption>Saved candidate-family construction and selected histories.</figcaption></figure></div><div class="issue944-print"><figure><img src="pipeline-2d-print.svg" alt="Print-color unit-square candidate family and recovered histories"><figcaption>Saved candidate-family construction and selected histories.</figcaption></figure></div></section>
<section><h2>Choice accounting</h2><div class="issue944-stats"><div class="issue944-stat"><strong>128</strong>role tuples</div><div class="issue944-stat"><strong>{structural}</strong>contract exclusions</div><div class="issue944-stat"><strong>{completed}</strong>completed attempts</div><div class="issue944-stat"><strong>{refused}</strong>numerical refusals</div></div>
<p>{summary}</p><ul>{sum_list}</ul><p>Every admitted role selection and its status is in the CSV and raw record. Faithful legacy hull order/status evidence is retained in each source-index trace.</p>
<div class="scroll issue944-table-scroll"><table><thead><tr><th>Vertex reducer</th><th>Vertex LP</th><th>Terminal optimizer</th><th>Attempts</th><th>Complete</th><th>Numeric refusal</th></tr></thead><tbody>{rows}</tbody></table></div>
<p><a href="role-matrix.csv" download>Download all 128 role tuples (CSV)</a> · <a href="records.json" download>Download exact C++ stdout (JSON)</a> · <a href="terminal-membership-regression.json" download>Download regression stdout</a></p></section>
<section><h2>Observed Qhull conversion output</h2><p>The retained KPABEP source-index hull supplied ordered V vertices [(0,1),(1,1),(0,0),(1,0)] with no rays. The pipeline trace below is the actual Qhull 8.0.2 Qx V→H output. The independent checker reconstructs its bounded vertices from all row intersections and verifies equality with the four input corners.</p>
<pre><code>{html.escape(trace)}</code></pre><p>The earlier source-5a V→H tiny-coefficient refusals remain preserved in the <a href="../issue944-strategy-a-each-choice-v1/index.html">historical 62+2 report</a> and tracked under <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/974">issue #974</a>. This follow-up is a separate capture on the source commit above.</p></section>
<section><h2>Recovered-history indexing regression</h2><p>The separate nonzero-origin witness is x₀={html.escape(point_text(initial))}, x₁={html.escape(point_text(terminal))}, u₀={html.escape(point_text(control))}. The independent checker confirms initial, terminal, and control domains, x₁=x₀+u₀, membership in the returned terminal family, and failure when u₀ is tested as the terminal coordinate.</p>
<div class="issue944-wide"><figure><img src="terminal-membership-regression.svg" alt="Separate initial, terminal, and control domains with the recorded witness"><figcaption>Coordinates are drawn from the saved recovered witness, not an analytic substitute.</figcaption></figure></div><div class="issue944-narrow"><figure><img src="terminal-membership-regression-mobile.svg" alt="Stacked initial, terminal, and control domains with the recorded witness"><figcaption>Coordinates are drawn from the saved recovered witness, not an analytic substitute.</figcaption></figure></div><div class="issue944-print"><figure><img src="terminal-membership-regression-print.svg" alt="Print-color separate state and control domains"><figcaption>Coordinates are drawn from the saved recovered witness, not an analytic substitute.</figcaption></figure></div>
<p><a href="terminal-membership-regression.stderr.txt" download>Download regression invocation stderr</a></p></section>
<section><h2>Source and reproduction</h2><p>Captured from Release source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source_commit}">{source_commit}</a>, with HiGHS and Qhull enabled. Rebuild <code>csl_strategy_a_each_choice_pipeline</code>, run <code>strategy_a_each_choice_pipeline_contract</code>, then validate the saved stdout files with <code>scripts/catalogue/check_944_each_choice_pipeline.py --record-json records.json --regression-json terminal-membership-regression.json --expected-numeric-boundaries 0</code>.</p>
<p>The public <a href="../examples/qhull-highs-strategy-a-2d.html">Qhull and Strategy A 2D interface example</a> is staged from the current source page. The actual build, executable, source and record hashes are listed below. Elapsed timings are functional observations only.</p>
<details><summary>Capture and publication provenance</summary><pre>{prov_html}</pre><p><a href="provenance.json">Capture provenance</a> · <a href="publication-provenance.json">Publication provenance</a> · <a href="SHA256SUMS">Bundle SHA256SUMS</a> · <a href="capture-SHA256SUMS">Original capture SHA256SUMS</a></p></details>
</section><footer>#944 remains open. The record covers one-step nominal open-loop candidate construction; feedback/MPC and remaining acceptance evidence are separate work.</footer>
</div></main></body></html>'''


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_issue944_postfix.py CAPTURE_DIRECTORY BUNDLE_DIRECTORY")
    capture, bundle = Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2]).resolve()
    if bundle.exists():
        raise SystemExit("output bundle must be fresh")
    capture_lines = (capture / "SHA256SUMS").read_text(encoding="ascii")
    for line in capture_lines.splitlines():
        expected, name = line.split("  ", 1)
        if digest(capture / name) != expected:
            raise ValueError("capture checksum mismatch: " + name)
    run = json.loads((capture / "records.json").read_text(encoding="utf-8"))
    regression = json.loads((capture / "terminal-membership-regression.json").read_text(encoding="utf-8"))
    capture_provenance = json.loads((capture / "provenance.json").read_text(encoding="utf-8"))
    if capture_provenance["checker_result"]["status"] != "passed":
        raise ValueError("independent capture checker did not pass")
    bundle.mkdir(parents=True)
    capture_files = [line.split("  ", 1)[1] for line in capture_lines.splitlines()]
    for name in capture_files:
        shutil.copyfile(capture / name, bundle / name)
    shutil.copyfile(capture / "SHA256SUMS", bundle / "capture-SHA256SUMS")
    helper = load_module(PLOT_HELPER, "issue944_postfix_helper")
    render_plot(run, bundle)
    (bundle / "terminal-membership-regression.svg").write_text(regression_svg(regression), encoding="utf-8")
    (bundle / "terminal-membership-regression-mobile.svg").write_text(regression_svg(regression, mobile=True), encoding="utf-8")
    (bundle / "terminal-membership-regression-print.svg").write_text(regression_svg(regression, print_mode=True), encoding="utf-8")
    with (bundle / "role-matrix.csv").open("w", encoding="utf-8", newline="") as stream:
        csv_fields = ["task", "controller", "representation", "vertex_reducer", "vertex_lp_provider",
                      "converter", "converter_lp_provider", "terminal_lp_provider",
                      "terminal_optimizer_choice", "terminal_optimizer_actual", "history_recovery_api",
                      "history_recovery_status", "history_selection_provider", "status", "outcome_class", "first_unmet"]
        writer = csv.DictWriter(stream, fieldnames=csv_fields, lineterminator="\n")
        writer.writeheader()
        for row in run["attempts"]:
            writer.writerow({key: (outcome_class(row) if key == "outcome_class" else row.get(key, ""))
                             for key in csv_fields})
    publication_provenance = {
        "schema": "csl.issue944-postfix-publication-provenance/1",
        "capture_source_commit": capture_provenance["source_commit"],
        "capture_provenance_sha256": digest(bundle / "provenance.json"),
        "capture_sha256sums_sha256": digest(bundle / "capture-SHA256SUMS"),
        "publication_renderer_sha256": digest(Path(__file__).resolve()),
        "plot_renderer_sha256": digest(PLOT),
        "shared_stylesheet_sha256": digest(ROOT / "docs/examples/examples.css"),
        "records_sha256": digest(bundle / "records.json"),
        "regression_sha256": digest(bundle / "terminal-membership-regression.json"),
    }
    (bundle / "publication-provenance.json").write_text(
        json.dumps(publication_provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stylesheet = (ROOT / "docs/examples/examples.css").read_text(encoding="utf-8")
    (bundle / "index.html").write_text(page(run, regression, capture_provenance, publication_provenance, stylesheet),
                                      encoding="utf-8")
    names = sorted(path.name for path in bundle.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest(bundle / name)}  {name}\n" for name in names), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

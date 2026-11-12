#!/usr/bin/env python3
"""Render the immutable #944 Strategy A choice-pipeline result bundle."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "issue944-strategy-a-each-choice-v1"
SOURCE_COMMIT = "5a4730c517a875400ec7b69e4c8e2c265e49016c"
RUNNER_SHA256 = "34cdaa1a6d85902b5188797e11a31b976ebb87ce8327a6bea012aef80ae23c8a"
CHECKER_SHA256 = "30b2ae4c28bac51c914526fa59373da3ed350176489a95dfe76b38d20fe7a6d3"
BINARY_SHA256 = "1c52ab404b11398b0d7ae45aaae1934047dac9a1af77840f06d56307438ee032"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regression_svg(record: dict) -> str:
    task, row = record["task"], record["attempt"]
    history = row["selected_history"]
    assert row["independent_check"]["selected_history_in_returned_family"]
    assert row["independent_check"]["selected_history_in_terminal_family"]
    assert not row["independent_check"]["selected_control_in_terminal_family"]
    x0, x1, u = history[:2], history[2:4], history[4:6]

    def panel(x, title, bounds, point, label, shift):
        left, top, width, height = shift, 95, 330, 250
        xlo, xhi = bounds[0]
        ylo, yhi = bounds[1]
        pad_x, pad_y = 36, 22
        sx = lambda value: left + pad_x + (value - xlo) / (xhi - xlo) * (width - 2 * pad_x)
        sy = lambda value: top + height - pad_y - (value - ylo) / (yhi - ylo) * (height - 2 * pad_y)
        corners = [(xlo,ylo),(xhi,ylo),(xhi,yhi),(xlo,yhi)]
        poly = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a,b in corners)
        return (f'<text x="{left}" y="68" class="panel">{html.escape(title)}</text>'
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
    content = panel("", "Initial state x₀", initial_bounds, x0, "x₀=(2,3)", 42)
    content += panel("", "Terminal state x₁", terminal_bounds, x1, "x₁=(3,4)", 430)
    content += panel("", "Control u₀", control_bounds, u, "u₀=(1,1)", 818)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 440" role="img" aria-labelledby="title desc">
<title id="title">Nonzero-origin terminal membership regression</title><desc id="desc">Separate initial state, terminal state, and control domains. The recovered history is x0=(2,3), x1=(3,4), u0=(1,1), so terminal state coordinates differ from control coordinates.</desc>
<style>text{{font-family:system-ui,sans-serif;fill:#e7e9e5}}.title{{font-size:22px;font-weight:650}}.panel{{font-size:18px;font-weight:600}}.frame{{fill:#141a19;stroke:#67716b}}.domain{{fill:#b3c99c;fill-opacity:.2;stroke:#b3c99c;stroke-width:2}}.point{{fill:#e5a84b;stroke:#101615;stroke-width:2}}.label{{font-size:14px}}.axis,.tick{{fill:#afb8b0;font-size:12px}}</style>
<rect width="1200" height="440" fill="#101615"/><text x="42" y="34" class="title">A recovered witness distinguishes terminal state from control</text>
{content}<text x="42" y="420" class="axis">Dynamics: x₁=x₀+u₀ · all three points lie in their declared domains · endpoint belongs to the returned terminal family.</text>
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
:root{{color-scheme:dark;--bg:#101615;--panel:#19211f;--ink:#e7e9e5;--muted:#b3bdb5;--line:#46524c;--accent:#b3c99c;--gold:#e5a84b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:clamp(20px,5vw,64px)}}h1,h2,h3{{line-height:1.2}}h1{{font-size:clamp(2rem,6vw,4rem);max-width:850px}}h2{{margin-top:2.2em}}a{{color:var(--accent)}}.eyebrow,.muted{{color:var(--muted)}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.stat{{background:#111918;border:1px solid var(--line);border-radius:10px;padding:16px}}.stat strong{{display:block;font-size:1.9rem;color:var(--gold)}}table{{border-collapse:collapse;width:100%;white-space:nowrap}}.table-scroll{{overflow-x:auto}}th,td{{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--accent)}}pre{{overflow:auto;background:#111918;padding:16px;border-radius:8px}}code{{overflow-wrap:anywhere}}img,svg{{max-width:100%;height:auto}}figure{{margin:0}}figcaption{{color:var(--muted);font-size:.92rem}}.matrix{{font-family:ui-monospace,monospace}}footer{{margin-top:56px;color:var(--muted);border-top:1px solid var(--line);padding-top:18px}}@media(max-width:600px){{main{{padding:18px}}}}
</style></head><body><main><p class="eyebrow">Saved numerical example · issue #944 · source commit {SOURCE_COMMIT[:12]}</p><h1>Run every admitted Strategy A choice through one small control task</h1><p>This publication records one-step nominal open-loop candidate-family construction in the public Strategy A pipeline. It exercises admitted reducer, vertex-LP, converter, terminal optimizer and witness-recovery roles. It is not completed feedback/MPC work, a full-family proof, or a global optimality claim.</p>
<section><h2>Declared task</h2><p>One transition with <span class="matrix">x₁ = A x₀ + B u₀</span>:</p><p class="matrix">A = [[1, 0], [0, 1]] &nbsp; B = [[1, 0], [0, 1]] &nbsp; c = [0, 0]</p><p class="matrix">x₀ = [0, 0] &nbsp; X₀ = [−1,1] × [−1,1] &nbsp; U = [0,1] × [0,1] &nbsp; X₁ = [0,1] × [0,1]</p><p class="matrix">linear terminal: c = [−1,0], constant = 0; quadratic terminal: H = [[2,0],[0,2]], center = [0,0], constant = 0</p><p>The optimizer's recovered history is stored in the result record and independently replayed by the checker.</p><figure><img src="pipeline-2d.svg" alt="Returned unit-square terminal family with public recovered linear and quadratic histories"><figcaption>The plot shows the returned terminal family and histories selected through public recovery. It illustrates these saved outcomes; it does not claim complete-family verification.</figcaption></figure></section>
<section><h2>Full admitted-choice accounting</h2><div class="stats"><div class="stat"><strong>128</strong>role tuples</div><div class="stat"><strong>{structural}</strong>structural contract exclusions</div><div class="stat"><strong>{completed}</strong>completed attempts</div><div class="stat"><strong>{refused}</strong>numeric refusals</div></div><ul>{sum_html}</ul><p>The {structural} exclusions are Phase-I profiles paired with nonzero terminal objectives, which the declared contracts disallow. Of 64 admitted attempts, {completed} completed and {refused} reached value-level numeric refusal. The refusals are retained attempts, not structural incompatibilities.</p><p><a href="role-matrix.csv" download>Download all 128 tuples with provider roles and statuses (CSV)</a> · <a href="records.json" download>Download complete raw execution record (JSON)</a></p><div class="table-scroll"><table><thead><tr><th>Reducer</th><th>Vertex LP</th><th>Terminal optimizer</th><th>Attempts</th><th>Complete</th><th>Numeric refusal</th></tr></thead><tbody>{group_rows}</tbody></table></div></section>
<section><h2>Observed converter boundary</h2><p>The faithful KPABEP provider produced ordered V input [(0,1),(1,1),(0,0),(1,0)]. Qhull returned H rows containing ±1.1102230246251565×10⁻¹⁶ coefficients. Separate HiGHS LP and convex checks refused those matrices under the 10⁻¹² removal threshold. The exact requests and diagnostics are in the raw record and linked follow-up <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/974">issue #974</a>. Coefficients were not rounded or dropped.</p></section>
<section><h2>Recovered-history indexing regression</h2><p>This separate fixture has nonzero origin and distinct state/control domains. The returned witness is x₀=(2,3), x₁=(3,4), u₀=(1,1). Since x₁ and u₀ differ, checking the terminal family against control coordinates would fail the public membership check. The saved independent record confirms initial membership, dynamics, control bounds, endpoint membership, and returned-family recovery; it does not assert an arbitrary LP tie-break.</p><figure><img src="terminal-membership-regression.svg" alt="Distinct initial state, terminal state, and control boxes with recovered witness points"><figcaption>Separate coordinate panels make the terminal state and control vectors visibly distinct.</figcaption></figure><p><a href="terminal-membership-regression.json" download>Download the independent regression record</a></p></section>
<section><h2>Reproduction and source identity</h2><p>Rebuild target: <code>csl_strategy_a_each_choice_pipeline</code> with CMake Release, HiGHS and Qhull enabled. Run <code>ctest --test-dir &lt;build&gt; -C Release --output-on-failure -R '^strategy_a_each_choice_pipeline_contract$'</code>, then run the native executable and <code>scripts/catalogue/check_944_each_choice_pipeline.py</code> against the emitted JSON. These are functional checks; elapsed times in the record are not performance results.</p><p>Solver source commit: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{SOURCE_COMMIT}">{SOURCE_COMMIT}</a>. The matrix and regression records below are checksummed in <code>SHA256SUMS</code>. Implementation source and executable hashes are retained in provenance:</p><pre>{html.escape(provenance)}</pre><p><a href="SHA256SUMS">Checksums</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{SOURCE_COMMIT}">Runner and checker source commit</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/pull/976">Related #976 Qhull follow-up and public Strategy A example</a></p></section>
<footer>Controlled Systems Lab · Saved execution record · #944 remains open while two admitted KPABEP→HiGHS outcomes await the #974 conversion fix.</footer></main></body></html>'''


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
    finally:
        sys.argv = old_argv
    (bundle / "terminal-membership-regression.svg").write_text(regression_svg(regression), encoding="utf-8")
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
    names = ["index.html", "pipeline-2d.svg", "terminal-membership-regression.svg", "records.json",
             "terminal-membership-regression.json", "role-matrix.csv", "provenance.json"]
    (bundle / "SHA256SUMS").write_text("".join(f"{digest(bundle/name)}  {name}\n" for name in names),encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

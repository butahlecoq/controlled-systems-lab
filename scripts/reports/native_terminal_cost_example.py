"""Render the native terminal-cost correction from saved diagnostic exchanges."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import zipfile

import numpy as np
import site_design
from mathematical_notation import matrix_html

ROOT = Path(__file__).resolve().parents[2]
ROUTE = "native-terminal-cost-33f907a0"
BUNDLE = ROOT / "reports/algorithm-results" / ROUTE


def palette(printed: bool) -> dict[str, str]:
    blocks = re.findall(r":root\s*\{([^}]+)\}", site_design.stylesheet().decode(), re.S)
    values = dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", blocks[int(printed)]))
    required = {"--page", "--surface", "--text", "--text-muted", "--accent", "--warm", "--line"}
    if not required <= values.keys():
        raise ValueError("Shared plot palette is incomplete")
    return values


def quadratic(spec: dict, point) -> float:
    x = np.asarray(point, dtype=float)
    return float(0.5 * x @ np.asarray(spec["Q"]) @ x + np.asarray(spec["linear"]) @ x + spec["offset"])


def load_records(bundle: Path):
    before = json.loads((bundle / "before/summary.json").read_text())
    after = json.loads((bundle / "after/record.json").read_text())
    if after.get("schema") != "csl.native-terminal-objective-diagnostic/1":
        raise ValueError("Unsupported diagnostic record")
    old_rows = {row["task"]: row for row in before["rows"]}
    if set(old_rows) != {row["task"] for row in after["rows"]}:
        raise ValueError("Before and after tasks differ")
    for row in after["rows"]:
        if not row["parity_passed"] or row["task_sha256"] != old_rows[row["task"]]["source_task_sha256"]:
            raise ValueError("Task identity or corrected component parity differs")
        if row["selected_plan"]["states"][-1] != old_rows[row["task"]]["final_state"]:
            raise ValueError("This comparison requires matching returned final states")
        raw = json.loads((bundle / "after" / (row["task"] + "-capture.json")).read_text())
        if raw["parsed_response"]["selected_plan"] != row["selected_plan"]:
            raise ValueError("Component record differs from the raw native response")
        definition = row["source_definition"]
        point = row["selected_plan"]["states"][-1]
        expected = sum(w*((x-t)/scale)**2 for w,x,t,scale in zip(
            definition["terminal_weights"], point, definition["terminal_target"], definition["terminal_scale"]))
        if not math.isclose(expected,row["reported_cost"]["terminal"],rel_tol=1e-10,abs_tol=1e-10):
            raise ValueError("Saved native terminal value differs from the source formula")
    captures = [json.loads((bundle / phase / "syn-nl-lv-01-capture.json").read_text())
                for phase in ("before", "after")]
    specs = [capture["request"]["terminal_objective"] for capture in captures]
    for spec in specs:
        q = np.asarray(spec["Q"], dtype=float)
        if q.shape != (2, 2) or not np.array_equal(q, np.diag(np.diag(q))) or not (np.diag(q) > 0).all():
            raise ValueError("This illustration requires two positive diagonal quadratic coordinates")
    if specs[0]["linear"] != specs[1]["linear"] or specs[0]["offset"] != specs[1]["offset"]:
        raise ValueError("The diagnostic changes more than the quadratic coefficient convention")
    if not np.array_equal(2 * np.asarray(specs[0]["Q"]), specs[1]["Q"]):
        raise ValueError("Corrected Hessian is not twice the previous matrix")
    return before, after, specs


def plot(path: Path, specs: list[dict], printed: bool) -> None:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Ellipse

    colors = palette(printed)
    with plt.rc_context({"font.family": ["DejaVu Sans", "sans-serif"], "font.size": 16,
                         "svg.fonttype": "none", "svg.hashsalt": ROUTE}):
        fig, ax = plt.subplots(figsize=(6, 5), facecolor=colors["--page"])
        ax.set_facecolor(colors["--surface"])
        for spec, color, style, letter in zip(specs, [colors["--warm"], colors["--accent"]], ["--", "-"], ["B", "A"]):
            q = np.asarray(spec["Q"])
            center = np.linalg.solve(q, -np.asarray(spec["linear"]))
            for delta in (0.25, 1.0):
                radii = np.sqrt(2 * delta / np.diag(q))
                ax.add_patch(Ellipse(center, 2*radii[0], 2*radii[1], fill=False,
                                    edgecolor=color, linewidth=2, linestyle=style))
            ax.scatter(*center, color=color, s=55, zorder=5)
            ax.annotate(letter, center, xytext=(8, 8), textcoords="offset points",
                        color=color, fontsize=18, fontweight="bold")
        ax.set(xlim=(0, 360), ylim=(0, 288), xlabel="State x₁", ylabel="State x₂")
        ax.set_aspect("equal",adjustable="box")
        ax.set_xticks([0, 100, 200, 300]); ax.set_yticks([0, 80, 160, 240])
        ax.tick_params(colors=colors["--text"], labelsize=16)
        ax.xaxis.label.set_color(colors["--text"]); ax.yaxis.label.set_color(colors["--text"])
        for spine in ax.spines.values(): spine.set_color(colors["--line"])
        ax.grid(color=colors["--line"], linewidth=0.7, alpha=0.7)
        handles = [Line2D([], [], color=colors["--accent"], linewidth=2, label="Source cost"),
                   Line2D([], [], color=colors["--warm"], linewidth=2, linestyle="--", label="Previous adapter")]
        ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=15,
                  labelcolor=colors["--text"])
        fig.tight_layout(pad=0.7)
        fig.savefig(path, format="svg", metadata={"Date": None, "Creator": "native_terminal_cost_example.py"})
        plt.close(fig)
    text = path.read_text()
    text = text.replace('<svg ', '<svg role="img" aria-labelledby="cost-title cost-description" ', 1)
    end = text.index('>', text.index('<svg ')) + 1
    text = text[:end] + '<title id="cost-title">Lotka terminal-cost coefficient correction</title><desc id="cost-description">A is the source target [100,80]. B is the previous quadratic minimum [200,160]. Solid and dashed ellipses show levels one quarter and one above their respective unconstrained minima.</desc>' + text[end:]
    path.write_text(text)


def render(bundle: Path) -> None:
    before, after, specs = load_records(bundle)
    plot(bundle / "cost-contours.svg", specs, False)
    plot(bundle / "cost-contours-print.svg", specs, True)
    definition = next(row["source_definition"] for row in after["rows"] if row["task"] == "syn-nl-lv-01")
    target = definition["terminal_target"]
    d = [[definition["terminal_weights"][i] / definition["terminal_scale"][i]**2 if i == j else 0
          for j in range(2)] for i in range(2)]
    matrices = '<div class="cost-matrices">' + ''.join(
        '<p>' + escape(label) + ' = ' + matrix_html(values, label, display_significant_digits=7) + '</p>'
        for label, values in [('r', [[x] for x in target]), ('D', d), ('Q', specs[1]['Q']),
                              ('q', [[x] for x in specs[1]['linear']])]) + '</div>'
    rows = []
    old = {row['task']: row for row in before['rows']}
    for row in after['rows']:
        label = 'Lotka' if row['task'] == 'syn-nl-lv-01' else 'Fuel'
        values = [old[row['task']]['reported_terminal'], row['reported_cost']['terminal'], row['expected_source_cost']['terminal']]
        rows.append('<tr><th scope="row">' + label + '</th>' + ''.join('<td>' + format(v,'.6g') + '</td>' for v in values) + '</tr>')
    css = '<style>.cost-matrices{display:flex;flex-wrap:wrap;gap:1.5rem}.cost-contour{max-width:46rem;margin-inline:auto}.cost-values{max-width:46rem}.cost-print{display:none}@media print{.cost-screen{display:none}.cost-print{display:block}.cost-contour img{max-height:3.6in;width:auto;max-width:100%;margin-inline:auto}}</style>'
    page = site_design.page_start('Match the source terminal cost', crumbs=[('Examples','https://butahlecoq.github.io/controlled-systems-lab/examples/index.html'),('Terminal cost','index.html')], current_href='index.html') + css
    page += '<h1>Match the source terminal cost</h1><p>A factor of two in a quadratic interface changes the preferred terminal state. These saved Lotka and fuel queries isolate the native adapter correction in <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/980">issue #980</a>.</p>'
    page += '<section><h2>The mathematical interface</h2><p class="math-input">J<sub>T</sub>(x) = (x − r)ᵀD(x − r) = ½xᵀQx + qᵀx + c, with Q = 2D, q = −2Dr and c = rᵀDr.</p>' + matrices
    page += '<p>For this Lotka task, r is a 2 × 1 column vector and D and Q are 2 × 2 matrices. The previous adapter supplied Q = D while keeping the full linear and constant terms. Its unconstrained minimum moves to 2r.</p></section>'
    page += '<figure class="cost-contour"><img class="cost-screen" src="cost-contours.svg" alt="Source minimum A and previous adapter minimum B with terminal cost contours"><img class="cost-print" src="cost-contours-print.svg" alt="Print palette of the source and previous terminal cost contours"><figcaption>A = r = (100,80)ᵀ; B = 2r = (200,160)ᵀ. Each pair of contours is ¼ and 1 above that polynomial’s own minimum. This analytic construction explains the coefficient convention; control constraints and reachable sets are separate.</figcaption></figure>'
    max_difference=max(abs(row['reported_cost'][key]-value) for row in after['rows'] for key,value in row['expected_source_cost'].items())
    page += '<section><h2>Check the native values</h2><p>Both queries start at a source target state and solve only the final remaining decision with the original horizon normalization. They are diagnostic queries, not full episodes. The before and after queries return the same final state in each task.</p><div class="scroll cost-values" role="region" tabindex="0" aria-label="Native terminal cost comparison"><table><thead><tr><th>Task</th><th>Previous terminal</th><th>Corrected terminal</th><th>Source formula</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div><p>Displayed values use six significant digits; raw records retain binary64 values. The saved source checks compare terminal, running and total components separately. The largest corrected absolute component difference is ' + format(max_difference,'.3g') + '.</p></section>'
    page += '<section><h2>Historical evidence</h2><p>The frozen native results at source 64560a03 used the previous polynomial. Their physical trajectories and independently recomputed physical costs remain observations. Preserve those records; use the corrected source identity for new source-cost comparisons. The independent continuous NMPC adapters and the orbit norm adapter use separate constructions.</p></section>'
    page += '<details><summary>Source, raw diagnostics and reproduction</summary><p><a href="after/record.json">Corrected component checks and source hashes</a> · <a href="before/summary.json">Previous diagnostic summary</a> · <a href="SHA256SUMS">Bundle checksums</a> · <a href="https://butahlecoq.github.io/controlled-systems-lab/' + ROUTE + '.zip">Offline bundle</a></p><ul>'
    for phase in ('before','after'):
        for task in ('syn-nl-lv-01','syn-nl-fuel-01'):
            name=phase+'/'+task+'-capture.json'
            page += '<li><a href="'+name+'">'+phase+' '+task+' request and native response</a></li>'
    page += '</ul><p>Corrected capture source: <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/' + after['source_commit'] + '">' + after['source_commit'] + '</a>. The supplied bridge artifact hash is recorded; its exact build revision was unavailable.</p>'
    command = 'cmake -S . -B build-cost -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON\ncmake --build build-cost --target csl_closed_loop_native_policy -j1\npython benchmarks/reporting/closed_loop/terminal_objective_probe.py --bridge build-cost/csl_closed_loop_native_policy --output fresh-cost-diagnostics'
    page += '<p>At the corrected capture source tag, build the public bridge and capture into a new directory:</p>' + site_design.code_block(command,'Reproduce the final-stage cost diagnostics') + '</details>' + site_design.page_end()
    (bundle / 'index.html').write_text(page)
    provenance = {'renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'shared_stylesheet_sha256':hashlib.sha256(site_design.stylesheet()).hexdigest(),
        'capture_source':after['source_commit'],'scope':'Rendered from saved diagnostic exchanges; no solver or benchmark is run.'}
    (bundle / 'presentation.json').write_text(json.dumps(provenance,indent=2)+'\n')
    files=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (bundle / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(bundle).as_posix()+'\n' for p in files))
    archive=bundle.parent/(ROUTE+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as saved:
        for path in sorted(p for p in bundle.rglob('*') if p.is_file()):
            entry=zipfile.ZipInfo(ROUTE+'/'+path.relative_to(bundle).as_posix(),(1980,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            saved.writestr(entry,path.read_bytes())
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')



def stage(site: Path) -> None:
    if any(path.is_symlink() for path in BUNDLE.rglob('*')):
        raise ValueError('Source bundle contains a symlink')
    archive=BUNDLE.parent/(ROUTE+'.zip')
    expected=(archive.with_suffix('.zip.sha256')).read_text().split()[0]
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
        raise ValueError('Offline archive checksum differs')
    with zipfile.ZipFile(archive) as saved:
        if saved.testzip() is not None:
            raise ValueError('Offline archive CRC differs')
        expected_members={ROUTE+'/'+p.relative_to(BUNDLE).as_posix():p for p in BUNDLE.rglob('*') if p.is_file()}
        if set(saved.namelist())!=expected_members.keys():
            raise ValueError('Offline archive inventory differs')
        if any(saved.read(name)!=path.read_bytes() for name,path in expected_members.items()):
            raise ValueError('Offline archive payload differs')
    target=site/ROUTE
    if target.exists():
        if {p.relative_to(target) for p in target.rglob('*') if p.is_file()} != {p.relative_to(BUNDLE) for p in BUNDLE.rglob('*') if p.is_file()}:
            raise ValueError('Existing staged cost bundle has a different inventory')
        if any(p.read_bytes() != (target/p.relative_to(BUNDLE)).read_bytes() for p in BUNDLE.rglob('*') if p.is_file()):
            raise ValueError('Existing staged cost bundle differs')
    else:
        shutil.copytree(BUNDLE,target)
    staged_archive=site/archive.name
    if staged_archive.exists() and staged_archive.read_bytes()!=archive.read_bytes():
        raise ValueError('Existing staged archive differs')
    if not staged_archive.exists():shutil.copyfile(archive,staged_archive)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--site',type=Path)
    args=parser.parse_args()
    if args.render: render(BUNDLE)
    if args.site: stage(args.site)
    if not args.render and args.site is None: parser.error('Choose --render or --site')


if __name__ == '__main__': main()

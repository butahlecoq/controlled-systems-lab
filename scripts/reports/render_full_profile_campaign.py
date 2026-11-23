"""Render the frozen 513-graph closed-loop campaign as an HTML dashboard and figures."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import campaign_graph_figures as figures  # noqa: E402
from site_design import page_end, page_start  # noqa: E402

TASK_LABELS = {
    "syn-nl-lv-01": "Lotka–Volterra",
    "earth-orbit": "Earth orbit",
    "syn-nl-fuel-01": "Fuel transfer",
}
PLANES: dict[str, list[figures.Projection]] = {
    "syn-nl-lv-01": [
        {
            "id": "populations",
            "indices": [0, 1],
            "labels": ["Prey P", "Predator R"],
            "units": ["thousand individuals", "thousand individuals"],
        }
    ],
    "earth-orbit": [
        {
            "id": "orbit",
            "indices": [0, 3],
            "labels": ["Radius r", "Angular rate ω"],
            "units": ["km", "rad/s"],
        }
    ],
    "syn-nl-fuel-01": [
        {
            "id": "oxidizer",
            "indices": [0, 2],
            "labels": ["Oxidizer mass mₒₓ", "Oxidizer flow qₒₓ"],
            "units": ["kg", "kg/s"],
        },
        {
            "id": "fuel",
            "indices": [1, 3],
            "labels": ["Fuel mass m_f", "Fuel flow q_f"],
            "units": ["kg", "kg/s"],
        },
    ],
}
FUEL_PAIRED_PLANES: list[figures.Projection] = [
    {
        "id": "propellant-masses",
        "indices": [0, 1],
        "labels": ["Oxidizer mass mₒₓ", "Fuel mass m_f"],
        "units": ["kg", "kg"],
    },
    {
        "id": "propellant-flows",
        "indices": [2, 3],
        "labels": ["Oxidizer flow qₒₓ", "Fuel flow q_f"],
        "units": ["kg/s", "kg/s"],
    },
]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt_number(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.6g}"
    return esc(value)


def draw_box_tube_svg(
    title: str,
    plane: figures.Projection,
    tubes: list[dict[str, Any]],
    plan: list[list[float]],
    replay: list[list[float]],
    compact: bool = False,
) -> str:
    """Plot authored outer boxes with the plan and observed replay in one projection."""
    i, j = plane["indices"]
    stages = [stage for tube in tubes for stage in tube.get("stages", [])]
    xs = [float(row[key][index]) for row in stages for key, index in (("lower", i), ("upper", i))]
    ys = [float(row[key][index]) for row in stages for key, index in (("lower", j), ("upper", j))]
    xs += [float(point[i]) for point in plan] + [float(point[i]) for point in replay]
    ys += [float(point[j]) for point in plan] + [float(point[j]) for point in replay]
    x0, x1 = figures.limits(xs)
    y0, y1 = figures.limits(ys)
    if compact:
        width, height = 620, 500
        left, right, top, bottom = 145, 22, 82, 155
        font_size, title_size, axis_size = 9, 19, 14
        legend_y, x_label_y = height - 55, height - 120
    else:
        width, height = 1120, 820
        left, right, top, bottom = 110, 60, 100, 150
        font_size, title_size, axis_size = 14, 23, 15
        legend_y, x_label_y = height - 62, height - 35
    pw, ph = width - left - right, height - top - bottom

    def px(x: float) -> float:
        return left + (x - x0) * pw / (x1 - x0)

    def py(y: float) -> float:
        return top + (y1 - y) * ph / (y1 - y0)

    def points(sequence: list[list[float]]) -> str:
        return " ".join(
            f"{px(float(point[i])):.2f},{py(float(point[j])):.2f}" for point in sequence
        )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{esc(title)}</title><rect width="100%" height="100%" fill="white"/>',
        f"<style>text{{font:{font_size}px system-ui,sans-serif;fill:#253047}}.title{{font-size:{title_size}px;font-weight:700}}.axis{{font-size:{axis_size}px;font-weight:600}}</style>",
        f'<text x="{left}" y="42" class="title">{esc(title)}</text>',
        f'<text x="{left}" y="68">Outer fixed-plan trajectory enclosures · box representation</text>',
    ]
    for tick in range(6):
        x = x0 + (x1 - x0) * tick / 5
        y = y0 + (y1 - y0) * tick / 5
        out += [
            f'<line x1="{px(x):.2f}" y1="{top}" x2="{px(x):.2f}" y2="{top + ph}" stroke="#e2e8f0"/>',
            f'<line x1="{left}" y1="{py(y):.2f}" x2="{left + pw}" y2="{py(y):.2f}" stroke="#e2e8f0"/>',
            f'<text x="{px(x):.2f}" y="{top + ph + 22}" text-anchor="middle">{x:.5g}</text>',
            f'<text x="{left - 10}" y="{py(y) + 4:.2f}" text-anchor="end">{y:.5g}</text>',
        ]
    for tube in tubes:
        for row in tube.get("stages", []):
            xlo, xhi = px(float(row["lower"][i])), px(float(row["upper"][i]))
            ylo, yhi = py(float(row["upper"][j])), py(float(row["lower"][j]))
            out.append(
                f'<rect x="{min(xlo, xhi):.2f}" y="{min(ylo, yhi):.2f}" width="{max(abs(xhi - xlo), 1):.2f}" height="{max(abs(yhi - ylo), 1):.2f}" fill="#d97706" fill-opacity=".22" stroke="#b45309" stroke-width="1"/>'
            )
    out += [
        f'<polyline points="{points(plan)}" fill="none" stroke="#dc2626" stroke-width="3"/>',
        f'<polyline points="{points(replay)}" fill="none" stroke="#2563eb" stroke-width="3" stroke-dasharray="8 5"/>',
        f'<text x="{left}" y="{legend_y}">Amber: numerical outer fixed-plan tube · red: selected plan · blue dashed: observed closed-loop replay</text>',
        f'<text x="{left}" y="{x_label_y}" class="axis">{esc(plane["labels"][0])} ({esc(plane["units"][0])})</text>',
        f'<text x="34" y="{top + ph / 2}" class="axis" transform="rotate(-90 34 {top + ph / 2})">{esc(plane["labels"][1])} ({esc(plane["units"][1])})</text></svg>',
    ]
    return "\n".join(out)


def draw_paired_svg_from_plot_data(data: dict[str, Any]) -> str:
    task = data["task_name"]
    representation = data["representation"]
    case = f"{task}-{representation}"
    title = f"{TASK_LABELS[task]} · {representation} · paired projections"
    receipt = data.get("graph_receipt")
    plan = data["selected_plan"]["states"]
    replay = data["observed_closed_loop_replay"]
    final_stage = (
        int(receipt["original_horizon"])
        if receipt
        else len(data["predicted_sets"][0].get("stages", [])) - 1
    )
    panels: list[tuple[str, str]] = []
    for plane in FUEL_PAIRED_PLANES:
        axis_pair = (
            "x1–x2 · propellant masses"
            if plane["indices"] == [0, 1]
            else "x3–x4 · propellant flows"
        )
        panel_title = axis_pair
        if receipt:
            panel = figures.draw_svg(
                panel_title,
                case,
                plane,
                receipt["nodes"],
                plan,
                replay,
                final_stage,
                compact=True,
            )
        else:
            panel = draw_box_tube_svg(
                panel_title, plane, data["predicted_sets"], plan, replay, compact=True
            )
        panels.append((axis_pair, panel))
    return figures.draw_paired_svg(title, panels)


def paired_example_html(
    data: dict[str, Any], provenance: dict[str, Any], contract: dict[str, Any]
) -> str:
    task = data["task_name"]
    representation = data["representation"]
    case = f"{task}-{representation}"
    figure_id = f"{case}-paired"
    title = f"{TASK_LABELS[task]} · {representation} · paired projections"
    task_contract = contract["model"]
    state_order = "(mₒₓ, m_f, qₒₓ, q_f)"
    state_rows = "".join(
        f"<tr><th>{esc(state['name'])}</th><td>{fmt_number(state['initial'])} {esc(state['unit'])}</td>"
        f"<td>[{fmt_number(state['bounds'][0])}, {fmt_number(state['bounds'][1])}] {esc(state['unit'])}</td></tr>"
        for state in task_contract["states"]
    )
    control_rows = "".join(
        f"<tr><th>{esc(control['name'])}</th><td>[{fmt_number(control['bounds'][0])}, {fmt_number(control['bounds'][1])}]</td></tr>"
        for control in task_contract["controls"]
    )
    parameter_rows = ", ".join(
        f"{esc(name)}={fmt_number(value['value'])} {esc(value['unit'])}"
        for name, value in task_contract["parameters"].items()
    )
    equations = "".join(
        f"<li><code>{esc(equation)}</code></li>" for equation in task_contract["equations"]
    )
    objective = contract["objective"]["source_definition"]
    objective_reference = ", ".join(fmt_number(value) for value in objective["terminal_target"])
    objective_weights = ", ".join(fmt_number(value) for value in objective["terminal_weights"])
    terminal_scales = ", ".join(fmt_number(value) for value in objective["terminal_scale"])
    running_scales = ", ".join(fmt_number(value) for value in objective["running_scale"])
    plan_terminal = data["selected_plan"]["states"][-1]
    replay_terminal = data["observed_closed_loop_replay"][-1]
    plan_objective = data["selected_plan"]["total_objective"]
    replay_objective = data["quality_and_resource_evidence"]["nonlinear_physical_objective"][
        "total"
    ]
    task_contract_link = "raw/task-contracts/syn-nl-fuel-01.json"
    plotted_link = f"raw/plotted-data/{case}.json"
    reproduction = (
        "python scripts/reports/render_campaign_paired_projection.py "
        f"--data docs/examples/closed-loop/campaign-2026-11-18/{plotted_link}"
    )
    pair_crumb = (
        ("Examples", "../../index.html"),
        ("Campaign", "index.html"),
        (title, ""),
    )
    parts = [page_start(title, stylesheet_href="../../examples.css", crumbs=pair_crumb)]
    parts.append(
        f"<p><a href='index.html'>Campaign dashboard</a> · <a href='{esc(plotted_link)}'>plotted source data</a> · <a href='{esc(task_contract_link)}'>complete task contract</a> · <a href='{esc(figure_id)}.json'>figure provenance</a></p>"
        f"<p>Individual views: <a href='{esc(case)}-oxidizer.html'>oxidizer mass vs flow</a> · <a href='{esc(case)}-fuel.html'>fuel mass vs flow</a>.</p>"
        f"<object data='{esc(figure_id)}.svg' type='image/svg+xml' aria-label='Propellant mass and flow projections across the same stages'><a href='{esc(figure_id)}.svg'>Open paired SVG</a></object>"
    )
    parts.append(
        "<details><summary>Model, inputs and numerical check</summary>"
        f"<p>State order {state_order}; one controller; zero-order hold over {int(contract['episode']['intervals'])} intervals of {fmt_number(contract['episode']['dt'])} s, ending at {fmt_number(contract['episode']['final_time'])} s.</p>"
        "<table><thead><tr><th>State</th><th>Initial value</th><th>Bounds</th></tr></thead>"
        f"<tbody>{state_rows}</tbody></table><p>Controls</p><table><thead><tr><th>Input</th><th>Bounds</th></tr></thead><tbody>{control_rows}</tbody></table>"
        f"<p>Dynamics:</p><ul>{equations}</ul><p>Parameters: {parameter_rows}.</p>"
        f"<p>Objective: running <code>{esc(objective['running_formula'])}</code> with weight {fmt_number(objective['running_weight'])}, control scales ({running_scales}) and {esc(objective['running_reference'])}; terminal <code>{esc(objective['terminal_formula'])}</code> with target ({objective_reference}), scales ({terminal_scales}) and weights ({objective_weights}). It is a soft objective and creates no final constraint or target set.</p>"
        f"<p>Saved affine-model plan endpoint: ({', '.join(fmt_number(value) for value in plan_terminal)}), objective {fmt_number(plan_objective)}. Observed nonlinear replay endpoint: ({', '.join(fmt_number(value) for value in replay_terminal)}), replay objective {fmt_number(replay_objective)}. Values and full stage histories are in the <a href='{esc(plotted_link)}'>plotted-data record</a>.</p>"
        f"<p>Source: <a href='https://github.com/butahlecoq/controlled-systems-lab/commit/{esc(provenance['source_commit'])}'>campaign/model commit</a>; renderer: <a href='https://github.com/butahlecoq/controlled-systems-lab/commit/{esc(provenance['renderer_source_commit'])}'>figure generator commit</a>.</p>"
        f"<p>Recreate this figure from its saved data:</p><pre><code>{esc(reproduction)}</code></pre></details>"
    )
    if data.get("graph_receipt"):
        reading_note = (
            "Retained finite-action graph nodes and backward-viable nodes are shown over stages. "
            "Graph search coverage is incomplete; the points do not define continuous reachable-set boundaries. "
            "Purple marks are terminal-stage graph nodes, not a terminal set."
        )
    else:
        reading_note = (
            "Amber regions are numerical outer enclosures of the selected fixed plan, not the full reachable set. "
            "This box view has no finite-graph marks; search coverage is not applicable."
        )
    parts.append(
        "<aside class='notice'><h2>Reading the paired projections</h2>"
        "<p>The left panel plots oxidizer mass against fuel mass (x1–x2); the right plots oxidizer flow against fuel flow (x3–x4). Both panels show the same attempt and stages. "
        + esc(reading_note)
        + " The red trace is the selected affine-model plan; the blue dashed trace is the observed nonlinear replay. The soft objective defines no terminal set.</p></aside>"
    )
    parts.append(page_end())
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument(
        "--outcomes",
        type=Path,
        required=True,
        help="full-profile runner output root containing attempt records",
    )
    parser.add_argument(
        "--targeted-reruns",
        type=Path,
        required=True,
        help="supplemental compatible-profile rerun root",
    )
    parser.add_argument("--archive-manifest", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/examples/closed-loop/campaign-2026-11-18"
    )
    args = parser.parse_args()

    renderer_source_commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()

    freeze = read_json(args.freeze)
    coverage = read_json(args.coverage)
    outcomes = args.outcomes.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "raw").mkdir(exist_ok=True)
    (args.output / "raw/plotted-data").mkdir(exist_ok=True)

    by_cell = {(cell["task_name"], cell["graph_id"]): cell for cell in coverage["cells"]}
    selected: list[dict[str, Any]] = []
    for graph in freeze["graphs"]:
        controller = graph["controller"]
        if controller.get("adapter") != "native_graph_policy":
            continue
        representation = controller.get("factory_options", {}).get("representation")
        cell = by_cell[(graph["task_name"], graph["graph_id"])]
        complete = next(
            (row for row in reversed(cell["attempts"]) if row["category"] == "complete"), None
        )
        if complete is None:
            continue
        selected.append(
            {
                "graph": graph,
                "representation": representation,
                "attempt": complete,
                "task": graph["task_name"],
            }
        )

    expected = {
        (task, rep)
        for task in TASK_LABELS
        for rep in ("box", "exact-polytope", "zonotope", "parallelotope", "ellipsoid")
    }
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(
        selected, key=lambda item: (item["task"], item["representation"], item["graph"]["graph_id"])
    ):
        key = (row["task"], row["representation"])
        if key not in chosen:
            stage_path = outcomes / Path(row["attempt"]["path"]).parent / "stage-000.json"
            bridge = read_json(stage_path)["query_receipt"]["bridge_response"]
            # Prefer the graph-composition receipt. The box controller emits a
            # fixed-plan outer tube instead, which is rendered with its own label.
            row["figure_kind"] = "graph" if "graph_receipt" in bridge else "box-tube"
            if row["figure_kind"] == "graph" or row["representation"] == "box":
                chosen[key] = row
    missing = expected - chosen.keys()
    if missing:
        raise ValueError(f"no completed native graph for combinations: {sorted(missing)}")

    cards: dict[str, list[str]] = defaultdict(list)
    quality_rows: list[str] = []
    for (task, representation), row in sorted(chosen.items()):
        relative = row["attempt"]["path"]
        attempt_dir = outcomes / Path(relative).parent
        stage = read_json(attempt_dir / "stage-000.json")
        attempt = read_json(attempt_dir / "attempt.json")
        response = stage["query_receipt"]["bridge_response"]
        plan = response["selected_plan"]["states"]
        replay = attempt["physical_states"]
        objective = attempt.get("physical_objective", {})
        observed = attempt.get("resource_limits", {}).get("observed", {})
        action_profile = row["graph"]["action_profile_id"]
        case = f"{task}-{representation}"
        figure_link = (
            f"{case}-paired.html"
            if task == "syn-nl-fuel-01"
            else f"{case}-{PLANES[task][0]['id']}.html"
        )
        worker_rss_mib = observed.get("worker_max_rss_kib")
        rss_value = (
            fmt_number(worker_rss_mib / 1024)
            if isinstance(worker_rss_mib, (int, float))
            else "not recorded"
        )
        quality_rows.append(
            f"<tr><th>{esc(TASK_LABELS[task])}</th><td><a href='{esc(figure_link)}'>{esc(representation)}</a></td>"
            f"<td><code>{esc(action_profile)}</code></td>"
            f"<td>{fmt_number(response['selected_plan'].get('total_objective', 'not recorded'))}</td>"
            f"<td>{fmt_number(objective.get('total', 'not recorded'))}</td>"
            f"<td>{fmt_number(attempt.get('completed_holds', 'not recorded'))}</td>"
            f"<td>{fmt_number(attempt.get('end_to_end', {}).get('worker_wall_seconds', 'not recorded'))}</td>"
            f"<td>{fmt_number(observed.get('worker_cpu_seconds', 'not recorded'))}</td>"
            f"<td>{rss_value}</td><td><a href='raw/plotted-data/{esc(case)}.json'>saved run data</a></td></tr>"
        )
        receipt = response.get("graph_receipt")
        final_stage = (
            int(receipt["original_horizon"])
            if receipt
            else len(response.get("predicted_sets", [{}])[0].get("stages", [])) - 1
        )
        task_label = TASK_LABELS[task]
        plotted = {
            "schema": "csl.closed-loop-campaign-plotted-data/1",
            "source_commit": freeze["source_commit"],
            "task_name": task,
            "graph_id": row["graph"]["graph_id"],
            "representation": representation,
            "action_profile_id": action_profile,
            "attempt_id": row["attempt"]["attempt_id"],
            "graph_receipt": receipt,
            "predicted_sets": response.get("predicted_sets", []),
            "selected_plan": response["selected_plan"],
            "observed_closed_loop_replay": replay,
            "quality_and_resource_evidence": {
                "nonlinear_physical_objective": objective,
                "completed_holds": attempt.get("completed_holds"),
                "worker_wall_seconds": attempt.get("end_to_end", {}).get("worker_wall_seconds"),
                "worker_cpu_seconds": observed.get("worker_cpu_seconds"),
                "worker_max_rss_kib": observed.get("worker_max_rss_kib"),
                "limit_usage": attempt.get("resolved_graph", {})
                .get("controller", {})
                .get("limit_usage", {}),
                "resource_limits": attempt.get("resource_limits", {}),
            },
        }
        plot_path = args.output / "raw/plotted-data" / f"{case}.json"
        plot_path.write_text(json.dumps(plotted, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        for plane in PLANES[task]:
            stem = f"{task}-{representation}-{plane['id']}"
            title = f"{task_label} · {representation} · {plane['id']} projection"
            if receipt:
                svg = figures.draw_svg(
                    title, case, plane, receipt["nodes"], plan, replay, final_stage
                )
                figure_note = "Retained finite-action states and backward viability are shown; points do not define a continuous reachable-set boundary."
            else:
                svg = draw_box_tube_svg(title, plane, response["predicted_sets"], plan, replay)
                figure_note = "The amber set is an outer enclosure of one selected fixed plan, not the full reachable set."
            (args.output / f"{stem}.svg").write_text(svg + "\n", encoding="utf-8")
            description = (
                f"{response.get('representation', representation)} · controller {row['graph']['controller']['id']} · "
                f"attempt {row['attempt']['attempt_id']} · graph {row['graph']['graph_id']}"
            )
            crumb = (("Examples", "../../index.html"), ("Campaign", "index.html"), (title, ""))
            page = [page_start(title, stylesheet_href="../../examples.css", crumbs=crumb)]
            page.append(
                f"<p><a href='index.html'>Campaign dashboard</a> · <a href='raw/plotted-data/{esc(case)}.json'>Plotted source data</a></p><p>{esc(description)}</p>"
            )
            page.append(
                f"<object data='{esc(stem)}.svg' type='image/svg+xml'><a href='{esc(stem)}.svg'>Open SVG</a></object>"
            )
            page.append(
                f"<aside class='notice'><h2>Reading this projection</h2><p>{esc(figure_note)} The selected plan comes from the affine prediction model; the blue dashed trace replays the original nonlinear plant under applied controls. Search coverage is incomplete and optimality is limited to the retained graph where graph search is used.</p></aside>"
            )
            page.append(page_end())
            (args.output / f"{stem}.html").write_text("".join(page), encoding="utf-8")
            if task != "syn-nl-fuel-01":
                cards[task].append(
                    f"<li><a href='{esc(stem)}.html'><img loading='lazy' src='{esc(stem)}.svg' alt='{esc(title)}'><strong>{esc(representation)} · {esc(plane['id'])}</strong></a></li>"
                )

        if task == "syn-nl-fuel-01":
            paired_stem = f"{case}-paired"
            paired_title = f"{task_label} · {representation} · paired projections"
            paired_svg = draw_paired_svg_from_plot_data(plotted)
            paired_svg_path = args.output / f"{paired_stem}.svg"
            paired_svg_path.write_text(paired_svg + "\n", encoding="utf-8")
            pair_record = {
                "schema": "csl.closed-loop-paired-projection-figure/1",
                "figure_id": paired_stem,
                "source_commit": freeze["source_commit"],
                "renderer_source_commit": renderer_source_commit,
                "task_name": task,
                "graph_id": row["graph"]["graph_id"],
                "attempt_id": row["attempt"]["attempt_id"],
                "plotted_data": f"raw/plotted-data/{case}.json",
                "plotted_data_sha256": hashlib.sha256(plot_path.read_bytes()).hexdigest(),
                "svg_sha256": hashlib.sha256(paired_svg_path.read_bytes()).hexdigest(),
                "stage_count": final_stage + 1,
                "search_coverage": receipt.get("search_coverage") if receipt else "not-applicable",
                "projections": FUEL_PAIRED_PLANES,
                "terminal_condition": "soft objective reference; no terminal constraint or final set",
            }
            (args.output / f"{paired_stem}.json").write_text(
                json.dumps(pair_record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            contract = read_json(ROOT / "docs/contracts/closed-loop/syn-nl-fuel-01.json")
            paired_html = paired_example_html(plotted, pair_record, contract)
            (args.output / f"{paired_stem}.html").write_text(paired_html, encoding="utf-8")
            cards[task].append(
                f"<li><a href='{esc(paired_stem)}.html'><img loading='lazy' src='{esc(paired_stem)}.svg' alt='{esc(paired_title)}'><strong>{esc(representation)} · masses + flows</strong></a></li>"
            )

    # Keep the complete machine-readable disposition and its provenance adjacent to the page.
    raw_files = {
        "raw/coverage.json": args.coverage.read_bytes(),
        "raw/freeze.json": args.freeze.read_bytes(),
        "raw/campaign-events.jsonl": (outcomes / "campaign-events.jsonl").read_bytes(),
        "raw/targeted-reruns-summary.json": (args.targeted_reruns / "summary.json").read_bytes(),
        "raw/targeted-rerun-events.jsonl": (
            args.targeted_reruns / "targeted-rerun-events.jsonl"
        ).read_bytes(),
        "raw/archive-manifest.json": args.archive_manifest.read_bytes(),
    }
    contracts: dict[str, dict[str, Any]] = {}
    for task in TASK_LABELS:
        contract_path = ROOT / "docs/contracts/closed-loop" / f"{task}.json"
        relative = f"raw/task-contracts/{task}.json"
        content = contract_path.read_bytes()
        raw_files[relative] = content
        contracts[task] = json.loads(content)
    for name, content in raw_files.items():
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        (path.with_suffix(path.suffix + ".sha256")).write_text(
            f"{hashlib.sha256(content).hexdigest()}  {path.name}\n", encoding="utf-8"
        )
    per_task: dict[str, Counter[str]] = defaultdict(Counter)
    for cell in coverage["cells"]:
        per_task[cell["task_name"]][
            cell["attempts"][-1]["category"] if cell["attempts"] else "pending"
        ] += 1
    all_statuses = sorted({status for counts in per_task.values() for status in counts})
    table_rows = "".join(
        "<tr><th>"
        + esc(TASK_LABELS[task])
        + "</th><td>"
        + str(sum(counts.values()))
        + "</td>"
        + "".join(f"<td>{counts.get(status, 0)}</td>" for status in all_statuses)
        + "</tr>"
        for task, counts in sorted(per_task.items())
    )
    table_head = "".join(f"<th>{esc(status)}</th>" for status in all_statuses)
    model_rows = []
    for task, contract in sorted(contracts.items()):
        model = contract["model"]
        episode = contract["episode"]
        finite = contract["control_domains"]["finite"]["actions"]
        continuous = contract["control_domains"]["continuous"]
        continuous_bounds = " × ".join(
            f"[{lower}, {upper}]" for lower, upper in continuous["bounds"]
        )
        model_rows.append(
            f"<tr><th>{esc(TASK_LABELS[task])}</th><td>{len(model['states'])} · {esc(model['model_id'])}</td>"
            f"<td>{episode['dt']} × {episode['intervals']} {esc(episode['time_unit'])}</td>"
            f"<td>{len(finite)} catalog actions</td><td>{esc(continuous_bounds)}</td>"
            f"<td>{esc(contract['objective']['kind'])}</td><td>{esc(contract['terminal_condition']['kind'])}</td>"
            f"<td>{esc(contract['prediction']['affine_model_id'])}</td>"
            f"<td>{esc(contract['prediction']['plant'])} · {esc(episode['execution']['method'])}</td>"
            f"<td>{episode['closed_loop']['players']} · {esc(episode['closed_loop']['observation'])}</td>"
            f"<td><a href='raw/task-contracts/{esc(task)}.json'>contract</a></td></tr>"
        )
    native_representation_counts: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for graph in freeze["graphs"]:
        controller = graph["controller"]
        if controller.get("adapter") != "native_graph_policy":
            continue
        representation = controller.get("factory_options", {}).get("representation")
        cell = by_cell[(graph["task_name"], graph["graph_id"])]
        outcome = cell["attempts"][-1]["category"] if cell["attempts"] else "pending"
        native_representation_counts[
            (graph["task_name"], graph["action_profile_id"], representation)
        ][outcome] += 1
    representation_rows = []
    for (task, action_profile, representation), counts in sorted(
        native_representation_counts.items()
    ):
        total = sum(counts.values())
        representation_rows.append(
            f"<tr><th>{esc(TASK_LABELS[task])}</th><td>{esc(representation)}</td>"
            f"<td>{esc(action_profile)}</td><td>{total}</td>"
            f"<td>{counts.get('complete', 0)}</td><td>{counts.get('failed', 0)}</td>"
            f"<td>{counts.get('unsupported', 0)}</td><td>{counts.get('inconclusive', 0)}</td>"
            f"<td>{counts.get('pending', 0)}</td></tr>"
        )
    role_specs = (
        ("representation", "Set representation"),
        ("control_optimizer", "Control optimizer"),
        ("reachable_set_method", "Reachable-set method"),
        ("vertex_lp", "Vertex LP"),
        ("hull_provider", "Hull provider"),
        ("converter", "V↔H converter"),
        ("set_reducer", "Set reducer"),
        ("terminal_solver", "Terminal solver"),
        ("bellman_solver", "Bellman solver"),
        ("geometry_checker", "Geometry checker"),
    )
    role_rows = []
    for role, label in role_specs:
        bound = 0
        explicitly_unused = 0
        declared_not_consumed = 0
        identities: set[str] = set()
        explicitly_inactive = 0
        for graph in freeze["graphs"]:
            binding = graph.get("role_bindings", {})
            inactive = graph.get("inactive_roles", {})
            explicitly_inactive += role in inactive
            if role not in binding:
                continue
            bound += 1
            value = binding[role]
            if value == "not_used":
                explicitly_unused += 1
            elif isinstance(value, dict) and "not consumed" in str(value.get("status", "")).lower():
                declared_not_consumed += 1
            elif isinstance(value, dict):
                identity = next(
                    (
                        value[key]
                        for key in ("module_id", "profile_id", "name", "id", "provider", "status")
                        if key in value
                    ),
                    "active binding",
                )
                identities.add(str(identity))
            else:
                identities.add(str(value))
        role_rows.append(
            f"<tr><th>{esc(label)}</th><td>{bound - explicitly_unused - declared_not_consumed}</td><td>{len(identities)}</td>"
            f"<td>{explicitly_unused}</td><td>{declared_not_consumed}</td>"
            f"<td>{len(freeze['graphs']) - bound}</td>"
            f"<td>{explicitly_inactive}</td></tr>"
        )
    limiter_usage: dict[str, Counter[str]] = defaultdict(Counter)
    complete_attempt_count = 0
    for cell in coverage["cells"]:
        if not cell["attempts"] or cell["attempts"][-1]["category"] != "complete":
            continue
        complete_attempt_count += 1
        attempt_path = outcomes / Path(cell["attempts"][-1]["path"]).parent / "attempt.json"
        attempt_data = read_json(attempt_path)
        usage = attempt_data.get("resolved_graph", {}).get("controller", {}).get("limit_usage", {})
        for limit, status in usage.items():
            limiter_usage[limit][str(status)] += 1
    limiter_rows = []
    for limit, statuses in sorted(limiter_usage.items()):
        for status, count in sorted(statuses.items()):
            limiter_rows.append(
                f"<tr><th>{esc(limit)}</th><td>{esc(status.replace('_', ' '))}</td><td>{count}</td>"
                f"<td>{complete_attempt_count - sum(statuses.values())}</td></tr>"
            )
    task_sections = "".join(
        f"<section><h2>{esc(TASK_LABELS[task])}</h2><div class='cards'><ul>{''.join(cards[task])}</ul></div></section>"
        for task in TASK_LABELS
    )
    reconciliation = coverage.get("reconciliation", {})
    archive = read_json(args.archive_manifest)
    graph_outcomes = coverage["outcomes"]["by_graph_outcome"]
    admitted = coverage["outcomes"]["admitted_graphs"]
    attempt_rows = coverage["outcomes"]["attempt_rows"]
    latest_complete = graph_outcomes.get("complete", 0)
    latest_inconclusive = graph_outcomes.get("inconclusive", 0)
    latest_failed = graph_outcomes.get("failed", 0)
    latest_unsupported = graph_outcomes.get("unsupported", 0)
    incomplete_cells = [
        cell
        for cell in coverage["cells"]
        if cell["attempts"] and cell["attempts"][-1]["category"] == "inconclusive"
    ]
    compatible_reruns = sum(
        cell["attempts"][-1].get("compatible_profile_rerun", {}).get("status") == "complete"
        for cell in incomplete_cells
    )
    title = "Closed-loop composition campaign · full profile"
    crumbs = (("Examples", "../../index.html"), ("Campaign evidence", ""))
    release_is_published = archive["release_status"] == "published"
    release_is_immutable = release_is_published and archive.get("release_immutable") is True
    if release_is_immutable:
        release_link_label = "immutable GitHub evidence release"
        release_status_text = (
            "This evidence release is immutable on GitHub; use the recorded SHA-256 hashes "
            "to verify its contents."
        )
    elif release_is_published:
        release_link_label = "published evidence release"
        release_status_text = (
            "The evidence release is published with hashes recorded for verification."
        )
    else:
        release_link_label = "planned release URL"
        release_status_text = "The evidence release is pending publication with this report."
    page = [page_start(title, stylesheet_href="../../examples.css", crumbs=crumbs)]
    page.append(
        f"<header class='notice'><p>Single-player closed-loop · Lotka–Volterra · Earth orbit · fuel transfer</p><h1>Full-profile module composition</h1><p>Every admitted graph was attempted. Failed, unsupported and inconclusive outcomes remain visible below and in the raw coverage record.</p><div class='cards'><ul><li><strong>{admitted}</strong> admitted graph configurations</li><li><strong>{latest_complete}</strong> complete</li><li><strong>{latest_failed}</strong> failed</li><li><strong>{latest_unsupported}</strong> unsupported</li><li><strong>{latest_inconclusive}</strong> inconclusive</li></ul></div><p>{attempt_rows} total attempt records include retries.</p></header>"
    )
    outcomes = coverage["outcomes"]
    page.append(
        f"<section><h2>Exhaustive disposition</h2><div class='scroll'><table><thead><tr><th>Task</th><th>Admitted</th>{table_head}</tr></thead><tbody>{table_rows}</tbody></table></div>"
        f"<p>Candidate ledger: {outcomes['canonical_active_graphs']} canonical active and admitted graphs; {outcomes['attempted_graphs']} attempted; {outcomes['pending_graphs']} pending. The source catalogues contain {outcomes['source_candidates']} composition candidates ({outcomes['by_candidate_status'].get('requestable', 0)} requestable and {outcomes['incompatible_candidates']} incompatible), {outcomes['canonical_catalogue_references']} graph references ({outcomes['duplicate_catalogue_references']} duplicate references), {outcomes['backend_unavailable_candidates']} backend-unavailable candidates and {outcomes['implementation_missing_candidates']} implementation-missing candidates. Full reasons are retained in the coverage record.</p>"
        f"<p>Of the {latest_inconclusive} latest inconclusive full-profile graph outcomes, {compatible_reruns} have completed reruns under a separate compatible profile; those reruns are supplemental, not merged into full-profile totals.</p>"
        "<p><a href='raw/coverage.json'>Download exhaustive graph and attempt coverage</a> · <a href='raw/freeze.json'>Frozen candidate universe</a> · <a href='raw/campaign-events.jsonl'>Full-profile event ledger</a> · <a href='raw/targeted-rerun-events.jsonl'>Compatible-profile rerun events</a> · <a href='raw/archive-manifest.json'>Raw archive manifest</a></p>"
        f"<p>The full attempt tree is a {archive['archive_bytes'] / 1_000_000_000:.2f} GB archive in {len(archive['parts'])} parts. {release_status_text} Download each part in manifest order, concatenate the bytes, and verify the archive SHA-256 before extraction. The <a href='{esc(archive['release_url'])}'>{release_link_label}</a> is recorded in the manifest.</p></section>"
    )
    page.append(
        "<section><h2>Representation outcomes on finite-action profiles</h2>"
        "<p>This table isolates the native finite-action graph profiles by task hash and action catalog. Continuous-action adapters appear in the exhaustive disposition above but are not pooled into these representation counts.</p>"
        f"<div class='scroll'><table><thead><tr><th>Task</th><th>Representation</th><th>Action profile</th><th>Admitted</th><th>Complete</th><th>Failed</th><th>Unsupported</th><th>Inconclusive</th><th>Pending</th></tr></thead><tbody>{''.join(representation_rows)}</tbody></table></div></section>"
    )
    page.append(
        "<section><h2>Representative quality and worker footprint</h2>"
        "<p>One completed graph is shown for each task and representation, using the same task and action profile within each task. The first objective is the first query’s full affine plan; the second is the recorded objective for the applied receding-horizon controls on nonlinear plant replay. Replanning can change later controls, so their difference is not a same-controls affine prediction error. Interpret objective values within a task, not across tasks. Worker wall time, CPU and resident memory are one-run descriptors, not a timing ranking. Worker wall includes in-worker controller work and inline geometry checks; it excludes post-run independent replay, checker processes and rendering. Worker CPU and peak RSS are worker-process only and exclude bridge subprocesses.</p>"
        f"<div class='scroll'><table><thead><tr><th>Task</th><th>Representation</th><th>Action profile</th><th>Affine-plan objective</th><th>Nonlinear replay objective</th><th>Holds</th><th>Worker wall (s)</th><th>Worker CPU (s)</th><th>Worker peak RSS (MiB)</th><th>Data</th></tr></thead><tbody>{''.join(quality_rows)}</tbody></table></div></section>"
    )
    page.append(
        "<details><summary>Role participation and limit declarations</summary>"
        "<p>Role counts come from frozen admitted graph bindings. ‘Not used’ is an explicit binding value; ‘declared but not consumed’ records a capability that the selected path did not exercise; ‘not declared’ means the binding contract has no such role. These are separate from missing implementations. Per-graph reasons are in the frozen universe. Limit statuses below are controller declarations in latest complete attempts: ‘used’ means the method consults that budget, not that it reached the cap. A missing status is not treated as zero use.</p>"
        f"<div class='scroll'><table><thead><tr><th>Algorithm role</th><th>Selected/consumed bindings</th><th>Distinct selected identities</th><th>Explicitly not used</th><th>Declared but not consumed</th><th>Not declared</th><th>Explicit inactive-role entries</th></tr></thead><tbody>{''.join(role_rows)}</tbody></table></div>"
        f"<p>Limit declarations are present for {sum(sum(values.values()) for values in limiter_usage.values())} role-limit entries across {complete_attempt_count} latest complete attempts. Fixed-plan profiles explicitly mark graph-search beam/node budgets as not used; graph-search profiles declare those budgets active, without asserting that any cap was hit. Details remain in the individual attempt records.</p>"
        f"<div class='scroll'><table><thead><tr><th>Controller limit</th><th>Recorded status</th><th>Complete attempts</th><th>No status recorded</th></tr></thead><tbody>{''.join(limiter_rows)}</tbody></table></div>"
        "<p>Download <a href='raw/freeze.json'>frozen bindings and inactive-role reasons</a> and <a href='raw/coverage.json'>complete attempt coverage</a>.</p></details>"
    )
    page.append(
        "<section><h2>What is matched, and what differs by environment</h2>"
        "<p>Each module configuration is compared only against other configurations with the same task hash and declared action/problem profile. Across the three tasks, the source models, objectives, physical constraints and control units differ; they are not one shared numerical fixture. All use one player, exact full execution-state observations and first-input zero-order holds, with failure stopping before the next input and no fallback action.</p>"
        f"<div class='scroll'><table><thead><tr><th>Task</th><th>States · nonlinear model</th><th>Step × horizon</th><th>Finite catalog</th><th>Continuous bounds</th><th>Objective</th><th>Terminal condition</th><th>Affine predictor</th><th>Nonlinear execution</th><th>Information pattern</th><th>Contract</th></tr></thead><tbody>{''.join(model_rows)}</tbody></table></div></section>"
    )
    page.append(
        "<section><h2>All-stage sets and trajectories by representation</h2><p>Each representation card uses one completed native graph on that task. Its selected plan is computed with the controller’s affine prediction model; the observed replay is a separate execution of the original nonlinear plant. Fuel includes a paired view: x1–x2 plots oxidizer mass against fuel mass, and x3–x4 plots oxidizer flow against fuel flow, using the same stages and attempt. The graph figures show retained forward/backward-viable nodes, plan, and replay. Box cards show the fixed-plan outer tube rather than a full reachable set.</p></section>"
    )
    page.append(task_sections)
    page.append(
        f"<section><h2>Resource limits, interpretation and provenance</h2><aside class='notice'><p><strong>These are outcome and geometry illustrations, not a performance ranking.</strong> The campaign does not contain the five alternating, tuned repetitions required for comparative timing claims. Complete means the configured run and its configured evidence stages completed; it does not establish global search completeness or globally optimal feedback.</p><p>Search uses beam width 8 and incomplete finite-action coverage. Projected dots are retained graph states, not inferred continuous reachable-set boundaries. Numerical feasibility uses binary64 checks rather than validated arithmetic.</p></aside><p>Shared per-attempt cap: {freeze['resource_profile']['attempt_wall_seconds']} s wall and {freeze['resource_profile']['attempt_cpu_seconds']} s CPU, {freeze['resource_profile']['address_space_bytes'] / (1024**3):.0f} GiB address-space limit, {freeze['resource_profile']['suite_worker_count']} worker and {freeze['resource_profile']['solver_threads']} solver thread. These limits are held common; per-attempt durations remain in the archived evidence and are not used here as a performance comparison.</p><p>Frozen source commit <code>{esc(freeze['source_commit'])}</code>. Coverage refresh method: {esc(reconciliation.get('method', 'verified campaign coverage'))}. New attempt reconciliation and verification limitations are recorded in the coverage JSON.</p></section>"
    )
    page.append(page_end())
    (args.output / "index.html").write_text("".join(page), encoding="utf-8")
    file_hashes = {}
    for path in sorted(args.output.rglob("*")):
        if path.is_file() and path.name not in {
            "provenance-manifest.json",
            "provenance-manifest.json.sha256",
        }:
            file_hashes[path.relative_to(args.output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    manifest = {
        "schema": "csl.closed-loop-campaign-publication/1",
        "frozen_source_commit": freeze["source_commit"],
        "admitted_graphs": admitted,
        "attempt_rows": attempt_rows,
        "latest_graph_outcomes": coverage["outcomes"]["by_graph_outcome"],
        "excluded_incompatible_candidates": coverage["outcomes"]["incompatible_candidates"],
        "coverage_refresh": reconciliation,
        "files_sha256": file_hashes,
    }
    manifest_path = args.output / "provenance-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest_path.with_suffix(".json.sha256").write_text(
        f"{manifest_digest}  {manifest_path.name}\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "figures": sum(map(len, cards.values())),
                "selected_graphs": len(chosen),
                "coverage_source": str(args.coverage),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

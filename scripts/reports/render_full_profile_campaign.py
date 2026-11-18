"""Render the frozen 513-graph closed-loop campaign as an HTML dashboard and figures."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def draw_box_tube_svg(
    title: str,
    plane: figures.Projection,
    tubes: list[dict[str, Any]],
    plan: list[list[float]],
    replay: list[list[float]],
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
    width, height = 1120, 820
    left, right, top, bottom = 110, 60, 100, 150
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
        "<style>text{font:14px system-ui,sans-serif;fill:#253047}.title{font-size:23px;font-weight:700}.axis{font-size:15px;font-weight:600}</style>",
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
        f'<text x="{left}" y="{height - 62}">Amber: numerical outer fixed-plan tube · red: selected plan · blue dashed: observed closed-loop replay</text>',
        f'<text x="{left}" y="{height - 35}" class="axis">{esc(plane["labels"][0])} ({esc(plane["units"][0])})</text>',
        f'<text x="34" y="{top + ph / 2}" class="axis" transform="rotate(-90 34 {top + ph / 2})">{esc(plane["labels"][1])} ({esc(plane["units"][1])})</text></svg>',
    ]
    return "\n".join(out)


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
    for (task, representation), row in sorted(chosen.items()):
        relative = row["attempt"]["path"]
        attempt_dir = outcomes / Path(relative).parent
        stage = read_json(attempt_dir / "stage-000.json")
        attempt = read_json(attempt_dir / "attempt.json")
        response = stage["query_receipt"]["bridge_response"]
        plan = response["selected_plan"]["states"]
        replay = attempt["physical_states"]
        receipt = response.get("graph_receipt")
        final_stage = (
            int(receipt["original_horizon"])
            if receipt
            else len(response.get("predicted_sets", [{}])[0].get("stages", [])) - 1
        )
        case = f"{task}-{representation}"
        task_label = TASK_LABELS[task]
        plotted = {
            "schema": "csl.closed-loop-campaign-plotted-data/1",
            "source_commit": freeze["source_commit"],
            "task_name": task,
            "graph_id": row["graph"]["graph_id"],
            "representation": representation,
            "attempt_id": row["attempt"]["attempt_id"],
            "graph_receipt": receipt,
            "predicted_sets": response.get("predicted_sets", []),
            "selected_plan": response["selected_plan"],
            "observed_closed_loop_replay": replay,
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
                f"<aside class='notice'><h2>Reading this projection</h2><p>{esc(figure_note)} The red line is the selected plan and the blue dashed line is the observed closed-loop replay. Search coverage is incomplete and optimality is limited to the retained graph where graph search is used.</p></aside>"
            )
            page.append(page_end())
            (args.output / f"{stem}.html").write_text("".join(page), encoding="utf-8")
            cards[task].append(
                f"<li><a href='{esc(stem)}.html'><img loading='lazy' src='{esc(stem)}.svg' alt='{esc(title)}'><strong>{esc(representation)} · {esc(plane['id'])}</strong></a></li>"
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
        action_summary = f"{len(finite)} finite actions; continuous bounds {continuous['bounds']}"
        model_rows.append(
            f"<tr><th>{esc(TASK_LABELS[task])}</th><td>{len(model['states'])} · {esc(model['model_id'])}</td>"
            f"<td>{episode['dt']} × {episode['intervals']} {esc(episode['time_unit'])}</td>"
            f"<td>{esc(action_summary)}</td><td>{esc(contract['objective']['kind'])}</td>"
            f"<td>{esc(contract['terminal_condition']['kind'])}</td>"
            f"<td>{episode['closed_loop']['players']} · {esc(episode['closed_loop']['observation'])}</td>"
            f"<td><a href='raw/task-contracts/{esc(task)}.json'>contract</a></td></tr>"
        )
    task_sections = "".join(
        f"<section><h2>{esc(TASK_LABELS[task])}</h2><div class='cards'><ul>{''.join(cards[task])}</ul></div></section>"
        for task in TASK_LABELS
    )
    reconciliation = coverage.get("reconciliation", {})
    archive = read_json(args.archive_manifest)
    title = "Closed-loop composition campaign · full profile"
    crumbs = (("Examples", "../../index.html"), ("Campaign evidence", ""))
    page = [page_start(title, stylesheet_href="../../examples.css", crumbs=crumbs)]
    page.append(
        "<header class='notice'><p>Single-player closed-loop · Lotka–Volterra · Earth orbit · fuel transfer</p><h1>Full-profile module composition</h1><p>Every admitted graph was attempted. Failed, unsupported and inconclusive outcomes remain visible below and in the raw coverage record.</p><div class='cards'><ul><li><strong>513</strong> admitted graph configurations</li><li><strong>516</strong> full-profile attempt records</li><li><strong>483</strong> latest graph outcomes complete</li><li><strong>30</strong> latest graph outcomes inconclusive</li></ul></div></header>"
    )
    page.append(
        f"<section><h2>Disposition by task</h2><div class='scroll'><table><thead><tr><th>Task</th><th>Admitted</th>{table_head}</tr></thead><tbody>{table_rows}</tbody></table></div><p>Twenty additional candidates are incompatible with the current source-index hull dimension contract; their full reasons and module settings are in the coverage record.</p><p>Among the 30 inconclusive full-profile graph outcomes, 15 fixed-tail attempts have completed reruns under a separate compatible profile; 7 failed before returning a structured controller response, and 8 were refused or unsupported, including independent hull-checker rejections. The 15 reruns are supplemental evidence and are not merged into full-profile totals.</p><p><a href='raw/coverage.json'>Download exhaustive graph and attempt coverage</a> · <a href='raw/freeze.json'>Frozen candidate universe</a> · <a href='raw/campaign-events.jsonl'>Full-profile event ledger</a> · <a href='raw/targeted-rerun-events.jsonl'>Compatible-profile rerun events (15)</a> · <a href='raw/archive-manifest.json'>Raw archive manifest</a></p><p>The full attempt tree is a 4.77 GB archive in 48 parts. <a href='{esc(archive['release_url'])}'>Open the immutable archive release</a>. Download each part in manifest order, concatenate the bytes, and verify the archive SHA-256 before extraction.</p></section>"
    )
    page.append(
        "<section><h2>What is matched, and what differs by environment</h2>"
        "<p>Each module configuration is compared only against other configurations with the same task hash and declared action/problem profile. Across the three tasks, the source models, objectives, physical constraints and control units differ; they are not one shared numerical fixture. All use one player, exact full execution-state observations and first-input zero-order holds, with failure stopping before the next input and no fallback action.</p>"
        f"<div class='scroll'><table><thead><tr><th>Task</th><th>States · model</th><th>Step × horizon</th><th>Action domains</th><th>Objective</th><th>Terminal condition</th><th>Information pattern</th><th>Source</th></tr></thead><tbody>{''.join(model_rows)}</tbody></table></div></section>"
    )
    page.append(
        "<section><h2>All-stage sets and trajectories by representation</h2><p>Each representation card uses one completed native graph on that task. Fuel projections follow the authored state order: oxidizer (mass, flow) and fuel (mass, flow). The figures combine the initial graph query’s retained forward/backward-viable nodes, its selected plan, and the observed closed-loop replay.</p></section>"
    )
    page.append(task_sections)
    admitted = coverage["outcomes"]["admitted_graphs"]
    attempt_rows = coverage["outcomes"]["attempt_rows"]
    page.append(
        f"<section><h2>Interpretation and provenance</h2><aside class='notice'><p><strong>These are outcome and geometry illustrations, not a performance ranking.</strong> The campaign does not contain the five alternating, tuned repetitions required for comparative timing claims. Complete means the configured run and its configured evidence stages completed; it does not establish global search completeness or globally optimal feedback.</p><p>Search uses beam width 8 and incomplete finite-action coverage. Projected dots are retained graph states, not inferred continuous reachable-set boundaries. Numerical feasibility uses binary64 checks rather than validated arithmetic.</p></aside><p>Frozen source commit <code>{esc(freeze['source_commit'])}</code>. Coverage refresh method: {esc(reconciliation.get('method', 'verified campaign coverage'))}. New attempt reconciliation and verification limitations are recorded in the coverage JSON.</p></section>"
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

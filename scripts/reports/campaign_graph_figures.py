"""Publish point-level figures for the retained finite-action campaign graphs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, TypedDict

from site_design import page_end, page_start

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = "closed-loop-composition-campaign-v2"
RELEASE_TAG = "evidence/closed-loop-campaign-v2-9140e2a6-20261115"
RELEASE_BASE = (
    "https://github.com/butahlecoq/controlled-systems-lab/releases/download/" + RELEASE_TAG
)


class Projection(TypedDict):
    id: str
    indices: list[int]
    labels: list[str]
    units: list[str]


class Case(TypedDict):
    task: str
    attempt: str
    archive: str
    time_step: float
    planes: list[Projection]


CASES: dict[str, Case] = {
    "syn-nl-lv-01": {
        "task": "syn-nl-lv-01/continuous-receding/1",
        "attempt": "syn-nl-lv-01-20261115T112425Z-8de524f1",
        "archive": "lotka-results.tar.zst",
        "time_step": 0.1,
        "planes": [
            {
                "id": "lotka",
                "indices": [0, 1],
                "labels": ["Prey P", "Predator R"],
                "units": ["thousand individuals", "thousand individuals"],
            },
        ],
    },
    "earth-orbit": {
        "task": "env717-earth-orbit/continuous-receding/1",
        "attempt": "earth-orbit-20261115T110111Z-4475ae9f",
        "archive": "earth-orbit-results.tar.zst",
        "time_step": 100.0,
        "planes": [
            {
                "id": "orbit",
                "indices": [0, 3],
                "labels": ["Radius r", "Angular rate ω"],
                "units": ["km", "rad/s"],
            },
        ],
    },
    "syn-nl-fuel-01": {
        "task": "syn-nl-fuel-01/continuous-receding/1",
        "attempt": "syn-nl-fuel-01-20261115T110441Z-2ccaccc0",
        "archive": "fuel-results.tar.zst.parts.json",
        "time_step": 0.5,
        "planes": [
            {
                "id": "oxidizer",
                "indices": [2, 0],
                "labels": ["Oxidizer flow qₒₓ", "Oxidizer mass mₒₓ"],
                "units": ["kg/s", "kg"],
            },
            {
                "id": "fuel",
                "indices": [3, 1],
                "labels": ["Fuel flow q_f", "Fuel mass m_f"],
                "units": ["kg/s", "kg"],
            },
        ],
    },
}

MISSING_LAYERS = [
    "complete unpruned action reachability (search coverage is incomplete; beam width is 8)",
    "continuous-control reachable-set boundaries; points are retained graph states, with no convex hull drawn",
    "validated-arithmetic certificates for predecessor and membership checks",
    "globally optimal causal feedback policy",
]


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def number(value: float) -> str:
    return f"{value:.6g}"


def xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


def color(stage: int, final_stage: int) -> str:
    hue = 205.0 - 70.0 * (stage / max(1, final_stage))
    return f"hsl({hue:.1f} 66% 47%)"


def limits(values: list[float]) -> tuple[float, float]:
    low, high = min(values), max(values)
    span = high - low
    if span <= max(abs(low), abs(high), 1.0) * 1e-12:
        span = max(abs(low), 1.0)
        low -= span * 0.1
        high += span * 0.1
    pad = 0.08 * span
    return low - pad, high + pad


def ticks(low: float, high: float, count: int = 6) -> list[float]:
    step = (high - low) / (count - 1)
    return [low + i * step for i in range(count)]


def draw_svg(
    title: str,
    case_id: str,
    plane: Projection,
    nodes: list[dict[str, Any]],
    plan: list[list[float]],
    replay: list[list[float]],
    final_stage: int,
    compact: bool = False,
) -> str:
    if compact:
        width, height = 620, 500
        left, right, top, bottom = 145, 20, 82, 155
        title_size, note_size, tick_size, axis_size, legend_size, small_size = (
            20,
            12,
            11,
            14,
            11,
            10,
        )
        axis_label_y, legend_rows, small_y = height - 120, (height - 55, height - 34), height - 10
        secondary_legend_x = left + 250
    else:
        width, height = 1240, 900
        left, right, top, bottom = 145, 80, 140, 250
        title_size, note_size, tick_size, axis_size, legend_size, small_size = (
            25,
            14,
            12,
            16,
            14,
            12,
        )
        axis_label_y, legend_rows, small_y = height - 170, (height - 100, height - 65), height - 25
        secondary_legend_x = left + 470
    plot_width, plot_height = width - left - right, height - top - bottom
    i, j = plane["indices"]
    points = [(float(n["state"][i]), float(n["state"][j])) for n in nodes]
    points += [(float(s[i]), float(s[j])) for s in plan]
    points += [(float(s[i]), float(s[j])) for s in replay]
    x0, x1 = limits([p[0] for p in points])
    y0, y1 = limits([p[1] for p in points])

    def px(x: float) -> float:
        return left + (x - x0) * plot_width / (x1 - x0)

    def py(y: float) -> float:
        return top + (y1 - y) * plot_height / (y1 - y0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{xml(title)}</title>',
        '<desc id="desc">All retained finite-action graph nodes over all stages, backward-viable nodes, selected retained-graph plan and observed closed-loop replay.</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{left}" y="43" class="title">{xml(title)}</text>',
        f'<text x="{left}" y="75" class="note">Retained graph only · beam width 8 · search coverage incomplete · no convex hull inferred</text>',
        f"<style>text{{font-family:system-ui,sans-serif;fill:#253047}}.title{{font-size:{title_size}px;font-weight:700}}.note{{font-size:{note_size}px;fill:#8b2d24}}.tick{{font-size:{tick_size}px;fill:#475569}}.axis{{font-size:{axis_size}px;font-weight:600}}.legend{{font-size:{legend_size}px}}.small{{font-size:{small_size}px;fill:#475569}}</style>",
    ]
    for x in ticks(x0, x1):
        X = px(x)
        parts.append(
            f'<line x1="{X:.2f}" y1="{top}" x2="{X:.2f}" y2="{top + plot_height}" stroke="#e2e8f0"/>'
        )
        parts.append(
            f'<text x="{X:.2f}" y="{top + plot_height + (18 if compact else 25)}" class="tick" text-anchor="middle">{xml(number(x))}</text>'
        )
    for y in ticks(y0, y1):
        Y = py(y)
        parts.append(
            f'<line x1="{left}" y1="{Y:.2f}" x2="{left + plot_width}" y2="{Y:.2f}" stroke="#e2e8f0"/>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{Y + 4:.2f}" class="tick" text-anchor="end">{xml(number(y))}</text>'
        )
    parts.append(
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#64748b"/>'
    )

    for node, (x, y) in zip(
        nodes,
        [(float(n["state"][i]), float(n["state"][j])) for n in nodes],
        strict=True,
    ):
        stage = int(node["absolute_stage"])
        tip = f"stage {stage}; node {node['node_id']}; state {node['state']}; backward viable {node.get('backward_viable')}"
        parts.append(
            f'<circle cx="{px(x):.2f}" cy="{py(y):.2f}" r="4.2" fill="{color(stage, final_stage)}" fill-opacity="0.43"><title>{xml(tip)}</title></circle>'
        )
        if node.get("backward_viable") is True:
            parts.append(
                f'<circle cx="{px(x):.2f}" cy="{py(y):.2f}" r="7.2" fill="none" stroke="#d97706" stroke-width="2.2"><title>{xml("Retained forward node with backward-viable continuation: " + tip)}</title></circle>'
            )

    def polyline(
        states: list[list[float]], stroke: str, dash: str = "", width_px: float = 3.0
    ) -> None:
        if len(states) < 2:
            return
        coords = " ".join(f"{px(float(s[i])):.2f},{py(float(s[j])):.2f}" for s in states)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{stroke}" stroke-width="{width_px}" stroke-linejoin="round" stroke-linecap="round"{dash_attr}/>'
        )

    polyline(replay, "#2563eb", "9 6", 3.0)
    polyline(plan, "#dc2626", "", 4.0)
    for k, state in enumerate(plan):
        parts.append(
            f'<circle cx="{px(float(state[i])):.2f}" cy="{py(float(state[j])):.2f}" r="3.1" fill="#dc2626"><title>selected retained-graph plan stage {k}</title></circle>'
        )
    if nodes:
        first = next((n for n in nodes if int(n["absolute_stage"]) == 0), None)
        terminal_nodes = [n for n in nodes if int(n["absolute_stage"]) == final_stage]
        if first:
            x, y = float(first["state"][i]), float(first["state"][j])
            parts.append(
                f'<path d="M {px(x):.2f} {py(y) - 11:.2f} L {px(x) + 3:.2f} {py(y) - 3:.2f} L {px(x) + 11:.2f} {py(y) - 3:.2f} L {px(x) + 5:.2f} {py(y) + 2:.2f} L {px(x) + 7:.2f} {py(y) + 10:.2f} L {px(x):.2f} {py(y) + 5:.2f} L {px(x) - 7:.2f} {py(y) + 10:.2f} L {px(x) - 5:.2f} {py(y) + 2:.2f} L {px(x) - 11:.2f} {py(y) - 3:.2f} L {px(x) - 3:.2f} {py(y) - 3:.2f} Z" fill="#15803d" stroke="#fff" stroke-width="1.2"><title>initial graph state</title></path>'
            )
        for n in terminal_nodes:
            x, y = float(n["state"][i]), float(n["state"][j])
            parts.append(
                f'<path d="M {px(x):.2f} {py(y) - 7:.2f} L {px(x) + 7:.2f} {py(y):.2f} L {px(x):.2f} {py(y) + 7:.2f} L {px(x) - 7:.2f} {py(y):.2f} Z" fill="#7c3aed" fill-opacity="0.8"><title>terminal-stage retained node {n["node_id"]}</title></path>'
            )

    parts.append(
        f'<text x="{left + plot_width / 2:.2f}" y="{axis_label_y}" class="axis" text-anchor="middle">{xml(plane["labels"][0])} ({xml(plane["units"][0])})</text>'
    )
    parts.append(
        f'<text x="34" y="{top + plot_height / 2:.2f}" class="axis" text-anchor="middle" transform="rotate(-90 34 {top + plot_height / 2:.2f})">{xml(plane["labels"][1])} ({xml(plane["units"][1])})</text>'
    )
    if compact:
        entries = [
            (left, legend_rows[0], "#64748b", "Retained graph nodes"),
            (secondary_legend_x, legend_rows[0], "#d97706", "Backward-viable nodes"),
            (left, legend_rows[1], "#dc2626", "Selected plan"),
            (secondary_legend_x, legend_rows[1], "#2563eb", "Observed replay"),
        ]
    else:
        entries = [
            (left, legend_rows[0], "#64748b", "Retained forward nodes F_ret[k]"),
            (
                secondary_legend_x,
                legend_rows[0],
                "#d97706",
                "Backward-viable nodes F_ret[k] ∩ B_ret[k]",
            ),
            (left, legend_rows[1], "#dc2626", "Selected plan (retained-graph optimum)"),
            (secondary_legend_x, legend_rows[1], "#2563eb", "Observed closed-loop replay"),
        ]
    for x, y, c, label in entries:
        parts.append(f'<circle cx="{x}" cy="{y - 5}" r="5" fill="{c}"/>')
        parts.append(f'<text x="{x + 12}" y="{y}" class="legend">{xml(label)}</text>')
    parts.append(
        f'<text x="{left}" y="{small_y}" class="small">Stage color: k=0 to k={final_stage}. Purple diamonds: terminal nodes. Green star: initial state.</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def draw_paired_svg(title: str, panels: list[tuple[str, str]]) -> str:
    """Place two existing projection plots side by side in one accessible SVG."""
    if len(panels) != 2:
        raise ValueError("a paired projection figure requires exactly two panels")

    width, height = 2560, 1000
    panel_width = width // 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="paired-title paired-desc">',
        f'<title id="paired-title">{xml(title)}</title>',
        '<desc id="paired-desc">Two synchronized projections of the same stages, retained graph, selected plan, and observed replay.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for index, (label, panel) in enumerate(panels):
        clean = panel.strip()
        opening = clean.find(">")
        closing = clean.rfind("</svg>")
        if not clean.startswith("<svg") or opening < 0 or closing <= opening:
            raise ValueError(f"panel {index + 1} is not a complete SVG document")
        view_box = re.search(r'\bviewBox="([^"]+)"', clean[: opening + 1])
        if view_box is None:
            raise ValueError(f"panel {index + 1} has no SVG viewBox")
        content = clean[opening + 1 : closing]
        content = content.replace('id="title"', f'id="panel-{index}-title"')
        content = content.replace('id="desc"', f'id="panel-{index}-desc"')
        x = index * panel_width
        parts.append(
            f'<svg x="{x}" y="0" width="{panel_width}" height="1000" viewBox="{xml(view_box.group(1))}" role="group" aria-label="{xml(label)}">{content}</svg>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def page_html(title: str, svg_name: str, scope: str) -> str:
    crumbs = (("Examples", "../../index.html"), ("Closed-loop", "../index.html"), (title, ""))
    parts = [page_start(title, stylesheet_href="../../examples.css", crumbs=crumbs)]
    parts.append(
        '<p><a href="../../../learn/native-substitution-matrix.html">Learning book · native composition campaign</a></p>'
    )
    parts.append(
        f'<section class="saved-figure"><p>{xml(scope)}</p><object data="{xml(svg_name)}" type="image/svg+xml"><a href="{xml(svg_name)}">Open the SVG figure</a></object></section>'
    )
    parts.append(
        '<aside class="notice"><h2>Interpretation limits</h2><p>The dots are retained finite-action graph states in physical coordinates. Orange rings identify states in the retained graph with a backward-viable continuation. The red line is the selected plan from the first query; the blue dashed line is the observed receding-policy replay. No continuous reachable-set boundary is inferred from these points. The search uses beam width 8 and reports incomplete search coverage, so the plan is optimal only over the retained graph.</p></aside>'
    )
    parts.append(page_end())
    return "".join(parts)


def dashboard_html(coverage: dict[str, Any]) -> str:
    statuses = ("complete", "incorrect", "failed", "timed_out", "unsupported")
    task_rows = []
    for task, categories in coverage["per_task_graph_outcomes"].items():
        task_rows.append(
            f"<tr><th>{xml(task)}</th><td>{sum(categories.values())}</td>"
            + "".join(f"<td>{categories.get(status, 0)}</td>" for status in statuses)
            + "</tr>"
        )
    graph_outcomes = coverage["graph_outcomes"]
    totals = sum(sum(row.values()) for row in coverage["per_task_graph_outcomes"].values())
    figure_cards = []
    for figure_id, label in (
        ("campaign-syn-nl-lv-01-lotka", "Lotka–Volterra"),
        ("campaign-earth-orbit-orbit", "Earth orbit"),
        ("campaign-syn-nl-fuel-01-oxidizer", "Fuel · oxidizer projection"),
        ("campaign-syn-nl-fuel-01-fuel", "Fuel · fuel projection"),
    ):
        figure_cards.append(
            f'<li><a href="../figures/{figure_id}.html">'
            f'<img src="../figures/{figure_id}.svg" alt="All retained graph stages and trajectories for {xml(label)}">'
            f"<strong>{xml(label)}</strong></a></li>"
        )
    archive_links = "".join(
        f'<li><a href="{RELEASE_BASE}/{asset}">{xml(asset)}</a></li>'
        for asset in coverage["archive_assets"]
    )
    title = "Three-task closed-loop composition campaign"
    crumbs = (
        ("Examples", "../../index.html"),
        ("Closed-loop", "../index.html"),
        ("Campaign evidence", ""),
    )
    parts = [page_start(title, stylesheet_href="../../examples.css", crumbs=crumbs)]
    parts.append(
        '<p><a href="../../../learn/native-substitution-matrix.html">Learning book</a> · campaign evidence</p>'
    )
    parts.append(
        f'<header class="notice"><p>Single-player closed-loop · Lotka–Volterra · Earth orbit · fuel transfer</p><h1>Module-composition coverage</h1><p>Every admitted graph has a recorded attempt outcome. The complete graph-by-graph disposition and all raw attempts are available for download.</p><div class="cards"><ul><li><strong>{coverage["candidate_counts"]["admitted_graphs"]}</strong> admitted graphs · {totals} attempted</li><li><strong>{graph_outcomes.get("complete", 0)}</strong> complete runner outcomes</li><li><strong>{sum(graph_outcomes.get(s, 0) for s in statuses[1:])}</strong> non-complete outcomes, with reason records</li></ul></div></header>'
    )
    parts.append(
        f'<section><h2>Outcomes by task</h2><div class="scroll"><table><thead><tr><th>Task</th><th>Admitted</th><th>Complete</th><th>Incorrect</th><th>Failed</th><th>Timed out</th><th>Unsupported</th></tr></thead><tbody>{"".join(task_rows)}</tbody><tfoot><tr><th>Total</th><td>{totals}</td>{"".join(f"<td>{graph_outcomes.get(s, 0)}</td>" for s in statuses)}</tr></tfoot></table></div><p>Fifteen additional inconclusive historical attempt rows are retained separately from final graph outcomes. Twenty source candidates are recorded as incompatible; they are listed in the downloadable coverage JSON.</p><p><a href="coverage.json">Download graph-by-graph coverage JSON ({coverage["candidate_counts"]["admitted_graphs"]} admitted tuples)</a></p></section>'
    )
    parts.append(
        f'<section><h2>All-stage projections and trajectories</h2><div class="cards"><ul>{"".join(figure_cards)}</ul></div><p>Dots show retained finite-action graph states at every stage; the plots separately show backward-viable retained nodes, the selected first-query plan, and observed closed-loop replay. Fuel uses flow-versus-mass projections for oxidizer and fuel.</p></section>'
    )
    parts.append(
        f'<section><h2>Scope and limits</h2><aside class="notice"><p><strong>These are coverage results, not a performance ranking.</strong> There are no five alternating timing repetitions. A graph outcome marked complete means its configured runner completed; it does not imply globally complete search or global optimality.</p><p>The illustrative backward-graph figures report beam width 8 and <code>search_coverage=incomplete</code>. Their dots are retained finite-action states, not continuous reachable-set boundaries; no convex hull is drawn. The selected plan is optimal only over its retained graph, and plant replay is shown separately.</p></aside><p>Source commit <code>{xml(coverage["source_commit"])}</code>. Freeze SHA-256 <code>{xml(coverage["freeze_sha256"])}</code>; complete coverage record SHA-256 <code>{xml(coverage["coverage_record_sha256"])}</code>.</p><p><a href="archive-manifest.json">Archive SHA-256 manifest</a>.</p></section><section><h2>Raw immutable records</h2><p>Compressed tar archives can be extracted into one directory to restore the campaign tree. Verify SHA-256 using the manifest before analysis. The fuel archive is published as deterministic 100 MiB parts because the release connection cannot carry a 1.99 GB stream reliably: download every listed part, concatenate them in numerical order, then verify the reconstructed archive SHA-256 in the manifest.</p><ul>{archive_links}</ul></section>'
    )
    parts.append(page_end())
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/examples/closed-loop/figures")
    parser.add_argument(
        "--figure-index", type=Path, default=ROOT / "docs/examples/closed-loop/figure-index.json"
    )
    parser.add_argument(
        "--coverage-output",
        type=Path,
        default=ROOT / "docs/examples/closed-loop/campaign-v2/coverage.json",
    )
    parser.add_argument(
        "--dashboard-html",
        type=Path,
        default=ROOT / "docs/examples/closed-loop/campaign-v2/index.html",
    )
    args = parser.parse_args()
    campaign_root = args.campaign_root.resolve()
    summary = read_json(campaign_root / "results/campaign-coverage-with-stage-dispositions-v2.json")
    freeze = read_json(campaign_root / "freeze.json")
    expected_outcomes = {
        "complete": 498,
        "failed": 6,
        "incorrect": 5,
        "timed_out": 1,
        "unsupported": 3,
    }
    if summary.get("outcomes", {}).get("by_graph_outcome") != expected_outcomes:
        raise ValueError("campaign graph outcome totals differ from the frozen coverage record")
    if summary.get("candidate_counts", {}).get("admitted_graphs") != 513:
        raise ValueError("campaign admitted graph count differs from the frozen coverage record")
    by_task: dict[str, dict[str, int]] = {}
    for cell in summary["cells"]:
        latest = cell["attempts"][-1]["category"]
        task_counts = by_task.setdefault(cell["task_name"], {})
        task_counts[latest] = task_counts.get(latest, 0) + 1
    if sum(sum(counts.values()) for counts in by_task.values()) != 513:
        raise ValueError("per-task graph outcomes do not reconcile to the admitted universe")
    coverage = {
        "schema": "csl.closed-loop.campaign-coverage-dashboard/1",
        "source_commit": freeze["source_commit"],
        "freeze_sha256": sha256(campaign_root / "freeze.json"),
        "coverage_record": "campaign-coverage-with-stage-dispositions-v2.json",
        "coverage_record_sha256": sha256(
            campaign_root / "results/campaign-coverage-with-stage-dispositions-v2.json"
        ),
        "candidate_counts": summary["candidate_counts"],
        "graph_outcomes": summary["outcomes"]["by_graph_outcome"],
        "attempt_outcomes": summary["outcomes"]["by_attempt_category"],
        "per_task_graph_outcomes": by_task,
        "graph_records": [
            {
                "task_name": cell["task_name"],
                "task_sha256": cell["task_sha256"],
                "graph_id": cell["graph_id"],
                "graph_fingerprint": cell["graph_fingerprint"],
                "outcome": cell["attempts"][-1]["category"],
                "attempts": cell["attempts"],
            }
            for cell in summary["cells"]
        ],
        "excluded_candidates": summary["outcomes"]["excluded_candidates"],
        "profile_followup": summary["profile_followup"],
        "timing_claim": "No comparative speed claim: this campaign run is not an alternating five-repetition comparison.",
        "raw_evidence_release": RELEASE_BASE,
        "archive_assets": [
            "campaign-index.tar.zst",
            "lotka-results.tar.zst",
            "earth-orbit-results.tar.zst",
            "fuel-results.tar.zst.parts.json",
        ],
    }
    args.coverage_output.parent.mkdir(parents=True, exist_ok=True)
    args.coverage_output.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.write_text(dashboard_html(coverage), encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    figure_index = read_json(args.figure_index)
    campaign_figure_ids = {
        f"campaign-{case_id}-{plane['id']}"
        for case_id, case in CASES.items()
        for plane in case["planes"]
    }
    figure_index["figures"] = [
        item for item in figure_index.get("figures", []) if item["id"] not in campaign_figure_ids
    ]
    known = {item["id"] for item in figure_index["figures"]}

    for case_id, case in CASES.items():
        rel = f"results/{case_id}/attempts/{case['attempt']}"
        attempt_path = campaign_root / rel / "attempt.json"
        stage_path = campaign_root / rel / "stage-000.json"
        attempt = read_json(attempt_path)
        stage_record = read_json(stage_path)
        response = stage_record["query_receipt"]["bridge_response"]
        graph = response["graph_receipt"]
        if graph.get("search_coverage") != "incomplete" or graph.get("beam_width") != 8:
            raise ValueError(f"{case_id}: frozen campaign graph semantics changed")
        if attempt.get("overall_status") != "complete":
            raise ValueError(f"{case_id}: selected attempt is not complete")
        if attempt.get("task_id") != case["task"]:
            raise ValueError(f"{case_id}: task identity changed")
        nodes = response["predicted_sets"][0]["nodes"]
        plan = response["selected_plan"]["states"]
        replay = attempt["physical_states"]
        final_stage = max(int(node["absolute_stage"]) for node in nodes)
        if len(plan) != final_stage + 1 or len(replay) != final_stage + 1:
            raise ValueError(f"{case_id}: plan, replay, and node horizons do not agree")
        if any(not isinstance(node.get("state"), list) for node in nodes):
            raise ValueError(f"{case_id}: a graph node has no physical state")
        task_sha = attempt["task_sha256"]

        for plane in case["planes"]:
            figure_id = f"campaign-{case_id}-{plane['id']}"
            base = figure_id.replace("_", "-")
            title = f"{case_id}: retained graph and closed-loop replay ({plane['id']})"
            svg_name, data_name, html_name = (
                f"{base}.svg",
                f"{base}.plotted-data.json",
                f"{base}.html",
            )
            scope = (
                f"Stages k=0,…,{final_stage}; time step Δt={case['time_step']:g}. "
                f"{len(nodes)} retained nodes, {sum(n.get('backward_viable') is True for n in nodes)} backward-viable nodes, "
                f"{len(plan) - 1} planned transitions, and {len(replay) - 1} observed holds."
            )
            (args.output / svg_name).write_text(
                draw_svg(title, case_id, plane, nodes, plan, replay, final_stage), encoding="utf-8"
            )
            relative_attempt = f"reports/{CAMPAIGN}/{rel}/attempt.json"
            relative_stage = f"reports/{CAMPAIGN}/{rel}/stage-000.json"
            data = {
                "schema": "csl.closed-loop.retained-graph-figure/1",
                "figure_id": figure_id,
                "case_id": case_id,
                "task_id": case["task"],
                "task_sha256": task_sha,
                "source_commit": freeze["source_commit"],
                "attempt_id": case["attempt"],
                "attempt_sha256": sha256(attempt_path),
                "first_query_sha256": sha256(stage_path),
                "projection": plane,
                "time_step": case["time_step"],
                "stage_count": final_stage + 1,
                "search_coverage": graph["search_coverage"],
                "beam_width": graph["beam_width"],
                "max_graph_nodes": graph["max_graph_nodes"],
                "optimality_scope": graph["optimality_scope"],
                "source_model_id": graph["source_model_id"],
                "predictor_model_id": graph["predictor_model_id"],
                "retained_nodes": nodes,
                "selected_first_query_plan": plan,
                "observed_closed_loop_replay": replay,
                "record_refs": [
                    {
                        "archive": case["archive"],
                        "member": relative_attempt,
                        "sha256": sha256(attempt_path),
                    },
                    {
                        "archive": case["archive"],
                        "member": relative_stage,
                        "sha256": sha256(stage_path),
                    },
                ],
            }
            (args.output / data_name).write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            (args.output / html_name).write_text(
                page_html(title, svg_name, scope), encoding="utf-8"
            )
            attempt_url = f"{RELEASE_BASE}/{case['archive']}"
            figure_index["figures"].append(
                {
                    "id": figure_id,
                    "availability": "ready",
                    "href": f"examples/closed-loop/figures/{html_name}",
                    "svg_href": f"examples/closed-loop/figures/{svg_name}",
                    "plotted_data_href": f"examples/closed-loop/figures/{data_name}",
                    "title": title,
                    "task_id": case["task"],
                    "task_sha256": task_sha,
                    "geometry_source_commit": freeze["source_commit"],
                    "stage_count": final_stage + 1,
                    "transition_count": final_stage,
                    "time_step": case["time_step"],
                    "timeline_end": final_stage * case["time_step"],
                    "coordinate_transform": {
                        "raw_indices": plane["indices"],
                        "names": plane["labels"],
                        "units": plane["units"],
                        "description": "Physical coordinates; no scaling or convexification applied.",
                        "source_values_are_physical": True,
                        "scale_applied_to_source_values": False,
                    },
                    "layer_scopes": [
                        "retained finite-action graph states F_ret[k] across all stages",
                        "backward-viable retained nodes F_ret[k] ∩ B_ret[k]",
                        "selected retained-graph plan from first query",
                        "observed closed-loop plant replay",
                        "initial state and terminal-stage retained nodes",
                    ],
                    "missing_layers": MISSING_LAYERS,
                    "raw_record_refs": [
                        {
                            "url": attempt_url,
                            "archive_member": relative_attempt,
                            "sha256": sha256(attempt_path),
                        },
                        {
                            "url": attempt_url,
                            "archive_member": relative_stage,
                            "sha256": sha256(stage_path),
                        },
                    ],
                    "reproduction_command": "python scripts/reports/campaign_graph_figures.py --campaign-root reports/closed-loop-composition-campaign-v2",
                }
            )
            known.add(figure_id)

    args.figure_index.write_text(
        json.dumps(figure_index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"rendered {len(known)} indexed figures; campaign figures added: {sum(len(c['planes']) for c in CASES.values())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

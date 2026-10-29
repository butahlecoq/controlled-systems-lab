#!/usr/bin/env python3
"""Render one saved B04 smoke attempt per solver beside the exact witness."""

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import shutil

from b04_projection_example import CASE, REFERENCE, check_saved_trajectory, fraction


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ATTEMPTS = ROOT / "docs/research/evidence/b04-reference-v1/native-smoke-20261026/b04-cold-attempts.jsonl"
DEFAULT_OUTPUT = ROOT / "docs/research/evidence/b04-reference-v1/native-smoke-20261026"
DEFAULT_MANIFEST = DEFAULT_OUTPUT / "manifest.json"
COLORS = {
    "exact-reference": ("#f2b880", "solid"),
    "osqp-sparse-qp": ("#75c6e8", "8 5"),
    "hpipm-structured-ocp-qp": ("#a8d18d", "3 4"),
}
DISPLAY = {
    "exact-reference": "Exact saved witness",
    "osqp-sparse-qp": "OSQP, one cold smoke attempt",
    "hpipm-structured-ocp-qp": "HPIPM, one cold smoke attempt",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_attempts(path: Path, case: dict, manifest: dict | None) -> list[dict]:
    case_digest = hashlib.sha256(CASE.read_bytes()).hexdigest()
    attempts_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest is not None:
        require(manifest.get("schema") == "csl.mpc01-native-smoke-figure/1", "unsupported figure manifest schema")
        require(manifest.get("case_sha256") == case_digest, "manifest case digest differs from the frozen input")
        require(manifest.get("attempts_sha256") == attempts_digest, "attempt rows differ from the pinned manifest digest")
        require(manifest.get("attempt_count") == 2, "manifest attempt count differs")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(rows) == 2, "expected exactly one cold B04 attempt per solver")
    require({row.get("method") for row in rows} == {"osqp-sparse-qp", "hpipm-structured-ocp-qp"},
            "attempt file must contain one OSQP and one HPIPM row")
    for row in rows:
        require(row.get("case_id") == case["case_id"], "attempt case identity differs")
        require(row.get("input_sha256") == case_digest, "attempt input digest differs from the frozen case")
        require(row.get("start_mode") == "cold", "only cold starts are shown")
        require(row.get("termination") == "completed" and row.get("mathematical_outcome") == "optimal",
                "attempt is not an optimal-status smoke result")
        require("trajectory" in row and "candidate_iterate" not in row,
                "attempt does not contain a solver-returned trajectory")
        states = row["trajectory"]["states"]
        controls = row["trajectory"]["controls"]
        require(len(states) == case["horizon"] + 1 and all(len(s) == 4 for s in states),
                "attempt state dimensions differ from the frozen case")
        require(len(controls) == case["horizon"] and all(len(u) == 1 for u in controls),
                "attempt control dimensions differ from the frozen case")
        diagnostics = row["original_data_diagnostics"]
        require(diagnostics["evidence_status"] == "inconclusive",
                "smoke residuals must remain labeled inconclusive")
        values = [diagnostics[k] for k in ("max_dynamics_residual", "max_state_bound_violation", "max_control_bound_violation")]
        require(all(math.isfinite(v) and v >= 0 for v in values), "attempt residual diagnostics are invalid")
        require(row["original_objective"] is not None and math.isfinite(row["original_objective"]),
                "attempt lacks a finite objective evaluated on the original norm")
    return sorted(rows, key=lambda row: row["method"])


def text(x: float, y: float, label: str, size: int = 13, anchor: str = "middle") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}">{html.escape(label)}</text>'


def panel(series: list[tuple[str, list[list[float]]]], ix: int, iy: int,
          title: str, xlabel: str, ylabel: str, left: int,
          bounds: tuple[tuple[float, float], tuple[float, float]] | None = None) -> str:
    top, width, height = 148, 420, 360
    xs = [state[ix] for _, states in series for state in states]
    ys = [state[iy] for _, states in series for state in states]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    if bounds:
        (xlo, xhi), (ylo, yhi) = bounds
        xmin, xmax = min(xmin, xlo), max(xmax, xhi)
        ymin, ymax = min(ymin, ylo), max(ymax, yhi)
    xpad, ypad = max((xmax - xmin) * 0.08, 1.0), max((ymax - ymin) * 0.08, 1.0)
    xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad
    sx = lambda value: left + (value - xmin) / (xmax - xmin) * width
    sy = lambda value: top + height - (value - ymin) / (ymax - ymin) * height
    parts = [text(left + width / 2, 112, title, 18)]
    for i in range(6):
        xv, yv = xmin + (xmax - xmin) * i / 5, ymin + (ymax - ymin) * i / 5
        parts.append(f'<path d="M{sx(xv):.1f} {top}V{top+height} M{left} {sy(yv):.1f}H{left+width}" class="grid"/>')
        parts.append(text(sx(xv), top + height + 22, f"{xv:.1f}", 11))
        parts.append(text(left - 10, sy(yv) + 4, f"{yv:.1f}", 11, "end"))
    parts.append(f'<path d="M{left} {top+height}H{left+width} M{left} {top}V{top+height}" class="axis"/>')
    if bounds:
        (xlo, xhi), (ylo, yhi) = bounds
        parts.append(f'<rect x="{sx(xlo):.1f}" y="{sy(yhi):.1f}" width="{sx(xhi)-sx(xlo):.1f}" height="{sy(ylo)-sy(yhi):.1f}" class="feasible"/>')
        parts.append(text(left + width / 2, top + 20, "flow bounds apply at stages 0 and 16", 11))
    flow_offsets = {0: (15, -14), 4: (-28, -22), 8: (8, -26), 12: (-20, 24), 16: (16, 13)}
    stock_offsets = {0: (15, -13), 4: (25, -16), 8: (26, 4), 12: (-28, 20), 16: (-18, -15)}
    offsets = flow_offsets if title == "Flow plane" else stock_offsets
    for name, states in series:
        color, dash = COLORS[name]
        points = " ".join(f"{sx(state[ix]):.1f},{sy(state[iy]):.1f}" for state in states)
        dash_attr = "" if dash == "solid" else f' stroke-dasharray="{dash}"'
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"{dash_attr}/>')
        for t, state in enumerate(states):
            radius = 4 if name == "exact-reference" else 2.5
            parts.append(f'<circle cx="{sx(state[ix]):.1f}" cy="{sy(state[iy]):.1f}" r="{radius}" fill="{color}"/>')
            if name == "exact-reference" and t in (0, 4, 8, 12, 16):
                dx, dy = offsets[t]
                anchor = "end" if dx < 0 else "start"
                parts.append(f'<path d="M{sx(state[ix]):.1f} {sy(state[iy]):.1f}L{sx(state[ix])+dx*.72:.1f} {sy(state[iy])+dy*.72:.1f}" class="leader"/>')
                parts.append(text(sx(state[ix]) + dx, sy(state[iy]) + dy, str(t), 10, anchor))
    parts.extend([text(left + width / 2, top + height + 48, xlabel, 13),
                  f'<text transform="translate({left-58} {top+height/2}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>'])
    return "\n".join(parts)


def render_svg(case: dict, exact_states: list[list[float]], rows: list[dict]) -> str:
    series = [("exact-reference", exact_states)] + [
        (row["method"], row["trajectory"]["states"]) for row in rows
    ]
    flow_bounds = ((1176.0, 1224.0), (432.0, 468.0))
    legend = []
    legend_labels = {"exact-reference": "Exact witness", "osqp-sparse-qp": "OSQP cold", "hpipm-structured-ocp-qp": "HPIPM cold"}
    for x, (name, states) in zip((155, 475, 795), series):
        color, dash = COLORS[name]
        label = legend_labels[name]
        dash_attr = "" if dash == "solid" else f' stroke-dasharray="{dash}"'
        legend.append(f'<path d="M{x} 75h36" stroke="{color}" stroke-width="4"{dash_attr}/>{text(x+44, 80, label, 12, "start")}')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 670" role="img" aria-labelledby="title desc">
<title id="title">B04 native smoke trajectories projected from four states into two planes</title>
<desc id="desc">One cold OSQP trajectory and one cold HPIPM trajectory from a single smoke capture are overlaid with the exact saved reference witness. The left panel projects four-dimensional states onto oxidizer and fuel flows; the right projects them onto working stocks. This is not a benchmark aggregate or historical B04 reconstruction. Binary64 solver residual checks are inconclusive.</desc>
<rect width="1100" height="670" fill="#172019"/><style>svg{{font-family:system-ui,sans-serif;color:#dce5d5}}text{{fill:#dce5d5}}.axis{{stroke:#a9b7a0;stroke-width:2}}.grid{{stroke:#71806e;stroke-opacity:.25;stroke-width:1}}.leader{{stroke:#dce5d5;stroke-width:1}}.feasible{{fill:#76966d;fill-opacity:.10;stroke:#b4cda3;stroke-dasharray:6 4;stroke-width:2}}</style>
<text x="550" y="32" text-anchor="middle" font-size="22">Fuel reference case: native solver trajectories in two 2D projections</text>
<text x="550" y="54" text-anchor="middle" font-size="12">b04-reference-v1 · one cold smoke attempt per solver · not historical B04 or a repeated benchmark</text>
{' '.join(legend)}
{panel(series, 0, 2, "Flow plane", "Oxidizer flow (kg/s)", "Fuel flow (kg/s)", 112, flow_bounds)}
{panel(series, 1, 3, "Working-stock plane", "Oxidizer working stock (kg)", "Fuel working stock (kg)", 605)}
<text x="550" y="628" text-anchor="middle" font-size="12">State order: oxidizer flow, oxidizer stock, fuel flow, fuel stock. Stage numbers label the exact saved witness.</text>
<text x="550" y="649" text-anchor="middle" font-size="12">Stocks are unconstrained in the source; solver optimal status and binary64 residuals do not independently prove optimality.</text>
</svg>'''


def render_html(svg_name: str, attempts_link: str, reference_link: str,
                rows: list[dict], exact_norm: float, input_digest: str,
                attempts_digest: str, runner_commit: str | None) -> str:
    table_rows = []
    table_rows.append(f'<tr><th scope="row">Exact saved witness</th><td>{exact_norm:.12f}</td><td>0 (rational check)</td><td>exact global optimum for this frozen reference</td></tr>')
    for row in rows:
        diag = row["original_data_diagnostics"]
        max_residual = max(diag["max_dynamics_residual"], diag["max_state_bound_violation"], diag["max_control_bound_violation"])
        table_rows.append(f'<tr><th scope="row">{html.escape(DISPLAY[row["method"]])}</th><td>{row["original_objective"]:.12f}</td><td>{max_residual:.3g}</td><td>inconclusive</td></tr>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B04 native smoke trajectory projections</title>
<style>body{{margin:0;background:#0b1020;color:#e2e8f0;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:2rem}}a{{color:#7dd3fc}}img{{display:block;width:100%;height:auto}}.scope{{border-left:4px solid #fb7185;padding:.7rem 1rem;background:#171d30}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border-bottom:1px solid #475569;padding:.5rem;text-align:left}}code{{overflow-wrap:anywhere;color:#fde68a}}</style></head>
<body><main><p>Native solver output, shown as a diagnostic illustration</p><h1>Native B04 smoke trajectories as two projections of the 4D state</h1>
<p>The left panel plots oxidizer flow against fuel flow. The right plots the two working stocks. The same 17 states from each four-dimensional trajectory appear in both panels.</p>
<img src="{html.escape(svg_name)}" alt="One cold OSQP and one cold HPIPM trajectory overlaid with the exact saved B04 reference witness in flow and working-stock planes. The plotted solver residual checks are labeled inconclusive.">
<p><a href="{html.escape(attempts_link)}" download>Download the two saved native attempt rows</a> · <a href="{html.escape(reference_link)}">Open the exact reference witness</a></p>
<div class="scope"><strong>Evidence scope.</strong> This is one smoke capture, with one cold attempt per solver. It is an illustration of returned solver trajectories, not a repeated benchmark, canonical comparison record, independent optimality proof, or reconstruction of historical B04. The exact saved witness is separately proven globally optimal for the frozen <code>b04-reference-v1</code> input. The solver output is preserved with its raw attempt rows. State/control feasibility diagnostics use binary64 residuals and remain inconclusive.</div>
<h2>Recorded solver values</h2><table><caption>Objective values use the original Euclidean residual norm. Residual summary is the largest of dynamics, state-bound and control-bound diagnostics.</caption><thead><tr><th>Attempt</th><th>Original norm</th><th>Max residual</th><th>Evidence status</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table>
<h2>Reproduce</h2><pre><code>python3 scripts/reports/mpc01/b04_native_smoke_projection.py</code></pre>
<p>Runner source commit: <code>{html.escape(runner_commit or "unrecorded for custom attempt input")}</code>. Frozen input SHA-256: <code>{input_digest}</code>. Attempt rows SHA-256: <code>{attempts_digest}</code>.</p>
</main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=Path, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path,
                        help="verify input/attempt digests against a machine-readable manifest")
    args = parser.parse_args()
    case = json.loads(CASE.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    exact = check_saved_trajectory(case, reference)
    manifest_path = args.manifest
    if manifest_path is None and args.attempts.resolve() == DEFAULT_ATTEMPTS.resolve():
        manifest_path = DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path else None
    rows = load_attempts(args.attempts, case, manifest)
    exact_float = [[float(v) for v in state] for state in exact]
    if (args.attempts.resolve() != DEFAULT_ATTEMPTS.resolve() and
            args.output_dir.resolve() == DEFAULT_OUTPUT.resolve()):
        raise ValueError("custom --attempts requires a fresh --output-dir to preserve the pinned evidence")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    attempts_link = "b04-cold-attempts.jsonl"
    reference_link = "../exact-optimal-reference.json"
    if args.output_dir.resolve() != DEFAULT_OUTPUT.resolve():
        shutil.copyfile(args.attempts, args.output_dir / attempts_link)
        shutil.copyfile(REFERENCE, args.output_dir / "exact-optimal-reference.json")
        reference_link = "exact-optimal-reference.json"
    svg_path = args.output_dir / "native-smoke-projections.svg"
    html_path = args.output_dir / "native-smoke-projections.html"
    input_digest = hashlib.sha256(CASE.read_bytes()).hexdigest()
    attempt_digest = hashlib.sha256(args.attempts.read_bytes()).hexdigest()
    svg_path.write_text(render_svg(case, exact_float, rows) + "\n", encoding="utf-8")
    html_path.write_text(render_html(svg_path.name, attempts_link, reference_link, rows,
                                     float(reference["exact_norm_optimum_decimal"]),
                                     input_digest, attempt_digest,
                                     manifest.get("runner_source_commit") if manifest else None) + "\n", encoding="utf-8")
    try:
        svg_display, html_display = svg_path.resolve().relative_to(ROOT), html_path.resolve().relative_to(ROOT)
    except ValueError:
        svg_display, html_display = svg_path.resolve(), html_path.resolve()
    print(f"wrote {svg_display} and {html_display}")


if __name__ == "__main__":
    main()

"""Build B04 oxidizer/fuel phase-plane figures from preserved attempts."""
from __future__ import annotations

import hashlib
import html
import json
import math
from fractions import Fraction
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import figure_style


METHODS = {
    "exact-reference": ("Exact saved witness", "#b23b33", "-"),
    "osqp-sparse-qp": ("OSQP · one cold smoke attempt", "#2367a8", "--"),
    "hpipm-structured-ocp-qp": ("HPIPM · one cold smoke attempt", "#2a7f62", ":"),
}


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe B04 evidence file: " + str(path))
    return path.read_bytes()


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate(root: Path) -> tuple[dict, dict, bytes, bytes, bytes, bytes]:
    evidence = root / "docs/research/evidence/b04-reference-v1"
    smoke = evidence / "native-smoke-20261026"
    paths = {
        "case": evidence / "canonical-case.json",
        "reference": evidence / "exact-optimal-reference.json",
        "exact_check": evidence / "exact-check-report.json",
        "attempts": smoke / "b04-cold-attempts.jsonl",
        "manifest": smoke / "manifest.json",
    }
    raw = {key: _read(path) for key, path in paths.items()}
    case, reference, exact_check, manifest = (
        json.loads(raw[key]) for key in ("case", "reference", "exact_check", "manifest"))
    if case.get("case_id") != "b04-reference-v1" or case.get("state_dimension") != 4:
        raise ValueError("unexpected B04 reference case identity or dimension")
    if case.get("state_coordinates") != [
            "oxidizer_flow", "oxidizer_working_stock", "fuel_flow", "fuel_working_stock"]:
        raise ValueError("B04 state coordinate order changed")
    if case.get("state_units") != ["kg/s", "kg", "kg/s", "kg"]:
        raise ValueError("B04 state units changed")
    if (manifest.get("schema") != "csl.mpc01-native-smoke-figure/1" or
            manifest.get("case_sha256") != _hash(raw["case"]) or
            manifest.get("attempts_sha256") != _hash(raw["attempts"]) or
            manifest.get("attempt_count") != 2):
        raise ValueError("B04 native smoke evidence does not match its saved manifest")
    if (exact_check.get("case_id") != case["case_id"] or
            exact_check.get("acados_witness_check", {}).get("highs_check", {}).get("outcome") != "optimal"):
        raise ValueError("B04 exact-reference check does not report the saved optimal outcome")
    exact_states = reference.get("exact_optimal_states_one_solution")
    if (not isinstance(exact_states, list) or len(exact_states) != case.get("horizon", -1) + 1 or
            any(not isinstance(state, list) or len(state) != 4 for state in exact_states)):
        raise ValueError("B04 exact saved witness has an unexpected state shape")
    if reference.get("exact_norm_optimum_decimal") != exact_check.get("exact_global_optimum", {}).get(
            "exact_norm_optimum_decimal"):
        raise ValueError("B04 exact witness value differs from the saved exact-check record")
    rows = [json.loads(line) for line in raw["attempts"].decode("utf-8").splitlines() if line.strip()]
    if {row.get("method") for row in rows} != {"osqp-sparse-qp", "hpipm-structured-ocp-qp"}:
        raise ValueError("B04 attempt file must contain one row per native solver")
    if len(rows) != manifest["attempt_count"]:
        raise ValueError("B04 attempt count differs from its manifest")
    for row in rows:
        trajectory = row.get("trajectory", {})
        states = trajectory.get("states", [])
        diagnostics = row.get("original_data_diagnostics", {})
        residuals = [diagnostics.get(name) for name in (
            "max_dynamics_residual", "max_state_bound_violation", "max_control_bound_violation")]
        if (row.get("case_id") != case["case_id"] or row.get("input_sha256") != _hash(raw["case"]) or
                row.get("start_mode") != "cold" or row.get("termination") != "completed" or
                row.get("mathematical_outcome") != "optimal" or
                diagnostics.get("evidence_status") != "inconclusive" or
                len(states) != case["horizon"] + 1 or any(len(state) != 4 for state in states) or
                not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
                        for value in residuals) or
                not isinstance(row.get("original_objective"), (int, float)) or
                not math.isfinite(row["original_objective"])):
            raise ValueError("B04 saved native attempt is incomplete or exceeds its evidence status")
    return case, reference, raw["case"], raw["reference"], raw["attempts"], raw["manifest"]


def _plot(case: dict, reference: dict, rows: list[dict], style_path: Path,
          out: Path) -> dict:
    style_raw = _read(style_path)
    style = json.loads(style_raw)
    if style.get("schema") != "csl.figure-style/1" or style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("B04 companion requires the versioned quantitative plot style")
    import matplotlib
    if matplotlib.__version__ != style.get("matplotlib_version"):
        raise ValueError("Matplotlib version differs from the pinned figure style")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    units = case["state_units"]
    by_id = {row["method"]: row for row in rows}
    series = [("exact-reference", reference["exact_optimal_states_one_solution"])] + [
        (method, by_id[method]["trajectory"]["states"])
        for method in ("osqp-sparse-qp", "hpipm-structured-ocp-qp")]
    projections = ((0, 1, "Oxidizer plane · (x₁, x₂)", "Oxidizer flow x₁", "Oxidizer working stock x₂"),
                   (2, 3, "Fuel plane · (x₃, x₄)", "Fuel flow x₃", "Fuel working stock x₄"))
    bounds_by_coordinate = {
        item["coordinate"]: (float(item["lower"]), float(item["upper"]))
        for item in case["state_bounds_each_stage"]
    }
    rc = {"font.family": style["font_family"], "font.size": style["font_size"],
          "svg.hashsalt": style["style_id"], "svg.fonttype": "none"}
    out.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context(rc):
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.3))
        try:
            for axis, (x_index, y_index, title, x_label, y_label) in zip(axes, projections):
                for method, states in series:
                    name, color, linestyle = METHODS[method]
                    points = [[float(Fraction(value)) if isinstance(value, str) else float(value)
                               for value in state] for state in states]
                    axis.plot([point[x_index] for point in points],
                              [point[y_index] for point in points],
                              color=color, linestyle=linestyle, linewidth=1.8,
                              marker="o", markersize=2.6, label=name)
                    axis.scatter([points[0][x_index]], [points[0][y_index]],
                                 marker="o", s=34, color=color, edgecolors="white", linewidths=.6,
                                 zorder=4)
                    axis.scatter([points[-1][x_index]], [points[-1][y_index]],
                                 marker="X", s=44, color=color, edgecolors="white", linewidths=.6,
                                 zorder=4)
                if x_index in bounds_by_coordinate:
                    low, high = bounds_by_coordinate[x_index]
                    axis.axvspan(low, high, color="#d9d4ae", alpha=.20,
                                 label="Flow bounds at stages 0 and 16")
                axis.set_title(title)
                axis.set_xlabel(f"{x_label} ({units[x_index]})")
                axis.set_ylabel(f"{y_label} ({units[y_index]})")
                figure_style.configure_numeric_axis(axis)
            handles, labels = axes[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .89),
                       ncol=2, fontsize="small")
            fig.suptitle("B04 reference variant · saved exact witness and native smoke paths", fontsize=12)
            fig.tight_layout(rect=(0, 0, 1, .78))
            svg_path, png_path = out / "geometry.svg", out / "geometry.png"
            fig.savefig(svg_path, metadata={"Date": None, "Creator": "CSL saved B04 figure exporter"})
            fig.savefig(png_path, dpi=style["png_dpi"], metadata={"Software": style["style_id"]})
        finally:
            plt.close(fig)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    root.set("role", "img")
    root.set("aria-labelledby", "figure-title figure-description")
    title = ET.Element("{http://www.w3.org/2000/svg}title", {"id": "figure-title"})
    title.text = "B04 saved trajectories in oxidizer and fuel phase planes"
    description = ET.Element("{http://www.w3.org/2000/svg}desc", {"id": "figure-description"})
    description.text = (
        "Side-by-side projections of the saved four-state histories: oxidizer flow versus oxidizer working stock, "
        "and fuel flow versus fuel working stock. Each panel overlays the exact saved witness, one cold OSQP "
        "attempt, and one cold HPIPM attempt. Circles mark initial states and crosses mark terminal states. "
        "Numeric ticks and major grids follow csl-report-quantitative-v1. Axis units differ, so each panel "
        "uses independent data scaling. Shading marks flow bounds that apply only at stages 0 and 16. "
        "This is trajectory evidence, not a reachable-set or repeated-benchmark plot; native residual checks are inconclusive.")
    root.insert(0, description)
    root.insert(0, title)
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    return {"schema": "csl.figure-export/1", "style_id": style["style_id"],
            "quantitative_axis_policy": figure_style.STYLE_ID,
            "style_sha256": _hash(style_raw), "matplotlib": matplotlib.__version__,
            "files": {path.name: _hash(path.read_bytes()) for path in (svg_path, png_path)}}


def build(style_path: Path) -> tuple[dict[str, bytes], str, dict]:
    """Render a paired, offline companion from immutable saved B04 inputs."""
    root = Path(__file__).resolve().parents[2]
    case, reference, case_raw, reference_raw, attempts_raw, manifest_raw = _validate(root)
    rows = [json.loads(line) for line in attempts_raw.decode("utf-8").splitlines() if line.strip()]
    exact_check_path = root / "docs/research/evidence/b04-reference-v1/exact-check-report.json"
    style_path = Path(style_path)
    with tempfile.TemporaryDirectory(prefix="csl-viz09-b04-smoke-") as temporary:
        rendered = Path(temporary)
        export = _plot(case, reference, rows, style_path, rendered)
        svg = (rendered / "geometry.svg").read_bytes()
        png = (rendered / "geometry.png").read_bytes()

    pairs = (("oxidizer", 0, 1), ("fuel", 2, 3))
    projections = {}
    for name, first, second in pairs:
        projections[name] = {
            "axes": [case["state_coordinates"][first], case["state_coordinates"][second]],
            "units": [case["state_units"][first], case["state_units"][second]],
            "series": [{"id": method, "points": [[state[first], state[second]] for state in states]}
                       for method, states in ([
                           ("exact-reference", reference["exact_optimal_states_one_solution"])] +
                           [(row["method"], row["trajectory"]["states"]) for row in rows])],
        }
    attempt_rows = []
    for row in rows:
        diag = row["original_data_diagnostics"]
        attempt_rows.append({"method": row["method"], "native_status": row["native_status"],
                             "objective_norm": row["original_objective"],
                             "max_dynamics_residual": diag["max_dynamics_residual"],
                             "max_state_bound_violation": diag["max_state_bound_violation"],
                             "max_control_bound_violation": diag["max_control_bound_violation"],
                             "evidence_status": diag["evidence_status"], "start_mode": row["start_mode"]})
    evidence = {
        "schema": "csl.control-witness-b04-native-smoke/1", "case_id": case["case_id"],
        "source_variant": case["variant_status"],
        "state_order": case["state_coordinates"], "state_units": case["state_units"],
        "horizon_steps": case["horizon"], "capture": json.loads(manifest_raw)["capture"],
        "runner_source_commit": json.loads(manifest_raw)["runner_source_commit"],
        "projection_data": projections,
        "exact_reference": {"norm_optimum": reference["exact_norm_optimum_decimal"],
                            "optimality_evidence": "exact-check-report.json exact_global_optimum"},
        "native_attempts": attempt_rows,
        "flow_bounds": {"stages": case["state_bound_stages"], "coordinate_bounds": case["state_bounds_each_stage"]},
        "input_sha256": _hash(case_raw), "exact_reference_sha256": _hash(reference_raw),
        "exact_check_sha256": _hash(_read(exact_check_path)),
        "attempt_rows_sha256": _hash(attempts_raw), "attempt_manifest_sha256": _hash(manifest_raw),
        "source_renderers": {
            "native_smoke_projection_sha256": _hash(_read(root / "scripts/reports/mpc01/b04_native_smoke_projection.py")),
            "exact_reference_projection_sha256": _hash(_read(root / "scripts/reports/mpc01/b04_projection_example.py")),
        },
        "figure_export": export,
        "claim_scope": "saved trajectory presentation; no solver, geometry query, experiment, or benchmark",
        "limitations": [
            "The source variant does not resolve historical B04.",
            "This figure overlays three trajectories; it does not show reachable sets or an optimal family.",
            "The two cold native solver residual checks remain inconclusive and are not an independent optimality proof.",
            "The exact witness is separately proven globally optimal for this frozen reference input.",
        ],
    }
    evidence_raw = (json.dumps(evidence, indent=2) + "\n").encode("utf-8")
    outputs = {
        "control-witness/b04-native-smoke-projections.svg": svg,
        "control-witness/b04-native-smoke-projections.png": png,
        "control-witness/b04-native-smoke-evidence.json": evidence_raw,
        "control-witness/b04-native-smoke-case.json": case_raw,
        "control-witness/b04-native-smoke-reference.json": reference_raw,
        "control-witness/b04-native-smoke-exact-check.json": _read(exact_check_path),
        "control-witness/b04-native-smoke-attempts.jsonl": attempts_raw,
        "control-witness/b04-native-smoke-manifest.json": manifest_raw,
    }
    objectives = [{"method": "Exact saved witness", "details":
                   f"Original norm {reference['exact_norm_optimum_decimal']}; maximum residual 0 by exact rational check; "
                   "exact global optimum for this frozen input."}]
    for row in attempt_rows:
        residual = max(row["max_dynamics_residual"], row["max_state_bound_violation"],
                       row["max_control_bound_violation"])
        objectives.append({"method": METHODS[row["method"]][0], "details":
                           f"Original norm {row['objective_norm']}; maximum listed residual {residual:.3g}; "
                           f"native status {row['native_status']}; binary64 evidence inconclusive."})
    table = "".join("<tr><th scope=\"row\">" + html.escape(item["method"]) + "</th><td>" +
                    html.escape(item["details"]) + "</td></tr>" for item in objectives)
    article = (
        '<article id="b04-native-smoke"><h2>B04 reference variant · saved native smoke paths</h2>'
        '<p>The two panels use the requested within-species projections: oxidizer flow versus oxidizer working stock '
        '(<code>x₁,x₂</code>) and fuel flow versus fuel working stock (<code>x₃,x₄</code>). Lines show all 17 saved '
        'states for the exact reference witness and each single cold native solver attempt. Circles mark starts; crosses '
        'mark terminal states. The shaded intervals are flow constraints at stages 0 and 16 only. The axes have different '
        'units and use independent scales.</p>'
        '<figure><a href="control-witness/b04-native-smoke-projections.svg"><img '
        'src="control-witness/b04-native-smoke-projections.svg" alt="Side-by-side oxidizer flow versus working-stock '
        'and fuel flow versus working-stock trajectories for the exact witness, one cold OSQP smoke attempt, and one '
        'cold HPIPM smoke attempt."></a><figcaption>Numeric ticks and major grids follow csl-report-quantitative-v1. '
        '<a href="control-witness/b04-native-smoke-projections.png">Open PNG figure ↗</a></figcaption></figure>'
        '<div class="scroll" tabindex="0" role="region" aria-label="B04 saved trajectory values"><table>'
        '<caption>Saved objective norms and residual evidence</caption><thead><tr><th scope="col">History</th>'
        '<th scope="col">Saved values and evidence</th></tr></thead><tbody>' + table + '</tbody></table></div>'
        '<p>The exact saved witness is separately proven globally optimal for the frozen <code>b04-reference-v1</code> '
        'input. The OSQP and HPIPM rows are one smoke attempt each; their binary64 residual checks are inconclusive. '
        'This is a trajectory illustration, not a reachable-set figure, a repeated benchmark, or a reconstruction of '
        'historical B04.</p><p><a href="control-witness/b04-native-smoke-case.json">Saved input ↗</a> · '
        '<a href="control-witness/b04-native-smoke-reference.json">Exact witness ↗</a> · '
        '<a href="control-witness/b04-native-smoke-exact-check.json">Exact-check record ↗</a> · '
        '<a href="control-witness/b04-native-smoke-attempts.jsonl">Native attempt rows ↗</a> · '
        '<a href="control-witness/b04-native-smoke-manifest.json">Attempt manifest ↗</a> · '
        '<a href="control-witness/b04-native-smoke-evidence.json">Projection data, hashes, and export metadata ↗</a></p>'
        '<p>Reproduce the gallery from saved evidence with '
        '<code>python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site</code>.</p></article>')
    entry = {"family": "B04 saved trajectory projections",
             "title": "Oxidizer and fuel phase planes from B04 saved smoke paths",
             "status": "saved-data-companion", "anchor": "b04-native-smoke",
             "page": "control-witness-v1.html#b04-native-smoke",
             "figure": "control-witness/b04-native-smoke-projections.svg",
             "source_page": "https://github.com/butahlecoq/controlled-systems-lab/blob/"
                            "a9ad775b7c6db5043835e3e8557fb06ee734f959/docs/research/evidence/"
                            "b04-reference-v1/native-smoke-20261026/README.md",
             "raw_record": "control-witness/b04-native-smoke-evidence.json"}
    return outputs, article, entry

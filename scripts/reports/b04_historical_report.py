"""Build a run-free B04 historical report from versioned saved evidence."""
from __future__ import annotations

import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "csl.b04-historical-report/1"
POLICY_LABELS = {
    "u(t)=0": "Nominal reference, u(t)=0",
    "frozen_coefficient_regulator": "Nonlinear, frozen-coefficient regulator u*",
    "optimal_linear_witness_1": "Nonlinear, optimal linear witness 1",
    "optimal_linear_witness_2": "Nonlinear, optimal linear witness 2",
    "optimal_linear_witness_3": "Nonlinear, optimal linear witness 3",
    "linear_any_of_witnesses_1_to_3": "Linear, any of witnesses 1–3",
}
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = Path(path).read_bytes()
    value = json.loads(raw, parse_float=Decimal, object_pairs_hook=_pairs_no_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _token(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal, str)):
        raise ValueError(f"{path} must retain a decimal or integer token")
    token = str(value)
    try:
        Decimal(token)
    except Exception as error:
        raise ValueError(f"{path} is not a finite decimal token") from error
    if not Decimal(token).is_finite():
        raise ValueError(f"{path} is not a finite decimal token")
    return token


def _rounding_radius(token: str) -> dict[str, Any]:
    exponent = Decimal(token).as_tuple().exponent
    if exponent >= 0:
        numerator, denominator = 10**exponent, 2
    else:
        numerator, denominator = 1, 2 * 10 ** (-exponent)
    radius = Fraction(numerator, denominator)
    return {"fractional_digits": max(0, -exponent), "radius_exact": str(radius)}


def _plain_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain_json(item) for key, item in value.items()}
    return value


def _index_sources(entries: list[Any], name: str) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError(f"{name} entries must be objects with string IDs")
        source_id = item["id"]
        if source_id in by_id:
            raise ValueError(f"{name} contains duplicate source ID {source_id}")
        by_id[source_id] = item
    return by_id


def _source_map(register: dict[str, Any], manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = register.get("selected_sources")
    if not isinstance(entries, list):
        raise ValueError("archive register selected_sources must be an array")
    by_id = _index_sources(entries, "archive register")
    required = {"A11", "A12", "A14"}
    if not required <= by_id.keys():
        raise ValueError("archive register must contain the B04 A11, A12, and A14 sources")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("historical manifest sources must be an array")
    by_manifest_id = _index_sources(sources, "historical manifest")
    l11 = by_manifest_id.get("L11")
    if not isinstance(l11, dict) or l11.get("sha256") != by_id["A14"].get("sha256"):
        raise ValueError("historical L11 and byte-identical A14 source identities disagree")
    a11, a12, a14 = (by_id[source_id] for source_id in ("A11", "A12", "A14"))
    for source_id, item in (("A11", a11), ("A12", a12), ("A14", a14)):
        if not isinstance(item.get("sha256"), str) or not HEX_SHA256.fullmatch(item["sha256"]):
            raise ValueError(f"archive source {source_id} has an invalid SHA-256")
    r40 = by_manifest_id.get("R40")
    if not isinstance(r40, dict) or not r40.get("doi") or not r40.get("url"):
        raise ValueError("historical manifest must cite the R40 published counterpart")
    return {
        "A11": {"id": "A11", "path": a11["path"], "sha256": a11["sha256"], "role": a11["role"], "table": "Table 2"},
        "A12": {"id": "A12", "path": a12["path"], "sha256": a12["sha256"], "role": a12["role"], "page": 20},
        "A14": {"id": "A14", "path": a14["path"], "sha256": a14["sha256"], "role": a14["role"]},
        "R40": {"id": "R40", "url": r40["url"], "doi": r40["doi"], "role": r40["role"]},
    }


def _validate_inputs(manifest: dict[str, Any], consistency: dict[str, Any], register: dict[str, Any],
                     manifest_hash: str) -> None:
    if (manifest.get("id") != "B04-historical" or manifest.get("schema_version") != 1 or
            manifest.get("executable") is not False or
            manifest.get("restoration_status") != "incomplete_and_inconsistent" or
            not isinstance(manifest.get("unresolved"), list) or not manifest["unresolved"] or
            not isinstance(manifest.get("execution_gate"), str) or not manifest["execution_gate"]):
        raise ValueError("manifest must retain the non-executable, incomplete B04 historical gate")
    if (consistency.get("scenario") != "B04-historical" or
            consistency.get("source_manifest_sha256") != manifest_hash or
            consistency.get("status") != "displayed_data_inconsistent_with_reported_optimizer" or
            consistency.get("historical_reproduction_complete") is not False):
        raise ValueError("consistency audit must match the historical manifest and unresolved status")
    for field in ("stock_invariant", "unrestricted_terminal_plane_minimum", "displayed_table_evaluations"):
        if field not in consistency:
            raise ValueError(f"consistency audit is missing {field}")
    _source_map(register, manifest)


def _coordinate_values(values: list[Any], path: str) -> list[dict[str, Any]]:
    if len(values) != 4:
        raise ValueError(f"{path} must contain four terminal-state coordinates")
    result = []
    for index, value in enumerate(values):
        token = _token(value, f"{path}[{index}]")
        result.append({"value": token, **_rounding_radius(token)})
    return result


def build(manifest_path: Path, consistency_path: Path, register_path: Path) -> dict[str, Any]:
    manifest, _, manifest_hash = _load(manifest_path)
    consistency, _, consistency_hash = _load(consistency_path)
    register, _, register_hash = _load(register_path)
    _validate_inputs(manifest, consistency, register, manifest_hash)
    sources = _source_map(register, manifest)
    reported = manifest["reported"]
    rows = []

    raw_rows = [reported.get("nominal_reference")]
    raw_rows.extend(reported.get("nonlinear_table_rows", []))
    raw_rows.append({
        "policy": "linear_any_of_witnesses_1_to_3",
        "terminal_state": reported.get("terminal_state"),
        "objective": reported.get("objective"),
    })
    evaluations = consistency["displayed_table_evaluations"]
    evaluations_by_policy = {item.get("policy"): item for item in evaluations if isinstance(item, dict)}
    if len(evaluations_by_policy) != 6 or len(raw_rows) != 6:
        raise ValueError("B04 Table 2 must preserve all six policy rows and their display evaluations")
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise ValueError(f"reported table row {index} must be an object")
        policy = raw_row.get("policy")
        if policy not in POLICY_LABELS:
            raise ValueError(f"reported table row {index} has an unsupported policy label")
        evaluation = evaluations_by_policy.get(policy)
        coordinates = _coordinate_values(raw_row.get("terminal_state", []), f"reported row {policy}.terminal_state")
        reported_objective = _token(raw_row.get("objective"), f"reported row {policy}.objective")
        if (evaluation is None or evaluation.get("terminal_state_printed") != [item["value"] for item in coordinates] or
                evaluation.get("reported_objective_printed") != reported_objective):
            raise ValueError(f"displayed-coordinate evaluation does not bind to the printed row {policy}")
        rows.append({
            "policy_id": policy,
            "policy_label": POLICY_LABELS[policy],
            "source_ids": ["A11", "A12", "R40"],
            "terminal_state": coordinates,
            "reported_objective": {"value": reported_objective, **_rounding_radius(reported_objective)},
            "printed_coordinate_evaluation": {
                "objective_norm": evaluation["objective_at_printed_coordinates"],
                "objective_squared_exact": evaluation["objective_squared_at_printed_coordinates_exact"],
                "coordinate_rounding_effect_bound": evaluation["objective_rounding_effect_bound"],
                "coordinate_rounding_effect_bound_squared_exact": evaluation["objective_rounding_effect_bound_squared_exact"],
                "interpretation": evaluation["interpretation"],
            },
            "row_note": (reported["nominal_reference"].get("role") if index == 0 else
                         "optimal for the linear model; this row does not claim nonlinear global optimality"
                         if policy.startswith("optimal_linear_witness_") else None),
        })

    current_runtime = {"status": "unavailable", "reason": "No executable B04 historical run exists in the archived manifest."}
    report = {
        "schema": SCHEMA,
        "track": "historical-only",
        "scenario_id": "B04-historical",
        "manifest_sha256": manifest_hash,
        "consistency_audit_sha256": consistency_hash,
        "archive_register_sha256": register_hash,
        "source_citations": list(sources.values()),
        "reported_table": {
            "source_label": reported["nonlinear_table_source"],
            "rows": rows,
        },
        "restoration": {
            "status": consistency["status"],
            "execution_gate": manifest["execution_gate"],
            "unresolved_inputs": manifest["unresolved"],
            "stock_invariant": _plain_json(consistency["stock_invariant"]),
            "unrestricted_terminal_plane_minimum": _plain_json(consistency["unrestricted_terminal_plane_minimum"]),
            "limits": _plain_json(consistency["limits"]),
            "excluded_control_interval_hypothesis": _plain_json(manifest.get("related_noncanonical_evidence")),
        },
        "runtime": {
            "historical_reported_seconds": _token(reported["runtime_seconds"], "reported.runtime_seconds"),
            "historical_context": _plain_json(reported["runtime_context"]),
            "current_measurement": current_runtime,
        },
        "reproduction": {
            "status": "unavailable",
            "reason": "The manifest is non-executable, has unresolved controls and first-action semantics, and contains a proved displayed-model/terminal-result inconsistency.",
        },
    }
    return validate(report)


def validate(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema") != SCHEMA or report.get("track") != "historical-only":
        raise ValueError("report must use the csl.b04-historical-report/1 historical-only schema")
    if report.get("scenario_id") != "B04-historical":
        raise ValueError("historical report scenario identity is invalid")
    for key in ("manifest_sha256", "consistency_audit_sha256", "archive_register_sha256"):
        if not isinstance(report.get(key), str) or not HEX_SHA256.fullmatch(report[key]):
            raise ValueError(f"{key} must be a SHA-256")
    if not isinstance(report.get("reported_table", {}).get("rows"), list) or len(report["reported_table"]["rows"]) != 6:
        raise ValueError("historical report must preserve six reported Table 2 rows")
    if report.get("reproduction", {}).get("status") != "unavailable":
        raise ValueError("historical B04 output cannot claim a reproduced result")
    if report.get("runtime", {}).get("current_measurement", {}).get("status") != "unavailable":
        raise ValueError("historical B04 output has no current measured runtime")
    if report.get("restoration", {}).get("status") != "displayed_data_inconsistent_with_reported_optimizer":
        raise ValueError("historical report must preserve the checked restoration status")
    return report


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_html(report: dict[str, Any]) -> str:
    report = validate(report)
    rows = []
    for row in report["reported_table"]["rows"]:
        coordinates = "<br>".join(_escape(item["value"]) for item in row["terminal_state"])
        coordinate_precision = "<br>".join(
            f"{item['fractional_digits']} decimal places; ±{_escape(item['radius_exact'])}"
            for item in row["terminal_state"])
        evaluation = row["printed_coordinate_evaluation"]
        objective = row["reported_objective"]
        note = row["row_note"] or ""
        rows.append(
            "<tr>"
            f"<th scope=\"row\">{_escape(row['policy_label'])}</th>"
            f"<td>{coordinates}</td><td>{coordinate_precision}</td>"
            f"<td>{_escape(objective['value'])}<br>{objective['fractional_digits']} decimal places; ±{_escape(objective['radius_exact'])}</td>"
            f"<td>{_escape(evaluation['objective_norm'])}<br>±{_escape(evaluation['coordinate_rounding_effect_bound'])}</td>"
            f"<td>{_escape(note)}</td></tr>")
    stock = report["restoration"]["stock_invariant"]
    lower = report["restoration"]["unrestricted_terminal_plane_minimum"]
    citations = "".join(
        f"<li>{_escape(item['id'])} · SHA-256 {_escape(item['sha256']) if item.get('sha256') else 'not supplied'} · {_escape(item.get('role', ''))}</li>"
        for item in report["source_citations"] if item["id"] != "R40")
    r40 = next(item for item in report["source_citations"] if item["id"] == "R40")
    citations += (f"<li><a href=\"{_escape(r40['url'])}\">R40 published counterpart</a> · DOI "
                 f"{_escape(r40['doi'])}</li>")
    html_text = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B04 historical table and restoration evidence</title>
<style>
body{{margin:2rem auto;padding:0 1rem;max-width:1100px;font:16px/1.55 system-ui,sans-serif;color:#18212a}}
h1,h2{{line-height:1.2}}.notice{{padding:1rem;border-left:5px solid #c55;background:#fff4ee}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:850px}}th,td{{border:1px solid #bbc4cc;padding:.55rem;text-align:left;vertical-align:top}}thead{{background:#edf2f5}}
code{{overflow-wrap:anywhere}}.muted{{color:#4c5863}}
</style></head><body>
<main><h1>B04 historical Table 2 and restoration evidence</h1>
<p class="notice"><strong>Historical-only record.</strong> The B04 manifest is non-executable. This report presents published values and calculations at printed coordinates. It contains no solver run or current benchmark measurement.</p>
<p>Scenario <code>B04-historical</code>. Restoration status: <strong>{_escape(report['restoration']['status'])}</strong>.</p>
<h2>Reported terminal rows</h2><p>{_escape(report['reported_table']['source_label'])}. Coordinates and objectives preserve the printed decimal precision. The separate calculated column evaluates the objective at the displayed terminal coordinates; its ± value bounds the effect of coordinate display rounding.</p>
<div class="scroll"><table><thead><tr><th>Policy</th><th>Reported terminal state (x₁, x₂, x₃, x₄)</th><th>Coordinate precision / rounding radius</th><th>Reported objective</th><th>Computed at printed coordinates (rounding bound)</th><th>Interpretation</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Restoration diagnostics</h2>
<p>Missing controls: {_escape(report['restoration']['unresolved_inputs'][0])}. The first-action convention is unresolved. See the full unresolved list in the machine-readable report.</p>
<p>Stock invariant for the displayed model: required value <code>{_escape(stock['required_exact'])}</code>; reported point gives <code>{_escape(stock['reported_point_exact'])}</code>; exact gap <code>{_escape(stock['gap_exact'])}</code>. The terminal-coordinate rounding radius is <code>{_escape(stock['reported_point_rounding_radius_exact'])}</code>.</p>
<p>The unrestricted terminal-plane minimum is {_escape(lower['objective_float'])}. This is a lower bound for constraints on the displayed model, not a constrained optimum and not a reproduced historical result. Exact squared value: <code>{_escape(lower['objective_squared_exact'])}</code>.</p>
<p>The owner-recalled control interval [-1, 1] is provisional and comes from a different adaptive demonstration. It is not an input to this historical manifest. The separate article-derived reference case has its own identity, <code>b04-reference-v1</code>.</p>
<h2>Runtime and reproduction</h2><p>Historical reported runtime: {_escape(report['runtime']['historical_reported_seconds'])} seconds ({_escape(report['runtime']['historical_context'].get('software', 'source software unavailable'))}; scope {_escape(report['runtime']['historical_context'].get('timing_scope', 'not specified'))}). Current measurement: unavailable. Reproduction: unavailable. {_escape(report['reproduction']['reason'])}</p>
<h2>Sources</h2><ul>{citations}</ul><p>Archive paths and source roles are recorded in the <a href="archive-selected-sources.json">hash-identified source register</a>. Original archive files are not redistributed.</p>
<p>Source manifest SHA-256: <code>{_escape(report['manifest_sha256'])}</code>. Audit SHA-256: <code>{_escape(report['consistency_audit_sha256'])}</code>.</p>
<p><a href="b04-historical-comparison.json">Machine-readable report data</a> · <a href="b04-restoration.md">Restoration dossier</a> · <a href="b04-tables.md">Table transcription</a></p>
</main></body></html>
"""
    return html_text


def render_markdown(report: dict[str, Any]) -> str:
    report = validate(report)
    lines = [
        "# B04 historical table and restoration evidence",
        "",
        "> Historical-only record. The B04 manifest is non-executable. This report contains no solver run or current benchmark measurement.",
        "",
        f"Scenario `B04-historical`. Restoration status: `{report['restoration']['status']}`.",
        "",
        "## Reported terminal rows",
        "",
        f"Source: {report['reported_table']['source_label']}. Printed-coordinate evaluations are separate from reported objectives. The coordinate-rounding bound limits the effect of the displayed coordinate precision; it is not a source-data uncertainty model.",
        "",
        "| Policy | Printed terminal state `(x1, x2, x3, x4)` | Reported objective | Computed at printed coordinates | Rounding bound | Interpretation |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report["reported_table"]["rows"]:
        state = ", ".join(f"{item['value']} (±{item['radius_exact']})" for item in row["terminal_state"])
        objective = row["reported_objective"]
        evaluation = row["printed_coordinate_evaluation"]
        note = row["row_note"] or "reported Table 2 row"
        lines.append(
            f"| {row['policy_label']} | `{state}` | `{objective['value']}` (±{objective['radius_exact']}) "
            f"| `{evaluation['objective_norm']}` | `{evaluation['coordinate_rounding_effect_bound']}` | {note} |")
    stock = report["restoration"]["stock_invariant"]
    lower = report["restoration"]["unrestricted_terminal_plane_minimum"]
    lines.extend([
        "",
        "## Restoration diagnostics",
        "",
        f"- Execution gate: {report['restoration']['execution_gate']}",
        f"- Stock invariant: required `{stock['required_exact']}`; the reported point gives `{stock['reported_point_exact']}`; gap `{stock['gap_exact']}`; coordinate rounding radius `{stock['reported_point_rounding_radius_exact']}`.",
        f"- Unrestricted terminal-plane minimum: `{lower['objective_float']}` with exact squared value `{lower['objective_squared_exact']}`. This is a lower bound for constrained versions of the displayed model, not a constrained optimum or historical reproduction.",
        f"- Provisional interval: `[-1, 1]` is a separate owner recollection from {report['restoration']['excluded_control_interval_hypothesis']['source']}; it is not an input to this historical manifest. The distinct article-derived case is `b04-reference-v1`.",
        "- Missing controls and the first-action convention remain unresolved. The displayed model and reported terminal result remain inconsistent.",
        "",
        "## Runtime and reproduction",
        "",
        f"- Historical reported runtime: `{report['runtime']['historical_reported_seconds']}` seconds. This is publication context, not a current measurement.",
        "- Current measured runtime: unavailable.",
        f"- Reproduction: unavailable. {report['reproduction']['reason']}",
        "",
        "## Sources",
        "",
    ])
    for source in report["source_citations"]:
        digest = source.get("sha256", "not supplied")
        detail = f"SHA-256 `{digest}`" if digest != "not supplied" else f"DOI [{source['doi']}]({source['url']})"
        lines.append(f"- {source['id']}: {source.get('role', '')}; {detail}.")
    lines.extend([
        "",
        f"Manifest SHA-256: `{report['manifest_sha256']}`. Audit SHA-256: `{report['consistency_audit_sha256']}`. Archive-register SHA-256: `{report['archive_register_sha256']}`.",
        "",
        "Rebuild instructions and schema details are in [historical-versus-reproduced](../artifacts/historical-versus-reproduced.md).",
        "",
    ])
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    report = validate(report)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "b04-historical-comparison.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (output_dir / "b04-historical-comparison.html").write_text(render_html(report), encoding="utf-8")
    (output_dir / "b04-historical-comparison.md").write_text(render_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--consistency", type=Path, required=True)
    parser.add_argument("--archive-register", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_report(build(args.manifest, args.consistency, args.archive_register), args.out)


if __name__ == "__main__":
    main()

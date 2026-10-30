"""Build additive gallery companions from frozen control-report evidence."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import statistics
import tempfile
from typing import Literal

import b04_native_smoke_companion
import geometry_figures


SourceRole = Literal[
    "collector", "saved-plot-renderer", "report-plot-renderer",
    "collector-and-plot-renderer", "bundle-composer", "bundle-composer-and-plot-renderer",
    "bundle-regenerator", "publication-mapper", "analytic-diagram-renderer",
]


@dataclass(frozen=True)
class SourceDisposition:
    path: str
    role: SourceRole
    disposition: str
    companion_ids: tuple[str, ...] = ()


# The issue's exact reviewed source set lives here. Keep semantic classification
# separate from the text scan, which remains useful only for finding new hits.
SOURCE_DISPOSITIONS = (
    SourceDisposition("scripts/reports/syn01/collect.py", "collector-and-plot-renderer", "frozen-evidence-collector-preserved-with-gallery-timing-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn01/render_saved.py", "saved-plot-renderer", "frozen-renderer-preserved-with-gallery-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn01/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-saved-timing-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn02/collect.py", "collector-and-plot-renderer", "frozen-evidence-collector-preserved-with-failure-aware-gallery-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn02/publication_map.py", "publication-mapper", "publication-identity-map-preserved"),
    SourceDisposition("scripts/reports/syn02/render_saved.py", "saved-plot-renderer", "frozen-renderer-preserved-with-failure-aware-gallery-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn03/strategy_a_report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-relation-and-timing-companions", ("control-witness-companions", "control-witness-timings")),
    SourceDisposition("scripts/reports/syn03_ts02/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-relation-and-timing-companions", ("control-witness-companions", "control-witness-timings")),
    SourceDisposition("scripts/reports/syn04/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-relation-and-timing-companions", ("control-witness-companions", "control-witness-timings")),
    SourceDisposition("scripts/reports/syn04_ts02/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-relation-and-timing-companions", ("control-witness-companions", "control-witness-timings")),
    SourceDisposition("scripts/reports/syn04_ts03/build_bundle.py", "bundle-composer", "frozen-bundle-composer-preserved"),
    SourceDisposition("scripts/reports/syn04_ts03/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-projection-and-timing-companions", ("control-witness-companions", "control-witness-timings")),
    SourceDisposition("scripts/reports/syn06/collect.py", "collector-and-plot-renderer", "frozen-envelope-collector-preserved-with-gallery-timing-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn_ts01_paired/build_bundle.py", "bundle-composer-and-plot-renderer", "frozen-bundle-composer-preserved-with-saved-timing-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/syn_ts01_paired/regenerate_bundle.py", "bundle-regenerator", "regeneration-entrypoint-preserved-gallery-never-invokes-it"),
    SourceDisposition("scripts/reports/syn_ts01_paired/report.py", "report-plot-renderer", "frozen-report-plot-preserved-with-saved-timing-companion", ("control-witness-timings",)),
    SourceDisposition("scripts/reports/ts01/report.py", "analytic-diagram-renderer", "reviewed-analytic-diagram-preserved"),
    SourceDisposition("scripts/reports/viz04/render_saved.py", "saved-plot-renderer", "adopted-shared-quantitative-policy"),
    SourceDisposition("scripts/reports/mpc06/capture_tube.py", "collector-and-plot-renderer", "frozen-renderer-preserved-with-gallery-companion", ("control-witness-companions",)),
    SourceDisposition("scripts/reports/mpc06/render_tube.py", "saved-plot-renderer", "frozen-renderer-preserved-with-gallery-companion", ("control-witness-companions",)),
    SourceDisposition("scripts/reports/mpc01/summarize_strategy_ab.py", "report-plot-renderer", "frozen-report-plot-preserved-with-gallery-companion", ("control-witness-companions",)),
    SourceDisposition("scripts/reports/mpc01/b04_native_smoke_projection.py", "report-plot-renderer", "frozen-report-plot-preserved-with-phase-plane-companion", ("b04-native-smoke",)),
    SourceDisposition("scripts/reports/mpc01/b04_projection_example.py", "report-plot-renderer", "frozen-report-plot-preserved-with-phase-plane-companion", ("b04-native-smoke",)),
    SourceDisposition("scripts/reports/mpc01/summarize_repeated_comparison.py", "report-plot-renderer", "frozen-repeated-b04-figure-preserved-with-shared-policy-companion", ("b04-repeated-benchmark",)),
    SourceDisposition("scripts/reports/b04_native_smoke_companion.py", "saved-plot-renderer", "shared-quantitative-policy-companion-renderer"),
)

PROJECTIONS = (
    ("syn03-strategy-a-ts01-20261014-451d0f75", "Strategy A · T-S01",
     "(0,s,1,s,1-s), 0<=s<=1", [[0, 1], [1, 0]]),
    ("syn03-strategy-a-ts02-20261014-272fb9a5", "Strategy A · T-S02",
     "(0,s,s+t,s,t), 0<=s<=1, 0<=t<=1", [[0, 0], [1, 0], [1, 1], [0, 1]]),
    ("syn04-strategy-b-ts01-20261014-2a5ab835", "Strategy B · T-S01",
     "(0,s,1,s,1-s), 0<=s<=1", [[0, 1], [1, 0]]),
    ("syn04-strategy-b-ts02-20261014-e7f66a9e", "Strategy B · T-S02",
     "(0,s,s+t,s,t), 0<=s<=1, 0<=t<=1", [[0, 0], [1, 0], [1, 1], [0, 1]]),
    ("syn04-strategy-b-ts03-20261022-2c0c9210", "Strategy B · T-S03",
     "(0,s,1,s,1), 0<=s<=1", [[0, 1], [1, 1]]),
)

STRATEGY_TIMINGS = (
    ("syn03-strategy-a-ts01-20261014-451d0f75", "Strategy A · T-S01 saved timing observations"),
    ("syn03-strategy-a-ts02-20261014-272fb9a5", "Strategy A · T-S02 saved timing observations"),
    ("syn04-strategy-b-ts01-20261014-2a5ab835", "Strategy B · T-S01 saved timing observations"),
    ("syn04-strategy-b-ts02-20261014-e7f66a9e", "Strategy B · T-S02 saved timing observations"),
    ("syn04-strategy-b-ts03-20261022-2c0c9210", "Strategy B · T-S03 saved timing observations"),
)


def strategy_slug(report_id: str) -> str:
    family = "strategy-a" if "syn03-strategy-a-" in report_id else "strategy-b"
    task = next((f"ts0{n}" for n in range(1, 4) if f"-ts0{n}-" in report_id), None)
    if task is None or not report_id.startswith(("syn03-strategy-a-", "syn04-strategy-b-")):
        raise ValueError("unrecognized strategy report identity: " + report_id)
    return family + "-" + task


def asset_paths() -> list[str]:
    paths = ["control-witness-v1.html", "control-witness-timing-v1.html",
             "control-witness/b04-repeated-oxidizer.svg",
             "control-witness/b04-repeated-oxidizer.png",
             "control-witness/b04-repeated-fuel.svg",
             "control-witness/b04-repeated-fuel.png",
             "control-witness/b04-repeated-evidence.json",
             "control-witness/b04-repeated-attempts.jsonl",
             "control-witness/b04-repeated-manifest.json",
             "control-witness/b04-repeated-case.json",
             "control-witness/b04-repeated-reference.json",
             "control-witness/exp02-ts02-control-family.svg",
             "control-witness/exp02-ts02-control-family.png",
             "control-witness/exp02-ts02-control-family-evidence.json",
             "control-witness/exp02-ts02-scenario.json",
             "control-witness/exp02-ts02-events.jsonl",
             "control-witness/exp02-ts03-control-family.svg",
             "control-witness/exp02-ts03-control-family.png",
             "control-witness/exp02-ts03-control-family-evidence.json",
             "control-witness/exp02-ts03-scenario.json",
             "control-witness/exp02-ts03-events.jsonl",
             "control-witness/b04-native-smoke-projections.svg",
             "control-witness/b04-native-smoke-projections.png",
             "control-witness/b04-native-smoke-evidence.json",
             "control-witness/b04-native-smoke-case.json",
             "control-witness/b04-native-smoke-reference.json",
             "control-witness/b04-native-smoke-exact-check.json",
             "control-witness/b04-native-smoke-attempts.jsonl",
             "control-witness/b04-native-smoke-manifest.json",
             "control-witness/mpc06-tube.svg", "control-witness/mpc06-tube.png",
             "control-witness/mpc06-tube-evidence.json",
             "control-witness/ts01-strategy-ab.svg", "control-witness/ts01-strategy-ab.png",
             "control-witness/ts01-strategy-ab-evidence.json",
             "control-witness/ts01-strategy-ab-events.jsonl",
             "control-witness/ts01-strategy-ab-environment.json",
             "control-witness/ts01-strategy-ab-scenario.json"]
    for report_id, *_ in PROJECTIONS:
        stem = "control-witness/" + strategy_slug(report_id)
        paths.extend(stem + suffix for suffix in (".svg", ".png", "-evidence.json"))
    for name in ("syn01", "syn02", "syn06", "syn-ts01-paired"):
        stem = "control-witness/" + name + "-timing"
        paths.extend((stem + ".svg", stem + ".png", stem + "-evidence.json"))
    for report_id, _ in STRATEGY_TIMINGS:
        stem = f"control-witness/{strategy_slug(report_id)}-timing"
        paths.extend((stem + ".svg", stem + ".png", stem + "-evidence.json"))
    return paths


def source_inventory() -> dict[str, SourceDisposition]:
    """Return reviewed role metadata keyed by repository-relative source path."""
    result = {entry.path: entry for entry in SOURCE_DISPOSITIONS}
    if len(result) != len(SOURCE_DISPOSITIONS):
        raise ValueError("duplicate VIZ-09 source disposition")
    return result


def _exp02_control_family_companion(style: Path) -> tuple[dict[str, bytes], str, dict]:
    root = Path(__file__).resolve().parents[2]
    bundle = root / "reports/algorithm-results/exp02-paired-profiles-20261027-r1"
    sums = {}
    for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    source_names = (
        "index.html", "render_report.py", "ts02-constant-integrator.json",
        "raw/ts02_constant_integrator.jsonl", "ts03-singular-integrator.json",
        "raw/ts03_singular_integrator.jsonl",
    )
    raw = {name: (bundle / name).read_bytes() for name in source_names}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    if any(sums.get(name) != value for name, value in hashes.items()):
        raise ValueError("Exp-02 paired-profile source bytes differ from their frozen checksum manifest")
    scenarios = {name: json.loads(raw[f"{name}.json"]) for name in (
        "ts02-constant-integrator", "ts03-singular-integrator")}
    expected = {
        "ts02-constant-integrator": {
            "model": {"kind": "linear_discrete", "A": [[1]], "B": [[1]]},
            "controls": {"kind": "box", "lower": [0], "upper": [1]},
            "objective": {"kind": "linear", "coefficients": [0], "offset": 3},
        },
        "ts03-singular-integrator": {
            "model": {"kind": "linear_discrete", "A": [[0]], "B": [[1]]},
            "controls": {"kind": "box", "lower": [0], "upper": [1]},
            "objective": {"kind": "quadratic", "Q": [[2]], "linear": [-2], "offset": 1},
        },
    }
    scenario_keys = {"schema", "id", "horizon", "model", "initial_state", "controls", "objective"}
    records = {}
    for scenario_id, properties in expected.items():
        scenario = scenarios[scenario_id]
        if (set(scenario) != scenario_keys or scenario.get("schema") != "csl.scenario/1" or
                scenario.get("id") != scenario_id or scenario.get("horizon") != 2 or
                scenario.get("initial_state") != [0] or
                any(scenario.get(key) != value for key, value in properties.items())):
            raise ValueError("Exp-02 paired-profile fixture changed: " + scenario_id)
        event_name = f"raw/{'ts02_constant_integrator' if scenario_id.startswith('ts02') else 'ts03_singular_integrator'}.jsonl"
        rows = [json.loads(line) for line in raw[event_name].decode().splitlines() if line.strip()]
        if (len(rows) != 13 or rows[0].get("event") != "header" or
                rows[0].get("profile") != event_name.removeprefix("raw/").removesuffix(".jsonl")):
            raise ValueError("Exp-02 paired-profile event identity differs: " + scenario_id)
        trials = rows[1:]
        measured = [row for row in trials if row.get("warmup") is False]
        if (len(trials) != 12 or len(measured) != 10 or
                any(row.get("event") != "trial" or row.get("status") != "passed" or
                    row.get("termination") != "completed" or row.get("outcome") != "optimal" or
                    row.get("complete_family_verified") is not True or row.get("distinct_witnesses") != 2
                    for row in trials)):
            raise ValueError("Exp-02 paired-profile saved family evidence is incomplete: " + scenario_id)
        records[scenario_id] = {"scenario": scenario, "rows": rows,
                                "event_name": event_name, "measured_trials": len(measured)}

    projections = (
        ("ts02-constant-integrator", "ts02", "T-S02 · constant objective",
         "Every feasible control pair is optimal because the saved objective is constant.",
         [{"kind": "polygon", "label": "Feasible and complete optimal set", "color": "#2367a8",
           "points": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": True, "alpha": .18},
          {"kind": "polygon", "label": "Optimal boundary", "color": "#b23b33",
           "points": [[0, 0], [1, 0], [1, 1], [0, 1]], "linewidth": 2.3, "linestyle": "--"}]),
        ("ts03-singular-integrator", "ts03", "T-S03 · singular integrator",
         "The saved recurrence gives x₂=u₁ and objective (x₂−1)²; u₀ is free and every optimum has u₁=1.",
         [{"kind": "polygon", "label": "Feasible controls", "color": "#2367a8",
           "points": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": True, "alpha": .18},
          {"kind": "path", "label": "Complete analytic optimal family", "color": "#b23b33",
           "points": [[0, 1], [1, 1]], "linewidth": 2.6}]),
    )
    outputs = {}
    articles = []
    for scenario_id, stem_id, title, description, series in projections:
        item = records[scenario_id]
        outputs[f"control-witness/exp02-{stem_id}-scenario.json"] = raw[f"{scenario_id}.json"]
        outputs[f"control-witness/exp02-{stem_id}-events.jsonl"] = raw[item["event_name"]]
        document = {"schema": "csl.saved-geometric-plot/1", "title": title,
                    "description": description,
                    "axes": {"x": {"label": "Control u₀ (dimensionless)"},
                             "y": {"label": "Control u₁ (dimensionless)"}},
                    "aspect": "equal", "series": series}
        with tempfile.TemporaryDirectory(prefix="csl-viz09-exp02-family-") as temporary:
            generated = Path(temporary)
            export = geometry_figures.render(document, style, generated)
            stem = f"control-witness/exp02-{stem_id}-control-family"
            for suffix in ("svg", "png"):
                outputs[f"{stem}.{suffix}"] = (generated / f"geometry.{suffix}").read_bytes()
        evidence = {"schema": "csl.control-witness-exp02-family/1", "scenario_id": scenario_id,
                    "scenario_sha256": hashes[f"{scenario_id}.json"],
                    "saved_profile_events_sha256": hashes[item["event_name"]],
                    "frozen_index_sha256": hashes["index.html"],
                    "frozen_renderer_sha256": hashes["render_report.py"],
                    "measured_trials": item["measured_trials"],
                    "analytic_relation": description,
                    "displayed_sets": {"feasible_control_square": [[0, 0], [1, 0], [1, 1], [0, 1]],
                                       "optimal_family": ("entire feasible square" if stem_id == "ts02"
                                                          else "u1=1, 0<=u0<=1")},
                    "assurance": "exact algebraic fixture derivation; saved algorithm family checks are numerical",
                    "claim_scope": "Additive presentation of a frozen report; no algorithm, geometry query, or measurement rerun.",
                    "figure_export": export}
        evidence_name = f"control-witness/exp02-{stem_id}-control-family-evidence.json"
        outputs[evidence_name] = (json.dumps(evidence, indent=2, ensure_ascii=False) + "\n").encode()
        page_stem = f"control-witness/exp02-{stem_id}-control-family"
        articles.append(
            f'<article id="exp02-{stem_id}-control-family"><h2>{html.escape(title)}</h2>'
            f'<p>{html.escape(description)} Feasible and optimal control sets are projected onto the exact '
            f'<code>(u₀,u₁)</code> plane with equal axis scaling. The figure is algebraically derived from the '
            f'frozen scenario; the saved paired strategy runs numerically verified their complete families.</p>'
            f'<figure><a href="{page_stem}.svg"><img src="{page_stem}.svg" alt="{html.escape(description, quote=True)}"></a>'
            f'<figcaption>Shared quantitative axis policy; equal data scaling. '
            f'<a href="{page_stem}.png">Open PNG figure ↗</a></figcaption></figure>'
            f'<p><a href="control-witness/exp02-{stem_id}-scenario.json">Frozen scenario input ↗</a> · '
            f'<a href="control-witness/exp02-{stem_id}-events.jsonl">Saved profile events ↗</a> · '
            f'<a href="{evidence_name}">Figure evidence and hashes ↗</a></p></article>')
    entry = {"family": "Control strategy and witness reports",
             "title": "Exp-02 paired-profile optimal control families",
             "status": "saved-data-companion", "anchor": "exp02-paired-family",
             "page": "control-witness-v1.html#exp02-paired-family",
             "figure": "control-witness/exp02-ts02-control-family.svg",
             "source_page": "control-witness-v1.html",
             "raw_record": "control-witness/exp02-ts02-control-family-evidence.json"}
    section = ('<section id="exp02-paired-family"><h2>Exp-02 saved paired-profile control families</h2>' +
               ''.join(articles) + '</section>')
    return outputs, section, entry


def _b04_repeated_companion(style: Path) -> tuple[dict[str, bytes], str, dict]:
    root = Path(__file__).resolve().parents[2]
    evidence_root = root / "docs/research/evidence"
    repeated = evidence_root / "mpc01-external-qps-20261026-r3"
    case_path = evidence_root / "b04-reference-v1/canonical-case.json"
    reference_path = evidence_root / "b04-reference-v1/exact-optimal-reference.json"
    manifest_raw = (repeated / "figure-manifest.json").read_bytes()
    selected_raw = (repeated / "b04-representative-cold-attempts.jsonl").read_bytes()
    comparison_raw = (repeated / "comparison-records.jsonl").read_bytes()
    case_raw, reference_raw = case_path.read_bytes(), reference_path.read_bytes()
    manifest = json.loads(manifest_raw)
    selected = [json.loads(line) for line in selected_raw.decode().splitlines() if line.strip()]
    comparison_records = [json.loads(line) for line in comparison_raw.decode().splitlines() if line.strip()]
    case, reference = json.loads(case_raw), json.loads(reference_raw)
    if (manifest.get("schema") != "csl.mpc01-repeated-benchmark-figure/1" or
            manifest.get("case_id") != "b04-reference-v1" or
            case.get("case_id") != manifest.get("case_id") or
            manifest.get("records_sha256") != hashlib.sha256(comparison_raw).hexdigest() or
            manifest.get("selected_attempts_sha256") != hashlib.sha256(selected_raw).hexdigest() or
            manifest.get("case_sha256") != hashlib.sha256(case_raw).hexdigest() or
            len(selected) != 2 or {row.get("method") for row in selected} !=
            {"osqp-sparse-qp", "hpipm-structured-ocp-qp"}):
        raise ValueError("saved repeated-B04 representative attempts do not match their figure manifest")
    comparison_id = manifest.get("comparison_spec_id")
    b04_record = None
    for record in comparison_records:
        if record.get("comparison_spec_id") == comparison_id:
            b04_record = record
            break
    if b04_record is None:
        raise ValueError("saved repeated-B04 figure manifest names no canonical comparison record")
    spec = json.loads(b04_record.get("spec", "{}"))
    case_hash = hashlib.sha256(case_raw).hexdigest()
    if (spec.get("problem_id") != f"csl.problem.v1.sha256:{case_hash}" or
            spec.get("input_manifest_hash") != case_hash):
        raise ValueError("saved repeated-B04 comparison does not match the canonical case identity")
    if (spec.get("repetitions") != 5 or len(b04_record.get("attempts", [])) != 20):
        raise ValueError("saved repeated-B04 comparison does not establish five repetitions per arm")
    cold_rows = []
    for attempt in b04_record["attempts"]:
        event = json.loads(attempt["measurement_payload"])
        row = event.get("attempt", {})
        if (row.get("case_id") != case.get("case_id") or
                row.get("input_sha256") != case_hash):
            raise ValueError("saved repeated-B04 attempt does not match the canonical case hash")
        if row.get("case_id") == "b04-reference-v1" and row.get("start_mode") == "cold":
            cold_rows.append((attempt["repetition_index"], row))
    by_method: dict[str, list[tuple[int, dict]]] = {}
    for repetition, row in cold_rows:
        by_method.setdefault(row["method"], []).append((repetition, row))
    selection = manifest.get("selection")
    expected_methods = {"osqp-sparse-qp", "hpipm-structured-ocp-qp"}
    if (set(by_method) != expected_methods or any(
            len(rows) != 5 or {rep for rep, _ in rows} != set(range(5))
            for rows in by_method.values()) or
            not isinstance(selection, list) or len(selection) != 2 or
            {item.get("method") for item in selection} != expected_methods):
        raise ValueError("saved repeated-B04 selection does not cover five cold attempts per backend")
    selection_by_method = {item["method"]: item for item in selection}
    selected_by_method = {row["method"]: row for row in selected}
    for method, rows in by_method.items():
        item = selection_by_method[method]
        repetition = item.get("repetition")
        by_repetition = {rep: row for rep, row in rows}
        if (not isinstance(repetition, int) or repetition not in by_repetition or
                item.get("solve_ns") != by_repetition[repetition]["timings_ns"]["solve"] or
                item.get("median_cold_solve_ns") != statistics.median(
                    row["timings_ns"]["solve"] for _, row in rows) or
                selected_by_method[method] != by_repetition[repetition]):
            raise ValueError("saved repeated-B04 path label differs from its canonical attempt")
    if (case.get("state_coordinates") != ["oxidizer_flow", "oxidizer_working_stock", "fuel_flow", "fuel_working_stock"] or
            case.get("state_units") != ["kg/s", "kg", "kg/s", "kg"]):
        raise ValueError("saved B04 coordinate order or units changed")
    exact = reference.get("exact_optimal_states_one_solution")
    if not isinstance(exact, list) or len(exact) != case.get("horizon", -1) + 1 or any(len(row) != 4 for row in exact):
        raise ValueError("saved B04 exact witness has an unexpected trajectory shape")
    exact_states = [[float(Fraction(value)) for value in state] for state in exact]
    if any(row.get("case_id") != case["case_id"] or row.get("start_mode") != "cold" or
           row.get("termination") != "completed" or row.get("mathematical_outcome") != "optimal" or
           len(row.get("trajectory", {}).get("states", [])) != case["horizon"] + 1
           for row in selected):
        raise ValueError("saved B04 representative path is incomplete or has an unexpected outcome")
    display = {"exact-reference": "Exact saved witness"}
    selected_repetitions = {method: item["repetition"] + 1 for method, item in selection_by_method.items()}
    display.update({row["method"]: f"{row['method']} · cold rep {selected_repetitions[row['method']]} of 5"
                    for row in selected})
    projections = ((0, 1, "oxidizer", "Oxidizer flow x₁ (kg/s)", "Oxidizer working stock x₂ (kg)"),
                   (2, 3, "fuel", "Fuel flow x₃ (kg/s)", "Fuel working stock x₄ (kg)"))
    outputs = {
        "control-witness/b04-repeated-attempts.jsonl": selected_raw,
        "control-witness/b04-repeated-manifest.json": manifest_raw,
        "control-witness/b04-repeated-case.json": case_raw,
        "control-witness/b04-repeated-reference.json": reference_raw,
    }
    hashes = {"figure_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
              "comparison_records_sha256": hashlib.sha256(comparison_raw).hexdigest(),
              "selected_attempts_sha256": hashlib.sha256(selected_raw).hexdigest(),
              "case_sha256": hashlib.sha256(case_raw).hexdigest(),
              "exact_reference_sha256": hashlib.sha256(reference_raw).hexdigest()}
    export_receipts = {}
    for x, y, slug, x_label, y_label in projections:
        paths = [{"kind": "path", "label": display["exact-reference"], "color": "#b23b33",
                  "points": [[state[x], state[y]] for state in exact_states], "linewidth": 1.8}]
        for row in selected:
            paths.append({"kind": "path", "label": display[row["method"]],
                          "color": "#2367a8" if row["method"] == "osqp-sparse-qp" else "#2a7f62",
                          "points": [[state[x], state[y]] for state in row["trajectory"]["states"]],
                          "linewidth": 1.8})
        document = {"schema": "csl.saved-geometric-plot/1",
                    "title": f"B04 repeated benchmark · {slug} projection",
                    "description": (f"Exact saved witness and one representative cold trajectory per native solver. "
                                    "Each solver path was selected from five cold repetitions by proximity to its median solve time; "
                                    "it is an individual path, not an average. Solver residual evidence remains inconclusive."),
                    "axes": {"x": {"label": x_label}, "y": {"label": y_label}},
                    "aspect": "independent", "series": paths}
        with tempfile.TemporaryDirectory(prefix="csl-viz09-b04-repeat-") as temporary:
            generated = Path(temporary)
            receipt = geometry_figures.render(document, style, generated)
            stem = f"control-witness/b04-repeated-{slug}"
            for suffix in ("svg", "png"):
                outputs[f"{stem}.{suffix}"] = (generated / f"geometry.{suffix}").read_bytes()
        export_receipts[slug] = receipt
    data = {"schema": "csl.control-witness-b04-repeated/1", "case_id": case["case_id"],
            "comparison_spec_id": comparison_id, "problem_id": spec["problem_id"],
            "input_manifest_hash": spec["input_manifest_hash"],
            "coordinate_pairs": {"oxidizer": ["x1", "x2"], "fuel": ["x3", "x4"]},
            "selection": manifest["selection"], "path_kind": "representative individual cold paths",
            "claim_scope": "Three trajectories projected into two 2D planes; no reachable-set or historical B04 claim.",
            "evidence_status": "native binary64 residual evidence inconclusive",
            **hashes, "figure_exports": export_receipts}
    evidence_name = "control-witness/b04-repeated-evidence.json"
    outputs[evidence_name] = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    articles = []
    for slug, axis_description in (("oxidizer", "oxidizer flow x₁ versus working stock x₂"),
                                   ("fuel", "fuel flow x₃ versus working stock x₄")):
        stem = f"control-witness/b04-repeated-{slug}"
        articles.append(f'<figure><a href="{stem}.svg"><img src="{stem}.svg" alt="Exact saved B04 witness and representative cold solver paths in the {axis_description} plane"></a>'
                        f'<figcaption>{axis_description}; unequal units use independent axis scaling. <a href="{stem}.png">Open PNG ↗</a></figcaption></figure>')
    article = ('<article id="b04-repeated-benchmark"><h2>B04 repeated comparison · representative trajectories</h2>'
               '<p>The panels show the requested fuel-model views: (x₁,x₂) for oxidizer and (x₃,x₄) for fuel. '
               'Each solver trajectory is one saved cold repetition selected by proximity to that backend’s median solve time; '
               'the paths are not averages. The exact witness is separate. Binary64 residual evidence is inconclusive, '
               'so this is an illustrative trajectory companion, not a reachability-set result or a historical B04 reconstruction.</p>' +
               ''.join(articles) + '<p><a href="control-witness/b04-repeated-attempts.jsonl">Representative saved attempt rows ↗</a> · '
               '<a href="control-witness/b04-repeated-reference.json">Exact reference witness ↗</a> · '
               '<a href="control-witness/b04-repeated-manifest.json">Selection manifest ↗</a> · '
               '<a href="control-witness/b04-repeated-evidence.json">Figure data and hashes ↗</a></p></article>')
    entry = {"family": "Control strategy and witness reports",
             "title": "B04 representative solver trajectories in oxidizer/fuel planes",
             "status": "saved-data-companion", "anchor": "b04-repeated-benchmark",
             "page": "control-witness-v1.html#b04-repeated-benchmark",
             "figure": "control-witness/b04-repeated-oxidizer.svg",
             "source_page": "control-witness-v1.html",
             "raw_record": evidence_name}
    return outputs, article, entry


@dataclass(frozen=True)
class BuildResult:
    files: dict[str, bytes]
    gallery_entries: tuple[dict, ...]


@dataclass(frozen=True)
class TimingSet:
    key: str
    title: str
    report_id: str
    record_bytes: bytes
    rows: list[dict]
    description: str
    samples: list[dict] | None = None


def published_routes(catalog_path: Path) -> dict[str, str]:
    """Map immutable source report IDs to their current published route IDs."""
    catalog_path = Path(catalog_path)
    candidates = (catalog_path, catalog_path.with_name("syn06-publications.json"))
    routes: dict[str, str] = {}
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.is_symlink():
            raise ValueError("report catalogue must not be a symlink: " + str(candidate))
        catalogue = json.loads(candidate.read_text(encoding="utf-8"))
        for entry in catalogue.get("reports", ()):
            source_id = entry.get("source_report_id", entry.get("report_id"))
            route_id = entry.get("report_id")
            for identity in (source_id, route_id):
                if not isinstance(identity, str) or any(
                    char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
                    for char in identity
                ):
                    raise ValueError("unsafe report identity in catalogue")
            previous = routes.get(source_id)
            if previous is not None and previous != route_id:
                raise ValueError("ambiguous published route for source report: " + source_id)
            routes[source_id] = route_id
    return routes


def _load_record(site: Path, report_id: str, route_id: str) -> tuple[dict, bytes]:
    if not report_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in report_id):
        raise ValueError("unsafe saved report identity")
    if not route_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in route_id):
        raise ValueError("unsafe published report route")
    route = site / route_id
    path = route / "records.json"
    if route.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe staged record: " + report_id)
    raw = path.read_bytes()
    record = json.loads(raw)
    if record.get("report_id") != report_id:
        raise ValueError("staged record identity differs for " + report_id)
    return record, raw


def _mpc06_tube_companion() -> tuple[str, bytes, bytes, bytes]:
    """Render only the exact geometry retained in the immutable MPC-06 bundle."""
    root = Path(__file__).resolve().parents[2]
    bundle = root / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1"
    expected = {"README.md", "capture.json", "figure-data.json", "index.html",
                "projection.svg", "result.json", "scenario.json", "SHA256SUMS"}
    if bundle.is_symlink() or not bundle.is_dir() or {path.name for path in bundle.iterdir()} != expected:
        raise ValueError("MPC-06 frozen report inventory differs")
    files = {name: (bundle / name).read_bytes() for name in expected}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate MPC-06 frozen report checksum")
        checksums[name] = digest
    actual = {name: hashlib.sha256(value).hexdigest()
              for name, value in files.items() if name != "SHA256SUMS"}
    if checksums != actual:
        raise ValueError("MPC-06 frozen report checksum mismatch")
    result = json.loads(files["result.json"])
    plot_data = json.loads(files["figure-data.json"])
    scenario = json.loads(files["scenario.json"])
    if (result.get("schema") != "csl.mpc06-nilpotent-tube-pilot/1" or
            plot_data.get("schema") != "csl.mpc06-tube-figure-data/1" or
            scenario.get("scenario_id") != result.get("case_id") or
            scenario.get("state_order") != ["position", "velocity"]):
        raise ValueError("MPC-06 saved identities or state order differ")

    # Match stage_mpc06_tube.py's immutable route derivation without staging or
    # rerunning its solver, checker, or geometry producer.
    route_identity = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    route_bytes = json.dumps(route_identity, sort_keys=True, separators=(",", ":")).encode()
    route_id = "mpc06-tube-" + hashlib.sha256(route_bytes).hexdigest()[:20]
    sets = plot_data["sets"]

    def rectangle(bounds: list[list[float]]) -> list[list[float]]:
        (xmin, xmax), (ymin, ymax) = bounds
        return [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]

    document = {
        "schema": "csl.saved-geometric-plot/1",
        "title": "MPC-06 exact tube and tightened state constraints",
        "description": ("Saved exact state box, support-tightened state box and dyadic RPI tube "
                        "for one position-velocity fixture with no declared physical units. This is a feasibility picture, "
                        "not an optimized or minimax reachable set."),
        "axes": {"x": {"label": "Position state x₁ (model coordinate)"},
                 "y": {"label": "Velocity state x₂ (model coordinate)"}},
        "aspect": "equal",
        "series": [
            {"kind": "polygon", "label": "State constraint X", "color": "#6b7280",
             "points": rectangle(sets["state_box_X"]["bounds"]), "linestyle": "--"},
            {"kind": "polygon", "label": "Tightened state set X ⊖ Z", "color": "#d97706",
             "points": rectangle(sets["tightened_state_X_minus_Z"]["bounds"]),
             "fill": True, "alpha": .18},
            {"kind": "polygon", "label": "Exact RPI error tube Z", "color": "#0072b2",
             "points": sets["error_tube_Z"]["vertices"], "fill": True, "alpha": .42},
        ],
    }
    style = Path(__file__).with_name("styles") / "control-v1.json"
    with tempfile.TemporaryDirectory(prefix="csl-viz09-mpc06-") as temporary:
        generated = Path(temporary)
        geometry_figures.render(document, style, generated)
        figure_svg = (generated / "geometry.svg").read_bytes()
        figure_png = (generated / "geometry.png").read_bytes()
        export = json.loads((generated / "export.json").read_text(encoding="utf-8"))
    evidence = {
        "schema": "csl.control-witness-mpc06-tube-companion/1",
        "source_report": "mpc06-nilpotent-tube-pilot-v1",
        "published_route": route_id,
        "result_sha256": actual["result.json"],
        "figure_data_sha256": actual["figure-data.json"],
        "scenario_sha256": actual["scenario.json"],
        "profile": {
            "state_dimension": len(scenario["state_order"]),
            "state_order": scenario["state_order"],
            "horizon_steps": scenario["nominal_plan"]["horizon_steps"],
            "feedback_law": scenario["feedback"]["law"],
            "feedback_gain": result["system"]["K"],
        },
        "plot_data": plot_data,
        "figure_export": export,
        "claim_scope": "presentation of frozen saved geometry; no solver or geometry query",
    }
    evidence_bytes = (json.dumps(evidence, indent=2) + "\n").encode()
    return route_id, figure_svg, figure_png, evidence_bytes


def _ts01_strategy_ab_companion() -> dict[str, bytes]:
    """Replot saved T-S01 selected controls without replaying a strategy."""
    root = Path(__file__).resolve().parents[2]
    evidence = root / "docs/research/evidence/mpc01-external-qps-20261026-r3"
    names = ("strategy-ab-ts01-events.jsonl", "strategy-ab-ts01-stdout.jsonl",
             "strategy-ab-ts01-environment.json")
    if evidence.is_symlink() or not evidence.is_dir():
        raise ValueError("T-S01 Strategy A/B evidence directory is missing or unsafe")
    paths = {name: evidence / name for name in names}
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError("T-S01 Strategy A/B evidence file is missing or unsafe")
    raw = {name: path.read_bytes() for name, path in paths.items()}
    if raw[names[0]] != raw[names[1]]:
        raise ValueError("T-S01 Strategy A/B event and stdout evidence differ")
    scenario_path = root / "examples/scenarios/two-stage-integrator.json"
    if scenario_path.is_symlink() or not scenario_path.is_file():
        raise ValueError("T-S01 scenario is missing or unsafe")
    scenario_bytes = scenario_path.read_bytes()
    scenario = json.loads(scenario_bytes)
    environment = json.loads(raw[names[2]])
    events = [json.loads(line) for line in raw[names[0]].decode("utf-8").splitlines() if line]
    if len(events) != 17 or events[0].get("event") != "header":
        raise ValueError("T-S01 Strategy A/B evidence must contain one header and 16 trials")
    header, trials = events[0], events[1:]
    scenario_hash = hashlib.sha256(scenario_bytes).hexdigest()
    if (header.get("schema") != "csl.synthesis.paired-ts01-event/1" or
            header.get("profile") != "ts01_exact_integrator" or
            header.get("assurance") != "numerical" or
            header.get("target") != "exact_optimal_relation" or
            header.get("representation") != "csl.polyhedron.h" or
            header.get("scenario_sha256") != scenario_hash or
            environment.get("scenario_sha256") != scenario_hash or
            environment.get("scenario") != "examples/scenarios/two-stage-integrator.json"):
        raise ValueError("T-S01 Strategy A/B evidence is not bound to the saved scenario")
    if (scenario.get("id") != "two-stage-integrator" or scenario.get("horizon") != 2 or
            scenario.get("initial_state") != [0] or scenario.get("model") != {"kind": "linear_discrete", "A": [[1]], "B": [[1]]} or
            scenario.get("controls") != {"kind": "box", "lower": [0], "upper": [1]} or
            scenario.get("objective") != {"kind": "quadratic", "Q": [[2]], "linear": [-2], "offset": 1}):
        raise ValueError("T-S01 saved scenario differs from the reviewed two-stage integrator")

    strategies = {"csl.synthesis.reach-back", "csl.synthesis.strategy-b"}
    selected = {strategy: set() for strategy in strategies}
    warmups = [row for row in trials if row.get("warmup")]
    measured = [row for row in trials if not row.get("warmup")]
    if len(warmups) != 2 or len(measured) != 14:
        raise ValueError("T-S01 Strategy A/B run must retain one warmup pair and seven measured pairs")
    measurement = environment.get("measurement", {})
    if (measurement.get("event_count_including_header") != 17 or
            measurement.get("warmup_pairs_excluded") != 1 or
            measurement.get("measured_alternating_pairs") != 7):
        raise ValueError("T-S01 saved run metadata differs from its event rows")
    for index, row in enumerate(trials):
        if (row.get("event") != "trial" or row.get("strategy") not in strategies or
                row.get("status") != "passed" or row.get("termination") != "completed" or
                row.get("outcome") != "optimal" or row.get("distinct_witnesses") != 2 or
                row.get("complete_family_verified") is not True):
            raise ValueError("T-S01 Strategy A/B saved trial is incomplete or failed")
        if row.get("repetition") != index // 2 or row.get("order_position") != index % 2:
            raise ValueError("T-S01 Strategy A/B saved trial order differs")
        expected_order = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
        if row["repetition"] > 0 and row["repetition"] % 2 == 0:
            expected_order = tuple(reversed(expected_order))
        if row["strategy"] != expected_order[row["order_position"]]:
            raise ValueError("T-S01 Strategy A/B saved trials do not alternate execution order")
        if not row["warmup"]:
            if (row["verification_summary"].get("optimality") != "unsupported" or
                    row["verification_summary"].get("completeness") != "unsupported"):
                raise ValueError("T-S01 selected-witness check overstates its guarantees")
        for witness in row.get("witnesses", []):
            controls = witness.get("controls")
            if not isinstance(controls, list) or len(controls) != 2 or any(
                    not isinstance(control, list) or len(control) != 1 for control in controls):
                raise ValueError("T-S01 selected history has an unexpected shape")
            point = (float(controls[0][0]), float(controls[1][0]))
            if (not all(0 <= value <= 1 for value in point) or sum(point) != 1.0 or
                    witness.get("original_objective") != 0 or witness.get("recomputed_objective") != 0):
                raise ValueError("T-S01 selected history does not satisfy its exact saved optimum")
            if not row["warmup"]:
                if any(witness.get("verification", {}).get(key) != "numerical_pass"
                       for key in ("bindings", "feasibility", "objective")):
                    raise ValueError("T-S01 selected history lacks original-data witness checks")
                selected[row["strategy"]].add(point)
    if any(len(points) != 2 or sum(
            row.get("strategy") == strategy and not row.get("warmup") for row in trials) != 7
           for strategy, points in selected.items()):
        raise ValueError("T-S01 Strategy A/B measured histories differ from the two saved witnesses")

    point_a = [list(point) for point in sorted(selected["csl.synthesis.reach-back"])]
    point_b = [list(point) for point in sorted(selected["csl.synthesis.strategy-b"])]
    geometry = {
        "schema": "csl.saved-geometric-plot/1",
        "title": "T-S01 saved Strategy A/B controls and exact optimal family",
        "description": ("Filled markers and outlined rings are the two distinct selected histories saved by each strategy. "
                        "Both strategies selected (0,1) and (1,0). The dashed segment is the exact minimizing family "
                        "u₀+u₁=1 for the two-stage integrator. The axes are dimensionless controls with equal data scaling; "
                        "this is a control projection, not a state-space reachable set."),
        "axes": {"x": {"label": "First-stage control u₀"},
                 "y": {"label": "Second-stage control u₁"}},
        "aspect": "equal",
        "series": [
            {"kind": "path", "label": "Exact minimizing family u₀+u₁=1", "color": "#4b5563",
             "points": [[0, 1], [1, 0]], "linestyle": "--", "linewidth": 1.5},
            {"kind": "points", "label": "Strategy A: reach-back selected histories", "color": "#0072b2",
             "points": point_a, "size": 42},
            *[{"kind": "circle", "label": f"Strategy B: selected history ({point[0]:g}, {point[1]:g})",
               "color": "#b23b33", "center": point, "radius": .022, "linewidth": 1.6}
              for point in point_b],
        ],
    }
    style = Path(__file__).with_name("styles") / "control-v1.json"
    with tempfile.TemporaryDirectory(prefix="csl-viz09-ts01-") as temporary:
        generated = Path(temporary)
        geometry_figures.render(geometry, style, generated)
        figure_svg = (generated / "geometry.svg").read_bytes()
        figure_png = (generated / "geometry.png").read_bytes()
        export = json.loads((generated / "export.json").read_text(encoding="utf-8"))
    source_script = root / "scripts/reports/mpc01/summarize_strategy_ab.py"
    if source_script.is_symlink() or not source_script.is_file():
        raise ValueError("T-S01 source report script is missing or unsafe")
    plot_data = {"schema": "csl.control-witness-ts01-strategy-ab/1",
                 "strategies": {"csl.synthesis.reach-back": point_a,
                                "csl.synthesis.strategy-b": point_b},
                 "optimal_family": {"relation": "u₀ + u₁ = 1", "vertices": [[0, 1], [1, 0]]},
                 "controls": {"lower": [0], "upper": [1]}, "horizon_steps": 2,
                 "axes": {"x": "u₀", "y": "u₁", "units": "dimensionless"},
                 "aspect": "equal"}
    evidence = {
        "schema": "csl.control-witness-ts01-strategy-ab-evidence/1",
        "scenario_id": scenario["id"], "source_commit": environment["source_commit"],
        "driver_sha256": environment["source_file_sha256"],
        "report_renderer_sha256": hashlib.sha256(source_script.read_bytes()).hexdigest(),
        "scenario_sha256": scenario_hash,
        "events_sha256": hashlib.sha256(raw[names[0]]).hexdigest(),
        "stdout_sha256": hashlib.sha256(raw[names[1]]).hexdigest(),
        "environment_sha256": hashlib.sha256(raw[names[2]]).hexdigest(),
        "state_dimension": len(scenario["model"]["A"]), "horizon_steps": scenario["horizon"],
        "objective": scenario["objective"], "plot_data": plot_data,
        "figure_export": export,
        "claim_scope": ("presentation of saved selected controls and exact T-S01 minimizer relation; "
                        "no solver, strategy, benchmark, or geometry query"),
    }
    outputs = {
        "control-witness/ts01-strategy-ab.svg": figure_svg,
        "control-witness/ts01-strategy-ab.png": figure_png,
        "control-witness/ts01-strategy-ab-evidence.json": (json.dumps(evidence, indent=2, ensure_ascii=False) + "\n").encode(),
        "control-witness/ts01-strategy-ab-events.jsonl": raw[names[0]],
        "control-witness/ts01-strategy-ab-environment.json": raw[names[2]],
        "control-witness/ts01-strategy-ab-scenario.json": scenario_bytes,
    }
    return outputs


def build(site: Path, catalog_path: Path) -> BuildResult:
    """Build companions from staged published records only."""
    site = Path(site).resolve(strict=True)
    routes = published_routes(catalog_path)

    def load_record(report_id: str) -> tuple[dict, bytes]:
        try:
            route_id = routes[report_id]
        except KeyError as error:
            raise ValueError("saved report is absent from publication catalogues: " + report_id) from error
        return _load_record(site, report_id, route_id)

    style = Path(__file__).with_name("styles") / "control-v1.json"
    outputs: dict[str, bytes] = {}
    cards: list[dict] = []
    outputs.update(_ts01_strategy_ab_companion())
    exp02_files, exp02_article, exp02_entry = _exp02_control_family_companion(style)
    outputs.update(exp02_files)
    b04_repeat_files, b04_repeat_article, b04_repeat_entry = _b04_repeated_companion(style)
    outputs.update(b04_repeat_files)
    b04_files, b04_article, b04_entry = b04_native_smoke_companion.build(style)
    outputs.update(b04_files)
    mpc06_route, mpc06_svg, mpc06_png, mpc06_evidence = _mpc06_tube_companion()
    outputs["control-witness/mpc06-tube.svg"] = mpc06_svg
    outputs["control-witness/mpc06-tube.png"] = mpc06_png
    outputs["control-witness/mpc06-tube-evidence.json"] = mpc06_evidence

    for report_id, title, expected_relation, points in PROJECTIONS:
        record, record_bytes = load_record(report_id)
        route_id = routes[report_id]
        relation = record.get("canonical_relation", {}).get("parametric_form")
        if relation != expected_relation:
            raise ValueError("saved relation differs for " + report_id)
        slug = strategy_slug(report_id)
        if "ts03" in report_id:
            description = ("Projection of the saved five-coordinate joint relation onto (u₀,u₁). "
                           "The line does not display the complete joint relation.")
        elif "ts02" in report_id:
            description = ("Projection of the saved five-coordinate joint relation onto (u₀,u₁). "
                           "The square is the complete control projection; it is not a state-space plot.")
        else:
            description = ("Projection of the saved five-coordinate joint relation onto (u₀,u₁). "
                           "The segment is the full control projection for this saved fixture.")
        geometry = {
            "schema": "csl.saved-geometric-plot/1", "title": title + " · control projection",
            "description": description + " Saved parametric form: " + relation + ".",
            "axes": {"x": {"label": "Control u₀ (saved coordinate units)"},
                     "y": {"label": "Control u₁ (saved coordinate units)"}},
            "aspect": "equal", "series": [{"kind": "polygon" if len(points) > 2 else "path",
                "label": "Saved exact control projection", "color": "#2367a8", "points": points,
                "fill": len(points) > 2, "alpha": .18, "marker": "o"}],
        }
        with tempfile.TemporaryDirectory(prefix="csl-viz09-") as temporary:
            generated = Path(temporary)
            geometry_figures.render(geometry, style, generated)
            stem = "control-witness/" + slug
            for suffix in ("svg", "png"):
                outputs[stem + "." + suffix] = (generated / ("geometry." + suffix)).read_bytes()
            export = json.loads((generated / "export.json").read_text())
        raw_hash = hashlib.sha256(record_bytes).hexdigest()
        outputs[stem + "-evidence.json"] = (json.dumps({
            "schema": "csl.control-witness-evidence/1", "report_id": report_id,
            "published_report_id": route_id,
            "record_sha256": raw_hash, "parametric_form": relation,
            "coordinates": record["canonical_relation"]["coordinates"],
            "projection": {"axes": ["u0", "u1"], "vertices": points,
                           "meaning": description}, "figure_export": export,
        }, indent=2, ensure_ascii=False) + "\n").encode()
        cards.append({"title": title, "report_id": report_id, "route_id": route_id, "stem": stem,
                      "description": description, "relation": relation,
                      "vertices": points})

    timing_sets = []
    syn01_id = "syn01-nominal-20261013-f7ba310d-48a679cfc0d4"
    syn01, syn01_bytes = load_record(syn01_id)
    rows = []
    for scenario in syn01["summary"]:
        for phase in ("setup_ns", "solve_ns", "execute_ns"):
            stats = scenario["phases"][phase]
            rows.append({"label": f"{scenario['scenario']} · {phase.removesuffix('_ns')}",
                         "median": stats["median_ns"], "minimum": stats["min_ns"],
                         "maximum": stats["max_ns"], "status": f"{stats['available_trials']} of {scenario['attempts']} trials"})
    timing_sets.append(TimingSet("syn01", "SYN01 saved phase timings", syn01_id, syn01_bytes, rows,
                        "The figure plots per-phase medians. The table gives the observed minimum and maximum; phases are separate measurements."))

    syn02_id = "syn02-terminal-20261013-c234a1a0-35de886a7fb4"
    syn02, syn02_bytes = load_record(syn02_id)
    rows = []
    for scenario in syn02["summary"]:
        if not scenario["completed"]:
            terminations = ", ".join(scenario.get("observed_terminations", {})) or "termination unavailable"
            status = f"failed: {terminations}; {scenario['non_success']} non-success outcomes; no timing available"
        else:
            status = f"{scenario['completed']} completed"
        timings = scenario.get("timings", {})
        for phase in ("prepare_ns", "solve_ns", "execute_ns"):
            stats = timings.get(phase)
            rows.append({"label": f"{scenario['scenario']} · {phase.removesuffix('_ns')}",
                         "median": stats.get("median_ns") if stats else None,
                         "minimum": stats.get("min_ns") if stats else None,
                         "maximum": stats.get("max_ns") if stats else None,
                         "status": status})
    timing_sets.append(TimingSet("syn02", "SYN02 saved terminal timing observations", syn02_id, syn02_bytes, rows,
                        "The figure plots saved medians; the table gives ranges for completed fixtures. The failed shifted-residual fixture remains listed with no timing."))

    syn06_id = "syn06-verifier-20261012-f0e32e2b"
    syn06, syn06_bytes = load_record(syn06_id)
    rows = []
    for item in syn06["payload"]["summary"]:
        batch = item["batch"]
        rows.append({"label": item["fixture"] + " · median elapsed / batch",
                     "median": item["median_elapsed_ns"] / batch,
                     "minimum": item["min_elapsed_ns"] / batch,
                     "maximum": item["max_elapsed_ns"] / batch,
                     "status": f"{item['trials']} trials · {item['checked_calls']} checked calls · batch {batch}",
                     "saved_median_elapsed_ns": item["median_elapsed_ns"], "batch": batch})
    timing_sets.append(TimingSet("syn06", "SYN06 saved verifier timings", syn06_id, syn06_bytes, rows,
                        "Points show the archived median elapsed nanoseconds divided by the archived batch size; the exact source median and batch are in the evidence table."))

    paired_id = "syn-ts01-paired-20261014-b7f1ac0"
    paired, paired_bytes = load_record(paired_id)
    samples = []
    rows = []
    strategies = {name: index for index, name in enumerate(paired["strategies"])}
    for event in paired["measurement"]["events"]:
        if event.get("event") != "trial":
            continue
        timing = event.get("timings_ns", {}).get("end_to_end_strategy", {})
        available = timing.get("available") is True and isinstance(timing.get("value"), (float, int))
        label = f"{event['strategy']} · repetition {event['repetition']} · {event['status']}"
        rows.append({"label": label, "median": timing.get("value") if available else None,
                     "minimum": None, "maximum": None, "status": event["status"]})
        if available:
            samples.append({"label": event["strategy"], "value": timing["value"],
                            "y": event["repetition"] + strategies[event["strategy"]] * .12})
    timing_sets.append(TimingSet("syn-ts01-paired", "Paired SYN-TS01 end-to-end timings", paired_id, paired_bytes, rows,
                        "Each point is one saved end-to-end strategy observation; the inclusive total is not a sum of other phase durations.", samples))

    for report_id, title in STRATEGY_TIMINGS:
        record, record_bytes = load_record(report_id)
        timing = record.get("measurement", {}).get("timing_ns", {})
        observations = timing.get("observations")
        if not isinstance(observations, list) or len(observations) != 7:
            raise ValueError("expected seven saved timing observations for " + report_id)
        rows = [{"label": f"measured repetition {index + 1}", "median": value,
                 "minimum": value, "maximum": value, "status": "saved observation"}
                for index, value in enumerate(observations)]
        timing_sets.append(TimingSet(strategy_slug(report_id) + "-timing", title, report_id, record_bytes, rows,
                            "Each point is one of the seven saved non-warmup elapsed-time observations, in nanoseconds."))

    timing_cards = []
    for item in timing_sets:
        key, title, report_id, record_bytes, rows, description = (
            item.key, item.title, item.report_id, item.record_bytes, item.rows, item.description)
        record_hash = hashlib.sha256(record_bytes).hexdigest()
        points = ([[row["median"], index] for index, row in enumerate(rows) if row["median"] is not None]
                  if item.samples is None else [[sample["value"], sample["y"]] for sample in item.samples])
        if not points:
            raise ValueError("saved timing companion has no available observations: " + key)
        stem = "control-witness/" + (key if key.startswith("strategy-") else key + "-timing")
        series = [{"kind": "points", "label": "Saved timing observations", "color": "#b23b33", "points": points}]
        if item.samples is not None:
            series = [{"kind": "points", "label": strategy, "color": color,
                       "points": [[sample["value"], sample["y"]] for sample in item.samples
                                  if sample["label"] == strategy]}
                      for strategy, color in zip(paired["strategies"], ("#b23b33", "#2367a8"))]
        document = {"schema": "csl.saved-geometric-plot/1", "title": title,
                    "description": description,
                    "axes": {"x": {"label": "Duration (ns/call)" if key == "syn06" else "Duration (ns)"},
                             "y": {"label": "Saved observation row" if item.samples is None else "Paired repetition"}},
                    "aspect": "independent", "series": series}
        with tempfile.TemporaryDirectory(prefix="csl-viz09-time-") as temporary:
            generated = Path(temporary)
            geometry_figures.render(document, style, generated)
            for suffix in ("svg", "png"):
                outputs[stem + "." + suffix] = (generated / ("geometry." + suffix)).read_bytes()
            export = json.loads((generated / "export.json").read_text())
        outputs[stem + "-evidence.json"] = (json.dumps({"schema": "csl.control-witness-timing/1",
            "report_id": report_id, "published_report_id": routes[report_id],
            "record_sha256": record_hash, "description": description,
            "rows": rows, "figure_export": export}, indent=2, ensure_ascii=False) + "\n").encode()
        table = "".join("<tr><th>" + html.escape(row["label"]) + "</th><td>" +
            (html.escape(str(row["median"])) if row["median"] is not None else "Unavailable") +
            "</td><td>" + (html.escape(str(row["minimum"])) if row["minimum"] is not None else "—") +
            "</td><td>" + (html.escape(str(row["maximum"])) if row["maximum"] is not None else "—") +
            "</td><td>" + html.escape(row["status"]) + "</td></tr>" for row in rows)
        timing_cards.append("<article><h2>" + html.escape(title) + "</h2><p>" + html.escape(description) +
            "</p><figure><img src=\"" + stem + ".svg\" alt=\"" + html.escape(description, quote=True) +
            "\"><figcaption><a href=\"" + stem + ".png\">Open PNG figure ↗</a></figcaption></figure><table><caption>Exact displayed timing values; units are stated on the figure</caption><thead><tr><th>Observation</th>"
            "<th>Median or sample</th><th>Minimum</th><th>Maximum</th><th>Status</th></tr></thead><tbody>" + table +
            "</tbody></table><p><a href=\"../" + routes[report_id] + "/records.json\">Raw saved record ↗</a> · "
            "<a href=\"" + stem + "-evidence.json\">Evidence data ↗</a></p></article>")

    outputs["control-witness-timing-v1.html"] = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Saved control report timings</title><link rel="stylesheet" href="examples.css"></head><body class="control-witness-page"><main>'
        '<p><a href="index.html">← Visual examples</a></p><h1>Saved control report timing figures</h1>' +
        ''.join(timing_cards) + '</main></body></html>').encode()
    timing_entry = {"family": "Control strategy and witness reports", "title": "Saved SYN report timings",
                    "status": "saved-data-companion", "anchor": "control-witness-timings",
                    "page": "control-witness-timing-v1.html", "figure": "control-witness/syn01-timing.svg",
                    "source_page": "../" + routes[syn01_id] + "/index.html",
                    "raw_record": "../" + routes[syn01_id] + "/records.json"}

    body = [b04_article, exp02_article, b04_repeat_article]
    for card in cards:
        record_link = "../" + card["route_id"] + "/records.json"
        page_link = "../" + card["route_id"] + "/index.html"
        stem = card["stem"]
        table_rows = "".join(f"<tr><th>({p[0]}, {p[1]})</th><td>saved projection vertex</td></tr>" for p in card["vertices"])
        body.append(
            '<article><h2>' + html.escape(card["title"]) + '</h2><p>' + html.escape(card["description"]) +
            '<br>Saved parametric relation: <code>' + html.escape(card["relation"]) + '</code>.</p>'
            '<figure><a href="' + stem + '.svg"><img src="' + stem + '.svg" alt="' +
            html.escape(card["description"], quote=True) + '"></a><figcaption>Projection axes: u₀ and u₁. '
            'Exact saved vertices are listed below. <a href="' + stem + '.png">Open PNG figure ↗</a></figcaption></figure>'
            '<table><caption>Exact displayed projection vertices</caption><thead><tr><th>Coordinates</th><th>Meaning</th></tr></thead><tbody>' +
            table_rows + '</tbody></table><p><a href="' + record_link + '">Raw saved record ↗</a> · '
            '<a href="' + page_link + '">Published report ↗</a> · <a href="' + stem + '-evidence.json">Figure evidence JSON ↗</a></p></article>')
    mpc06_bounds = json.loads(mpc06_evidence)["plot_data"]["sets"]
    mpc06_profile = json.loads(mpc06_evidence)["profile"]
    state_box_bounds = mpc06_bounds["state_box_X"]["bounds"]
    state_bounds = mpc06_bounds["tightened_state_X_minus_Z"]["bounds"]
    tube_vertices = mpc06_bounds["error_tube_Z"]["vertices"]
    body.append(
        '<article id="ts01-strategy-ab"><h2>T-S01 · Strategy A/B selected controls</h2>'
        '<p>The scalar two-stage integrator uses <code>x₀=0</code>, <code>xₜ₊₁=xₜ+uₜ</code>, '
        '<code>uₜ∈[0,1]</code>, and terminal objective <code>(x₂−1)²</code>. Filled markers show '
        'the two distinct histories selected by Strategy A (reach-back); red rings show the saved '
        'histories selected by Strategy B (paired capture). Both selected the histories '
        '<code>(0,1)</code> and <code>(1,0)</code>. The dashed segment is the exact minimizing family '
        '<code>u₀+u₁=1</code>. Axes are dimensionless controls plotted with equal data scaling. '
        'Selected-witness checks passed numerically, while separate optimality and completeness checks '
        'are unsupported. This is not the full #597 comparison matrix or a performance ranking.</p>'
        '<figure><a href="control-witness/ts01-strategy-ab.svg"><img src="control-witness/ts01-strategy-ab.svg" '
        'alt="Strategy A and B selected control histories on the exact line u0 plus u1 equals one, with equal data scaling"></a>'
        '<figcaption>Numeric ticks and major gridlines follow csl-report-quantitative-v1. '
        '<a href="control-witness/ts01-strategy-ab.png">Open PNG figure ↗</a></figcaption></figure>'
        '<p><a href="control-witness/ts01-strategy-ab-events.jsonl">Saved paired events ↗</a> · '
        '<a href="control-witness/ts01-strategy-ab-environment.json">Run environment metadata ↗</a> · '
        '<a href="control-witness/ts01-strategy-ab-scenario.json">Scenario input ↗</a> · '
        '<a href="control-witness/ts01-strategy-ab-evidence.json">Figure data, checks and hashes ↗</a></p></article>')

    body.append(
        '<article id="mpc06-tube"><h2>MPC-06 · exact tube feasibility geometry</h2>'
        '<p>This two-state discrete double-integrator fixture uses a three-step horizon. '
        'The checked feasibility case uses the fixed zero nominal plan and full-state feedback '
        '<code>' + html.escape(mpc06_profile["feedback_law"]) + '</code> with '
        '<code>K=' + html.escape(str(mpc06_profile["feedback_gain"])) + '</code>. '
        'The figure re-plots the frozen position–velocity box, support tightening and exact dyadic RPI tube. '
        'The source declares no physical units for the state coordinates; equal data scaling is a display choice, '
        'not physical dimensional scaling. The underlying study checks feasibility and safety for one fixed '
        'nilpotent profile; it does not optimize an objective or compute a minimax reachable set.</p>'
        '<figure><a href="control-witness/mpc06-tube.svg"><img src="control-witness/mpc06-tube.svg" '
        'alt="Saved position-velocity state box, tightened state set, and exact RPI tube on equal numeric axes"></a>'
        '<figcaption>Numeric ticks and major gridlines follow csl-report-quantitative-v1. '
        '<a href="control-witness/mpc06-tube.png">Open PNG figure ↗</a></figcaption></figure>'
        '<div class="scroll" tabindex="0" role="region" aria-label="MPC-06 saved geometry coordinates">'
        '<table><caption>Exact values retained in the frozen result</caption><thead><tr><th scope="col">Set</th>'
        '<th scope="col">Saved coordinates</th></tr></thead><tbody>'
        '<tr><th scope="row">State constraint X</th><td>' + html.escape(str(state_box_bounds)) + '</td></tr>'
        '<tr><th scope="row">Tightened state set X ⊖ Z</th><td>' + html.escape(str(state_bounds)) + '</td></tr>'
        '<tr><th scope="row">Exact RPI error tube Z</th><td>' + html.escape(str(tube_vertices)) + '</td></tr>'
        '</tbody></table></div><p><a href="../' + mpc06_route + '/index.html">Frozen MPC-06 report ↗</a> · '
        '<a href="../' + mpc06_route + '/result.json">Saved result ↗</a> · '
        '<a href="../' + mpc06_route + '/figure-data.json">Original saved figure data ↗</a> · '
        '<a href="control-witness/mpc06-tube-evidence.json">Companion data and hashes ↗</a></p></article>')
    outputs["control-witness-v1.html"] = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Saved control figures · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css">'
        '<style>.control-witness-page #b04-native-smoke th,.control-witness-page #b04-native-smoke td{white-space:normal;vertical-align:top}'
        '@media print{.control-witness-page #b04-native-smoke{break-inside:auto;page-break-inside:auto}'
        '.control-witness-page #b04-native-smoke h2{break-after:avoid;page-break-after:avoid}'
        '.control-witness-page #b04-native-smoke figure{break-inside:avoid;page-break-inside:avoid}'
        '.control-witness-page #b04-native-smoke .scroll{overflow:visible;margin:.5rem 0}}</style></head>'
        '<body class="control-witness-page"><main><p><a href="index.html">← Visual examples</a></p><h1>Saved control and witness figures</h1>'
        '<p>The first five figures show projections of frozen five-coordinate state/control relations into the control plane '
        '(u₀,u₁); each can omit distinctions present in the full joint relation. The MPC-06 figure re-plots a saved two-state '
        'feasibility tube. The T-S01 figure shows saved Strategy A/B control histories and an exact analytic minimizer relation. '
        'The Exp-02 and B04 companions replot frozen control-family and representative trajectory evidence. '
        'These companions do not run a solver or recompute scientific geometry.</p>' +
        ''.join(body) + '</main></body></html>').encode()
    strategy_ab_entry = {
        "family": "Control strategy and witness reports",
        "title": "T-S01 Strategy A/B selected histories and exact minimizer family",
        "status": "saved-data-companion", "anchor": "ts01-strategy-ab",
        "page": "control-witness-v1.html#ts01-strategy-ab",
        "figure": "control-witness/ts01-strategy-ab.svg",
        "source_page": ("https://github.com/butahlecoq/controlled-systems-lab/blob/"
                        "bccf2d5a985d7dd8cbfc15f86b2867cf266fbc37/docs/research/evidence/"
                        "mpc01-external-qps-20261026-r3/strategy-ab-ts01-summary.html"),
        "raw_record": "control-witness/ts01-strategy-ab-evidence.json",
    }
    entries = ({"family": "Control strategy and witness reports",
                "title": "Strategy A/B control relations and MPC-06 tube geometry",
                "status": "saved-data-companion", "anchor": "control-witness-companions",
                "page": "control-witness-v1.html", "figure": cards[0]["stem"] + ".svg",
                "source_page": "../" + cards[0]["route_id"] + "/index.html",
                "raw_record": "../" + cards[0]["route_id"] + "/records.json"},
               strategy_ab_entry, timing_entry, b04_entry, exp02_entry, b04_repeat_entry)
    if set(outputs) != set(asset_paths()):
        missing = sorted(set(asset_paths()) - set(outputs))
        extra = sorted(set(outputs) - set(asset_paths()))
        raise ValueError(f"VIZ-09 asset registry differs from build outputs; missing={missing}, extra={extra}")
    return BuildResult(outputs, entries)

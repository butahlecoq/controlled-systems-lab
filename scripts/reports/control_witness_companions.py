"""Build additive gallery companions from frozen control-report evidence."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import tempfile
from typing import Literal

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
             "control-witness/mpc06-tube.svg", "control-witness/mpc06-tube.png",
             "control-witness/mpc06-tube-evidence.json"]
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
        "plot_data": plot_data,
        "figure_export": export,
        "claim_scope": "presentation of frozen saved geometry; no solver or geometry query",
    }
    evidence_bytes = (json.dumps(evidence, indent=2) + "\n").encode()
    return route_id, figure_svg, figure_png, evidence_bytes


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

    body = []
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
    state_bounds = mpc06_bounds["tightened_state_X_minus_Z"]["bounds"]
    tube_vertices = mpc06_bounds["error_tube_Z"]["vertices"]
    body.append(
        '<article id="mpc06-tube"><h2>MPC-06 · exact tube feasibility geometry</h2>'
        '<p>This figure re-plots the frozen position–velocity box, support tightening and exact dyadic RPI tube. '
        'The source declares no physical units for the state coordinates; equal data scaling is a display choice, '
        'not physical dimensional scaling. The underlying study checks feasibility and safety for one fixed '
        'nilpotent profile; it does not optimize an objective or compute a minimax reachable set.</p>'
        '<figure><a href="control-witness/mpc06-tube.svg"><img src="control-witness/mpc06-tube.svg" '
        'alt="Saved position-velocity state box, tightened state set, and exact RPI tube on equal numeric axes"></a>'
        '<figcaption>Numeric ticks and major gridlines follow csl-report-quantitative-v1. '
        '<a href="control-witness/mpc06-tube.png">Open PNG figure ↗</a></figcaption></figure>'
        '<table><caption>Exact values retained in the frozen result</caption><thead><tr><th scope="col">Set</th>'
        '<th scope="col">Saved coordinates</th></tr></thead><tbody>'
        '<tr><th scope="row">State constraint X</th><td>[-1,1] × [-1,1]</td></tr>'
        '<tr><th scope="row">Tightened state set X ⊖ Z</th><td>' + html.escape(str(state_bounds)) + '</td></tr>'
        '<tr><th scope="row">Exact RPI error tube Z</th><td>' + html.escape(str(tube_vertices)) + '</td></tr>'
        '</tbody></table><p><a href="../' + mpc06_route + '/index.html">Frozen MPC-06 report ↗</a> · '
        '<a href="../' + mpc06_route + '/result.json">Saved result ↗</a> · '
        '<a href="../' + mpc06_route + '/figure-data.json">Original saved figure data ↗</a> · '
        '<a href="control-witness/mpc06-tube-evidence.json">Companion data and hashes ↗</a></p></article>')
    outputs["control-witness-v1.html"] = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Saved control figures · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css"></head>'
        '<body class="control-witness-page"><main><p><a href="index.html">← Visual examples</a></p><h1>Saved control and witness figures</h1>'
        '<p>The first five figures show projections of frozen five-coordinate state/control relations into the control plane '
        '(u₀,u₁); each can omit distinctions present in the full joint relation. The MPC-06 figure re-plots a saved two-state '
        'feasibility tube. These companions do not run a solver or recompute scientific geometry.</p>' +
        ''.join(body) + '</main></body></html>').encode()
    entries = ({"family": "Control strategy and witness reports",
                "title": "Strategy A/B control relations and MPC-06 tube geometry",
                "status": "saved-data-companion", "anchor": "control-witness-companions",
                "page": "control-witness-v1.html", "figure": cards[0]["stem"] + ".svg",
                "source_page": "../" + cards[0]["route_id"] + "/index.html",
                "raw_record": "../" + cards[0]["route_id"] + "/records.json"}, timing_entry)
    if set(outputs) != set(asset_paths()):
        missing = sorted(set(asset_paths()) - set(outputs))
        extra = sorted(set(outputs) - set(asset_paths()))
        raise ValueError(f"VIZ-09 asset registry differs from build outputs; missing={missing}, extra={extra}")
    return BuildResult(outputs, entries)

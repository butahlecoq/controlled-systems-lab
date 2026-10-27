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
    paths = ["control-witness-v1.html", "control-witness-timing-v1.html"]
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
        '<title>Saved control report timings</title><link rel="stylesheet" href="examples.css"></head><body><main>'
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
    outputs["control-witness-v1.html"] = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Control relation projections · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css"></head>'
        '<body><main><p><a href="index.html">← Visual examples</a></p><h1>Saved control-relation projections</h1>'
        '<p>These figures read frozen reports and show projections of their five-coordinate state/control relations into the control plane '
        '(u₀,u₁). A projection can omit distinctions present in the full joint relation; each card states what its report establishes.</p>' +
        ''.join(body) + '</main></body></html>').encode()
    entries = ({"family": "Control strategy and witness reports",
                "title": "Strategy A and B control-relation projections",
                "status": "saved-data-companion", "anchor": "control-witness-companions",
                "page": "control-witness-v1.html", "figure": cards[0]["stem"] + ".svg",
                "source_page": "../" + cards[0]["route_id"] + "/index.html",
                "raw_record": "../" + cards[0]["route_id"] + "/records.json"}, timing_entry)
    if set(outputs) != set(asset_paths()):
        missing = sorted(set(asset_paths()) - set(outputs))
        extra = sorted(set(outputs) - set(asset_paths()))
        raise ValueError(f"VIZ-09 asset registry differs from build outputs; missing={missing}, extra={extra}")
    return BuildResult(outputs, entries)

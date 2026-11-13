"""Inventory and retire obsolete presentation from the composed Pages site."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import argparse
from urllib.parse import unquote, urlsplit
import zipfile


BARE_ROUTE_LESSONS = {
    "finite-feedback-registered-f874133e442eb0fb884b8813a06591cc0f077063ee75ddf627de74656fc11c0f/index.html": ("archive", "Finite-feedback saved timing companion in the examples gallery"),
    "geo02-20261012T235755Z-7275580339899c6ac27496fc2b05cb040d9fec14f8ec7f8bf219cc299c55eefc/index.html": ("archive", "Minkowski-sum analytic lesson in the examples gallery"),
    "geo02-20261013T061151Z-449f188d2de1f50164a55a7b3b3931132dfa8384306ac3c93d5fb3a958cbd754/index.html": ("archive", "Follow-up measurement in the GEO-02 geometry and timing companion; the analytic lesson covers the family, not this run."),
    "geo03-20261012-30157d9ac59269cc26a2ca24dfd1744297971b435a8bba13dcb68f2a1dbcd104/index.html": ("archive", "Distinct H/V conversion analytic example in the examples gallery"),
    "geo05-8918ad3ac4b0b3d1ff9c8b807d6b509f324ef3e9b11716be496c8e6e437f6795/index.html": ("archive", "Two-dimensional analytic projection illustration in the examples gallery; not a measured two-dimensional run"),
    "issue3-finite-catalogue-388b4be3a35ac10c9b42bf8f92ac5ae06b2120049dc6003791bc6487628478de/index.html": ("archive", "Issue 3 control walkthrough and saved timing companion in the examples gallery"),
    "opt04-20261013T172839Z-bf1844fdf81c94c82ca91aadbd9d0988c7367093c5cf70269c2d0e0ca7d44b2f/index.html": ("archive", "Analytic simplex-slice example in the examples gallery"),
    "opt05-hull-20261012-d6d3282081d5ea90d8a0c440ccc1ec774d40221e209a01d8207ebd06a551dbf5/index.html": ("archive", "Related convex-hull educational examples in the gallery; their fixture and method differ from this measurement."),
    "opt06-basis-reuse-20261014-ef70e8c5-57c666a4f82b1f7c84d3507fbad32982a7928129c18f80348ea2c9ad457b3a8d/index.html": ("archive", "Solver basis-reuse timing evidence; no control lesson is claimed"),
    "perf03-ts01-single-process-correlation-20261014-365f6e659e316219/index.html": ("archive", "Profiling evidence; no geometry lesson is claimed"),
    "syn02-1b07970d73d90c79c4bba2c65d429ba05bd798751d885146cb21d8a876a067c3/index.html": ("archive", "Saved SYN02 timing chart in the gallery; this is not a terminal-control lesson."),
    "env717-two-points-33ebdad360671940fb54/index.html": ("archive", "Finite TwoPoints control walkthrough and comparison evidence"),
    "review05-family-query-d6af180b0e398d78ebd2/review05-build-phases-20261110-468cc0eb/index.html": ("hidden-evidence", "Superseded REVIEW05 build-phase evidence; current aggregate remains linked from the archive"),
}

BARE_ROUTE_REPLACEMENTS = {
    "finite-feedback-registered-f874133e442eb0fb884b8813a06591cc0f077063ee75ddf627de74656fc11c0f/index.html": "examples/finite-feedback-timing-v1.html",
    "geo02-20261012T235755Z-7275580339899c6ac27496fc2b05cb040d9fec14f8ec7f8bf219cc299c55eefc/index.html": "examples/index.html#visual-geo02-minkowski-triangles",
    "geo02-20261013T061151Z-449f188d2de1f50164a55a7b3b3931132dfa8384306ac3c93d5fb3a958cbd754/index.html": "examples/index.html#geometry-optimization-companions",
    "geo03-20261012-30157d9ac59269cc26a2ca24dfd1744297971b435a8bba13dcb68f2a1dbcd104/index.html": "examples/index.html#visual-geo03-hv-square",
    "geo05-8918ad3ac4b0b3d1ff9c8b807d6b509f324ef3e9b11716be496c8e6e437f6795/index.html": "examples/index.html#visual-geo05-predecessor-boxes",
    "issue3-finite-catalogue-388b4be3a35ac10c9b42bf8f92ac5ae06b2120049dc6003791bc6487628478de/index.html": "examples/issue3-control-walkthrough.html",
    "opt04-20261013T172839Z-bf1844fdf81c94c82ca91aadbd9d0988c7367093c5cf70269c2d0e0ca7d44b2f/index.html": "examples/index.html#visual-opt04-phase-one-simplex",
    "opt05-hull-20261012-d6d3282081d5ea90d8a0c440ccc1ec774d40221e209a01d8207ebd06a551dbf5/index.html": "examples/index.html#square_duplicates",
    "opt06-basis-reuse-20261014-ef70e8c5-57c666a4f82b1f7c84d3507fbad32982a7928129c18f80348ea2c9ad457b3a8d/index.html": None,
    "perf03-ts01-single-process-correlation-20261014-365f6e659e316219/index.html": None,
    "syn02-1b07970d73d90c79c4bba2c65d429ba05bd798751d885146cb21d8a876a067c3/index.html": "examples/control-witness-timing-v1.html",
    "env717-two-points-33ebdad360671940fb54/index.html": None,
    "review05-family-query-d6af180b0e398d78ebd2/review05-build-phases-20261110-468cc0eb/index.html": None,
}

# Gallery pages are assembled by visual_examples.py. These additional sources
# own page content or figures for the routes they contribute.
EXAMPLE_ROUTE_PRODUCERS = {
    "examples/native-model-tracking-first-pass-v1/index.html": ["scripts/reports/stage_native_model_tracking_first_pass.py", "scripts/reports/visual_examples.py"],
    "examples/native-model-tracking-first-pass-v1/reproducing.html": ["scripts/reports/stage_native_model_tracking_first_pass.py", "reports/algorithm-results/native-model-tracking-first-pass-v1/reproducing.html"],
    "examples/native-model-tracking-first-pass-v1/figures/model-21-state-3-9.svg": ["scripts/reports/stage_native_model_tracking_first_pass.py", "reports/algorithm-results/native-model-tracking-first-pass-v1/visual-example-20261113T184921Z/figures/model-21-state-3-9.svg"],
    "examples/native-fixed-tail-geometry-a6/index.html": [
        "scripts/reports/native_fixed_tail_geometry.py",
        "scripts/reports/native_fixed_tail_episode_report.py",
        "scripts/reports/assets/native-fixed-tail-geometry/index.html",
        "scripts/reports/assets/native-fixed-tail-geometry/geometry.js",
        "scripts/reports/assets/native-fixed-tail-geometry/geometry.css"],
    "examples/native-slide50-reachability.html": ["scripts/reports/stage_native_extended_models.py", "docs/examples/native-slide50-reachability.html"],
    "examples/native-spatial-flight.html": ["scripts/reports/stage_native_extended_models.py", "docs/examples/native-spatial-flight.html"],
    "examples/native-discrete-models.html": ["scripts/reports/stage_native_discrete_models.py", "docs/examples/native-discrete-models.html"],
    "examples/native-quadcopter-mpc.html": ["scripts/reports/stage_native_discrete_models.py", "scripts/reports/native_discrete_models.py", "docs/examples/native-quadcopter-mpc.html"],
    "examples/adaptive-ode-replay.html": ["scripts/reports/render_adaptive_ode_example.py"],
    "examples/source-index-geometry-2d.html": ["docs/examples/source-index-geometry-2d.html"],
    "examples/app01-plan-timing-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/app02-diamond-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/app03-zonotope-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/app04-square-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/b04-reference-trajectory-projections.html": ["scripts/reports/mpc01/b04_projection_example.py"],
    "examples/buryatia-volterra-affine-2d.html": [
        "scripts/reports/stage_buryatia_volterra.py",
        "docs/examples/buryatia-volterra-affine-2d-manifest.json",
        "docs/examples/buryatia-volterra-affine-2d.html",
        "docs/examples/buryatia-volterra-affine-2d-records.json",
        "docs/examples/buryatia-volterra-affine-2d-terminal.svg",
        "docs/examples/buryatia-volterra-affine-2d-records-superseded-v1.json",
        "docs/examples/buryatia-volterra-affine-2d-superseded-v1.html",
        "docs/examples/buryatia-volterra-affine-2d-terminal-superseded-v1.svg",
        "docs/examples/buryatia-volterra-affine-2d-manifest-superseded-v1.json",
    ],
    "examples/buryatia-volterra-affine-2d-superseded-v1.html": [
        "scripts/reports/stage_buryatia_volterra.py",
        "docs/examples/buryatia-volterra-affine-2d-manifest.json",
        "docs/examples/buryatia-volterra-affine-2d.html",
        "docs/examples/buryatia-volterra-affine-2d-records.json",
        "docs/examples/buryatia-volterra-affine-2d-terminal.svg",
        "docs/examples/buryatia-volterra-affine-2d-records-superseded-v1.json",
        "docs/examples/buryatia-volterra-affine-2d-superseded-v1.html",
        "docs/examples/buryatia-volterra-affine-2d-terminal-superseded-v1.svg",
        "docs/examples/buryatia-volterra-affine-2d-manifest-superseded-v1.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/index.html": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-literal-affine.html",
        "docs/examples/buryatia-dim4-literal-affine-v1-records.json",
        "docs/examples/buryatia-dim4-literal-affine-v1-capture.json",
        "docs/examples/buryatia-dim4-box-trace-correction-v1.json",
        "benchmarks/scenarios/buryatia-dim4-matlab-literal-affine-v1.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/terminal-x1-x2.svg": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-literal-affine-v1-records.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-records.json": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-literal-affine-v1-records.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-capture.json": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-literal-affine-v1-capture.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/buryatia-dim4-box-trace-correction-v1.json": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-box-trace-correction-v1.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/buryatia-dim4-matlab-literal-affine-v1.json": [
        "scripts/reports/stage_buryatia_dim4.py",
        "benchmarks/scenarios/buryatia-dim4-matlab-literal-affine-v1.json",
    ],
    "examples/buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-SHA256SUMS": [
        "scripts/reports/stage_buryatia_dim4.py",
        "docs/examples/buryatia-dim4-literal-affine-v1-SHA256SUMS",
        "docs/examples/buryatia-dim4-literal-affine-v1-records.json",
        "docs/examples/buryatia-dim4-literal-affine-v1-capture.json",
        "docs/examples/buryatia-dim4-box-trace-correction-v1.json",
        "benchmarks/scenarios/buryatia-dim4-matlab-literal-affine-v1.json",
    ],
    "examples/control-witness-timing-v1.html": ["scripts/reports/control_witness_companions.py"],
    "examples/control-witness-v1.html": ["scripts/reports/control_witness_companions.py"],
    "examples/ext01-b08-timing-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/ext04-affine-synthesis-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/ext04-observed-replay-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/ext05-states-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/ext07-feasible-relation-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/ext07-two-control-family-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/finite-feedback-timing-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/feedback_geometry_2d.html": ["scripts/reports/feedback_geometry_example.py",
                                             "examples/feedback_geometry_2d.html"],
    "examples/fuel-b06-viz03.html": ["scripts/reports/visual_example_fuel_layers.py",
                                     "docs/examples/fuel-b06-viz03.html"],
    "examples/fuel-b06-viz06.html": ["scripts/reports/visual_example_fuel_layers.py",
                                     "docs/examples/fuel-b06-viz06.html"],
    "examples/fuel-reachability-layers/index.html": ["scripts/reports/fuel_reachability_layers.py"],
    "examples/geometry-optimization-v1.html": ["scripts/reports/geometry_opt_companions.py"],
    "examples/lotka-volterra-sampled-v1.html": ["scripts/reports/approx_extension_companions.py"],
    "examples/closed-loop-pilot-2d.html": ["scripts/reports/stage_closed_loop_pilot.py",
                                           "scripts/reports/render_closed_loop_pilot.py"],
    "examples/viz10/index.html": ["scripts/reports/viz10_plot_companions.py"],
}

STANDALONE_REPORT_ROUTE_PRODUCERS = {
    "closed-loop-history-functional/native-parallelotope-d6fc-v1/index.html": [
        "scripts/reports/stage_history_functional.py",
        "scripts/reports/native_parallelotope_functional.py",
        "reports/closed-loop-history-functional/native-parallelotope-d6fc-v1/index.html",
        ".github/workflows/algorithm-reports.yml"],
    "closed-loop-history-functional/warm-gap-9540-v1/index.html": [
        "scripts/reports/stage_history_functional.py",
        "scripts/reports/history_warm_gap_report.py",
        "reports/closed-loop-history-functional/warm-gap-9540-v1/render-source.py",
        ".github/workflows/algorithm-reports.yml"],
    "closed-loop-history-functional/index.html": ["scripts/reports/stage_history_functional.py",
                                                   "reports/closed-loop-history-functional/index.html",
                                                   ".github/workflows/algorithm-reports.yml"],
    "closed-loop-pilot-v1/index.html": ["scripts/reports/render_closed_loop_pilot.py",
                                        "scripts/reports/stage_closed_loop_pilot.py",
                                        ".github/workflows/algorithm-reports.yml"],
    "closed-loop-pilot-v1/example-2d.html": ["scripts/reports/render_closed_loop_pilot.py",
                                             "scripts/reports/stage_closed_loop_pilot.py",
                                             ".github/workflows/algorithm-reports.yml"],
}

GALLERY_INDEX_PRODUCERS = [
    "scripts/reports/stage_buryatia_volterra.py",
    "scripts/reports/stage_native_extended_models.py",
    "scripts/reports/stage_native_discrete_models.py",
    "scripts/reports/approx_extension_companions.py",
    "scripts/reports/control_witness_companions.py",
    "scripts/reports/geometry_opt_companions.py",
    "scripts/reports/visual_illustrations.py",
    "scripts/reports/feedback_geometry_example.py",
    "scripts/reports/visual_example_geometry.py",
    "scripts/reports/visual_example_fuel_layers.py",
    "scripts/reports/visual_example_hybrid.py",
    "scripts/reports/viz10_plot_companions.py",
]


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str]] = []
        self.tags: set[str] = set()
        self.anchors: set[str] = set()
        self.inline_svg = 0
        self.text: list[str] = []
        self.svg_text: list[str] = []
        self.in_svg = False
        self.alt: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self.tags.add(tag.lower())
        if tag.lower() == "svg":
            self.inline_svg += 1
            self.in_svg = True
        for key, value in attrs:
            if (key.lower() == "id" or (key.lower() == "name" and tag.lower() == "a")) and value:
                self.anchors.add(value)
            if key.lower() in {"href", "src", "poster", "data"} and value:
                self.refs.append((key.lower(), value))
            if key.lower() == "alt" and value:
                self.alt.append(value)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())
            if self.in_svg:
                self.svg_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "svg":
            self.in_svg = False


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def legacy_root_snapshot() -> bytes:
    """Load the exact Pages landing page recorded before route retirement."""
    repo = Path(__file__).resolve().parents[2]
    metadata_path = repo / "docs/research/evidence/pages-legacy-index-ed2dda1.json"
    snapshot_path = repo / "docs/research/evidence/pages-legacy-index-ed2dda1.html"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    snapshot = snapshot_path.read_bytes()
    expected = {
        "schema": "csl.pages-legacy-root-snapshot/1",
        "source_commit": "ed2dda1ef049ac4fbe259a800d3314e446ceee28",
        "source_report_run_id": 42902971467,
        "complete_pages_artifact_run_id": 42909649474,
        "artifact_relative_path": "index.html",
        "snapshot_path": "docs/research/evidence/pages-legacy-index-ed2dda1.html",
        "bytes": 176366,
        "sha256": "29376974f806ad83816be9b42bda19fbeccaebc9a7ca79c291ed3d9ea3d522d2",
    }
    if metadata != expected or len(snapshot) != expected["bytes"] or sha256(snapshot) != expected["sha256"]:
        raise ValueError("pinned legacy Pages snapshot provenance or bytes differ")
    return snapshot


def _internal_target(site: Path, page: Path, ref: str) -> str | None:
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    target = (page.parent / unquote(parsed.path)).resolve()
    if not target.is_relative_to(site.resolve()):
        raise ValueError(f"HTML reference escapes the Pages site: {page.relative_to(site)} -> {ref}")
    if target.is_dir():
        target = target / "index.html"
    return target.relative_to(site.resolve()).as_posix()


def _route_role(route: str, catalog: dict[str, dict]) -> tuple[str, str]:
    parts = PurePosixPath(route).parts
    if len(parts) == 1 and parts[0] in {"index.html", "archive.html", "legacy-index.html"}:
        return "learning navigation", "learning"
    if len(parts) > 1 and parts[0] == "learn":
        return "learning book chapter", "learning"
    if len(parts) > 1 and parts[0] == "examples":
        return "illustrated learning example", "learning"
    if len(parts) > 1 and parts[0] == "docs":
        return "research evidence", "archive"
    if "rejected" in parts:
        return "rejected result", "hidden-evidence"
    if "superseded" in parts or "recheck-v2" in route:
        return "superseded or recheck evidence", "hidden-evidence"
    report = parts[0] if parts else route
    if report in catalog:
        return "catalogued result", "archive"
    if route in BARE_ROUTE_LESSONS:
        return "historical or supplemental evidence", BARE_ROUTE_LESSONS[route][0]
    if len(parts) > 1:
        return "nested report or supporting artifact", "archive"
    return "historical or supplemental report", "archive"


def _illustration_type(route: str, parser: References, refs: list[dict], entries: list[dict]) -> tuple[str, list[str]]:
    linked = [ref["target"] for ref in refs if ref["kind"] in {"href", "src", "poster", "data"}
              and Path(ref["target"]).suffix.lower() in {".svg", ".png", ".jpg", ".jpeg", ".webp"}]
    if not parser.tags.intersection({"img", "svg", "canvas", "object", "figure"}):
        return ("linked-figure-only" if linked else "none"), linked
    signals = " ".join([route, *parser.svg_text, *parser.alt, *linked,
                        *(str(entry.get("family", "")) + " " + str(entry.get("title", "")) + " " + str(entry.get("status", "")) for entry in entries)]).lower()
    if re.search(r"timing|latency|resource|profile|throughput|nanosecond|microsecond|milliseconds?", signals):
        return "timing-or-resource-plot", linked
    if re.search(r"reachable|hull|state|set |trajectory|geometry|control|phase|orbit|simplex|polytope", signals):
        if any(entry.get("status") == "analytic-illustration" for entry in entries):
            return "analytic-geometry-or-control-illustration", linked
        return "saved-geometry-or-control-plot", linked
    return "graphic-purpose-unclassified", linked


def _producer_record(site: Path, route: str, catalog: dict[str, dict], source_identity: dict) -> dict:
    parts = PurePosixPath(route).parts
    top = parts[0] if parts else route
    repo = Path(__file__).resolve().parents[2]
    if route == "index.html":
        return {"files": ["scripts/reports/pages_route_retirement.py"], "owner_status": "exact"}
    if route in {"archive.html", "legacy-index.html"}:
        return {"files": ["scripts/reports/pages_route_retirement.py", "scripts/reports/landing.py"], "owner_status": "exact"}
    if top == "learn":
        sources = ["scripts/reports/learning_book.py", "docs/catalogue/learning-book-v1.json",
                   "docs/catalogue/module-composition-inventory-v1.json"]
        parts = PurePosixPath(route).parts
        if route.endswith("/index.html"):
            manifest = repo / "docs/catalogue/learning-book-v1.json"
            if manifest.is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                sources.extend("docs/examples/learning/chapters/" + chapter["source"]
                               for chapter in data.get("chapters", []))
        elif route == "learn/module-catalogue.html":
            sources.append("docs/catalogue/module-composition-inventory-v1.json")
        elif len(parts) == 2 and parts[1].endswith(".html"):
            sources.append("docs/examples/learning/chapters/" + parts[1][:-5] + ".html")
        return {"files": sources, "owner_status": "chapter-manifest-producer"}
    if top == "examples":
        if route.startswith("examples/closed-loop/"):
            sources = ["scripts/reports/learning_book.py",
                       "scripts/reports/recorded_closed_loop_figures.py",
                       "docs/examples/closed-loop/figure-index.json"]
            asset_root = repo / "docs/examples/closed-loop"
            if asset_root.is_dir():
                sources.extend(path.relative_to(repo).as_posix()
                               for path in asset_root.rglob("*") if path.is_file())
            return {"files": sources, "owner_status": "recorded-figure-and-book-stage"}
        files = ["scripts/reports/visual_examples.py"]
        if route == "examples/index.html":
            files.extend(GALLERY_INDEX_PRODUCERS)
            return {"files": files, "owner_status": "gallery-aggregation-pipeline"}
        if route.startswith("examples/native-extended-models-v1/"):
            files.extend(["scripts/reports/stage_native_extended_models.py",
                          "scripts/reports/frozen_native_bundle.py",
                          "reports/algorithm-results/native-extended-models-v1/manifest.json"])
        files.extend(EXAMPLE_ROUTE_PRODUCERS.get(route, []))
        return {"files": files, "owner_status": "gallery-aggregator"}
    if top == "docs":
        return {"files": ["scripts/reports/augment_pages_bundle.py"], "owner_status": "exact"}
    route_modules = {
        "app02-example": "scripts/reports/stage_app02.py",
        "app03-example": "scripts/reports/stage_app03.py",
        "env717-two-points-33ebdad360671940fb54": "scripts/reports/stage_env717_two_points.py",
        "perf03-ts01-single-process-correlation-20261014-365f6e659e316219": "scripts/reports/stage_perf03.py",
        "mpc01-per-attempt-20261103-r3": "scripts/reports/mpc01/stage_per_attempt.py",
    }
    if top in route_modules:
        return {"files": [route_modules[top], "scripts/reports/augment_pages_bundle.py"], "owner_status": "exact"}
    if route in STANDALONE_REPORT_ROUTE_PRODUCERS:
        return {"files": STANDALONE_REPORT_ROUTE_PRODUCERS[route], "owner_status": "exact"}
    if top in catalog:
        kind = catalog[top].get("report_kind", "")
        family = kind.split("-", 1)[0]
        adapter = Path(__file__).with_name(f"{family}_registered_reports.py")
        if not adapter.is_file():
            adapter = Path(__file__).with_name("registered_reports.py")
        return {"files": ["scripts/reports/site.py", adapter.relative_to(repo).as_posix()],
                "owner_status": "exact"}
    manifest_path = site / top / "publication-manifest.json"
    schema = None
    if manifest_path.is_file() and not manifest_path.is_symlink():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            schema = data.get("schema") if isinstance(data, dict) else None
        except (OSError, ValueError):
            pass
    if not isinstance(schema, str):
        schema = source_identity.get("schema")
    stage = _stage_owner(route, schema if isinstance(schema, str) else None)
    if stage:
        return {"files": [stage, "scripts/reports/augment_pages_bundle.py"], "owner_status": "exact"}
    if (repo / "reports/algorithm-results" / top).is_dir():
        return {"files": [f"reports/algorithm-results/{top}", ".github/workflows/algorithm-reports.yml"],
                "owner_status": "source-bundle-and-workflow"}
    source_id = source_identity.get("source_report_id")
    if isinstance(source_id, str) and (repo / "reports/algorithm-results" / source_id).is_dir():
        return {"files": [f"reports/algorithm-results/{source_id}", ".github/workflows/algorithm-reports.yml"],
                "owner_status": "source-bundle-and-workflow"}
    return {"files": [".github/workflows/algorithm-reports.yml"], "owner_status": "artifact-workflow"}


def _stage_owner(route: str, schema: str | None) -> str | None:
    if not schema or not schema.startswith("csl."):
        return None
    root = PurePosixPath(route).parts[0]
    aliases = {
        "csl.mpc06-completion-publication/1": "stage_mpc06_delivery.py",
        "csl.mpc06.offline-publication/1": "stage_mpc06_offline_costs.py",
        "csl.exp06-report-manifest/1": "stage_exp06.py",
        "csl.mpc07.publication/1": "stage_mpc07_comparison.py",
        "csl.mpc08.publication/1": "stage_mpc08_complete.py",
        "csl.mpc10.publication/1": "stage_mpc10_comparison.py",
        "csl.mpc11.publication/1": "stage_mpc11_controller_comparison.py",
        "csl.mpc11.study-publication/1": "stage_mpc11_mesh_timing.py",
        "csl.review05.publication/1": "stage_review05_family_query.py",
    }
    if schema in aliases:
        path = Path(__file__).with_name(aliases[schema])
        return path.relative_to(Path(__file__).resolve().parents[2]).as_posix() if path.is_file() else None
    if schema.startswith("csl.env717-publication/"):
        suffix = root.removeprefix("env717-").rsplit("-", 1)[0]
        stem = "env717_" + suffix.replace("-", "_")
    else:
        stem = schema.removeprefix("csl.").split("/", 1)[0].removesuffix("-publication")
        stem = stem.replace(".", "_").replace("-", "_")
    candidate = Path(__file__).with_name("stage_" + stem + ".py")
    if candidate.is_file():
        return candidate.relative_to(Path(__file__).resolve().parents[2]).as_posix()
    return None


def _source_identity(site: Path, route: str, catalog: dict[str, dict]) -> dict:
    report_id = PurePosixPath(route).parts[0]
    route_dir = site / report_id
    identity = {key: catalog[report_id][key] for key in
                ("report_id", "source_commit", "payload_sha256", "native_payload_sha256", "zip_sha256")
                if report_id in catalog and key in catalog[report_id]}
    for name in ("publication-manifest.json", "report-envelope.json", "record.json", "manifest.json"):
        path = route_dir / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in ("report_id", "source_report_id", "source_commit", "payload_sha256", "schema", "scenario_id"):
            value = data.get(key)
            if isinstance(value, (str, int)) and key not in identity:
                identity[key] = value
    return identity


def _archive_fragment(route: str) -> str:
    return "route-" + hashlib.sha256(route.encode("utf-8")).hexdigest()[:16]


def inventory(site: Path, *, source_commit: str = "unknown") -> dict:
    site = site.resolve(strict=True)
    catalog_path = site / "catalog.json"
    catalog = {}
    if catalog_path.is_file():
        rows = json.loads(catalog_path.read_text(encoding="utf-8")).get("reports", [])
        catalog = {row.get("report_id"): row for row in rows if isinstance(row, dict)}
    gallery_entries: dict[str, list[dict]] = {}
    related_examples: dict[str, list[dict]] = {}
    gallery_path = site / "examples/visual-coverage.json"
    if gallery_path.is_file():
        gallery = json.loads(gallery_path.read_text(encoding="utf-8"))
        for entry in gallery.get("entries", []):
            page = entry.get("page")
            if isinstance(page, str):
                gallery_entries.setdefault("examples/" + page.split("#", 1)[0], []).append(entry)
            for field in ("source_page", "report_records"):
                refs = entry.get(field)
                for ref in refs if isinstance(refs, list) else [refs]:
                    if not isinstance(ref, str):
                        continue
                    try:
                        target = _internal_target(site, site / "examples/index.html", ref)
                    except ValueError:
                        continue
                    if target in {"", None}:
                        continue
                    related_examples.setdefault(target, []).append(entry)
    html_files = sorted(path for path in site.rglob("*.html") if path.is_file())
    pages = {}
    inbound: dict[str, list[str]] = {}
    for path in html_files:
        rel = path.relative_to(site).as_posix()
        parser = References()
        content = path.read_bytes()
        parser.feed(content.decode("utf-8", errors="replace"))
        refs = []
        for kind, ref in parser.refs:
            target = _internal_target(site, path, ref)
            if target is not None:
                exists = (site / target).is_file()
                fragment = unquote(urlsplit(ref).fragment)
                refs.append({"kind": kind, "value": ref, "target": target,
                             "fragment": fragment or None, "exists": exists})
                if exists and target.endswith(".html"):
                    inbound.setdefault(target, []).append(rel)
        figure_tags = sorted(parser.tags & {"img", "svg", "canvas", "object", "figure"})
        route_entries = related_examples.get(rel, [])
        illustration, linked_figures = _illustration_type(rel, parser, refs, route_entries)
        role, visibility = _route_role(rel, catalog)
        if rel in BARE_ROUTE_LESSONS:
            visibility, lesson = BARE_ROUTE_LESSONS[rel]
            if visibility == "hidden-evidence":
                role = "superseded or hidden evidence"
            completeness = {"status": "evidence-only", "basis": "reviewed route disposition",
                            "related_gallery_entries": [item.get("title") for item in route_entries]}
            replacement_page = BARE_ROUTE_REPLACEMENTS.get(rel)
        elif role == "illustrated learning example":
            lesson = "examples gallery entry; inspect its saved inputs and stated limits"
            completeness = {"status": "gallery-inventory-classified", "entries": [
                {key: item.get(key) for key in ("title", "family", "status", "anchor", "source_page", "raw_record")}
                for item in gallery_entries.get(rel, [])]}
            replacement_page = None
        elif role == "learning navigation":
            lesson = "primary learning entrypoint" if rel == "index.html" else "evidence archive"
            completeness = {"status": "navigation-only", "basis": "no numerical lesson is claimed"}
            replacement_page = None
        elif role == "learning book chapter":
            if rel == "learn/module-catalogue.html":
                lesson = "generated module inventory reference"
                completeness = {"status": "inventory-reference",
                                "basis": "module facts come from the source-owned inventory and link to executable lessons when present"}
            else:
                lesson = "chapter generated from the ordered learning-book manifest"
                completeness = {"status": "chapter-manifest-classified",
                                "basis": "generated lesson chapters carry source-owned status and executable evidence links"}
            replacement_page = None
        else:
            lesson = "No lesson replacement asserted"
            statuses = sorted({str(item.get("status")) for item in route_entries if item.get("status")})
            completeness = {"status": "evidence-only", "basis": "not listed as a lesson in the gallery inventory",
                            "related_gallery_entries": [{"title": item.get("title"), "family": item.get("family"),
                                                         "status": item.get("status"), "anchor": item.get("anchor"),
                                                         "page": item.get("page")} for item in route_entries]}
            replacement_page = None
        route_parts = PurePosixPath(rel).parts
        adjacent_zip = route_parts[0] if len(route_parts) > 1 else ""
        zip_path = site / (adjacent_zip + ".zip" if adjacent_zip else "")
        zip_identity = None
        if zip_path.is_file():
            zip_identity = {"route": zip_path.relative_to(site).as_posix(), "sha256": sha256(zip_path.read_bytes())}
        expected_zip = catalog.get(route_parts[0], {}).get("zip_sha256") if route_parts else None
        if expected_zip and (zip_identity is None or zip_identity["sha256"] != expected_zip):
            raise ValueError("catalogue offline ZIP identity differs for " + rel)
        source_identity = _source_identity(site, rel, catalog)
        producer = _producer_record(site, rel, catalog, source_identity)
        pages[rel] = {
            "producer": producer, "source_identity": source_identity,
            "role": role, "visibility": visibility,
            "anchors": sorted(parser.anchors),
            "illustration": {"type": illustration, "basis": "observed HTML tags, inline SVG labels, alt text, linked asset names, and gallery metadata",
                             "embedded_tags": figure_tags,
                             "inline_svg_count": parser.inline_svg,
                             "linked_figures": linked_figures},
            "educational_completeness": completeness,
            "replacement_lesson": {"description": lesson, "page": replacement_page},
            "inbound_html_references": [], "outbound_references": refs,
            "immutable_identity": {"html_sha256": sha256(content), "adjacent_zip": zip_identity},
        }
    for route, row in pages.items():
        row["inbound_html_references"] = sorted(set(inbound.get(route, [])))
    repo = Path(__file__).resolve().parents[2]
    for route, row in pages.items():
        owner = row["producer"]
        if owner["owner_status"] not in {
                "exact", "source-bundle-and-workflow", "gallery-aggregator",
                "gallery-aggregation-pipeline", "chapter-manifest-producer",
                "recorded-figure-and-book-stage"}:
            raise ValueError(f"HTML route has no reviewed producer owner: {route} ({owner['owner_status']})")
        missing_owners = [path for path in owner["files"] if not (repo / path).exists()]
        if missing_owners:
            raise ValueError(f"HTML route names a missing producer source: {route} -> {missing_owners}")
    zip_rows = []
    for path in sorted(site.rglob("*.zip")):
        if not path.is_file():
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                names = sorted(archive.namelist())
        except zipfile.BadZipFile as error:
            raise ValueError(f"invalid offline archive: {path.relative_to(site)}") from error
        zip_rows.append({"route": path.relative_to(site).as_posix(), "sha256": sha256(path.read_bytes()), "members": names})
    return {"schema": "csl.pages-route-inventory/1", "source_commit": source_commit,
            "html_route_count": len(html_files), "zip_route_count": len(zip_rows),
            "html_routes": pages, "zip_routes": zip_rows}


def learning_page(*, has_learning_book: bool = False) -> bytes:
    cards = (
        ("Vertex algorithms", "LP and simplex methods select vertices. Their membership and redundancy checks are separate from terminal optimization.", "vertex-algorithms"),
        ("Reachable-set representations", "Polytopes, zonotopes, parallelotopes, ellipsoids, and boxes carry different relations and guarantees.", "reachable-sets"),
        ("Control algorithms", "Read saved reachability, synthesis, and MPC examples with their replay and completeness limits.", "control-algorithms"),
        ("Supporting algorithms", "Follow conversions, projections, sums, intersections, predecessor recovery, and optimization providers.", "supporting-algorithms"),
    )
    body = "".join(f'<li id="{anchor}"><h3>{escape(title)}</h3><p class="summary">{escape(summary)}</p><a href="examples/index.html#algorithm-coverage">Browse related examples</a></li>' for title, summary, anchor in cards)
    book_link = '<a href="learn/index.html">Learning book</a>' if has_learning_book else ""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Learn · Controlled Systems Lab</title><link rel=\"stylesheet\" href=\"examples/examples.css\"></head><body data-csl-pages-learning-root=\"1\"><div class=\"shell\"><aside>"
            "<a class=\"brand\" href=\"index.html\">[ csl ]<br>Controlled Systems Lab</a><p class=\"eyebrow\">Learning routes</p>"
            "<nav aria-label=\"Learning routes\"><a href=\"index.html\" aria-current=\"page\">Learn</a>" + book_link + "<a href=\"examples/index.html\">Examples</a><a href=\"archive.html\">Evidence archive</a>"
            "<a href=\"index.html#vertex-algorithms\">Vertex algorithms</a><a href=\"index.html#reachable-sets\">Reachable sets</a>"
            "<a href=\"index.html#control-algorithms\">Control algorithms</a><a href=\"index.html#supporting-algorithms\">Supporting algorithms</a></nav></aside>"
            "<main class=\"report-home\"><header><p class=\"eyebrow\">Start here</p><h1>Learn controlled systems</h1><p>Start with an illustrated example, then open its saved report to inspect the inputs, result, and evidence limits. The archive keeps historical and supplemental reports with their original files.</p></header>"
            "<div class=\"cards\"><ul>" + body + "</ul></div></main></div></body></html>").encode("utf-8")


def archive_page(site: Path, inventory_data: dict) -> bytes:
    routes = sorted(path.relative_to(site).as_posix() for path in site.rglob("index.html")
                    if path.is_file() and path.relative_to(site).as_posix() != "index.html")
    learning_rows = []
    ordinary_rows = []
    hidden_rows = []
    for route in routes:
        route_data = inventory_data["html_routes"][route]
        hidden = route_data["visibility"] == "hidden-evidence"
        if route in BARE_ROUTE_LESSONS:
            disposition, lesson = BARE_ROUTE_LESSONS[route]
            summary = (f"Hidden or superseded evidence. {lesson}." if hidden
                       else f"Retained in the archive. {lesson}.")
        elif hidden:
            summary = f"{route_data['role']}; retained for provenance and direct-route continuity."
        else:
            summary = f"{route_data['role']}. Read the page for its scope and evidence limits."
        row = (f'<li class="coverage-row" id="{_archive_fragment(route)}">'
               f'<h3><a href="{escape(route, quote=True)}">{escape(route)}</a></h3>'
               f'<p class="summary">{escape(summary)}</p></li>')
        if hidden:
            hidden_rows.append(row)
        elif route_data["visibility"] == "learning":
            learning_rows.append(row)
        else:
            ordinary_rows.append(row)
    for route, route_data in sorted(inventory_data["html_routes"].items()):
        if (not route.endswith("/index.html") and route_data["visibility"] == "archive"):
            ordinary_rows.append(
                f'<li class="coverage-row" id="{_archive_fragment(route)}">'
                f'<h3><a href="{escape(route, quote=True)}">{escape(route)}</a></h3>'
                f'<p class="summary">{escape(route_data["role"])}; retained in the evidence archive.</p></li>')
    learning_section = ("<section id=\"learning-pages\"><h2>Learning pages and examples</h2>"
                        "<div class=\"cards\"><ul>" + "".join(learning_rows) + "</ul></div></section>") if learning_rows else ""
    hidden_section = ("<section id=\"hidden-evidence\"><h2>Hidden and superseded evidence</h2>"
                      "<p>Retained for provenance and stable direct URLs. These pages are not current primary lessons or ordinary report entries.</p>"
                      "<div class=\"cards\"><ul>" + "".join(hidden_rows) + "</ul></div></section>") if hidden_rows else ""
    hidden_nav = '<a href="archive.html#hidden-evidence">Hidden/superseded evidence</a>' if hidden_rows else ""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Evidence archive · Controlled Systems Lab</title><link rel=\"stylesheet\" href=\"examples/examples.css\"></head><body><div class=\"shell\"><aside>"
            "<a class=\"brand\" href=\"index.html\">[ csl ]<br>Controlled Systems Lab</a><p class=\"eyebrow\">Learning routes</p>"
            "<nav aria-label=\"Learning routes\"><a href=\"index.html\">Learn</a><a href=\"examples/index.html\">Examples</a><a href=\"archive.html\" aria-current=\"page\">Evidence archive</a>" + hidden_nav + "</nav></aside>"
            "<main class=\"report-home\"><header><p class=\"eyebrow\">Saved pages</p><h1>Evidence archive</h1>"
            "<p>Learning pages, current saved reports, and supporting evidence are listed in their own sections. Hidden or superseded evidence is listed separately with its stable URL."
            " The previous archive landing page remains byte-identical at <a href=\"legacy-index.html\">legacy-index.html</a>.</p></header><section id=\"saved-reports\"><h2>Saved reports and supporting evidence</h2><div class=\"cards\"><ul>"
            + "".join(ordinary_rows) + "</ul></div></section>" + learning_section + hidden_section + "</main></div></body></html>").encode("utf-8")


def _validate_replacement_lessons(site: Path, inventory_data: dict) -> None:
    pages = inventory_data["html_routes"]
    for retired_route, lesson in BARE_ROUTE_REPLACEMENTS.items():
        if lesson is None or retired_route not in pages:
            continue
        parsed = urlsplit(lesson)
        if parsed.scheme or parsed.netloc or not parsed.path:
            raise ValueError(f"replacement lesson must be an internal route: {retired_route} -> {lesson}")
        target = (site.resolve() / unquote(parsed.path)).resolve()
        if not target.is_relative_to(site.resolve()):
            raise ValueError(f"replacement lesson escapes the Pages site: {retired_route} -> {lesson}")
        if target.is_dir():
            target = target / "index.html"
        target_route = target.relative_to(site.resolve()).as_posix()
        target_page = pages.get(target_route)
        if target_page is None:
            raise ValueError(f"replacement lesson route is missing: {retired_route} -> {lesson}")
        fragment = unquote(parsed.fragment)
        if fragment and fragment not in target_page["anchors"]:
            raise ValueError(f"replacement lesson fragment is missing: {retired_route} -> {lesson}")


def _validate_generated_fragments(inventory_data: dict) -> None:
    pages = inventory_data["html_routes"]
    for route in ("index.html", "archive.html"):
        for ref in pages[route]["outbound_references"]:
            if ref["kind"] != "href" or not ref["exists"] or not ref["fragment"]:
                continue
            target_page = pages.get(ref["target"])
            if target_page is None or ref["fragment"] not in target_page["anchors"]:
                raise ValueError(f"generated navigation fragment is broken: {route} -> {ref['value']}")
    for ref in pages["examples/index.html"]["outbound_references"]:
        if (ref["kind"] != "href" or ref["target"] != "archive.html"
                or not ref["fragment"]):
            continue
        if ref["fragment"] not in pages["archive.html"]["anchors"]:
            raise ValueError(f"generated archive link fragment is broken: examples/index.html -> {ref['value']}")


def preflight(site: Path) -> Path:
    """Validate every finalizer destination before an augmentation writer runs."""
    site = Path(site)
    canonical_stylesheet = Path(__file__).resolve().parents[2] / "docs/examples/examples.css"
    if site.is_symlink() or not site.is_dir():
        raise ValueError("Pages site must be an existing regular directory")
    outputs = ("index.html", "examples/index.html", "archive.html", "legacy-index.html",
               "pages-route-inventory.json", "examples/examples.css")
    site = site.absolute()
    site_root = site.resolve()
    if not canonical_stylesheet.is_file() or canonical_stylesheet.is_symlink():
        raise ValueError("canonical shared Pages stylesheet is unavailable")
    for relative in outputs:
        path = site / relative
        parent = path.parent
        while parent != site:
            if parent.is_symlink() or not parent.is_dir():
                raise ValueError(f"Pages output parent is not a regular directory: {parent.relative_to(site)}")
            parent = parent.parent
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Pages output is not a regular file: {relative}")
        if not path.resolve().is_relative_to(site_root):
            raise ValueError(f"Pages output escapes the site: {relative}")
    return canonical_stylesheet


def finalize(site: Path, *, source_commit: str = "unknown",
             original_root_bytes: bytes | None = None) -> dict:
    site = Path(site)
    if site.is_symlink() or not site.is_dir():
        raise ValueError("Pages site must be an existing regular directory")
    root = site / "index.html"
    gallery = site / "examples/index.html"
    if root.is_symlink() or not root.is_file():
        raise ValueError("composed Pages artifact has no regular root index")
    if gallery.is_symlink() or not gallery.is_file():
        raise ValueError("composed Pages artifact has no regular examples gallery")
    canonical_stylesheet = preflight(site)
    baseline = inventory(site, source_commit=source_commit)
    broken_figures = [f"{route} -> {ref['value']}" for route, row in baseline["html_routes"].items()
                      for ref in row["outbound_references"]
                      if ref["kind"] in {"src", "poster", "data"} and not ref["exists"]]
    if broken_figures:
        raise ValueError("composed site contains broken local figure references: " + "; ".join(broken_figures[:10]))
    _validate_replacement_lessons(site, baseline)
    root_bytes = root.read_bytes()
    archive = site / "archive.html"
    legacy = site / "legacy-index.html"
    managed = b'data-csl-pages-learning-root="1"' in root_bytes
    previous_inventory = None
    prior_inventory_path = site / "pages-route-inventory.json"
    if managed and prior_inventory_path.is_file():
        previous_inventory = json.loads(prior_inventory_path.read_text(encoding="utf-8"))
    before_artifact = (previous_inventory.get("artifact_transition", {}).get("before")
                       if isinstance(previous_inventory, dict) else None)
    if before_artifact is None:
        before_artifact = {
            "html_routes": {route: row["immutable_identity"]["html_sha256"]
                            for route, row in baseline["html_routes"].items()},
            "zip_routes": {row["route"]: row["sha256"] for row in baseline["zip_routes"]},
        }
    if managed:
        if not legacy.is_file():
            raise ValueError("managed learning root has no retained legacy index")
        legacy_bytes = legacy.read_bytes()
        if original_root_bytes is not None:
            pinned_root = legacy_root_snapshot()
            if original_root_bytes != pinned_root:
                raise ValueError("supplied legacy root is not the hash-verified Pages snapshot")
            if legacy_bytes != pinned_root:
                legacy_bytes = pinned_root
                legacy.write_bytes(pinned_root)
    else:
        if legacy.exists() and legacy.read_bytes() != root_bytes:
            raise ValueError("legacy-index.html already exists with different content")
        legacy_bytes = original_root_bytes if original_root_bytes is not None else root_bytes
    immutable_before = {
        path.relative_to(site).as_posix(): sha256(path.read_bytes())
        for path in site.rglob("*") if path.is_file()
        and path.relative_to(site).as_posix() not in {"index.html", "examples/index.html", "archive.html", "legacy-index.html"}
        and path.suffix.lower() in {".html", ".zip", ".json", ".csv", ".jsonl", ".txt", ".svg", ".png", ".pdf"}
        and path.name != "pages-route-inventory.json"
    }
    gallery_bytes = gallery.read_bytes()
    gallery_text = gallery_bytes.decode("utf-8")
    gallery_text = re.sub(r'<a href="\.\./index\.html">All numerical reports ↗</a>',
                          '<a href="../index.html">Learn</a> · <a href="../archive.html">Evidence archive</a>', gallery_text)
    for route in BARE_ROUTE_LESSONS:
        gallery_text = gallery_text.replace("../" + route,
                                            "../archive.html#" + _archive_fragment(route))
    if "../archive.html" not in gallery_text:
        navigation = ""
        if "../index.html" not in gallery_text:
            navigation += '<a href="../index.html">Learn</a>'
        navigation += '<a href="../archive.html">Evidence archive</a>'
        if "</nav>" in gallery_text:
            gallery_text = gallery_text.replace("</nav>", navigation + "</nav>", 1)
        elif "</aside>" in gallery_text:
            gallery_text = gallery_text.replace(
                "</aside>", '<nav aria-label="Site">' + navigation + "</nav></aside>", 1)
        elif "</body>" in gallery_text:
            gallery_text = gallery_text.replace(
                "</body>", '<nav aria-label="Site">' + navigation + "</nav></body>", 1)
        else:
            raise ValueError("gallery has no insertion point for evidence archive navigation")
    root.write_bytes(learning_page(has_learning_book=(site / "learn/index.html").is_file()))
    legacy.write_bytes(legacy_bytes)
    archive.write_bytes(archive_page(site, baseline))
    gallery.write_text(gallery_text, encoding="utf-8")
    stylesheet = site / "examples/examples.css"
    stylesheet.write_bytes(canonical_stylesheet.read_bytes())
    immutable_after = {
        path.relative_to(site).as_posix(): sha256(path.read_bytes())
        for path in site.rglob("*") if path.is_file()
        and path.relative_to(site).as_posix() not in {"index.html", "examples/index.html", "archive.html", "legacy-index.html"}
        and path.suffix.lower() in {".html", ".zip", ".json", ".csv", ".jsonl", ".txt", ".svg", ".png", ".pdf"}
        and path.name != "pages-route-inventory.json"
    }
    if immutable_before != immutable_after:
        raise ValueError("route finalization changed an evidence or illustration file")
    result = inventory(site, source_commit=source_commit)
    old_root = References()
    old_root.feed(legacy_bytes.decode("utf-8", errors="replace"))
    old_report_links = sorted({ref for kind, ref in old_root.refs
                               if kind == "href" and ref.endswith("/index.html")})
    new_report_links = sorted({ref["value"] for ref in result["html_routes"]["index.html"]["outbound_references"]
                               if ref["kind"] == "href" and ref["value"].endswith("/index.html")
                               and not ref["value"].startswith("examples/")})
    result["navigation_transition"] = {
        "former_root_report_links": old_report_links,
        "former_root_report_link_count": len(old_report_links),
        "new_root_report_links": new_report_links,
        "new_root_report_link_count": len(new_report_links),
        "retired_primary_routes": sorted(BARE_ROUTE_LESSONS),
        "deleted_html_wrappers": [],
        "deletion_disposition": "No HTML routes were deleted. Every report page is reachable through its learning, ordinary archive, or hidden-evidence section according to its reviewed visibility, so no standalone wrapper was shown to be disposable.",
        "archive_index_route_count": sum(route.endswith("/index.html") and route != "index.html"
                                         for route in result["html_routes"]),
        "ordinary_archive_routes": sorted(route for route, row in result["html_routes"].items()
                                           if route.endswith("/index.html") and route != "index.html"
                                           and row["visibility"] == "archive"),
        "ordinary_archive_html_routes": sorted(route for route, row in result["html_routes"].items()
                                                if route != "index.html" and row["visibility"] == "archive"),
        "learning_page_routes": sorted(route for route, row in result["html_routes"].items()
                                        if route.endswith("/index.html") and route != "index.html"
                                        and row["visibility"] == "learning"),
        "hidden_evidence_routes": sorted(route for route, row in result["html_routes"].items()
                                         if route.endswith("/index.html") and route != "index.html"
                                         and row["visibility"] == "hidden-evidence"),
        "primary_route_dispositions": [
            {"route": route, "disposition": "moved to the evidence archive",
             "replacement_lesson": BARE_ROUTE_LESSONS.get(route, ("archive", "No replacement lesson assigned."))[1],
             "lesson_page": BARE_ROUTE_REPLACEMENTS.get(route)}
            for route in old_report_links
        ],
    }
    result["artifact_transition"] = {
        "before": before_artifact,
        "after": {
            "html_routes": {route: row["immutable_identity"]["html_sha256"]
                            for route, row in result["html_routes"].items()},
            "zip_routes": {row["route"]: row["sha256"] for row in result["zip_routes"]},
        },
        "preserved_immutable_html": sorted(
            route for route, digest in before_artifact["html_routes"].items()
            if route not in {"index.html", "examples/index.html"}
            and result["html_routes"].get(route, {}).get("immutable_identity", {}).get("html_sha256") == digest),
        "preserved_zip_routes": sorted(
            route for route, digest in before_artifact["zip_routes"].items()
            if next((item["sha256"] for item in result["zip_routes"] if item["route"] == route), None) == digest),
        "preexisting_broken_local_references": [
            {"source": route, "reference": ref["value"], "target": ref["target"]}
            for route, row in baseline["html_routes"].items()
            for ref in row["outbound_references"] if not ref["exists"]
        ],
    }
    (site / "pages-route-inventory.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if "archive.html" not in result["html_routes"]:
        raise ValueError("archive route is missing from final inventory")
    if result["html_routes"]["index.html"]["immutable_identity"]["html_sha256"] == result["html_routes"]["archive.html"]["immutable_identity"]["html_sha256"]:
        raise ValueError("learning entrypoint was not installed")
    if not any(row["inbound_html_references"] for route, row in result["html_routes"].items()
               if route.endswith("index.html") and route not in {"index.html", "archive.html"}):
        raise ValueError("composed report routes have no inbound HTML references")
    broken_figures = [f"{route} -> {ref['value']}" for route, row in result["html_routes"].items()
                      for ref in row["outbound_references"]
                      if ref["kind"] in {"src", "poster", "data"} and not ref["exists"]]
    if broken_figures:
        raise ValueError("broken local figure references: " + "; ".join(broken_figures[:10]))
    for generated in ("index.html", "archive.html", "examples/index.html"):
        for ref in result["html_routes"][generated]["outbound_references"]:
            if ref["kind"] == "href" and not ref["exists"]:
                raise ValueError(f"generated navigation link is broken: {generated} -> {ref['value']}")
    _validate_generated_fragments(result)
    for route in BARE_ROUTE_LESSONS:
        direct = "../" + route
        if any(ref["value"] == direct for ref in result["html_routes"]["examples/index.html"]["outbound_references"]):
            raise ValueError("bare report route returned to the primary examples gallery: " + route)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", "unknown"))
    args = parser.parse_args()
    result = finalize(args.site, source_commit=args.source_commit,
                      original_root_bytes=legacy_root_snapshot())
    print(json.dumps({"html_route_count": result["html_route_count"],
                      "zip_route_count": result["zip_route_count"],
                      "inventory": "pages-route-inventory.json",
                      "navigation_transition": result["navigation_transition"]}, sort_keys=True))


if __name__ == "__main__":
    main()

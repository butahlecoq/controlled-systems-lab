"""Inventory report/gallery visual producers and frozen published figure routes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
VISUAL_SIGNAL = re.compile(r"<svg|savefig\s*\(|write_image\s*\(|\.svg\b|\.png\b|render_svg", re.I)
ASSET_NAME = re.compile(r"[A-Za-z0-9_.-]+\.(?:svg|png)")
MIGRATION_ISSUES = {
    "approximation-and-extensions": 684,
    "geometry-and-optimization": 685,
    "control-strategy-and-witness": 686,
    "historical-and-benchmarks": 687,
}
COMPOSED_SAVED_ROUTES = {
    "scripts/reports/ext03_transform/report.py",
    "scripts/reports/ext04/continuous_report.py",
    "scripts/reports/issue422/build_bundle.py",
}
FROZEN_DIAGRAM_EXCEPTIONS = {"benchmarks/reporting/approximation_pilot/summarize.py"}
PUBLICATION_EXPORT_ROUTES = {"scripts/reports/render.py"}
VIZ10_ROLE_REASONS = {
    "benchmarks/reporting/approximation_pilot/summarize.py":
        "Draws a reviewed static fixture diagram from authored input shapes and area formulas; it does not plot a saved run record.",
    "benchmarks/reporting/issue6/b07_render_projection.py":
        "Frozen B07 report producer for saved four-state terminal rows; the shared-policy companion plots x1/x3 and x2/x4 rows directly without constructing a hull.",
    "benchmarks/reporting/issue6/b09_render_projection.py":
        "Frozen B09 report producer and nonlinear replay display; the shared-policy companion plots stored terminal rows and replay endpoints separately without recomputing the projected hull.",
    "scripts/reports/b08_exact_report.py":
        "Produces a quantitative plot from saved fresh-process durations; the companion reads the immutable records and separates the excluded warmup.",
    "scripts/reports/exp04/render_saved.py":
        "Validates saved EXP-04 records and plots two-state replay paths; the companion retains the physical coordinates and discloses independent unit scales.",
    "scripts/reports/issue3/render_saved.py":
        "Validates and plots saved finite-catalogue timing summaries; the companion shows saved median and min/max values without recollection.",
    "scripts/reports/issue3/validated_saved.py":
        "Validates a frozen capture and draws its authored analytic 2D fixture; the companion preserves the two plan points and target as an illustration.",
    "scripts/reports/issue422/build_bundle.py":
        "Assembles a report bundle by copying the pre-existing fixed-plan SVG; it does not create or transform plot data.",
    "scripts/reports/issue4_volterra/render.py":
        "Validates and publishes a saved interval certificate with error-box artwork; the companion reads endpoint strings from the frozen record and does not rerun the checker.",
    "scripts/reports/issue6/render.py":
        "Publishes the saved B06 four-state projection; a VIZ-03 shared-policy companion already provides labeled x1/x3 flow and x2/x4 stock projections.",
    "scripts/reports/render.py":
        "Generic report exporter validates and copies a supplied saved figure; it does not produce quantitative plot data.",
}
SAVED_COMPANION_ROUTES = {
    "scripts/reports/app02/render_saved.py",
    "scripts/reports/app03/render_saved.py",
    "scripts/reports/app04/render_saved.py",
    "scripts/reports/ext01/render_saved.py",
    "scripts/reports/ext05/render_saved.py",
    "scripts/reports/lotka_volterra_sampled.py",
    "scripts/reports/geo02/render.py",
    "scripts/reports/geo03/build_report.py",
    "scripts/reports/geo04/render.py",
    "scripts/reports/geo05/render.py",
    "scripts/reports/geo07/render_saved.py",
    "scripts/reports/geo07_dependent/render_saved.py",
    "scripts/reports/geo07_port/render_saved.py",
    "scripts/reports/geo08/render_saved.py",
    "scripts/reports/opt04/render.py",
    "scripts/reports/opt10/render_saved.py",
    "scripts/reports/opt12_render.py",
    "scripts/reports/b08_exact_report.py",
    "scripts/reports/exp04/render_saved.py",
    "scripts/reports/issue3/render_saved.py",
    "scripts/reports/issue3/validated_saved.py",
    "scripts/reports/issue4_volterra/render.py",
    "scripts/reports/issue6/render.py",
    "benchmarks/reporting/issue6/b07_render_projection.py",
    "benchmarks/reporting/issue6/b09_render_projection.py",
}
FROZEN_COMPANIONS = {
    "app02-box-8ff979de60ea9d22": "examples/app02-diamond-v1.html",
    "app03-zonotope-4522855018fa9b0b": "examples/app03-zonotope-v1.html",
    "app04-ellipsoid-fd302c34092f8b19": "examples/app04-square-v1.html",
    "ext01-fixed-plan-20261016-11b7bc74": "examples/ext01-b08-timing-v1.html",
    "ext05-discretization-a40ba9647cc023dc": "examples/ext05-states-v1.html",
    "lotka-volterra-sampled-20261023": "examples/lotka-volterra-sampled-v1.html",
}


def migration_issue(source: str) -> int:
    if "/viz04/" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    if any(token in source for token in ("/app0", "/ext", "/finite_feedback", "/lotka_volterra")):
        return MIGRATION_ISSUES["approximation-and-extensions"]
    if any(token in source for token in ("/geo", "/opt", "/it17_hull")):
        return MIGRATION_ISSUES["geometry-and-optimization"]
    if "/syn" in source or "/ts01" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    return MIGRATION_ISSUES["historical-and-benchmarks"]


def source_inventory(root: Path) -> list[dict]:
    entries = []
    bases = (root / "scripts/reports", root / "benchmarks/reporting")
    for base in bases:
        for path in sorted(base.rglob("*.py")):
            if path.name == "audit_visual_routes.py" or any(part.startswith("test") for part in path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            matches = VISUAL_SIGNAL.findall(source)
            if not matches:
                continue
            relative = path.relative_to(root).as_posix()
            assets = sorted(set(ASSET_NAME.findall(source)))
            if relative in COMPOSED_SAVED_ROUTES:
                disposition = "composes-or-copies-existing-saved-figure"
            elif relative in FROZEN_DIAGRAM_EXCEPTIONS:
                disposition = "reviewed-static-diagram-exception"
            elif relative in PUBLICATION_EXPORT_ROUTES:
                disposition = "publication-validation-or-frozen-route"
            elif relative in SAVED_COMPANION_ROUTES:
                disposition = "frozen-renderer-preserved-with-shared-policy-companion"
            elif relative.endswith(("/geometry_figures.py", "/approx_extension_companions.py",
                                    "/geometry_opt_companions.py", "/viz10_plot_companions.py")):
                disposition = "shared-quantitative-policy-companion-renderer"
            elif relative == "scripts/reports/stage_projection_figures.py":
                disposition = "adopted-shared-quantitative-policy"
            elif relative == "benchmarks/reporting/it17_hull/summarize.py":
                disposition = "reviewed-static-diagram-exception"
            elif relative.endswith("/control_figures.py") or relative.endswith("/plot.py"):
                disposition = "adopted-shared-quantitative-policy"
            elif relative.endswith("/visual_illustrations.py"):
                disposition = "reviewed-static-diagram-exception"
            elif relative.endswith("/visual_examples.py"):
                disposition = "gallery-composition-and-route"
            elif ("registered_reports.py" in path.name or path.name.startswith(("stage_", "validate_"))
                  or path.name in {"site.py", "report_data.py"}):
                disposition = "publication-validation-or-frozen-route"
            else:
                disposition = "deferred-family-specific-migration"
            entries.append({"source": relative, "signal_count": len(matches),
                            "asset_name_literals": assets, "disposition": disposition,
                            **({"role_and_disposition_reason": VIZ10_ROLE_REASONS[relative]}
                               if relative in VIZ10_ROLE_REASONS else {}),
                            **({"follow_up_issue": migration_issue(relative)}
                               if disposition == "deferred-family-specific-migration" else {})})
    return entries


def frozen_routes(root: Path) -> list[dict]:
    base = root / "reports/algorithm-results"
    routes = []
    for page in sorted(base.rglob("index.html")):
        bundle = page.parent
        figures = sorted(path for path in bundle.iterdir()
                         if path.is_file() and path.suffix.lower() in {".svg", ".png"})
        if not figures:
            continue
        route = bundle.relative_to(base).as_posix()
        entry = {"route": route, "source_bundle": route,
                 "assets": [path.name for path in figures],
                 "index_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
                 "disposition": "deferred: original frozen route-level readability review remains; companion availability is listed separately",
                 "follow_up_issue": 669}
        if route in FROZEN_COMPANIONS:
            entry["companion_route"] = FROZEN_COMPANIONS[route]
        routes.append(entry)
    return routes


def build(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    return {"schema": "csl.visual-route-inventory/1",
            "policy": {"id": "csl-report-quantitative-v1",
                       "solution": "Matplotlib 3.11.2 static SVG/PNG plus passive hand-authored SVG for reviewed diagrams",
                       "no_solver_or_geometry_runs": True},
            "source_discovery": {"method": "deterministic text scan of scripts/reports/**/*.py and benchmarks/reporting/**/*.py for SVG/PNG/savefig/write_image/render_svg signals",
                                 "review_required": "signal hits are candidate producers or route validators; inspect the role before migration"},
            "producers_and_routes": source_inventory(root),
            "frozen_published_routes": frozen_routes(root),
            "gallery_routes": [
                {"route": "examples/index.html", "assets": [
                    "examples.css", "fuel-b06-viz06.html", "fuel-b06-viz06-source.json",
                    "fuel-b06-viz06-export.json", "fuel-b06-viz03.html", "fuel-b06-viz06-before.svg",
                    "fuel-b06-viz06-flow.svg", "fuel-b06-viz06-flow.png",
                    "fuel-b06-viz06-stock.svg", "fuel-b06-viz06-stock.png",
                    "fuel-b06-viz06-trajectory.svg", "fuel-b06-viz06-trajectory.png",
                    "fuel-b06-viz06-timing.svg", "fuel-b06-viz06-timing.png",
                    "lotka-volterra-sampled-v1.html", "lotka-volterra-sampled-v1.svg",
                    "lotka-volterra-sampled-v1.png", "lotka-volterra-sampled-v1-export.json",
                    "app02-diamond-v1.html", "app02-diamond-v1.svg",
                    "app02-diamond-v1.png", "app02-diamond-v1-export.json",
                    "app04-square-v1.html", "app04-square-v1.svg",
                    "app04-square-v1.png", "app04-square-v1-export.json",
                    "app03-zonotope-v1.html", "app03-zonotope-v1.svg",
                    "app03-zonotope-v1.png", "app03-zonotope-v1-export.json",
                    "ext01-b08-timing-v1.html", "ext01-b08-timing-v1.svg",
                    "ext01-b08-timing-v1.png", "ext01-b08-timing-v1-export.json",
                    "ext05-states-v1.html", "ext05-states-v1.svg",
                    "ext05-states-v1.png", "ext05-states-v1-export.json"] + geometry_companion_assets() +
                    viz10_companion_assets(),
                 "disposition": "adopted-shared-quantitative-policy"}],
            "migration_owner": "#669 owns the shared policy; deferred family renderers link to scoped follow-up issues #684–#687, while frozen report bundles remain immutable evidence"}


def geometry_companion_assets() -> list[str]:
    from geometry_opt_companions import GEOMETRY_REPORTS, TIMING_REPORTS
    assets = ["geometry-optimization-v1.html"]
    for slug, report_id, *_ in TIMING_REPORTS:
        assets.extend((f"geometry-opt/{slug}/figure.svg", f"geometry-opt/{slug}/figure.png",
                       f"geometry-opt/{slug}/export.json", f"geometry-opt/data/{report_id}.json"))
    for slug, report_id, *_ in GEOMETRY_REPORTS:
        assets.extend((f"geometry-opt/{slug}/geometry.svg", f"geometry-opt/{slug}/geometry.png",
                       f"geometry-opt/{slug}/export.json", f"geometry-opt/data/{report_id}.json"))
    return assets


def viz10_companion_assets() -> list[str]:
    base = ROOT / "docs/examples/viz10"
    return ["viz10/" + path.relative_to(base).as_posix()
            for path in sorted(base.rglob("*")) if path.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts/reports/visual-route-inventory.json")
    args = parser.parse_args()
    result = build()
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

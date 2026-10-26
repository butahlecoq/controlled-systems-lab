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


def migration_issue(source: str) -> int:
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
            if relative.endswith("/control_figures.py") or relative.endswith("/plot.py"):
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
        routes.append({"route": route, "source_bundle": route,
                       "assets": [path.name for path in figures],
                       "index_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
                       "disposition": "justified-exception: immutable historical evidence; publish an additive companion for presentation changes"})
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
                    "fuel-b06-viz06-timing.svg", "fuel-b06-viz06-timing.png"],
                 "disposition": "adopted-shared-quantitative-policy"}],
            "migration_owner": "#669 owns the shared policy; deferred family renderers link to scoped follow-up issues #684–#687, while frozen report bundles remain immutable evidence"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts/reports/visual-route-inventory.json")
    args = parser.parse_args()
    result = build()
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

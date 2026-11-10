"""Publish all Pages augmentations together from one reviewed base artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts/reports") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts/reports"))

from scripts.reports import (
    stage_b04_c_strategy_a, stage_mpc06_tube_objective, stage_mpc06_delivery,
    stage_mpc06_offline_costs,
    stage_review05_family_query, stage_mpc11_controller_comparison,
    stage_mpc08_complete, stage_mpc07_comparison, stage_mpc10_comparison, stage_mpc11_mesh_timing,
)
from scripts.reports.mpc01 import augment_pages, stage_per_attempt

B04_SOURCE = ROOT / "reports/algorithm-results/b04-c-strategy-a-verification-v1"
MPC06_SOURCE = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1"
STRATEGY_AB_ROUTE = "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1"


def stage_all(site: Path) -> dict[str, str]:
    """Add every standalone Pages augmentation and verify their combined site."""
    if site.is_symlink() or not site.is_dir():
        raise ValueError("extracted Pages site must be a regular directory")

    per_attempt = stage_per_attempt.stage(site)
    b04_route = stage_b04_c_strategy_a.stage(B04_SOURCE, site)
    mpc06_route = stage_mpc06_tube_objective.stage(MPC06_SOURCE, site)
    mpc06_complete = stage_mpc06_delivery.stage(stage_mpc06_delivery.SOURCE, site)
    mpc06_offline = stage_mpc06_offline_costs.stage(site, parent_route=mpc06_complete)
    review05 = stage_review05_family_query.stage(site)
    mpc11 = stage_mpc11_controller_comparison.stage(site)
    mpc08 = stage_mpc08_complete.stage(site)
    mpc07 = stage_mpc07_comparison.stage(site)
    stage_per_attempt._insert_landing_link(site,mpc07+"-archive",mpc07+".zip","Download the complete robust-policy comparison evidence")
    mpc10 = stage_mpc10_comparison.stage(site)
    mpc11_studies = stage_mpc11_mesh_timing.stage(site)

    stage_per_attempt.validate(site)
    landing = site / "index.html"
    if landing.is_symlink() or not landing.is_file():
        raise ValueError("augmented Pages site has no regular root landing page")
    landing_html = landing.read_text(encoding="utf-8")
    expected_links = (
        f'href="{per_attempt.name}/index.html"',
        f'href="{STRATEGY_AB_ROUTE}/strategy-ab-ts03-summary.html"',
        f'href="{b04_route}/index.html"',
        f'href="{b04_route}.zip"',
        f'href="{mpc06_route}/index.html"',
        f'href="{mpc06_route}.zip"',
        f'href="{mpc06_complete}/index.html"',
        f'href="{mpc06_complete}.zip"',
        f'href="{mpc06_offline}/index.html"',
        f'href="{mpc06_offline}.zip"',
        f'href="{review05}/index.html"',
        f'href="{mpc11}/index.html"',
        f'href="{mpc08}/index.html"',
        f'href="{mpc08}.zip"',
        f'href="{mpc07}/index.html"',
        f'href="{mpc07}.zip"',
        f'href="{mpc10}/index.html"',
        f'href="{mpc10}.zip"',
        f'href="{mpc11_studies}/index.html"',
        f'href="{mpc11_studies}.zip"',
    )
    if any(link not in landing_html for link in expected_links):
        raise ValueError("combined Pages landing page is missing an augmentation link")

    for route, required in (
        (b04_route, ("index.html", "publication-manifest.json", "trajectory.svg")),
        (mpc06_route, ("index.html", "publication-manifest.json", "trajectory.svg")),
        (mpc06_complete, ("index.html", "publication-manifest.json", "invariant-tightenings.svg", "feasibility-grid.png")),
        (mpc06_offline, ("index.html", "publication-manifest.json", "minimal-inputs.json", "offline_check.py", "invariant-tightenings.svg")),
        (review05, ("index.html", "publication-manifest.json")),
        (mpc11, ("index.html", "publication-manifest.json")),
        (mpc08, ("index.html", "publication-manifest.json", "minimal-inputs.json", "offline_check.py", "figures/exact-critical-regions.svg", "figures/horizon-regions.svg")),
        (mpc07, ("index.html", "publication-manifest.json", "minimal-inputs.json", "offline_check.py",
                 "figures/fixed-filter-policy.svg", "figures/joint-filter-policy.svg",
                 "online-verification.json", "online-figure-data.json", "online-figure-export.json",
                 "figures/online-policy-traces.svg", "figures/online-policy-traces.png")),
        (mpc10, ("index.html", "publication-manifest.json", "minimal-inputs.json", "figures/paths.svg", "figures/branches.svg")),
        (mpc11_studies, ("index.html", "publication-manifest.json", "minimal-inputs.json", "mesh-phase-overlays.svg", "mesh-differences.svg", "timing-phases.svg")),
    ):
        report = site / route
        if report.is_symlink() or not report.is_dir() or any(
                (report / name).is_symlink() or not (report / name).is_file()
                for name in required):
            raise ValueError("combined Pages site is missing a staged report asset: " + route)
        archive = site / f"{route}.zip"
        if archive.is_symlink() or not archive.is_file():
            raise ValueError("combined Pages site is missing an offline report bundle: " + route)
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            if not all(f"{route}/{name}" in names for name in required):
                raise ValueError("combined Pages offline report bundle is incomplete: " + route)

    strategy_page = site / STRATEGY_AB_ROUTE / "strategy-ab-ts03-summary.html"
    if strategy_page.is_symlink() or not strategy_page.is_file():
        raise ValueError("combined Pages site is missing the Strategy A/B T-S03 report")
    return {"mpc01": per_attempt.name, "b04_c": b04_route, "mpc06": mpc06_route, "mpc06_complete": mpc06_complete, "mpc06_offline": mpc06_offline, "review05": review05, "mpc11": mpc11, "mpc08": mpc08, "mpc07": mpc07, "mpc10": mpc10, "mpc11_studies": mpc11_studies}


def augment(download: Path, destination: Path) -> dict[str, str]:
    site = augment_pages.extract_pages_site(download, destination)
    return stage_all(site)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(augment(args.download, args.site), sort_keys=True))


if __name__ == "__main__":
    main()

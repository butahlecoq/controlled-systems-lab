"""Stage the saved B08 MIQCP result and add its gallery card."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
from mpc03.b08_report import render_html, render_svg

REPORT_ID = "mpc03-b08-l04-miQCP-v1"
FILES = ("solver-output.json", "independent-oracle.json", "record.json", "index.html", "disturbance-tube.svg")
CARD = (
    '<article class="saved-figure" id="mpc03-b08-l04-miQCP-v1">'
    '<h3>B08: robust minimax and its convex-hull bound</h3>'
    '<a href="../mpc03-b08-l04-miQCP-v1/index.html">'
    '<img src="../mpc03-b08-l04-miQCP-v1/disturbance-tube.svg" '
    'alt="B08 four-state disturbance histories projected onto oxidizer and fuel flow coordinates"></a>'
    '<p>Four-state L04 displayed-data MIQCP with exact finite enumeration and a continuous-control lower bound. '
    'The figure shows the stage-by-stage disturbance tube projected to two flow coordinates.</p>'
    '<p><a href="../mpc03-b08-l04-miQCP-v1/index.html">Open the saved report, raw results and exact oracle →</a></p></article>'
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def stage(source: Path, site: Path) -> None:
    source = Path(source).resolve()
    site = Path(site).resolve()
    require(source.is_dir(), "B08 saved result bundle is missing")
    for name in FILES:
        path = source / name
        require(path.is_file() and not path.is_symlink(), "missing or unsafe B08 report asset: " + name)
    record = json.loads((source / "record.json").read_text(encoding="utf-8"))
    solver = json.loads((source / "solver-output.json").read_text(encoding="utf-8"))
    oracle = json.loads((source / "independent-oracle.json").read_text(encoding="utf-8"))
    require(record.get("solver_output_sha256") == digest(source / "solver-output.json"),
            "B08 solver output hash differs")
    require(record.get("oracle_sha256") == digest(source / "independent-oracle.json"),
            "B08 exact oracle hash differs")
    require(record.get("schema") == "csl.mpc03-b08-miQCP-record/1", "unexpected B08 record schema")
    require(solver.get("schema") == "csl.mpc03-b08-solver-output/1", "unexpected B08 solver schema")
    require(record.get("source_commit") == solver.get("source_commit"), "B08 source commit differs")
    require(record.get("scenario_sha256") == solver.get("scenario_sha256"), "B08 scenario hash differs")
    result = record.get("result", {})
    require(result.get("finite") == solver.get("finite_miqcp"),
            "B08 finite-action solver result differs from saved record")
    require(result.get("relaxation") == solver.get("convex_control_qcp"),
            "B08 relaxation solver result differs from saved record")
    require(record.get("result", {}).get("exact_reference") == oracle,
            "B08 record and independent oracle differ")
    require(solver.get("disturbance_history_count") == 256, "B08 does not retain all disturbance histories")
    stages = record.get("result", {}).get("projected_tube", [])
    require([stage.get("corner_history_count") for stage in stages] == [1, 4, 16, 64, 256],
            "B08 projected tube does not retain every stage corner history")
    driver = ROOT / solver.get("driver_path", "")
    require(driver.is_file() and not driver.is_symlink(), "B08 source driver is missing or unsafe")
    require(solver.get("driver_sha256") == digest(driver), "B08 source driver hash differs")
    require((source / "index.html").read_text(encoding="utf-8") == render_html(record),
            "B08 HTML differs from deterministic saved-record rendering")
    require((source / "disturbance-tube.svg").read_text(encoding="utf-8") == render_svg(record),
            "B08 SVG differs from deterministic saved-record rendering")
    gallery = site / "examples/index.html"
    require(gallery.is_file() and not gallery.is_symlink(), "visual examples gallery is missing")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    card_id = 'id="mpc03-b08-l04-miQCP-v1"'
    require(marker in html or card_id in html, "visual examples gallery insertion point is missing")
    require(card_id not in html or CARD in html, "B08 gallery route conflicts with existing content")
    route = site / REPORT_ID
    route.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(source / name, route / name)
    if card_id not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT / "reports/algorithm-results" / REPORT_ID)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()

"""Stage the saved MPC-03 pilot report and link it from the examples gallery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


REPORT_ID = "mpc03-open-loop-pilot-v1"
FILES = ("index.html", "record.json", "pilot-output.json", "build-provenance.json", "disturbance-tube.svg")
CARD = (
    '<article class="saved-figure" id="mpc03-open-loop-pilot-v1">'
    '<p class="eyebrow">Open-loop minimax · formulation pilot</p>'
    '<h3>A robust two-stage minimax bound</h3>'
    '<a href="../mpc03-open-loop-pilot-v1/index.html">'
    '<img src="../mpc03-open-loop-pilot-v1/disturbance-tube.svg" '
    'alt="Four endpoint disturbance histories projected onto intermediate and terminal state coordinates."></a>'
    '<p>A synthetic scalar example: finite actions and a shared-selector MILP give 2.25; '
    'the convex action relaxation gives lower bound 2.0. No timing is measured.</p>'
    '<p><a href="../mpc03-open-loop-pilot-v1/index.html">Open the saved report and raw record →</a></p></article>'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def stage(source: Path, site: Path) -> None:
    source = source.resolve()
    site = site.resolve()
    require(source.is_dir(), "MPC-03 saved report bundle is missing")
    provenance = json.loads((source / "build-provenance.json").read_text(encoding="utf-8"))
    record = json.loads((source / "record.json").read_text(encoding="utf-8"))
    raw = (source / "pilot-output.json").read_bytes()
    require(record.get("schema") == "csl.mpc03-open-loop-pilot-record/1",
            "unexpected MPC-03 record schema")
    require(record.get("result") == json.loads(raw), "saved raw output differs from the report record")
    require(provenance.get("schema") == "csl.mpc03-pilot-provenance/1" and
            provenance.get("output_sha256") == hashlib.sha256(raw).hexdigest(),
            "MPC-03 output provenance hash differs")
    require(record.get("provenance") == provenance, "record and provenance metadata differ")
    scenario_hash = hashlib.sha256(json.dumps(record.get("scenario"), sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    require(record.get("scenario_sha256") == scenario_hash, "MPC-03 scenario hash differs")
    require(provenance.get("driver_path") == "benchmarks/reporting/mpc03/robust_minimax_driver.cpp",
            "unexpected MPC-03 driver path")
    driver = Path(__file__).resolve().parents[2] / provenance["driver_path"]
    require(driver.is_file() and not driver.is_symlink() and
            provenance.get("driver_sha256") == hashlib.sha256(driver.read_bytes()).hexdigest(),
            "MPC-03 driver provenance hash differs")
    for name in FILES:
        path = source / name
        require(path.is_file() and not path.is_symlink(), "missing or unsafe MPC-03 report asset: " + name)
    gallery = site / "examples/index.html"
    require(gallery.is_file() and not gallery.is_symlink(), "visual examples gallery is missing")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    require(marker in html or 'id="mpc03-open-loop-pilot-v1"' in html,
            "visual examples gallery insertion point is missing")
    require('id="mpc03-open-loop-pilot-v1"' not in html or CARD in html,
            "MPC-03 gallery route collides with existing content")
    route = site / REPORT_ID
    route.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(source / name, route / name)
    if 'id="mpc03-open-loop-pilot-v1"' not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()

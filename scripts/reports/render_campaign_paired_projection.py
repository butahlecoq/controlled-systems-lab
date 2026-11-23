"""Recreate a paired fuel projection SVG from one saved plotted-data record."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_full_profile_campaign as campaign  # noqa: E402


def render(data_path: Path) -> tuple[Path, Path, Path]:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if data.get("schema") != "csl.closed-loop-campaign-plotted-data/1":
        raise ValueError(f"unsupported plotted-data schema in {data_path}")
    if data.get("task_name") != "syn-nl-fuel-01":
        raise ValueError("paired mass/flow projections require the SYN-NL-FUEL-01 task")
    report_dir = data_path.resolve().parents[2]
    figure_id = f"{data['task_name']}-{data['representation']}-paired"
    svg_path = report_dir / f"{figure_id}.svg"
    provenance_path = report_dir / f"{figure_id}.json"
    contract_path = report_dir / "raw/task-contracts/syn-nl-fuel-01.json"
    manifest_path = report_dir / "provenance-manifest.json"
    contract = campaign.read_json(contract_path)
    provenance = campaign.read_json(provenance_path)
    svg = campaign.draw_paired_svg_from_plot_data(data)
    svg_bytes = (svg + "\n").encode("utf-8")
    svg_path.write_bytes(svg_bytes)
    provenance["svg_sha256"] = hashlib.sha256(svg_bytes).hexdigest()
    provenance["renderer_source_commit"] = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    page = campaign.paired_example_html(data, provenance, contract)
    page_path = report_dir / f"{figure_id}.html"
    page_path.write_text(page, encoding="utf-8")

    manifest = campaign.read_json(manifest_path)
    for path in (svg_path, provenance_path, page_path):
        manifest["files_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    (report_dir / "provenance-manifest.json.sha256").write_text(
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  provenance-manifest.json\n",
        encoding="utf-8",
    )
    return svg_path, page_path, provenance_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="saved plotted-data JSON")
    args = parser.parse_args()
    render(args.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

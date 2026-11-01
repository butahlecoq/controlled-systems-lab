"""Verify and stage the saved EXT-02 finite/mixed-control report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "ext02-two-state-mixed-v1"
BUNDLE = ROOT / "reports/algorithm-results" / REPORT_ID
FILES = {"README.md", "SHA256SUMS", "figure.svg", "index.html", "measurement.json",
         "raw.jsonl", "stderr.txt", "trials.csv"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(bundle: Path) -> dict[str, bytes]:
    if bundle.is_symlink() or not bundle.is_dir() or {p.name for p in bundle.iterdir()} != FILES:
        raise ValueError("EXT-02 report file inventory differs")
    files = {path.name: path.read_bytes() for path in bundle.iterdir()}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate EXT-02 report checksum")
        checksums[name] = checksum
    if checksums != {name: digest(value) for name, value in files.items() if name != "SHA256SUMS"}:
        raise ValueError("EXT-02 report checksum mismatch")
    record = json.loads(files["measurement.json"])
    summary = record.get("summary", {})
    if (record.get("schema") != "csl.ext02-portfolio-record/1" or
            record.get("scenario_sha256") is None or record.get("executable_sha256") is None or
            summary.get("trials") != 7 or summary.get("failures") != 0 or
            summary.get("horizon") != 1 or summary.get("catalogue_size") != 3 or
            summary.get("history_count") != 3 or summary.get("retained_relation_rows", 0) <= 0):
        raise ValueError("EXT-02 report evidence is incomplete")
    return files


def catalog_entry(bundle: Path = BUNDLE) -> dict:
    files = verified_bundle(bundle)
    record = json.loads(files["measurement.json"])
    zip_path = bundle.with_suffix(".zip")
    if not zip_path.is_file() or zip_path.is_symlink():
        raise ValueError("EXT-02 offline ZIP is missing")
    return {"report_id": REPORT_ID, "source_commit": record["source_commit"],
            "scenario_sha256": record["scenario_sha256"],
            "measurement_sha256": digest(files["measurement.json"]),
            "zip_sha256": digest(zip_path.read_bytes()),
            "measured_scope": "Seven solve calls on one analytic two-state, one-stage mixed-control fixture",
            "evidence_limits": "One binary64 fixture; no comparator, performance winner, hard RSS bound, or general scalability claim"}


def stage(catalog: Path, site: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    if data.get("schema") != "csl.ext02-publications/1" or not isinstance(data.get("reports"), list):
        raise ValueError("EXT-02 publication catalog differs")
    expected = catalog_entry(BUNDLE)
    if data["reports"] != [expected]:
        raise ValueError("EXT-02 publication catalog differs from the saved report")
    files = verified_bundle(BUNDLE)
    zip_path = BUNDLE.with_suffix(".zip")
    site = Path(site)
    index_path = site / "index.html"
    index = index_path.read_text(encoding="utf-8")
    if not site.is_dir() or site.is_symlink() or index.count("</ul>") != 1:
        raise ValueError("EXT-02 Pages insertion point differs")
    destination = site / REPORT_ID
    if destination.exists() or destination.is_symlink():
        raise ValueError("EXT-02 Pages route must be fresh")
    route = (f'<li><a href="{REPORT_ID}/index.html">EXT-02 finite/mixed branch portfolio</a>'
             f' · <a href="{REPORT_ID}/figure.svg">2D branch geometry</a>'
             f' · <a href="{REPORT_ID}/measurement.json">saved measurements</a>'
             f' · <a href="{REPORT_ID}/{REPORT_ID}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    shutil.copyfile(zip_path, destination / f"{REPORT_ID}.zip")
    index_path.write_text(index.replace("</ul>", route + "</ul>"), encoding="utf-8")
    return REPORT_ID


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.ext02-publications/1", "reports": [catalog_entry()]},
                         indent=2, sort_keys=True))
    elif not args.source and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source, or --catalog and --site")

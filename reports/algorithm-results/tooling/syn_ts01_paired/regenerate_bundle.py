"""Regenerate the paired T-S01 HTML, figure, CSV and manifest from a saved bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import report


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def regenerate(source: Path, out: Path):
    record = report.validate_bundle(source)
    if out.exists():
        raise ValueError("refusing to overwrite regenerated bundle")
    out.mkdir(parents=True)
    derived = {"index.html", "performance.svg", "trials.csv", "manifest.json"}
    for name in sorted(report.BUNDLE_FILES - derived):
        (out / name).write_bytes((source / name).read_bytes())
    (out / "index.html").write_text(report.render_html(record), encoding="utf-8", newline="")
    (out / "performance.svg").write_text(report.render_svg(record), encoding="utf-8", newline="")
    (out / "trials.csv").write_bytes(report.trials_csv_bytes(record))
    files = {name: (out / name).read_bytes() for name in report.BUNDLE_FILES - {"manifest.json"}}
    (out / "manifest.json").write_bytes(report.bundle_manifest_bytes(record, files))
    report.validate_bundle(out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "report_id": record["report_id"],
        "out": str(out),
        "files": len(report.BUNDLE_FILES),
        "manifest_sha256": hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest(),
        "events_sha256": manifest["files"]["measurement-events.jsonl"],
        "solver_ran": False,
    }, sort_keys=True, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    regenerate(args.source, args.out)


if __name__ == "__main__":
    main()

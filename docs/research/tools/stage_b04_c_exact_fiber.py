"""Validate and stage the B04-C result bundle as a stable Pages route."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from check_b04_c_exact_fiber import check
from render_b04_c_exact_fiber_report import render

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/research/evidence/b04-c-exact-dyadic-v1"
ROUTE = "b04-c-exact-dyadic-v1"


def stage(source: Path, site: Path) -> Path:
    if source.is_symlink() or site.is_symlink():
        raise ValueError("B04-C source and site roots cannot be symlinks")
    source = source.resolve(strict=True)
    site = site.resolve(strict=True)
    if source.name != ROUTE or not source.is_dir():
        raise ValueError("B04-C source bundle identity differs")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("evidence_files")
    if manifest.get("schema") != "csl.b04-c-exact-dyadic-manifest/1" or not isinstance(files, dict):
        raise ValueError("B04-C evidence manifest schema differs")
    expected = set(files) | {"manifest.json"}
    actual = {item.name for item in source.iterdir() if item.is_file() and not item.is_symlink()}
    if actual != expected or any(item.is_symlink() for item in source.iterdir()):
        raise ValueError("B04-C evidence bundle inventory differs")
    for name, checksum in files.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("B04-C evidence hash mismatch: " + name)
    check(source / "record.json")
    if (source / "index.html").read_text(encoding="utf-8") != render():
        raise ValueError("B04-C report page differs from the verified record")
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("B04-C Pages route already exists")
    shutil.copytree(source, destination, symlinks=False)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

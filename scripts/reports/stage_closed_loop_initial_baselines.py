#!/usr/bin/env python3
"""Stage the immutable source-only initial closed-loop baseline report."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "closed-loop-initial-baselines-v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(source: Path, site: Path) -> None:
    source, site = source.resolve(), site.resolve()
    manifest_path = source / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.closed-loop-initial-baseline-publication/1":
        raise ValueError("unsupported initial-baseline publication manifest")
    for relative, expected in manifest["files"].items():
        path = source / relative
        if path.is_symlink() or not path.is_file() or source not in path.resolve().parents:
            raise ValueError(f"unsafe or missing report asset: {relative}")
        if path.stat().st_size != expected["bytes"] or sha(path) != expected["sha256"]:
            raise ValueError(f"report asset hash mismatch: {relative}")
    archive = source.parent / f"{REPORT_ID}.zip"
    if (
        not archive.is_file()
        or archive.is_symlink()
        or sha(archive) != manifest["archive"]["sha256"]
    ):
        raise ValueError("frozen evidence ZIP is missing or its hash differs")
    route = site / REPORT_ID
    route.mkdir(parents=True, exist_ok=True)
    for relative in (*manifest["files"], "publication-manifest.json"):
        target = route / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != (source / relative).read_bytes():
            raise ValueError(f"existing Pages route differs from frozen source: {relative}")
        shutil.copyfile(source / relative, target)
    target_archive = site / f"{REPORT_ID}.zip"
    if target_archive.exists() and sha(target_archive) != manifest["archive"]["sha256"]:
        raise ValueError("existing Pages ZIP differs from frozen evidence")
    shutil.copyfile(archive, target_archive)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "reports" / REPORT_ID)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()

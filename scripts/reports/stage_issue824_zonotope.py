"""Verify and stage the issue #824 zonotope bundle for the visual gallery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2"
ROUTE = "issue824-two-points-zonotope-pilot-v2"
FILES = ("README.md", "capture.json", "check.json", "figure-data.json", "index.html",
         "planar-example.html", "planar-example.svg", "projections.svg", "result.json", "SHA256SUMS")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {item.name for item in source.iterdir()} != set(FILES):
        raise ValueError("issue #824 zonotope report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate issue #824 report checksum")
        sums[name] = checksum
    if sums != {name: digest(value) for name, value in files.items() if name != "SHA256SUMS"}:
        raise ValueError("issue #824 report checksum mismatch")
    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    if (capture.get("source_tree_clean_before_report_generation") is not True or
            result.get("schema") != "csl.issue824-two-points-box-minimax/2" or
            check.get("status") != "verified" or
            not check.get("planar_zonotope_inclusion")):
        raise ValueError("issue #824 report lacks a clean capture or verified planar inclusion")
    for name, expected in capture["source_files_sha256"].items():
        path = ROOT / name
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError("issue #824 source identity differs: " + name)
    planar = files["planar-example.html"].decode("utf-8")
    if "Complete minimal input" not in planar or "Exact reachable corners" not in planar:
        raise ValueError("issue #824 planar example omits its inputs or checked answer")
    return files


def stage(source: Path, site: Path) -> str:
    files = verified_bundle(source)
    site = site.resolve(strict=True)
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 Pages route already exists")
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    return ROUTE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

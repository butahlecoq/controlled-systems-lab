"""Verify and stage the issue #824 zonotope minimax bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_source_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-minimax-v1"
ROUTE = "issue824-two-points-zonotope-minimax-v1"
ROUTES = {ROUTE, "issue824-two-points-zonotope-minimax-v2"}
FILES = ("README.md", "capture.json", "check.json", "figure-data.json", "index.html",
         "planar-example.html", "planar-example.svg", "projections.svg", "result.json", "SHA256SUMS")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {item.name for item in source.iterdir()} != set(FILES):
        raise ValueError("issue #824 zonotope minimax report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate issue #824 zonotope minimax checksum")
        sums[name] = checksum
    if sums != {name: digest(value) for name, value in files.items() if name != "SHA256SUMS"}:
        raise ValueError("issue #824 zonotope minimax checksum mismatch")
    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    if (capture.get("source_tree_clean_before_report_generation") is not True or
            result.get("schema") != "csl.issue824-two-points-zonotope-minimax/1" or
            check.get("status") != "verified" or
            not check.get("planar_zonotope_inclusion")):
        raise ValueError("issue #824 zonotope minimax report lacks a clean capture or verified planar inclusion")
    if not report_source_identity.source_hashes_match_commit(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("issue #824 zonotope minimax source files differ from the captured commit")
    planar = files["planar-example.html"].decode("utf-8")
    if "Every fixed control candidate" not in planar or "selected plan worst-history replay" not in planar:
        raise ValueError("issue #824 planar selector example omits candidate scores or replay")
    return files


def stage(source: Path, site: Path) -> str:
    files = verified_bundle(source)
    route = source.name
    if route not in ROUTES:
        raise ValueError("unknown issue #824 zonotope minimax report version")
    check = json.loads(files["check.json"])
    if route.endswith("-v2") and "every exact facet inequality" not in check.get(
            "stage_zonotope_relation", ""):
        raise ValueError("issue #824 zonotope v2 lacks exact full-set inclusion evidence")
    site = site.resolve(strict=True)
    destination = site / route
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 zonotope minimax Pages route already exists")
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    return route


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

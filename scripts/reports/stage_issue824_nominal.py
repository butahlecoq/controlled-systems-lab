"""Verify and stage the issue #824 classic nominal report bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "exp824"))
import check_nominal
import report_source_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-nominal-v1"
ROUTE = "issue824-two-points-nominal-v1"
FILES = ("README.md", "capture.json", "check.json", "figure-data.json", "index.html",
         "projections.svg", "result.json", "SHA256SUMS")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {path.name for path in source.iterdir()} != set(FILES):
        raise ValueError("issue #824 nominal report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate issue #824 nominal checksum")
        sums[name] = checksum
    if sums != {name: digest(content) for name, content in files.items() if name != "SHA256SUMS"}:
        raise ValueError("issue #824 nominal checksum mismatch")
    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    if (capture.get("source_worktree_clean") is not True or
            result.get("schema") != "csl.issue824-two-points-nominal-bundle/1" or
            check.get("status") != "passed" or result.get("independent_check") != check):
        raise ValueError("issue #824 nominal bundle lacks clean source capture or independent replay evidence")
    if not report_source_identity.source_hashes_match_commit(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("issue #824 nominal source differs from the captured commit")
    native = result["nominal_result"]
    if check_nominal.check(native) != check:
        raise ValueError("issue #824 nominal checker result differs from the saved check")
    svg = files["projections.svg"].decode("utf-8")
    if "Classic nominal replay (fixed v=+1)" not in svg or "Forward/backward intersection" not in svg:
        raise ValueError("issue #824 nominal figure is missing the nominal path or minimax geometry")
    return files


def stage(source: Path, site: Path) -> str:
    files = verified_bundle(source)
    site = site.resolve(strict=True)
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 nominal Pages route already exists")
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

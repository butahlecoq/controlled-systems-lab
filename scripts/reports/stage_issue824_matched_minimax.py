"""Verify and stage the matched five-track issue #824 minimax report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "exp824"))
import check_matched_minimax
import report_source_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-matched-minimax-v1"
ROUTE = "issue824-two-points-matched-minimax-v1"
FILES = {"README.md", "capture.json", "check.json", "e2e-timing.json",
         "geometry-reference-ellipsoid.svg", "geometry-reference-parallelotope.svg",
         "index.html", "limiter-profile.json", "result.json", "SHA256SUMS"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {item.name for item in source.iterdir()} != FILES:
        raise ValueError("issue #824 matched minimax bundle inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate issue #824 matched minimax checksum")
        sums[name] = checksum
    if sums != {name: digest(content) for name, content in files.items() if name != "SHA256SUMS"}:
        raise ValueError("issue #824 matched minimax checksum mismatch")
    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    e2e = json.loads(files["e2e-timing.json"])
    profile = json.loads(files["limiter-profile.json"])
    if (capture.get("source_tree_clean_before_report_generation") is not True or
            result.get("schema") != "csl.issue824.matched-minimax-benchmark/1" or
            check.get("status") != "verified" or result.get("check") not in (None, check) or
            e2e.get("schema") != "csl.issue824.matched-minimax-e2e/1" or
            len(e2e.get("trials", [])) != 5 or any(
                row.get("status") != "completed" or row.get("failures") != 0 or
                row.get("sample_count") != 25 for row in e2e["trials"]) or
            profile.get("schema") != "csl.issue824.matched-minimax-limiter/1" or
            profile.get("method") != "zonotope"):
        raise ValueError("issue #824 matched minimax evidence is incomplete")
    if check_matched_minimax.check(result) != check:
        raise ValueError("issue #824 matched minimax rational checker result differs")
    if not report_source_identity.source_hashes_match_commit(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("issue #824 matched minimax source differs from its captured commit")
    for key, figure in (("ellipsoid", "geometry-reference-ellipsoid.svg"),
                        ("parallelotope", "geometry-reference-parallelotope.svg")):
        if capture.get("figure_sources", {}).get(key, {}).get("sha256") != digest(files[figure]):
            raise ValueError(f"issue #824 {key} geometry figure differs from its source bundle")
    page = files["index.html"].decode("utf-8")
    if ("(x1,x2)" not in page or "(x3,x4)" not in page or
            "upstream differential game" not in page or "continuous-action 10-second RL task" not in page or
            "does not establish a general winner" not in page):
        raise ValueError("issue #824 matched minimax page omits its projections or evidence limits")
    return files


def stage(source: Path, site: Path) -> str:
    site = site.resolve(strict=True)
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 matched minimax Pages route already exists")
    if source.name != ROUTE:
        raise ValueError("unknown issue #824 matched minimax report version")
    files = verified_bundle(source)
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

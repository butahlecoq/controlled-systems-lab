"""Verify and stage the issue #824 four-state box-minimax report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_source_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-box-pilot-v4"
ROUTE = "issue824-two-points-box-pilot-v4"
FILES = ("README.md", "SHA256SUMS", "capture.json", "check.json", "figure-data.json",
         "index.html", "projections.svg", "result.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {path.name for path in source.iterdir()} != set(FILES):
        raise ValueError("issue #824 box-minimax report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate issue #824 box-minimax checksum")
        checksums[name] = checksum
    if checksums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("issue #824 box-minimax checksum mismatch")

    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    box = result.get("box_method", {})
    exact = result.get("exact_reference", {})
    if (capture.get("source_tree_clean_before_report_generation") is not True or
            result.get("schema") != "csl.issue824-two-points-box-minimax/1" or
            result.get("environment") != "TwoPointsOnParallelLines" or
            check.get("status") != "verified" or
            check.get("exact_finite_minimax_value") != exact.get("finite_minimax_value") or
            check.get("selected_plan_replay_value") != box.get("full_catalogue_replay_value") or
            len(box.get("stages", [])) != 4 or len(box.get("all_plan_scores", [])) != 27 or
            "every exact finite-catalog state checked at every stage" not in
            check.get("stage_box_inclusion", "") or
            "not a validated bound" not in check.get("objective_bound_status", "")):
        raise ValueError("issue #824 box-minimax report lacks verified stage, replay, or scope evidence")
    if not report_source_identity.source_hashes_match_commit(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("issue #824 box-minimax source differs from the captured commit")
    figure = files["projections.svg"].decode("utf-8")
    if ("x1 position" not in figure or "x2 velocity" not in figure or
            "x3 position" not in figure or "x4 velocity" not in figure or
            "Box-selected plan replay" not in figure):
        raise ValueError("issue #824 box-minimax figure omits player projections or replay")
    return files


def stage(source: Path, site: Path) -> str:
    files = verified_bundle(source)
    site = site.resolve(strict=True)
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 box-minimax Pages route already exists")
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

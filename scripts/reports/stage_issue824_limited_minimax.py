"""Verify and stage the resource-limited matched Issue 824 minimax report."""
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
ROUTE = "issue824-two-points-matched-minimax-resource-v1"
SOURCE = ROOT / "reports/algorithm-results" / ROUTE
FILES = {
    "README.md", "capture.json", "check.json", "e2e-timing.json",
    "geometry-reference-ellipsoid.svg", "geometry-reference-parallelotope.svg",
    "index.html", "limiter-profile.json", "result.json", "resource-profile.json",
    "SHA256SUMS",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {item.name for item in source.iterdir()} != FILES:
        raise ValueError("resource-limited Issue 824 bundle inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums: dict[str, str] = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate resource-limited Issue 824 checksum")
        sums[name] = checksum
    expected = {name: digest(content) for name, content in files.items() if name != "SHA256SUMS"}
    if sums != expected:
        raise ValueError("resource-limited Issue 824 checksums differ")

    capture = json.loads(files["capture.json"])
    check = json.loads(files["check.json"])
    result = json.loads(files["result.json"])
    e2e = json.loads(files["e2e-timing.json"])
    limiter = json.loads(files["limiter-profile.json"])
    resource_file = json.loads(files["resource-profile.json"])
    accounting = capture.get("resource_accounting", {})
    requested = resource_file.get("requested_limits", {})
    enforced = resource_file.get("enforced_limits", {})
    observed = resource_file.get("observed", {})
    if (capture.get("schema") != "csl.issue824.matched-minimax-capture/2" or
            capture.get("source_tree_clean_before_report_generation") is not True or
            result.get("schema") != "csl.issue824.matched-minimax-benchmark/1" or
            check_matched_minimax.check(result) != check or
            check.get("status") not in ("verified", "incomplete") or
            check.get("attempts_observed") != len(result.get("samples", [])) or
            check.get("measurement_samples_verified", 0) + check.get("failures", -1) != check.get("attempts_observed") or
            e2e.get("schema") != "csl.issue824.matched-minimax-e2e/1" or len(e2e.get("trials", [])) != 5 or
            any(row.get("status") != "completed" or row.get("sample_count") != 25 or
                len(row.get("failed_attempts", [])) != row.get("failures") for row in e2e["trials"]) or
            limiter.get("schema") != "csl.issue824.matched-minimax-limiter/1" or
            limiter.get("method") != "zonotope" or
            capture.get("limiter_profile_source_bundle") != "issue824-two-points-matched-minimax-v1" or
            resource_file.get("schema") != "csl.issue824.resource-profile/1" or
            resource_file.get("profile") != "comparison-program-default-enforced" or
            resource_file.get("status") != "completed" or
            requested.get("process_tree_wall_time_seconds") != 300 or
            requested.get("process_tree_memory_bytes") != 8 * 1024**3 or
            requested.get("maximum_concurrent_jobs") != 1 or
            enforced.get("process_tree_wall_time") is not True or
            enforced.get("process_tree_memory") is not True or
            enforced.get("memory_max_bytes") != 8 * 1024**3 or
            observed.get("timed_out") is not False or observed.get("exit_code") != 0 or
            observed.get("process_tree_peak_memory_bytes", 2**64) > 8 * 1024**3 or
            any(not event.endswith(" 0") for event in observed.get("memory_events", [])
                if event.startswith(("max ", "oom ", "oom_kill ", "oom_group_kill "))) or
            accounting.get("policy") != "comparison-program-default-enforced" or
            accounting.get("enforced_limits", {}).get("process_tree_memory") is not True):
        raise ValueError("resource-limited Issue 824 evidence is incomplete or inconsistent")
    if not report_source_identity.source_hashes_match_commit_or_checkout(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("resource-limited Issue 824 source differs from its captured commit")
    for key, filename in (("ellipsoid", "geometry-reference-ellipsoid.svg"),
                          ("parallelotope", "geometry-reference-parallelotope.svg")):
        if capture.get("figure_sources", {}).get(key, {}).get("sha256") != digest(files[filename]):
            raise ValueError(f"resource-limited Issue 824 {key} source figure differs")
    page = files["index.html"].decode("utf-8")
    if ("(x1,x2)" not in page or "(x3,x4)" not in page or
            "8 GiB cgroup-v2 memory cap" not in page or "does not establish a general winner" not in page or
            "continuous-action 10-second RL task" not in page or "uncapped" in page):
        raise ValueError("resource-limited Issue 824 page omits its evidence limits")
    return files


def stage(source: Path, site: Path) -> str:
    site = site.resolve(strict=True)
    destination = site / ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("resource-limited Issue 824 route already exists")
    if source.name != ROUTE:
        raise ValueError("unknown resource-limited Issue 824 version")
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

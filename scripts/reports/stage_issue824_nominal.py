"""Verify and stage the issue #824 classic nominal report bundle."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "exp824"))
import check_nominal
import report_source_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/issue824-two-points-nominal-v1"
BASE_FILES = {"README.md", "capture.json", "check.json", "figure-data.json", "index.html",
              "projections.svg", "result.json", "SHA256SUMS"}
V2_FILES = BASE_FILES | {"e2e-timing.json", "limiter-profile.json", "limiter-profile.txt",
                         "limiter-profile-raw.tar.gz"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    version = {"issue824-two-points-nominal-v1": "1",
               "issue824-two-points-nominal-v2": "2"}.get(source.name, "")
    expected = V2_FILES if version == "2" else BASE_FILES if version == "1" else set()
    if source.is_symlink() or not source.is_dir() or {path.name for path in source.iterdir()} != expected:
        raise ValueError("issue #824 nominal report inventory differs")
    files = {name: (source / name).read_bytes() for name in expected}
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
            result.get("schema") != f"csl.issue824-two-points-nominal-bundle/{version}" or
            check.get("status") != "passed" or result.get("independent_check") != check):
        raise ValueError("issue #824 nominal bundle lacks clean source capture or independent replay evidence")
    if not report_source_identity.source_hashes_match_commit(
            ROOT, capture.get("source_commit", ""), capture.get("source_files_sha256", {})):
        raise ValueError("issue #824 nominal source differs from the captured commit")
    native = result["nominal_result"]
    if check_nominal.check(native) != check:
        raise ValueError("issue #824 nominal checker result differs from the saved check")
    if version == "2":
        measurement = result.get("measurement", {})
        profile = measurement.get("limiter_profile", {})
        e2e = measurement.get("end_to_end_report_generation", {})
        saved_profile = json.loads(files["limiter-profile.json"])
        saved_e2e = json.loads(files["e2e-timing.json"])
        if (profile.get("performed") is not True or profile.get("failures") != 0 or
                profile.get("profile_runs") != 5 or profile.get("total_profiled_calls") != 350 or
                profile.get("timings_used_as_performance_evidence") is not False or
                e2e.get("run_count") != 5 or e2e.get("all_checks_passed") is not True or
                e2e.get("all_score_checksums_match") is not True or
                saved_profile.get("schema") != "csl.issue824-nominal-limiter-profile/1" or
                saved_profile.get("merged_top_self_cpu_samples") != profile.get("top_self_cpu_samples") or
                saved_e2e.get("schema") != e2e.get("schema") or
                saved_e2e.get("runs") != e2e.get("runs") or
                saved_e2e.get("summary", {}).get("median_wall_ns") != e2e.get("median_wall_ns")):
            raise ValueError("issue #824 nominal v2 is missing valid limiter or end-to-end evidence")
        try:
            with tarfile.open(fileobj=io.BytesIO(files["limiter-profile-raw.tar.gz"]), mode="r:gz") as archive:
                names = archive.getnames()
        except (tarfile.TarError, OSError) as error:
            raise ValueError("issue #824 nominal v2 raw profiler archive is invalid") from error
        if (sum(name.startswith("gmon-") and name.endswith(".out") for name in names) != 5 or
                sum(name.startswith("gprof-run-") and name.endswith(".json") for name in names) != 5 or
                "gprof-flat.txt" not in names or "gprof-profile.txt" not in names):
            raise ValueError("issue #824 nominal v2 raw profiler archive is incomplete")
    svg = files["projections.svg"].decode("utf-8")
    if "Classic nominal replay (fixed v=+1)" not in svg or "Forward/backward intersection" not in svg:
        raise ValueError("issue #824 nominal figure is missing the nominal path or minimax geometry")
    return files


def stage(source: Path, site: Path) -> str:
    files = verified_bundle(source)
    site = site.resolve(strict=True)
    destination = site / source.name
    if destination.exists() or destination.is_symlink():
        raise ValueError("issue #824 nominal Pages route already exists")
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    return source.name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

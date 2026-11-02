#!/usr/bin/env python3
"""Finalize an independently supervised Issue 824 report bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESOURCE_BUNDLE = "issue824-two-points-matched-minimax-resource-v1"
FILES = (
    "README.md", "capture.json", "check.json", "e2e-timing.json",
    "geometry-reference-ellipsoid.svg", "geometry-reference-parallelotope.svg",
    "index.html", "limiter-profile.json", "result.json",
)
SUPERVISION_SOURCES = (
    "scripts/reports/exp824/run_limited_capture.py",
    "scripts/reports/exp824/finalize_limited_report.py",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("resource_profile", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {args.output}")

    capture_dir = args.capture_dir.resolve(strict=True)
    resource_bytes = args.resource_profile.resolve(strict=True).read_bytes()
    resource = json.loads(resource_bytes)
    if resource.get("schema") != "csl.issue824.resource-profile/1":
        raise ValueError("unknown resource profile schema")
    observed = resource["observed"]
    if (resource.get("status") != "completed" or observed.get("exit_code") != 0 or
            observed.get("timed_out") is not False or
            any(not event.endswith(" 0") for event in observed.get("memory_events", [])
                if event.startswith(("max ", "oom ", "oom_kill ", "oom_group_kill ")))):
        raise ValueError("resource-limited capture did not complete cleanly")
    files = {name: (capture_dir / name).read_bytes() for name in FILES}
    capture = json.loads(files["capture.json"])
    previous_capture = json.loads((ROOT / "reports/algorithm-results/issue824-two-points-matched-minimax-v1/capture.json").read_text(encoding="utf-8"))

    source_files = dict(capture["source_files_sha256"])
    for relative in SUPERVISION_SOURCES:
        source_files[relative] = digest((ROOT / relative).read_bytes())
    source_status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                                   check=True, capture_output=True, text=True).stdout.splitlines()
    source_commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   check=True, capture_output=True, text=True).stdout.strip()
    capture.update({
        "schema": "csl.issue824.matched-minimax-capture/2",
        "source_commit": source_commit,
        "source_tree_clean_before_report_generation": not source_status,
        "source_status_before_report_generation": source_status,
        "source_files_sha256": source_files,
        "limiter_profile_build": previous_capture["limiter_profile_build"],
        "limiter_profile_source_bundle": "issue824-two-points-matched-minimax-v1",
        "resource_accounting": {
            "policy": resource["profile"],
            "requested_limits": resource["requested_limits"],
            "enforced_limits": resource["enforced_limits"],
            "observed": {
                "process_tree_wall_time_ns": resource["elapsed_wall_time_ns"],
                "process_tree_peak_memory_bytes": resource["observed"]["process_tree_peak_memory_bytes"],
                "memory_events": resource["observed"]["memory_events"],
                "timed_out": resource["observed"]["timed_out"],
                "exit_code": resource["observed"]["exit_code"],
            },
            "scope": resource["measurement_scope"],
        },
    })
    files["capture.json"] = (json.dumps(capture, indent=2, sort_keys=True) + "\n").encode()
    files["resource-profile.json"] = resource_bytes

    readme = files["README.md"].decode("utf-8")
    old_paragraph = (
        "The differences describe this one small fixture only. The methods do not use the same candidate-score representation, so these numbers do not establish a general performance winner. "
        "The run was uncapped: no process-tree wall or memory limit was requested or enforced, and process-tree peak memory was not observed. "
        "The zonotope limiter profile is separate from the reported timing build and identifies `score_corners` as the main sampled CPU path for this workload. "
        "Profiling used GNU gprof 2.47, Release `-O3 -DNDEBUG -pg`, ten calls, and 10 ms sampling. See `limiter-profile.json`."
    )
    new_paragraph = (
        "The differences describe this one small fixture only. The methods do not use the same candidate-score representation, so these numbers do not establish a general performance winner. "
        "The complete capture ran in one supervised process tree under a 300-second wall limit and an 8 GiB cgroup-v2 memory limit, with one concurrent job. "
        f"The report-generation command completed in {resource['elapsed_wall_time_ns'] / 1e9:.3f} s and the cgroup recorded a peak of {resource['observed']['process_tree_peak_memory_bytes'] / 1024**2:.1f} MiB, with no timeout or OOM events. "
        "These shared limits cover all repeated calls and checking in the report capture, so the total run must fit inside each per-attempt cap; the cap is not reset between calls. "
        "The separate zonotope limiter profile is reused from the immutable v1 bundle: it identifies `score_corners` as the main sampled CPU path. "
        "That profile used GNU gprof 2.47, Release `-O3 -DNDEBUG -pg`, ten calls, and 10 ms sampling. See `limiter-profile.json` and `resource-profile.json`."
    )
    if old_paragraph not in readme:
        raise ValueError("uncapped paragraph not found in raw README")
    readme = readme.replace(old_paragraph, new_paragraph)
    readme = readme.replace("# Matched TwoPoints fixed-plan minimax run", "# Resource-limited matched TwoPoints fixed-plan minimax run")
    readme = readme.replace("reports/algorithm-results/{BUNDLE}", f"reports/algorithm-results/{RESOURCE_BUNDLE}")
    readme = readme.replace("See `limiter-profile.json`.", "See `limiter-profile.json` and `resource-profile.json`.")
    files["README.md"] = readme.encode()

    page = files["index.html"].decode("utf-8")
    old_html = (
        "This local run was uncapped: no process-tree wall-time or memory limit was requested or enforced, and process-tree peak memory was not observed. "
        "The methods use different candidate scoring rules: approximate enclosure corner/support scores are numerical ranking estimates, not certified objective bounds."
    )
    new_html = (
        "This capture ran under a shared 300-second process-tree wall cap and 8 GiB cgroup-v2 memory cap. "
        f"The full report command took {resource['elapsed_wall_time_ns'] / 1e9:.3f} s and peaked at {resource['observed']['process_tree_peak_memory_bytes'] / 1024**2:.1f} MiB, with no timeout or OOM event. "
        "The cap covered all repeated calls and checking as one job. The separate zonotope limiter profile is reused from the immutable v1 bundle. "
        "The methods use different candidate scoring rules: approximate enclosure corner/support scores are numerical ranking estimates, not certified objective bounds."
    )
    if old_html not in page:
        raise ValueError("uncapped paragraph not found in raw HTML")
    page = page.replace(old_html, new_html)
    page = page.replace("Issue 824 · Matched fixed-plan minimax", "Issue 824 · Resource-limited matched fixed-plan minimax")
    files["index.html"] = page.encode()

    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (args.output / name).write_bytes(content)
    lines = [f"{digest(content)}  {name}" for name, content in sorted(files.items())]
    (args.output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    print(f"wrote {len(files) + 1} files to {args.output.resolve()}")


if __name__ == "__main__":
    main()

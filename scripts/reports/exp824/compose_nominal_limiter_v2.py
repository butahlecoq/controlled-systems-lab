#!/usr/bin/env python3
"""Add separately collected limiter and report-path evidence to nominal v1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--e2e", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, e2e_path, profile_dir, output = map(lambda p: p.resolve(strict=True),
        (args.source, args.e2e, args.profile, args.output.parent))
    output = output / args.output.name
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    original_sums = {}
    for line in (source / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        checksum, name = line.split("  ", 1)
        original_sums[name] = checksum
    if original_sums != {p.name: digest(p) for p in source.iterdir()
                          if p.is_file() and p.name != "SHA256SUMS"}:
        raise SystemExit("source report SHA256SUMS verification failed")

    e2e = json.loads(e2e_path.read_text(encoding="utf-8"))
    runs = e2e.get("runs", [])
    if (e2e.get("schema") != "csl.issue824-nominal-report-e2e/1" or len(runs) != 5
            or not e2e["summary"]["all_checks_passed"]
            or not e2e["summary"]["all_score_checksums_match"]
            or any(run["calls"] != 70 or run["failures"] != 0
                   or run["checker_status"] != "passed" for run in runs)):
        raise SystemExit("end-to-end evidence is incomplete or failed")
    profile_runs = [profile_dir / f"gprof-run-{i}.json" for i in range(1, 6)]
    if any(not path.is_file() for path in profile_runs):
        raise SystemExit("five profiler-run records are required")
    profiles = [json.loads(path.read_text(encoding="utf-8")) for path in profile_runs]
    if any(item["completed_calls"] != 70 or item["failures"] != 0 for item in profiles):
        raise SystemExit("a profiler run did not complete the full 70 calls")
    flat = profile_dir / "gprof-flat.txt"
    if not flat.is_file():
        raise SystemExit("merged gprof flat profile is missing")
    text = flat.read_text(encoding="utf-8")
    entries = []
    for line in text.splitlines():
        match = re.match(r"\s*(\d+\.\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(.+)$", line)
        if match:
            entries.append({"self_percent": float(match[1]), "cumulative_seconds": float(match[2]),
                            "self_seconds": float(match[3]), "calls": int(match[4]),
                            "seconds_per_call_self": float(match[5]),
                            "seconds_per_call_total": float(match[6]), "function": match[7].strip()})
        if len(entries) == 3:
            break
    if len(entries) != 3:
        raise SystemExit("could not parse top three gprof rows")
    raw_archive = output.parent / "issue824-nominal-v2-limiter-raw.tar.gz"
    with tarfile.open(raw_archive, "w:gz") as archive:
        for path in sorted(profile_dir.glob("gmon-*.out")):
            archive.add(path, arcname=path.name)
        for path in profile_runs:
            archive.add(path, arcname=path.name)
        archive.add(profile_dir / "gprof-profile.txt", arcname="gprof-profile.txt")
        archive.add(flat, arcname="gprof-flat.txt")

    output.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file() and path.name != "SHA256SUMS":
            shutil.copyfile(path, output / path.name)
    result_path = output / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["schema"] = "csl.issue824-two-points-nominal-bundle/2"
    result["measurement"]["limiter_profile"] = {
        "performed": True,
        "profiler": "GNU gprof 2.47; 0.01 s sampling interval",
        "profile_runs": 5,
        "measured_calls_per_run": 70,
        "warmup_calls_per_run": 1,
        "total_profiled_calls": 350,
        "failures": 0,
        "build_flags": "Release -O3 -DNDEBUG -pg -fno-omit-frame-pointer",
        "linker_flags": "-pg",
        "timings_used_as_performance_evidence": False,
        "scope": "combined five-track nominal API call on one three-stage fixture",
        "top_self_cpu_samples": entries,
        "raw_artifact": "limiter-profile-raw.tar.gz",
        "interpretation": "Zonotope corner scoring is the largest sampled CPU path in this combined call; this is not per-representation timing or a winner comparison.",
    }
    summary = e2e["summary"]
    result["measurement"]["end_to_end_report_generation"] = {
        "schema": e2e["schema"], "scope": e2e["scope"], "run_count": summary["run_count"],
        "median_wall_ns": summary["median_wall_ns"], "wall_range_ns": summary["wall_range_ns"],
        "median_api_timed_region_ns": summary["median_api_timed_region_ns"],
        "median_api_share": summary["median_api_share"], "all_checks_passed": summary["all_checks_passed"],
        "all_score_checksums_match": summary["all_score_checksums_match"], "runs": runs,
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "e2e-timing.json").write_bytes(e2e_path.read_bytes())
    profile = {"schema": "csl.issue824-nominal-limiter-profile/1", "profiler": "GNU gprof 2.47",
        "sampling_interval_seconds": 0.01, "profile_runs": 5, "measured_calls_per_run": 70,
        "warmup_calls_per_run": 1, "failures": 0, "build_flags": result["measurement"]["limiter_profile"]["build_flags"],
        "merged_top_self_cpu_samples": entries,
        "caveats": ["Profiler timings are excluded from wall-time summaries.",
                    "Sampling resolution is 10 ms.",
                    "One three-stage fixture and a combined API call do not support per-representation rankings."]}
    (output / "limiter-profile.json").write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copyfile(flat, output / "limiter-profile.txt")
    shutil.copyfile(raw_archive, output / "limiter-profile-raw.tar.gz")
    raw_archive.unlink()
    capture_path = output / "capture.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["source_commit"] = "62f65dcbe2a56a209f997ca54f6ad26167c91043"
    # Use Git's blob content through Python for the same files tracked by the run commit.
    root = Path(__file__).resolve().parents[3]
    source_names = json.loads((source / "capture.json").read_text(encoding="utf-8"))["source_files_sha256"]
    capture["source_files_sha256"] = {
        name: hashlib.sha256(subprocess.run(["git", "-C", str(root), "show",
                                            f"{capture['source_commit']}:{name}"], check=True,
                                           capture_output=True).stdout).hexdigest()
        for name in source_names
    }
    capture["profiler"] = profile
    capture["end_to_end_capture"] = {"host": e2e["host"], "trials": len(runs),
        "load_averages_before_after_each_trial": [
            {"before": run["load_average_before"], "after": run["load_average_after"]} for run in runs]}
    capture_path.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    page = (output / "index.html").read_text(encoding="utf-8")
    old = "No limiter profile or comparative performance claim is made."
    new = (f"Five serial report-generation trials (including the independent checker and checksum check) took a median "
           f"{summary['median_wall_ns'] / 1e9:.3f} s (range {summary['wall_range_ns'][0] / 1e9:.3f}–"
           f"{summary['wall_range_ns'][1] / 1e9:.3f} s); the timed API region was a median "
           f"{summary['median_api_share'] * 100:.1f}% of that path. A separate gprof profile attributes "
           f"{entries[0]['self_percent']:.2f}% of self CPU samples to zonotope corner scoring, "
           f"{entries[1]['self_percent']:.2f}% to matrix access, and {entries[2]['self_percent']:.2f}% to objective evaluation. "
           "The profiler run is excluded from timing. This is one combined-call fixture, with no per-representation "
           "ranking, speedup, or winner claim. Raw captures: <a href=\"e2e-timing.json\">five end-to-end trials</a>, "
           "<a href=\"limiter-profile.json\">profile summary</a>, <a href=\"limiter-profile.txt\">flat profile</a>, "
           "<a href=\"limiter-profile-raw.tar.gz\">raw gprof data</a>.")
    if old not in page:
        raise SystemExit("could not find v1 limitation paragraph to replace")
    (output / "index.html").write_text(page.replace(old, new), encoding="utf-8")
    readme = (output / "README.md").read_text(encoding="utf-8")
    readme = readme.replace(
        "The report makes no speedup, scalability or bottleneck claim; no separate limiter profile was performed.",
        "The immutable v1 capture made no speedup, scalability or bottleneck claim. This v2 bundle adds separate report-path timing and a limiter profile, described below.")
    readme += f'''\n## Limiter and report-path evidence (v2)\n\nFive serial end-to-end report generations, each followed by the independent exact checker and manifest verification, took median `{summary['median_wall_ns'] / 1e9:.3f} s` (range `{summary['wall_range_ns'][0] / 1e9:.3f}–{summary['wall_range_ns'][1] / 1e9:.3f} s`). The API timed region represented median `{summary['median_api_share'] * 100:.1f}%`. Across these five trials, 350 measured calls completed with zero failures and identical score checksums. Raw trial data is in `e2e-timing.json`.\n\nA separate Release `-pg` gprof run profiled five runs of 70 calls plus one warmup each. The top sampled self-CPU rows were zonotope corner scoring ({entries[0]['self_percent']:.2f}%), matrix access ({entries[1]['self_percent']:.2f}%), and objective evaluation ({entries[2]['self_percent']:.2f}%). The profiler data is not used for timing. Ten-millisecond sampling and one combined five-track, three-stage fixture limit this inference; there is no per-representation timing, winner, or speedup claim. See `limiter-profile.json`, `limiter-profile.txt`, and `limiter-profile-raw.tar.gz`.\n'''
    readme += '''\nTo recompose this v2 record from the saved evidence, first generate the baseline v1 capture using the command above, extract `limiter-profile-raw.tar.gz` into a temporary directory, and run:\n\n```sh\npython3 scripts/reports/exp824/compose_nominal_limiter_v2.py \\\n  --source reports/algorithm-results/issue824-two-points-nominal-v1 \\\n  --e2e reports/algorithm-results/issue824-two-points-nominal-v2/e2e-timing.json \\\n  --profile /tmp/issue824-gprof \\\n  --output reports/algorithm-results/issue824-two-points-nominal-v2-rebuilt\n```\n\nThe extracted profile directory must contain the five `gprof-run-*.json` files, `gprof-flat.txt`, `gprof-profile.txt`, and five `gmon-*.out` files.\n'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    sums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in sums.items()), encoding="ascii")


if __name__ == "__main__":
    main()

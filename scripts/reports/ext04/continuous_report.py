#!/usr/bin/env python3
"""Render the saved EXT-04 continuous-policy measurement into an offline bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import statistics
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(trials_path: Path, build_log_path: Path, example_path: Path,
           out: Path, source_commit: str, collected_utc: str,
           load_observation: str, driver_path: Path | None = None) -> None:
    raw = trials_path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    expected_result = [
        {"initial": [0, 0], "action": [0], "terminal": [0, 0], "action_margin": 1.25},
        {"initial": [0, 1], "action": [0], "terminal": [1, 1], "action_margin": 1.25},
        {"initial": [1, 0], "action": [1], "terminal": [1.5, 1], "action_margin": 0.25},
        {"initial": [1, 1], "action": [1], "terminal": [2.5, 2], "action_margin": 0.25},
    ]
    if len(rows) != 8 or rows[0]["warmup"] is not True or any(
            row.get("schema") != "csl.ext04-continuous-policy-trial/1" or
            row.get("status") != "passed" or row.get("assurance") != "numerical" or
            row.get("feasibility") != "within_tolerance" or
            row.get("batch") != 5000 or row.get("generators_per_call") != 4 or
            row.get("feasibility_tolerance") != 1e-9 or
            row.get("fixture_reused") is not True or row.get("outer_workers") != 1 or
            row.get("result") != expected_result or
            row.get("warmup") != (index == 0) or row.get("round") != index
            for index, row in enumerate(rows)):
        raise ValueError("saved trial identity or outcome differs")
    measured = [row["elapsed_ns"] for row in rows[1:]]
    if any(value < 20_000_000 for value in measured):
        raise ValueError("measured batch shorter than 20 ms")
    out.mkdir(parents=True, exist_ok=False)
    (out / "trials.jsonl").write_bytes(raw)
    (out / "example-2d.svg").write_bytes(example_path.read_bytes())
    driver = (driver_path or Path("benchmarks/reporting/ext04/continuous_policy_driver.cpp")).read_bytes()
    renderer = Path(__file__).read_bytes()
    (out / "driver.cpp").write_bytes(driver)
    (out / "renderer.py").write_bytes(renderer)
    build = build_log_path.read_text(encoding="utf-8", errors="replace")
    build = build.replace(str(Path.cwd()), "$SOURCE_ROOT")
    build = build.replace(str(Path.home()), "$HOME")
    build_bytes = build.encode("utf-8")
    (out / "release-build-log.txt").write_bytes(build_bytes)
    summary = {
        "schema": "csl.ext04-continuous-policy-report/1",
        "report_id": "ext04-continuous-" + source_commit[:16],
        "source_commit": source_commit,
        "source_tree_clean_after_commit": True,
        "collected_utc": collected_utc,
        "algorithm": "evaluate_continuous_policy",
        "assurance": "numerical binary64",
        "fixture": {
            "system": "x[k+1]=[[1,1],[0,1]]x[k]+[[0.5],[1]]u[k]",
            "observation": "y[k]=[1,0]x[k], available before decision 0",
            "joint_initial_generators": [[0, 0], [0, 1], [1, 0], [1, 1]],
            "policy": "estimate=[y,0]; action=estimate[0]",
            "safety": "u<=1.25",
            "expected_states": [[[0, 0], [0, 0]], [[0, 1], [1, 1]],
                                [[1, 0], [1.5, 1]], [[1, 1], [2.5, 2]]],
            "expected_actions": [[0], [0], [1], [1]],
            "expected_margins": [1.25, 1.25, 0.25, 0.25],
        },
        "input_sha256": digest(json.dumps({
            "system": "x[k+1]=[[1,1],[0,1]]x[k]+[[0.5],[1]]u[k]",
            "generators": [[0, 0], [0, 1], [1, 0], [1, 1]],
            "policy": "estimate=[y,0]; action=estimate[0]", "safety": "u<=1.25"
        }, sort_keys=True, separators=(",", ":")).encode()),
        "timing_scope": rows[0]["timing_scope"],
        "harness_sha256": digest(driver),
        "renderer_sha256": digest(renderer),
        "release_build_log_sha256": digest(build_bytes),
        "batch_size": 5000,
        "warmup_policy": "one excluded 5,000-call batch followed by seven sequential measured batches; same process and fixture reused",
        "seed": "not applicable; fixture and policy are deterministic",
        "feasibility_tolerance": 1e-9,
        "workers": {"outer_requested": 1, "outer_observed": 1,
                    "native_requested": "not applicable; no parallel backend in this evaluator",
                    "native_observed": "not applicable; no parallel backend in this evaluator"},
        "workspace_reuse": "same immutable system/domain/policy fixture reused across calls; evaluator has no cross-call workspace",
        "load_observation_before_build_and_measurement": load_observation,
        "warmups_excluded": 1,
        "measured_batches": len(measured),
        "successes": len(measured),
        "failures": 0,
        "median_batch_ns": statistics.median(measured),
        "min_batch_ns": min(measured),
        "max_batch_ns": max(measured),
        "median_ns_per_call": statistics.median(measured) / 5000,
        "environment": {
            "os": "Linux x86_64 (Omarchy; kernel 7.2.5)",
            "cpu": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx",
            "logical_processors": 8,
            "compiler": "GCC 16.2.1",
            "cmake": "3.31.6",
            "configuration": "Release, -O3, C++20",
            "native_threads": "no parallel backend used by this operation",
            "limiter": "not controlled; single process, no separate limiter profile",
        },
        "evidence_limits": [
            "One analytic two-state, one-step fixture with four supplied joint generators.",
            "Does not search for a policy or prove a universal initial/disturbance relation.",
            "Numerical binary64 checks; no validated rounding enclosure.",
            "Single adapter only; no comparator, speedup, scalability or application-load claim.",
            "Timings cover repeated public evaluator calls and per-generator literal checks; fixture setup and serialization are excluded.",
        ],
        "performance_conclusion": "Inconclusive for comparisons: one adapter, no comparator or source-mapped limiter profile.",
        "artifacts": {
            "driver": "benchmarks/reporting/ext04/continuous_policy_driver.cpp",
            "driver_sha256": digest(driver),
            "command": "cmake -S . -B build/ext04-continuous-report -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXT04_CONTINUOUS_REPORT=ON -DBUILD_TESTING=OFF; cmake --build build/ext04-continuous-report --config Release --target csl_ext04_continuous_policy_report --parallel 4; csl_ext04_continuous_policy_report measure",
        },
    }
    (out / "records.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["round", "batch_calls", "elapsed_ns", "ns_per_call", "status"])
        for row in rows[1:]:
            writer.writerow([row["round"], row["batch"], row["elapsed_ns"],
                             row["elapsed_ns"] / row["batch"], row["status"]])
    table = "".join(
        f'<tr><td>{r["round"]}</td><td>{r["elapsed_ns"] / 1e6:.3f}</td>'
        f'<td>{r["elapsed_ns"] / r["batch"]:.1f}</td><td>passed</td></tr>'
        for r in rows[1:])
    report_id = summary["report_id"]
    safe_load_observation = html.escape(load_observation)
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXT-04 continuous policy evaluation</title>
<style>body{{font:16px system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#17242d}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #b7c6ce;padding:.5rem;text-align:left}}th{{background:#e9f0f4}}img{{max-width:100%}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>EXT-04 continuous affine policy evaluation</h1>
<p class="limits"><strong>Verdict: inconclusive for comparisons.</strong> This is descriptive evidence from one adapter. No comparator or source-mapped limiter profile was measured.</p>
<p>This report measures the public continuous evaluator on one fixed, analytic, one-step fixture. The joint set has four supplied initial-state generators. The policy reads the first observation component and applies it as the scalar action. The action constraint is <code>u ≤ 1.25</code>. Every call returned numerical evidence with feasibility <code>within_tolerance</code>; literal state, action, and margin checks passed for all four generators.</p>
<figure><img src="example-2d.svg" alt="Two-dimensional control and terminal state example"><figcaption>Standalone visual for the supported two-dimensional case.</figcaption></figure>
<h2>Measurements</h2><p>One excluded warmup followed by seven 5,000-call batches. Median: {summary["median_batch_ns"] / 1e6:.3f} ms per batch ({summary["median_ns_per_call"]:.1f} ns/call); range {summary["min_batch_ns"] / 1e6:.3f}–{summary["max_batch_ns"] / 1e6:.3f} ms. The measured interval includes public evaluator calls and literal checks; it excludes fixture setup, process startup, JSONL serialization, and rendering.</p>
<table><thead><tr><th>Round</th><th>Batch ms</th><th>ns/call</th><th>Outcome</th></tr></thead><tbody>{table}</tbody></table>
<h2>Environment</h2><p>Linux x86_64, AMD Ryzen 5 3550H, GCC 16.2.1, CMake 3.31.6, Release, C++20. Host-load observation before collection: {safe_load_observation}. This is a host snapshot rather than a controlled limiter profile; CPU frequency was not controlled.</p>
<h2>Scope and limits</h2><p>This is descriptive single-adapter evidence for one small fixture. It establishes no speedup, scalability, application-load performance, validated rounding enclosure, policy synthesis, or universal initial-state and disturbance guarantee. All-joint mode checks the supplied generators under numerical binary64 arithmetic.</p>
<h2>Reproduce</h2><pre>cmake -S . -B build/ext04-continuous-report -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXT04_CONTINUOUS_REPORT=ON -DBUILD_TESTING=OFF
cmake --build build/ext04-continuous-report --config Release --target csl_ext04_continuous_policy_report --parallel 4
build/ext04-continuous-report/csl_ext04_continuous_policy_report measure</pre>
<p>Measured source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{html.escape(source_commit)}"><code>{html.escape(source_commit)}</code></a>. Report ID <code>{report_id}</code>. The report bundle contains the exact driver and renderer source, raw JSONL rows, saved records, summary CSV, visual, and Release build log. <a href="driver.cpp">Driver source</a> · <a href="renderer.py">Saved-data renderer</a> · <a href="records.json">Saved records</a> · <a href="trials.jsonl">Raw rows</a> · <a href="summary.csv">CSV</a> · <a href="{report_id}.zip">Offline bundle</a>.</p>
</body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    files = sorted(path for path in out.iterdir() if path.is_file())
    manifest = {path.name: digest(path.read_bytes()) for path in files}
    (out / "manifest.json").write_text(json.dumps({
        "schema": "csl.ext04-continuous-manifest/1", "report_id": report_id,
        "source_commit": source_commit, "files": manifest}, indent=2, sort_keys=True) + "\n")
    with zipfile.ZipFile(out / f"{report_id}.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(out.iterdir()):
            if path.name != f"{report_id}.zip":
                info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--collected-utc", required=True)
    parser.add_argument("--load-observation", required=True)
    parser.add_argument("--driver", type=Path)
    args = parser.parse_args()
    render(args.trials, args.build_log, args.example, args.out,
           args.source_commit, args.collected_utc, args.load_observation,
           args.driver)

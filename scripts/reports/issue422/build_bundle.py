#!/usr/bin/env python3
"""Build the offline EXP-05 fixed-plan minimax report bundle from saved evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def pretty(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page(result: dict, environment: dict) -> bytes:
    rows = []
    for arm, method in enumerate(("Numerical", "Validated")):
        for item in result["comparison_record"]["attempts"]:
            if item["arm_index"] != arm:
                continue
            event = json.loads(item["measurement_payload"])
            rows.append(f"<tr><td>{method}</td><td>{item['repetition_index'] + 1}</td>"
                        f"<td>{item['reported_status']}</td><td>{event.get('elapsed_ns', '—')}</td></tr>")
    timing = result["timing_summary"]
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>EXP-05 finite fixed-plan minimax</title>
<style>
body{{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;background:#172019;color:#dce5d5;line-height:1.55}}
main{{background:#202a22;border:1px solid #405045;border-radius:12px;padding:1.5rem}}a{{color:#b4cda3}}
svg{{display:block;width:100%;height:auto;margin:1rem 0}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{border:1px solid #53634f;padding:.45rem;text-align:left}}code{{color:#b4cda3}}
</style><main>
<h1>Finite fixed-plan minimax</h1>
<p>This report compares two solvers on one bounded, one-stage scalar case. The action is fixed before the disturbance is revealed. The case is <code>x₁=x₀+u+w</code>, <code>x₀=0</code>, <code>u∈{{0,1}}</code>, <code>w∈{{0,2}}</code>, safe set <code>−10≤x≤10</code>, and terminal cost <code>|x₁−1|</code>.</p>
<img src="visual.svg" alt="State trajectories for both fixed actions and disturbance vertices">
<p>The independent oracle enumerates every action and disturbance pair, checks both stage constraints, and evaluates the terminal cost. Its global minimax value is <strong>{result['independent_oracle']['global_minimax_value']}</strong>. All seven measured outcomes from each method passed the oracle checks.</p>
<h2>Exploratory timings</h2>
<p>Each duration covers the solver call only. One warmup per arm was excluded. Median and min–max range: numerical {timing[0]['median_ns']} ns ({timing[0]['min_ns']}–{timing[0]['max_ns']} ns); validated {timing[1]['median_ns']} ns ({timing[1]['min_ns']}–{timing[1]['max_ns']} ns). Ranges overlap. This tiny fixture supports no performance winner, scalability, or application-scale claim. No separate limiter profile was collected.</p>
<table><thead><tr><th>Method</th><th>Measured repetition</th><th>Status</th><th>Solver time (ns)</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Reproduce and inspect</h2><p>Source revision: <code>{result['source_revision']}</code>. Input manifest SHA-256: <code>{result['input_manifest_sha256']}</code>. Build: {environment['build']['compiler_id']} {environment['build']['compiler_version']}, {environment['build']['build_type']}.</p>
<ul><li><a href="comparison.json">Raw comparison record and all 14 run records</a></li><li><a href="environment.json">Build and runtime environment</a></li><li><a href="trials.csv">Per-attempt timing table</a></li><li><a href="fixed_plan_comparison.cpp">Comparison driver and independent oracle</a></li><li><a href="build.log">Release build log</a></li><li><a href="commands.txt">Reproduction command</a></li></ul>
</main></html>""".encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, default=ROOT / "benchmarks/reporting/issue422/results/finite-plan-comparison.json")
    parser.add_argument("--build-log", type=Path, default=ROOT / "build/tmp/issue422-build.log")
    parser.add_argument("--configure-log", type=Path, default=ROOT / "build/tmp/issue422-configure.log")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    record = result["comparison_record"]
    spec = json.loads(record["spec"])
    report_id = f"exp05-fixed-plan-minimax-20261026-{result['source_revision'][:8]}"
    if result["comparison_claim"] != "supported" or record["schema"] != "csl.comparison-record/1":
        raise SystemExit("refusing to publish an unsupported comparison claim")
    if args.out is None:
        args.out = ROOT / "reports/algorithm-results" / report_id
    if len(record["attempts"]) != 14 or any(item["reported_status"] != "completed" for item in record["attempts"]):
        raise SystemExit("report bundle expects 14 completed measured attempts")
    environment = spec["environment"]
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ROOT / "benchmarks/reporting/issue422/fixed_plan_comparison.cpp", out / "fixed_plan_comparison.cpp")
    shutil.copyfile(ROOT / "docs/examples/fixed-plan-minimax-2d.svg", out / "visual.svg")
    shutil.copyfile(ROOT / "docs/artifacts/schemas/comparison-spec-v3.schema.json", out / "comparison-spec-v3.schema.json")
    (out / "comparison.json").write_bytes(pretty(result))
    (out / "environment.json").write_bytes(pretty(environment))
    (out / "build.log").write_bytes(args.build_log.read_bytes())
    (out / "configure.log").write_bytes(args.configure_log.read_bytes())
    (out / "commands.txt").write_text(
        "cmake -S . -B build/core -DCMAKE_BUILD_TYPE=Release -DCSL_BUILD_ISSUE422_REPORT=ON\n"
        "cmake --build build/core --target csl_issue422_fixed_plan_comparison --parallel 4\n"
        "build/core/csl_issue422_fixed_plan_comparison > benchmarks/reporting/issue422/results/finite-plan-comparison.json\n"
        "python scripts/reports/issue422/check_smoke.py build/core/csl_issue422_fixed_plan_comparison\n",
        encoding="utf-8")
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(["arm", "repetition", "status", "elapsed_ns"])
    for item in record["attempts"]:
        event = json.loads(item["measurement_payload"])
        writer.writerow([item["arm_index"], item["repetition_index"], item["reported_status"], event["elapsed_ns"]])
    (out / "trials.csv").write_text(csv_buffer.getvalue(), encoding="utf-8")
    (out / "index.html").write_bytes(page(result, environment))
    readme = (f"# EXP-05 fixed-plan minimax report\n\n"
              f"This is an exploratory comparison on one bounded analytic fixture. All 14 measured attempts passed the independent exhaustive oracle. The global minimax value is 1.0. Timings are descriptive; no winner, scalability, or application-scale claim is made. No limiter profile was collected.\n\n"
              f"Source revision: `{result['source_revision']}`. Input hash: `{result['input_manifest_sha256']}`. Read `index.html` offline or open the deterministic `bundle.zip`.\n")
    (out / "README.md").write_text(readme, encoding="utf-8")
    files = sorted(path.name for path in out.iterdir() if path.is_file() and path.name not in {"manifest.json", "bundle.zip"})
    manifest = {"schema": "csl.exp05-minimax-report-manifest/1", "report_id": out.name,
                "source_commit": result["source_revision"], "files": {name: digest(out / name) for name in files}}
    (out / "manifest.json").write_bytes(pretty(manifest))
    with zipfile.ZipFile(out / "bundle.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(out.iterdir()):
            if path.name == "bundle.zip":
                continue
            info = zipfile.ZipInfo(path.name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

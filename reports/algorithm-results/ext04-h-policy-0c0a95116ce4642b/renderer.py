#!/usr/bin/env python3
"""Render and seal saved EXT-04 joint H-domain policy measurements."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import sys
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def helper_directory() -> Path:
    for candidate in (Path(__file__).parent, Path(__file__).parents[1]):
        if (candidate / "figure_style.py").is_file():
            return candidate
    raise ValueError("the saved quantitative figure policy is missing")


def make_figure(out: Path, helper_dir: Path) -> tuple[bytes, bytes]:
    sys.path.insert(0, str(helper_dir))
    os.environ.setdefault("MPLCONFIGDIR", str(out.parent / "mpl-config"))
    import matplotlib
    if matplotlib.__version__ != "3.11.2":
        raise ValueError("the report figure requires pinned Matplotlib 3.11.2")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import figure_style
    import plot as report_plot

    with matplotlib.rc_context({"font.family":"DejaVu Sans", "font.size":10,
            "svg.hashsalt":"csl-report-style-v1", "svg.fonttype":"path"}):
        figure, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
        try:
            x = [-1.0, 1.0]
            error = [-0.1, 0.1]
            terminal = [0.1, -0.1]
            axes[0].plot(x, error, color="#147d75", linewidth=2.8,
                         marker="o", markersize=6)
            axes[0].set(xlim=(-1.15,1.15), ylim=(-0.12,0.12),
                xlabel="Initial state x₀", ylabel="Measurement error e",
                title="Joint H-domain: e = 0.1x₀")
            axes[1].plot(x, terminal, color="#d77a1f", linewidth=2.8,
                         marker="o", markersize=6)
            axes[1].set(xlim=(-1.15,1.15), ylim=(-0.12,0.12),
                xlabel="Initial state x₀", ylabel="Terminal state x₁",
                title="Policy image: x₁ = −e")
            for axis in axes:
                figure_style.configure_numeric_axis(axis, "both", bins=5)
            figure.suptitle("Correlated uncertainty and its reachable-state projection")
            svg = io.StringIO()
            figure.savefig(svg, format="svg",
                metadata={"Date":None,"Format":None,"Type":None,"Creator":None})
            png = io.BytesIO()
            figure.savefig(png, format="png", dpi=180,
                metadata={"Software":"CSL report style csl-report-quantitative-v1"})
            return report_plot.normalize_owned_svg(svg.getvalue()), png.getvalue()
        finally:
            plt.close(figure)


def render(trials_path: Path, build_log_path: Path, environment_path: Path,
           out: Path, source_commit: str, collected_utc: str,
           driver_path: Path) -> None:
    raw = trials_path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    if len(rows) != 8:
        raise ValueError("expected one warmup and seven measured batches")
    expected = [1.0, 1.0, 0.1, 0.1, 1.1, 1.1]
    for index, row in enumerate(rows):
        actual = [item["support_upper_bound"] for item in row["result"]["constraints"]]
        if (row.get("schema") != "csl.ext04-h-policy-trial/1" or
                row.get("round") != index or row.get("warmup") != (index == 0) or
                row.get("batch") != 100 or row.get("status") != "passed" or
                row.get("assurance") != "numerical" or
                row.get("feasibility") != "within_tolerance" or
                row.get("safety_rows") != 6 or row.get("lp_solves_per_call") != 7 or
                row.get("workspace_reused") is not True or
                len(actual) != len(expected) or
                any(abs(value - target) > 1e-7 for value, target in zip(actual, expected))):
            raise ValueError(f"trial {index} has an unexpected identity or result")
        witness = row["result"]["domain_witness"]
        if abs(witness[1] - 0.1 * witness[0]) > 1e-8:
            raise ValueError(f"trial {index} lost the authored H-domain correlation")
    measured = [row["elapsed_ns"] for row in rows[1:]]
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    driver = driver_path.read_bytes()
    renderer = Path(__file__).read_bytes()
    helper_dir = helper_directory()
    helper_sources = {name: (helper_dir / name).read_bytes()
                      for name in ("figure_style.py", "plot.py", "report_data.py")}
    build = build_log_path.read_text(encoding="utf-8", errors="replace")
    build = build.replace(str(Path.cwd()), "$SOURCE_ROOT")
    build = build.replace(str(Path.home()), "$HOME")
    build_bytes = build.encode("utf-8")
    if not build_bytes.strip():
        raise ValueError("release build log is empty")

    report_id = "ext04-h-policy-" + source_commit[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out / "trials.jsonl").write_bytes(raw)
    (out / "driver.cpp").write_bytes(driver)
    (out / "renderer.py").write_bytes(renderer)
    for name, source in helper_sources.items():
        (out / name).write_bytes(source)
    (out / "release-build-log.txt").write_bytes(build_bytes)
    (out / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    svg, png = make_figure(out, helper_dir)
    (out / "h-domain-2d.svg").write_bytes(svg)
    (out / "h-domain-2d.png").write_bytes(png)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["round", "batch_calls", "lp_solves_per_call", "elapsed_ns", "ns_per_call", "status"])
        for row in rows[1:]:
            writer.writerow([row["round"], row["batch"], row["lp_solves_per_call"],
                             row["elapsed_ns"], row["elapsed_ns"] / row["batch"], row["status"]])

    summary = {
        "schema": "csl.ext04-h-policy-report/1", "report_id": report_id,
        "source_commit": source_commit, "collected_utc": collected_utc,
        "algorithm": "evaluate_h_continuous_policy", "backend": "HiGHS LP adapter 1.11.0",
        "assurance": "numerical binary64",
        "fixture": {
            "dynamics": "x1=x0+u0", "observation": "y=x0+e, available before decision",
            "joint_h_domain": "-1<=x0<=1; -0.1<=e<=0.1; e=0.1*x0",
            "policy": "u0=-y", "terminal_state": "x1=-e=-0.1*x0",
            "safety_rows": [
                {"family":"state","stage":0,"max_activity":1.0,"upper_bound":1.2},
                {"family":"state","stage":0,"max_activity":1.0,"upper_bound":1.2},
                {"family":"state","stage":1,"max_activity":0.1,"upper_bound":0.2},
                {"family":"state","stage":1,"max_activity":0.1,"upper_bound":0.2},
                {"family":"action","stage":0,"max_activity":1.1,"upper_bound":1.2},
                {"family":"action","stage":0,"max_activity":1.1,"upper_bound":1.2}]},
        "input_sha256": digest(b"x1=x0+u0;y=x0+e;e=0.1*x0;u0=-y"),
        "batch_size": 100, "warmups_excluded": 1, "measured_batches": len(measured),
        "successes": len(measured), "failures": 0,
        "median_batch_ns": statistics.median(measured), "min_batch_ns": min(measured),
        "max_batch_ns": max(measured), "median_ns_per_call": statistics.median(measured)/100,
        "workspace_reuse": "one HiGHS LP workspace reused sequentially within each process; each evaluator call solves one domain LP and six support dual LPs",
        "figure": {"style":"csl-report-quantitative-v1", "matplotlib":"3.11.2",
            "timing_included":False, "axis_policy":"positioned numeric ticks, labels and major grids"},
        "timing_scope": rows[0]["timing_scope"], "environment": environment,
        "performance_conclusion": "Descriptive single-adapter timing only; no comparator, source-mapped limiter profile, speedup, or scalability claim.",
        "evidence_limits": [
            "One analytic scalar one-step fixture with a one-dimensional correlated H-polytope.",
            "The H-set is caller-authored; the report does not prove it encloses a physical disturbance model.",
            "Floating-point feasibility and dual multipliers are numerical evidence, not validated arithmetic.",
            "No policy synthesis, existential-initial-state claim, or universal disturbance claim is made.",
            "One HiGHS backend and one machine; no comparative or application-scale performance claim."],
        "artifacts": {"driver":"benchmarks/reporting/ext04/h_policy_driver.cpp",
            "driver_sha256":digest(driver), "renderer":"scripts/reports/ext04/h_policy_report.py",
            "renderer_sha256":digest(renderer), "build_log_sha256":digest(build_bytes),
            "figure_style_sha256":digest(helper_sources["figure_style.py"]),
            "plot_adapter_sha256":digest(helper_sources["plot.py"]),
            "report_data_sha256":digest(helper_sources["report_data.py"]),
            "environment_sha256":digest((out/"environment.json").read_bytes())}}
    (out / "records.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    measurements = "".join(f"<tr><td>{r['round']}</td><td>{r['elapsed_ns']/1e6:.3f}</td><td>{r['elapsed_ns']/r['batch']:.1f}</td><td>passed</td></tr>" for r in rows[1:])
    safe_env = html.escape(json.dumps(environment, sort_keys=True))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXT-04 joint H-domain policy evaluation</title><style>body{{font:16px system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#17242d}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #b7c6ce;padding:.5rem;text-align:left}}th{{background:#e9f0f4}}img{{max-width:100%}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>EXT-04 joint H-domain policy evaluation</h1><p><strong>Verdict: descriptive result; performance comparison is inconclusive.</strong> One pinned LP adapter and one fixture were measured. No comparator or source-mapped limiter profile was collected.</p>
<p>This one-step scalar example preserves a correlation between the initial state and measurement error: <code>e=0.1x₀</code>. The controller uses the pre-decision observation <code>y=x₀+e</code> and applies <code>u=−y</code>, producing <code>x₁=−e</code>. A numerical feasible domain witness, six dual support bounds, and a separate primal counterexample smoke case were checked.</p>
<figure><img src="h-domain-2d.svg" alt="Correlated joint H-domain and its terminal state projection"><figcaption>Left: the authored joint H-set in initial-state/error coordinates. Right: its image in initial-state/terminal-state coordinates. Both numeric axes include positioned tick labels and grid lines; the vertical scale is deliberately distinct from the horizontal scale.</figcaption></figure>
<p>Figure policy: Matplotlib 3.11.2 and <code>csl-report-quantitative-v1</code>. Plot rendering is excluded from solver timing. <a href="h-domain-2d.png">PNG view</a> · <a href="figure_style.py">tick/grid policy source</a>.</p>
<h2>Analytic support values</h2><table><thead><tr><th>Constraint</th><th>Maximum activity</th><th>Safety bound</th></tr></thead><tbody>{''.join(f"<tr><td>{r['family']} stage {r['stage']} row {r['row']}</td><td>{r['support_upper_bound']:.8g}</td><td>{r['upper_bound']:.8g}</td></tr>" for r in rows[-1]['result']['constraints'])}</tbody></table>
<h2>Measurements</h2><p>One excluded 100-call warmup followed by seven measured batches of 100 calls. Median {summary['median_batch_ns']/1e6:.3f} ms per batch ({summary['median_ns_per_call']:.1f} ns/call); range {summary['min_batch_ns']/1e6:.3f}–{summary['max_batch_ns']/1e6:.3f} ms. Each call performed seven LP solves and literal correlation, residual, support-bound, replay-status checks. Fixture creation and JSON serialization were excluded.</p>
<table><thead><tr><th>Round</th><th>Batch ms</th><th>ns/call</th><th>Outcome</th></tr></thead><tbody>{measurements}</tbody></table><h2>Environment</h2><pre>{safe_env}</pre>
<h2>Scope and limits</h2><p>These are single-adapter numerical observations on one analytic fixture. The caller-authored H-set is assumed to describe the relevant uncertainty. No validated-arithmetic, policy-synthesis, universal-disturbance, speedup, scalability, or application-load claim is made. The source-mapped performance limiter is unavailable, so performance interpretation is inconclusive.</p>
<p>Source commit <code>{html.escape(source_commit)}</code>; report ID <code>{report_id}</code>. Bundle: <a href="driver.cpp">driver</a>, <a href="renderer.py">renderer</a>, <a href="plot.py">plot adapter</a>, <a href="report_data.py">SVG validator source</a>, <a href="records.json">records</a>, <a href="trials.jsonl">raw trials</a>, <a href="summary.csv">CSV</a>, <a href="environment.json">environment</a>, <a href="release-build-log.txt">Release build log</a>, <a href="{report_id}.zip">offline ZIP</a>.</p></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    files = sorted(path for path in out.iterdir() if path.is_file())
    (out / "manifest.json").write_text(json.dumps({"schema":"csl.ext04-h-policy-manifest/1",
        "report_id":report_id,"source_commit":source_commit,
        "files":{path.name:digest(path.read_bytes()) for path in files}},indent=2,sort_keys=True)+"\n")
    with zipfile.ZipFile(out / f"{report_id}.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(out.iterdir()):
            if path.name != f"{report_id}.zip":
                info = zipfile.ZipInfo(path.name, date_time=(2026,1,1,0,0,0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--collected-utc", required=True)
    parser.add_argument("--driver", type=Path, default=Path("benchmarks/reporting/ext04/h_policy_driver.cpp"))
    args = parser.parse_args()
    render(args.trials, args.build_log, args.environment, args.out,
           args.source_commit, args.collected_utc, args.driver)

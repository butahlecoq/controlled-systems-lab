#!/usr/bin/env python3
"""Render OPT-12 HTML and file hashes from saved records without solver access."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import statistics
import zipfile
from pathlib import Path


def median_range(values: list[float]) -> str:
    if not values:
        return "unavailable"
    return f"{statistics.median(values):.6g} [{min(values):.6g}, {max(values):.6g}]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    source = args.records.resolve(strict=True)
    if args.out.exists():
        parser.error("output destination must be new")
    bundle = json.loads(source.read_text(encoding="utf-8"))
    if bundle.get("metadata", {}).get("schema") != "csl.opt12-cost-report/1":
        parser.error("unsupported OPT-12 records schema")
    rows = bundle["trials"]
    args.out.mkdir(parents=True)
    target = args.out / "records.json"
    target.write_bytes(source.read_bytes())
    raw_path = source.parent / "raw-events.jsonl"
    stderr_path = source.parent / "raw-stderr.txt"
    build_path = source.parent / "release-build-log.txt"
    environment_path = source.parent / "environment.json"
    command_path = source.parent / "measurement-command.txt"
    for item in (raw_path, stderr_path, build_path, environment_path, command_path):
        if item.exists():
            (args.out / item.name).write_bytes(item.read_bytes())
    metadata = bundle["metadata"]
    summaries = []
    for scenario in ("tiny-overhead", "small-reuse"):
        for mode in ("cold", "warm"):
            trials = [row for row in rows if row["scenario"] == scenario and row["mode"] == mode]
            if not trials:
                continue
            get = lambda key: [float(r[key]) for r in trials if r.get(key) is not None]
            work = [sum(float(r.get(key) or 0.0) for key in ("model_load_seconds", "basis_transfer_seconds", "solve_seconds"))
                    for r in trials]
            iterations = [int(r["simplex_iterations"]) for r in trials if r.get("simplex_iterations") is not None]
            summaries.append({"scenario": scenario, "mode": mode, "n": len(trials), "wall_ns": median_range(get("wall_ns")),
                              "load_s": median_range(get("model_load_seconds")), "basis_s": median_range(get("basis_transfer_seconds")),
                              "solve_s": median_range(get("solve_seconds")), "native_work_s": median_range(work),
                              "iterations": median_range(iterations)})
    tiny = {row["mode"]: row for row in summaries if row["scenario"] == "tiny-overhead"}
    if "cold" in tiny and "warm" in tiny:
        tiny_work_more = statistics.median([sum(float(r.get(k) or 0) for k in ("model_load_seconds", "basis_transfer_seconds", "solve_seconds")) for r in rows if r["scenario"] == "tiny-overhead" and r["mode"] == "warm"]) > statistics.median([sum(float(r.get(k) or 0) for k in ("model_load_seconds", "basis_transfer_seconds", "solve_seconds")) for r in rows if r["scenario"] == "tiny-overhead" and r["mode"] == "cold"])
        tiny_iterations_same = sorted(int(r["simplex_iterations"]) for r in rows if r["scenario"] == "tiny-overhead" and r["mode"] == "warm" if r.get("simplex_iterations") is not None) == sorted(int(r["simplex_iterations"]) for r in rows if r["scenario"] == "tiny-overhead" and r["mode"] == "cold" if r.get("simplex_iterations") is not None)
        cost_text = ("The tiny case records higher median model-load + basis-transfer + solve work for reuse with no simplex-iteration reduction." if tiny_work_more and tiny_iterations_same
                     else "The tiny case records basis-transfer overhead; its measured aggregate work does not establish a higher warm cost in this run.")
    else:
        cost_text = "Cold/warm paired cost comparison is incomplete."
    rows_html = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(row[k]))}</td>" for k in ("scenario", "mode", "n", "wall_ns", "load_s", "basis_s", "solve_s", "native_work_s", "iterations")) + "</tr>" for row in summaries)
    trial_html = []
    for row in rows:
        details = html.escape(row.get("diagnostics", ""))
        trial_html.append(f"<tr><td>{html.escape(row['scenario'])}</td><td>{row['pair']}</td><td>{html.escape(row['mode'])}</td><td>{html.escape(str(row.get('cache_state')))}</td><td>{html.escape(str(row.get('basis_accepted')))}</td><td>{row.get('wall_ns')}</td><td>{html.escape(str(row.get('simplex_iterations')))}</td><td><details><summary>raw diagnostics</summary><pre>{details}</pre></details></td></tr>")
    trial_table = "\n".join(trial_html)
    report_id = args.out.name
    metadata_html = "\n".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(json.dumps(v, sort_keys=True))}</td></tr>" for k, v in metadata.items() if k not in {"system_before", "system_after", "input_fixtures"})
    fixtures_html = "\n".join(f"<tr><td>{html.escape(name)}</td><td>{v['rows']} × {v['columns']}</td><td>{html.escape(v['sha256'])}</td><td>{html.escape(str(v['source_rhs']))} → {html.escape(str(v['changed_rhs']))}</td><td>{html.escape(str(v['expected_objective']))}</td></tr>" for name, v in metadata.get("input_fixtures", {}).items())
    files = [p.name for p in args.out.iterdir() if p.is_file()]
    links = " ".join(f'<a href="{html.escape(name)}">{html.escape(name)}</a>' for name in sorted(files) if name != "index.html")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(report_id)} — OPT-12</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}h1,h2{{line-height:1.2}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #9aa4ad;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#edf2f5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:24rem;overflow:auto}}.note{{padding:1rem;border-left:4px solid #46647a;background:#f3f6f8}}.files a{{margin-right:1rem}}small{{color:#48535e}}</style></head>
<body><h1>OPT-12: HiGHS cross-query basis reuse</h1>
<p class="note">{html.escape(cost_text)} These are descriptive measurements for two synthetic LPs on the recorded host. They do not establish a general speedup or worst-case complexity change.</p>
<p>Source commit <code>{html.escape(metadata.get('source_commit',''))}</code>; adapter {html.escape(metadata.get('adapter_version',''))}; native solver {html.escape(metadata.get('native_solver',''))}; {html.escape(str(metadata.get('build_configuration','')))}.</p>
<h2>Workload and independent checks</h2><p>Each warm trial performs one unreported source solve in a fresh workspace, then solves the same changed LP as its paired cold trial. Every measured output is checked for completed optimal status, feasibility, and literal objective. The side order alternates within each pair. Timings use a monotonic clock around <code>LPWorkspace.solve</code>; native model-load, basis-transfer setup, and solve intervals are reported separately.</p>
<table><thead><tr><th>Case</th><th>Size</th><th>Input SHA-256</th><th>RHS change</th><th>Expected objective</th></tr></thead><tbody>{fixtures_html}</tbody></table>
<h2>Median and range</h2><p>Time columns are seconds except public call wall time, which is nanoseconds. “Native work” is the sum of disjoint model-load, basis-transfer, and solve intervals. It excludes independent result verification.</p>
<table><thead><tr><th>Case</th><th>Mode</th><th>n</th><th>Wall ns: median [min, max]</th><th>Model load s</th><th>Basis transfer/setup s</th><th>Solve s</th><th>Native work s</th><th>Simplex iterations</th></tr></thead><tbody>{rows_html}</tbody></table>
<h2>Trials</h2><table><thead><tr><th>Case</th><th>Pair</th><th>Mode</th><th>Cache state</th><th>Basis accepted</th><th>Wall ns</th><th>Iterations</th><th>Diagnostics</th></tr></thead><tbody>{trial_table}</tbody></table>
<h2>Provenance</h2><table><tbody>{metadata_html}</tbody></table><p class="files">Saved evidence: {links} <a href="../{html.escape(report_id)}.zip">offline ZIP</a></p>
<small>Standalone HTML rendered only from saved records. For scope and interpretation, consult the repository's OPT-12 design note and published algorithm-results policy.</small></body></html>"""
    (args.out / "index.html").write_text(page, encoding="utf-8", newline="\n")
    manifest = {"schema": "csl.opt12-cost-manifest/1", "report_id": report_id,
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.out.iterdir()) if p.is_file()}}
    (args.out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    archive = args.out.parent / f"{report_id}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for item in sorted(args.out.iterdir()):
            if item.is_file():
                zipped.write(item, f"{report_id}/{item.name}")
        zipped.writestr(f"{report_id}/offline-index.html", f"<!doctype html><meta charset=\"utf-8\"><a href=\"index.html\">Open {html.escape(report_id)}</a>")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.out.parent / f"{report_id}.zip.sha256").write_text(f"{archive_hash}  {report_id}.zip\n", encoding="ascii")
    print(json.dumps({"report_id": report_id, "files": manifest["files"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

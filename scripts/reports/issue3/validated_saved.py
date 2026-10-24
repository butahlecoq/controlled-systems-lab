"""Build a self-contained issue #3 validated minimax report from saved JSONL."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
import statistics
import sys


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(capture: Path, output: Path) -> None:
    raw = (capture / "measure.stdout.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    expected = {"analytic_2d": (2, 2), "all_infeasible": (1, 0),
                "b08_rounded": (625, 160000)}
    if len(rows) != 24 or any(r["status"] != "passed" for r in rows):
        raise ValueError("expected 24 successful observations")
    for r in rows:
        if r["source_commit"] != "c72f3480c8fea2575ba860890502857006e9b9f4" or r["harness_commit"] != "1c606969b0d15700b61e43effdbbd545e9d0ed73":
            raise ValueError("source or harness identity changed")
        if r["result"].get("plans", r["result"].get("plan_count")) != expected[r["fixture"]][0]:
            raise ValueError("plan count changed")
        if r["result"].get("histories_examined", 0) != expected[r["fixture"]][1]:
            raise ValueError("history count changed")
    measured = [r for r in rows if not r["warmup"]]
    summaries = {}
    for name in expected:
        values = [r["elapsed_ns"] for r in measured if r["fixture"] == name]
        if len(values) != 7:
            raise ValueError("expected seven measured rounds per fixture")
        summaries[name] = {"calls_per_batch": next(r["calls"] for r in measured if r["fixture"] == name),
                           "median_ns": statistics.median(values), "min_ns": min(values), "max_ns": max(values),
                           "observations_ns": values}
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    for p in capture.iterdir():
        if p.is_file() and p.name != "csl_issue3_validated_report":
            (output / "evidence" / p.name).write_bytes(p.read_bytes())
    record = {"schema": "csl.issue3-validated-minimax-record/1", "source_commit": rows[0]["source_commit"],
              "harness_commit": rows[0]["harness_commit"], "fixture_sha256": rows[0]["fixture_sha256"],
              "raw_jsonl_sha256": sha(raw), "rows": rows, "summary": summaries,
              "scope": "Validated finite-action minimax bounds for three fixed fixtures; descriptive single-adapter batch timings."}
    rec_bytes = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    (output / "records.json").write_bytes(rec_bytes)
    with (output / "trials.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["fixture", "round", "warmup", "calls", "elapsed_ns", "status", "plans", "histories"])
        for r in rows:
            res = r["result"]
            w.writerow([r["fixture"], r["round"], r["warmup"], r["calls"], r["elapsed_ns"], r["status"], res.get("plans", res.get("plan_count")), res.get("histories_examined", res.get("evaluated_vertices"))])
    # The analytic fixture is x1 = x0 + u, with u in {(0,0),(1,0)} and target (1,0).
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="330" viewBox="0 0 600 330"><rect width="100%" height="100%" fill="white"/><text x="24" y="30" font-family="sans-serif" font-size="18">2D analytic fixture: two plans, exact zero residual</text><line x1="70" y1="275" x2="530" y2="275" stroke="#333"/><line x1="70" y1="275" x2="70" y2="70" stroke="#333"/><text x="520" y="300" font-family="sans-serif">x₁</text><text x="35" y="78" font-family="sans-serif">x₂</text><circle cx="140" cy="215" r="7" fill="#3674b8"/><circle cx="330" cy="215" r="7" fill="#3674b8"/><circle cx="330" cy="215" r="12" fill="none" stroke="#d23" stroke-width="3"/><text x="115" y="242" font-family="sans-serif">u = (0,0)</text><text x="300" y="242" font-family="sans-serif">u = (1,0)</text><text x="355" y="208" font-family="sans-serif" fill="#b11">target (1,0), residual 0</text><path d="M140 215 L330 215" stroke="#777" stroke-dasharray="5 4"/></svg>'''
    (output / "analytic-2d.svg").write_text(svg, encoding="utf-8")
    cells = []
    for name, s in summaries.items():
        cells.append(f"<tr><td>{html.escape(name)}</td><td>{s['calls_per_batch']}</td><td>{s['median_ns']:,.0f}</td><td>{s['min_ns']:,}–{s['max_ns']:,}</td></tr>")
    b08 = next(r["result"] for r in rows if r["fixture"] == "b08_rounded")
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Issue #3 validated minimax report</title><style>body{{font:16px/1.55 system-ui;max-width:980px;margin:2rem auto;padding:0 1rem;color:#17212b}}table{{border-collapse:collapse}}td,th{{padding:.45rem .8rem;border:1px solid #aaa}}img{{max-width:100%}}code{{overflow-wrap:anywhere}}</style><h1>Issue #3: validated finite-action minimax bounds</h1><p>Three fixed fixtures exercise the public validated API. Timings are descriptive for this host and workload; no comparator, speedup, source-mapped limiter, or per-call latency claim is made.</p><h2>Results</h2><table><thead><tr><th>Fixture</th><th>Calls / batch</th><th>Median batch (ns)</th><th>Range (ns)</th></tr></thead><tbody>{''.join(cells)}</tbody></table><h2>Checked work</h2><p>The 2D analytic case checks 2 plans and 2 disturbance histories per plan and returns the exact bound [0, 0]. The infeasible case checks the one plan is infeasible. The displayed-data B08 case checks {b08['plans']} plans and {b08['histories_examined']:,} histories, with bounds [{b08['lower']}, {b08['upper']}]. This B08 fixture uses the binary64 values represented by its saved hexadecimal input. It is distinct from the printed-decimal rational audit.</p><img src="analytic-2d.svg" alt="Two plans in the 2D analytic fixture; the second reaches the target exactly"><h2>Measurement</h2><p>Seven measured batches per fixture after one excluded warmup. The measured interval includes the public call and result/plan-count checks. Release build, GCC 16.2.1, C++20, Linux x86_64; 8 logical CPUs. Load average before capture: 1.31, 1.81, 1.93. Other interactive processes were present. No profiling counters were collected, so the limiting resource is unidentified.</p><p>Algorithm source <code>{rows[0]['source_commit']}</code>; harness <code>{rows[0]['harness_commit']}</code>; fixture source SHA-256 <code>{rows[0]['fixture_sha256']}</code>.</p><p><a href="records.json">Raw records</a> · <a href="trials.csv">Trial table</a> · <a href="README.md">Reproduction and scope</a> · <a href="manifest.json">File hashes</a></p></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    readme = f'''# Issue #3 validated minimax capture\n\nSeven measured batches per fixture after one excluded warmup. This report measures the validated bounds API with the public driver at source `{rows[0]['source_commit']}` and harness `{rows[0]['harness_commit']}`. It is a single-adapter descriptive capture, not a comparison. No source-mapped limiter profile was collected.\n\nThe B08 capture uses exact-real semantics for the binary64 inputs represented by saved hexadecimal floats. It is not the separate printed-decimal rational audit, and does not establish a general solver guarantee beyond this API's documented contract.\n\n`evidence/` retains configure/build output, smoke and measurement stdout/stderr, the executable SHA-256 receipt, host/platform/compiler receipts, and source status. The executable itself is not included. Regenerate the checked report with `python3 scripts/reports/issue3/validated_saved.py <capture-dir> <new-output-dir>`. Rendering reads saved JSONL and does not run the solver.\n'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    files = {}
    for p in sorted(output.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files[p.relative_to(output).as_posix()] = sha(p.read_bytes())
    manifest = {"schema": "csl.issue3-validated-minimax-manifest/1", "report_id": output.name,
                "source_commit": rows[0]["source_commit"], "harness_commit": rows[0]["harness_commit"],
                "files": files}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))

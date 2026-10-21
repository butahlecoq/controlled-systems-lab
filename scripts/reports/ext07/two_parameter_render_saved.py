"""Render the saved two-parameter EXT-07 report without running the solver."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import io
import json
from pathlib import Path
import statistics
import zipfile

_spec = importlib.util.spec_from_file_location(
    "csl_ext07_two_parameter_collect", Path(__file__).with_name("two_parameter_collect.py"))
collect = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(collect)

RENDERED = ("index.html", "two-control-example.html", "feasible-polygons.svg",
            "summary.csv")


def validate(bundle: Path) -> dict:
    require = collect.require
    require(bundle.is_dir() and not bundle.is_symlink(),
            "Two-parameter bundle missing or unsafe")
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    expected_id = "ext07-hybrid-two-parameter-" + collect.sha(
        collect.encoded(unsigned))[:16]
    require(record.get("schema") == "csl.ext07-hybrid-two-parameter-report/1" and
            record.get("report_id") == bundle.name == expected_id,
            "Two-parameter report identity differs")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        require(path.is_file() and not path.is_symlink() and
                collect.sha(path.read_bytes()) == record["source_sha256"][name],
                "Two-parameter source file differs: " + name)
    pre, post = (record["source_receipts"][name]
                 for name in ("prebuild", "postrun"))
    require(pre["status"] == post["status"] == [] and
            pre["commit"] == post["commit"] == record["source_commit"] and
            pre["tree"] == post["tree"] == record["source_tree"] and
            pre["observed_utc"] < post["observed_utc"] <=
            record["environment"]["collected_utc"],
            "Two-parameter source receipts differ")
    smoke = collect.jsonl(bundle / "smoke.jsonl", 1)
    measure = collect.jsonl(bundle / "measure.jsonl", 8)
    collect.validate_run(smoke[0], "smoke", 0, 1)
    collect.validate_run(measure[0], "warmup", 0, 10)
    for repetition, row in enumerate(measure[1:]):
        collect.validate_run(row, "trial", repetition, 20)
    trials = measure[1:]
    measurement = record["measurement"]
    require(measurement["trials"] == trials and measurement["warmup"] == measure[0] and
            measurement["raw_smoke_sha256"] == record["source_sha256"]["smoke.jsonl"] and
            measurement["raw_measure_sha256"] == record["source_sha256"]["measure.jsonl"] and
            measurement["measured_calls"] == 140 and measurement["failures"] == 0,
            "Two-parameter raw trial data differs")
    totals = [row["end_to_end_total_ns"] for row in trials]
    call_times = [value for row in trials for value in row["call_durations_ns"]]
    require(measurement["median_batch_end_to_end_ns"] ==
            int(statistics.median(totals)) and
            measurement["min_batch_end_to_end_ns"] == min(totals) and
            measurement["max_batch_end_to_end_ns"] == max(totals) and
            measurement["median_call_ns"] == int(statistics.median(call_times)),
            "Two-parameter summary timings differ from raw calls")
    return record


def figure() -> bytes:
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 440" role="img" aria-labelledby="title desc">
<title id="title">Two-stage hybrid feasible control polygons and tied minimizing faces</title>
<desc id="desc">The horizontal axis is u0 and the vertical axis is u1. The enter-full path allows the unit square. The enter-half path allows the rectangle from u0 zero to one half. Both have the same minimizing face u0 equals zero, with u1 anywhere from zero to one.</desc>
<rect width="720" height="440" fill="#16161e"/>
<g font-family="system-ui,sans-serif" fill="#e0def4"><text x="68" y="36" font-size="19">EXT-07 · two free interval controls</text><text x="328" y="408" font-size="16">stage 0 control u₀</text><text x="20" y="90" font-size="16" transform="rotate(-90 20,90)">stage 1 control u₁</text></g>
<path d="M100 350 H620 M100 350 V72" stroke="#908caa" stroke-width="2"/>
<g stroke="#6e6a86" stroke-dasharray="4 5"><path d="M100 350 V72"/><path d="M360 350 V72"/><path d="M620 350 V72"/><path d="M100 211 H620"/><path d="M100 72 H620"/></g>
<path d="M100 350 L620 350 L620 72 L100 72 Z" fill="#9ccfd8" fill-opacity=".08" stroke="#9ccfd8" stroke-width="3" stroke-dasharray="9 6"/>
<path d="M100 350 L360 350 L360 72 L100 72 Z" fill="#c4a7e7" fill-opacity=".35" stroke="#c4a7e7" stroke-width="4"/>
<path d="M100 350 V72" stroke="#f6c177" stroke-width="8"/>
<g font-family="system-ui,sans-serif" fill="#e0def4" font-size="14"><text x="92" y="375">0</text><text x="348" y="375">0.5</text><text x="612" y="375">1</text><text x="69" y="355">0</text><text x="69" y="77">1</text><text x="390" y="105">enter-full: [0,1] × [0,1]</text><text x="390" y="128">enter-half: [0,0.5] × [0,1]</text><text x="128" y="225" fill="#f6c177">both minimizing faces: u₀=0, 0≤u₁≤1</text></g>
<g font-family="system-ui,sans-serif" font-size="13"><path d="M390 164 h28" stroke="#9ccfd8" stroke-width="3" stroke-dasharray="7 4"/><text x="426" y="169" fill="#e0def4">enter-full path</text><path d="M390 189 h28" stroke="#c4a7e7" stroke-width="5"/><text x="426" y="194" fill="#e0def4">enter-half path</text><path d="M390 214 h28" stroke="#f6c177" stroke-width="7"/><text x="426" y="219" fill="#e0def4">global minimizing family</text></g>
</svg>\n'''.encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["repetition", "calls", "failures", "paths", "relation_rows",
                     "relation_matrix_elements", "end_to_end_total_ns",
                     "minimum_call_ns", "maximum_call_ns", "provider", "verifier"])
    for row in record["measurement"]["trials"]:
        writer.writerow([row["repetition"], row["calls"], row["failures"], row["paths"],
                         row["relation_rows"], row["relation_matrix_elements"],
                         row["end_to_end_total_ns"], min(row["call_durations_ns"]),
                         max(row["call_durations_ns"]), row["provider"], row["verifier"]])
    return output.getvalue().encode()


def example_page(record: dict) -> bytes:
    source = html.escape(record["source_commit"])
    scope = html.escape(record["report_id"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXT-07 two-control visual example</title><style>
body{{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}}div{{max-width:980px;margin:auto;padding:1.2rem}}a{{color:#9ccfd8}}section{{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}
</style></head><body><div><p>Controlled Systems Lab - EXT-07</p><h1>Two-control feasible sets and minimizing family</h1><p>This standalone visual example accompanies a measured two-stage scalar hybrid verification fixture.</p></div><div><section><h2>Fixture and analytic answer</h2><p>This scalar-state, two-stage fixture uses joint coordinates <code>(x0,u0,x_pre1,x_post1,u1,x_pre2,x_terminal)</code>, initial state <code>x0=0</code>, flows <code>x_pre1=u0</code> and <code>x_pre2=x_post1+0*u1</code>, identity resets <code>x_post1=x_pre1</code> and <code>x_terminal=x_pre2</code>, a guarded <code>enter-half</code> edge, a parallel universal-guard <code>enter-full</code> edge, and a universal-guard <code>finish</code> edge.</p><p>Two free controls satisfy <code>0 &lt;= u0 &lt;= 1</code> and <code>0 &lt;= u1 &lt;= 1</code>. The <code>enter-half</code> branch adds <code>u0 &lt;= 0.5</code>; <code>enter-full</code> leaves the unit square unchanged. Both minimize the terminal objective <code>x_terminal = u0</code> at zero, so the complete global minimizing family is <code>u0 = 0, 0 &lt;= u1 &lt;= 1</code>.</p><img src="feasible-polygons.svg" alt="Full unit square, half-width feasible rectangle, and shared minimizing face"><p>Assurance is numerical binary64. The figure illustrates the exact fixture; it does not claim measured samples or validated arithmetic.</p></section><section><h2>Reproduce and inspect</h2><p>Build the versioned source commit <code>{source}</code> in Release and run the report capture. From a clean checkout:</p><pre>python scripts/reports/ext07/two_parameter_capture.py --source &lt;source-checkout&gt; --capture &lt;fresh-capture&gt; --commit {source} --cmake &lt;cmake-executable&gt;
python scripts/reports/ext07/two_parameter_collect.py --capture &lt;fresh-capture&gt; --source &lt;source-checkout&gt; --out reports/algorithm-results
python scripts/reports/ext07/two_parameter_render_saved.py --bundle reports/algorithm-results/{scope}
python scripts/reports/ext07/two_parameter_render_saved.py --bundle reports/algorithm-results/{scope} --check</pre><p>Read the <a href="index.html">measured report</a>, <a href="records.json">versioned record</a>, <a href="measure.jsonl">raw per-call measurements</a>, <a href="summary.csv">summary CSV</a>, and <a href="two_parameter_driver.cpp">measured C++ driver</a>. The <a href="{scope}.zip">offline ZIP</a> includes the report and source records.</p></section></div><div><p>EXT-07 - bounded two-stage scalar profile - source <code>{source}</code></p></div></body></html>'''.encode()


def index_page(record: dict) -> bytes:
    source = html.escape(record["source_commit"])
    measurement = record["measurement"]
    trials = "".join(
        f"<tr><td>{row['repetition']}</td><td>{row['calls']}</td>"
        f"<td>{row['end_to_end_total_ns']:,}</td><td>0</td></tr>"
        for row in measurement["trials"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXT-07 two-parameter verifier report</title><style>body{{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}}main,header,footer{{max-width:980px;margin:auto;padding:1.2rem}}a{{color:#9ccfd8}}section{{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #524f67;padding:.45rem;text-align:left}}code{{overflow-wrap:anywhere}}</style></head><body><header><p>Controlled Systems Lab · EXT-07</p><h1>Two-parameter hybrid family verification</h1><p>Measured public path construction, two-branch optimization, and complete-family verification for one fixed two-stage scalar fixture.</p></header><main><section><h2>Analytic answer</h2><p>The <code>enter-half</code> path has feasible controls <code>[0,0.5]×[0,1]</code>; <code>enter-full</code> has <code>[0,1]×[0,1]</code>. Both minimize <code>x_terminal=u₀</code> at zero, retaining the complete tied families <code>u₀=0, 0≤u₁≤1</code>.</p><p><a href="two-control-example.html">Open the standalone two-control example</a> (includes a labelled plot, fixture, independent answer, and reproduction commands).</p><img src="feasible-polygons.svg" alt="The full unit square, half-width feasible rectangle, and common minimizing face"></section><section><h2>Measured execution</h2><p>One excluded 10-call warmup followed by seven measured batches of 20 calls: 140 measured calls, no failures. Median batch duration is {measurement['median_batch_end_to_end_ns']:,} ns (range {measurement['min_batch_end_to_end_ns']:,}–{measurement['max_batch_end_to_end_ns']:,} ns); median individual call is {measurement['median_call_ns']:,} ns. Each end-to-end interval includes fixture/provider setup, complete two-path relation assembly, both HiGHS LP solves, tied-face construction, and verification of both path families. CTest and build time are excluded.</p><table><thead><tr><th>Batch</th><th>Calls</th><th>End-to-end total (ns)</th><th>Failures</th></tr></thead><tbody>{trials}</tbody></table><p>Recorded provider: <code>{collect.EXPECTED_PROVIDER}</code>. Verifier: <code>csl.hybrid.scalar-two-parameter-polytope</code>. Outcomes for both branches are feasibility, objective optimality, and continuous coverage established.</p></section><section><h2>Scope and provenance</h2><p>This is descriptive evidence for one Windows MSVC Release host and one analytic fixture. It makes no comparison, speedup, source-mapped bottleneck, or scalability claim. It covers exactly two scalar free controls; larger polytope dimensions and general horizons remain unmeasured. Assurance is numerical binary64, not validated arithmetic.</p><p>Source commit: <code>{source}</code>. See <a href="records.json">versioned record</a>, <a href="measure.jsonl">raw per-call timings and batches</a>, <a href="smoke.jsonl">smoke record</a>, <a href="summary.csv">summary CSV</a>, <a href="manifest.json">hash manifest</a>, <a href="two_parameter_driver.cpp">measured driver</a>, and <a href="{html.escape(record['report_id'])}.zip">offline ZIP</a>.</p></section></main><footer>EXT-07 · two-parameter numerical evidence · source <code>{source}</code></footer></body></html>'''.encode()


def offline_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = zipfile.ZIP_STORED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
    return output.getvalue()


def render(bundle: Path, check: bool) -> dict:
    record = validate(bundle)
    files = {"index.html": index_page(record),
             "two-control-example.html": example_page(record),
             "feasible-polygons.svg": figure(), "summary.csv": summary_csv(record)}
    for name, content in files.items():
        path = bundle / name
        if check:
            collect.require(path.read_bytes() == content,
                            "Two-parameter rendered file differs: " + name)
        else:
            collect.require(not path.exists(),
                            "Two-parameter rendered output already exists: " + name)
            path.write_bytes(content)
    inventory = {name: collect.sha((bundle / name).read_bytes())
                 for name in (*collect.SOURCE_FILES, "records.json", *RENDERED)}
    manifest = {"schema": "csl.ext07-hybrid-two-parameter-manifest/1",
                "report_id": bundle.name, "source_commit": record["source_commit"],
                "files": inventory}
    manifest_path = bundle / "manifest.json"
    if check:
        collect.require(manifest_path.read_bytes() == collect.encoded(manifest),
                        "Two-parameter manifest differs")
    else:
        collect.require(not manifest_path.exists(),
                        "Two-parameter manifest already exists")
        manifest_path.write_bytes(collect.encoded(manifest))
    all_files = {name: (bundle / name).read_bytes()
                 for name in (*inventory, "manifest.json")}
    zip_bytes = offline_zip(all_files)
    zip_path = bundle / (bundle.name + ".zip")
    if check:
        collect.require(zip_path.read_bytes() == zip_bytes,
                        "Two-parameter offline ZIP differs")
    else:
        collect.require(not zip_path.exists(), "Two-parameter offline ZIP already exists")
        zip_path.write_bytes(zip_bytes)
    collect.require({path.name for path in bundle.iterdir()} ==
                    set((*inventory, "manifest.json", zip_path.name)),
                    "Two-parameter bundle inventory differs")
    return {"report_id": bundle.name, "source_commit": record["source_commit"],
            "manifest_sha256": collect.sha(manifest_path.read_bytes()),
            "zip_sha256": collect.sha(zip_bytes),
            "index_sha256": collect.sha(files["index.html"]),
            "example_sha256": collect.sha(files["two-control-example.html"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(render(args.bundle, args.check), sort_keys=True))

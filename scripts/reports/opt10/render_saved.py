"""Render the OPT-10 report, 2D example, manifest and ZIP from saved bytes."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("opt10_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "feasible-box-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "OPT-10 bundle missing")
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == "csl.opt10-smooth-convex-report/1" and
                    record.get("report_id") == bundle.name ==
                    "opt10-smooth-" + collect.sha(collect.encoded(unsigned))[:16],
                    "OPT-10 record identity differs")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink() and
                        collect.sha(path.read_bytes()) == record["source_sha256"][name],
                        "OPT-10 source file differs: " + name)
    collect.require(record["problem"] == {
        "variables": [[0, 1], [-1, 1]], "rows": [],
        "objective": "0.5*((x-2)^2+(y+2)^2)",
        "gradient": ["x-2", "y+2"], "start": [0, 0],
        "objective_claim": "caller-declared differentiable convex"},
        "OPT-10 problem fixture differs")
    collect.require(record["analytic"] == {
        "point": [1, -1], "objective": 1,
        "gradient": [-1, 1], "projected_residual": 0},
        "OPT-10 analytic answer differs")
    pre, post = (record["source_receipts"][key] for key in ("prebuild", "postrun"))
    collect.require(pre["status"] == post["status"] == [] and
                    pre["commit"] == post["commit"] == record["source_commit"] ==
                    record["environment"]["source_commit"] and
                    pre["tree"] == post["tree"] == record["source_tree"] ==
                    record["environment"]["source_tree"] and
                    pre["observed_utc"] < post["observed_utc"] <=
                    record["environment"]["collected_utc"] and
                    (bundle / "smoke.stderr.txt").read_bytes() ==
                    (bundle / "measure.stderr.txt").read_bytes() == b"",
                    "OPT-10 saved capture receipts differ")
    collect.rows(bundle / "smoke.csv", "smoke")
    measure = collect.rows(bundle / "measure.csv", "measure")
    collect.require(record["measurement"]["warmup"] == measure[0] and
                    record["measurement"]["trials"] == measure[1:] and
                    record["measurement"]["raw_smoke_sha256"] ==
                    record["source_sha256"]["smoke.csv"] and
                    record["measurement"]["raw_measure_sha256"] ==
                    record["source_sha256"]["measure.csv"] and
                    record["measurement"]["measured_calls"] == 700 and
                    record["measurement"]["failures"] == 0,
                    "OPT-10 measurement record differs")
    durations = [int(row["elapsed_ns"]) for row in measure[1:]]
    collect.require(record["measurement"]["median_batch_ns"] == sorted(durations)[3] and
                    record["measurement"]["min_batch_ns"] == min(durations) and
                    record["measurement"]["max_batch_ns"] == max(durations),
                    "OPT-10 timing summary differs")
    return record


def figure() -> bytes:
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 440" role="img" aria-labelledby="title desc">
<title id="title">OPT-10 feasible box and analytic minimizer</title>
<desc id="desc">The feasible box spans x from zero to one and y from minus one to one. The supplied start is at zero, zero. The independently derived minimizer is at one, minus one. The connecting segment illustrates feasibility and is not a saved iteration trace.</desc>
<rect width="700" height="440" fill="#16161e"/>
<g fill="#e0def4" font-family="sans-serif" font-size="16">
<text x="48" y="32">OPT-10 · smooth convex quadratic on a 2D box</text>
<text x="495" y="400">x</text><text x="54" y="65">y</text>
<text x="80" y="424">The segment illustrates feasible points, not a saved iterate trace.</text>
</g>
<path d="M 85 350 H 570 M 100 375 V 50" stroke="#908caa"/>
<rect x="100" y="50" width="400" height="300" fill="#31748f" fill-opacity=".17" stroke="#9ccfd8" stroke-width="3"/>
<path d="M 100 200 L 500 350" stroke="#f6c177" stroke-width="2" stroke-dasharray="7 6"/>
<circle cx="100" cy="200" r="7" fill="#ebbcba"/>
<circle cx="500" cy="350" r="8" fill="#f6c177"/>
<g fill="#e0def4" font-family="sans-serif" font-size="15">
<text x="115" y="192">start (0, 0)</text>
<text x="345" y="340">minimizer (1, -1)</text>
<text x="106" y="70">y = 1</text><text x="106" y="343">y = -1</text>
<text x="105" y="375">x = 0</text><text x="453" y="375">x = 1</text>
</g>
</svg>'''
    return (svg + "\n").encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["case", "measured_batches", "calls_per_batch", "successes",
                     "failures", "median_batch_ns", "min_batch_ns", "max_batch_ns"])
    measurement = record["measurement"]
    writer.writerow(["box-quadratic", 7, 100, 700, 0,
                     measurement["median_batch_ns"], measurement["min_batch_ns"],
                     measurement["max_batch_ns"]])
    return output.getvalue().encode()


def page(record: dict, example: bool) -> bytes:
    report_id = escape(record["report_id"])
    source = escape(record["source_commit"])
    measurement = record["measurement"]
    title = "2D feasible-direction example" if example else "Declared smooth-convex adapter report"
    lead = ("An analytic quadratic on a box shows the feasible start and constrained minimizer."
            if example else "Saved numerical observations of the public OPT-10 adapter route.")
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OPT-10 · {title}</title><style>
body{{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}}
div.header,div.main,div.footer{{max-width:960px;margin:auto;padding:1.4rem}}
a{{color:#9ccfd8}} div.section{{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%;display:block;overflow-x:auto}}
td,th{{border:1px solid #524f67;padding:.45rem;text-align:left;white-space:nowrap}}
img{{width:100%;height:auto}} code{{overflow-wrap:anywhere}}
</style></head><body><div class="header"><p>Controlled Systems Lab · OPT-10</p><h1>{title}</h1><p>{lead}</p></div><div class="main">
<div class="section"><h2>Minimal input and analytic answer</h2>
<p>The decision coordinates are <code>(x,y)</code>. The feasible box is
<code>0 ≤ x ≤ 1</code>, <code>-1 ≤ y ≤ 1</code>. The supplied start is
<code>(0,0)</code>. The caller declares the differentiable convex objective
<code>f(x,y)=0.5*((x-2)²+(y+2)²)</code> with analytic gradient
<code>(x-2,y+2)</code>. Independent coordinatewise minimization gives
<code>(1,-1)</code> and objective <code>1</code>. The unconstrained center
<code>(2,-2)</code> lies outside the box. The dashed segment is a geometric
illustration of feasible points, not a saved iteration trace.</p>
<img src="feasible-box-2d.svg" alt="Two-dimensional feasible box, supplied start and analytic minimizer"></div>
<div class="section"><h2>Recorded result</h2>
<table><thead><tr><th>Output</th><th>Saved value</th><th>Independent answer</th></tr></thead><tbody>
<tr><td>Point</td><td>(1,-1)</td><td>(1,-1)</td></tr>
<tr><td>Objective</td><td>1</td><td>1</td></tr>
<tr><td>Projected residual</td><td>0</td><td>0 at the exact box minimizer</td></tr>
</tbody></table><p>Every timed call checked the point, objective, gradient, projected residual,
one accepted iteration and numerical evidence label. The API's stationarity is
conditional on the caller's convexity and gradient assertions. It is not a
validated convexity certificate, numerical global-error bound or complete optimal family.</p></div>
<div class="section"><h2>Measurement and scope</h2>
<p>One excluded 100-call warmup preceded seven measured 100-call batches: 700 verified
calls, zero observed failures. Median batch duration was {measurement['median_batch_ns']:,} ns
(range {measurement['min_batch_ns']:,}–{measurement['max_batch_ns']:,} ns). Each interval includes
feasible-set/objective construction, production LP registration and workspace creation,
the public minimization call and literal checks. It excludes CSV output and rendering.
These are descriptive single-adapter durations on the recorded host; no comparator,
speedup or source-mapped limiter is claimed. Native internal counters and actual
thread activity were unavailable.</p>
<p>Source commit: <code>{source}</code>. The saved <a href="records.json">record</a>,
<a href="measure.csv">raw trial CSV</a>, <a href="summary.csv">summary CSV</a>,
<a href="manifest.json">manifest</a> and <a href="{report_id}.zip">offline ZIP</a>
bind the observation to the build and host receipts. Reproduce with
<code>python scripts/reports/opt10/capture.py --source &lt;clean-checkout&gt; --capture &lt;new-directory&gt; --commit {source} --cmake &lt;cmake&gt;</code>,
then run <code>collect.py</code> and <code>render_saved.py</code> on the saved capture.</p></div>
<p><a href="{'index.html' if example else 'example-2d.html'}">{'Full report' if example else '2D example'}</a></p>
</div><div class="footer">OPT-10 · saved binary64 evidence only</div></body></html>'''
    return html.encode()


def offline_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = zipfile.ZIP_STORED
            item.external_attr = 0o644 << 16
            archive.writestr(item, data, compress_type=zipfile.ZIP_STORED)
    return output.getvalue()


def render(bundle: Path, check: bool) -> dict:
    record = validate(bundle)
    files = {"index.html": page(record, False),
             "example-2d.html": page(record, True),
             "feasible-box-2d.svg": figure(),
             "summary.csv": summary_csv(record)}
    for name, data in files.items():
        path = bundle / name
        if check:
            collect.require(path.read_bytes() == data, "OPT-10 rendered file differs: " + name)
        else:
            collect.require(not path.exists(), "OPT-10 rendered file already exists: " + name)
            path.write_bytes(data)
    inventory = {name: collect.sha((bundle / name).read_bytes()) for name in
                 (*collect.SOURCE_FILES, "records.json", *RENDERED)}
    manifest = {"schema": "csl.opt10-manifest/1", "report_id": bundle.name,
                "source_commit": record["source_commit"], "sha256": inventory}
    path = bundle / "manifest.json"
    if check:
        collect.require(path.read_bytes() == collect.encoded(manifest),
                        "OPT-10 manifest differs")
    else:
        collect.require(not path.exists(), "OPT-10 manifest already exists")
        path.write_bytes(collect.encoded(manifest))
    all_files = {name: (bundle / name).read_bytes() for name in (*inventory, "manifest.json")}
    archive = offline_zip(all_files)
    zip_path = bundle / (bundle.name + ".zip")
    if check:
        collect.require(zip_path.read_bytes() == archive, "OPT-10 ZIP differs")
    else:
        collect.require(not zip_path.exists(), "OPT-10 ZIP already exists")
        zip_path.write_bytes(archive)
    collect.require({path.name for path in bundle.iterdir()} ==
                    set((*all_files, zip_path.name)), "OPT-10 bundle inventory differs")
    return {"report_id": bundle.name, "source_commit": record["source_commit"],
            "manifest_sha256": collect.sha(path.read_bytes()),
            "zip_sha256": collect.sha(archive),
            "index_sha256": collect.sha(files["index.html"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(render(args.bundle, args.check), sort_keys=True))

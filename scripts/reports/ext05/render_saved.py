"""Render the EXT-05 HTML, 2D example, manifest and offline ZIP from saved bytes."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("ext05_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "trajectory-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "EXT-05 bundle missing")
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == "csl.ext05-discretization-report/1" and
                    record.get("report_id") == bundle.name ==
                    "ext05-discretization-" + collect.sha(collect.encoded(unsigned))[:16],
                    "EXT-05 record identity differs")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink() and
                        collect.sha(path.read_bytes()) == record["source_sha256"][name],
                        "EXT-05 source file differs: " + name)
    collect.require(record["model"] == {
        "time_domain": "continuous", "coefficient_variation": "constant_lti",
        "hold": "zero_order_hold", "times": [0, 1, 3],
        "A": [[0, 1], [0, 0]], "B": [[0], [1]],
        "E_shape": [2, 0], "offset": [0, 0],
        "controls": [2, -1], "initial_state": [0, 0]},
        "EXT-05 model fixture differs")
    collect.require(record["analytic"] == {
        "transition_A01": [1, 2], "transition_B0": [0.5, 2],
        "transition_B1": [1, 2], "trajectory": [[0, 0], [1, 2], [3, 0]]},
        "EXT-05 analytic reference differs")
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
                    "EXT-05 saved capture receipts differ")
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
                    "EXT-05 measurement record differs")
    durations = [int(row["elapsed_ns"]) for row in measure[1:]]
    collect.require(record["measurement"]["median_batch_ns"] == sorted(durations)[3] and
                    record["measurement"]["min_batch_ns"] == min(durations) and
                    record["measurement"]["max_batch_ns"] == max(durations),
                    "EXT-05 timing summary differs")
    return record


def figure() -> bytes:
    # Physical axes: position horizontally, velocity vertically.
    points = [(0, 0), (1, 2), (3, 0)]
    xy = [(110 + 160*x, 330 - 110*y) for x, y in points]
    line = " ".join(f"{x},{y}" for x, y in xy)
    circles = "\n".join(
        f'<circle cx="{x}" cy="{y}" r="6" fill="#f6c177"/>'
        f'<text x="{x+10}" y="{y-10}" fill="#e0def4" font-size="15">'
        f'x{k}=({points[k][0]},{points[k][1]})</text>'
        for k, (x, y) in enumerate(xy))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 410" role="img" aria-labelledby="title desc">
<title id="title">EXT-05 double-integrator state trajectory</title>
<desc id="desc">Position and velocity states at times zero, one and three: (0,0), (1,2), (3,0).</desc>
<rect width="700" height="410" fill="#16161e"/>
<path d="M 75 330 H 640 M 110 365 V 55" stroke="#908caa"/>
<g fill="#e0def4" font-family="sans-serif" font-size="16">
<text x="540" y="355">position</text><text x="20" y="65">velocity</text>
<text x="28" y="30">EXT-05 · continuous double integrator, explicit ZOH conversion</text>
<text x="100" y="389">t=0</text><text x="250" y="389">t=1</text><text x="570" y="389">t=3</text>
</g>
<polyline points="{line}" fill="none" stroke="#9ccfd8" stroke-width="3"/>
{circles}
</svg>'''
    return (svg + "\n").encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["case", "measured_batches", "calls_per_batch", "successes",
                     "failures", "median_batch_ns", "min_batch_ns", "max_batch_ns"])
    measurement = record["measurement"]
    writer.writerow(["double-integrator", 7, 100, 700, 0,
                     measurement["median_batch_ns"], measurement["min_batch_ns"],
                     measurement["max_batch_ns"]])
    return output.getvalue().encode()


def page(record: dict, example: bool) -> bytes:
    report_id = escape(record["report_id"])
    source = escape(record["source_commit"])
    measurement = record["measurement"]
    median = measurement["median_batch_ns"]
    title = "2D double-integrator example" if example else "Continuous-model discretization report"
    lead = ("A two-state continuous plant is converted over physical intervals of one and two time units."
            if example else "Saved numerical observations of the public EXT-05 conversion route.")
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXT-05 · {title}</title><style>
body{{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}}
div.header,div.main,div.footer{{max-width:960px;margin:auto;padding:1.4rem}}
a{{color:#9ccfd8}} div.section{{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%;display:block;overflow-x:auto}}
td,th{{border:1px solid #524f67;padding:.45rem;text-align:left;white-space:nowrap}}
img{{width:100%;height:auto}} code{{overflow-wrap:anywhere}}
</style></head><body><div class="header"><p>Controlled Systems Lab · EXT-05</p><h1>{title}</h1><p>{lead}</p></div><div class="main">
<div class="section"><h2>Minimal input and analytic answer</h2>
<p>State coordinates are position and velocity. The continuous rates are
<code>A=[[0,1],[0,0]]</code>, <code>B=[[0],[1]]</code>, zero offset and no external port.
Physical times are <code>[0,1,3]</code>; zero-order-held controls are <code>[2,-1]</code>.
The initial state is <code>(0,0)</code>. Analytic transitions are
<code>A_d=[[1,Δt],[0,1]]</code> and <code>B_d=[Δt²/2,Δt]</code>, yielding
<code>(0,0) → (1,2) → (3,0)</code>.</p>
<img src="trajectory-2d.svg" alt="Position and velocity state trajectory at times zero, one and three"></div>
<div class="section"><h2>Recorded result</h2><table><thead><tr><th>Stage</th><th>Duration</th><th>A[0,1]</th><th>B[0]</th><th>B[1]</th><th>State after stage</th></tr></thead>
<tbody><tr><td>0</td><td>1</td><td>1</td><td>0.5</td><td>1</td><td>(1,2)</td></tr>
<tr><td>1</td><td>2</td><td>2</td><td>2</td><td>2</td><td>(3,0)</td></tr></tbody></table>
<p>Every saved call checked these independent literals. The receipt records constant LTI rates,
zero-order hold, RK4 step doubling and an observed local estimate. That estimate is not a
certified global error bound.</p></div>
<div class="section"><h2>Measurement and scope</h2>
<p>One excluded 100-call warmup preceded seven measured 100-call batches: 700 verified calls,
zero observed failures. Median batch duration was {median:,} ns (range
{measurement['min_batch_ns']:,}–{measurement['max_batch_ns']:,} ns). Each interval includes
fixture construction, the public discretizer, snapshot, two state steps and literal checks;
it excludes CSV output and rendering. These are single-adapter descriptive durations on
the recorded host, with no comparator, speedup or limiter attribution. Native internal
counters and actual thread activity were unavailable.</p>
<p>Source commit: <code>{source}</code>. The saved <a href="records.json">record</a>,
<a href="measure.csv">raw trial CSV</a>, <a href="summary.csv">summary CSV</a>,
<a href="manifest.json">manifest</a> and <a href="{report_id}.zip">offline ZIP</a>
bind the result to the build and host receipts. Reproduce with
<code>python scripts/reports/ext05/capture.py --source &lt;clean-checkout&gt; --capture &lt;new-directory&gt; --commit {source} --cmake &lt;cmake&gt;</code>,
then run <code>collect.py</code> and <code>render_saved.py</code> on the saved capture.</p></div>
<p><a href="{'index.html' if example else 'example-2d.html'}">{'Full report' if example else '2D example'}</a></p>
</div><div class="footer">EXT-05 · saved binary64 evidence only</div></body></html>'''
    return html.encode()


def offline_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    return output.getvalue()


def render(bundle: Path, check: bool) -> dict:
    record = validate(bundle)
    files = {"index.html": page(record, False),
             "example-2d.html": page(record, True),
             "trajectory-2d.svg": figure(),
             "summary.csv": summary_csv(record)}
    for name, data in files.items():
        path = bundle / name
        if check:
            collect.require(path.read_bytes() == data, "EXT-05 rendered file differs: " + name)
        else:
            collect.require(not path.exists(), "EXT-05 rendered file already exists: " + name)
            path.write_bytes(data)
    inventory = {name: collect.sha((bundle / name).read_bytes()) for name in
                 (*collect.SOURCE_FILES, "records.json", *RENDERED)}
    manifest = {"schema": "csl.ext05-manifest/1", "report_id": bundle.name,
                "source_commit": record["source_commit"], "sha256": inventory}
    path = bundle / "manifest.json"
    if check:
        collect.require(path.read_bytes() == collect.encoded(manifest),
                        "EXT-05 manifest differs")
    else:
        collect.require(not path.exists(), "EXT-05 manifest already exists")
        path.write_bytes(collect.encoded(manifest))
    all_files = {name: (bundle / name).read_bytes() for name in (*inventory, "manifest.json")}
    archive = offline_zip(all_files)
    zip_path = bundle / (bundle.name + ".zip")
    if check:
        collect.require(zip_path.read_bytes() == archive, "EXT-05 ZIP differs")
    else:
        collect.require(not zip_path.exists(), "EXT-05 ZIP already exists")
        zip_path.write_bytes(archive)
    collect.require({path.name for path in bundle.iterdir()} ==
                    set((*all_files, zip_path.name)), "EXT-05 bundle inventory differs")
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

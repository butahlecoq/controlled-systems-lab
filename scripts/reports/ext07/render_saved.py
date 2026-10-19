"""Render the EXT-07 saved report and 2D joint-state/control example without execution."""
from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

_collect_spec = importlib.util.spec_from_file_location(
    "csl_ext07_report_collect", Path(__file__).with_name("ext07_collect.py"))
collect = importlib.util.module_from_spec(_collect_spec)
assert _collect_spec.loader is not None
_collect_spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "joint-relation-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    require = collect.require
    require(bundle.is_dir() and not bundle.is_symlink(), "EXT-07 bundle missing or unsafe")
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    require(record.get("schema") == "csl.ext07-hybrid-profile-report/1" and
            record.get("report_id") == bundle.name ==
            "ext07-hybrid-" + collect.sha(collect.encoded(unsigned))[:16],
            "EXT-07 record identity differs")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        require(path.is_file() and not path.is_symlink() and
                collect.sha(path.read_bytes()) == record["source_sha256"][name],
                "EXT-07 source file differs: " + name)
    pre, post = (record["source_receipts"][key] for key in ("prebuild", "postrun"))
    require(pre["status"] == post["status"] == [] and
            pre["commit"] == post["commit"] == record["source_commit"] and
            pre["tree"] == post["tree"] == record["source_tree"] and
            pre["observed_utc"] < post["observed_utc"] <= record["environment"]["collected_utc"],
            "EXT-07 frozen-source receipts differ")
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
            "EXT-07 saved trial data differs from the raw capture")
    durations = [row["end_to_end_total_ns"] for row in trials]
    require(measurement["median_batch_end_to_end_ns"] == int(__import__("statistics").median(durations)) and
            measurement["min_batch_end_to_end_ns"] == min(durations) and
            measurement["max_batch_end_to_end_ns"] == max(durations),
            "EXT-07 timing summary differs from raw repetitions")
    return record


def figure() -> bytes:
    return ('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 440" role="img" aria-labelledby="title desc">
<title id="title">One-step scalar hybrid feasible relation and minimizer</title>
<desc id="desc">The horizontal axis is the scalar control u0 from zero to one half. The vertical axis is terminal state x1. The feasible joint relation is x1 equals u0 on the interval from zero to one half. The unique minimum of x1 is at u0 equals zero and x1 equals zero.</desc>
<rect width="720" height="440" fill="#16161e"/>
<g font-family="system-ui,sans-serif" fill="#e0def4">
<text x="70" y="38" font-size="20">EXT-07 · one-step scalar hybrid profile</text>
<text x="350" y="405" font-size="16">continuous control u₀</text>
<text x="19" y="85" font-size="16" transform="rotate(-90 19,85)">terminal state x₁</text>
</g>
<path d="M90 350 H650 M90 350 V65" stroke="#908caa" stroke-width="2"/>
<g stroke="#6e6a86" stroke-dasharray="4 5"><path d="M90 350 V65"/><path d="M370 350 V65"/><path d="M90 65 H650"/></g>
<path d="M90 350 L370 65" fill="none" stroke="#9ccfd8" stroke-width="5"/>
<circle cx="90" cy="350" r="9" fill="#f6c177" stroke="#16161e" stroke-width="3"/>
<g font-family="system-ui,sans-serif" fill="#e0def4" font-size="14">
<text x="82" y="375">0</text><text x="362" y="375">0.5</text><text x="636" y="375">1</text>
<text x="62" y="355">0</text><text x="52" y="70">0.5</text>
<text x="110" y="320">global minimum (u₀,x₁)=(0,0)</text>
<text x="405" y="135">feasible: x₁=u₀, 0≤u₀≤0.5</text>
</g>
</svg>\n''').encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["repetition", "calls", "failures", "assembly_total_ns", "solve_total_ns",
                     "verify_total_ns", "end_to_end_total_ns", "objective", "control",
                     "relation_rows", "relation_matrix_elements"])
    for row in record["measurement"]["trials"]:
        writer.writerow([row["repetition"], row["calls"], row["failures"],
                         row["assembly_total_ns"], row["solve_total_ns"],
                         row["verify_total_ns"], row["end_to_end_total_ns"],
                         row["objective"], row["control"], row["relation_rows"],
                         row["relation_matrix_elements"]])
    return output.getvalue().encode()


def page(record: dict, example: bool) -> bytes:
    report_id = escape(record["report_id"])
    source = escape(record["source_commit"])
    measurement = record["measurement"]
    medians = measurement["median_phase_total_ns"]
    trials = measurement["trials"]
    provider = escape(trials[0]["provider"])
    bounds_returned = all(row["objective_lower"] is not None and row["objective_upper"] is not None
                          for row in trials)
    bound_note = ("The solver returned objective bounds for every repetition."
                  if bounds_returned else
                  "The LP adapter returned no objective interval bounds; the bounded independent scalar family verifier checked the global minimum and complete minimizer set.")
    row_residuals = [row["primal_row_violation"] for row in trials if row["primal_row_violation"] is not None]
    variable_residuals = [row["primal_variable_violation"] for row in trials
                          if row["primal_variable_violation"] is not None]
    residual_note = ("Maximum reported primal row residual: " + format(max(row_residuals), ".3g") +
                     "; variable residual: " + format(max(variable_residuals), ".3g") + "."
                     if row_residuals and variable_residuals else
                     "Primal residual counters were unavailable.")
    title = "2D joint-relation example" if example else "Hybrid profile numerical report"
    intro = ("The axes show the joint relation between one scalar control and the terminal state."
             if example else "Recorded execution of the public hybrid path, optimization and family-verification route.")
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXT-07 · {title}</title><style>
body{{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}}
header,main,footer{{max-width:980px;margin:auto;padding:1.3rem}}a{{color:#9ccfd8}}
.section{{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%;display:block;overflow-x:auto}}td,th{{border:1px solid #524f67;padding:.45rem;text-align:left;white-space:nowrap}}
img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}
</style></head><body><div><p>Controlled Systems Lab · EXT-07</p><h1>{title}</h1><p>{intro}</p></div><div>
<div class="section"><h2>Input and analytic result</h2>
<p>There are two modes (<code>coast</code> and <code>terminal</code>) and one permitted edge.
The scalar flow is <code>x_pre=x₀+u₀</code>, with <code>x₀=0</code>, <code>u₀∈[0,1]</code>,
guard <code>x_pre∈[0,0.5]</code>, identity reset and terminal objective <code>minimize x₁</code>.
The full joint relation is <code>x₀=0, x_pre=u₀, x₁=u₀, 0≤u₀≤0.5</code>.
Its complete minimizer family is the point <code>(x₀,u₀,x_pre,x₁)=(0,0,0,0)</code>.</p>
<img src="joint-relation-2d.svg" alt="Control versus terminal state for the feasible one-step hybrid relation, with its unique minimum marked"></div>
<div class="section"><h2>Observed branch and verification</h2>
<table><thead><tr><th>Paths</th><th>H rows</th><th>Dense row entries</th><th>Provider</th><th>Outcome</th><th>Feasibility</th><th>Optimality</th><th>Family coverage</th></tr></thead>
<tbody><tr><td>1</td><td>7</td><td>28</td><td>{provider}</td><td>completed / optimal</td>
<td>established</td><td>established</td><td>established</td></tr></tbody></table>
<p>Every measured repetition matched objective 0 and control 0 within <code>1e-8</code>.
The verifier uses numerical binary64 checks; this is not validated arithmetic. {escape(bound_note)}
{escape(residual_note)}</p></div>
<div class="section"><h2>Measurements</h2>
<p>One excluded 10-call warmup preceded seven measured 20-call batches: 140 measured calls and
zero observed failures. Median total batch duration: {measurement['median_batch_end_to_end_ns']:,} ns
(range {measurement['min_batch_end_to_end_ns']:,}–{measurement['max_batch_end_to_end_ns']:,} ns).
Median accumulated phase durations: setup {medians['setup']:,} ns, relation assembly {medians['assembly']:,} ns,
solve {medians['solve']:,} ns, verify {medians['verify']:,} ns, and end-to-end {medians['end_to_end']:,} ns.
End-to-end includes fixture/provider setup, path enumeration, relation construction, solve and family verification.
Phase medians are calculated separately across batches and are not additive to the end-to-end median;
output serialization and rendering are excluded.</p>
<p>One host and one fixed profile are measured. There is no comparator, speedup, source-mapped bottleneck,
or scalability claim. Thread and backend details, all raw repetitions, source/build receipts, and failures
are retained in the <a href="records.json">versioned record</a>,
<a href="measure.jsonl">raw trials</a>, <a href="smoke.jsonl">smoke row</a>,
<a href="summary.csv">summary CSV</a>, <a href="manifest.json">manifest</a>, and
<a href="{report_id}.zip">offline ZIP</a>. Source commit: <code>{source}</code>.</p></div>
<p><a href="{'index.html' if example else 'example-2d.html'}">{'Full report' if example else 'Open the 2D example'}</a></p>
</div><div>EXT-07 · one-step scalar interval evidence only</div></body></html>'''
    return html.encode()


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
    files = {"index.html": page(record, False), "example-2d.html": page(record, True),
             "joint-relation-2d.svg": figure(), "summary.csv": summary_csv(record)}
    for name, content in files.items():
        path = bundle / name
        if check:
            collect.require(path.read_bytes() == content, "EXT-07 renderer output differs: " + name)
        else:
            collect.require(not path.exists(), "EXT-07 rendered output already exists: " + name)
            path.write_bytes(content)
    inventory = {name: collect.sha((bundle / name).read_bytes()) for name in
                 (*collect.SOURCE_FILES, "records.json", *RENDERED)}
    manifest = {"schema": "csl.ext07-manifest/1", "report_id": bundle.name,
                "source_commit": record["source_commit"], "sha256": inventory}
    manifest_path = bundle / "manifest.json"
    if check:
        collect.require(manifest_path.read_bytes() == collect.encoded(manifest),
                        "EXT-07 manifest differs")
    else:
        collect.require(not manifest_path.exists(), "EXT-07 manifest already exists")
        manifest_path.write_bytes(collect.encoded(manifest))
    files["manifest.json"] = manifest_path.read_bytes()
    zip_bytes = offline_zip({name: (bundle / name).read_bytes() for name in
                             (*inventory, "manifest.json")})
    zip_path = bundle / (bundle.name + ".zip")
    if check:
        collect.require(zip_path.read_bytes() == zip_bytes, "EXT-07 offline ZIP differs")
    else:
        collect.require(not zip_path.exists(), "EXT-07 offline ZIP already exists")
        zip_path.write_bytes(zip_bytes)
    collect.require({path.name for path in bundle.iterdir()} ==
                    set((*inventory, "manifest.json", zip_path.name)),
                    "EXT-07 bundle inventory differs")
    return {"report_id": bundle.name, "source_commit": record["source_commit"],
            "manifest_sha256": collect.sha(manifest_path.read_bytes()),
            "zip_sha256": collect.sha(zip_bytes),
            "index_sha256": collect.sha(files["index.html"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(render(args.bundle, args.check), sort_keys=True))

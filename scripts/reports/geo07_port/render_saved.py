"""Validate and render the accepted GEO-07 port report solely from saved bytes."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

_collect_spec = importlib.util.spec_from_file_location(
    "csl_geo07_port_saved_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(_collect_spec)
assert _collect_spec.loader is not None
_collect_spec.loader.exec_module(collect)

REPORT_ID = "geo07-port-4dee19cde3d50259"
SOURCE = "41b4b58f2ef982e75554519862afdd803e30f717"
HARNESS = "95ba77d3fb2077ec3f56c8fe68903eb18f26488a"
CODE_PARENT = "2ccea2271e3e8d0518543e8aa20b0bbbdf3b33be"
RAW_SHA = "41649b7f4acde2c0e980b7c648358d9d217f68e3e5ec9c103f25173e7ab0d39e"
RECORDS_SHA = "e197ee1852fdb49b3b9180e0a7bfee3004cbb5bb000cf3f175f5ba22b61a5cb1"
NATIVE_MANIFEST_SHA = "27b162d9d9ac271c7eea3145a4cb75972e13f11771ff700341c8603cf9ce63a2"
HOST_SHA = "fbb1805b82ec420665e0db6a0996223d71a590d4122b55f14ff045c28a5dec69"
POST_HOST_SHA = "dff519dc043fe14cd451f919315a9eee34f00a919e979fba46be809a71548c8a"
REJECTED_RAW_SHA = "7f31a8988d36fde6846b4fbb463b797ced9f4b93796bf06e3e9db5843a7d433e"
NATIVE_FILES = frozenset({
    "build-provenance.json", "build.stderr.log", "build.stdout.log",
    "collection-status.json", "driver-description.jsonl", "driver.stderr",
    "fixture-inputs.json", "host-observation.json", "host-observation.stderr",
    "manifest.json", "process-capture.json", "records.json", "review-seal.json",
    "trials.jsonl",
})
SAVED_FILES = NATIVE_FILES | {"post-host-observation.json"}
RENDERED_FILES = frozenset({"index.html", "performance.svg", "summary.csv", "trials.csv",
                            "report-manifest.json", "bundle.zip"})


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_object(content: bytes) -> dict:
    value = json.loads(content.decode("utf-8"), object_pairs_hook=collect.strict_json_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON token")))
    require(isinstance(value, dict), "JSON object required")
    return value


def file(bundle: Path, name: str) -> Path:
    require(name in SAVED_FILES | RENDERED_FILES, "unlisted GEO-07 port report file")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked GEO-07 port file: " + name)
    return path


def validate_native(bundle: Path) -> dict:
    bundle = Path(bundle)
    require(bundle.name == REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "GEO-07 port source report identity differs")
    for name in SAVED_FILES:
        file(bundle, name)
    raw = file(bundle, "trials.jsonl").read_bytes()
    record_bytes = file(bundle, "records.json").read_bytes()
    native_manifest_bytes = file(bundle, "manifest.json").read_bytes()
    post_host_bytes = file(bundle, "post-host-observation.json").read_bytes()
    require((sha(raw), sha(record_bytes), sha(native_manifest_bytes), sha(post_host_bytes)) ==
            (RAW_SHA, RECORDS_SHA, NATIVE_MANIFEST_SHA, POST_HOST_SHA),
            "audited saved byte identity differs")
    native_manifest = json_object(native_manifest_bytes)
    require(native_manifest.get("schema") == "csl.geo07-port-manifest/1" and
            native_manifest.get("report_id") == REPORT_ID and
            set(native_manifest.get("files", {})) == NATIVE_FILES - {"manifest.json"},
            "native manifest identity or inventory differs")
    for name, digest in native_manifest["files"].items():
        require(sha(file(bundle, name).read_bytes()) == digest,
                "native manifest hash differs: " + name)
    record = json_object(record_bytes)
    require(record.get("schema") == collect.RECORD_SCHEMA and
            record.get("report_id") == REPORT_ID and
            record.get("source_commit") == SOURCE and
            record.get("harness_commit") == HARNESS and
            record.get("reviewed_code_commit") == CODE_PARENT and
            record.get("source_tree") == "54e7efa11cb55522a114d55e978f6874a8b1d251" and
            record.get("harness_tree") == "43e7485fd9b39a29a746788f271104c10b150725" and
            record.get("payload_sha256") == sha(collect.json_bytes({
                key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")})),
            "sealed record source or payload identity differs")
    timing = record["timing"]
    require(timing["scope"] == collect.INTERVAL and timing["clock"] == "steady_clock" and
            timing["unit"] == "ns" and timing["warmup_rounds"] == 1 and
            timing["measured_rounds"] == 7 and timing["batch_calls"] == 5000 and
            timing["minimum_admitted_batch_ns"] == 20_000_000 and
            timing["order"] == "alternating fixtures",
            "reviewed timing scope or profile differs")
    rows, summary = collect.admit_raw(raw, repetitions=7, batch=5000)
    require(record["rows"] == rows and record["summary"] == summary and
            len(rows) == 24 and all(row["status"] == "passed" for row in rows),
            "saved rows or summary differ from literal admission")
    process = json_object(file(bundle, "process-capture.json").read_bytes())
    require(process.get("schema") == "csl.geo07-port-process-capture/1" and
            process["exit_code"] == 0 and process["timed_out"] is False and
            process["stdout_sha256"] == RAW_SHA and
            process["stderr_sha256"] == sha(file(bundle, "driver.stderr").read_bytes()) and
            file(bundle, "driver.stderr").read_bytes() == b"" and
            process["host_observation_sha256"] == HOST_SHA and
            process["collection_start_utc"] == record["collection_start_utc"] and
            process["collection_end_utc"] == record["collection_end_utc"] and
            record["process"] == {"exit_code": 0, "raw_sha256": RAW_SHA,
                                  "stderr_sha256": process["stderr_sha256"]},
            "native process or collection window differs")
    input_bytes, input_hashes = collect.admit_description(file(bundle, "driver-description.jsonl").read_bytes())
    require(file(bundle, "fixture-inputs.json").read_bytes() == input_bytes and
            record["inputs"]["fixtures"] == collect.INPUTS and
            record["inputs"]["fixture_sha256"] == input_hashes and
            record["inputs"]["canonical_bytes_sha256"] == sha(input_bytes) and
            record["inputs"]["driver_description_sha256"] ==
            sha(file(bundle, "driver-description.jsonl").read_bytes()),
            "authored fixture or driver description differs")
    host_bytes = file(bundle, "host-observation.json").read_bytes()
    host = json_object(host_bytes)
    post_host = json_object(post_host_bytes)
    start = datetime.fromisoformat(record["collection_start_utc"])
    end = datetime.fromisoformat(record["collection_end_utc"])
    post = datetime.fromisoformat(post_host["observed_utc"])
    require(sha(host_bytes) == HOST_SHA and
            record["environment"]["host_observation_sha256"] == HOST_SHA and
            record["environment"]["host_observation"] == host and
            host["schema"] == collect.HOST_SCHEMA and
            post_host["schema"] == collect.HOST_SCHEMA and
            start < end < post <= end + timedelta(seconds=30) and
            post_host["cpu_load_percent"] == 0 and
            post_host["logical_processors"] == 12 and
            post_host["build_processes"] == {"cmake": 0, "MSBuild": 0, "cl": 0},
            "collector or independent post-host observation differs")
    provenance_bytes = file(bundle, "build-provenance.json").read_bytes()
    provenance = json_object(provenance_bytes)
    require(record["build_provenance_sha256"] == sha(provenance_bytes) and
            provenance["schema"] == "csl.geo07-port-build-provenance/1" and
            provenance["source_commit"] == SOURCE and provenance["harness_commit"] == HARNESS and
            provenance["configuration"] == "Release" and
            provenance["settings"] == collect.RELEASE_FLAGS and
            provenance["compiler_version"] == "19.44.35215.0" and
            provenance["build_stdout_sha256"] == sha(file(bundle, "build.stdout.log").read_bytes()) and
            provenance["build_stderr_sha256"] == sha(file(bundle, "build.stderr.log").read_bytes()),
            "saved Release build provenance differs")
    status = json_object(file(bundle, "collection-status.json").read_bytes())
    require(status.get("accepted_for_report_review") is True and
            status.get("publishable") is False and status.get("records_sha256") == RECORDS_SHA,
            "native admission or publication gate differs")
    require(record["performance_conclusion"].startswith("exploratory single-adapter") and
            record["environment"]["observed_native_threads"] is None and
            record["inputs"]["representation_claim"].startswith("equivalent real-set"),
            "performance or numerical assurance limit differs")
    return record


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def figure(record: dict) -> bytes:
    colors = {"affine_box": "#216c98", "constrained_disjoint_sum": "#aa542c",
              "finite_v": "#4c7848"}
    names = {"affine_box": "Affine box image", "constrained_disjoint_sum": "Constrained disjoint sum",
             "finite_v": "Bounded V conversion"}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="440" '
             'viewBox="0 0 960 440" role="img" '
             'aria-label="Seven measured verified batches per GEO-07 port fixture in milliseconds; common zero to one hundred millisecond scale">',
             '<rect width="960" height="440" fill="#ffffff"/>',
             '<text x="60" y="30" fill="#183344" font-size="20" font-family="system-ui,sans-serif">Verified batch observations</text>']
    for ms in (0, 20, 40, 60, 80, 100):
        y = 360 - ms * 3
        parts.append(f'<line x1="96" y1="{y}" x2="834" y2="{y}" stroke="#d9e4e9"/>')
        parts.append(f'<text x="42" y="{y + 5}" fill="#536875" font-size="14" font-family="system-ui,sans-serif">{ms}</text>')
    for index in range(7):
        x = 125 + index * 112
        parts.append(f'<text x="{x - 5}" y="386" fill="#536875" font-size="14" font-family="system-ui,sans-serif">{index + 1}</text>')
    parts.append('<text x="370" y="415" fill="#536875" font-size="14" font-family="system-ui,sans-serif">Measured round</text>')
    parts.append('<text x="12" y="220" fill="#536875" font-size="14" font-family="system-ui,sans-serif" transform="rotate(-90 12 220)">Batch duration (ms)</text>')
    for name in collect.EXPECTED:
        values = [row["elapsed_ns"] / 1_000_000 for row in record["rows"]
                  if row["fixture"] == name and not row["warmup"]]
        require(len(values) == 7 and all(0 <= value <= 100 for value in values),
                "seven measured plottable batches required")
        points = [(125 + index * 112, 360 - value * 3) for index, value in enumerate(values)]
        color = colors[name]
        parts.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in points) +
                     f'" fill="none" stroke="{color}" stroke-width="3"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')
    for index, name in enumerate(collect.EXPECTED):
        x = 120 + index * 260
        parts.append(f'<line x1="{x}" y1="52" x2="{x + 30}" y2="52" stroke="{colors[name]}" stroke-width="4"/>')
        parts.append(f'<text x="{x + 38}" y="57" fill="#183344" font-size="14" font-family="system-ui,sans-serif">{escape(names[name])}</text>')
    parts.append('</svg>\n')
    return "".join(parts).encode("utf-8")


def page(record: dict, svg: bytes) -> bytes:
    outcomes = (
        ("Affine image", "2 ≤ x ≤ 12", "center 7; generators [2, 3]; factor IDs horizontal, vertical",
         "four feasible physical witnesses and two outside points"),
        ("Constrained disjoint-ID Minkowski sum", "1 ≤ x ≤ 7",
         "center 4; generators [1, 0, 0, 2]; factor IDs u, v, p, q; equalities u = v and p = −q",
         "three feasible physical witnesses and two outside points"),
        ("Bounded zonotope to V conversion", "2 ≤ x ≤ 12; V = {2, 6, 8, 12}",
         "vertices 2, 6, 8, 12; zero rays; coordinate label x",
         "all four vertices and two outside points"),
    )
    outcome_rows = "".join(
        "<tr><th scope=\"row\">" + escape(label) + "</th><td>" + escape(expected) +
        "</td><td>" + escape(observed) + "</td><td>" + escape(checks) + "</td></tr>"
        for label, expected, observed, checks in outcomes)
    labels = {"affine_box": "Affine box image", "constrained_disjoint_sum": "Constrained disjoint sum",
              "finite_v": "Bounded V conversion"}
    summary_rows = "".join(
        f'<tr><th scope="row">{escape(labels[name])}</th><td>5,000</td><td>7/7</td>'
        f'<td>{record["summary"][name]["median_batch_ns"] / 1_000_000:.3f}</td>'
        f'<td>{record["summary"][name]["min_batch_ns"] / 1_000_000:.3f}–'
        f'{record["summary"][name]["max_batch_ns"] / 1_000_000:.3f}</td></tr>'
        for name in collect.EXPECTED)
    downloads = tuple(sorted(SAVED_FILES | {"trials.csv", "summary.csv", "performance.svg", "report-manifest.json"}))
    download_links = "".join('<li><a href="' + name + '">' + escape(name) + '</a></li>' for name in downloads)
    env = record["environment"]
    html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GEO-07 registered generator ports · saved report</title>'
        '<style>:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f8fa;color:#193340;font:16px/1.55 system-ui,sans-serif}'
        '.header{background:#12394d;color:#fff;padding:2.6rem max(1.25rem,calc((100vw - 1040px)/2))}'
        '.header p{max-width:870px;color:#cde1ea}.main{max-width:1040px;margin:auto;padding:1.5rem 1.25rem 3rem}'
        'h1{font-size:clamp(2rem,4vw,3rem);line-height:1.1;margin:.2rem 0 1rem}h2{margin:0 0 .8rem;line-height:1.25}'
        '.eyebrow{font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:#a9d4e5}'
        '.card{background:white;border:1px solid #d5e3e9;border-radius:12px;padding:1.35rem;margin:1.1rem 0;box-shadow:0 4px 14px #12394d0a}'
        '.callout{border-left:4px solid #21749d;padding:.2rem 1rem;background:#e9f3f7}.table-wrap{overflow-x:auto}'
        'table{border-collapse:collapse;width:100%;min-width:690px;margin:.6rem 0}th,td{padding:.65rem .75rem;border-bottom:1px solid #dce7eb;text-align:left;vertical-align:top}'
        'thead th{background:#edf4f7}tbody th{font-weight:650}caption{text-align:left;font-weight:650;margin:.35rem 0}'
        'figure{margin:1.2rem 0;overflow-x:auto}.plot{display:block;width:100%;min-width:680px;height:auto;background:#fff;border:1px solid #dce7eb;border-radius:8px}'
        '.downloads{columns:2;overflow-wrap:anywhere}code{overflow-wrap:anywhere}a{color:#0d608b}a:hover{text-decoration-thickness:2px}'
        '.scroll-hint{font-size:.88rem;color:#536875}'
        '@media(max-width:650px){.downloads{columns:1}.header{padding:2rem 1.25rem}}'
        '</style></head><body><div class="header"><div class="eyebrow">Saved algorithm result · GEO-07</div>'
        '<h1>Registered generator geometry ports</h1>'
        '<p>Three bounded public adapter examples: affine image, constrained disjoint-ID Minkowski sum, and capped zonotope-to-V conversion. '
        'The representation algebra is equivalent over real sets; coefficient evaluation uses binary64 and has no validated rounding enclosure.</p>'
        '</div><div class="main"><div class="card"><h2>Numerical outcomes</h2>'
        '<p class="scroll-hint">On narrow screens, scroll tables and the chart horizontally to see all values.</p>'
        '<div class="table-wrap"><table><caption>Literal independent H/V references and observed public outputs</caption>'
        '<thead><tr><th>Fixture</th><th>Expected physical set</th><th>Observed output</th><th>Checked examples</th></tr></thead><tbody>' +
        outcome_rows + '</tbody></table></div>'
        '<p>Every fresh call checked factor IDs, coefficients and equality rows where applicable, feasible witnesses against physical H, '
        'outside points, V vertices, and scoped rejection controls. The requested relation was equivalent with numerical assurance and no error bound. '
        'These examples do not establish general geometric correctness, constrained conversion, intersection, overlapping-ID independent sums, or validated arithmetic.</p></div>'
        '<div class="card"><h2>Measured verified batches</h2>'
        '<p>One excluded warmup and seven measured batches per fixture in alternating order. Each batch made 5,000 fresh registered-port calls; '
        'all 24 warmup and measured batches passed literal checks with zero observed failures. The 20 ms admission floor was met in every batch.</p>'
        '<div class="table-wrap"><table><caption>Seven measured batches per fixture; milliseconds</caption>'
        '<thead><tr><th>Fixture</th><th>Calls per batch</th><th>Successful batches</th><th>Median ms</th><th>Range ms</th></tr></thead><tbody>' +
        summary_rows + '</tbody></table></div>'
        '<figure>' + svg.decode("utf-8").replace('<svg ', '<svg class="plot" ', 1) +
        '<figcaption>Each point is a verified batch, with a shared vertical scale. Warmups are excluded.</figcaption></figure>'
        '<p class="callout">Performance interpretation is exploratory and inconclusive. There is no comparator, speedup, source-mapped limiter profile, '
        'application-scale workload, or throughput claim. These are verified-batch times, not isolated operation or per-call latency.</p>'
        '<p>The <code>steady_clock</code> interval includes fresh generator handles, public provider registration and preparation, workspace execution, '
        'literal H/V and factor checks, rejection controls, and per-call nlohmann JSON result construction and assignment. Process startup, JSONL '
        'serialization, saved-row validation, persistence, rendering and deployment are outside the interval. Internal phase counters and observed native '
        'thread count are unavailable.</p></div>'
        '<div class="card"><h2>Source and host evidence</h2><p>Algorithm source <code>' + SOURCE +
        '</code>; reviewed harness <code>' + HARNESS + '</code>; saved report <code>' + REPORT_ID +
        '</code>. Raw trials SHA-256 <code>' + RAW_SHA + '</code>; records SHA-256 <code>' + RECORDS_SHA +
        '</code>; native manifest SHA-256 <code>' + NATIVE_MANIFEST_SHA + '</code>. The later publication commit is a separate identity.</p>'
        '<p>MSVC 19.44.35215.0, x64 C++20 Release <code>/O2 /Ob2 /DNDEBUG</code>. Host: ' +
        escape(str(env["os"])) + ', ' + str(env["logical_processors"]) + ' logical processors. '
        'The collector observed CPU 0% and no <code>cmake</code>, <code>MSBuild</code> or <code>cl</code> processes just before measurement. '
        'The separate post-run observation also recorded CPU 0% and zero such processes; its exact-byte SHA-256 is <code>' + POST_HOST_SHA +
        '</code>. One sequential driver worker was requested; observed native thread count is unavailable.</p>'
        '<p>Collection ran from <code>' + escape(record["collection_start_utc"]) + '</code> to <code>' +
        escape(record["collection_end_utc"]) + '</code>. Earlier collection-001 is excluded: its 1,000-call batches were below the 20 ms floor, '
        'although all literal rows passed. Its raw SHA-256 is <code>' + REJECTED_RAW_SHA +
        '</code>; those rejected bytes are preserved outside this published bundle. The accepted native collection status records report-review acceptance and '
        'the publication gate then pending.</p></div>'
        '<div class="card"><h2>Download and audit</h2><p>Saved inputs, description, trial events, build/probe evidence and rendered tables are available as individual files.</p>'
        '<div class="downloads"><ul>' + download_links + '</ul></div></div></div></body></html>\n')
    return html.encode("utf-8")


def generated(record: dict) -> dict[str, bytes]:
    trials = [{key: row[key] for key in ("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status")}
              for row in record["rows"]]
    summary = [{"fixture": name, "batch": 5000, **record["summary"][name]} for name in collect.EXPECTED]
    svg = figure(record)
    return {"index.html": page(record, svg), "performance.svg": svg,
            "trials.csv": csv_bytes(("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status"), trials),
            "summary.csv": csv_bytes(("fixture", "batch", "attempts", "successes", "failures", "median_batch_ns",
                                      "min_batch_ns", "max_batch_ns"), summary)}


def render_manifest(bundle: Path, assets: dict[str, bytes]) -> bytes:
    hashes = {name: sha(file(bundle, name).read_bytes()) for name in SAVED_FILES}
    hashes.update({name: sha(content) for name, content in assets.items()})
    return collect.json_bytes({"schema": "csl.geo07-port-render-manifest/1", "report_id": REPORT_ID,
                               "source_commit": SOURCE, "harness_commit": HARNESS,
                               "post_host_sha256": POST_HOST_SHA, "files": hashes})


def offline_zip(bundle: Path, assets: dict[str, bytes], report_manifest: bytes) -> bytes:
    files = {name: file(bundle, name).read_bytes() for name in SAVED_FILES}
    files.update(assets)
    files["report-manifest.json"] = report_manifest
    landing = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
               '<title>Offline GEO-07 port report</title></head><body>'
               '<h1>Offline GEO-07 port report</h1><a href="' + REPORT_ID +
               '/index.html">Open saved registered-port report</a></body></html>\n').encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        entries = [("index.html", landing)] + [(REPORT_ID + "/" + name, files[name]) for name in sorted(files)]
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def render(bundle: Path, *, check: bool) -> None:
    bundle = Path(bundle)
    record = validate_native(bundle)
    assets = generated(record)
    report_manifest = render_manifest(bundle, assets)
    archive = offline_zip(bundle, assets, report_manifest)
    expected = assets | {"report-manifest.json": report_manifest, "bundle.zip": archive}
    inventory = {path.name for path in bundle.iterdir() if path.is_file()}
    require(all(not path.is_symlink() for path in bundle.iterdir()) and
            (inventory == SAVED_FILES | RENDERED_FILES if check else
             inventory in (SAVED_FILES, SAVED_FILES | RENDERED_FILES)),
            "source/rendered report inventory differs")
    if check:
        for name, content in expected.items():
            require(file(bundle, name).read_bytes() == content,
                    "rendered report differs from saved evidence: " + name)
    else:
        for name, content in expected.items():
            (bundle / name).write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, check=args.check)
    print("checked" if args.check else "rendered", args.bundle)


if __name__ == "__main__":
    main()

"""Validate and render the saved finite-feedback report without native execution."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

_spec = importlib.util.spec_from_file_location("finite_feedback_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(collect)

RAW_FILES = frozenset(set(collect.RAW) | {"build-graph.json", "source-tree.txt",
                                          "records.json", "trials.jsonl", "manifest.json"})
RENDERED_FILES = frozenset({"index.html", "performance.svg", "summary.csv", "trials.csv",
                            "report-manifest.json", "bundle.zip"})
SUMMARY_FIELDS = ("scenario", "attempts", "matches", "failures", "median_ns", "min_ns", "max_ns")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "saved bundle missing or linked")
    for name in RAW_FILES:
        collect.require((bundle / name).is_file() and not (bundle / name).is_symlink(),
                        "missing or linked saved file: " + name)
    manifest = collect.read_json(bundle / "manifest.json")
    collect.require(manifest.get("schema") == "csl.finite-feedback-source-manifest/2" and
                    set(manifest.get("files", {})) == RAW_FILES - {"manifest.json"},
                    "source inventory differs")
    for name, digest in manifest["files"].items():
        collect.require(collect.sha((bundle / name).read_bytes()) == digest,
                        "source file hash differs: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("harness_commit") == record.get("numerical_source_commit") == collect.NUMERICAL_SOURCE and
                    record.get("payload_sha256") == collect.sha(collect.encoded(unsigned)) and
                    record.get("report_id") == "finite-feedback-" + record["payload_sha256"][:16] and
                    manifest["report_id"] == record["report_id"] == bundle.name,
                    "saved record identity differs")
    capture = collect.read_json(bundle / "capture-status.json")
    pre = collect.read_json(bundle / "prebuild-receipt.json")
    post = collect.read_json(bundle / "postrun-receipt.json")
    collect.require(capture["state"] == "captured" and capture["failure"] is None and
                    capture["return_codes"] == {"configure": 0, "build": 0, "smoke": 0, "measure": 0} and
                    capture["prebuild"] == pre and capture["postrun"] == post and
                    pre["commit"] == post["commit"] == record["source_commit"] and
                    pre["tree"] == post["tree"] == record["source_tree"] and
                    pre["status_sha256"] == post["status_sha256"] == collect.EMPTY_SHA and
                    capture["executable_sha256_before"] == capture["executable_sha256_after"] ==
                    record["executable_sha256"] and
                    collect.sha((bundle / "prebuild-receipt.json").read_bytes()) == record["prebuild_receipt_sha256"] and
                    collect.sha((bundle / "postrun-receipt.json").read_bytes()) == record["postrun_receipt_sha256"] and
                    collect.sha((bundle / "source-tree.txt").read_bytes()) == record["source_inventory_sha256"],
                    "saved clean-tree/executable ownership differs")
    graph = collect.read_json(bundle / "build-graph.json")
    collect.require(collect.sha(collect.encoded(graph)) == record["build_graph_sha256"] and
                    graph["configuration"] == "Release" and
                    graph["schema"] == "csl.finite-feedback-build-graph/2" and
                    graph["source_root"] == "SOURCE_ROOT" and graph["build_root"] == "BUILD_ROOT" and
                    graph["selected_artifact"] == "Release/csl_finite_feedback_report.exe",
                    "saved build graph differs")
    report_target = graph["targets"]["csl_finite_feedback_report"]
    collect.require(report_target["sources"] == ["benchmarks/reporting/finite_feedback/driver.cpp"] and
                    {"csl_finite_feedback_port", "csl_finite_feedback"} <= set(graph["targets"]) and
                    graph["compiler"]["version"] == record["environment"]["compiler"]["version"],
                    "linked source/compiler graph differs")
    inventory = {line.split(b"\t", 1)[1].decode() for line in
                 (bundle / "source-tree.txt").read_bytes().splitlines()}
    collect.require(len(inventory) == pre["tracked_count"] and
                    all(source in inventory for target in graph["targets"].values()
                        for source in target["sources"] if not source.startswith("build/")),
                    "linked sources absent from complete tree inventory")
    smoke = collect.rows((bundle / "smoke.stdout.log").read_bytes(), "smoke")
    attempts = collect.rows((bundle / "measure.stdout.log").read_bytes(), "measure")
    collect.require(collect.sha((bundle / "measure.stdout.log").read_bytes()) ==
                    record["raw_csv_sha256"] and attempts == record["trials"] and
                    collect.summarize([row for row in attempts if row["purpose"] == "trial"]) ==
                    record["summary"] and len(smoke) == 4,
                    "saved raw rows or summary differ")
    jsonl = b"".join(collect.encoded(row) for row in attempts)
    collect.require((bundle / "trials.jsonl").read_bytes() == jsonl and
                    (bundle / "smoke.stderr.log").read_bytes() == b"" and
                    (bundle / "measure.stderr.log").read_bytes() == b"" and
                    record["work"] == {"smoke_calls": 4, "warmup_calls": 4,
                                       "measured_registered_calls": 28, "matched": 28,
                                       "failed": 0, "unsupported": 0, "cancelled": 0, "missing": 0},
                    "saved work or error count differs")
    return record


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def generated(record: dict) -> dict[str, bytes]:
    trials = [row for row in record["trials"] if row["purpose"] == "trial"]
    summary = record["summary"]
    colors = ("#1565c0", "#00897b", "#7b1fa2", "#d97706")
    bars = []
    for index, row in enumerate(summary):
        y = 45 + 62 * index
        lo, hi, mid = (row[key] / 7000 * 580 for key in ("min_ns", "max_ns", "median_ns"))
        bars.append(f'<text x="10" y="{y+12}" font-size="14">{escape(row["scenario"])}</text>'
                    f'<line x1="{190+lo:.1f}" x2="{190+hi:.1f}" y1="{y}" y2="{y}" stroke="{colors[index]}" stroke-width="8"/>'
                    f'<circle cx="{190+mid:.1f}" cy="{y}" r="7" fill="{colors[index]}"/>'
                    f'<text x="790" y="{y+5}" font-size="13">{row["median_ns"]} ns ({row["min_ns"]}–{row["max_ns"]})</text>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 315" role="img" '
           'aria-label="Seven measured verified registered calls per fixture, median and range">'
           '<rect width="1100" height="315" fill="white"/><text x="10" y="295" font-size="13">'
           'Exploratory single-adapter verified public-call latency; medians are circles, ranges are bars (ns).</text>'
           + ''.join(bars) + '</svg>\n').encode()
    body_rows = ''.join('<tr><th>' + escape(row["scenario"]) + '</th><td>7</td><td>0</td><td>' +
                        str(row["median_ns"]) + '</td><td>' + str(row["min_ns"]) + '</td><td>' +
                        str(row["max_ns"]) + '</td></tr>' for row in summary)
    expected = ''.join('<tr><th>' + escape(name) + '</th><td>' + escape(values[0]) +
                       '</td><td>' + escape(values[1]) + '</td><td>' + escape(values[2]) +
                       '</td></tr>' for name, values in collect.CASES.items())
    host = record["environment"]["host_pre"]
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>Finite feedback registered-port results</title>'
            '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:70rem;box-sizing:border-box;'
            'margin:auto;padding:1rem;color:#172033}'
            'table{border-collapse:collapse;display:block;max-width:100%;overflow-x:auto}'
            'th,td{border:1px solid #b7c2ce;padding:.45rem;text-align:left}'
            'th{background:#eef3f8}code{overflow-wrap:anywhere}img{max-width:100%}</style></head><body>'
            '<h1>Finite feedback: verified registered-port calls</h1><p><strong>Verdict:</strong> '
            'inconclusive exploratory single-adapter timings. No comparator or speedup is claimed.</p>'
            '<p>Clean build source commit <code>' + escape(record["source_commit"]) + '</code>; '
            'unchanged numerical source and driver <code>' + escape(record["harness_commit"]) + '</code>; '
            'saved report <code>' + escape(record["report_id"]) + '</code>; executable SHA-256 '
            '<code>' + escape(record["executable_sha256"]) + '</code>.</p>'
            '<h2>Literal finite games and policy outputs</h2><table><thead><tr><th>Game</th>'
            '<th>Initial winning</th><th>Initial action indices</th><th>Observed branch actions</th>'
            '</tr></thead><tbody>' + expected + '</tbody></table>'
            '<p>Whole-successor clipping, observed-state branching, empty actions, and nominal single-disturbance '
            'cases use exact authored transition tables. The frozen driver compares <strong>all winning flags</strong> '
            'and only these admissible-action cells: stage 0/state 0 in every game, plus stage 1/states 1 and 2 '
            'in branching. Other action-tensor cells are not independently checked by this report driver. '
            'The branching row checks distinct later actions after states 1 and 2 are observed.</p>'
            '<h2>Measured latency</h2><table><thead><tr><th>Game</th><th>Measured calls</th>'
            '<th>Failures</th><th>Median ns</th><th>Min ns</th><th>Max ns</th></tr></thead><tbody>'
            + body_rows + '</tbody></table><p><a href="performance.svg">Median and range figure (SVG)</a></p>'
            '<p>Four smoke calls and four warmups are excluded. Seven round-robin measured repetitions per game '
            '(28 calls total) were verified. Median and min–max range describe these repetitions; the range is '
            'not a confidence interval.</p>'
            '<h2>Interval and environment</h2><p>The steady-clock interval begins before registry construction '
            'and ends after registered execution, all-winning-flags comparison, and selected action-cell checks. It excludes '
            'fixture construction, object destruction, CSV serialization, and process startup. It is a verified '
            'public-call interval, not native-only time or application end-to-end latency.</p>'
            '<p>' + escape(host["processor"]) + '; ' + escape(host["platform"]) + '; ' +
            str(host["logical_processors"]) +
            ' logical processors; MSVC 19.44.35215.0, x64 Release /O2 /DNDEBUG /std:c++20. One requested '
            'outer worker; native OS thread count was unavailable. One process with fresh registry, prepared plan '
            'and workspace per call; caches may be warm. Concurrent work was not fully quantified.</p>'
            '<h2>Evidence limits</h2><p>Single finite-table adapter, four small authored games, one host, and '
            'one measured session. Unlisted action-tensor cells were not checked. No competitor, source-mapped limiter profile, speedup, continuous-state '
            'disturbance enclosure, partial observation, physical-model correspondence, or global causal minimax '
            'claim. Internal phase and native-only counters were unavailable.</p>'
            '<h2>Saved evidence</h2><ul><li><a href="records.json">Versioned raw JSON</a></li>'
            '<li><a href="measure.stdout.log">Raw driver CSV</a></li>'
            '<li><a href="trials.jsonl">Trial JSONL</a></li><li><a href="trials.csv">Measured trial CSV</a></li>'
            '<li><a href="summary.csv">Summary CSV</a></li><li><a href="build-graph.json">Release target graph</a></li>'
            '<li><a href="source-tree.txt">Complete Git tree inventory</a></li>'
            '<li><a href="prebuild-receipt.json">Prebuild clean receipt</a></li>'
            '<li><a href="postrun-receipt.json">Postrun clean receipt</a></li>'
            '<li><a href="capture-status.json">Build and run capture</a></li>'
            '<li><a href="manifest.json">Source manifest</a></li><li><a href="report-manifest.json">Report manifest</a></li>'
            '<li><a href="bundle.zip">Offline ZIP</a></li></ul></body></html>\n').encode()
    return {"index.html": html, "performance.svg": svg,
            "trials.csv": csv_bytes(collect.FIELDS, trials),
            "summary.csv": csv_bytes(SUMMARY_FIELDS, summary)}


def bundle_zip(bundle: Path, files: dict[str, bytes]) -> bytes:
    landing = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline finite feedback report</title>'
               '<p><a href="' + escape(bundle.name, quote=True) + '/index.html">Open saved report</a></p></html>\n').encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [("index.html", landing)] + [(bundle.name + "/" + key, files[key]) for key in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue()


def render(bundle: Path, check: bool = False) -> dict:
    record = validate(bundle)
    files = generated(record)
    manifest = {"schema": "csl.finite-feedback-report-manifest/1", "report_id": bundle.name,
                "files": {name: collect.sha((bundle / name).read_bytes()) for name in sorted(RAW_FILES)}}
    manifest["files"].update({name: collect.sha(content) for name, content in files.items()})
    files["report-manifest.json"] = collect.encoded(manifest)
    files["bundle.zip"] = bundle_zip(bundle, {**{name: (bundle / name).read_bytes() for name in RAW_FILES},
                                               **{name: value for name, value in files.items() if name != "bundle.zip"}})
    collect.require({path.name for path in bundle.iterdir()} in (set(RAW_FILES), set(RAW_FILES | RENDERED_FILES)),
                    "unexpected source/report inventory")
    for name, content in files.items():
        path = bundle / name
        if check:
            collect.require(path.is_file() and not path.is_symlink() and path.read_bytes() == content,
                            "rendered file differs: " + name)
        else:
            collect.require(not path.exists(), "refusing to overwrite: " + name)
            path.write_bytes(content)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(render(args.bundle, check=args.check)["report_id"])


if __name__ == "__main__":
    main()

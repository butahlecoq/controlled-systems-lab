"""Validate and render the accepted GEO-07 report solely from saved bytes."""
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
    "csl_geo07_saved_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(_collect_spec)
assert _collect_spec.loader is not None
_collect_spec.loader.exec_module(collect)

REPORT_ID = "geo07-9ef0d347291774da"
SOURCE = "db7906cb33ca40da55e31b9bf6b21cf7ffcc1ee4"
HARNESS = "580da5368aac21b14d9e817da5937b4494a905aa"
RAW_SHA = "768dae54cb5aabcec1445a2703df4ae45ed26145de7f52a012307b8d267dfd36"
RECORDS_SHA = "4dc756380e87bd4e9342f55777bb2adb9a9aaeba62e9e142fb656d60d393d7c6"
NATIVE_MANIFEST_SHA = "be4c075afa202348e35d800fcca3413f4501f58ce4faefde7cff2d394344366d"
SOURCE_FILES = frozenset({"build-provenance.json", "build.stderr.log", "build.stdout.log",
    "collection-status.json", "driver-description.jsonl", "driver.stderr", "fixture-inputs.json",
    "manifest.json", "process-capture.json", "records.json", "trials.jsonl"})
RENDERED_FILES = frozenset({"index.html", "performance.svg", "trials.csv", "summary.csv",
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
    require(name in SOURCE_FILES | RENDERED_FILES, "unlisted GEO-07 report file")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked GEO-07 file: " + name)
    return path


def validate_native(bundle: Path) -> dict:
    bundle = Path(bundle)
    require(bundle.name == REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "GEO-07 source report identity differs")
    for name in SOURCE_FILES:
        file(bundle, name)
    raw = file(bundle, "trials.jsonl").read_bytes()
    record_bytes = file(bundle, "records.json").read_bytes()
    manifest_bytes = file(bundle, "manifest.json").read_bytes()
    require((sha(raw), sha(record_bytes), sha(manifest_bytes)) ==
            (RAW_SHA, RECORDS_SHA, NATIVE_MANIFEST_SHA), "reviewed native byte identity differs")
    manifest = json_object(manifest_bytes)
    require(manifest.get("schema") == "csl.geo07-manifest/1" and
            manifest.get("report_id") == REPORT_ID and
            set(manifest.get("files", {})) == SOURCE_FILES - {"manifest.json"},
            "native manifest inventory differs")
    for name, digest in manifest["files"].items():
        require(sha(file(bundle, name).read_bytes()) == digest,
                "native manifest file hash differs: " + name)
    record = json_object(record_bytes)
    require(record.get("schema") == collect.RECORD_SCHEMA and
            record.get("report_id") == REPORT_ID and
            record.get("source_commit") == SOURCE and record.get("harness_commit") == HARNESS and
            record.get("payload_sha256") == sha(collect.json_bytes({
                key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")})),
            "fixed source, harness or sealed record identity differs")
    timing = record["timing"]
    require(timing["scope"] == collect.INTERVAL and timing["warmup_rounds"] == 1 and
            timing["measured_rounds"] == 7 and timing["batch_calls"] == 5000 and
            timing["minimum_admitted_batch_ns"] == 20_000_000,
            "reviewed timing interpretation differs")
    rows, summary = collect.admit_raw(raw, repetitions=7, batch=5000)
    require(record["rows"] == rows and record["summary"] == summary and
            len(rows) == 24 and all(row["status"] == "passed" for row in rows),
            "saved rows or summary differ from independent oracle")
    process = json_object(file(bundle, "process-capture.json").read_bytes())
    require(process["exit_code"] == 0 and process["timed_out"] is False and
            process["stdout_sha256"] == RAW_SHA and
            process["stderr_sha256"] == sha(file(bundle, "driver.stderr").read_bytes()) and
            file(bundle, "driver.stderr").read_bytes() == b"" and
            record["process"] == {"exit_code": 0, "raw_sha256": RAW_SHA,
                                  "stderr_sha256": process["stderr_sha256"]},
            "native process status or exact output differs")
    input_bytes, input_hashes = collect.admit_description(file(bundle, "driver-description.jsonl").read_bytes())
    require(file(bundle, "fixture-inputs.json").read_bytes() == input_bytes and
            record["inputs"]["fixtures"] == collect.INPUTS and
            record["inputs"]["fixture_sha256"] == input_hashes and
            record["inputs"]["canonical_bytes_sha256"] == sha(input_bytes) and
            record["inputs"]["driver_description_sha256"] ==
            sha(file(bundle, "driver-description.jsonl").read_bytes()),
            "authored fixture bytes or per-fixture hashes differ")
    provenance_bytes = file(bundle, "build-provenance.json").read_bytes()
    provenance = json_object(provenance_bytes)
    require(record["build_provenance_sha256"] == sha(provenance_bytes) and
            provenance["source_commit"] == SOURCE and provenance["harness_commit"] == HARNESS and
            provenance["configuration"] == "Release" and
            provenance["compiler_version"] == "19.44.35215.0" and
            provenance["build_stdout_sha256"] == sha(file(bundle, "build.stdout.log").read_bytes()) and
            provenance["build_stderr_sha256"] == sha(file(bundle, "build.stderr.log").read_bytes()),
            "saved Release provenance differs")
    status = json_object(file(bundle, "collection-status.json").read_bytes())
    require(status.get("accepted_for_report_review") is True and status.get("publishable") is False and
            status.get("records_sha256") == RECORDS_SHA,
            "collection admission or publication gate differs")
    require(record["performance_conclusion"].startswith("exploratory single-adapter") and
            record["environment"]["observed_native_threads"] is None,
            "performance or unavailable counter scope differs")
    return record


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def figure(record: dict) -> bytes:
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="680" height="385" '
             'viewBox="0 0 680 385" role="img" '
             'aria-label="Seven verified batch observations for each GEO-07 fixture in milliseconds">']
    colors = {"box_image": "#245c83", "shared_cancellation": "#9a5127",
              "constrained_sum": "#527246"}
    for panel, name in enumerate(collect.EXPECTED):
        values = [row["elapsed_ns"] / 1_000_000 for row in record["rows"]
                  if row["fixture"] == name and not row["warmup"]]
        require(len(values) == 7, "seven plotted GEO-07 observations required")
        low, high = min(values), max(values)
        spread = max(high - low, 0.1)
        top = 18 + panel * 120
        points = [(190 + index * 70, top + 78 - 65 * (value - low) / spread)
                  for index, value in enumerate(values)]
        label = name.replace("_", " ")
        parts.append(f'<text x="8" y="{top + 42}" font-size="16">{escape(label)}</text>')
        parts.append(f'<line x1="180" y1="{top + 80}" x2="620" y2="{top + 80}" stroke="#bac8d0"/>')
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" '
                     f'fill="none" stroke="{colors[name]}" stroke-width="2"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[name]}"/>')
        parts.append(f'<text x="630" y="{top + 18}" font-size="12">{high:.2f} ms</text>')
        parts.append(f'<text x="630" y="{top + 80}" font-size="12">{low:.2f} ms</text>')
    parts.append('<text x="335" y="381" font-size="13">Measured round 1–7 (within each fixture)</text></svg>\n')
    return "".join(parts).encode("utf-8")


def page(record: dict, svg: bytes) -> bytes:
    summary_rows = "".join(
        '<tr><th scope="row">' + escape(name.replace("_", " ")) + '</th><td>5,000</td><td>7/7</td>'
        '<td>' + f'{record["summary"][name]["median_batch_ns"]/1_000_000:.3f}' + '</td><td>' +
        f'{record["summary"][name]["min_batch_ns"]/1_000_000:.3f}–'
        f'{record["summary"][name]["max_batch_ns"]/1_000_000:.3f}' + '</td></tr>'
        for name in collect.EXPECTED)
    outcomes = {
        "box_image": ("Affine image of a two-factor box", "Physical H: 2 ≤ x ≤ 12", "center 7; generator columns [2, 3]; factor IDs horizontal, vertical"),
        "shared_cancellation": ("Correlated cancellation", "Physical H: x = 0", "center 0; shared history.0 column cancels to 0"),
        "constrained_sum": ("Dependent sum with two distinct equalities", "Physical H: x = 0, y = 0", "center [0, 0]; factor IDs u, v, w; two joined equalities"),
    }
    outcome_rows = "".join('<tr><th scope="row">' + escape(label) + '</th><td>' +
                           escape(expected) + '</td><td>' + escape(observed) +
                           '</td><td>8/8 verified batches, including one excluded warmup</td></tr>'
                           for name, (label, expected, observed) in outcomes.items())
    downloads = ("records.json", "trials.jsonl", "trials.csv", "summary.csv", "fixture-inputs.json",
                 "driver-description.jsonl", "build-provenance.json", "build.stdout.log", "build.stderr.log",
                 "process-capture.json", "driver.stderr", "manifest.json", "report-manifest.json",
                 "performance.svg")
    links = "".join('<li><a href="' + name + '">' + escape(name) + '</a></li>' for name in downloads)
    env = record["environment"]
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GEO-07 generator-set report</title>'
        '<style>body{font:16px system-ui,sans-serif;max-width:940px;margin:2rem auto;padding:0 1rem;color:#1c2a35;line-height:1.45}'
        'h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;margin:1rem 0}'
        'th,td{border:1px solid #bac8d0;padding:.55rem;text-align:left;vertical-align:top}'
        'th{background:#eaf0f4}code{overflow-wrap:anywhere}figure{margin:1.5rem 0}'
        'svg{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '</head><body><h1>GEO-07 generator-set operations</h1>'
        '<p>Single-adapter, fixed-source evidence for an affine image, a correlated cancellation, '
        'and a constrained dependent sum. Representation algebra preserves shared factor identity. '
        'Coefficient evaluation is binary64 with no validated rounding enclosure.</p>'
        '<h2>Numerical outcomes and literal oracle</h2>'
        '<table><caption>Authored physical H references and observed generator outputs</caption>'
        '<thead><tr><th>Fixture</th><th>Expected physical relation</th><th>Observed output</th>'
        '<th>Evidence</th></tr></thead><tbody>' + outcome_rows + '</tbody></table>'
        '<p>Every fresh call checks feasible factor witnesses against the literal physical H relation, '
        'separate outside points, factor IDs and coefficients. The constrained case retains two '
        'distinct equality systems. An infeasible factor tuple may map inside a noninjective physical '
        'image; no false feasibility equivalence is asserted. Residual vectors are unavailable from '
        'this public API. These are three bounded examples, not a general correctness or complete-family proof.</p>'
        '<h2>Saved Release batch observations</h2><p>One excluded warmup and seven measured batches '
        'per fixture, in alternating order; 5,000 freshly constructed, fully checked calls per batch. '
        'All 24 warmup and measured batches passed; there were zero observed failures. Values are '
        'verified-batch milliseconds, not isolated operation or per-call latency. The measured '
        'interval includes public construction and operations, the independent-sum rejection control, '
        'factor lift, literal H/identity/coefficient checks, and per-call nlohmann JSON result '
        'construction and assignment. It excludes process startup, JSONL serialization, saved-row '
        'verification, persistence and rendering.</p>'
        '<table><caption>Seven measured batches per fixture, milliseconds</caption><thead><tr>'
        '<th>Fixture</th><th>Calls/batch</th><th>Successful batches</th><th>Median ms</th>'
        '<th>Range ms</th></tr></thead><tbody>' + summary_rows + '</tbody></table>'
        '<figure aria-label="Within-fixture verified batch variation">' + svg.decode("utf-8") +
        '<figcaption>Each line shows seven batches of one fixture. Vertical scales are local to the '
        'fixture; the figure does not compare methods or imply a speedup.</figcaption></figure>'
        '<p>Performance interpretation is exploratory and inconclusive. There is no comparator, '
        'source-mapped limiter profile, application-scale workload, or throughput/scalability claim. '
        'Internal phase timings and measured native thread count are unavailable.</p>'
        '<h2>Provenance and limits</h2><p>Algorithm source <code>' + SOURCE +
        '</code>; reviewed harness <code>' + HARNESS + '</code>; saved artifact <code>' + REPORT_ID +
        '</code>; raw JSONL SHA-256 <code>' + RAW_SHA + '</code>; records SHA-256 <code>' +
        RECORDS_SHA + '</code>; native manifest SHA-256 <code>' + NATIVE_MANIFEST_SHA +
        '</code>. The artifact Git commit is the '
        'repository revision carrying these files and is separate from source and harness commits.</p>'
        '<p>MSVC 19.44.35215.0, C++20 x64 Release /O2 /Ob2 /DNDEBUG. Host: ' +
        escape(str(env["os"])) + '; ' + str(env["logical_processors"]) +
        ' logical processors. One sequential driver was requested; observed native thread count '
        'is unavailable. The saved concurrent-work note says: ' +
        escape(str(env["concurrent_work_note"])) + '</p>'
        '<p>Source fixture payloads and per-fixture hashes, the exact raw driver description, '
        'Release compiler/link settings, process status and raw trial bytes are downloadable below. '
        'The earlier collection-001 failed the provenance parser and is excluded from this report. '
        'The accepted collection-002 used the reviewed CRLF parser fix. Its collection-status file '
        'records acceptance for report review and a then-pending publication gate.</p>'
        '<h2>Download and audit</h2><ul>' + links + '</ul></body></html>\n')
    return html.encode("utf-8")


def generated(record: dict) -> dict[str, bytes]:
    trials = [{key: row[key] for key in ("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status")}
              for row in record["rows"]]
    summary = [{"fixture": name, "batch": 5000, **record["summary"][name]} for name in collect.EXPECTED]
    figure_bytes = figure(record)
    return {"index.html": page(record, figure_bytes), "performance.svg": figure_bytes,
            "trials.csv": csv_bytes(("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status"), trials),
            "summary.csv": csv_bytes(("fixture", "batch", "attempts", "successes", "failures", "median_batch_ns",
                                      "min_batch_ns", "max_batch_ns"), summary)}


def render_manifest(bundle: Path, assets: dict[str, bytes]) -> bytes:
    hashes = {name: sha(file(bundle, name).read_bytes()) for name in SOURCE_FILES}
    hashes.update({name: sha(content) for name, content in assets.items()})
    return collect.json_bytes({"schema": "csl.geo07-render-manifest/1", "report_id": REPORT_ID,
                               "source_commit": SOURCE, "harness_commit": HARNESS,
                               "files": hashes})


def offline_zip(bundle: Path, assets: dict[str, bytes], report_manifest: bytes) -> bytes:
    files = {name: file(bundle, name).read_bytes() for name in SOURCE_FILES}
    files.update(assets)
    files["report-manifest.json"] = report_manifest
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        root = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline GEO-07 report</title>'
                f'<h1>Offline GEO-07 report</h1><a href="{REPORT_ID}/index.html">Open saved report</a></html>\n').encode()
        for name, content in [("index.html", root)] + [(REPORT_ID + "/" + name, files[name]) for name in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def render(bundle: Path, *, check: bool) -> None:
    bundle = Path(bundle)
    record = validate_native(bundle)
    assets = generated(record)
    manifest = render_manifest(bundle, assets)
    archive = offline_zip(bundle, assets, manifest)
    expected = assets | {"report-manifest.json": manifest, "bundle.zip": archive}
    inventory = {path.name for path in bundle.iterdir() if path.is_file()}
    require(all(not path.is_symlink() for path in bundle.iterdir()) and
            (inventory == SOURCE_FILES | RENDERED_FILES if check else
             inventory in (SOURCE_FILES, SOURCE_FILES | RENDERED_FILES)),
            "source/rendered report inventory differs")
    if check:
        for name, content in expected.items():
            require(file(bundle, name).read_bytes() == content,
                    "rendered report differs from saved record: " + name)
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

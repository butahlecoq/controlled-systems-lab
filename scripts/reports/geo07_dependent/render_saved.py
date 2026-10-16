"""Validate and render the accepted GEO-07 dependent sum from saved bytes only."""
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

_spec = importlib.util.spec_from_file_location("geo07_dependent_saved_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(collect)

REPORT_ID = "geo07-dependent-4dcc5a8fe36f17ed"
SOURCE = "5411e37ad456f0d5b3bf775130f149622ef5ebfa"
HARNESS = "eef1eda3d326418a392b3cc1e8f8f4b204ca7a73"
CODE_PARENT = "eaa32fdfdcf42b3f3f3221dd3031d654fe05e576"
RAW_SHA = "3cc538611451add4eaef7adcbb5f225bbe668eadb8c32bd9e98de298f85fbc0c"
RECORDS_SHA = "fb4a0bab5953e679ece8e814aeb2a0fcbe68c4816fad3cc097c9e1b48774399c"
NATIVE_MANIFEST_SHA = "08e5bda248ee6eee7dd54732a7427b07f3c27638ef1001e588262c7ff5edc72a"
REJECTED_MANIFESTS = {
    "rejected-001": "c39f7f144ff1fd42b673f32ed5ac5a69bcbe72fdb27817d0fdd666396c278d7e",
    "rejected-002": "05fea510c3569d8fe2c1437dd3378a79ba9e7c2a285425674bba88057ed39a98",
}
NATIVE = frozenset({
    "build-provenance.json", "build.capture.json", "build.stderr", "build.stdout",
    "collection-status.json", "describe.capture.json", "describe.stderr", "describe.stdout",
    "fixture-inputs.json", "host-observation.json", "host-observation.stderr", "manifest.json",
    "records.json", "smoke.capture.json", "smoke.stderr", "smoke.stdout",
    "trials.capture.json", "trials.stderr", "trials.stdout",
})
GENERATED = frozenset({"index.html", "performance.svg", "summary.csv", "trials.csv",
                       "report-manifest.json", "bundle.zip"})


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_json(data: bytes) -> dict:
    value = json.loads(data, object_pairs_hook=collect.unique_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    require(isinstance(value, dict), "JSON object required")
    return value


def file(bundle: Path, name: str) -> Path:
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked saved file: " + name)
    return path


def validate_manifest(bundle: Path, expected: str, required: frozenset[str] | None = None) -> set[str]:
    manifest_bytes = file(bundle, "manifest.json").read_bytes()
    require(sha(manifest_bytes) == expected, "saved native manifest changed")
    manifest = object_json(manifest_bytes)
    names = set(manifest.get("files", {}))
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    require(manifest.get("schema") == collect.SCHEMA + "-manifest/1" and
            (required is None or names | {"manifest.json"} == required) and
            (actual == names | {"manifest.json"} or
             (required is not None and actual == names | {"manifest.json"} | GENERATED)) and
            all(not path.is_symlink() and
                (path.is_file() or (required is not None and path.name == "evidence" and path.is_dir()))
                for path in bundle.iterdir()),
            "native manifest inventory changed")
    for name, digest in manifest["files"].items():
        require(sha(file(bundle, name).read_bytes()) == digest, "native byte hash changed: " + name)
    return names | {"manifest.json"}


def validate_rejected(bundle: Path) -> set[str]:
    paths = set()
    for attempt, expected_sha in REJECTED_MANIFESTS.items():
        directory = bundle / "evidence" / attempt
        require(directory.is_dir() and not directory.is_symlink(), "rejected attempt missing")
        names = validate_manifest(directory, expected_sha)
        status = object_json(file(directory, "collection-status.json").read_bytes())
        require(status.get("publishable") is False and
                status.get("schema") == collect.SCHEMA + "-collection-status/1", "rejected status changed")
        host = object_json(file(directory, "host-observation.json").read_bytes())
        if attempt == "rejected-001":
            require("host observation" in status["reason"] and
                    host["build_processes"]["MSBuild"] == 3 and
                    "trials.stdout" not in names, "first rejected attempt changed")
        else:
            require("trial identity" in status["reason"] and
                    host["build_processes"] == {"cmake": 0, "MSBuild": 0, "cl": 0},
                    "second rejected attempt changed")
            rows = collect.parse_jsonl(file(directory, "trials.stdout").read_bytes())
            require(len(rows) == 16 and any(row["elapsed_ns"] < 20_000_000 for row in rows) and
                    all(row["status"] == "passed" and row["checked_calls"] == 1000 for row in rows),
                    "second rejected trial facts changed")
        paths.update("evidence/" + attempt + "/" + name for name in names)
    return paths


def validate_native(bundle: Path) -> dict:
    bundle = Path(bundle)
    require(bundle.is_dir() and not bundle.is_symlink() and bundle.name == REPORT_ID,
            "saved report identity changed")
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    require(actual in (NATIVE, NATIVE | GENERATED) and
            {path.name for path in bundle.iterdir() if path.is_dir()} == {"evidence"} and
            {path.name for path in (bundle / "evidence").iterdir()} == set(REJECTED_MANIFESTS),
            "saved report inventory changed")
    validate_manifest(bundle, NATIVE_MANIFEST_SHA, NATIVE)
    validate_rejected(bundle)
    raw = file(bundle, "trials.stdout").read_bytes()
    records_bytes = file(bundle, "records.json").read_bytes()
    require(sha(raw) == RAW_SHA and sha(records_bytes) == RECORDS_SHA,
            "audited raw or records bytes changed")
    record = object_json(records_bytes)
    require(record.get("schema") == collect.SCHEMA + "-records/1" and
            record.get("report_id") == REPORT_ID and
            record.get("source_commit") == SOURCE and
            record.get("source_tree") == "29996b5a58a1bb775cd7ea5e85b24a49cfaf7938" and
            record.get("harness_commit") == HARNESS and
            record.get("harness_tree") == "555954400146134d67a4aefca19bb767106c7e5f" and
            record.get("reviewed_code_commit") == CODE_PARENT and
            record.get("payload_sha256") == sha(collect.json_bytes({
                key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")})),
            "source, harness, or payload identity changed")
    inputs, hashes = collect.admit_description(file(bundle, "describe.stdout").read_bytes())
    require(file(bundle, "fixture-inputs.json").read_bytes() == inputs and
            record["inputs"]["fixtures"] == collect.INPUTS and
            record["inputs"]["fixture_sha256"] == hashes and
            record["inputs"]["canonical_bytes_sha256"] == sha(inputs) and
            record["inputs"]["driver_description_sha256"] == sha(file(bundle, "describe.stdout").read_bytes()),
            "authored input catalogue changed")
    smoke, _ = collect.admit_rows(file(bundle, "smoke.stdout").read_bytes(),
                                  repetitions=1, batch=1, smoke=True)
    rows, summary = collect.admit_rows(raw, repetitions=7, batch=2000)
    require(len(smoke) == 2 and len(rows) == 16 and record["rows"] == rows and
            record["summary"] == summary and record["timing"]["scope"] == collect.INTERVAL and
            record["timing"]["batch_calls"] == 2000 and
            record["timing"]["measured_rounds"] == 7 and
            record["timing"]["warmup_rounds"] == 1 and
            record["process"] == {"exit_code": 0, "raw_sha256": RAW_SHA,
                                   "stderr_sha256": sha(file(bundle, "trials.stderr").read_bytes())},
            "saved measured work changed")
    for stem in ("build", "describe", "smoke", "trials"):
        capture = object_json(file(bundle, stem + ".capture.json").read_bytes())
        require(capture["exit_code"] == 0 and capture["timed_out"] is False and
                capture["stdout_sha256"] == sha(file(bundle, stem + ".stdout").read_bytes()) and
                capture["stderr_sha256"] == sha(file(bundle, stem + ".stderr").read_bytes()) and
                file(bundle, stem + ".stderr").read_bytes() == b"", "process capture changed: " + stem)
    host_raw = file(bundle, "host-observation.json").read_bytes()
    host = object_json(host_raw)
    provenance_raw = file(bundle, "build-provenance.json").read_bytes()
    provenance = object_json(provenance_raw)
    status = object_json(file(bundle, "collection-status.json").read_bytes())
    require(record["environment"]["host_observation"] == host and
            record["environment"]["host_observation_sha256"] == sha(host_raw) and
            host["build_processes"] == {"cmake": 0, "MSBuild": 0, "cl": 0} and
            record["build_provenance_sha256"] == sha(provenance_raw) and
            provenance["source_commit"] == SOURCE and provenance["harness_commit"] == HARNESS and
            provenance["configuration"] == "Release" and
            provenance["settings"] == collect.RELEASE_FLAGS and
            provenance["compiler_version"] == "19.44.35215.0" and
            status.get("accepted_for_report_review") is True and
            status.get("publishable") is False and status.get("records_sha256") == RECORDS_SHA and
            record["performance_conclusion"].startswith("exploratory single-adapter") and
            record["environment"]["observed_native_threads"] is None,
            "host, Release build, or report gate changed")
    return record


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def figure(record: dict) -> bytes:
    names = {"shared_cancellation": "Shared cancellation", "constrained_shared": "Constrained shared"}
    colors = {"shared_cancellation": "#156f9a", "constrained_shared": "#a75432"}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="380" viewBox="0 0 900 380" '
             'role="img" aria-label="Seven verified measured batches per dependent sum fixture in milliseconds">',
             '<rect width="900" height="380" fill="white"/>',
             '<text x="65" y="27" font-size="20" fill="#183344" font-family="system-ui,sans-serif">Verified batch observations</text>']
    for ms in (0, 10, 20, 30, 40):
        y = 300 - ms * 6
        parts.append(f'<line x1="85" y1="{y}" x2="820" y2="{y}" stroke="#dce6ea"/>')
        parts.append(f'<text x="35" y="{y + 5}" font-size="13" fill="#526672">{ms}</text>')
    for name in collect.EXPECTED:
        values = [row["elapsed_ns"] / 1_000_000 for row in record["rows"]
                  if row["fixture"] == name and not row["warmup"]]
        require(len(values) == 7 and all(20 <= value <= 40 for value in values), "plot interval changed")
        points = [(110 + i * 110, 300 - value * 6) for i, value in enumerate(values)]
        parts.append('<polyline points="' + " ".join(f"{x},{y:.2f}" for x, y in points) +
                     f'" fill="none" stroke="{colors[name]}" stroke-width="3"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x}" cy="{y:.2f}" r="4" fill="{colors[name]}"/>')
    for index, name in enumerate(collect.EXPECTED):
        x = 90 + index * 270
        parts.append(f'<line x1="{x}" y1="340" x2="{x+30}" y2="340" stroke="{colors[name]}" stroke-width="4"/>')
        parts.append(f'<text x="{x+36}" y="345" font-size="14" fill="#183344">{escape(names[name])}</text>')
    parts.append('</svg>\n')
    return "".join(parts).encode("utf-8")


def page(record: dict, svg: bytes, downloads: set[str]) -> bytes:
    labels = {"shared_cancellation": "Shared cancellation", "constrained_shared": "Constrained shared factors"}
    summary = "".join(
        f'<tr><th scope="row">{escape(labels[name])}</th><td>2,000</td><td>7/7</td>'
        f'<td>{record["summary"][name]["median_batch_ns"] / 1_000_000:.3f}</td>'
        f'<td>{record["summary"][name]["min_batch_ns"] / 1_000_000:.3f}–'
        f'{record["summary"][name]["max_batch_ns"] / 1_000_000:.3f}</td></tr>'
        for name in collect.EXPECTED)
    links = "".join('<li><a href="' + escape(name, quote=True) + '">' + escape(name) + '</a></li>'
                    for name in sorted(downloads))
    host = record["environment"]["host_observation"]
    html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GEO-07 registered dependent sum · saved report</title>'
        '<style>body{margin:0;background:#f4f8fa;color:#193340;font:16px/1.55 system-ui,sans-serif}'
        '.header{background:#12394d;color:white;padding:2.2rem max(1.2rem,calc((100vw - 1000px)/2))}'
        '.header p{max-width:850px}.main{max-width:1000px;margin:auto;padding:1.5rem 1.2rem 3rem}'
        '.card{background:white;border:1px solid #d5e3e9;border-radius:12px;padding:1.3rem;margin:1rem 0}'
        'h1{line-height:1.1}table{border-collapse:collapse;width:100%;min-width:650px}th,td{padding:.6rem;border-bottom:1px solid #dce7eb;text-align:left;vertical-align:top}'
        'thead th{background:#edf4f7}.scroll{overflow-x:auto}svg{max-width:100%;height:auto}.downloads{columns:2;overflow-wrap:anywhere}'
        'code{overflow-wrap:anywhere}a{color:#0b608c}@media(max-width:650px){.downloads{columns:1}}</style></head><body>'
        '<div class="header"><p>Saved algorithm result · GEO-07</p><h1>Registered dependent generator sum</h1>'
        '<p>Two bounded public GeometryPort fixtures with shared factor IDs. The generator algebra is equivalent over real sets; '
        'binary64 evaluation has no validated rounding enclosure.</p></div><div class="main">'
        '<div class="card"><h2>Numerical outcomes</h2><div class="scroll"><table><thead><tr><th>Fixture</th><th>Literal physical reference</th><th>Observed generator result</th><th>Checks</th></tr></thead><tbody>'
        '<tr><th>Shared cancellation</th><td>x = 0</td><td>Center 0; retained history.0 factor with coefficient 0</td>'
        '<td>Three feasible factor witnesses map to 0; −1 and 1 are outside. Independent Minkowski sum rejects shared IDs.</td></tr>'
        '<tr><th>Constrained shared factors</th><td>u − v = 0 and u + w = 0 imply (x,y) = (0,0)</td>'
        '<td>Joined factors [u,v,w]; coefficients [0,0,0; 0,1,1]; both equality rows retained</td>'
        '<td>Three feasible witnesses map to the origin; (0,1) and (1,0) are outside. Independent sum rejects shared IDs.</td></tr>'
        '</tbody></table></div><p>Every checked call used fresh handles, the registered public port, prepared typed DependentSum, '
        'workspace execution and literal factor/H checks. Evidence is structural with numerical assurance and no error bound. '
        'These examples do not prove all geometry inputs or validated floating point equivalence.</p></div>'
        '<div class="card"><h2>Verified batch observations</h2><p>One excluded warmup and seven alternating measured batches per fixture. '
        'Each batch made 2,000 fully checked calls. All 16 warmup and measured batches passed; all 14 measured batches exceeded 20 ms.</p>'
        '<div class="scroll"><table><thead><tr><th>Fixture</th><th>Calls/batch</th><th>Successes</th><th>Median ms</th><th>Range ms</th></tr></thead><tbody>' +
        summary + '</tbody></table></div><figure>' + svg.decode("utf-8") +
        '<figcaption>Seven measured batches per fixture on one shared millisecond scale; warmups excluded.</figcaption></figure>'
        '<p>Performance interpretation is exploratory and inconclusive: no comparator, speedup, source-mapped limiter profile, '
        'application-scale workload or isolated native-operation latency is claimed.</p>'
        '<p>The steady_clock interval includes fresh handles and registration, admission, workspace execution, literal checks, '
        'independent rejection and per-call JSON result assignment. It excludes startup, JSONL serialization, Python validation, '
        'persistence and rendering. Internal phase counters and observed native thread count are unavailable.</p></div>'
        '<div class="card"><h2>Source and host evidence</h2><p>Algorithm source <code>' + SOURCE + '</code>; reviewed harness code <code>' +
        CODE_PARENT + '</code>; sealed collection HEAD <code>' + HARNESS + '</code>; saved report <code>' + REPORT_ID +
        '</code>. Raw SHA-256 <code>' + RAW_SHA + '</code>; records SHA-256 <code>' + RECORDS_SHA +
        '</code>; native manifest SHA-256 <code>' + NATIVE_MANIFEST_SHA + '</code>.</p>'
        '<p>MSVC 19.44.35215.0, x64 C++20 Release /O2 /Ob2 /DNDEBUG; ' +
        escape(str(record["environment"]["os"])) + ', ' + str(record["environment"]["logical_processors"]) +
        ' logical processors. Immediately before measurement, the collector observed CPU ' +
        str(host["cpu_load_percent"]) + '% and zero cmake, MSBuild or cl processes. One sequential driver worker was requested.</p>'
        '<p>Two earlier attempts were rejected and preserved in evidence/rejected-001 and evidence/rejected-002. '
        'The first observed three idle MSBuild nodes and stopped before trials. The second executed all literal checks, '
        'but its 1,000-call batches fell below the 20 ms admission floor. Neither contributes measured results.</p></div>'
        '<div class="card"><h2>Download and audit</h2><p>The original process captures, failed attempts, inputs, build evidence, '
        'records and rendered tables are available below and in the offline ZIP.</p><ul>' + links +
        '</ul></div></div></body></html>\n')
    return html.encode("utf-8")


def generated(record: dict, native_paths: set[str]) -> dict[str, bytes]:
    rows = [{key: row[key] for key in ("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status")}
            for row in record["rows"]]
    summary = [{"fixture": name, "batch": 2000, **record["summary"][name]} for name in collect.EXPECTED]
    svg = figure(record)
    links = native_paths | {"trials.csv", "summary.csv", "performance.svg", "report-manifest.json"}
    return {"index.html": page(record, svg, links), "performance.svg": svg,
            "trials.csv": csv_bytes(("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status"), rows),
            "summary.csv": csv_bytes(("fixture", "batch", "attempts", "successes", "failures", "median_batch_ns",
                                      "min_batch_ns", "max_batch_ns"), summary)}


def saved_paths(bundle: Path) -> set[str]:
    return set(NATIVE) | validate_rejected(bundle)


def offline_zip(bundle: Path, files: dict[str, bytes]) -> bytes:
    landing = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Offline GEO-07 dependent report</title>'
               '</head><body><h1>Offline GEO-07 dependent report</h1><a href="' + REPORT_ID +
               '/index.html">Open saved report</a></body></html>\n').encode("utf-8")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [("index.html", landing)] + [(REPORT_ID + "/" + name, files[name]) for name in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue()


def render(bundle: Path, *, check: bool) -> None:
    bundle = Path(bundle)
    record = validate_native(bundle)
    originals = {name: file(bundle, name).read_bytes() for name in saved_paths(bundle)}
    assets = generated(record, set(originals))
    report_manifest = collect.json_bytes({"schema": collect.SCHEMA + "-render-manifest/1",
                                          "report_id": REPORT_ID, "source_commit": SOURCE,
                                          "harness_commit": HARNESS,
                                          "files": {name: sha(content) for name, content in (originals | assets).items()}})
    archive = offline_zip(bundle, originals | assets | {"report-manifest.json": report_manifest})
    expected = assets | {"report-manifest.json": report_manifest, "bundle.zip": archive}
    inventory = {path.name for path in bundle.iterdir() if path.is_file()}
    require((inventory == NATIVE | GENERATED if check else inventory in (NATIVE, NATIVE | GENERATED)),
            "rendered report inventory changed")
    if check:
        for name, content in expected.items():
            require(file(bundle, name).read_bytes() == content, "rendered byte differs: " + name)
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

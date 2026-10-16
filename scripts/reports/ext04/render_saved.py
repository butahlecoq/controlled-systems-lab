"""Validate and render the audited EXT-04 collection without running C++."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

_spec = importlib.util.spec_from_file_location("csl_ext04_saved_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(collect)

REPORT_ID = "ext04-df62c7c6d295e135"
SOURCE = "c23aaf13c1c1e5480cc22dd5bac5cd3e79562609"
HARNESS = "959755ed5f69641ae643e852c00efe718fa9eb86"
RAW_SHA = "7c6c33024ffa93eb37065bf1a66df8a8f02827e0e0e039ec93a9090db1b900d8"
RECORDS_SHA = "0d11f932157f0bde7d3ab605bf4bcc56a8cf8c755ad0642f9452713123ed1b70"
NATIVE_MANIFEST_SHA = "13950e8c24b689b18109b9da182d575ab5d55f3f0dc5749f6510b9f438811343"
HOST_PRE_SHA = "065ba5ab520ef3825a2a7b35f0e512468a1cf06f875a4589aabf9adf6209c5e5"
HOST_POST_SHA = "7619f6c36dd6081b433b0c31c69fcadc4af1044ecd5307170d90411dbaa7c072"
RAW_FILES = frozenset({"CMakeCache.raw.txt", "CMakeCXXCompiler.raw.cmake", "build-provenance.json",
    "build.stderr.log", "build.stdout.log", "collection-status.json", "driver-description.jsonl",
    "driver.stderr", "fixture-inputs.json", "manifest.json", "process-capture.json",
    "records.json", "trials.jsonl"})
SOURCE_FILES = RAW_FILES | {"host-pre.json", "host-post.json"}
RENDERED_FILES = frozenset({"index.html", "performance.svg", "trials.csv", "summary.csv",
                            "report-manifest.json", "bundle.zip"})


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def object_json(content: bytes) -> dict:
    value = json.loads(content.decode("utf-8"), object_pairs_hook=collect._unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON token")))
    require(isinstance(value, dict), "saved JSON object required")
    return value


def file(bundle: Path, name: str) -> Path:
    require(name in SOURCE_FILES | RENDERED_FILES, "unlisted EXT-04 file")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked EXT-04 file: " + name)
    return path


def validate_native(bundle: Path) -> dict:
    bundle = Path(bundle)
    require(bundle.name == REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "EXT-04 source bundle identity differs")
    for name in SOURCE_FILES:
        file(bundle, name)
    raw, record_bytes, manifest_bytes = (file(bundle, name).read_bytes()
                                          for name in ("trials.jsonl", "records.json", "manifest.json"))
    require((sha(raw), sha(record_bytes), sha(manifest_bytes)) ==
            (RAW_SHA, RECORDS_SHA, NATIVE_MANIFEST_SHA), "audited collection byte identity differs")
    manifest = object_json(manifest_bytes)
    require(manifest.get("schema") == "csl.ext04-manifest/1" and
            manifest.get("report_id") == REPORT_ID and
            set(manifest.get("files", {})) == RAW_FILES - {"manifest.json"},
            "native manifest inventory differs")
    for name, digest in manifest["files"].items():
        require(sha(file(bundle, name).read_bytes()) == digest,
                "audited raw file differs: " + name)
    require(sha(file(bundle, "host-pre.json").read_bytes()) == HOST_PRE_SHA and
            sha(file(bundle, "host-post.json").read_bytes()) == HOST_POST_SHA,
            "audited host observation differs")
    pre = object_json(file(bundle, "host-pre.json").read_bytes())
    post = object_json(file(bundle, "host-post.json").read_bytes())
    require(datetime.fromisoformat(pre["observed_utc"]) < datetime.fromisoformat(post["observed_utc"]) and
            pre["host"] == post["host"] and pre["logical_processors"] == post["logical_processors"] == 12 and
            pre["cpu_percent_5s"] <= 5 and post["cpu_percent_5s"] <= 5,
            "host pre/post observation differs")
    record = object_json(record_bytes)
    unsigned = {key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")}
    require(record.get("schema") == collect.RECORD_SCHEMA and record.get("report_id") == REPORT_ID and
            record.get("source_commit") == SOURCE and record.get("harness_commit") == HARNESS and
            record.get("payload_sha256") == sha(collect.json_bytes(unsigned)) and
            record.get("report_id") == "ext04-" + record["payload_sha256"][:16],
            "fixed-source saved record identity differs")
    require(record["timing"]["scope"] == collect.INTERVAL and
            record["timing"]["warmup_rounds"] == 1 and
            record["timing"]["measured_rounds"] == 7 and
            record["timing"]["batch_calls"] == 5000 and
            record["timing"]["minimum_admitted_batch_ns"] == 20_000_000,
            "timing scope or batch profile differs")
    rows, summary = collect.admit_raw(raw, repetitions=7, batch=5000)
    require(record["rows"] == rows and record["summary"] == summary and len(rows) == 24,
            "saved rows or summary differ from all admitted raw trials")
    process = object_json(file(bundle, "process-capture.json").read_bytes())
    require(process["exit_code"] == 0 and process["timed_out"] is False and
            process["stdout_sha256"] == RAW_SHA and
            process["stderr_sha256"] == sha(file(bundle, "driver.stderr").read_bytes()) and
            file(bundle, "driver.stderr").read_bytes() == b"" and
            record["process"] == {"exit_code": 0, "raw_sha256": RAW_SHA,
                                  "stderr_sha256": process["stderr_sha256"]},
            "native process status or exact output differs")
    inputs, hashes = collect.admit_description(file(bundle, "driver-description.jsonl").read_bytes())
    require(file(bundle, "fixture-inputs.json").read_bytes() == inputs and
            record["inputs"]["fixtures"] == collect.INPUTS and
            record["inputs"]["fixture_sha256"] == hashes and
            record["inputs"]["canonical_bytes_sha256"] == sha(inputs),
            "authored fixture input evidence differs")
    provenance_bytes = file(bundle, "build-provenance.json").read_bytes()
    provenance = object_json(provenance_bytes)
    require(record["build_provenance_sha256"] == sha(provenance_bytes) and
            provenance["source_commit"] == SOURCE and provenance["harness_commit"] == HARNESS and
            provenance["configuration"] == "Release" and provenance["compiler"]["id"] == "MSVC" and
            provenance["compiler"]["toolset"] == "v143" and
            provenance["cache_sha256"] == sha(file(bundle, "CMakeCache.raw.txt").read_bytes()) and
            provenance["compiler_file_sha256"] == sha(file(bundle, "CMakeCXXCompiler.raw.cmake").read_bytes()) and
            provenance["build_stdout_sha256"] == sha(file(bundle, "build.stdout.log").read_bytes()) and
            provenance["build_stderr_sha256"] == sha(file(bundle, "build.stderr.log").read_bytes()),
            "saved Release compiler/cache/build evidence differs")
    status = object_json(file(bundle, "collection-status.json").read_bytes())
    require(status.get("accepted_for_report_review") is True and status.get("publishable") is False and
            status.get("records_sha256") == RECORDS_SHA and
            record["environment"]["concurrent_work_note"].startswith("UTC pre-collection " + pre["observed_utc"]),
            "collection acceptance or host note differs")
    require(record["performance_conclusion"] ==
            "exploratory single-path batch observations; no comparator, speedup, or attributed limiter" and
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
    colors = ("#22607d", "#a45b2a", "#537447")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="780" height="420" '
             'viewBox="0 0 780 420" role="img" '
             'aria-label="Seven verified EXT-04 batch observations per fixture, in milliseconds">']
    for panel, name in enumerate(collect.EXPECTED):
        values = [row["elapsed_ns"] / 1_000_000 for row in record["rows"]
                  if row["fixture"] == name and not row["warmup"]]
        require(len(values) == 7, "seven plotted observations per fixture required")
        low, high = min(values), max(values)
        spread = max(high - low, 0.1)
        top = 18 + panel * 130
        points = [(200 + index * 74, top + 90 - 72 * (value - low) / spread)
                  for index, value in enumerate(values)]
        parts.append(f'<text x="8" y="{top + 45}" font-size="16">{escape(name.replace("_", " "))}</text>')
        parts.append(f'<line x1="190" y1="{top + 92}" x2="650" y2="{top + 92}" stroke="#b9cad0"/>')
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" '
                     f'fill="none" stroke="{colors[panel]}" stroke-width="2"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[panel]}"/>')
        parts.append(f'<text x="660" y="{top + 20}" font-size="12">{high:.2f} ms</text>')
        parts.append(f'<text x="660" y="{top + 92}" font-size="12">{low:.2f} ms</text>')
    parts.append('<text x="345" y="415" font-size="13">Measured round 1–7 (per fixture)</text></svg>\n')
    return "".join(parts).encode("utf-8")


def page(record: dict) -> bytes:
    output = {
        "partial_noisy_delayed": ("Partial, noisy, delayed observation", "(1, 7) → (2, 7) → (9, 7)",
                                  "4 before(0); 7 measured after(0), released before(1)", "1; 7"),
        "post_feedthrough": ("Post-decision feedthrough", "2 → 3 → 10",
                             "7 = x₀ + 2u₀ + v₀, released after(0)", "1; 7"),
        "no_channel": ("No observation channel", "5 → 7", "None; no implicit observation", "2"),
    }
    outcome_rows = "".join('<tr><th scope="row">' + escape(label) + '</th><td>' + escape(states) +
                           '</td><td>' + escape(observations) + '</td><td>' + escape(actions) + '</td></tr>'
                           for label, states, observations, actions in output.values())
    timing_rows = "".join('<tr><th scope="row">' + escape(name.replace("_", " ")) + '</th><td>5,000</td>'
                          '<td>7/7</td><td>' + f'{record["summary"][name]["median_batch_ns"]/1_000_000:.3f}' +
                          '</td><td>' + f'{record["summary"][name]["min_batch_ns"]/1_000_000:.3f}–'
                          f'{record["summary"][name]["max_batch_ns"]/1_000_000:.3f}' + '</td></tr>'
                          for name in collect.EXPECTED)
    downloads = sorted((SOURCE_FILES | RENDERED_FILES) - {"index.html", "bundle.zip"})
    links = "".join('<li><a href="' + name + '">' + escape(name) + '</a></li>' for name in downloads)
    env = record["environment"]
    scope = record["timing"]["scope"]
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>EXT-04 observed replay report</title>'
        '<style>body{font:16px system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;'
        'color:#1c2a35;line-height:1.5}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;margin:1rem 0}'
        'th,td{border:1px solid #bac8d0;padding:.55rem;text-align:left;vertical-align:top}th{background:#eaf0f4}'
        'code{overflow-wrap:anywhere}figure{margin:1.5rem 0}svg{max-width:100%;height:auto}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>'
        '<h1>EXT-04 observed policy replay</h1>'
        '<p>Fixed-source, binary64 sampled trajectories through the public <code>CSL::controllers</code> '
        'replay API. The estimator and controller are caller-defined callbacks. These examples check '
        'one supplied initial state and error sequence each; they do not establish policy nonanticipativity, '
        'state-estimate accuracy, all-initial-states feasibility, all-disturbance performance, optimality, '
        'family completeness or validated rounding enclosure.</p>'
        '<h2>Literal trajectory outcomes</h2><table><caption>Independent expected values checked on every call'
        '</caption><thead><tr><th>Fixture</th><th>Physical states</th><th>Released observations</th>'
        '<th>Actions</th></tr></thead><tbody>' + outcome_rows + '</tbody></table>'
        '<p>The noisy partial fixture checks sample channel/index and delayed release identity; the '
        'post-decision fixture includes the control-feedthrough term; the channel-free fixture checks '
        'that no full-state reading is invented. Decision stage, each available observation identity, '
        'state, estimate, action and retained inputs are checked inside every measured call.</p>'
        '<h2>Saved Release batch observations</h2><p>One excluded warmup per fixture, then seven '
        'alternating measured batches per fixture with 5,000 fresh and fully checked calls per batch. '
        'All 24 rows passed with zero observed failures. These are verified-batch durations in '
        'milliseconds, not isolated controller latency. Scope: ' + escape(scope) + '.</p>'
        '<table><caption>Seven measured batches per fixture, milliseconds</caption><thead><tr>'
        '<th>Fixture</th><th>Calls/batch</th><th>Successful batches</th><th>Median ms</th>'
        '<th>Range ms</th></tr></thead><tbody>' + timing_rows + '</tbody></table>'
        '<figure aria-label="Seven verified batch observations per fixture">' + figure(record).decode("utf-8") +
        '<figcaption>Within-fixture variation across '
        'seven rounds. The panels use local scales and do not compare methods.</figcaption></figure>'
        '<p>Performance interpretation is exploratory and inconclusive. There is no comparator, '
        'source-mapped limiter profile, application-scale workload, speedup or throughput claim. '
        'Internal phase durations and observed native thread count are unavailable.</p>'
        '<h2>Build, host and evidence</h2><p>Frozen algorithm source <code>' + SOURCE +
        '</code>; reviewed harness <code>' + HARNESS + '</code>; accepted collection <code>' +
        REPORT_ID + '</code>. Raw JSONL SHA-256 <code>' + RAW_SHA + '</code>; native manifest SHA-256 '
        '<code>' + NATIVE_MANIFEST_SHA + '</code>. The later artifact commit carries this page and is '
        'distinct from the source and harness revisions.</p>'
        '<p>Release x64 MSVC v143, C++20, <code>/O2 /Ob2 /DNDEBUG</code>; one sequential driver requested. '
        'Windows host ' + escape(str(env["os"])) + ', ' + str(env["logical_processors"]) +
        ' logical processors. Pre/post five-second host utilization was 1.1%; source cache, compiler '
        'record, build log and host snapshots are retained. The collection status records acceptance '
        'for report review and a then-pending publication gate.</p>'
        '<h2>Download and audit</h2><ul>' + links + '</ul></body></html>\n')
    return html.encode("utf-8")


def generated(record: dict) -> dict[str, bytes]:
    fields = ("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns", "status")
    trials = [{key: row[key] for key in fields} for row in record["rows"]]
    summary_fields = ("fixture", "attempts", "successes", "failures", "median_batch_ns",
                      "min_batch_ns", "max_batch_ns")
    summary = [{"fixture": name, **record["summary"][name]} for name in collect.EXPECTED]
    return {"index.html": page(record), "performance.svg": figure(record),
            "trials.csv": csv_bytes(fields, trials), "summary.csv": csv_bytes(summary_fields, summary)}


def report_manifest(bundle: Path, assets: dict[str, bytes]) -> bytes:
    files = {name: sha(file(bundle, name).read_bytes()) for name in SOURCE_FILES}
    files.update({name: sha(content) for name, content in assets.items()})
    return collect.json_bytes({"schema": "csl.ext04-render-manifest/1", "report_id": REPORT_ID,
                               "source_commit": SOURCE, "harness_commit": HARNESS, "files": files})


def offline_zip(bundle: Path, assets: dict[str, bytes], manifest: bytes) -> bytes:
    files = {name: file(bundle, name).read_bytes() for name in SOURCE_FILES}
    files.update(assets)
    files["report-manifest.json"] = manifest
    landing = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<title>Offline EXT-04 report</title></head><body><h1>Offline EXT-04 report</h1>'
               f'<a href="{REPORT_ID}/index.html">Open saved observed replay report</a></body></html>\n').encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [("index.html", landing)] + [(REPORT_ID + "/" + name, files[name])
                                                    for name in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def render(bundle: Path, *, check: bool) -> None:
    bundle = Path(bundle)
    record = validate_native(bundle)
    assets = generated(record)
    manifest = report_manifest(bundle, assets)
    expected = assets | {"report-manifest.json": manifest,
                         "bundle.zip": offline_zip(bundle, assets, manifest)}
    inventory = {path.name for path in bundle.iterdir() if path.is_file()}
    require(all(not path.is_symlink() for path in bundle.iterdir()) and
            (inventory == SOURCE_FILES | RENDERED_FILES if check else
             inventory in (SOURCE_FILES, SOURCE_FILES | RENDERED_FILES)),
            "source/rendered report inventory differs")
    if check:
        for name, content in expected.items():
            require(file(bundle, name).read_bytes() == content,
                    "rendered report differs from saved records: " + name)
    else:
        for name, content in expected.items():
            (bundle / name).write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, check=args.check)


if __name__ == "__main__":
    main()

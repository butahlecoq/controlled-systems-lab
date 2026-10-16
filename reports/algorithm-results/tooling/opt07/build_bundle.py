"""Build/check a native OPT-07 report solely from a future saved collection.

This module never invokes the reducer, driver, or measurement collector.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import re
import statistics
import zipfile

if __package__:
    from .collect import sanitize_build_log
    from .oracle import FIXTURES, require
    from .validate import validate_stream
else:
    from collect import sanitize_build_log
    from oracle import FIXTURES, require
    from validate import validate_stream


SCHEMA = "csl.opt07-ordered-hull-report/1"
MANIFEST_SCHEMA = "csl.opt07-report-manifest/1"
SOURCE_FILES = {
    "collection.json", "functional-validation.json", "raw-stdout.jsonl",
    "raw-stderr.txt", "release-build-log-sanitized.txt", "records.json",
    "trials.csv", "summary.csv", "latency.svg", "index.html",
}
TRIAL_FIELDS = ("case_id", "round", "warmup", "calls", "verified_calls",
                "elapsed_ns", "status", "failed_calls")
SUMMARY_FIELDS = ("case_id", "points", "measured_batches", "measured_calls",
                  "median_batch_ns", "min_batch_ns", "max_batch_ns", "failed_calls")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def payload_digest(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8"))


def csv_bytes(rows: list[dict], fields: tuple[str, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def read_collection(directory: Path) -> tuple[dict, list[dict], dict]:
    collection = json.loads((directory / "collection.json").read_text(encoding="utf-8"))
    require(isinstance(collection, dict), "collection metadata must be an object")
    source_commit = collection.get("source_commit")
    require(isinstance(source_commit, str) and
            re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None,
            "full measured source commit required")
    description = collection.get("description", {})
    require(description.get("source_commit") == source_commit and
            description.get("configuration") == "Release" and
            description.get("batch_calls") == 100 and
            description.get("repetitions") == 7 and
            collection.get("algorithm", {}).get("method") == "csl.hull.ordered-membership" and
            collection.get("process_exit_code") == 0,
            "collection is not a completed source-bound OPT-07 measurement")
    protocol = collection.get("protocol", {})
    require(protocol.get("warmup_batches_per_fixture") == 1 and
            protocol.get("measured_batches_per_fixture") == 7 and
            protocol.get("calls_per_batch") == 100,
            "collection batch protocol changed")
    require(all(isinstance(collection.get(key), str) and
                re.fullmatch(r"[0-9a-f]{64}", collection[key]) is not None
                for key in ("build_log_sha256", "sanitized_build_log_sha256",
                            "executable_sha256", "fixture_sha256",
                            "cmake_cache_sha256", "generated_release_project_sha256")) and
            isinstance(collection.get("source_sha256"), dict) and
            bool(collection["source_sha256"]) and
            all(re.fullmatch(r"[0-9a-f]{64}", value) is not None
                for value in collection["source_sha256"].values()),
            "collection provenance hashes missing")
    release = collection.get("release_project", {})
    require(release.get("LanguageStandard") == "stdcpp20" and
            release.get("Optimization") == "MaxSpeed" and
            "NDEBUG" in release.get("PreprocessorDefinitions", ""),
            "Release compiler evidence missing")
    environment = collection.get("environment", {})
    require(all(environment.get(key) for key in
                ("os", "machine", "logical_processors", "concurrent_work_note")),
            "host and concurrent-work evidence missing")
    sanitize_build_log(json.dumps(collection, ensure_ascii=True), {})
    public_log = (directory / "release-build-log-sanitized.txt").read_bytes()
    require(digest(public_log) == collection["sanitized_build_log_sha256"],
            "sanitized Release log hash mismatch")
    sanitize_build_log(public_log.decode("utf-8"), {})
    stderr = (directory / "raw-stderr.txt").read_bytes()
    sanitize_build_log(stderr.decode("utf-8"), {})
    raw = directory / "raw-stdout.jsonl"
    validation = validate_stream(raw, "measurement")
    saved_validation = json.loads((directory / "functional-validation.json").read_text(encoding="utf-8"))
    require(validation == saved_validation and
            validation == {"purpose": "measurement", "fixtures": 3,
                           "batches": 24, "calls": 2400},
            "saved functional validation differs from raw measurement")
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    return collection, rows, validation


def report_record(directory: Path) -> dict:
    collection, raw_rows, validation = read_collection(directory)
    batches = []
    for case_id in FIXTURES:
        for round_id in range(8):
            matching = [row for row in raw_rows if row["case_id"] == case_id and
                        row["round"] == round_id]
            batch = next(row for row in matching if row["kind"] == "batch")
            calls = [row for row in matching if row["kind"] == "call"]
            failed = sum(row["status"] != "complete" or row["verified"] is not True
                         for row in calls)
            batches.append({"case_id": case_id, "round": round_id,
                            "warmup": round_id == 0, "calls": batch["calls"],
                            "verified_calls": batch["verified_calls"],
                            "elapsed_ns": batch["elapsed_ns"],
                            "status": "complete" if failed == 0 else "failed",
                            "failed_calls": failed})
    summary = []
    for case_id, fixture in FIXTURES.items():
        measured = [row for row in batches if row["case_id"] == case_id and
                    not row["warmup"]]
        values = [row["elapsed_ns"] for row in measured]
        summary.append({"case_id": case_id, "points": len(fixture["points"]),
                        "measured_batches": len(measured),
                        "measured_calls": sum(row["calls"] for row in measured),
                        "median_batch_ns": statistics.median(values),
                        "min_batch_ns": min(values), "max_batch_ns": max(values),
                        "failed_calls": sum(row["failed_calls"] for row in measured)})
    payload = {"schema": SCHEMA, "source_commit": collection["source_commit"],
               "collection": collection, "validation": validation,
               "raw_stdout_sha256": digest((directory / "raw-stdout.jsonl").read_bytes()),
               "raw_stderr_sha256": digest((directory / "raw-stderr.txt").read_bytes()),
               "sanitized_build_log_sha256": collection["sanitized_build_log_sha256"],
               "batches": batches, "summary": summary,
               "scientific_scope": "exact dyadic certificates for represented binary64 points in three fixed small clouds",
               "performance_interpretation": "descriptive single-adapter batches; no comparator, speedup, source-mapped limiter, or scalability claim"}
    payload_sha256 = payload_digest(payload)
    return {**payload, "report_id": "opt07-" + payload_sha256[:16],
            "payload_sha256": payload_sha256}


def latency_svg(record: dict) -> str:
    rows = record["summary"]
    top = max(row["max_batch_ns"] for row in rows) or 1
    strokes = []
    for index, row in enumerate(rows):
        x = 130 + index * 210
        scale = lambda value: 245 - 190 * value / top
        low, med, high = (scale(row[key]) for key in
                          ("min_batch_ns", "median_batch_ns", "max_batch_ns"))
        strokes.append(f'<line x1="{x}" x2="{x}" y1="{high:.1f}" y2="{low:.1f}" stroke="#285c75" stroke-width="3"/>')
        strokes.append(f'<line x1="{x-16}" x2="{x+16}" y1="{med:.1f}" y2="{med:.1f}" stroke="#a44828" stroke-width="6"/>')
        strokes.append(f'<text x="{x}" y="280" text-anchor="middle">{html.escape(row["case_id"])}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc" '
            'viewBox="0 0 680 310"><title id="title">OPT-07 measured batch duration</title>'
            '<desc id="desc">Seven measured 100-call batches per fixture; median marker and minimum-to-maximum range, in nanoseconds.</desc>'
            '<style>text{font:13px system-ui,sans-serif;fill:#182b36}</style>'
            '<text x="24" y="28">Duration per 100-call batch (ns)</text>'
            + "".join(strokes) + '</svg>')


def page(record: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    rows = "".join("<tr>" + "".join(f"<td>{esc(row[field])}</td>" for field in
                   SUMMARY_FIELDS) + "</tr>" for row in record["summary"])
    trial_rows = "".join("<tr>" + "".join(f"<td>{esc(row[field])}</td>" for field in
                         TRIAL_FIELDS) + "</tr>" for row in record["batches"])
    headers = lambda fields: "".join(f"<th scope=\"col\">{esc(field)}</th>" for field in fields)
    collection = record["collection"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPT-07 ordered hull result</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:74rem;margin:2rem auto;padding:0 1rem;color:#172b36}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border:1px solid #bcc9d0;padding:.35rem;text-align:left}}code{{overflow-wrap:anywhere}}figure{{margin:1.5rem 0}}svg{{max-width:100%}}</style></head><body>
<h1>OPT-07 ordered hull membership</h1>
<p>Native record <code>{esc(record["report_id"])}</code>; measured source commit <code>{esc(record["source_commit"])}</code>. Algorithm <code>{esc(collection["algorithm"]["method"])}</code> version <code>{esc(collection["algorithm"]["version"])}</code>; backend <code>{esc(collection["backend"]["method"])}</code> adapter <code>{esc(collection["backend"]["adapter_version"])}</code>.</p>
<p>Three fixed binary64 clouds exercise signed-score ordering, a zero-width duplicate, and a late exterior point. Every one of 2,400 calls passed the independent exact-dyadic certificate and literal support oracle. This is evidence for these represented inputs, not a general or validated-real hull theorem.</p>
<h2>Measured batches</h2><figure>{latency_svg(record)}<figcaption>Each marker is the median of seven measured 100-call batches; the line spans minimum to maximum. One warmup batch per fixture is excluded. Durations are for registered <code>run_with</code> calls and output moves; fresh workspace construction, independent validation, JSON and HTML are outside the interval. Lazy native initialization inside the calls is included. No per-call latency is inferred by division.</figcaption></figure>
<table><thead><tr>{headers(SUMMARY_FIELDS)}</tr></thead><tbody>{rows}</tbody></table>
<h2>All batch outcomes</h2><table><thead><tr>{headers(TRIAL_FIELDS)}</tr></thead><tbody>{trial_rows}</tbody></table>
<p>Performance interpretation: {esc(record["performance_interpretation"])}. Internal LP phase durations, pivots and observed native thread count are unavailable. Configured native threads: {esc(collection["backend"]["configured_threads"])}. OS: {esc(collection["environment"]["os"])}; machine: {esc(collection["environment"]["machine"])}; logical processors: {esc(collection["environment"]["logical_processors"])}. Release compiler project: {esc(collection["release_project"]["LanguageStandard"])} with {esc(collection["release_project"]["Optimization"])} and NDEBUG; exact compile command is in the saved sanitized build log. Concurrent-work note: {esc(collection["environment"]["concurrent_work_note"])}.</p>
<h2>Saved evidence</h2><ul><li><a href="records.json">Versioned records and provenance</a></li><li><a href="raw-stdout.jsonl">Exact raw call and batch JSONL</a></li><li><a href="raw-stderr.txt">Exact process stderr</a></li><li><a href="collection.json">Collection provenance</a></li><li><a href="functional-validation.json">Independent validation result</a></li><li><a href="release-build-log-sanitized.txt">Sanitized Release build log</a></li><li><a href="trials.csv">All batch CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="latency.svg">Standalone figure</a></li><li><a href="manifest.json">Native manifest</a></li></ul>
<p>Generated from saved bytes without running the algorithm. The raw local build-log SHA-256 is preserved in collection provenance; its public copy is sanitized and separately hashed.</p></body></html>'''


def source_zip_bytes(bundle: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(SOURCE_FILES | {"manifest.json"}):
            info = zipfile.ZipInfo(f"{bundle.name}/{name}",
                                   date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (bundle / name).read_bytes())
    return buffer.getvalue()


def build(collection: Path, root: Path) -> Path:
    record = report_record(collection)
    bundle = root / record["report_id"]
    archive = root / (bundle.name + ".source.zip")
    require(not bundle.exists() and not archive.exists(), "report destination already exists")
    files = {name: (collection / name).read_bytes() for name in (
        "collection.json", "functional-validation.json", "raw-stdout.jsonl",
        "raw-stderr.txt", "release-build-log-sanitized.txt")}
    files.update({"records.json": json_bytes(record),
                  "trials.csv": csv_bytes(record["batches"], TRIAL_FIELDS),
                  "summary.csv": csv_bytes(record["summary"], SUMMARY_FIELDS),
                  "latency.svg": latency_svg(record).encode("utf-8"),
                  "index.html": page(record).encode("utf-8")})
    manifest = {"schema": MANIFEST_SCHEMA, "report_id": record["report_id"],
                "files": {name: digest(files[name]) for name in sorted(files)}}
    bundle.mkdir(parents=True)
    for name, content in files.items():
        (bundle / name).write_bytes(content)
    (bundle / "manifest.json").write_bytes(json_bytes(manifest))
    archive.write_bytes(source_zip_bytes(bundle))
    check(bundle)
    return bundle


def check(bundle: Path) -> dict:
    require(bundle.is_dir() and not bundle.is_symlink(), "report directory required")
    entries = list(bundle.iterdir())
    require({path.name for path in entries} == SOURCE_FILES | {"manifest.json"} and
            all(path.is_file() and not path.is_symlink() for path in entries),
            "native report inventory differs")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA and
            manifest.get("report_id") == bundle.name and
            set(manifest.get("files", {})) == SOURCE_FILES,
            "native report manifest differs")
    for name in SOURCE_FILES:
        require(digest((bundle / name).read_bytes()) == manifest["files"][name],
                f"native report hash mismatch: {name}")
    record = report_record(bundle)
    require(record["report_id"] == bundle.name and
            (bundle / "records.json").read_bytes() == json_bytes(record),
            "saved record differs from exact raw bytes")
    expected = {"trials.csv": csv_bytes(record["batches"], TRIAL_FIELDS),
                "summary.csv": csv_bytes(record["summary"], SUMMARY_FIELDS),
                "latency.svg": latency_svg(record).encode("utf-8"),
                "index.html": page(record).encode("utf-8")}
    for name, content in expected.items():
        require((bundle / name).read_bytes() == content,
                f"saved projection differs: {name}")
    archive = bundle.parent / (bundle.name + ".source.zip")
    require(archive.is_file() and not archive.is_symlink() and
            archive.read_bytes() == source_zip_bytes(bundle),
            "deterministic source ZIP differs")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        require(args.collection is not None and args.out_root is not None and
                args.bundle is None, "build requires collection and out-root")
        bundle = build(args.collection, args.out_root)
    else:
        require(args.bundle is not None and args.collection is None and
                args.out_root is None, "check requires bundle")
        bundle = args.bundle
        check(bundle)
    print(json.dumps({"report_id": bundle.name, "status": "saved_report_valid"},
                     sort_keys=True))


if __name__ == "__main__":
    main()

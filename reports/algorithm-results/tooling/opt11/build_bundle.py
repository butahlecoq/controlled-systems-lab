"""Saved-only OPT-11 report renderer/validator; never invokes the measured executable."""
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
    from .collect import SOURCE_PATHS, digest
    from .oracle import FIXTURES, fixture_digest, require
    from .validate import validate_stream
else:
    from collect import SOURCE_PATHS, digest
    from oracle import FIXTURES, fixture_digest, require
    from validate import validate_stream

SCHEMA = "csl.opt11-recursive-hull-report/1"
MANIFEST_SCHEMA = "csl.opt11-native-manifest/1"
FILES = {"records.json", "collection.json", "raw-stdout.jsonl", "raw-stderr.txt",
         "release-build-log-sanitized.txt", "functional-validation.json", "trials.csv",
         "summary.csv", "latency.svg", "compiler-identification.cmake", "index.html"}
TRIAL_FIELDS = ("fixture", "round", "warmup", "recursive_first", "baseline_ns", "recursive_ns",
                "paired_delta_recursive_minus_baseline_ns", "baseline_lp_calls", "recursive_lp_calls",
                "leaf_lp_calls", "merge_lp_calls", "peak_merge_points", "concurrent_child_subtrees",
                "parallel_overhead_microseconds", "baseline_status", "recursive_status", "status")
SUMMARY_FIELDS = ("fixture", "points", "measured_pairs", "baseline_median_ns", "baseline_min_ns",
                  "baseline_max_ns", "recursive_median_ns", "recursive_min_ns", "recursive_max_ns",
                  "median_paired_delta_recursive_minus_baseline_ns", "failed_pairs")


def json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows, fields) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def read_collection(directory: Path, allow_test=False):
    meta = json.loads((directory / "collection.json").read_text(encoding="utf-8"))
    require(meta.get("purpose") == "measurement" or (allow_test and meta.get("purpose") == "test"),
            "only measured collections are admitted; explicit test gate applies to tests")
    require(meta.get("fixture_sha256") == fixture_digest(), "fixture catalogue digest mismatch")
    require(set(meta.get("source_sha256", {})) == set(SOURCE_PATHS), "source file inventory changed")
    require(all(len(value) == 64 for value in meta["source_sha256"].values()), "invalid source digest")
    require(meta.get("harness_sha256") == meta["source_sha256"].get(
        "reports/algorithm-results/tooling/opt11/recursive_hull_driver.cpp"), "harness source identity mismatch")
    require(meta.get("description", {}).get("source_commit") == meta.get("source_commit") and
            meta["description"].get("harness_sha256") == meta["harness_sha256"] and
            meta["description"].get("configuration") == "Release" and
            meta["description"].get("ndebug") is True and
            meta["description"].get("cxx_standard", 0) >= 202002,
            "embedded executable identity or Release description mismatch")
    description_backend = meta["description"].get("backend")
    backend = meta.get("backend", {})
    require(isinstance(description_backend, dict) and
            backend.get("method") == description_backend.get("method") == "csl.lp.highs" and
            backend.get("version") == description_backend.get("version") == "1.0.0+highs.1.11.0" and
            backend.get("configured_threads") == 1 and backend.get("presolve") == "off" and
            backend.get("parallel") == "off" and backend.get("observed_native_threads") is None,
            "saved backend record differs from executable's runtime registration/configuration")
    protocol = meta.get("protocol", {})
    require(protocol.get("warmups_per_fixture") == 1 and protocol.get("measured_pairs_per_fixture") == 6,
            "paired protocol differs")
    raw = (directory / "raw-stdout.jsonl").read_bytes()
    err = (directory / "raw-stderr.txt").read_bytes()
    log = (directory / "release-build-log-sanitized.txt").read_bytes()
    require(digest(raw) == meta.get("raw_stdout_sha256") and digest(err) == meta.get("raw_stderr_sha256"),
            "raw byte hashes differ from collection-time hashes")
    require(digest(log) == meta.get("sanitized_build_log_sha256"), "sanitized Release log hash mismatch")
    compiler_source = (directory / "compiler-identification.cmake").read_bytes()
    compiler_text = compiler_source.decode("utf-8")
    require(digest(compiler_source) == meta.get("compiler_identification_sha256"),
            "sanitized compiler identification hash mismatch")
    require(isinstance(meta.get("compiler_identification_source_sha256"), str) and
            len(meta["compiler_identification_source_sha256"]) == 64,
            "generated compiler source hash is missing")
    compiler = meta.get("release_project", {})
    require(compiler.get("compiler_id") is not None and compiler.get("compiler_version") is not None and
            isinstance(compiler.get("compiler_path_sha256"), str) and
            re.fullmatch(r"[0-9a-f]{64}", compiler["compiler_path_sha256"]) is not None and
            "compiler_path" not in compiler and
            f'set(CMAKE_CXX_COMPILER_ID "{compiler["compiler_id"]}")' in compiler_text and
            f'set(CMAKE_CXX_COMPILER_VERSION "{compiler["compiler_version"]}")' in compiler_text,
            "compiler identity differs from retained CMake compiler source")
    require(meta.get("process_outcome") == "completed" and meta.get("process_exit_code") == 0,
            "failed or timed-out process bytes are retained but cannot form a completed report")
    validation = validate_stream(directory / "raw-stdout.jsonl", "measurement")
    saved = json.loads((directory / "functional-validation.json").read_text(encoding="utf-8"))
    require(validation == saved == meta.get("validation"), "independent validation result differs")
    machine_load = meta.get("environment", {}).get("machine_load")
    require(isinstance(machine_load, dict) and
            {"before", "after", "process_cpu_deltas"} <= set(machine_load),
            "before/after machine-load and process-CPU snapshots are missing")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    return meta, rows, validation


def make_record(directory: Path, allow_test=False):
    meta, rows, validation = read_collection(directory, allow_test)
    calls = {(row["fixture"], row["round"], row["method"]): row for row in rows if row["kind"] == "call"}
    pairs = {(row["fixture"], row["round"]): row for row in rows if row["kind"] == "pair"}
    trials = []
    summary = []
    for fixture, cloud in FIXTURES.items():
        for round_id in range(0, 7):
            r, p = calls[(fixture, round_id, "recursive")], pairs[(fixture, round_id)]
            base = calls[(fixture, round_id, "baseline")]
            metrics = r.get("recursive") or {}
            trials.append({"fixture": fixture, "round": round_id, "warmup": round_id == 0,
                           "recursive_first": p["recursive_first"], "baseline_ns": base["elapsed_ns"],
                           "recursive_ns": r["elapsed_ns"],
                           "paired_delta_recursive_minus_baseline_ns": r["elapsed_ns"] - base["elapsed_ns"],
                           "baseline_lp_calls": base["lp_calls"], "recursive_lp_calls": r["lp_calls"],
                           "leaf_lp_calls": metrics.get("leaf_lp_calls"), "merge_lp_calls": metrics.get("merge_lp_calls"),
                           "peak_merge_points": metrics.get("peak_merge_points"),
                           "concurrent_child_subtrees": metrics.get("concurrent_child_subtrees"),
                           "parallel_overhead_microseconds": metrics.get("parallel_overhead_microseconds"),
                           "baseline_status": base["status"], "recursive_status": r["status"],
                           "status": "complete" if base["status"] == r["status"] == "complete" else "incomplete"})
        batch = [row for row in trials if row["fixture"] == fixture and not row["warmup"]]
        baseline_values = [row["baseline_ns"] for row in batch]
        recursive_values = [row["recursive_ns"] for row in batch]
        deltas = [row["paired_delta_recursive_minus_baseline_ns"] for row in batch]
        summary.append({"fixture": fixture, "points": len(cloud), "measured_pairs": len(batch),
                        "baseline_median_ns": statistics.median(baseline_values),
                        "baseline_min_ns": min(baseline_values), "baseline_max_ns": max(baseline_values),
                        "recursive_median_ns": statistics.median(recursive_values),
                        "recursive_min_ns": min(recursive_values), "recursive_max_ns": max(recursive_values),
                        "median_paired_delta_recursive_minus_baseline_ns": statistics.median(deltas),
                        "failed_pairs": sum(row["status"] != "complete" for row in batch)})
    payload = {"schema": SCHEMA, "purpose": meta["purpose"], "source_commit": meta["source_commit"],
               "source_sha256": meta["source_sha256"], "fixture_sha256": meta["fixture_sha256"],
               "algorithm": meta["algorithm"], "backend": meta["backend"],
               "environment": meta["environment"], "release_project": meta["release_project"],
               "protocol": meta["protocol"], "validation": validation, "trials": trials, "summary": summary,
               "evidence_scope": "Exact dyadic deletion certificates and exact two-dimensional hull equivalence on three fixed finite binary64 point clouds.",
               "performance_interpretation": (
                   f"Six alternating paired attempts per fixture; {validation['noncomplete_calls']} of "
                   f"{validation['calls']} reducer calls were not complete. The timing summary includes "
                   "every pair, including incomplete outcomes; interpretation is inconclusive with no "
                   "universal speedup or scalability claim."),
               "unavailable_counters": meta["protocol"]["unavailable"],
               "collection_hashes": {"raw_stdout_sha256": meta["raw_stdout_sha256"],
                                     "raw_stderr_sha256": meta["raw_stderr_sha256"],
                                     "sanitized_build_log_sha256": meta["sanitized_build_log_sha256"],
                                     "executable_sha256": meta["executable_sha256"]}}
    payload_hash = digest(json_bytes(payload))
    return {**payload, "report_id": "opt11-" + payload_hash[:16], "payload_sha256": payload_hash}


def svg(record):
    rows = record["summary"]
    ceiling = max(1, max(row["baseline_max_ns"] for row in rows), max(row["recursive_max_ns"] for row in rows))
    shapes = ['<text x="210" y="20">Median duration (nanoseconds)</text>']
    for step in range(5):
        x = 210 + 520 * step / 4
        value = round(ceiling * step / 4)
        shapes.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="34" y2="236" stroke="#d9e2e7"/>'
                      f'<text x="{x:.1f}" y="250" text-anchor="middle">{value}</text>')
    for index, row in enumerate(rows):
        y = 50 + index * 64
        for name, color, key in (("baseline", "#376b89", "baseline_median_ns"),
                                 ("recursive", "#bd5a37", "recursive_median_ns")):
            width = 520 * row[key] / ceiling
            shapes.append(f'<text x="12" y="{y + (0 if name == "baseline" else 22)}">{html.escape(row["fixture"])} {name}</text>'
                          f'<rect x="210" y="{y - 14 + (0 if name == "baseline" else 22)}" width="{width:.3f}" height="14" fill="{color}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc" viewBox="0 0 760 260">'
            '<title id="title">OPT-11 paired median call durations</title><desc id="desc">Descriptive medians of six alternating paired calls per fixture. No speedup claim.</desc>'
            '<style>text{font:12px system-ui,sans-serif;fill:#172b36}</style>' + ''.join(shapes) + '</svg>')


def page(record):
    esc = lambda x: html.escape(str(x), quote=True)
    summary_rows = "".join("<tr>" + "".join(f"<td>{esc(row[k])}</td>" for k in SUMMARY_FIELDS) + "</tr>"
                           for row in record["summary"])
    trial_rows = "".join("<tr>" + "".join(f"<td>{esc(row[k])}</td>" for k in TRIAL_FIELDS) + "</tr>"
                         for row in record["trials"])
    th = lambda fields: "".join(f"<th scope=\"col\">{esc(k)}</th>" for k in fields)
    env = record["environment"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPT-11 recursive hull report</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:78rem;margin:2rem auto;padding:0 1rem;color:#172b36}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{border:1px solid #bbc9d0;padding:.35rem;text-align:left}}code{{overflow-wrap:anywhere}}svg{{max-width:100%}}</style></head><body>
<h1>OPT-11 recursive split-and-merge hull reduction</h1><p>Native record <code>{esc(record['report_id'])}</code>; measured source commit <code>{esc(record['source_commit'])}</code>. Schema <code>{SCHEMA}</code>.</p>
<p>Three fixed two-dimensional signed, duplicate and affine-degenerate fixtures. All {record['validation']['exact_certificates']} emitted deletion certificates passed exact dyadic validation; literal monotone-chain hulls and retained sets were checked independently where reducer output was available. {record['validation']['noncomplete_calls']} of {record['validation']['calls']} calls were incomplete or diagnostic, and remain visible in the trial table and raw rows. {esc(record['evidence_scope'])}</p>
<h2>Paired observations</h2><figure>{svg(record)}<figcaption>Median public-call duration in nanoseconds. Six alternating paired observations per fixture; each axis starts at zero. The table retains individual observations.</figcaption></figure>
<table><thead><tr>{th(SUMMARY_FIELDS)}</tr></thead><tbody>{summary_rows}</tbody></table>
<h2>All paired trials</h2><table><thead><tr>{th(TRIAL_FIELDS)}</tr></thead><tbody>{trial_rows}</tbody></table>
<p>Performance interpretation: {esc(record['performance_interpretation'])}. Timing is one public registered <code>run_with</code> call. Fixture parsing, reducer/injected-workspace creation, exact validation, serialization and rendering are excluded; recursive child LP-workspace creation and root task scheduling are included. Backend phase times, native thread count, CPU time, peak memory and source-mapped limiter are unavailable.</p>
<p>LP backend: <code>{esc(record['backend']['method'])}</code> version <code>{esc(record['backend']['version'])}</code>, reported by the executable's registered LP provider. Configured threads: {esc(record['backend']['configured_threads'])}; presolve: {esc(record['backend']['presolve'])}; parallel mode: {esc(record['backend']['parallel'])}. Observed native thread count remains unavailable.</p>
<p>Host: {esc(env['os'])}; machine {esc(env['machine'])}; logical processors {esc(env['logical_processors'])}. Compiler: {esc(record['release_project']['compiler_id'])} {esc(record['release_project']['compiler_version'])}; C++ setting {esc(record['release_project']['language_standard'])}, optimization {esc(record['release_project']['optimization'])}, NDEBUG enabled. Concurrent work: {esc(env['concurrent_work_note'])}. Machine-load and process-CPU snapshots: <code>{esc(json.dumps(env.get('machine_load', {}), sort_keys=True))}</code>. Full sanitized Release and compiler evidence are in <a href="release-build-log-sanitized.txt">the build log</a> and <a href="compiler-identification.cmake">CMake compiler identification</a>.</p>
<h2>Saved evidence</h2><ul><li><a href="records.json">Typed records</a></li><li><a href="collection.json">Collection provenance</a></li><li><a href="raw-stdout.jsonl">Raw JSONL</a></li><li><a href="raw-stderr.txt">Raw stderr bytes</a></li><li><a href="functional-validation.json">Independent validation</a></li><li><a href="compiler-identification.cmake">Compiler identification</a></li><li><a href="trials.csv">Trial CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="latency.svg">SVG figure</a></li><li><a href="manifest.json">Native manifest</a></li></ul>
<p>Performance is exploratory and fixture-limited. No universal speedup, scalability, or correctness claim for arbitrary point clouds follows.</p></body></html>'''


def zip_bytes(bundle: Path):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(FILES | {"manifest.json"}):
            info = zipfile.ZipInfo(f"{bundle.name}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (bundle / name).read_bytes())
    return out.getvalue()


def build(collection: Path, out_root: Path, allow_test=False):
    record = make_record(collection, allow_test)
    bundle = out_root / record["report_id"]
    archive = out_root / (bundle.name + ".source.zip")
    require(not bundle.exists() and not archive.exists(), "immutable report destination already exists")
    files = {name: (collection / name).read_bytes() for name in
             ("collection.json", "raw-stdout.jsonl", "raw-stderr.txt", "release-build-log-sanitized.txt", "functional-validation.json", "compiler-identification.cmake")}
    files.update({"records.json": json_bytes(record),
                  "trials.csv": csv_bytes(record["trials"], TRIAL_FIELDS),
                  "summary.csv": csv_bytes(record["summary"], SUMMARY_FIELDS),
                  "latency.svg": svg(record).encode(), "index.html": page(record).encode()})
    manifest = {"schema": MANIFEST_SCHEMA, "report_id": record["report_id"],
                "files": {name: digest(files[name]) for name in sorted(files)}}
    bundle.mkdir(parents=True)
    for name, content in files.items(): (bundle / name).write_bytes(content)
    (bundle / "manifest.json").write_bytes(json_bytes(manifest))
    archive.write_bytes(zip_bytes(bundle))
    check(bundle, allow_test)
    return bundle


def check(bundle: Path, allow_test=False):
    require(bundle.is_dir() and not bundle.is_symlink(), "bundle directory required")
    require({p.name for p in bundle.iterdir()} == FILES | {"manifest.json"}, "bundle inventory differs")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA and manifest.get("report_id") == bundle.name and
            set(manifest.get("files", {})) == FILES, "manifest inventory differs")
    for name in FILES:
        require(digest((bundle / name).read_bytes()) == manifest["files"][name], f"hash mismatch: {name}")
    record = make_record(bundle, allow_test)
    require(record["report_id"] == bundle.name and (bundle / "records.json").read_bytes() == json_bytes(record),
            "typed report differs from retained raw bytes")
    expected = {"trials.csv": csv_bytes(record["trials"], TRIAL_FIELDS),
                "summary.csv": csv_bytes(record["summary"], SUMMARY_FIELDS),
                "latency.svg": svg(record).encode(), "index.html": page(record).encode()}
    for name, value in expected.items(): require((bundle / name).read_bytes() == value, f"projection mismatch: {name}")
    archive = bundle.parent / (bundle.name + ".source.zip")
    require(archive.is_file() and archive.read_bytes() == zip_bytes(bundle), "offline ZIP mismatch")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    p = subs.add_parser("build"); p.add_argument("--collection", type=Path, required=True); p.add_argument("--out-root", type=Path, required=True)
    c = subs.add_parser("check"); c.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "build": result = build(args.collection, args.out_root)
    else: result = args.bundle; check(result)
    print(json.dumps({"report_id": result.name, "status": "saved_report_valid"}, sort_keys=True))


if __name__ == "__main__": main()

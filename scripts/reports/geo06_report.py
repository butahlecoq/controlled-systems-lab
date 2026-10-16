#!/usr/bin/env python3
"""Collect and render a descriptive GEO-06 QuickHull report from saved rows."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from pathlib import Path

SCHEMA = "csl.geo06-quickhull-report/1"
SOURCE = "ce63bff5a0face88c3c5e977f7d96337e8cbe948"
CASES = {
    "square_duplicates": {"points": [[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5], [0, 0], [1, 0]], "indices": "0:1:2:3"},
    "collinear_endpoints": {"points": [[2, 2], [0, 0], [1, 1], [3, 3], [2, 2]], "indices": "1:3"},
    "skinny_triangle": {"points": [[0, 0], [1, 0], [1, 2**-50], [0.5, 2**-52]], "indices": "0:1:2"},
}
ORDER = tuple(CASES)
FIELDS = ("scenario", "repetition", "warmup", "calls", "duration_ns", "status", "observed_vertices", "indices")
ALLOWED = {"CMakeLists.txt", "cmake/OptionalReports.cmake", "benchmarks/reporting/geo06/quickhull_driver.cpp",
           "scripts/reports/geo06_report.py", "reports/algorithm-results/tooling/geo06/README.md",
           "tests/reporting/test_geo06_report.py"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def rows_from_text(source):
    reader = csv.DictReader(io.StringIO(source))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("driver CSV columns differ")
    rows = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("malformed driver row")
        for key in ("repetition", "warmup", "calls", "duration_ns", "observed_vertices"):
            row[key] = int(row[key])
        rows.append(row)
    return rows


def validate_rows(rows, repetitions, warmups, calls):
    if not isinstance(rows, list) or not isinstance(repetitions, int) or repetitions < 7 or warmups != 1 or calls < 1:
        raise ValueError("publication needs seven repetitions, one warmup and positive calls")
    expected = [(name, 0, 1) for name in ORDER]
    expected += [(name, rep, 0) for rep in range(repetitions)
                 for name in (ORDER if rep % 2 == 0 else ORDER[::-1])]
    if len(rows) != len(expected):
        raise ValueError("missing or extra trial")
    for row, identity in zip(rows, expected):
        if (row["scenario"], row["repetition"], row["warmup"]) != identity:
            raise ValueError("trial order or identity differs")
        if row["calls"] != calls or row["duration_ns"] < 0:
            raise ValueError("invalid call count or duration")
        fixture = CASES[row["scenario"]]
        if (row["status"] != "passed" or row["indices"] != fixture["indices"] or
                row["observed_vertices"] != calls * len(fixture["indices"].split(":"))):
            raise ValueError("QuickHull output or work count differs from analytic fixture")


def summarize(rows):
    result = {}
    for name in ORDER:
        values = [row["duration_ns"] for row in rows if row["scenario"] == name and row["warmup"] == 0]
        result[name] = {"trials": len(values), "median_batch_ns": statistics.median(values),
                        "min_batch_ns": min(values), "max_batch_ns": max(values)}
    return result


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs)


def validate(record):
    if record.get("schema") != SCHEMA or record.get("purpose") != "measurement":
        raise ValueError("unregistered report schema or purpose")
    unsigned = {k: v for k, v in record.items() if k not in ("report_id", "payload_sha256")}
    sha = digest(unsigned)
    if record.get("payload_sha256") != sha or record.get("report_id") != "geo06-" + sha[:16]:
        raise ValueError("record identity differs")
    if record.get("source_commit") != SOURCE or not re.fullmatch(r"[0-9a-f]{40}", record.get("harness_commit", "")):
        raise ValueError("source or harness identity differs")
    if record.get("catalog") != CASES or record.get("interval") != "each batch of fresh QuickHull calls, including result observation; excludes process startup, JSON/CSV, and verification":
        raise ValueError("catalog or interval differs")
    rows = record["rows"]
    validate_rows(rows, record["repetitions"], record["warmups"], record["calls_per_trial"])
    if record.get("summary") != summarize(rows):
        raise ValueError("summary differs from all raw rows")
    if record.get("process_exit_code") != 0 or record.get("stderr") != "":
        raise ValueError("failed driver process is not publishable")
    return record


def render_html(record):
    validate(record)
    items = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>GEO-06 QuickHull results</title></head><body>",
             "<h1>GEO-06 geometric QuickHull: analytic microfixtures</h1>",
             "<p>Descriptive single-adapter Release measurements. No competitor, speedup, application throughput, or scalability claim. Orientation is exact only for supplied binary64 coordinates. These fixtures are not a general correctness proof.</p>",
             f"<p>Source commit <code>{record['source_commit']}</code>; harness commit <code>{record['harness_commit']}</code>; report <code>{record['report_id']}</code>.</p>",
             f"<p>{record['repetitions']} measured batches per fixture, {record['calls_per_trial']} QuickHull calls per batch, {record['warmups']} excluded warmup. Interleaved forward/reverse case order. Each batch constructs its result and observes every returned index. Timings use steady-clock nanoseconds; no profile or limiter attribution was collected.</p>",
             f"<table><caption>Batch latency; {record['repetitions']} measurements per fixture</caption><thead><tr><th>Fixture</th><th>Points</th><th>Hull indices</th><th>Median ns</th><th>Range ns</th></tr></thead><tbody>"]
    for name in ORDER:
        data = record["summary"][name]
        fixture = CASES[name]
        items.append(f"<tr><th>{html.escape(name)}</th><td>{len(fixture['points'])}</td><td>{fixture['indices']}</td><td>{data['median_batch_ns']}</td><td>{data['min_batch_ns']}–{data['max_batch_ns']}</td></tr>")
    items.extend(["</tbody></table>", f"<p>All {len(record['rows']) - len(ORDER)} measured batches passed the literal vertex-index oracle. The saved CSV retains every warmup and measured row. Observed OS thread count, per-call memory, and internal phase timings are unavailable.</p>",
                  "<p><a href=\"records.json\">Saved JSON</a> · <a href=\"trials.csv\">Raw trial CSV</a> · <a href=\"manifest.json\">File hashes</a></p>",
                  "<h2>Environment</h2><pre>", html.escape(json.dumps(record["environment"], indent=2, ensure_ascii=False)),
                  "</pre></body></html>"])
    return "\n".join(items) + "\n"


def collect(args):
    if git("rev-parse", "HEAD") != args.harness_commit:
        raise ValueError("harness commit differs from checkout")
    if git("status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("tracked source tree must be clean")
    if args.source_commit != SOURCE:
        raise ValueError("unreviewed algorithm source commit")
    changed = set(git("diff", "--name-only", SOURCE, args.harness_commit).splitlines())
    if not changed <= ALLOWED:
        raise ValueError("source changed outside report harness: " + repr(sorted(changed - ALLOWED)))
    exe = args.exe.resolve(strict=True)
    build_dir = args.build_dir.resolve(strict=True)
    if exe.parent != build_dir / "Release":
        raise ValueError("executable does not belong to configured build directory")
    if "Release" not in exe.parts or not exe.name.startswith("csl_geo06_quickhull_report"):
        raise ValueError("only the Release report executable is admissible")
    if args.out.exists():
        raise ValueError("report destination must be new")
    cache = (args.build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    if "CSL_BUILD_GEO06_REPORT:BOOL=ON" not in cache or "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" not in cache:
        raise ValueError("configured build identity differs")
    source_dir = next((line.split("=", 1)[1] for line in cache.splitlines()
                       if line.startswith("CSL_SOURCE_DIR:STATIC=")), None)
    if source_dir and Path(source_dir).resolve() != Path.cwd().resolve():
        raise ValueError("configured source directory differs")
    cmake = next((line.split("=", 1)[1] for line in cache.splitlines()
                  if line.startswith("CMAKE_COMMAND:INTERNAL=")), None)
    if not cmake:
        raise ValueError("configured CMake command unavailable")
    build = subprocess.run([cmake, "--build", str(build_dir), "--config", "Release",
                            "--target", "csl_geo06_quickhull_report", "--parallel", "4"],
                           capture_output=True, text=True, timeout=300, check=False)
    if build.returncode:
        raise ValueError("final Release build failed: " + build.stderr[-500:])
    result = subprocess.run([str(exe), "--measure", str(args.repetitions), "1", str(args.calls)],
                            capture_output=True, text=True, timeout=300, check=False)
    rows = rows_from_text(result.stdout)
    validate_rows(rows, args.repetitions, 1, args.calls)
    if result.returncode or result.stderr:
        raise ValueError("driver failed; preserve stdout/stderr separately before retrying")
    note = args.concurrent_work.read_text(encoding="utf-8")
    compiler_files = list((build_dir / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("CMake compiler identity unavailable")
    compiler_text = compiler_files[0].read_text(encoding="utf-8")
    compiler_match = re.search(r'^set\(CMAKE_CXX_COMPILER "([^"]+)"\)$', compiler_text, re.M)
    version_match = re.search(r'^set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)$', compiler_text, re.M)
    if not compiler_match or not version_match:
        raise ValueError("CMake compiler identity malformed")
    environment = {"os": platform.platform(), "cpu": platform.processor(), "logical_cores": os.cpu_count(),
                   "python": platform.python_version(), "compiler": compiler_match.group(1),
                   "compiler_version": version_match.group(1), "build": "Release / NDEBUG / C++20",
                   "native_thread_count": {"available": False, "reason": "not observed"},
                   "concurrent_work": note, "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                   "cmake_cache_sha256": hashlib.sha256(cache.encode()).hexdigest(),
                   "final_build_exit_code": build.returncode}
    record = {"schema": SCHEMA, "purpose": "measurement", "source_commit": SOURCE,
              "harness_commit": args.harness_commit, "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "catalog": CASES, "repetitions": args.repetitions, "warmups": 1,
              "calls_per_trial": args.calls, "rows": rows, "summary": summarize(rows),
              "process_exit_code": result.returncode, "stderr": result.stderr,
              "interval": "each batch of fresh QuickHull calls, including result observation; excludes process startup, JSON/CSV, and verification",
              "environment": environment, "raw_csv_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}
    sha = digest(record)
    record["payload_sha256"] = sha
    record["report_id"] = "geo06-" + sha[:16]
    validate(record)
    args.out.mkdir(parents=True)
    (args.out / "records.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (args.out / "trials.csv").write_text(result.stdout, encoding="utf-8")
    (args.out / "index.html").write_text(render_html(record), encoding="utf-8")
    redacted_build = build.stdout
    for path, label in ((build_dir, "BUILD_ROOT"), (Path.cwd(), "SOURCE_ROOT"), (Path.home(), "USER_HOME")):
        redacted_build = redacted_build.replace(str(path), label).replace(str(path).replace("\\", "/"), label)
    (args.out / "build-log.txt").write_text(redacted_build, encoding="utf-8")
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.out.iterdir() if p.is_file()}
    (args.out / "manifest.json").write_text(json.dumps({"schema": "csl.geo06-report-manifest/1", "report_id": record["report_id"], "files": files}, indent=2) + "\n", encoding="utf-8")
    print(record["report_id"])


def check(args):
    record = validate(strict_json(args.bundle / "records.json"))
    raw = (args.bundle / "trials.csv").read_text(encoding="utf-8")
    if hashlib.sha256(raw.encode()).hexdigest() != record["raw_csv_sha256"] or rows_from_text(raw) != record["rows"]:
        raise ValueError("raw CSV differs from saved rows")
    if (args.bundle / "index.html").read_text(encoding="utf-8") != render_html(record):
        raise ValueError("HTML differs from saved rows")
    manifest = strict_json(args.bundle / "manifest.json")
    if manifest.get("schema") != "csl.geo06-report-manifest/1" or manifest.get("report_id") != record["report_id"]:
        raise ValueError("manifest identity differs")
    if set(manifest["files"]) != {"records.json", "trials.csv", "index.html", "build-log.txt"}:
        raise ValueError("manifest inventory differs")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((args.bundle / name).read_bytes()).hexdigest() != expected:
            raise ValueError("bundle file hash differs: " + name)
    print(record["report_id"] + ": saved data and HTML verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    collection = sub.add_parser("collect")
    collection.add_argument("--exe", type=Path, required=True)
    collection.add_argument("--build-dir", type=Path, required=True)
    collection.add_argument("--source-commit", required=True)
    collection.add_argument("--harness-commit", required=True)
    collection.add_argument("--concurrent-work", type=Path, required=True)
    collection.add_argument("--repetitions", type=int, default=7)
    collection.add_argument("--calls", type=int, default=1000)
    collection.add_argument("--out", type=Path, required=True)
    verification = sub.add_parser("check")
    verification.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        collect(args) if args.action == "collect" else check(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"GEO-06 report: {error}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Collect and render a fixed-source, descriptive B08 exact-reference report."""
from __future__ import annotations

import argparse
import base64
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
import time
import zipfile
from pathlib import Path

SOURCE = "78212b21d42ec3f136f0e1c72b2b0861d306792c"
CHECKER = Path("docs/research/tools/check_b08_displayed_exact.py")
REFERENCE = Path("docs/research/evidence/b08-displayed-exact.json")
EXPECTED_OUTPUT = "B08 exact displayed-data record verified"
SCHEMA = "csl.b08-displayed-exact-report/1"
INTERVAL = ("parent perf_counter_ns immediately before child process spawn through child exit and "
            "captured stdout/stderr return; includes CPython startup, 625x256 exact rational "
            "enumeration, literal checks and record comparison; excludes parent validation, "
            "CSV/JSON persistence, HTML rendering and ZIP creation")
ALLOWED = {"scripts/reports/b08_exact_report.py",
           "reports/algorithm-results/tooling/b08_exact/README.md",
           "tests/reporting/test_b08_exact_report.py"}
SOURCE_FILE_HASHES = {
    CHECKER.as_posix(): "5a84edcf9a9761d5a7b8036417546d71160fe8d74eb800e651aad3edfe081866",
    REFERENCE.as_posix(): "dc8fbb816f359d132284fa92c8289b87a4cd7804270aa35fab926cdeb90e3e0a",
}
FIELDS = ("repetition", "warmup", "status", "duration_ns", "exit_code", "timed_out",
          "work_observed", "stdout_sha256", "stderr_sha256", "detail")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def strict_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def source_identity(root: Path, harness_commit: str) -> dict:
    if git("-C", str(root), "rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness commit differs from checked-out HEAD")
    if git("-C", str(root), "status", "--porcelain=v1"):
        raise ValueError("harness worktree must be clean")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", SOURCE,
                       harness_commit], check=False).returncode:
        raise ValueError("source commit is not an ancestor of harness commit")
    changed = set(git("-C", str(root), "diff", "--name-only", SOURCE, harness_commit).splitlines())
    if not changed <= ALLOWED:
        raise ValueError("unreviewed source delta: " + repr(sorted(changed - ALLOWED)))
    identities = {}
    for path in (CHECKER, REFERENCE):
        committed = git_bytes("-C", str(root), "show", f"{SOURCE}:{path.as_posix()}")
        local = (root / path).read_bytes()
        if local != committed:
            raise ValueError("fixed B08 source differs: " + path.as_posix())
        identities[path.as_posix()] = sha(local)
    if identities != SOURCE_FILE_HASHES:
        raise ValueError("fixed B08 source digest differs from reviewed literal")
    reference = strict_json(root / REFERENCE)
    if (reference.get("minimum_squared_exact") != "112730080707/25000000" or
            reference.get("plan_count") != 625 or
            reference.get("disturbance_corner_count_per_plan") != 256 or
            len(reference.get("exact_minimizers", [])) != 3):
        raise ValueError("B08 reference identity changed")
    return {"source_commit": SOURCE, "harness_commit": harness_commit,
            "source_files_sha256": identities,
            "source_tree_oid": git("-C", str(root), "rev-parse", f"{SOURCE}^{{tree}}"),
            "harness_tree_oid": git("-C", str(root), "rev-parse", f"{harness_commit}^{{tree}}"),
            "reviewed_harness_delta": sorted(changed)}


def expected_identities(repetitions: int) -> list[tuple[int, bool]]:
    return [(0, True)] + [(i, False) for i in range(repetitions)]


def validate_rows(rows: list[dict], repetitions: int) -> None:
    if not isinstance(repetitions, int) or repetitions < 7 or len(rows) != repetitions + 1:
        raise ValueError("expected one warmup and at least seven measured trials")
    for row, (index, warmup) in zip(rows, expected_identities(repetitions)):
        if set(row) != set(FIELDS) | {"stdout_base64", "stderr_base64"}:
            raise ValueError("trial fields differ")
        if row["repetition"] != index or row["warmup"] is not warmup:
            raise ValueError("trial order or identity differs")
        if (not isinstance(row["duration_ns"], int) or row["duration_ns"] < 0 or
                not isinstance(row["timed_out"], bool) or
                not isinstance(row["work_observed"], bool)):
            raise ValueError("invalid duration or observation")
        try:
            stdout = base64.b64decode(row["stdout_base64"], validate=True)
            stderr = base64.b64decode(row["stderr_base64"], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("invalid raw process output encoding") from error
        if sha(stdout) != row["stdout_sha256"] or sha(stderr) != row["stderr_sha256"]:
            raise ValueError("raw process output hash differs")
        passed = (row["exit_code"] == 0 and not row["timed_out"] and
                  stdout.strip() == EXPECTED_OUTPUT.encode("ascii") and stderr == b"")
        if row["status"] != ("passed" if passed else "failed") or row["work_observed"] != passed:
            raise ValueError("process status or work evidence differs")


def summary(rows: list[dict]) -> dict | None:
    if any(row["status"] != "passed" for row in rows):
        return None
    values = [row["duration_ns"] for row in rows if not row["warmup"]]
    return {"trials": len(values), "median_ns": statistics.median(values),
            "min_ns": min(values), "max_ns": max(values)}


def validate_record(record: dict) -> dict:
    if record.get("schema") != SCHEMA or record.get("purpose") != "measurement":
        raise ValueError("unregistered B08 report schema or purpose")
    unsigned = {key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")}
    digest = sha(canonical(unsigned))
    if record.get("payload_sha256") != digest or record.get("report_id") != "b08-exact-" + digest[:16]:
        raise ValueError("content-bound report identity differs")
    if record.get("source", {}).get("source_commit") != SOURCE or record.get("interval") != INTERVAL:
        raise ValueError("source or interval differs")
    source = record["source"]
    if (not re.fullmatch(r"[0-9a-f]{40}", source.get("harness_commit", "")) or
            source.get("source_files_sha256") != SOURCE_FILE_HASHES or
            source.get("reviewed_harness_delta") != sorted(ALLOWED) or
            not re.fullmatch(r"[0-9a-f]{40}", source.get("source_tree_oid", "")) or
            not re.fullmatch(r"[0-9a-f]{40}", source.get("harness_tree_oid", ""))):
        raise ValueError("fixed source and harness identity differs")
    if record.get("reference") != {"source_id": "L04", "source_sha256": "6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f",
                                   "plan_count": 625, "corner_histories_per_plan": 256,
                                   "minimum_squared_exact": "112730080707/25000000", "exact_minimizers": 3}:
        raise ValueError("numeric reference differs")
    rows = record["rows"]
    if record.get("warmups") != 1 or not isinstance(record.get("timeout_seconds"), int):
        raise ValueError("warmup or timeout policy differs")
    validate_rows(rows, record["repetitions"])
    if record.get("summary") != summary(rows) or record.get("publishable") != (record["summary"] is not None):
        raise ValueError("summary or publication status differs from complete attempts")
    if record["environment"].get("optimization") != "CPython -O; -B disables bytecode writes":
        raise ValueError("Python optimization scope differs")
    return record


def render_html(record: dict) -> str:
    validate_record(record)
    data = record["summary"]
    if data is None:
        raise ValueError("failed collection cannot be published")
    rows = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>B08 displayed-data exact reference</title></head><body>",
            "<h1>B08 displayed-data exact reference</h1>",
            "<p>Descriptive single-checker Python measurements. This is the printed rounded linear model, not the historical MATLAB run, nonlinear plant or a complete optimal-control family. No comparator, speedup or source-mapped limiter was measured; performance interpretation is inconclusive.</p>",
            f"<p>Source commit <code>{record['source']['source_commit']}</code>; harness commit <code>{record['source']['harness_commit']}</code>; report <code>{record['report_id']}</code>.</p>",
            "<p>Exact worst-case squared norm: <code>112730080707/25000000</code>, or about 67.1506011014 as a norm. Three plans tie exactly under printed rational inputs. The article reports 67.12 separately.</p>",
            f"<p>{record['repetitions']} measured fresh child processes and one excluded warmup. {html.escape(INTERVAL)}. Interpreter startup and output capture are included, so these are process-level times.</p>",
            "<table><caption>Fresh-process latency, nanoseconds</caption><thead><tr><th>Median</th><th>Minimum</th><th>Maximum</th><th>Successful trials</th></tr></thead><tbody>",
            f"<tr><td>{data['median_ns']}</td><td>{data['min_ns']}</td><td>{data['max_ns']}</td><td>{data['trials']}</td></tr></tbody></table>",
            "<p>All attempts, including the excluded warmup, are retained in the raw records. Peak memory, child CPU time and interpreter internal phase timings are unavailable. The host activity note and actual Python executable identity are in the saved record.</p>",
            "<p><a href=\"records.json\">Saved JSON</a> · <a href=\"trials.csv\">Trial CSV</a> · <a href=\"raw-trials.jsonl\">Raw process output and attempts</a> · <a href=\"manifest.json\">File hashes</a></p>",
            "<h2>Environment</h2><pre>", html.escape(json.dumps(record["environment"], indent=2, ensure_ascii=False)),
            "</pre></body></html>"]
    return "\n".join(rows) + "\n"


def csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row[key] for key in FIELDS})
    return stream.getvalue().encode("utf-8")


def save_bytes(path: Path, data: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def source_zip_bytes(bundle: Path) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(bundle.iterdir()):
            entry = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_STORED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    return stream.getvalue()


def run_child(command: list[str], index: int, warmup: bool, timeout: int) -> dict:
    start = time.perf_counter_ns()
    detail = "child failed, timed out, or output differed"
    try:
        process = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        stdout, stderr, exit_code, timed_out = process.stdout, process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b"", error.stderr or b""
        exit_code, timed_out = None, True
    except OSError as error:
        stdout, stderr = b"", b""
        exit_code, timed_out = None, False
        detail = f"child launch/capture failed: {type(error).__name__}: {error}"
    duration = time.perf_counter_ns() - start
    passed = exit_code == 0 and not timed_out and stdout.strip() == EXPECTED_OUTPUT.encode("ascii") and not stderr
    return {"repetition": index, "warmup": warmup, "status": "passed" if passed else "failed",
            "duration_ns": duration, "exit_code": exit_code, "timed_out": timed_out,
            "work_observed": passed, "stdout_sha256": sha(stdout),
            "stderr_sha256": sha(stderr),
            "detail": "exact checker and saved-record comparison passed" if passed else detail,
            "stdout_base64": base64.b64encode(stdout).decode("ascii"),
            "stderr_base64": base64.b64encode(stderr).decode("ascii")}


def collect(args) -> str:
    root = Path(__file__).resolve().parents[2]
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("output directory must be new")
    if args.repetitions < 7 or args.timeout < 1 or args.timeout > 300:
        raise ValueError("require at least seven repetitions and a 1..300 second child timeout")
    note = args.concurrent_work.read_text(encoding="utf-8").strip()
    if len(note) < 10 or "TODO" in note or "TBD" in note:
        raise ValueError("concurrent-work note is missing or unfinished")
    source = source_identity(root, args.harness_commit)
    executable = Path(sys.executable).resolve(strict=True)
    if sys.implementation.name != "cpython" or sys.version_info < (3, 11):
        raise ValueError("reviewed harness requires CPython 3.11 or newer")
    reference = strict_json(root / REFERENCE)
    command = [str(executable), "-B", "-O", str(root / CHECKER), "--verify-record", str(root / REFERENCE)]
    environment = {"os": platform.platform(), "processor": platform.processor() or "unavailable",
                   "logical_cores": os.cpu_count(), "python_version": sys.version,
                   "python_executable": executable.name, "python_executable_sha256": sha(executable.read_bytes()),
                   "optimization": "CPython -O; -B disables bytecode writes",
                   "arithmetic": "fractions.Fraction exact rational on printed decimal inputs",
                   "configured_workers": 1, "observed_threads": {"available": False, "reason": "not measured"},
                   "peak_memory": {"available": False, "reason": "not measured"},
                   "child_cpu_time": {"available": False, "reason": "not measured"},
                   "cache_policy": "new interpreter each attempt; OS file and instruction caches may be warm",
                   "host_activity": note, "clock": "parent time.perf_counter_ns"}
    args.out.mkdir(parents=True)
    rows = []
    raw = args.out / "raw-trials.jsonl"
    for index, warmup in expected_identities(args.repetitions):
        row = run_child(command, index, warmup, args.timeout)
        rows.append(row)
        with raw.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    validate_rows(rows, args.repetitions)
    record = {"schema": SCHEMA, "purpose": "measurement",
              "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "source": source, "reference": {"source_id": reference["source_id"],
              "source_sha256": reference["source_sha256"], "plan_count": 625,
              "corner_histories_per_plan": 256,
              "minimum_squared_exact": reference["minimum_squared_exact"],
              "exact_minimizers": len(reference["exact_minimizers"])},
              "repetitions": args.repetitions, "warmups": 1, "timeout_seconds": args.timeout,
              "interval": INTERVAL, "environment": environment,
              "rows": rows, "summary": summary(rows), "publishable": summary(rows) is not None,
              "raw_jsonl_sha256": sha(raw.read_bytes())}
    digest = sha(canonical(record))
    record["payload_sha256"] = digest
    record["report_id"] = "b08-exact-" + digest[:16]
    validate_record(record)
    save_bytes(args.out / "records.json", (json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    save_bytes(args.out / "trials.csv", csv_bytes(rows))
    if not record["publishable"]:
        save_bytes(args.out / "collection-status.json", (json.dumps({"publishable": False, "reason": "one or more child attempts failed",
            "record_id": record["report_id"]}, indent=2) + "\n").encode("utf-8"))
        raise ValueError("failed B08 attempts retained; publication rejected")
    save_bytes(args.out / "index.html", render_html(record).encode("utf-8"))
    inventory = {path.name: sha(path.read_bytes()) for path in sorted(args.out.iterdir()) if path.is_file()}
    save_bytes(args.out / "manifest.json", (json.dumps({"schema": "csl.b08-report-files/1",
        "report_id": record["report_id"], "files": inventory}, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    save_bytes(args.out.with_suffix(".zip"), source_zip_bytes(args.out))
    return record["report_id"]


def check(bundle: Path) -> str:
    record = validate_record(strict_json(bundle / "records.json"))
    if not record["publishable"]:
        raise ValueError("failed B08 collection is not publishable")
    raw = (bundle / "raw-trials.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    if sha(raw) != record["raw_jsonl_sha256"] or rows != record["rows"]:
        raise ValueError("raw attempts differ from saved record")
    if (bundle / "trials.csv").read_bytes() != csv_bytes(rows):
        raise ValueError("CSV differs from all saved trials")
    if (bundle / "index.html").read_text(encoding="utf-8") != render_html(record):
        raise ValueError("HTML differs from saved record")
    manifest = strict_json(bundle / "manifest.json")
    expected = {"records.json", "trials.csv", "raw-trials.jsonl", "index.html"}
    if manifest.get("schema") != "csl.b08-report-files/1" or manifest.get("report_id") != record["report_id"]:
        raise ValueError("manifest identity differs")
    if set(manifest["files"]) != expected or {p.name for p in bundle.iterdir() if p.is_file()} != expected | {"manifest.json"}:
        raise ValueError("bundle file inventory differs")
    for name, digest in manifest["files"].items():
        if sha((bundle / name).read_bytes()) != digest:
            raise ValueError("bundle file hash differs: " + name)
    if bundle.with_suffix(".zip").read_bytes() != source_zip_bytes(bundle):
        raise ValueError("offline ZIP bytes or metadata differ")
    return record["report_id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    collection = sub.add_parser("collect")
    collection.add_argument("--harness-commit", required=True)
    collection.add_argument("--concurrent-work", type=Path, required=True)
    collection.add_argument("--repetitions", type=int, default=7)
    collection.add_argument("--timeout", type=int, default=60)
    collection.add_argument("--out", type=Path, required=True)
    verification = sub.add_parser("check")
    verification.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "smoke":
            root = args.root.resolve(strict=True)
            result = subprocess.run([sys.executable, "-B", "-O", str(root / CHECKER),
                                     "--verify-record", str(root / REFERENCE)],
                                    capture_output=True, text=True, timeout=60, check=False)
            if result.returncode or result.stdout.strip() != EXPECTED_OUTPUT or result.stderr:
                raise ValueError("B08 exact functional smoke failed")
            print("B08 exact functional smoke passed; timing discarded")
        elif args.action == "collect":
            print(collect(args))
        else:
            print(check(args.bundle))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"B08 report: {error}\n")


if __name__ == "__main__":
    main()

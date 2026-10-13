"""Validated publication adapter for the T-S01 analytic result record."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import csv
from pathlib import Path
from html import escape

import registered_reports as common

KIND = "syn07-ts01-analytic"
FILES = {"README.md", "environment.json", "index.html", "publication-map.json", "raw-events.jsonl", "records.json", "scenarios.json", "trials.csv", "measurement-events.jsonl", "measurement.json", "timings.csv"}


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("T-S01 report tooling is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tools():
    root = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "ts01"
    return (_module("csl_syn07_ts01_report", root / "report.py"),
            _module("csl_syn07_ts01_map", root / "publication_map.py"))


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("T-S01 bundle cannot be a symlink")
    report, mapping = _tools()
    record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    errors = report.validate(record)
    if errors:
        raise ValueError("invalid T-S01 record: " + ", ".join(errors))
    if bundle.name != record["report_id"]:
        raise ValueError("T-S01 source identity differs from directory")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.syn07-ts01-report-manifest/1" or manifest.get("report_id") != bundle.name or manifest.get("source_commit") != record["source_commit"]:
        raise ValueError("T-S01 manifest identity mismatch")
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file() and not p.is_symlink()}
    if actual != FILES | {"manifest.json"} or set(manifest.get("files", {})) != FILES:
        raise ValueError("T-S01 bundle inventory mismatch")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected:
            raise ValueError("T-S01 bundle hash mismatch: " + name)
    if (bundle / "index.html").read_text(encoding="utf-8") != report.render_html(record):
        raise ValueError("T-S01 HTML differs from validated record")
    if json.loads((bundle / "publication-map.json").read_text(encoding="utf-8")) != mapping.project(record):
        raise ValueError("T-S01 publication map differs from native record")
    rows = record["membership_examples"]
    raw = b"".join(mapping.canonical(row) + b"\n" for row in rows)
    if (bundle / "raw-events.jsonl").read_bytes() != raw:
        raise ValueError("T-S01 raw membership events differ from saved results")
    stream = io.StringIO(newline="")
    fields = ("id", "point", "expected_member", "actual_member", "reason")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "point": json.dumps(row["point"], separators=(",", ":"))})
    if (bundle / "trials.csv").read_bytes() != stream.getvalue().encode("utf-8"):
        raise ValueError("T-S01 CSV differs from saved membership results")
    scenarios = {"assumptions": record["assumptions"], "canonical_relation": record["canonical_relation"]}
    if json.loads((bundle / "scenarios.json").read_text(encoding="utf-8")) != scenarios:
        raise ValueError("T-S01 scenario sidecar differs from native record")
    if "measurement" in record:
        timing_events = [json.loads(line) for line in (bundle / "measurement-events.jsonl").read_text(encoding="utf-8").splitlines()]
        if timing_events != record["measurement"]["events"]:
            raise ValueError("T-S01 timing events differ from native record")
        if json.loads((bundle / "measurement.json").read_text(encoding="utf-8")) != record["measurement"]:
            raise ValueError("T-S01 measurement summary differs from native record")
        stream = io.StringIO(newline="")
        fields = ("repetition", "warmup", "status", "elapsed_ns", "consumed_result_marker")
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in record["measurement"]["events"])
        if (bundle / "timings.csv").read_bytes() != stream.getvalue().encode("utf-8"):
            raise ValueError("T-S01 timing CSV differs from native record")
    expected_environment = record["measurement"]["environment"] if "measurement" in record else {"measurement": "not performed", "timing": "unavailable", "reason": record["performance"]["reason"]}
    if json.loads((bundle / "environment.json").read_text(encoding="utf-8")) != expected_environment:
        raise ValueError("T-S01 environment sidecar differs from performance availability")
    source_hashes = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(actual)}
    public_id = mapping.public_report_id(record["report_id"], source_hashes, Path(__file__).read_bytes())
    payload_sha = mapping.digest(record)
    limitations = "; ".join(record["evidence_limits"] + ["Single-strategy timing observations are exploratory and performance conclusions are inconclusive; no speedup is claimed."])
    return common.PublicationRecord(KIND, public_id, payload_sha, record["source_commit"],
        "Exact analytic optimal relation for the strict two-step scalar integrator profile; exploratory single-strategy timings",
        limitations, tuple(sorted(FILES)), record["schema"], payload_sha, record["report_id"])


def render_page(bundle, publication):
    report, _ = _tools()
    record = json.loads((Path(bundle) / "records.json").read_text(encoding="utf-8"))
    page = report.render_html(record)
    links = ('<p>Publication <code>' + escape(publication.report_id) + '</code>; native source <code>' +
             escape(publication.source_report_id) + '</code>. <a href="report-envelope.json">Versioned envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a></p>')
    return page.replace("</body>", links + "</body>")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files if name != "index.html"}
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    payload = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    files["report-envelope.json"] = _json_bytes({"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
        "report_kind": publication.kind, "payload_schema": publication.payload_schema, "payload_sha256": publication.payload_sha256,
        "native_payload_sha256": publication.native_payload_sha256, "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
        "source_report_id": publication.source_report_id, "payload": payload})
    files["publication-manifest.json"] = _json_bytes({"schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": publication.report_id, "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)

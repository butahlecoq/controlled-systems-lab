"""Validated publication adapter for SYN-01 nominal-forward reports."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from html import escape

import registered_reports as common
import report_data as data

KIND = "syn01-nominal-forward"
SCHEMA = "csl.syn01-nominal-forward-report/2"
FILES = {
    "README.md", "build-provenance.json", "configure-log.txt", "build-log.txt",
    "driver-stderr.txt", "environment.json", "index.html", "latency.svg",
    "measurement-command.txt", "profile-evidence.txt", "publication-map.json",
    "raw-events.jsonl", "records.json", "scenarios.json", "summary.csv", "trials.csv",
}


def _map():
    path = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "syn01" / "publication_map.py"
    spec = importlib.util.spec_from_file_location("csl_syn01_publication_map", path)
    if spec is None or spec.loader is None:
        raise ValueError("SYN-01 publication map is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path):
    return data.parse_json(Path(path).read_text(encoding="utf-8"))


def _trial_csv(record):
    import io
    import csv
    fields = ("scenario", "repetition", "warmup", "status", "outcome", "oracle_passed",
              "expected_marginals", "observed_marginals", "setup_ns", "setup_state", "solve_ns", "solve_state",
              "oracle_ns", "oracle_state", "execute_ns", "execute_state", "provider_identities",
              "execution_settings", "provider_operation_counts", "provider_operation_timing_ns", "detail")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in record["trials"]:
        writer.writerow({key: json.dumps(row.get(key), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                         if isinstance(row.get(key), (dict, list)) else row.get(key) for key in fields})
    return stream.getvalue().encode("utf-8")


def _summary_csv(record):
    import io
    import csv
    fields = ("scenario", "phase", "median_ns", "min_ns", "max_ns", "range_ns",
              "available_trials", "partial_trials", "not_reached_trials", "unavailable_trials", "coverage")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in record["summary"]:
        for phase in ("setup_ns", "solve_ns", "oracle_ns", "execute_ns"):
            writer.writerow({"scenario": item["scenario"], "phase": phase, **item["phases"][phase]})
    return stream.getvalue().encode("utf-8")


def _validate_bundle(bundle, record):
    import importlib.util
    tooling = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "syn01" / "report.py"
    spec = importlib.util.spec_from_file_location("csl_syn01_saved_report", tooling)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    errors = report.validate_record(record)
    if errors:
        raise ValueError("invalid SYN-01 saved record: " + ", ".join(errors))
    if record.get("collection", {}).get("state") != "complete":
        raise ValueError("failed SYN-01 collection is retained but not publishable")
    if not isinstance(record.get("report_id"), str) or re.fullmatch(r"syn01-nominal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}", record["report_id"]) is None:
        raise ValueError("unsafe SYN-01 native report ID")
    if _json(bundle / "publication-map.json") != _map().project(record):
        raise ValueError("SYN-01 publication map differs from native records")
    if (bundle / "trials.csv").read_bytes() != _trial_csv(record):
        raise ValueError("SYN-01 trials.csv differs from canonical records projection")
    if (bundle / "summary.csv").read_bytes() != _summary_csv(record):
        raise ValueError("SYN-01 summary.csv differs from recomputed summary")
    if (bundle / "index.html").read_text(encoding="utf-8") != report.render_html(record):
        raise ValueError("SYN-01 HTML differs from saved records")
    if (bundle / "latency.svg").read_text(encoding="utf-8") != report.render_svg(record):
        raise ValueError("SYN-01 SVG differs from saved records")
    data.validate_svg((bundle / "latency.svg").read_bytes())
    try:
        rows = [data.parse_json(line) for line in (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid SYN-01 raw events") from error
    if rows != record["trials"]:
        raise ValueError("SYN-01 raw event stream differs from saved trials")
    if _json(bundle / "scenarios.json") != {"fixture_catalog": record["fixture_catalog"], "scenario_hashes": record["scenario_hashes"]}:
        raise ValueError("SYN-01 fixture sidecar differs from saved records")
    for name, expected in (("environment.json", record["environment"]), ("build-provenance.json", record["provenance"])):
        if _json(bundle / name) != expected:
            raise ValueError("SYN-01 provenance sidecar differs: " + name)
    if "limiter and capacity remain unknown" not in (bundle / "profile-evidence.txt").read_text(encoding="utf-8").lower():
        raise ValueError("SYN-01 profiling limitation is not explicit")


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("SYN-01 bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    manifest = _json(bundle / "manifest.json")
    if manifest.get("schema") != "csl.syn01-report-manifest/1" or manifest.get("report_id") != record.get("report_id"):
        raise ValueError("SYN-01 manifest identity mismatch")
    if manifest.get("source_commit") != record.get("source_commit") or manifest.get("harness_commit") != record.get("harness_commit"):
        raise ValueError("SYN-01 manifest source identity mismatch")
    if bundle.name != record.get("report_id"):
        raise ValueError("SYN-01 source bundle identity mismatch")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("SYN-01 bundle cannot contain symlinks")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != FILES | {"manifest.json"} or set(manifest.get("files", {})) != FILES:
        raise ValueError("SYN-01 bundle inventory mismatch")
    for name, digest in manifest["files"].items():
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
            raise ValueError("SYN-01 bundle hash mismatch: " + name)
    _validate_bundle(bundle, record)
    source_hashes = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(actual)}
    public_id = _map().public_report_id(record["report_id"], source_hashes,
                                        Path(__file__).read_bytes().replace(b"\r\n", b"\n"))
    digest = common._digest(record)
    scope = record["measurement"]["scope"]
    limits = "; ".join(record["evidence_limits"])
    return common.PublicationRecord(KIND, public_id, digest, record["source_commit"], scope,
        limits, tuple(sorted(FILES)), SCHEMA, digest, record["report_id"])


def render_page(bundle, publication):
    record = _json(Path(bundle) / "records.json")
    report_path = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "syn01" / "report.py"
    spec = importlib.util.spec_from_file_location("csl_syn01_page_report", report_path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
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
    payload = _json(bundle / "records.json")
    files["report-envelope.json"] = _json_bytes({"schema": "csl.algorithm-report-envelope/1",
        "report_id": publication.report_id, "report_kind": publication.kind,
        "payload_schema": publication.payload_schema, "payload_sha256": publication.payload_sha256,
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

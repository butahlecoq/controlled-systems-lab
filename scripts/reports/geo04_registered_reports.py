"""Allowlisted publication adapter for the saved GEO-04 polyhedral report."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

import registered_reports as common


FILES = {"build-provenance.txt", "collection-status.json", "concurrent-work.txt", "environment.json", "index.html",
         "latency.svg", "measurement-command.txt", "process-stderr.txt", "profile-evidence.txt",
         "raw-driver-output.csv", "raw-events.jsonl", "records.json", "scenarios.json", "summary.csv"}
SCHEMA = "csl.geo04-polyhedral-report/1"


def _renderer():
    path = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "geo04" / "render.py"
    spec = importlib.util.spec_from_file_location("csl_geo04_publication_renderer", path)
    if spec is None or spec.loader is None:
        raise ValueError("GEO-04 renderer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def adapt_payload(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unregistered GEO-04 report schema")
    renderer = _renderer()
    renderer.validate(record)
    report_id = record.get("report_id", "")
    if not isinstance(report_id, str) or re.fullmatch(r"geo04-\d{8}T\d{6}Z-[0-9a-f]{12}", report_id) is None:
        raise ValueError("unsafe GEO-04 report ID")
    if not report_id.endswith(record["payload_sha256"][:12]):
        raise ValueError("GEO-04 report ID does not match payload digest")
    source = record.get("algorithm", {}).get("source_commit", "")
    if not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise ValueError("GEO-04 source commit is required")
    evidence = record.get("evidence", {})
    limitations = evidence.get("limitations")
    required_limits = {
        "small analytic fixtures only", "no competitor or speedup claim",
        "no application-scale or scalability claim",
        "LP query internal phase timings and OS-observed thread counts unavailable",
    }
    if not isinstance(limitations, list) or not required_limits.issubset(set(limitations)):
        raise ValueError("GEO-04 evidence limitations are incomplete")
    if evidence.get("limiter_profile", {}).get("timing_trials_profiled") is not False:
        raise ValueError("GEO-04 timing trials must remain unprofiled")
    if "retain all rows" not in evidence.get("essential_row_result", ""):
        raise ValueError("GEO-04 reducer limitation is missing")
    trials = record["trials"]
    measured = f"{len(trials)} measured trials across {len(record['expected'])} analytic polyhedral-intersection fixtures"
    limits = ("No comparator or speedup claim; binary64 numerical fixtures without exact validated geometry; "
              "no application-scale or scalability claim; HiGHS reduction remains incomplete and retains all rows; "
              "CPU profile and per-trial resource counters unavailable")
    return common.PublicationRecord("geo04-intersection", report_id, common._digest(record), source, measured, limits,
        payload_schema=SCHEMA, native_payload_sha256=record["payload_sha256"], source_report_id=report_id)


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("GEO-04 source bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    item = adapt_payload(record)
    if bundle.name != item.source_report_id:
        raise ValueError("GEO-04 source bundle identity mismatch")
    manifest = _json(bundle / "manifest.json")
    listed = manifest.get("files", {})
    if (set(manifest) != {"schema", "report_id", "files"} or
        manifest.get("schema") != "csl.geo04-report-manifest/1" or manifest.get("report_id") != item.source_report_id):
        raise ValueError("GEO-04 manifest identity mismatch")
    common.validate_source_inventory(bundle, listed, FILES, label="GEO-04")
    _validate_saved_data(bundle, record)
    _validate_source_zip(bundle, listed)
    publisher_source = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    identity = {
        "schema": "csl.registered-publication-identity/1",
        "source_report_id": item.source_report_id,
        "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(FILES | {"manifest.json"})},
        "publisher_sha256": hashlib.sha256(publisher_source).hexdigest(),
    }
    public_id = item.source_report_id.rsplit("-", 1)[0] + "-" + common._digest(identity)
    publication = common.PublicationRecord(item.kind, public_id, item.payload_sha256, item.source_commit,
        item.measured_scope, item.evidence_limits, tuple(sorted(FILES)), item.payload_schema,
        item.native_payload_sha256, item.source_report_id)


    return common.preserve_historical_publication(bundle, publication, offline_zip)


def _validate_saved_data(bundle, record):
    renderer = _renderer()
    rendered = dict(record)
    rendered["_files"] = sorted(FILES)
    if (bundle / "index.html").read_text(encoding="utf-8") != renderer.render_html(rendered):
        raise ValueError("GEO-04 HTML differs from saved records")
    if (bundle / "latency.svg").read_text(encoding="utf-8") != renderer.render_svg(record):
        raise ValueError("GEO-04 SVG differs from saved records")
    try:
        raw_events = [json.loads(line) for line in (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid GEO-04 raw event stream") from error
    if raw_events != record["trials"]:
        raise ValueError("GEO-04 raw events differ from saved records")
    trial_fields = ("scenario", "repetition", "status", "detail", "intersection_ns", "prepare_ns", "workspace_ns",
        "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns", "lp_calls", "lp_results", "lp_optimal",
        "lp_bounds", "lp_supported_bounds", "reduction_status", "inequalities", "equalities", "vertices", "oracle_checks",
        "vertices_json", "oracle_passed")
    try:
        with (bundle / "raw-driver-output.csv").open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(trial_fields):
                raise ValueError("GEO-04 raw CSV headers differ from validated records")
            actual_trials = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("invalid GEO-04 raw CSV") from error
    if len(actual_trials) != len(record["trials"]):
        raise ValueError("GEO-04 raw CSV row count differs from validated records")
    for actual, expected in zip(actual_trials, record["trials"]):
        try:
            vertices = json.loads(actual["vertices_json"])
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("GEO-04 CSV vertices are malformed") from error
        if vertices != expected["vertices_json"] or any(
            actual.get(field) != str(str(expected[field]).lower() if field == "oracle_passed" else expected[field])
            for field in trial_fields if field != "vertices_json"):
            raise ValueError("GEO-04 raw CSV differs from validated records")
    summary_fields = ("scenario", "attempts", "passed", "failures", "phase", "unit", "successful_trials", "median", "min", "max", "range", "trials_excluded_from_summary")
    expected_summary = []
    for scenario, group in record["summary"].items():
        for phase, stats in group["phases"].items():
            expected_summary.append({"scenario": scenario, "attempts": group["attempts"], "passed": group["passed"],
                "failures": group["failures"], "phase": phase, **stats})
    _compare_csv(bundle / "summary.csv", summary_fields, expected_summary)
    status = _json(bundle / "collection-status.json")
    collection = record["collection"]
    if (status.get("schema") != "csl.geo04-collection-status/1" or status.get("state") != collection["state"] or
        status.get("actual_trials") != collection["actual_trials"] or status.get("expected_trials") != collection["expected_trials"] or
        status.get("failures") != collection["failures"] or status.get("return_code") != collection["process_return_code"] or
        status.get("aborted_or_timed_out") != collection["aborted_or_timed_out"] or status.get("parse_error") != collection["parse_error"]):
        raise ValueError("GEO-04 collection status differs from saved records")
    if "Limiter attribution: unavailable" not in (bundle / "profile-evidence.txt").read_text(encoding="utf-8"):
        raise ValueError("GEO-04 unavailable profiler evidence must be explicit")


def _compare_csv(path, fields, expected_rows):
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(fields):
                raise ValueError(path.name + " headers differ from validated records")
            actual_rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("invalid GEO-04 " + path.name) from error
    if len(actual_rows) != len(expected_rows):
        raise ValueError(path.name + " row count differs from validated records")
    if any(any(row.get(field) != str(expected[field]) for field in fields) for row, expected in zip(actual_rows, expected_rows)):
        raise ValueError(path.name + " differs from validated records")


def _validate_source_zip(bundle, listed):
    archive_path = bundle.parent / (bundle.name + ".zip")
    if archive_path.is_symlink():
        raise ValueError("GEO-04 source ZIP cannot be a symlink")
    expected_names = set(listed) | {"manifest.json"}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected_names or archive.testzip() is not None:
                raise ValueError("GEO-04 source ZIP inventory mismatch")
            if any((entry.external_attr >> 16) & 0o170000 == 0o120000 for entry in archive.infolist()):
                raise ValueError("symlinks are forbidden in GEO-04 source ZIP")
            for name in expected_names:
                if archive.read(name) != (bundle / name).read_bytes():
                    raise ValueError("GEO-04 source ZIP content mismatch: " + name)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise ValueError("invalid GEO-04 source ZIP") from error


def render_page(bundle, publication):
    renderer = _renderer()
    payload = _json(Path(bundle) / "records.json")
    payload["_files"] = list(publication.files)
    page = renderer.render_html(payload)
    links = ('<p>Publication <code>'+publication.report_id+'</code>; source <code>'+publication.source_report_id+
             '</code>. <a href="report-envelope.json">Versioned report envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a></p>')
    return page.replace("</body>", links + "</body>")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    payload = _json(bundle / "records.json")
    envelope = {
        "schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
        "report_kind": publication.kind, "payload_schema": publication.payload_schema,
        "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
        "native_payload_sha256": publication.native_payload_sha256,
        "source_report_id": publication.source_report_id, "payload": payload,
    }
    return common.assemble_publication(bundle, publication,
        page=render_page(bundle, publication), envelope=envelope, source_files=publication.files)



def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)

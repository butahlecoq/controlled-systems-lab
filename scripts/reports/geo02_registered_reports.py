"""Allowlisted publication adapter for GEO-02 affine-sum measurements."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

import registered_reports as common
import report_data as data

SCHEMA = "csl.geo02-affine-sum-report/1"
FILES = {
    "build-provenance.txt", "collection-status.json", "concurrent-work.txt", "environment.json",
    "index.html", "measurement-command.txt", "profile-evidence.txt", "process-stderr.txt", "timings.svg",
    "raw-driver-output.csv", "raw-events.jsonl", "records.json", "scenarios.json", "summary.csv",
}
HASH_SCOPE = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
TRIAL_FIELDS = ("scenario", "repetition", "status", "detail", "setup_ns", "operation_ns", "oracle_ns",
                "total_ns", "input_sha256", "output_points", "support_checks", "support_values", "oracle_passed")


def _digest(value):
    return common._digest(value)


def _renderer():
    path = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "geo02" / "render.py"
    spec = importlib.util.spec_from_file_location("csl_geo02_publication_renderer", path)
    if spec is None or spec.loader is None:
        raise ValueError("GEO-02 renderer is unavailable")
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path):
    return data.parse_json(Path(path).read_text(encoding="utf-8"))


def _payload(record):
    return {key: value for key, value in record.items()
            if key not in ("report_id", "payload_sha256", "payload_hash_scope")}


def adapt_payload(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unregistered GEO-02 report schema")
    if record.get("payload_hash_scope") != HASH_SCOPE:
        raise ValueError("GEO-02 payload hash scope mismatch")
    try:
        _renderer().validate(record)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid GEO-02 report payload") from error
    rid = record.get("report_id", "")
    if not isinstance(rid, str) or re.fullmatch(r"geo02-\d{8}T\d{6}Z-[0-9a-f]{12}", rid) is None:
        raise ValueError("unsafe GEO-02 report ID")
    digest = _digest(_payload(record))
    if record.get("payload_sha256") != digest or not rid.endswith(digest[:12]):
        raise ValueError("GEO-02 report ID/payload digest mismatch")
    algorithm = record.get("algorithm", {})
    if algorithm.get("id") != "GEO-02" or any(re.fullmatch(r"[0-9a-f]{40}", algorithm.get(key, "")) is None
                                             for key in ("source_commit", "harness_commit")):
        raise ValueError("GEO-02 source and harness commits are required")
    evidence = record.get("evidence", {})
    limitations = evidence.get("limitations")
    limiter = evidence.get("limiter_profile", "")
    unavailable = evidence.get("unavailable_counters", [])
    if (not isinstance(limitations, list) or not any("candidate reducer" in x and "retains full candidate cloud" in x for x in limitations)
            or not any("tiny" in x and "fixture" in x for x in limitations)
            or not any(all(word in x for word in ("no competitor", "speedup", "application-scale", "scalability")) for x in limitations)
            or not any("exact" in x and "validated" in x for x in limitations)):
        raise ValueError("GEO-02 scope/reduction evidence limitations are incomplete")
    if not isinstance(limiter, str) or "not collected" not in limiter:
        raise ValueError("GEO-02 profiling limitation must be explicit")
    if not isinstance(unavailable, list) or not any("internal LP" in x for x in unavailable) or not any("per-trial CPU" in x for x in unavailable):
        raise ValueError("GEO-02 unavailable profiling/internal solver phases must be explicit")
    trials = record.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("GEO-02 trial records are required")
    for trial in trials:
        if not isinstance(trial, dict) or not set(TRIAL_FIELDS).issubset(trial):
            raise ValueError("GEO-02 trial fields are incomplete")
        if type(trial["repetition"]) is not int or trial["repetition"] < 0:
            raise ValueError("GEO-02 trial repetition is invalid")
        for key in ("setup_ns", "operation_ns", "oracle_ns", "total_ns", "support_checks"):
            if type(trial[key]) is not int or trial[key] < 0:
                raise ValueError("GEO-02 trial timing/count is invalid")
        if not isinstance(trial["output_points"], list) or not isinstance(trial.get("support_values"), list):
            raise ValueError("GEO-02 trial point/support observations are invalid")
        if trial["total_ns"] < trial["setup_ns"] + trial["operation_ns"] + trial["oracle_ns"]:
            raise ValueError("GEO-02 trial timing phases exceed total duration")
        if trial["status"] != "passed" or trial["oracle_passed"] is not True:
            raise ValueError("GEO-02 publication requires complete oracle-passing trials")
        if not isinstance(trial["scenario"], str) or not trial["scenario"] or re.fullmatch(r"[0-9a-f]{64}", trial["input_sha256"]) is None:
            raise ValueError("GEO-02 trial identity is invalid")
    collection = record.get("collection", {})
    if collection.get("state") != "complete" or collection.get("actual_trials") != len(trials) or collection.get("failures") != 0:
        raise ValueError("GEO-02 collection must be complete and failure-free")
    scope = f"{len(trials)} measured affine-sum trials across {len(record.get('expected', {}))} tiny binary64 fixtures"
    limits = "Full candidate cloud retained; validated reduction evidence is not applied; no comparator, speedup, application-scale, or scalability claim; binary64 tiny fixtures; profiling and internal solver-phase timings unavailable"
    return common.PublicationRecord("geo02-affine-sum", rid, digest, algorithm["source_commit"], scope, limits,
                                    tuple(sorted(FILES)), SCHEMA, digest, rid)


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("GEO-02 bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    item = adapt_payload(record)
    if bundle.name != item.source_report_id:
        raise ValueError("GEO-02 source bundle identity mismatch")
    manifest = _json(bundle / "manifest.json")
    if set(manifest) != {"schema", "report_id", "files"} or manifest.get("schema") != "csl.geo02-bundle/1" or manifest.get("report_id") != item.source_report_id:
        raise ValueError("GEO-02 manifest identity mismatch")
    listed = manifest.get("files")
    if not isinstance(listed, dict) or set(listed) != FILES:
        raise ValueError("GEO-02 registered bundle inventory mismatch")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are forbidden in GEO-02 bundle")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != FILES | {"manifest.json"}:
        raise ValueError("GEO-02 bundle has missing or unregistered files")
    for name, expected in listed.items():
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None or hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected:
            raise ValueError("GEO-02 bundle file hash mismatch: " + name)
    _validate_saved_data(bundle, record)
    data.validate_svg((bundle / "timings.svg").read_bytes())
    _validate_source_zip(bundle, listed)
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": item.source_report_id,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(FILES | {"manifest.json"})},
                "source_zip_sha256": hashlib.sha256((bundle.parent / (bundle.name + ".zip")).read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    public_id = item.source_report_id.rsplit("-", 1)[0] + "-" + _digest(identity)
    return common.PublicationRecord(item.kind, public_id, item.payload_sha256, item.source_commit, item.measured_scope,
                                    item.evidence_limits, item.files, item.payload_schema, item.native_payload_sha256,
                                    item.source_report_id)


def _validate_saved_data(bundle, record):
    renderer = _renderer()
    if (bundle / "index.html").read_text(encoding="utf-8") != renderer.render_html(record):
        raise ValueError("GEO-02 HTML differs from saved records")
    if (bundle / "timings.svg").read_text(encoding="utf-8") != renderer.render_svg(record):
        raise ValueError("GEO-02 SVG differs from saved records")
    try:
        events = [json.loads(line) for line in (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid GEO-02 raw event stream") from error
    if events != record["trials"]:
        raise ValueError("GEO-02 raw events differ from saved trials")
    _validate_driver_csv(bundle / "raw-driver-output.csv", record["trials"])
    _validate_summary_csv(bundle / "summary.csv", record["summary"])
    if _json(bundle / "scenarios.json") != record["expected"]:
        raise ValueError("GEO-02 scenarios differ from saved records")
    status = _json(bundle / "collection-status.json")
    for key in ("state", "actual_trials", "expected_trials", "failures", "warmups_per_scenario", "warmup_results",
                "warmup_failures", "warmup_parse_error", "process_return_code", "aborted_or_timed_out", "parse_error"):
        if status.get(key) != record["collection"].get(key):
            raise ValueError("GEO-02 collection status differs from saved records")
    profile = (bundle / "profile-evidence.txt").read_text(encoding="utf-8")
    if "not collected" not in profile.lower():
        raise ValueError("GEO-02 unavailable profiling evidence must be explicit")


def _compare_csv(path, fields, rows):
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            actual = list(reader)
            if reader.fieldnames != list(fields):
                raise ValueError(path.name + " headers differ from records")
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("invalid GEO-02 CSV: " + path.name) from error
    def text(value):
        return "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    if len(actual) != len(rows) or any(any(row.get(key) != text(value) for key, value in expected.items()) for row, expected in zip(actual, rows)):
        raise ValueError(path.name + " differs from saved records")


def _validate_driver_csv(path, trials):
    fields = ("scenario", "repetition", "status", "detail", "setup_ns", "operation_ns", "oracle_ns", "total_ns",
              "output_points", "support_checks", "support_values", "oracle_passed")
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            if reader.fieldnames != list(fields):
                raise ValueError("GEO-02 raw-driver CSV headers differ")
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("invalid GEO-02 raw-driver CSV") from error
    if len(rows) != len(trials):
        raise ValueError("GEO-02 raw-driver CSV row count differs")
    for row, trial in zip(rows, trials):
        for field in fields:
            if field in ("output_points", "support_values"):
                try:
                    equal = json.loads(row[field]) == trial[field]
                except (TypeError, json.JSONDecodeError):
                    equal = False
            else:
                expected = str(trial[field]).lower() if isinstance(trial[field], bool) else str(trial[field])
                equal = row.get(field) == expected
            if not equal:
                raise ValueError("GEO-02 raw-driver CSV differs from records")


def _validate_summary_csv(path, summary):
    fields = ("scenario", "phase", "unit", "median", "min", "max", "range", "successful_trials", "trials_excluded_from_summary")
    expected = [{"scenario": scenario, "phase": phase, **stats}
                for scenario, group in summary.items() for phase, stats in group["phases"].items()]
    _compare_csv(path, fields, expected)


def _validate_source_zip(bundle, listed):
    archive_path = bundle.parent / (bundle.name + ".zip")
    if archive_path.is_symlink():
        raise ValueError("GEO-02 source ZIP cannot be a symlink")
    expected = set(listed) | {"manifest.json"}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected or archive.testzip() is not None:
                raise ValueError("GEO-02 source ZIP inventory mismatch")
            if any((entry.external_attr >> 16) & 0o170000 == 0o120000 for entry in archive.infolist()):
                raise ValueError("GEO-02 source ZIP contains symlink")
            for name in expected:
                if archive.read(name) != (bundle / name).read_bytes():
                    raise ValueError("GEO-02 source ZIP content mismatch: " + name)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise ValueError("invalid GEO-02 source ZIP") from error


def render_page(bundle, publication):
    page = _renderer().render_html(_json(Path(bundle) / "records.json"))
    links = ('<p>Publication <code>' + publication.report_id + '</code>; source <code>' + publication.source_report_id +
             '</code>. <a href="report-envelope.json">Versioned report envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a></p>')
    return page.replace("</body>", links + "</body>")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files if name != "index.html"}
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    payload = _json(bundle / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_report_id": publication.source_report_id, "payload": _payload(payload)}
    files["report-envelope.json"] = common._json_bytes(envelope)
    files["publication-manifest.json"] = common._json_bytes({"schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": publication.report_id, "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)

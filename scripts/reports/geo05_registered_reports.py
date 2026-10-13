"""Strict publication adapter for saved GEO-05 numerical measurements."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import stat
import zipfile

import registered_reports as common

SCHEMA = "csl.geo05-numerical-report/1"
KIND = "geo05-projection-predecessor"
CATALOG_VERSION = "geo05-analytic-v1"
SCENARIOS = ("singular_a", "unreachable_equality_target", "integrator_predecessor", "v_projection_preserves_ray")
PHASES = ("preparation_ns", "workspace_ns", "run_ns", "verification_ns", "end_to_end_ns")
FILES = {"command.json", "index.html", "parse-errors.json", "provenance.json", "records.json", "stderr.txt",
         "stdout.jsonl", "trials.csv", "trials.jsonl"}
ORACLES = {
    "singular_a": {"inputs": {"X": {"kind": "universal", "dimension": 2}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "singleton", "point": [2, 0]}, "A": [[1, 0], [0, 0]], "B": [[1], [0]], "offset": [0, 0], "projected_coordinates": [0, 1]}, "input_rows": 4, "output_rows": 2, "result_kind": "h",
                   "sample_points": [[1, -1000], [3, 1000]], "rejected_points": [[0.5, 0]],
                   "meaning": "singular A retains the free state direction"},
    "unreachable_equality_target": {"inputs": {"X": {"kind": "universal", "dimension": 2}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "H", "equalities": [[0, 1]], "values": [1]}, "A": [[1, 0], [0, 0]], "B": [[1], [0]], "offset": [0, 0], "projected_coordinates": [0, 1]}, "input_rows": 3, "output_rows": 1, "result_kind": "h",
                                     "sample_points": [], "rejected_points": [[0, 0], [100, -100]],
                                     "meaning": "target equality is unreachable under singular dynamics"},
    "integrator_predecessor": {"inputs": {"X": {"kind": "interval", "bounds": [-2, 2]}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "interval", "bounds": [1, 3]}, "A": [[1]], "B": [[1]], "offset": [0], "projected_coordinates": [0]}, "input_rows": 6, "output_rows": 4, "result_kind": "h",
                               "sample_points": [[0], [1], [2]], "rejected_points": [[-0.125], [2.125]],
                               "meaning": "x'=x+u, X=[-2,2], U=[-1,1], S=[1,3] gives literal predecessor samples",
                               "expected_fm_peak_rows": 6,
                               "expected_fm_peak_basis": "2X+2U+2S rows; eliminating u generates 2x2+2=6 before tautology removal"},
    "v_projection_preserves_ray": {"inputs": {"V": {"vertices": [[2, 3]], "rays": [[1, 0], [0, -1]]}, "projected_coordinates": [1]}, "input_rows": 3, "output_rows": 3, "result_kind": "v",
                                   "vertices": [[3]], "rays": [[0], [-1]],
                                   "meaning": "selected ray images, including zero, are retained"},
}


class _DuplicateJsonKeyError(ValueError):
    pass


def _json(path: Path):
    return _strict_json_loads(path.read_text(encoding="utf-8"))


def _strict_json_loads(source):
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise _DuplicateJsonKeyError(f"duplicate JSON key: {key}")
            value[key] = item
        return value
    return json.loads(source, object_pairs_hook=object_pairs)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _scenario_order(repetition):
    return SCENARIOS if repetition % 2 == 0 else tuple(reversed(SCENARIOS))


def _expected_collection(record):
    trials = record["trials"]
    warmups = record["warmup_trials"]
    source = record["collection"]
    counts = {name: 0 for name in ("passed", "failed", "unsupported", "cancelled", "missing")}
    for row in [*warmups, *trials]:
        status = row.get("status")
        counts[status if status in counts else "failed"] += 1
    expected = len(SCENARIOS) * source["measured_repetitions"]
    counts["missing"] += max(0, expected - len(trials))
    expected_warmups = len(SCENARIOS) * source["warmups_per_scenario"]
    counts["missing"] += max(0, expected_warmups - len(warmups))
    timed_out = source.get("timed_out")
    valid = (counts["failed"] == counts["unsupported"] == counts["cancelled"] == counts["missing"] == 0
             and source.get("process_return_code") == 0 and source.get("parse_errors") == 0 and timed_out is False)
    def phase_stats(group):
        result = {}
        for phase in PHASES:
            values = [row.get("durations_ns", {}).get(phase) for row in group
                      if row.get("status") == "passed" and row.get("oracle_passed") is True
                      and type(row.get("durations_ns", {}).get(phase)) is int]
            result[phase] = {"median_ns": statistics.median(values) if valid and values else None,
                             "min_ns": min(values) if valid and values else None,
                             "max_ns": max(values) if valid and values else None,
                             "successful_trials": len(values), "unavailable_trials": len(group) - len(values),
                             "trials_excluded": 0 if valid else len(values)}
        return result
    phases = phase_stats(trials)
    by_scenario = {scenario: {"attempts": sum(row.get("scenario") == scenario for row in trials),
                              "phases": phase_stats([row for row in trials if row.get("scenario") == scenario])}
                   for scenario in SCENARIOS}
    return {"measured_repetitions": source["measured_repetitions"],
            "warmups_per_scenario": source["warmups_per_scenario"], "expected_trials": expected,
            "counts": counts, "valid_success_summary": valid,
            "expected_warmup_trials": expected_warmups, "actual_warmup_trials": len(warmups),
            "process_return_code": source.get("process_return_code", 0),
            "parse_errors": source.get("parse_errors", 0), "timed_out": timed_out,
            "phases": phases, "by_scenario": by_scenario}


def _validate_record(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unregistered GEO-05 report schema")
    if record.get("purpose") != "measurement":
        raise ValueError("only GEO-05 measurement records may be published")
    digest = record.get("payload_sha256")
    unsigned = {key: value for key, value in record.items() if key not in ("report_id", "payload_sha256")}
    if not isinstance(digest, str) or digest != _digest(unsigned):
        raise ValueError("GEO-05 payload digest mismatch")
    if record.get("report_id") != "geo05-" + digest[:16]:
        raise ValueError("GEO-05 report ID does not match payload digest")
    algorithm = record.get("algorithm")
    if (not isinstance(algorithm, dict) or algorithm.get("id") != "GEO-05"
            or any(not isinstance(algorithm.get(key), str) or re.fullmatch(r"[0-9a-f]{40}", algorithm[key]) is None
                   for key in ("source_commit", "harness_commit"))):
        raise ValueError("GEO-05 source and harness commits are required")
    catalog = record.get("catalog")
    if not isinstance(catalog, dict) or catalog != {"version": CATALOG_VERSION, "scenarios": list(SCENARIOS), "oracles": ORACLES}:
        raise ValueError("GEO-05 fixture catalog differs from pinned catalog")
    trials, warmups, collection = record.get("trials"), record.get("warmup_trials"), record.get("collection")
    if not isinstance(trials, list) or not isinstance(warmups, list) or not isinstance(collection, dict):
        raise ValueError("GEO-05 trial and collection records are required")
    repetitions = collection.get("measured_repetitions")
    if type(repetitions) is not int or repetitions < 7 or collection.get("warmups_per_scenario") != 1:
        raise ValueError("GEO-05 publication requires at least seven measured repetitions and one warmup")
    if (type(collection.get("process_return_code")) is not int or type(collection.get("parse_errors")) is not int
            or collection["parse_errors"] < 0 or type(collection.get("timed_out")) is not bool):
        raise ValueError("GEO-05 process outcome evidence is invalid")
    if algorithm.get("process_exit_code", 0) != collection["process_return_code"]:
        raise ValueError("GEO-05 process exit evidence differs from collection summary")
    expected_trials = {(name, repetition) for name in SCENARIOS for repetition in range(repetitions)}
    expected_warmups = {(name, 0) for name in SCENARIOS}
    for rows, expected, label in ((trials, expected_trials, "trial"), (warmups, expected_warmups, "warmup")):
        pairs = []
        for row in rows:
            if not isinstance(row, dict) or row.get("scenario") not in SCENARIOS or type(row.get("repetition")) is not int:
                raise ValueError(f"GEO-05 {label} identity is invalid")
            pairs.append((row["scenario"], row["repetition"]))
        if len(pairs) != len(set(pairs)) or not set(pairs) <= expected:
            raise ValueError(f"GEO-05 {label} matrix is duplicated or out of range")
    if [(row["scenario"], row["repetition"]) for row in warmups] != [
            pair for pair in ((name, 0) for name in SCENARIOS)
            if pair in {(row["scenario"], row["repetition"]) for row in warmups}]:
        raise ValueError("GEO-05 warmup order differs from the pinned fixture catalog")
    expected_order = [(scenario, repetition) for repetition in range(repetitions)
                      for scenario in _scenario_order(repetition)]
    trial_pairs = [(row["scenario"], row["repetition"]) for row in trials]
    if trial_pairs != [pair for pair in expected_order if pair in set(trial_pairs)]:
        raise ValueError("GEO-05 trial order differs from the alternating collection policy")
    for row in [*warmups, *trials]:
        if type(row.get("repetition")) is not int or isinstance(row.get("repetition"), bool):
            raise ValueError("GEO-05 repetition must be an integer")
        if row.get("oracle_scope") != "numeric_literal_samples":
            raise ValueError("GEO-05 oracle scope must remain numeric literal samples")
        if type(row.get("oracle_passed")) is not bool or type(row.get("work_observed")) is not bool:
            raise ValueError("GEO-05 oracle and work observations must be booleans")
        if row.get("status") not in ("passed", "failed", "unsupported", "cancelled", "oracle_failed"):
            raise ValueError("GEO-05 trial status is invalid")
        if row.get("status") == "passed" and (row.get("oracle_passed") is not True or row.get("work_observed") is not True):
            raise ValueError("GEO-05 passed trial lacks literal checks or observed work")
        expected_limit = None if row["scenario"] == "v_projection_preserves_ray" else 128
        if row.get("max_rows") != expected_limit:
            raise ValueError("GEO-05 row limit differs from the registered scenario")
        expected_case = ORACLES[row["scenario"]]
        if (row.get("status") == "passed" and (type(row.get("input_rows")) is not int
                or type(row.get("output_rows")) is not int
                or row.get("input_rows") != expected_case["input_rows"]
                or row.get("output_rows") != expected_case["output_rows"])):
            raise ValueError("GEO-05 observed row counts differ from the pinned scenario")
        if (row.get("expected_fm_peak_rows") != expected_case.get("expected_fm_peak_rows")
                or (row.get("expected_fm_peak_rows") is not None and type(row.get("expected_fm_peak_rows")) is not int)):
            raise ValueError("GEO-05 expected row peak differs from the pinned scenario")
        if (row.get("input_sha256") != _digest(expected_case["inputs"])
                or row.get("scenario_sha256") != _digest(expected_case)):
            raise ValueError("GEO-05 trial input/scenario digest differs from pinned fixture")
        if row.get("status") == "passed" and row.get("result_kind") != expected_case["result_kind"]:
            raise ValueError("GEO-05 result representation differs from pinned fixture")
        if row.get("status") != "passed" and row.get("result_kind") not in (None, ""):
            raise ValueError("GEO-05 failed attempt must not claim an unobserved result kind")
        expected_encoding = ("h_contradiction_row" if row["scenario"] == "unreachable_equality_target"
                             else "v_generators" if row["scenario"] == "v_projection_preserves_ray" else "h_rows")
        if row.get("status") == "passed" and row.get("result_encoding") != expected_encoding:
            raise ValueError("GEO-05 result encoding differs from pinned fixture")
        if row.get("status") != "passed" and row.get("result_encoding") not in (None, ""):
            raise ValueError("GEO-05 failed attempt must not claim an unobserved result encoding")
        if row.get("purpose") not in (None, "warmup" if row in warmups else "measurement"):
            raise ValueError("GEO-05 attempt purpose differs from its matrix")
        durations = row.get("durations_ns")
        if not isinstance(durations, dict):
            raise ValueError("GEO-05 duration scopes are required")
        if row["scenario"] != "v_projection_preserves_ray" and durations.get("workspace_ns") is not None:
            raise ValueError("GEO-05 workspace duration must remain unavailable for H operations")
        if row.get("status") == "passed":
            for phase in PHASES:
                value = durations.get(phase)
                if value is None and phase == "workspace_ns" and row["scenario"] != "v_projection_preserves_ray":
                    continue
                if type(value) is not int or value < 0:
                    raise ValueError("GEO-05 successful trial has an invalid duration")
    if any(row.get("purpose") not in (None, "warmup") for row in warmups):
        raise ValueError("GEO-05 warmup row has incorrect purpose")
    expected_collection = _expected_collection(record)
    if collection != expected_collection:
        raise ValueError("GEO-05 saved summary differs from trial matrix")
    limits = record.get("evidence_limits")
    if not isinstance(limits, list) or not limits or any(not isinstance(item, str) or not item for item in limits):
        raise ValueError("GEO-05 evidence limits are required")
    return digest, algorithm, collection


def adapt_payload(record):
    try:
        digest, algorithm, collection = _validate_record(record)
    except ValueError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError("malformed GEO-05 report payload") from error
    counts = collection["counts"]
    timing_claim = "Phase summaries include successful trials only when the full run summary is valid"
    completeness = "complete measurement trial matrix" if counts["missing"] == 0 else "partial measurement trial matrix; missing trials retained"
    failures = f"attempt outcomes: {json.dumps(counts, sort_keys=True)}"
    assessment = ("complete fixture attempt matrix; all attempts passed; eligible for independent review only"
                  if collection["valid_success_summary"] else
                  "INCOMPLETE / INCONCLUSIVE measurement; missing, non-passing, or timed-out attempts suppress all timing summaries")
    limitations = "; ".join(record["evidence_limits"] + [
        "tiny analytic fixtures only", "no comparator, speedup, application-scale, or scalability claim",
        "binary64 numerical samples do not establish exact set equality or validated arithmetic",
        "H relation support remains Unestablished", timing_claim, completeness, failures, assessment])
    scope = f"{len(record['trials'])} retained measured attempts across four GEO-05 analytic fixtures; {record['collection']['measured_repetitions']} requested repetitions per fixture"
    return common.PublicationRecord(KIND, record["report_id"], digest, algorithm["source_commit"], scope,
                                    limitations, tuple(sorted(FILES)), SCHEMA, digest, record["report_id"])


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("GEO-05 source bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    item = adapt_payload(record)
    if bundle.name != item.source_report_id:
        raise ValueError("GEO-05 source bundle identity mismatch")
    manifest = _json(bundle / "manifest.json")
    if manifest.get("schema") != "csl.geo05-report-files/1" or set(manifest) != {"schema", "files"}:
        raise ValueError("GEO-05 manifest schema mismatch")
    listed = manifest.get("files")
    if not isinstance(listed, dict) or set(listed) != FILES:
        raise ValueError("GEO-05 registered source inventory mismatch")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are forbidden in GEO-05 bundle")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != FILES | {"manifest.json"}:
        raise ValueError("GEO-05 bundle has missing or unregistered files")
    for name, expected in listed.items():
        if (not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None
                or hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected):
            raise ValueError("GEO-05 source file hash mismatch: " + name)
    _validate_saved_data(bundle, record)
    source_zip = bundle.parent / (bundle.name + ".zip")
    _validate_source_zip(bundle, source_zip)
    publisher_source = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": item.source_report_id,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                                 for name in sorted(FILES | {"manifest.json"})},
                "source_zip_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher_source).hexdigest()}
    public_id = "geo05-" + _digest(identity)
    return common.PublicationRecord(item.kind, public_id, item.payload_sha256, item.source_commit,
                                    item.measured_scope, item.evidence_limits, item.files,
                                    item.payload_schema, item.native_payload_sha256, item.source_report_id)


def _validate_saved_data(bundle, record):
    with (bundle / "trials.jsonl").open(encoding="utf-8") as stream:
        try:
            raw_rows = [_strict_json_loads(line) for line in stream if line.strip()]
        except _DuplicateJsonKeyError:
            raise
        except (UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("invalid GEO-05 raw trial stream") from error
    expected_rows = [*record["warmup_trials"], *record["trials"]]
    if raw_rows != expected_rows:
        raise ValueError("GEO-05 raw trial stream differs from saved records")
    fields = ("purpose", "scenario", "repetition", "status", "detail", "oracle_passed", "work_observed",
              "max_rows", "input_rows", "output_rows", "result_kind", "result_encoding", "input_sha256",
              "scenario_sha256", "expected_fm_peak_rows", *PHASES)
    try:
        with (bundle / "trials.csv").open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("invalid GEO-05 trials.csv") from error
    if reader.fieldnames != list(fields) or len(rows) != len(expected_rows):
        raise ValueError("GEO-05 trials.csv inventory differs from records")
    for actual, expected in zip(rows, expected_rows):
        if None in actual or any(value is None for value in actual.values()):
            raise ValueError("GEO-05 trials.csv row width differs from header")
        flat = {**expected, **expected.get("durations_ns", {})}
        if any(actual.get(field) != ("" if flat.get(field) is None else str(flat.get(field))) for field in fields):
            raise ValueError("GEO-05 trials.csv differs from saved records")
    provenance = _json(bundle / "provenance.json")
    if provenance != {key: value for key, value in record["algorithm"].items() if key != "id"}:
        raise ValueError("GEO-05 provenance differs from saved record")
    for filename, hash_field in (("stdout.jsonl", "raw_stdout_sha256"), ("stderr.txt", "raw_stderr_sha256")):
        expected_hash = provenance.get(hash_field)
        if (not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
                or hashlib.sha256((bundle / filename).read_bytes()).hexdigest() != expected_hash):
            raise ValueError("GEO-05 raw process stream differs from provenance: " + filename)
    parse_errors = _json(bundle / "parse-errors.json")
    if not isinstance(parse_errors, list) or len(parse_errors) != record["collection"]["parse_errors"]:
        raise ValueError("GEO-05 parse error count differs from summary")
    try:
        command = _json(bundle / "command.json")
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid GEO-05 command record") from error
    if (not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command)
            or "--measure" not in command or "--warmups" not in command or "--repetitions" not in command):
        raise ValueError("GEO-05 measurement command is invalid")
    try:
        repetitions_arg = command[command.index("--repetitions") + 1]
        warmups_arg = command[command.index("--warmups") + 1]
    except (ValueError, IndexError) as error:
        raise ValueError("GEO-05 measurement repetition/warmup argument is absent") from error
    if (repetitions_arg != str(record["collection"]["measured_repetitions"]) or warmups_arg != "1"):
        raise ValueError("GEO-05 measurement command scope differs from record")


def _validate_source_zip(bundle, archive_path):
    expected = FILES | {"manifest.json"}
    if archive_path.is_symlink():
        raise ValueError("GEO-05 source ZIP cannot be a symlink")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected or archive.testzip() is not None:
                raise ValueError("GEO-05 source ZIP inventory mismatch")
            if any(stat.S_ISLNK(item.external_attr >> 16) for item in archive.infolist()):
                raise ValueError("GEO-05 source ZIP contains a symlink")
            for name in expected:
                if archive.read(name) != (bundle / name).read_bytes():
                    raise ValueError("GEO-05 source ZIP content mismatch: " + name)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise ValueError("invalid GEO-05 source ZIP") from error


def render_page(bundle, publication):
    record = _json(Path(bundle) / "records.json")
    _validate_record(record)
    links = " · ".join(f'<a href="{html.escape(name, quote=True)}">{html.escape(name)}</a>'
                       for name in ("records.json", "trials.csv", "trials.jsonl", "provenance.json", "parse-errors.json"))
    rows = []
    for trial in [*record["warmup_trials"], *record["trials"]]:
        durations = trial.get("durations_ns", {})
        cells = (trial.get("purpose", "measurement"), trial.get("scenario"), trial.get("repetition"),
                 trial.get("status"), trial.get("result_kind"), trial.get("result_encoding"),
                 trial.get("oracle_passed"), trial.get("work_observed"),
                 *(durations.get(phase) for phase in PHASES), trial.get("detail", ""))
        rows.append("<tr>" + "".join("<td>" + html.escape(str(value)) + "</td>" for value in cells) + "</tr>")
    headings = ("Purpose", "Scenario", "Round", "Status", "Result kind", "Result encoding",
                "Literal checks", "Work observed", *PHASES, "Detail")
    limits = "".join("<li>" + html.escape(value) + "</li>" for value in record["evidence_limits"])
    summary_rows = []
    scopes = [("all fixtures", record["collection"]["phases"])]
    scopes.extend((scenario, record["collection"]["by_scenario"][scenario]["phases"]) for scenario in SCENARIOS)
    for scope, phase_summaries in scopes:
        for phase in PHASES:
            stat_row = phase_summaries[phase]
            cells = (scope, phase, stat_row["median_ns"], stat_row["min_ns"], stat_row["max_ns"],
                     stat_row["successful_trials"], stat_row["unavailable_trials"], stat_row["trials_excluded"])
            summary_rows.append("<tr>" + "".join("<td>" + html.escape(str(value) if value is not None else "unavailable") + "</td>"
                                                   for value in cells) + "</tr>")
    assessment = ("Complete fixture attempt matrix; all attempts passed; pending independent review."
                  if record["collection"]["valid_success_summary"] else
                  "INCOMPLETE / INCONCLUSIVE measurement: one or more attempts failed, were unsupported/cancelled, are missing, or the process timed out; all timing summaries are suppressed.")
    counts = html.escape(json.dumps(record["collection"]["counts"], sort_keys=True))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>GEO-05 report "
            + html.escape(publication.report_id) + "</title></head><body><h1>GEO-05 measurement report</h1>"
            + "<p><strong>Assessment: " + html.escape(assessment) + "</strong></p><p>Attempt counts: <code>"
            + counts + "</code></p><p>Report <code>" + html.escape(publication.report_id) + "</code>; source <code>"
            + html.escape(publication.source_report_id) + "</code>.</p><p>Measured scope: "
            + html.escape(publication.measured_scope) + "</p><p>Evidence limits: "
            + html.escape(publication.evidence_limits) + "</p><h2>Saved source files</h2><p>" + links
            + "</p><h2>Attempts, including warmups and failures</h2><table><thead><tr>"
            + "".join("<th>" + html.escape(name) + "</th>" for name in headings)
            + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table><h2>Phase summaries (ns)</h2><table><thead><tr>"
            + "".join("<th>" + html.escape(name) + "</th>" for name in
                     ("Scope", "Phase", "Median", "Min", "Max", "Successful trials", "Unavailable trials", "Excluded trials"))
            + "</tr></thead><tbody>" + "".join(summary_rows) + "</tbody></table><h2>Native evidence limits</h2><ul>"
            + limits + "</ul><p><a href=\"report-envelope.json\">Report envelope</a> · "
            + "<a href=\"publication-manifest.json\">Publication manifest</a></p></body></html>")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files if name != "index.html"}
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    record = _json(bundle / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_report_id": publication.source_report_id,
                "payload": {key: value for key, value in record.items()
                            if key not in ("report_id", "payload_sha256")}}
    files["report-envelope.json"] = common._json_bytes(envelope)
    files["publication-manifest.json"] = common._json_bytes({
        "schema": "csl.algorithm-report-publication-manifest/1", "report_id": publication.report_id,
        "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)

"""Registered publication adapter for SYN-02 terminal minimizer reports."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import statistics
import zipfile
from html import escape

import registered_reports as common
import report_data as data

KIND = "syn02-terminal-minimizers"
SCHEMA = "csl.syn02-terminal-report/1"
MANIFEST_SCHEMA = "csl.syn02-report-manifest/1"
TRIAL_FIELDS = ("scenario", "repetition", "status", "validation_errors", "outcome", "termination", "relation",
                "optimization_present", "optimum_present", "provider", "primal_value", "lower_bound", "upper_bound",
                "prepare_ns", "solve_ns", "oracle_ns", "execute_ns", "solver_observations")
SUMMARY_FIELDS = ("scenario", "requested", "matched_expected", "completed", "failed", "non_success", "expected_outcome",
                  "expected_termination", "observed_outcomes", "observed_terminations", "observed_providers", "relation_count",
                  "objective_bounds", "primal_objective_value", "residual_observations", "timings")
EXPECTED = {
    "linear-face": ("optimal", "completed", "csl.lp.highs", 7.0),
    "constant-linear": ("optimal", "completed", "csl.lp.highs", 3.0),
    "psd-null-direction": ("optimal", "completed", "csl.convex.highs", 0.0),
    "rectangular-residual": ("optimal", "completed", "csl.convex.highs", 0.0),
    "shifted-residual-degenerate": ("undetermined", "numerical_failure", "csl.convex.highs", 0.5),
}


def _json(path):
    return data.parse_json(Path(path).read_text(encoding="utf-8"))


def _map_module():
    path = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results" / "tooling" / "syn02" / "publication_map.py"
    spec = importlib.util.spec_from_file_location("csl_syn02_publication_map", path)
    if spec is None or spec.loader is None:
        raise ValueError("SYN-02 publication map is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(value):
    return common._digest(value)


def _source_inventory(bundle, manifest):
    expected = (set(_map_module().STAGED_SOURCE_FILES) - {"manifest.json"}) | {"index.html"}
    listed = manifest.get("files")
    if not isinstance(listed, dict) or set(listed) != expected:
        raise ValueError("SYN-02 native bundle inventory differs from publication contract")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("SYN-02 native bundle cannot contain symlinks")
        if path.is_file():
            name = path.relative_to(bundle).as_posix()
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("SYN-02 native bundle contains an unsafe path")
            actual.add(name)
    if actual != expected | {"manifest.json"}:
        raise ValueError("SYN-02 native bundle inventory mismatch")
    for name, expected_digest in listed.items():
        if not isinstance(expected_digest, str) or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
            raise ValueError("SYN-02 native manifest digest is invalid")
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected_digest:
            raise ValueError("SYN-02 native bundle hash mismatch: " + name)
    return sorted(actual)


def _validate_record(record, rows):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unsupported SYN-02 native report schema")
    source = record.get("source_commit")
    harness = record.get("harness_commit")
    if not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{40}", source) is None or not isinstance(harness, str) or re.fullmatch(r"[0-9a-f]{40}", harness) is None:
        raise ValueError("SYN-02 source identity is invalid")
    report_id = record.get("report_id")
    if not isinstance(report_id, str) or re.fullmatch(rf"syn02-terminal-\d{{8}}-{source[:8]}-[0-9a-f]{{12}}", report_id) is None:
        raise ValueError("unsafe SYN-02 source identity")
    measurement = record.get("measurement")
    if not isinstance(measurement, dict) or measurement.get("kind") != "descriptive_single_adapter" or measurement.get("repetitions") != 7 or measurement.get("warmups_per_scenario") != 1:
        raise ValueError("SYN-02 measurement scope differs from the validated seven-round protocol")
    if measurement.get("scope") != "Terminal optimizer on resolved objectives and a supplied terminal H-slice; not system simulation or complete control synthesis":
        raise ValueError("SYN-02 measured scope differs from registered policy")
    if not isinstance(record.get("evidence_limits"), list) or not record["evidence_limits"] or not any("no comparator" in item and "scalability" in item for item in record["evidence_limits"]):
        raise ValueError("SYN-02 evidence limits are incomplete")
    if not any("Unestablished" in item for item in record["evidence_limits"]):
        raise ValueError("SYN-02 optimality/relation assurance limit is missing")
    scenario_catalog = record.get("scenario_catalog")
    if not isinstance(scenario_catalog, dict) or set(scenario_catalog) != set(EXPECTED):
        raise ValueError("SYN-02 scenario catalog differs from registered fixtures")
    hashes = record.get("scenario_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(EXPECTED):
        raise ValueError("SYN-02 scenario hash catalog is incomplete")
    scenario_hash = lambda name: hashlib.sha256(json.dumps({"scenario": scenario_catalog[name], "terminal_slice": record.get("terminal_slice")},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if any(hashes[name] != scenario_hash(name) for name in EXPECTED):
        raise ValueError("SYN-02 scenario hash does not match saved fixture")
    if not isinstance(record.get("terminal_slice"), dict) or record["terminal_slice"].get("dimension") != 2:
        raise ValueError("SYN-02 terminal slice identity is invalid")

    if len(rows) != 40:
        raise ValueError("SYN-02 raw event matrix is incomplete")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("schema") != "csl.syn02-terminal-trial/1":
            raise ValueError("SYN-02 raw event schema is invalid")
        name = row.get("scenario")
        if name not in EXPECTED:
            raise ValueError("SYN-02 raw event names an unknown fixture")
        outcome, termination, provider, value = EXPECTED[name]
        repetition = row.get("repetition")
        if type(repetition) is not int or repetition not in range(8) or row.get("warmup") is not (repetition == 0):
            raise ValueError("SYN-02 raw event repetition/warmup identity is invalid")
        key = (name, repetition)
        if key in seen:
            raise ValueError("SYN-02 raw event matrix contains a duplicate")
        seen.add(key)
        if (row.get("source_commit") != source or row.get("harness_commit") != harness
                or row.get("scenario_hash") != hashes[name]
                or row.get("trial_id") != f"{source[:8]}-{harness[:8]}-{name}-{repetition}"):
            raise ValueError("SYN-02 raw event identity differs from records")
        if row.get("status") != "passed" or row.get("validation_errors") != []:
            raise ValueError("SYN-02 contains a failed oracle or malformed trial")
        if (row.get("expected_outcome") != outcome or row.get("expected_termination") != termination
                or row.get("expected_provider") != provider or row.get("outcome") != outcome
                or row.get("termination") != termination or row.get("provider") != provider):
            raise ValueError("SYN-02 trial result differs from literal fixture oracle")
        observations = row.get("solver_observations")
        if not isinstance(observations, dict):
            raise ValueError("SYN-02 solver observations are absent")
        if termination == "completed":
            if row.get("relation") is not True or row.get("optimization_present") is not True or row.get("optimum_present") is not True:
                raise ValueError("SYN-02 optimal trial result fields are incomplete")
            if row.get("relation_support") != "unestablished" or row.get("optimum_support") != "unestablished":
                raise ValueError("SYN-02 trial overstates numerical assurance")
            residuals = (("native.primal_infeasibility", "native.dual_infeasibility") if provider == "csl.lp.highs"
                         else ("check.rows.violation", "check.variables.violation", "check.stationarity.violation"))
            if any(key not in observations or abs(float(observations[key])) > 1e-7 for key in residuals):
                raise ValueError("SYN-02 optimal trial backend residual check failed")
        else:
            if row.get("relation") is not False or row.get("optimization_present") is not True or row.get("termination") != "numerical_failure":
                raise ValueError("SYN-02 expected numerical failure must remain undetermined without a relation")
            if (observations.get("phase.qp.model_status") != 7
                    or observations.get("optimality.withheld") != "original-space checks unavailable or failing"
                    or observations.get("check.stationarity.violation") != 1
                    or "original-space checks unavailable or failing" not in row.get("raw_diagnostics", "")):
                raise ValueError("SYN-02 numerical-failure diagnostic was not preserved")
        actual_value = row.get("primal_value")
        if actual_value is None or abs(float(actual_value) - value) > 1e-7:
            raise ValueError("SYN-02 literal objective value differs from fixture")
    if len(seen) != 40:
        raise ValueError("SYN-02 raw event matrix has missing fixture repetitions")

    expected_summary = _summarize(rows)
    if record.get("summary") != expected_summary:
        raise ValueError("SYN-02 summary differs from raw measured events")
    counts = record.get("attempt_counts")
    expected_counts = {"measured": 35, "matched_expected": 35, "failed": 0, "non_success": 7, "missing": 0}
    if counts != expected_counts:
        raise ValueError("SYN-02 attempt counts differ from raw events")
    profile_summary = record.get("profile_summary")
    if not isinstance(profile_summary, str) or "unknown" not in profile_summary.lower() or not any(token in profile_summary.lower() for token in ("call-stack", "limiter")):
        raise ValueError("SYN-02 profile limiter must remain unknown")


def _summarize(rows):
    result = []
    for name in EXPECTED:
        trials = [row for row in rows if not row["warmup"] and row["scenario"] == name]
        expected = EXPECTED[name]
        successful = [row for row in trials if not row["validation_errors"] and row["termination"] == "completed"]
        item = {"scenario": name, "requested": len(trials), "matched_expected": sum(not row["validation_errors"] for row in trials),
                "completed": len(successful), "failed": sum(bool(row["validation_errors"]) for row in trials),
                "non_success": sum(row["termination"] != "completed" for row in trials),
                "expected_outcome": expected[0], "expected_termination": expected[1], "timings": {}}
        item["observed_outcomes"] = {key: sum(row.get("outcome") == key for row in trials) for key in sorted({row.get("outcome", "missing") for row in trials})}
        item["observed_terminations"] = {key: sum(row.get("termination") == key for row in trials) for key in sorted({row.get("termination", "missing") for row in trials})}
        item["observed_providers"] = {key: sum(row.get("provider") == key for row in trials) for key in sorted({row.get("provider", "missing") for row in trials})}
        item["relation_count"] = sum(row.get("relation") is True for row in trials)
        item["objective_bounds"] = {"lower_available": sum(row.get("lower_bound") is not None for row in trials),
                                    "upper_available": sum(row.get("upper_bound") is not None for row in trials)}
        values = [float(row["primal_value"]) for row in trials if row.get("primal_value") is not None]
        item["primal_objective_value"] = {"min": min(values), "max": max(values), "count": len(values)} if values else None
        residual_fields = ("native.primal_infeasibility", "native.dual_infeasibility", "check.rows.violation", "check.variables.violation",
                           "check.stationarity.violation", "check.signs.violation", "check.complementarity.violation")
        observations = [row.get("solver_observations", {}) for row in trials]
        item["residual_observations"] = {field: {"max": max(float(values[field]) for values in observations if field in values),
            "count": sum(field in values for values in observations)} for field in residual_fields if any(field in values for values in observations)}
        for key in ("prepare_ns", "solve_ns", "oracle_ns", "execute_ns"):
            values = [int(row[key]) for row in successful]
            item["timings"][key] = ({"median_ns": statistics.median(values), "min_ns": min(values), "max_ns": max(values)}
                                    if len(values) >= 5 and len(successful) == len(trials) else None)
        result.append(item)
    return result


def _validate_csv(bundle, rows):
    try:
        actual = (bundle / "trials.csv").read_bytes()
    except OSError as exc:
        raise ValueError("invalid SYN-02 trials.csv") from exc
    if actual != _trials_csv_bytes(rows):
        raise ValueError("SYN-02 CSV trials.csv differs from canonical raw measured event projection")


def _trials_csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=TRIAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if not row["warmup"]:
            writer.writerow({key: (json.dumps(row.get(key), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                             if isinstance(row.get(key), (dict, list)) else row.get(key)) for key in TRIAL_FIELDS})
    return stream.getvalue().encode("utf-8")


def _summary_csv_bytes(summary):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in summary:
        writer.writerow({key: (json.dumps(row[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                         if isinstance(row[key], (dict, list)) else row[key]) for key in SUMMARY_FIELDS})
    return stream.getvalue().encode("utf-8")


def _validate_summary_csv(bundle, summary):
    try:
        actual = (bundle / "summary.csv").read_bytes()
    except OSError as exc:
        raise ValueError("invalid SYN-02 summary.csv") from exc
    if actual != _summary_csv_bytes(summary):
        raise ValueError("SYN-02 summary.csv differs from recomputed records summary")


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("SYN-02 native report bundle cannot be a symlink")
    try:
        record = _json(bundle / "records.json")
        manifest = _json(bundle / "manifest.json")
        if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("report_id") != record.get("report_id"):
            raise ValueError("SYN-02 manifest identity mismatch")
        if manifest.get("source_commit") != record.get("source_commit") or manifest.get("harness_commit") != record.get("harness_commit"):
            raise ValueError("SYN-02 manifest source identity mismatch")
        if bundle.name != record.get("report_id"):
            raise ValueError("SYN-02 source bundle identity mismatch")
        files = _source_inventory(bundle, manifest)
        try:
            rows = [data.parse_json(line) for line in (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid SYN-02 raw event stream") from exc
        _validate_record(record, rows)
        _validate_csv(bundle, rows)
        _validate_summary_csv(bundle, record["summary"])
        data.validate_svg((bundle / "latency.svg").read_bytes())
        projection = _map_module().project(record)
        if _json(bundle / "publication-map.json") != projection:
            raise ValueError("SYN-02 publication map differs from native records")
        native_digest = projection["native_payload_sha256"]
        publisher_bytes = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
        source_hashes = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in files}
        public_id = _map_module().public_report_id(record["report_id"], source_hashes, publisher_bytes)
        if projection["publication_contract"]["report_kind"] != KIND:
            raise ValueError("SYN-02 publication kind differs from registered contract")
        scope = record["measurement"]["scope"]
        limits = "; ".join(record["evidence_limits"])
        return common.PublicationRecord(KIND, public_id, _digest(record), record["source_commit"], scope, limits,
            tuple(sorted(set(files))), SCHEMA, native_digest, record["report_id"])
    except ValueError:
        raise
    except (OSError, KeyError, TypeError, AttributeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("malformed SYN-02 registered report bundle") from exc


def render_page(bundle, publication):
    record = _json(Path(bundle) / "records.json")
    rows = []
    for row in record["summary"]:
        timing = row["timings"]["solve_ns"]
        timing_text = "Unavailable" if timing is None else f'{timing["median_ns"] / 1e6:.3f} ms ({timing["min_ns"]:,}–{timing["max_ns"]:,} ns)'
        rows.append("<tr><th>" + escape(row["scenario"]) + "</th><td>" + escape(row["expected_outcome"]) + "</td><td>" +
            escape(row["expected_termination"]) + "</td><td>" + str(row["matched_expected"]) + "/" + str(row["requested"]) +
            "</td><td>" + str(row["failed"]) + "</td><td>" + str(row["non_success"]) + "</td><td>" + timing_text + "</td></tr>")
    evidence = "".join("<li>" + escape(item) + "</li>" for item in record["evidence_limits"])
    links = "".join("<li><a href=\"" + escape(name, quote=True) + "\">" + escape(name) + "</a></li>"
                    for name in publication.files if name in {"records.json", "trials.csv", "raw-events.jsonl", "latency.svg", "profile-evidence.json"})
    failed = next(row for row in record["summary"] if row["scenario"] == "shifted-residual-degenerate")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>SYN-02 terminal minimizers — " +
        escape(publication.report_id) + "</title></head><body><h1>Terminal minimizer relations (SYN-02)</h1><p>Descriptive single-adapter measurements using the public <code>TerminalOptimizer</code> with HiGHS LP and convex providers.</p><p>Source report <code>" +
        escape(publication.source_report_id) + "</code>; measured algorithm commit <code>" + escape(publication.source_commit) + "</code>.</p><p>Scope: " +
        escape(publication.measured_scope) + ". No comparator, speedup, or application-scale claim is made.</p><figure aria-label=\"Solve latency figure\"><a href=\"latency.svg\">View solve latency ranges by fixture</a><figcaption>Median and min–max solve time; values appear only for fully expected fixture groups.</figcaption></figure><table><thead><tr><th>Fixture</th><th>Expected outcome</th><th>Expected termination</th><th>Matched/requested</th><th>Failed</th><th>Non-success</th><th>Solve time</th></tr></thead><tbody>" +
        "".join(rows) + "</tbody></table><p>The shifted-residual fixture retains <code>undetermined</code> with <code>numerical_failure</code> and no constructed relation in all " +
        str(failed["non_success"]) + " measured trials. These expected numerical failures remain visible and are not filtered from the results.</p><h2>Evidence limits</h2><ul>" + evidence +
        "</ul><p>Profile limiter: unknown. Outcome support and relation support remain Unestablished.</p><h2>Saved evidence</h2><ul>" + links +
        "</ul><p><a href=\"report-envelope.json\">Versioned envelope</a> · <a href=\"publication-manifest.json\">Publication manifest</a></p></body></html>")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files if name != "index.html"}
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    payload = _json(bundle / "records.json")
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

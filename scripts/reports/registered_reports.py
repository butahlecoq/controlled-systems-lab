"""Explicit boundary adapters for validated non-LP report records."""
from dataclasses import dataclass, replace
import csv
import hashlib
import json
from pathlib import Path
import re
from html import escape
import io
import statistics
import zipfile


OPT_TOP_FILES = {"README.md", "analyze_profile.py", "collect.py", "index.html", "latency.svg", "records.json", "render_saved.py", "summary.csv", "test_validate_report.py", "trials.csv", "validate_report.py"}
OPT_NESTED_FILES = {"evidence/accepted-001/build-log-sanitized.txt", "evidence/accepted-001/concurrent-work.txt", "evidence/accepted-001/process-stderr.txt", "evidence/accepted-001/process-stdout.jsonl", "evidence/accepted-001/records.json", "evidence/accepted-001/summary.csv", "evidence/accepted-001/trials.csv", "evidence/accepted-002/build-log-sanitized.txt", "evidence/accepted-002/build-provenance.json", "evidence/accepted-002/concurrent-work.txt", "evidence/accepted-002/hull_measure.cpp", "evidence/accepted-002/process-stderr.txt", "evidence/accepted-002/process-stdout.jsonl", "evidence/accepted-002/records.json", "evidence/accepted-002/summary.csv", "evidence/accepted-002/trials.csv", "harness/CMakeLists.txt", "harness/hull_measure.cpp", "profile/README.md", "profile/final/profile-stderr.txt", "profile/final/profile-summary.jsonl", "profile/profile-stderr.txt", "profile/raw-profile.jsonl", "profile/target-process-samples.csv", "profile/target-process-samples.json"}
GEO_FILES = {"README.md", "build-provenance.txt", "environment.json", "index.html", "latency.svg", "measurement-command.txt", "process-stderr.txt", "profile.txt", "raw-driver-output.csv", "raw-events.jsonl", "records.json", "scenarios.json", "summary.csv", "trials.csv"}
LEGACY_REGISTERED_PUBLISHER_SHA256 = "7c6d9913396b1f8a2dd8d74e14a37536b659bc7552c0a5d0d3ed85fbb801793a"


@dataclass(frozen=True)
class PublicationRecord:
    kind: str
    report_id: str
    payload_sha256: str
    source_commit: str
    measured_scope: str
    evidence_limits: str
    files: tuple[str, ...] = ()
    payload_schema: str = ""
    native_payload_sha256: str = ""
    source_report_id: str = ""


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _adapt_payload(record):
    if not isinstance(record, dict):
        raise ValueError("report record must be an object")
    schema = record.get("schema")
    rid = record.get("report_id")
    if schema == "csl.hull-benchmark-records/1":
        if re.fullmatch(r"opt06-basis-reuse-\d{8}-[0-9a-f]{8}-r2", str(rid)):
            trials = record.get("trials")
            fixtures = record.get("fixtures")
            summary = record.get("summary")
            if not isinstance(trials, list) or len(trials) != 48 or not isinstance(fixtures, list) or not isinstance(summary, list):
                raise ValueError("OPT-06 requires the frozen 48-row accepted collection")
            points = {row.get("case_id"): row.get("points") for row in fixtures if isinstance(row, dict)}
            expected = {"permuted": 10, "degenerate": 7, "interior-basis": 5}
            if points != expected or len(summary) != 6:
                raise ValueError("OPT-06 fixture or summary catalog differs")
            measured = [trial for trial in trials if not trial.get("warmup")]
            from collections import Counter
            groups = Counter((trial.get("case_id"), trial.get("method")) for trial in measured)
            expected_groups = {(case, method) for case in expected for method in ("baseline", "basis-reuse")}
            if len(measured) != 42 or groups != {key: 7 for key in expected_groups}:
                raise ValueError("OPT-06 requires seven measured pairs per fixture and method")
            for trial in trials:
                case, method = trial.get("case_id"), trial.get("method")
                ids = trial.get("retained_points")
                if (case not in expected or method not in ("baseline", "basis-reuse") or trial.get("status") != "complete"
                        or trial.get("verified") is not True or trial.get("output_ids_valid") is not True
                        or trial.get("contains_all_inputs") is not True or not isinstance(ids, list) or not ids
                        or len(ids) != len(set(ids)) or any(type(i) is not int or not 0 <= i < expected[case] for i in ids)
                        or trial.get("retained") != len(ids)):
                    raise ValueError("OPT-06 trial failed completion, oracle, or point-ID validation")
            interior = [trial for trial in measured if trial["case_id"] == "interior-basis"]
            if any(0 not in trial.get("basis_points", []) or 0 not in trial["retained_points"] for trial in interior if trial["method"] == "basis-reuse"):
                raise ValueError("OPT-06 structural interior-basis evidence missing")
            if not all(trial["status"] == "complete" for trial in interior if trial["method"] == "baseline"):
                raise ValueError("OPT-06 interior baseline incomplete")
            for row in summary:
                group = [trial for trial in measured if (trial["case_id"], trial["method"]) == (row.get("case_id"), row.get("method"))]
                times = [trial["elapsed_ns"] for trial in group]
                if len(group) != 7 or row.get("attempts") != 7 or row.get("successes") != 7 or row.get("failures") != 0:
                    raise ValueError("OPT-06 summary group does not match trials")
                if (row.get("median_ns") != statistics.median(times) or row.get("min_ns") != min(times)
                        or row.get("max_ns") != max(times)):
                    raise ValueError("OPT-06 timing summary differs from trials")
                for field, trial_field in (("median_membership_lp_calls", "lp_calls"), ("median_basis_solves", "basis_solves"),
                                           ("median_pivots", "pivots"), ("median_degenerate_pivots", "degenerate_pivots"),
                                           ("median_bulk_candidates", "bulk_candidates"), ("median_bulk_removals", "bulk_removals")):
                    if row.get(field) != statistics.median([trial[trial_field] for trial in group]):
                        raise ValueError("OPT-06 counter summary differs from trials")
            code_commit = record.get("code_commit", "")
            if not re.fullmatch(r"[0-9a-f]{40}", str(code_commit)) or not rid.endswith(code_commit[:8] + "-r2"):
                raise ValueError("OPT-06 measured source identity mismatch")
            if not record.get("complexity", {}).get("representation") or not record.get("complexity", {}).get("work") or not record.get("evaluation_plan"):
                raise ValueError("OPT-06 complexity/evaluation contract missing")
            return PublicationRecord("opt06-basis-reuse", rid, _digest(record), code_commit,
                "42 verified measured trials across three small two-dimensional point clouds",
                "Descriptive paired timings only; no speedup claim or limiter profile; input-containment oracle uses numerical HiGHS LP checks",
                payload_schema=schema, source_report_id=rid)
        if not re.fullmatch(r"opt05-hull-\d{8}-[0-9a-f]{8}", str(rid)):
            raise ValueError("unsafe OPT-05 report ID")
        trials = record.get("trials")
        if not isinstance(trials, list) or any(not isinstance(t, dict) for t in trials):
            raise ValueError("OPT-05 trials must be objects")
        measured = [t for t in trials if not t.get("warmup")]
        if len(measured) != 21 or any(t.get("status") != "complete" or t.get("verified") is not True for t in measured):
            raise ValueError("OPT-05 requires 21 verified measured trials")
        from collections import Counter
        if Counter(t["case_id"] for t in measured) != {"grid-25": 7, "grid-81": 7, "grid-169": 7}:
            raise ValueError("OPT-05 case trial groups differ")
        expected_points={"grid-25":25,"grid-81":81,"grid-169":169}
        summary_keys=[row.get("case_id") for row in record.get("summary", []) if isinstance(row,dict)]
        if len(summary_keys)!=3 or set(summary_keys)!=set(expected_points):
            raise ValueError("OPT-05 summary must contain each expected case exactly once")
        if any(row.get("points")!=expected_points.get(row.get("case_id")) for row in record.get("summary",[])) or any(t.get("points")!=expected_points.get(t.get("case_id")) for t in measured):
            raise ValueError("OPT-05 point count differs from named case")
        code_commit = record.get("code_commit", "")
        if not re.fullmatch(r"[0-9a-f]{40}", str(code_commit)) or record.get("fixture", {}).get("oracle") is None:
            raise ValueError("OPT-05 source/fixture evidence missing")
        if rid.rsplit("-", 1)[1] != code_commit[:8]:
            raise ValueError("OPT-05 report ID does not match source commit")
        summary = record.get("summary")
        limits = record.get("fixture", {}).get("assurance", "")
        if not isinstance(summary, list) or not summary or any(not isinstance(row, dict) for row in summary) or not isinstance(limits, str) or "not exact arithmetic" not in limits:
            raise ValueError("OPT-05 assurance boundary missing")
        for row in summary:
            group=[t for t in measured if t.get("case_id")==row.get("case_id")]
            if len(group)!=7 or row.get("attempts")!=len(group) or row.get("successes")!=sum(t.get("status")=="complete" for t in group) or row.get("failures")!=sum(t.get("status")!="complete" for t in group):
                raise ValueError("OPT-05 summary group differs from trials")
            for field,fn in (("median_ns",lambda xs:statistics.median(xs)),("min_ns",min),("max_ns",max)):
                if row.get(field)!=fn([t["elapsed_ns"] for t in group]): raise ValueError("OPT-05 timing summary differs from trials")
            if row.get("median_lp_calls")!=statistics.median([t["lp_calls"] for t in group]): raise ValueError("OPT-05 LP-call summary differs from trials")
        return PublicationRecord("opt05-hull", rid, _digest(record), code_commit, "21 verified measured trials across 5x5, 9x9, and 13x13 square lattices", "No comparator; " + limits, payload_schema=schema, source_report_id=rid)
    if schema == "csl.geo03-hv-report/1":
        payload = record.get("payload")
        if not isinstance(payload, dict) or _digest(payload) != record.get("payload_sha256"):
            raise ValueError("GEO-03 payload digest mismatch")
        measurement = payload.get("measurement")
        if not isinstance(measurement, dict) or payload.get("schema") != schema or measurement.get("emitted_trials") != 56:
            raise ValueError("GEO-03 measured trial scope mismatch")
        trials = payload.get("trials")
        summary = payload.get("summary")
        if not isinstance(trials, list) or any(not isinstance(t, dict) for t in trials) or not isinstance(summary, list) or any(not isinstance(t, dict) for t in summary):
            raise ValueError("GEO-03 trials and summary must be object lists")
        if measurement.get("failures") != 0 or any(t.get("failures") != 0 for t in summary):
            raise ValueError("GEO-03 contains failed trials")
        from collections import Counter
        groups = Counter((t.get("fixture"), t.get("direction")) for t in trials)
        expected_groups={(fixture,direction) for fixture in ("embedded-segment","simplex","singleton","square") for direction in ("H-to-V","V-to-H")}
        summary_keys=[(row.get("fixture"),row.get("direction")) for row in summary]
        if len(trials) != 56 or set(groups)!=expected_groups or set(groups.values()) != {7} or any(t.get("oracle_passed") != "true" for t in trials):
            raise ValueError("GEO-03 requires eight seven-trial oracle-passing groups")
        if len(summary_keys)!=8 or set(summary_keys)!=expected_groups:
            raise ValueError("GEO-03 summary must contain each fixture/direction group exactly once")
        limits = payload.get("scope_limitations")
        if not isinstance(limits, list) or not limits:
            raise ValueError("GEO-03 scope limitations required")
        for row in summary:
            group=[t for t in trials if (t.get("fixture"),t.get("direction"))==(row.get("fixture"),row.get("direction"))]
            if len(group)!=7 or row.get("trials")!=7:
                raise ValueError("GEO-03 summary group differs from trials")
            for metric in ("run_ns","total_ns","preparation_ns","workspace_creation_ns"):
                values=[t[metric] for t in group]
                measured_stats=row.get(metric)
                if not isinstance(measured_stats,dict) or measured_stats.get("median")!=statistics.median(values) or measured_stats.get("min")!=min(values) or measured_stats.get("max")!=max(values):
                    raise ValueError("GEO-03 timing summary differs from trials")
        source = payload.get("report_source_commit")
        if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
            raise ValueError("GEO-03 full report source commit required")
        if not isinstance(record.get("report_id"), str) or not re.fullmatch(r"geo03-\d{8}-[0-9a-f]{12}", record["report_id"]):
            raise ValueError("unsafe GEO-03 report ID")
        if not record["report_id"].endswith(record["payload_sha256"][:12]):
            raise ValueError("GEO-03 report ID does not match payload digest")
        return PublicationRecord("geo03-hv", record["report_id"], record["payload_sha256"], source, "56 measured trials across four bounded 2D fixtures in both conversion directions", "; ".join(limits), payload_schema=schema, source_report_id=record["report_id"])
    raise ValueError("unregistered report schema")


def adapt_payload(record):
    try:
        return _adapt_payload(record)
    except ValueError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError("malformed registered report payload") from error


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("registered source bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    result = adapt_payload(record)
    if bundle.name != (result.source_report_id or result.report_id):
        raise ValueError("registered source bundle identity mismatch")
    if result.kind in ("opt05-hull", "opt06-basis-reuse"):
        listed = {}
        for line in (bundle / "manifest.sha256").read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
            if not match:
                raise ValueError("invalid OPT-05 manifest entry")
            listed[match.group(2)] = match.group(1)
    else:
        manifest = _json(bundle / "manifest.json")
        if manifest.get("schema") != "csl.geo03-report-manifest/1" or manifest.get("report_id") != result.report_id:
            raise ValueError("GEO-03 manifest identity mismatch")
        listed = manifest.get("files", {})
    if result.kind in ("opt05-hull", "opt06-basis-reuse"):
        allowed=OPT_TOP_FILES|OPT_NESTED_FILES
        if result.kind == "opt06-basis-reuse":
            safe_names = all(re.fullmatch(r"(?:README\.md|index\.html|latency\.svg|measurement-attestation\.json|records\.json|raw-(?:stdout\.jsonl|stderr\.txt)|release-build-log-sanitized\.txt|summary\.csv|trials\.csv|harness/(?:manifest\.sha256|CMakeLists\.txt|collect\.py|opt06_measure\.cpp|package\.py|render\.py|validate\.py)|evidence/manifest\.sha256|evidence/(?:accepted-002|failed-attempts(?:/failed-attempt-[0-9]{3}|/failed-attempt-collector-[0-9]{3})?|superseded(?:/superseded-[A-Za-z0-9-]+)?)/(?:README\.md|index\.html|latency\.svg|manifest\.sha256|records\.json|raw-(?:stdout\.jsonl|stderr\.txt)|release-build-log-sanitized\.txt|summary\.csv|trials\.csv))", name) for name in listed)
            if not safe_names or not set(listed) or not {"README.md", "index.html", "latency.svg", "records.json", "raw-stdout.jsonl", "raw-stderr.txt", "summary.csv", "trials.csv", "release-build-log-sanitized.txt", "harness/opt06_measure.cpp", "harness/collect.py", "harness/render.py", "harness/validate.py", "harness/package.py", "evidence/accepted-002/records.json", "evidence/accepted-002/raw-stdout.jsonl", "evidence/accepted-002/trials.csv"} <= set(listed):
                raise ValueError("OPT-06 registered inventory pattern mismatch")
        elif not set(listed)<=allowed or not set(OPT_TOP_FILES)-{"test_validate_report.py"}<=set(listed) or not OPT_NESTED_FILES<=set(listed):
            raise ValueError("OPT-05 registered inventory pattern mismatch")
        expected_files=set(listed)|{"manifest.sha256","bundle.zip","bundle.zip.sha256"}
    elif set(listed) != GEO_FILES:
        raise ValueError("registered bundle inventory mismatch")
    else:
        expected_files=set(listed)|{"manifest.json"}
    actual_files=set()
    for path in bundle.rglob("*"):
        if path.is_symlink(): raise ValueError("symlinks are forbidden in registered bundle")
        if path.is_file(): actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != expected_files:
        raise ValueError("registered bundle has missing or unregistered files")
    for name, expected in listed.items():
        path = bundle / name
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or any(part.is_symlink() for part in [bundle, *(bundle / Path(*relative.parts[:i]) for i in range(1, len(relative.parts)))]) or not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("unsafe or tampered registered bundle file: " + name)
    _validate_saved_csv(bundle, record, result.kind)
    if result.kind in ("opt05-hull", "opt06-basis-reuse"):
        _validate_opt05_bundle_zip(bundle, listed)
    public_id = _publication_id(bundle, result.source_report_id, actual_files)
    publication = PublicationRecord(result.kind, public_id, result.payload_sha256, result.source_commit, result.measured_scope, result.evidence_limits, tuple(sorted(listed)), result.payload_schema, source_report_id=result.source_report_id)


    return preserve_historical_publication(bundle, publication, offline_zip)

def _publication_id(bundle, source_id, source_files):
    # Source files contain no publication output, so hashing the full validated
    # inventory, including native manifests/ZIPs, introduces no digest cycle.
    # This module owns the staged page, envelope, manifest and offline ZIP.
    publisher_source = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    publisher_digest = (LEGACY_REGISTERED_PUBLISHER_SHA256 if source_id.startswith(("opt05-hull-", "geo03-"))
                        else hashlib.sha256(publisher_source).hexdigest())
    identity = {
        "schema": "csl.registered-publication-identity/1",
        "source_report_id": source_id,
        "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(source_files)},
        "publisher_sha256": publisher_digest,
    }
    return source_id.rsplit("-", 1)[0] + "-" + _digest(identity)


def _validate_saved_csv(bundle, record, kind):
    if kind == "opt06-basis-reuse":
        trial_fields = ("round", "case_id", "method", "warmup", "elapsed_ns", "status", "verified", "output_ids_valid", "contains_all_inputs", "lp_calls", "basis_solves", "pivots", "degenerate_pivots", "bulk_candidates", "bulk_removals", "retained", "fallback", "retained_points", "basis_points")
        trials = [{field: json.dumps(trial[field]) if field in ("retained_points", "basis_points") else trial[field] for field in trial_fields} for trial in record["trials"]]
        summary_fields = ("case_id", "method", "attempts", "successes", "failures", "median_ns", "min_ns", "max_ns", "median_membership_lp_calls", "median_basis_solves", "median_pivots", "median_degenerate_pivots", "median_bulk_candidates", "median_bulk_removals")
        summary = [{field: row[field] for field in summary_fields} for row in record["summary"]]
        _compare_csv(bundle / "trials.csv", trial_fields, trials)
        _compare_csv(bundle / "summary.csv", summary_fields, summary)
        return
    if kind == "opt05-hull":
        trial_fields = ("case_id", "round", "points", "warmup", "elapsed_ns", "status", "verified", "lp_calls", "attempts", "removed", "retained")
        outcome_fields = ("feasible", "infeasible", "unsupported", "stopped", "numerical_failure", "malformed_result")
        trials = [{**{field: trial[field] for field in trial_fields},
                   **{field: trial["outcomes"][field] for field in outcome_fields}}
                  for trial in record["trials"]]
        summary_fields = ("case_id", "points", "attempts", "successes", "failures", "median_ns", "min_ns", "max_ns", "median_lp_calls")
        summary = [{field: row[field] for field in summary_fields} for row in record["summary"]]
        _compare_csv(bundle / "trials.csv", trial_fields + outcome_fields, trials)
        _compare_csv(bundle / "summary.csv", summary_fields, summary)
        return
    payload = record["payload"]
    trials = payload["trials"]
    trial_fields = ("fixture", "direction", "round", "converter_id", "converter_version", "lp_backend_id", "lp_backend_version", "ambient_dimension", "input_representation", "output_representation", "input_inequalities", "input_equalities", "input_vertices", "input_rays", "preparation_ns", "workspace_creation_ns", "run_ns", "total_ns", "output_inequalities", "output_equalities", "output_vertices", "output_rays", "oracle_checks", "oracle_passed")
    summary_fields = ("fixture", "direction", "trials", "failures", "all_oracles_passed") + tuple(f"{metric}_{stat}_ns" for metric in ("preparation_ns", "workspace_creation_ns", "run_ns", "total_ns") for stat in ("median", "min", "max", "range"))
    summary = []
    for row in payload["summary"]:
        flat = {field: row[field] for field in summary_fields[:5]}
        for metric in ("preparation_ns", "workspace_creation_ns", "run_ns", "total_ns"):
            for stat in ("median", "min", "max", "range"):
                flat[f"{metric}_{stat}_ns"] = row[metric][stat]
        summary.append(flat)
    _compare_csv(bundle / "trials.csv", trial_fields, trials)
    _compare_csv(bundle / "summary.csv", summary_fields, summary)


def _compare_csv(path, fields, expected_rows):
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(fields):
                raise ValueError(f"{path.name} headers differ from validated records")
            actual_rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(f"invalid registered {path.name}") from error
    if len(actual_rows) != len(expected_rows):
        raise ValueError(f"{path.name} row count differs from validated records")
    for actual, expected in zip(actual_rows, expected_rows):
        if set(actual) != set(fields) or any(actual.get(field) != str(expected[field]) for field in fields):
            raise ValueError(f"{path.name} differs from validated records")


def _validate_opt05_bundle_zip(bundle, listed):
    archive_path = bundle / "bundle.zip"
    checksum_path = bundle / "bundle.zip.sha256"
    try:
        sidecar = checksum_path.read_text(encoding="ascii")
        match = re.fullmatch(r"([0-9a-f]{64})  bundle\.zip\n?", sidecar)
        if match is None or hashlib.sha256(archive_path.read_bytes()).hexdigest() != match.group(1):
            raise ValueError("OPT-05 bundle ZIP checksum mismatch")
        expected_names = {f"{bundle.name}/{name}" for name in set(listed) | {"manifest.sha256"}}
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected_names:
                raise ValueError("OPT-05 bundle ZIP inventory mismatch")
            if archive.testzip() is not None:
                raise ValueError("OPT-05 bundle ZIP content mismatch")
            for name in listed:
                if archive.read(f"{bundle.name}/{name}") != (bundle / name).read_bytes():
                    raise ValueError("OPT-05 bundle ZIP content mismatch: " + name)
            if archive.read(f"{bundle.name}/manifest.sha256") != (bundle / "manifest.sha256").read_bytes():
                raise ValueError("OPT-05 bundle ZIP content mismatch: manifest.sha256")
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise ValueError("invalid OPT-05 bundle ZIP") from error


def render_page(bundle, publication):
    """Render the publication view from validated typed data, never producer HTML."""
    bundle = Path(bundle)
    links = [f'<a href="{escape(name, quote=True)}">{escape(name)}</a>' for name in publication.files if name in {"records.json", "trials.csv", "summary.csv", "latency.svg"}]
    record=json.loads((bundle/"records.json").read_text(encoding="utf-8"))
    if publication.kind=="geo03-hv": record=record["payload"]
    if publication.kind in ("opt05-hull", "opt06-basis-reuse"):
        if publication.kind == "opt06-basis-reuse":
            rows=''.join('<tr><td>'+escape(str(row["case_id"]))+'</td><td>'+escape(str(row["method"]))+'</td><td>'+str(row["attempts"])+'</td><td>'+str(row["failures"])+'</td><td>'+f'{row["median_ns"]:,}'+'</td><td>'+f'{row["min_ns"]:,}'+'</td><td>'+f'{row["max_ns"]:,}'+'</td><td>'+str(row["median_membership_lp_calls"])+'</td><td>'+str(row["median_basis_solves"])+'</td><td>'+str(row["median_pivots"])+'</td><td>'+str(row["median_bulk_removals"])+'</td></tr>' for row in record["summary"])
            table='<table><thead><tr><th>Case</th><th>Method</th><th>Trials</th><th>Failures</th><th>Median ns</th><th>Min ns</th><th>Max ns</th><th>Membership LP calls (excluding Phase-I)</th><th>Phase-I solves</th><th>Pivots</th><th>Bulk removals</th></tr></thead><tbody>'+rows+'</tbody></table>'
        else:
            rows=''.join('<tr><td>'+escape(str(row["case_id"]))+'</td><td>'+str(row["points"])+'</td><td>'+str(row["attempts"])+'</td><td>'+str(row["failures"])+'</td><td>'+f'{row["median_ns"]:,}'+'</td><td>'+f'{row["min_ns"]:,}'+'</td><td>'+f'{row["max_ns"]:,}'+'</td><td>'+str(row["median_lp_calls"])+'</td></tr>' for row in record["summary"])
            table='<table><thead><tr><th>Case</th><th>Points</th><th>Attempts</th><th>Failures</th><th>Median ns</th><th>Min ns</th><th>Max ns</th><th>Median LP calls</th></tr></thead><tbody>'+rows+'</tbody></table>'
    else:
        rows=''.join('<tr><td>'+escape(row["fixture"])+'</td><td>'+escape(row["direction"])+'</td><td>'+str(row["trials"])+'</td><td>'+str(row["failures"])+'</td>'+''.join('<td>'+f'{row[metric][key]:,}'+'</td>' for metric in ("run_ns","total_ns") for key in ("median","min","max"))+'</tr>' for row in record["summary"])
        table='<table><thead><tr><th>Fixture</th><th>Direction</th><th>Trials</th><th>Failures</th>'+''.join('<th>'+metric.replace("_ns", "")+' '+key+' ns</th>' for metric in ("run_ns","total_ns") for key in ("median","min","max"))+'</tr></thead><tbody>'+rows+'</tbody></table>'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>' + escape(publication.report_id) +
            '</title></head><body><h1>' + escape(publication.kind) + ' measurement report</h1><p><code>' +
            escape(publication.report_id) + '</code></p><h2>Measured scope</h2><p>' + escape(publication.measured_scope) +
            '</p><h2>Saved measurements</h2>'+table+'<h2>Evidence limits</h2><p>' + escape(publication.evidence_limits) + '</p><p>Source commit <code>' +
            escape(publication.source_commit) + '</code></p><p><a href="report-envelope.json">Versioned report envelope</a></p><p><a href="publication-manifest.json">Publication manifest</a></p><p><a href="latency.svg">Checked latency SVG</a></p><ul><li>' + '</li><li>'.join(links) + '</li></ul></body></html>')


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def publication_envelope(bundle, publication):
    record = _json(Path(bundle) / "records.json")
    payload = record if publication.kind in ("lp", "convex", "opt05-hull", "opt06-basis-reuse") else record["payload"]
    envelope = {
        "schema": "csl.algorithm-report-envelope/1",
        "report_id": publication.report_id,
        "report_kind": publication.kind,
        "payload_schema": publication.payload_schema,
        "payload_sha256": publication.payload_sha256,
        "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope,
        "evidence_limits": publication.evidence_limits,
        "payload": payload,
    }
    if publication.kind in ("lp", "convex"):
        envelope["native_payload_sha256"] = publication.native_payload_sha256
    if publication.source_report_id:
        envelope["source_report_id"] = publication.source_report_id
    return envelope


def publication_artifacts(bundle, publication, page_bytes=None):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files if name != "index.html"}
    files["index.html"] = page_bytes if page_bytes is not None else render_page(bundle, publication).encode("utf-8")
    files["report-envelope.json"] = _json_bytes(publication_envelope(bundle, publication))
    files["publication-manifest.json"] = _json_bytes({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": publication.report_id,
        "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)},
    })
    return files


def publication_zip(report_id, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        entries = [("index.html", files["index.html"])] + [(report_id + "/" + name, files[name]) for name in sorted(files)]
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.flag_bits = 0
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def validate_publication_manifest(report_dir, expected):
    report_dir = Path(report_dir)
    try:
        if report_dir.is_symlink():
            raise ValueError("publication directory is a symlink")
        manifest = _json(report_dir / "publication-manifest.json")
        envelope = _json(report_dir / "report-envelope.json")
        actual = set()
        for path in report_dir.rglob("*"):
            if path.is_symlink():
                raise ValueError("publication files cannot be symlinks")
            if path.is_file() and path.name != "publication-manifest.json":
                actual.add(path.relative_to(report_dir).as_posix())
        if manifest.get("schema") != "csl.algorithm-report-publication-manifest/1" or manifest.get("report_id") != expected.get("report_id") or manifest.get("report_kind") != expected.get("report_kind"):
            raise ValueError("publication manifest identity/schema mismatch")
        entries = manifest.get("files")
        if not isinstance(entries, dict) or set(entries) != actual:
            raise ValueError("publication manifest inventory mismatch")
        for name, digest in entries.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or not isinstance(digest, str):
                raise ValueError("publication manifest contains an unsafe entry")
            path = report_dir / relative
            if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("publication manifest file hash mismatch")
        fields = ("report_id", "report_kind", "payload_schema", "payload_sha256", "source_commit", "measured_scope", "evidence_limits")
        if envelope.get("schema") != "csl.algorithm-report-envelope/1" or any(envelope.get(field) != expected.get(field) for field in fields):
            raise ValueError("publication envelope identity/schema mismatch")
        if expected.get("native_payload_sha256", "") != envelope.get("native_payload_sha256", ""):
            raise ValueError("publication envelope native payload hash mismatch")
        if expected.get("source_report_id", "") != envelope.get("source_report_id", ""):
            raise ValueError("publication envelope source identity mismatch")
        if _digest(envelope.get("payload")) != expected.get("payload_sha256"):
            raise ValueError("publication envelope payload hash mismatch")
        if not isinstance(envelope.get("payload"), dict) or envelope["payload"].get("schema") != expected.get("payload_schema"):
            raise ValueError("publication envelope payload schema mismatch")
        if expected.get("report_kind") in ("lp", "convex"):
            payload = envelope["payload"]
            if payload.get("payload_sha256") != expected.get("native_payload_sha256"):
                raise ValueError("publication native payload hash mismatch")
        return True
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("publication manifest or envelope is malformed") from error


def offline_zip(bundle, publication):
    bundle=Path(bundle)
    files=publication_artifacts(bundle,publication)
    return publication_zip(publication.report_id,files)


def validate_source_inventory(bundle, listed, expected_files, *, label):
    """Apply the same local-file and complete-inventory boundary to native kinds."""
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError(f"{label} source bundle cannot be a symlink")
    if not isinstance(listed, dict) or set(listed) != set(expected_files):
        raise ValueError(f"{label} registered source inventory mismatch")
    expected = set(expected_files) | {"manifest.json"}
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlinks are forbidden in {label} bundle")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != expected:
        raise ValueError(f"{label} bundle has missing or unregistered files")
    for name, digest in listed.items():
        relative = Path(name)
        if (not isinstance(name, str) or relative.is_absolute() or ".." in relative.parts
                or "\\" in name or ":" in name or not name or
                not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ValueError(f"unsafe {label} bundle file: {name}")
        path = bundle / relative
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"{label} source file hash mismatch: {name}")


def assemble_publication(bundle, publication, *, page, envelope, source_files):
    """Stage the common page/envelope/manifest inventory from admitted native data."""
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in source_files if name != "index.html"}
    files["index.html"] = page.encode("utf-8")
    files["report-envelope.json"] = _json_bytes(envelope)
    files["publication-manifest.json"] = _json_bytes({
        "schema": "csl.algorithm-report-publication-manifest/1", "report_id": publication.report_id,
        "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files


# Exact pre-#251 source and publication bytes; never applies to changed evidence.
_HISTORICAL_PUBLICATIONS = {
    "geo02-20261012T235755Z-6b1f504ad3db": {
        "inventory_sha256": "88d808f0005a6a1bc88fa36c3de90b0e0175135345dc3cd842e2e44fb2d59729",
        "report_id": "geo02-20261012T235755Z-7275580339899c6ac27496fc2b05cb040d9fec14f8ec7f8bf219cc299c55eefc",
        "zip_sha256": "8f2fe77d30b69a0a314a7cd9dbe69342d2d5e9dde6eccc891afafcde04e578a9"
    },
    "geo02-20261013T061151Z-338ff7d1d63c": {
        "inventory_sha256": "0993f90fb86db847c71bf7821dd5c7cc3bce34bbf3435eef5e0d86f1f3a953c2",
        "report_id": "geo02-20261013T061151Z-449f188d2de1f50164a55a7b3b3931132dfa8384306ac3c93d5fb3a958cbd754",
        "zip_sha256": "e9068d76389a5a5d66a4f73ca49e259edae618faad99c1b8b7a41f05df92669a"
    },
    "geo03-20261012-3c12ca125831": {
        "inventory_sha256": "9b6c03f342b1c82fbd7e582c9c08846dea5983f0e1bc2d9b3d031a2afbabbf82",
        "report_id": "geo03-20261012-30157d9ac59269cc26a2ca24dfd1744297971b435a8bba13dcb68f2a1dbcd104",
        "zip_sha256": "8e62aa3394ae02797329ab1244d863966a7c770fbcbdd60a51eb4362d8e49abe"
    },
    "geo04-20261012T224946Z-c37852bcc80d": {
        "inventory_sha256": "5a5ec6f0ffbe4731c5e1ed6287ee46e86bde7ca3d79c4ea4c7ba49f5b55bc1e5",
        "report_id": "geo04-20261012T224946Z-30606c76deb657567eb86a451c474c5aa796827651262a550b15fa4cb4ece549",
        "zip_sha256": "a708532a9068fa8127f742b7370f38836ce31e7af2d09f8633caf97ed8946db1"
    },
    "geo05-4dc3c0557570a52e": {
        "inventory_sha256": "4e01fdca414522270a70b80818273c1e7b8baf80a223d4e76514936a4cb46f1c",
        "report_id": "geo05-8918ad3ac4b0b3d1ff9c8b807d6b509f324ef3e9b11716be496c8e6e437f6795",
        "zip_sha256": "51826297b765b011423ca58fb3160fbdd4884c176d73adaf5eabc5f2508fefba"
    },
    "opt04-20261013T172839Z-6451c4b89d3b": {
        "inventory_sha256": "238ff015f68d98e385593d844436a562317e12bb0f7cdedbe07e96af7f32bda7",
        "report_id": "opt04-20261013T172839Z-bf1844fdf81c94c82ca91aadbd9d0988c7367093c5cf70269c2d0e0ca7d44b2f",
        "zip_sha256": "4e9d2d193cf83d56fa308ba3b7b3ebddf2728d8090e804ed0c2178ab0fbf3db7"
    },
    "opt05-hull-20261012-d1c211c2": {
        "inventory_sha256": "a5b97b8f4ac0acb877d2bc9776ea0a991244c87c7cac2313d61513b5e7939bc3",
        "report_id": "opt05-hull-20261012-d6d3282081d5ea90d8a0c440ccc1ec774d40221e209a01d8207ebd06a551dbf5",
        "zip_sha256": "46f77edf5b5485b18a310eb45763d07dd73f338659ba49c6246f2ecb156411af"
    },
    "opt06-basis-reuse-20261014-ef70e8c5-r2": {
        "inventory_sha256": "a4f8e08919479c26ccb6cb03f5e50fe2e2972c2132b2b625aef5c22541149a11",
        "report_id": "opt06-basis-reuse-20261014-ef70e8c5-57c666a4f82b1f7c84d3507fbad32982a7928129c18f80348ea2c9ad457b3a8d",
        "zip_sha256": "165fe50a882e37334e30e3bd04f613b261fb801c540fe806304942ac146c361f"
    },
    "syn01-nominal-20261013-f7ba310d-48a679cfc0d4": {
        "inventory_sha256": "f977f289ac3942098140373435e7322dae5f43eb030239952c25a3ac29c47aa3",
        "report_id": "syn01-6e207b2ee1f300929f054e679c8cd5707f979c02b173292660520e403ebf2852",
        "zip_sha256": "84de33d3a3f6500a9e8aea07fe8297a71cdbd44b269f94aa4358bc332b28ec65"
    },
    "syn02-terminal-20261013-c234a1a0-35de886a7fb4": {
        "inventory_sha256": "0212ce9d7f65bf66de374895853c5119214e27c531e578a7751ddb3c1843e843",
        "report_id": "syn02-1b07970d73d90c79c4bba2c65d429ba05bd798751d885146cb21d8a876a067c3",
        "zip_sha256": "8acb23c42447455385e63aefccbf25a680384d39de5f50339838e98af7f10bf8"
    },
    "syn03-strategy-a-ts01-20261014-451d0f75": {
        "inventory_sha256": "bbf59746a528f35a8a5f9762f347162eabcc9fc209c9c48e1432131ebb8d3d80",
        "report_id": "syn03-strategy-a-ts01-77f669553a7c803b4f061401d5c1f7ffb22ef7f973368cd1b7c3494686fa8e2a",
        "zip_sha256": "9ff4f8abe7f89ecbbfd154995cf6778a09106eea482b239f6a06a0904a902739"
    },
    "syn03-strategy-a-ts02-20261014-272fb9a5": {
        "inventory_sha256": "7f8b6dcbd62ba45eb1efd8d77b24094618752fae0c7fb3c6186fbda7eb2735ed",
        "report_id": "syn03-strategy-a-ts02-cfe716d94d74b7da3caf38130d9dd88f1b17c50711c69cbfbb2531e60a1fe416",
        "zip_sha256": "ad676698868382c2a3b76288d47a18bb9289f0e4c2a003d9a8175e54a6e1ee96"
    },
    "syn04-strategy-b-ts01-20261014-2a5ab835": {
        "inventory_sha256": "53c4e475b3ea20eec83ef98acaa23a3e502e99b1885ff437e4c1f052867f187d",
        "report_id": "syn04-strategy-b-ts01-46513fc77b3e1e9e7795b887b1d2a12d7bfa5dbde4d6c74563b7f06c6a0aff24",
        "zip_sha256": "aaf13eac7b3a5beb9eb7bf90b793dbbd4b909f37b826a4a85316721bcbb8fc8e"
    },
    "syn04-strategy-b-ts02-20261014-e7f66a9e": {
        "inventory_sha256": "deeae8cbcffe2672f50245298733b73dbd2a3f46fc9ddb87be2787c945215d6a",
        "report_id": "syn04-strategy-b-ts02-3999b008c529fd57b5cfb6a78841a9963a7e9c4c9919e0c4edafe705b236f929",
        "zip_sha256": "b2d38a913d3addbee9ad1493f611bfb41abda921be7356dbb2a8b0c9859e6878"
    },
    "syn06-verifier-20261012-f0e32e2b": {
        "inventory_sha256": "3a04c3a133abdac9174e4b50ebefb5b1290c7639bb860f25632e5b65e7f8f6db",
        "report_id": "syn06-verifier-20261012-7c39d67859c50ffb697ab07b1d788134ef15ac05485207d1428dbf4a2d335cbc",
        "zip_sha256": "657284bdf33b1786ba6bf74a37e47c48092a146d878fe86482074a682bb6b14a"
    },
    "syn07-ts01-20261014-e22d9c2aeb05": {
        "inventory_sha256": "d756b967fd2af2ac3fd9b8d2c7c7a5b3a9dc8610a32914e1ba9094f76c9fe865",
        "report_id": "syn07-ts01-5f46eaee678c04b251c4bd9a78dcfb5ea45ce4f417c6bff7b8ba6225e04a6d66",
        "zip_sha256": "998c864e16f70274cee1a4dcd23a7dfc7a1681171ed7499346918650a9efd5fb"
    }
}


def preserve_historical_publication(bundle, publication, archive_builder):
    pin = _HISTORICAL_PUBLICATIONS.get(publication.source_report_id)
    if pin is None:
        return publication
    bundle = Path(bundle)
    inventory = {path.relative_to(bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(bundle.rglob("*")) if path.is_file()}
    if _digest(inventory) != pin["inventory_sha256"]:
        return publication
    historical = replace(publication, report_id=pin["report_id"])
    if hashlib.sha256(archive_builder(bundle, historical)).hexdigest() != pin["zip_sha256"]:
        return publication
    return historical


def preserve_publication(adapter):
    """Retain old routes only when current validation and exact output both agree."""
    from functools import wraps
    @wraps(adapter)
    def adapt_with_history(bundle, *args, **kwargs):
        publication = adapter(bundle, *args, **kwargs)
        return preserve_historical_publication(bundle, publication, adapter.__globals__["offline_zip"])
    return adapt_with_history

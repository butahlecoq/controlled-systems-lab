"""Explicit boundary adapters for validated non-LP report records."""
from dataclasses import dataclass
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


@dataclass(frozen=True)
class PublicationRecord:
    kind: str
    report_id: str
    payload_sha256: str
    source_commit: str
    measured_scope: str
    evidence_limits: str
    files: tuple[str, ...] = ()


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
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("code_commit", ""))) or record.get("fixture", {}).get("oracle") is None:
            raise ValueError("OPT-05 source/fixture evidence missing")
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
        return PublicationRecord("opt05-hull", rid, _digest(record), record.get("code_commit", ""), "21 verified measured trials across 5x5, 9x9, and 13x13 square lattices", "No comparator; " + limits)
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
        if len(trials) != 56 or len(groups) != 8 or set(groups.values()) != {7} or any(t.get("oracle_passed") != "true" for t in trials):
            raise ValueError("GEO-03 requires eight seven-trial oracle-passing groups")
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
        return PublicationRecord("geo03-hv", record["report_id"], record["payload_sha256"], source, "56 measured trials across four bounded 2D fixtures in both conversion directions", "; ".join(limits))
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
    result = adapt_payload(_json(bundle / "records.json"))
    if result.kind == "opt05-hull":
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
    if result.kind == "opt05-hull":
        allowed=OPT_TOP_FILES|OPT_NESTED_FILES
        if not set(listed)<=allowed or not set(OPT_TOP_FILES)-{"test_validate_report.py"}<=set(listed) or not OPT_NESTED_FILES<=set(listed):
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
    return PublicationRecord(result.kind, result.report_id, result.payload_sha256, result.source_commit, result.measured_scope, result.evidence_limits, tuple(sorted(listed)))


def render_page(bundle, publication):
    """Render the publication view from validated typed data, never producer HTML."""
    bundle = Path(bundle)
    links = [f'<a href="{escape(name, quote=True)}">{escape(name)}</a>' for name in publication.files if name in {"records.json", "trials.csv", "summary.csv", "latency.svg"}]
    record=json.loads((bundle/"records.json").read_text(encoding="utf-8"))
    if publication.kind=="geo03-hv": record=record["payload"]
    if publication.kind=="opt05-hull":
        rows=''.join('<tr><td>'+escape(str(row["case_id"]))+'</td><td>'+str(row["points"])+'</td><td>'+str(row["attempts"])+'</td><td>'+str(row["failures"])+'</td><td>'+f'{row["median_ns"]:,}'+'</td><td>'+f'{row["min_ns"]:,}'+'</td><td>'+f'{row["max_ns"]:,}'+'</td><td>'+str(row["median_lp_calls"])+'</td></tr>' for row in record["summary"])
        table='<table><thead><tr><th>Case</th><th>Points</th><th>Attempts</th><th>Failures</th><th>Median ns</th><th>Min ns</th><th>Max ns</th><th>Median LP calls</th></tr></thead><tbody>'+rows+'</tbody></table>'
    else:
        rows=''.join('<tr><td>'+escape(row["fixture"])+'</td><td>'+escape(row["direction"])+'</td><td>'+str(row["trials"])+'</td><td>'+str(row["failures"])+'</td>'+''.join('<td>'+f'{row[metric][key]:,}'+'</td>' for metric in ("run_ns","total_ns") for key in ("median","min","max"))+'</tr>' for row in record["summary"])
        table='<table><thead><tr><th>Fixture</th><th>Direction</th><th>Trials</th><th>Failures</th>'+''.join('<th>'+metric.replace("_ns", "")+' '+key+' ns</th>' for metric in ("run_ns","total_ns") for key in ("median","min","max"))+'</tr></thead><tbody>'+rows+'</tbody></table>'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>' + escape(publication.report_id) +
            '</title></head><body><h1>' + escape(publication.kind) + ' measurement report</h1><p><code>' +
            escape(publication.report_id) + '</code></p><h2>Measured scope</h2><p>' + escape(publication.measured_scope) +
            '</p><h2>Saved measurements</h2>'+table+'<h2>Evidence limits</h2><p>' + escape(publication.evidence_limits) + '</p><p>Source commit <code>' +
            escape(publication.source_commit) + '</code></p><p><a href="latency.svg">Checked latency SVG</a></p><ul><li>' + '</li><li>'.join(links) + '</li></ul></body></html>')


def offline_zip(bundle, publication):
    bundle=Path(bundle)
    page=render_page(bundle,publication).encode("utf-8")
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        entries=[("index.html",page)]+[(publication.report_id+"/"+name,(bundle/name).read_bytes()) for name in publication.files if name!="index.html"]
        for name,content in entries:
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,content)
    return buffer.getvalue()

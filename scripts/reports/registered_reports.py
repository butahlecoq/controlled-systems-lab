"""Explicit boundary adapters for validated non-LP report records."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import zipfile


OPT_TOP_FILES = {"README.md", "analyze_profile.py", "collect.py", "index.html", "latency.svg", "records.json", "render_saved.py", "summary.csv", "test_validate_report.py", "trials.csv", "validate_report.py"}
GEO_FILES = {"README.md", "build-provenance.txt", "environment.json", "index.html", "latency.svg", "measurement-command.txt", "process-stderr.txt", "profile.txt", "raw-driver-output.csv", "raw-events.jsonl", "records.json", "scenarios.json", "summary.csv", "trials.csv"}


@dataclass(frozen=True)
class PublicationRecord:
    kind: str
    report_id: str
    payload_sha256: str
    source_commit: str
    measured_scope: str
    evidence_limits: str


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def adapt_payload(record):
    schema = record.get("schema")
    rid = record.get("report_id")
    if schema == "csl.hull-benchmark-records/1":
        if not re.fullmatch(r"opt05-hull-\d{8}-[0-9a-f]{8}", str(rid)):
            raise ValueError("unsafe OPT-05 report ID")
        trials = record.get("trials")
        measured = [t for t in trials if not t.get("warmup")] if isinstance(trials, list) else []
        if len(measured) != 21 or any(t.get("status") != "complete" or t.get("verified") is not True for t in measured):
            raise ValueError("OPT-05 requires 21 verified measured trials")
        from collections import Counter
        if Counter(t["case_id"] for t in measured) != {"grid-25": 7, "grid-81": 7, "grid-169": 7}:
            raise ValueError("OPT-05 case trial groups differ")
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("code_commit", ""))) or record.get("fixture", {}).get("oracle") is None:
            raise ValueError("OPT-05 source/fixture evidence missing")
        summary = record.get("summary")
        limits = record.get("fixture", {}).get("assurance", "")
        if not isinstance(summary, list) or not isinstance(limits, str) or "not exact arithmetic" not in limits:
            raise ValueError("OPT-05 assurance boundary missing")
        return PublicationRecord("opt05-hull", rid, _digest(record), record.get("code_commit", ""), "21 verified measured trials across 5x5, 9x9, and 13x13 square lattices", "No comparator; " + limits)
    if schema == "csl.geo03-hv-report/1":
        payload = record.get("payload")
        if not isinstance(payload, dict) or _digest(payload) != record.get("payload_sha256"):
            raise ValueError("GEO-03 payload digest mismatch")
        if payload.get("schema") != schema or payload.get("measurement", {}).get("emitted_trials") != 56:
            raise ValueError("GEO-03 measured trial scope mismatch")
        if payload["measurement"].get("failures") != 0 or any(t.get("failures") != 0 for t in payload.get("summary", [])):
            raise ValueError("GEO-03 contains failed trials")
        from collections import Counter
        groups = Counter((t.get("fixture"), t.get("direction")) for t in payload.get("trials", []))
        if len(groups) != 8 or set(groups.values()) != {7} or any(t.get("oracle_passed") != "true" for t in payload["trials"]):
            raise ValueError("GEO-03 requires eight seven-trial oracle-passing groups")
        limits = payload.get("scope_limitations")
        if not isinstance(limits, list) or not limits:
            raise ValueError("GEO-03 scope limitations required")
        return PublicationRecord("geo03-hv", record["report_id"], record["payload_sha256"], payload.get("report_source_commit", ""), "56 measured trials across four bounded 2D fixtures in both conversion directions", "; ".join(limits))
    raise ValueError("unregistered report schema")


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
        safe = all((name in OPT_TOP_FILES or re.fullmatch(r"evidence/accepted-00[12]/[A-Za-z0-9_.-]+", name) or re.fullmatch(r"harness/[A-Za-z0-9_.-]+", name) or re.fullmatch(r"profile/(?:[A-Za-z0-9_.-]+|final/[A-Za-z0-9_.-]+)", name)) for name in listed)
        if not safe or not OPT_TOP_FILES.issuperset(set(listed) & OPT_TOP_FILES) or not set(OPT_TOP_FILES) - {"test_validate_report.py"} <= set(listed):
            raise ValueError("OPT-05 registered inventory pattern mismatch")
    elif set(listed) != GEO_FILES:
        raise ValueError("registered bundle inventory mismatch")
    for name, expected in listed.items():
        path = bundle / name
        if ".." in Path(name).parts or not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("unsafe or tampered registered bundle file: " + name)
    return result

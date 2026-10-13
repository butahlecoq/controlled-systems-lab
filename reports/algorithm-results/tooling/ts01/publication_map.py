"""Canonical identity mapping for the standalone T-S01 report."""
from __future__ import annotations
import hashlib
import json

NATIVE_SCHEMA = "csl.syn07-ts01-analytic-report/2"
KIND = "syn07-ts01-analytic"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def public_report_id(source_report_id, source_hashes, publisher_source):
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": source_report_id,
                "source_files": {name: source_hashes[name] for name in sorted(source_hashes)},
                "publisher_sha256": hashlib.sha256(publisher_source.replace(b"\r\n", b"\n")).hexdigest()}
    return "syn07-ts01-" + digest(identity)


def project(record):
    if record.get("schema") != NATIVE_SCHEMA or not record.get("report_id"):
        raise ValueError("unsupported T-S01 native record")
    has_measurements = isinstance(record.get("measurement"), dict)
    conclusion = record.get("measurement", {}).get("performance_conclusion") if has_measurements else None
    scope = ("strict-profile analytic relation; exploratory timings available; performance conclusion inconclusive"
             if has_measurements and conclusion == "inconclusive" else
             "strict-profile analytic relation; performance unavailable")
    return {"schema": "csl.algorithm-report-publication-map/1", "source_report_id": record["report_id"],
            "native_payload_schema": NATIVE_SCHEMA, "native_payload_sha256": digest(record),
            "publication_contract": {"catalogue_schema": "csl.algorithm-report-catalog/3",
                "envelope_schema": "csl.algorithm-report-envelope/1", "report_kind": KIND,
                "payload_schema": NATIVE_SCHEMA, "source_commit": "payload.source_commit",
                "measured_scope": scope,
                "evidence_limits": "payload.evidence_limits joined in stored order"},
            "public_id": {"prefix": "syn07-ts01-", "source_files": "SHA-256 of each validated native file by sorted relative path, including manifest.json",
                "publisher_sha256": "SHA-256 of scripts/reports/ts01_registered_reports.py bytes"}}

"""Canonical schema-3 mapping and immutable identity for SYN-01 reports."""
from __future__ import annotations
import hashlib
import json

NATIVE_SCHEMA = "csl.syn01-nominal-forward-report/2"
MAP_SCHEMA = "csl.algorithm-report-publication-map/1"
KIND = "syn01-nominal-forward"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def public_report_id(source_report_id, source_hashes, publisher_source):
    identity = {"schema": "csl.registered-publication-identity/1",
                "source_report_id": source_report_id,
                "source_files": {name: source_hashes[name] for name in sorted(source_hashes)},
                "publisher_sha256": hashlib.sha256(publisher_source.replace(b"\r\n", b"\n")).hexdigest()}
    return "syn01-" + digest(identity)


def project(record):
    if record.get("schema") != NATIVE_SCHEMA or not record.get("report_id"):
        raise ValueError("unsupported SYN-01 native record")
    native_hash = digest(record)
    return {
        "schema": MAP_SCHEMA,
        "source_report_id": record["report_id"],
        "native_payload_schema": NATIVE_SCHEMA,
        "native_payload_sha256": native_hash,
        "publication_contract": {
            "catalogue_schema": "csl.algorithm-report-catalog/3",
            "envelope_schema": "csl.algorithm-report-envelope/1",
            "report_kind": KIND,
            "payload_schema": NATIVE_SCHEMA,
            "payload_sha256": "canonical digest of complete native records.json object",
            "native_payload_sha256": "same canonical digest as payload_sha256",
            "source_commit": "payload.source_commit",
            "measured_scope": "payload.measurement.scope",
            "evidence_limits": "payload.evidence_limits joined in stored order",
        },
        "manifest_inventory": "The exact registered staging inventory is the validated native inventory plus generated index.html and report-envelope.json; publication-manifest.json excludes itself.",
        "public_id": {
            "prefix": "syn01-",
            "identity_schema": "csl.registered-publication-identity/1",
            "source_files": "SHA-256 of every validated native file by sorted relative path, including manifest.json",
            "publisher_sha256": "LF-normalized scripts/reports/syn01_registered_reports.py bytes",
            "canonicalization": "UTF-8 JSON, ensure_ascii=false, sorted keys, compact separators",
        },
        "adapter": "scripts/reports/syn01_registered_reports.py",
    }

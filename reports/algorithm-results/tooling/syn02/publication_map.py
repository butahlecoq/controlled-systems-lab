"""Explicit projection from the SYN-02 native record to the shared report contract."""
from __future__ import annotations
import hashlib
import json

NATIVE_SCHEMA = "csl.syn02-terminal-report/1"
MAP_SCHEMA = "csl.algorithm-report-publication-map/1"
CATALOG_SCHEMA = "csl.algorithm-report-catalog/3"
ENVELOPE_SCHEMA = "csl.algorithm-report-envelope/1"
STAGED_SOURCE_FILES = [
    "README.md", "build-log.txt", "build-provenance.json", "collect.py",
    "configure-log.txt", "environment.json", "etw-profile-attempt.txt",
    "latency.svg", "manifest.json", "measurement-command.txt",
    "profile-evidence.json", "profile-note.txt", "profile-raw.jsonl",
    "publication-map.json", "raw-events.jsonl", "records.json",
    "render_saved.py", "terminal_driver.cpp", "test_report.py", "trials.csv",
]
STAGED_FILES = sorted([*STAGED_SOURCE_FILES, "index.html", "report-envelope.json"])


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def public_report_id(source_report_id, source_file_hashes, publisher_source):
    """Derive the registered immutable ID from validated inputs, matching site adapters."""
    identity = {
        "schema": "csl.registered-publication-identity/1",
        "source_report_id": source_report_id,
        "source_files": {name: source_file_hashes[name] for name in sorted(source_file_hashes)},
        "publisher_sha256": hashlib.sha256(publisher_source.replace(b"\r\n", b"\n")).hexdigest(),
    }
    return "syn02-" + digest(identity)


def project(record):
    if record.get("schema") != NATIVE_SCHEMA:
        raise ValueError("unsupported SYN-02 native report schema")
    if not record.get("report_id") or not record.get("source_commit"):
        raise ValueError("native report identity is incomplete")
    payload = {key: value for key, value in record.items() if key != "publication_mapping"}
    return {
        "schema": MAP_SCHEMA,
        "source_report_id": record["report_id"],
        "native_payload_schema": NATIVE_SCHEMA,
        "native_payload_sha256": digest(payload),
        "publication_contract": {
            "catalogue_schema": CATALOG_SCHEMA,
            "envelope_schema": ENVELOPE_SCHEMA,
            "report_kind": "syn02-terminal-minimizers",
            "payload_schema": NATIVE_SCHEMA,
            "payload": "complete native records.json object",
            "report_id": "publisher-derived immutable public ID",
            "source_report_id": "native records.json report_id",
            "payload_sha256": "canonical payload digest",
            "source_commit": "payload.source_commit",
            "measured_scope": "payload.measurement.scope",
            "evidence_limits": "payload.evidence_limits joined in stored order",
        },
        "envelope_fields": {
            "schema": ENVELOPE_SCHEMA,
            "report_id": "publisher-derived immutable public ID",
            "report_kind": "syn02-terminal-minimizers",
            "payload_schema": NATIVE_SCHEMA,
            "payload_sha256": "canonical payload digest",
            "source_commit": "payload.source_commit",
            "measured_scope": "payload.measurement.scope",
            "evidence_limits": "payload.evidence_limits joined in stored order",
            "payload": "complete native records.json object",
            "source_report_id": "native records.json report_id",
        },
        "manifest_fields": {
            "schema": "csl.algorithm-report-publication-manifest/1",
            "report_id": "same publisher-derived public ID as envelope",
            "report_kind": "syn02-terminal-minimizers",
            "files": {
                "meaning": "exact staged artifact inventory: relative path to SHA-256 of staged bytes",
                "entries": STAGED_FILES,
                "excludes": ["publication-manifest.json"],
                "includes": ["generated index.html", "latency.svg", "raw evidence", "report-envelope.json"],
            },
        },
        "immutable_public_id": {
            "identity_schema": "csl.registered-publication-identity/1",
            "identity_fields": {
                "schema": "csl.registered-publication-identity/1",
                "source_report_id": "native records.json report_id",
                "source_files": "SHA-256 of every validated native bundle file, using sorted relative paths; inventory is manifest.json.files plus manifest.json itself",
                "publisher_sha256": "SHA-256 of scripts/reports/syn02_registered_reports.py UTF-8 bytes after CRLF-to-LF normalization",
            },
            "canonicalization": "UTF-8 JSON, ensure_ascii=false, sort_keys=true, separators=(',', ':')",
            "public_report_id": "syn02- plus lowercase SHA-256 hex of the canonical identity record",
            "source_zip": "If the adapter validates a separate native source ZIP, include its SHA-256 in source_files under its validated relative name.",
            "offline_zip": "Generated from the exact staged file mapping; its SHA-256 is stored in the schema-3 catalogue zip_sha256, avoiding a digest cycle.",
        },
        "publisher_registration": {
            "adapter_module": "scripts/reports/syn02_registered_reports.py",
            "site_import_point": "scripts/reports/site.py adapter imports",
            "site_kind_allowlist_point": "site.stage schema-3 registered report_kind dispatch tuple",
            "site_dispatch_point": "site.stage publisher selection expression",
            "required_adapter_operations": ["adapt", "render_page", "publication_artifacts", "offline_zip"],
            "required_validation": ["safe source ID/path", "native schema and source identity", "trial-to-summary consistency including failures", "raw/evidence file inventory and SHA256 manifest", "SVG safety", "envelope field projection", "deterministic offline ZIP"],
            "required_staging": ["schema-3 catalogue projection", "site.stage validation", "main-only Pages deployment", "verify immutable live page and ZIP URLs"],
            "publishable_now": False,
            "blocking_reason": "No SYN-02 publisher adapter is currently registered in site.py.",
        },
    }


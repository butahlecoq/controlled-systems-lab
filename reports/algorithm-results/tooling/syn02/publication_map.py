"""Explicit projection from the SYN-02 native record to the shared report contract."""
from __future__ import annotations
import hashlib
import json

NATIVE_SCHEMA = "csl.syn02-terminal-report/1"
MAP_SCHEMA = "csl.algorithm-report-publication-map/1"
CATALOG_SCHEMA = "csl.algorithm-report-catalog/3"
ENVELOPE_SCHEMA = "csl.algorithm-report-envelope/1"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


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
            "files": "exact generated source inventory mapped to sha256 per file",
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


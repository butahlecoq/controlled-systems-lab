"""Static publication adapter for the immutable paired T-S01 report bundle."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import registered_reports as common

ROOT = Path(__file__).resolve().parents[2]
REPORT_SPEC = importlib.util.spec_from_file_location(
    "csl_syn_ts01_paired_report_contract",
    ROOT / "scripts/reports/syn_ts01_paired/report.py",
)
report = importlib.util.module_from_spec(REPORT_SPEC)
sys.modules[REPORT_SPEC.name] = report
REPORT_SPEC.loader.exec_module(report)

KIND = "syn-ts01-paired-comparison"
FILES = {
    "README.md", "build-provenance.json", "commands.json", "environment.json",
    "index.html", "limiter-profile.json", "manifest.json", "measurement-events.jsonl",
    "performance.svg", "process-run.json", "process-stderr.bin", "process-stdout.bin",
    "records.json", "scenario.json", "trials.csv", "validation.json",
}


def _json(path):
    return report.parse_json(Path(path).read_text(encoding="utf-8"))


def _pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _validate_bundle(bundle, record):
    report.validate_bundle(bundle)


@common.preserve_publication
def adapt(bundle):
    bundle = Path(bundle)
    record = _json(bundle / "records.json")
    errors = report.validate(record)
    if errors:
        raise ValueError("invalid paired T-S01 record: " + ", ".join(errors))
    _validate_bundle(bundle, record)
    payload_sha256 = common._digest(record)
    scope = "One exact T-S01 paired experiment; one excluded warmup and seven alternating measured pairs; performance conclusion inconclusive"
    evidence_limits = "; ".join(record["evidence_limits"])
    identity = {
        "schema": "csl.registered-publication-identity/1",
        "source_report_id": record["report_id"],
        "source_files": {name: _sha256((bundle / name).read_bytes()) for name in sorted(FILES)},
        "publisher_sha256": _sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
    }
    public_id = "syn-ts01-paired-" + common._digest(identity)
    return common.PublicationRecord(
        KIND,
        public_id,
        payload_sha256,
        record["source"]["harness_commit"],
        scope,
        evidence_limits,
        tuple(sorted(FILES)),
        record["schema"],
        payload_sha256,
        record["report_id"],
    )


def render_page(bundle, publication):
    # Preserve the exact versioned report HTML and all relative download URLs.
    return (Path(bundle) / "index.html").read_text(encoding="utf-8")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files}
    record = _json(bundle / "records.json")
    files["report-envelope.json"] = _pretty({
        "schema": "csl.algorithm-report-envelope/1",
        "report_id": publication.report_id,
        "report_kind": publication.kind,
        "payload_schema": publication.payload_schema,
        "payload_sha256": publication.payload_sha256,
        "native_payload_sha256": publication.native_payload_sha256,
        "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope,
        "evidence_limits": publication.evidence_limits,
        "source_report_id": publication.source_report_id,
        "payload": record,
    })
    files["publication-manifest.json"] = _pretty({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": publication.report_id,
        "report_kind": publication.kind,
        "files": {name: _sha256(files[name]) for name in sorted(files)},
    })
    return files


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)

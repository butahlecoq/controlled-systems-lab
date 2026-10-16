"""Publish the reviewed B08 exact-reference record without rerunning its checker."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

import b08_exact_report as source
import registered_reports as common


KIND = "b08-displayed-exact"
SOURCE_FILES = {"index.html", "records.json", "raw-trials.jsonl", "trials.csv", "manifest.json"}
LIMITS = ("Printed rounded L04 linear model only; historical 67.12, unrounded arrays, nonlinear "
          "plant, and complete optimal family remain unresolved; fresh CPython process time "
          "includes startup and output capture; no comparator or speedup; no source-mapped limiter")


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("B08 source bundle must be a directory")
    record = source.validate_record(source.strict_json(bundle / "records.json"))
    source_id = record["report_id"]
    if re.fullmatch(r"b08-exact-[0-9a-f]{16}", source_id) is None or bundle.name != source_id:
        raise ValueError("unsafe B08 source report ID")
    if not record["publishable"]:
        raise ValueError("B08 source record is not publishable")
    manifest = source.strict_json(bundle / "manifest.json")
    if (set(manifest) != {"schema", "report_id", "files"} or
            manifest.get("schema") != "csl.b08-report-files/1" or
            manifest.get("report_id") != source_id):
        raise ValueError("B08 source manifest identity differs")
    common.validate_source_inventory(bundle, manifest["files"], SOURCE_FILES - {"manifest.json"}, label="B08")
    if source.check(bundle) != source_id:
        raise ValueError("B08 saved-data checker identity differs")
    source_zip = bundle.parent / (source_id + ".zip")
    if source_zip.is_symlink() or not source_zip.is_file() or source_zip.read_bytes() != source.source_zip_bytes(bundle):
        raise ValueError("B08 source ZIP differs from saved bundle")
    publisher_bytes = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": source_id,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                                 for name in sorted(SOURCE_FILES)},
                "source_zip_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher_bytes).hexdigest()}
    public_id = "b08-displayed-exact-" + common._digest(identity)
    scope = (f"Printed B08 linear model, 625 plans x 256 corners; {record['repetitions']} verified "
             "fresh-process measured trials after one excluded warmup; performance interpretation inconclusive")
    return common.PublicationRecord(KIND, public_id, common._digest(record),
                                    record["source"]["source_commit"], scope, LIMITS,
                                    tuple(sorted(SOURCE_FILES)), source.SCHEMA,
                                    record["payload_sha256"], source_id)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    if page.count("</body>") != 1:
        raise ValueError("B08 source page insertion point differs")
    links = (f'<p>Versioned publication <code>{publication.report_id}</code>; '
             f'native report <code>{publication.source_report_id}</code>. '
             '<a href="report-envelope.json">Report envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</body>", links + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    bundle = Path(bundle)
    record = source.strict_json(bundle / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "source_report_id": publication.source_report_id, "payload": record}
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def catalogue_entry(bundle: Path) -> dict:
    publication = adapt(bundle)
    archive = offline_zip(bundle, publication)
    return {"report_id": publication.report_id, "report_kind": publication.kind,
            "source_report_id": publication.source_report_id,
            "payload_schema": publication.payload_schema,
            "payload_sha256": publication.payload_sha256,
            "native_payload_sha256": publication.native_payload_sha256,
            "source_commit": publication.source_commit,
            "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "zip_sha256": hashlib.sha256(archive).hexdigest()}

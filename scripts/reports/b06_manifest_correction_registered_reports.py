"""Publish a versioned B06 manifest correction without rewriting its measured report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import registered_reports as common
import issue6.scenario_contract as scenario_contract

KIND = "issue6-b06-manifest-correction"
SOURCE_PATTERN = r"b06-manifest-correction-v1"
SOURCE_ID = "b06-owner-confirmed-7df01ba3af5e4c46"


def validate_canonical_fixture(bundle: Path, canonical_fixture: Path) -> None:
    corrected_path = Path(bundle) / "corrected-scenario.json"
    corrected_bytes = corrected_path.read_bytes()
    canonical_bytes = Path(canonical_fixture).read_bytes()
    scenario_contract.validate(json.loads(corrected_bytes))
    scenario_contract.validate(json.loads(canonical_bytes))
    if corrected_bytes != canonical_bytes:
        raise ValueError("B06 correction scenario differs from the canonical executable fixture")


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir() or bundle.name != SOURCE_PATTERN:
        raise ValueError("B06 correction source bundle identity differs")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.issue6-b06-correction-files/1" or not isinstance(manifest.get("files"), dict):
        raise ValueError("B06 correction source manifest schema differs")
    files = tuple(sorted(manifest["files"]))
    common.validate_source_inventory(bundle, manifest["files"], set(files), label="B06 correction")
    correction = json.loads((bundle / "manifest-correction.json").read_text(encoding="utf-8"))
    scenario = json.loads((bundle / "corrected-scenario.json").read_text(encoding="utf-8"))
    scenario_contract.validate(scenario)
    if correction.get("schema") != "csl.issue6-b06-manifest-correction/1" or correction.get("correction_id") != SOURCE_PATTERN:
        raise ValueError("B06 correction record identity/schema differs")
    if correction.get("original_source_report_id") != SOURCE_ID or correction.get("corrected_fixture_sha256") != hashlib.sha256((bundle / "corrected-scenario.json").read_bytes()).hexdigest():
        raise ValueError("B06 correction record source or scenario hash differs")
    payload_sha = common._digest(correction)
    publisher = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    identity = {"schema": "csl.issue6-b06-correction-publication/1",
                "source_report_id": bundle.name, "source_files": manifest["files"],
                "publisher_sha256": hashlib.sha256(publisher).hexdigest(),
                "payload_sha256": payload_sha}
    report_id = KIND + "-" + common._digest(identity)
    return common.PublicationRecord(KIND, report_id, payload_sha,
        correction["measured_source_commit"],
        "Versioned manifest correction and source-level audit of the saved B06 five-stage model",
        "No solver rerun. Existing results retain binary64 numerical assurance and are not newly recertified; this is not a historical reproduction.",
        files, correction["schema"], hashlib.sha256((bundle / "manifest-correction.json").read_bytes()).hexdigest(), bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    footer = (f'<p>Versioned report <code>{publication.report_id}</code>; source companion '
              f'<code>{publication.source_report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</body>", footer + "</body>") if "</body>" in page else page + footer


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    correction = json.loads((Path(bundle) / "manifest-correction.json").read_text(encoding="utf-8"))
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "source_report_id": publication.source_report_id, "payload": correction}
    return common.assemble_publication(bundle, publication,
        page=render_page(bundle, publication), envelope=envelope, source_files=publication.files)


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

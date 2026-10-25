"""Publish the saved B09 fuel reference without rerunning the solver."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import registered_reports as common
import report_data


KIND = "issue6-b09-reference"
SOURCE_PATTERN = r"b09-a08-source-reference-[0-9a-f]{8}"
FILES = {"README.md", "independent-oracle-verification.json", "index.html",
         "lambda0-result.json", "lambda1-result.json", "projections-lambda0.svg",
         "projections-lambda1.svg", "raw-runs.jsonl", "records.json", "results.jsonl",
         "run-provenance.json", "scenario.json"}
LIMITS = ("Source-revision reference, not a historical reproduction; finite action catalog only; "
          "binary64 numerical assurance; replay trajectories are examples, not a global causal "
          "optimality claim; single-adapter timings without a source-mapped limiter profile.")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("B09 source bundle must be a real directory")
    record = _json(bundle / "records.json")
    if (record.get("schema") != "csl.issue6-b09-evidence/1" or
            record.get("report_id") != bundle.name or
            re.fullmatch(SOURCE_PATTERN, bundle.name) is None):
        raise ValueError("B09 saved report identity differs")
    manifest = _json(bundle / "manifest.json")
    if (manifest.get("schema") != "csl.issue6-b09-files/1" or
            set(manifest) != {"schema", "files"} or
            manifest.get("files") != sorted(FILES)):
        raise ValueError("B09 source manifest schema differs")
    expected = FILES | {"manifest.json", "SHA256SUMS"}
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    if actual != expected or any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("B09 source inventory differs")
    checksums = {}
    for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksums or Path(name).name != name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("B09 checksum inventory is malformed")
        checksums[name] = digest
    if set(checksums) != expected - {"SHA256SUMS"}:
        raise ValueError("B09 checksum inventory differs")
    for name, digest in checksums.items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
            raise ValueError("B09 saved file checksum differs: " + name)
    for value in (0, 1):
        result = _json(bundle / f"lambda{value}-result.json")
        if result.get("lambda") != float(value) or result.get("status") != "numerical_optimal":
            raise ValueError("B09 objective result is incomplete")
        report_data.validate_svg((bundle / f"projections-lambda{value}.svg").read_bytes())
    if len((bundle / "index.html").read_text(encoding="utf-8").split("<figure>")) < 3:
        raise ValueError("B09 report must include both projection figures")
    publisher = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    identity = {"schema": "csl.issue6-b09-publication-identity/1",
                "source_report_id": bundle.name, "source_files": checksums,
                "source_manifest_sha256": hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher).hexdigest()}
    report_id = KIND + "-" + common._digest(identity)
    scope = ("Four-stage A08 finite-action minimax case: 6,561 plans per objective; "
             "seven alternating measured Release calls per objective, each after one process warmup")
    record_bytes = (bundle / "records.json").read_bytes()
    return common.PublicationRecord(KIND, report_id, common._digest(record), record["source_commit"],
                                    scope, LIMITS, tuple(sorted(expected)),
                                    record["schema"], hashlib.sha256(record_bytes).hexdigest(), bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    if page.count("</body>") != 1:
        raise ValueError("B09 source page insertion point differs")
    footer = (f'<p>Versioned publication <code>{publication.report_id}</code>; '
              f'native report <code>{publication.source_report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</body>", footer + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    record = _json(Path(bundle) / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
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
            "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "zip_sha256": hashlib.sha256(archive).hexdigest()}

"""Publish the saved B06 reference capture without rerunning its solver."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import registered_reports as common


KIND = "issue6-b06-reference"
SOURCE_PATTERN = r"b06-owner-confirmed-7df01ba3af5e4c46"
LIMITS = ("Owner-confirmed disturbance box is not printed in L09; this is a distinct reference, "
          "not a historical reproduction. Exact integer enumeration applies only to this declared "
          "rational finite-action case; solver assurance is binary64. Single-adapter timings only, "
          "without a limiter profile or speedup claim. The projected vertices are numerical.")


def _record(bundle: Path) -> dict:
    return json.loads((bundle / "records.json").read_text(encoding="utf-8"))


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("B06 source bundle must be a real directory")
    record = _record(bundle)
    if (record.get("schema") != "csl.issue6-b06-evidence/1" or
            record.get("report_id") != SOURCE_PATTERN or bundle.name != SOURCE_PATTERN):
        raise ValueError("B06 saved report identity differs")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.issue6-b06-files/1":
        raise ValueError("B06 source manifest schema differs")
    files = tuple(sorted(set(manifest["files"]) | {"manifest.json"}))
    common.validate_source_inventory(bundle, manifest["files"], set(files) - {"manifest.json"}, label="B06")
    checker = Path(__file__).parent / "issue6" / "check_capture.py"
    result = subprocess.run([sys.executable, str(checker), str(bundle.resolve())],
                            cwd=Path.cwd(), check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError("B06 saved-data checker failed: " + result.stderr.strip())
    source_zip = bundle.parent / (bundle.name + ".zip")
    if source_zip.is_symlink() or not source_zip.is_file():
        raise ValueError("B06 source ZIP is missing")
    publisher = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    identity = {"schema": "csl.issue6-b06-publication-identity/1",
                "source_report_id": bundle.name,
                "source_files": manifest["files"],
                "source_manifest_sha256": hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(),
                "source_zip_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher).hexdigest()}
    public_id = KIND + "-" + common._digest(identity)
    scope = ("One five-stage finite-action minimax case: 3,125 plans x 1,024 disturbance-corner "
             "histories; one excluded warmup and seven measured Release calls")
    payload = common._digest(record)
    return common.PublicationRecord(KIND, public_id, payload, record["source_commit"], scope, LIMITS,
                                    files, record["schema"],
                                    hashlib.sha256((bundle / "records.json").read_bytes()).hexdigest(),
                                    bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    if page.count("</html>") != 1:
        raise ValueError("B06 source page insertion point differs")
    page = page.replace("../" + publication.source_report_id + ".zip",
                        "../" + publication.report_id + ".zip")
    footer = (f'<p>Versioned publication <code>{publication.report_id}</code>; '
              f'native report <code>{publication.source_report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</html>", footer + "</html>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    bundle = Path(bundle)
    record = _record(bundle)
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

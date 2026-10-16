"""Schema-3 publication adapter for the immutable issue #3 saved report."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from issue3 import render_saved as native
import registered_reports as common

KIND = "issue3-finite-catalogue"
SCOPE = ("Eight checked finite-action minimax fixtures; seven Release batch observations "
         "per fixture, with fixture-specific call counts")
LIMITS = ("Exploratory single-adapter batch timings with possible host contention; no "
          "comparator, speedup, source-mapped limiter, or per-call latency claim; "
          "displayed rounded B08 open-loop linear model only, binary64 numerical assurance")


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    record = native.render(bundle, check=True)
    if record["schema"] != native.SCHEMA or record["report_id"] != native.REPORT_ID:
        raise ValueError("issue #3 native report identity differs")
    manifest = native.strict_json((bundle / "manifest.json").read_bytes())
    identity = {"schema": "csl.issue3-publication-identity/1",
                "source_report_id": native.REPORT_ID,
                "source_files": manifest["files"],
                "source_manifest_sha256": native.sha((bundle / "manifest.json").read_bytes())}
    public_id = "issue3-finite-catalogue-" + common._digest(identity)
    payload_hash = common._digest(record)
    return common.PublicationRecord(KIND, public_id, payload_hash, native.SOURCE,
                                    SCOPE, LIMITS,
                                    tuple(sorted(native.SOURCE_FILES | {"manifest.json"})),
                                    native.SCHEMA, payload_hash, native.REPORT_ID)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    if page.count("</body>") != 1:
        raise ValueError("issue #3 page insertion point differs")
    footer = (f'<p>Versioned publication <code>{publication.report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</body>", footer + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    record = native.strict_json((Path(bundle) / "records.json").read_bytes())
    envelope = {"schema": "csl.algorithm-report-envelope/1",
                "report_id": publication.report_id, "report_kind": publication.kind,
                "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "source_report_id": publication.source_report_id,
                "payload": record}
    return common.assemble_publication(bundle, publication,
                                       page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id,
                                  publication_artifacts(bundle, publication))


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

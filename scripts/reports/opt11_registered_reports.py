"""Schema-3 publication adapter for a reviewed OPT-11 native report bundle."""
from __future__ import annotations

import hashlib
import html
import importlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType

import registered_reports as common

_PACKAGE = "csl_opt11_report_tooling"
_tooling = Path(__file__).resolve().parents[2] / "reports/algorithm-results/tooling/opt11"
if _PACKAGE not in sys.modules:
    package = ModuleType(_PACKAGE)
    package.__path__ = [str(_tooling)]
    sys.modules[_PACKAGE] = package
source = importlib.import_module(_PACKAGE + ".build_bundle")

KIND = "opt11-recursive-hull"
FILES = source.FILES
STAGE_FILES = FILES | {"manifest.json"}
LIMITS = (
    "Fixed finite binary64 point clouds; exact dyadic certificates cover the represented inputs. "
    "Seven alternating paired batches per fixture; backend and host specific observations only; "
    "no universal speedup, application-scale, or scalability claim."
)


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    record = source.check(bundle)
    if record.get("purpose") != "measurement":
        raise ValueError("test-only OPT-11 artifact cannot be published")
    if re.fullmatch(r"opt11-[0-9a-f]{16}", bundle.name) is None:
        raise ValueError("unsafe OPT-11 source identity")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    common.validate_source_inventory(bundle, manifest["files"], FILES, label="OPT-11")
    source_zip = bundle.parent / (bundle.name + ".source.zip")
    identity = {
        "schema": "csl.registered-publication-identity/1",
        "source_report_id": bundle.name,
        "source_files": {
            name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
            for name in sorted(STAGE_FILES)
        },
        "source_zip_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
        "publisher_sha256": hashlib.sha256(
            Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        ).hexdigest(),
    }
    public_id = bundle.name.rsplit("-", 1)[0] + "-" + common._digest(identity)
    measured = [trial for trial in record["trials"] if not trial["warmup"]]
    complete_pairs = sum(trial["status"] == "complete" for trial in measured)
    fixture_count = len(source.FIXTURES)
    scope = (f"{len(measured)} alternating baseline/recursive pairs across {fixture_count} fixed clouds; "
             f"{complete_pairs} pairs complete; performance interpretation inconclusive")
    return common.PublicationRecord(
        KIND, public_id, common._digest(record), record["source_commit"], scope, LIMITS,
        tuple(sorted(STAGE_FILES)), source.SCHEMA, record["payload_sha256"], bundle.name,
    )


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    record = source.check(Path(bundle))
    original = source.page(record)
    if original.count("</body>") != 1:
        raise ValueError("OPT-11 source HTML structure is malformed")
    links = (f'<p>Publication <code>{html.escape(publication.report_id)}</code>; '
             f'native report <code>{html.escape(publication.source_report_id)}</code>. '
             '<a href="report-envelope.json">Versioned envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return original.replace("</body>", links + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict:
    bundle = Path(bundle)
    record = source.check(bundle)
    envelope = {
        "schema": "csl.algorithm-report-envelope/1",
        "report_id": publication.report_id,
        "report_kind": publication.kind,
        "payload_schema": publication.payload_schema,
        "payload_sha256": publication.payload_sha256,
        "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope,
        "evidence_limits": publication.evidence_limits,
        "native_payload_sha256": publication.native_payload_sha256,
        "source_report_id": publication.source_report_id,
        "payload": record,
    }
    return common.assemble_publication(
        bundle, publication, page=render_page(bundle, publication),
        envelope=envelope, source_files=publication.files,
    )


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id,
                                  publication_artifacts(bundle, publication))

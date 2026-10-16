"""Schema-3 publication adapter for a reviewed saved OPT-07 native bundle."""
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

_PACKAGE = "csl_opt07_report_tooling"
_tooling = Path(__file__).resolve().parents[2] / "reports/algorithm-results/tooling/opt07"
if _PACKAGE not in sys.modules:
    package = ModuleType(_PACKAGE)
    package.__path__ = [str(_tooling)]
    sys.modules[_PACKAGE] = package
source = importlib.import_module(_PACKAGE + ".build_bundle")


KIND = "opt07-ordered-hull"
FILES = source.SOURCE_FILES
STAGE_FILES = FILES | {"manifest.json"}
LIMITS = ("Three fixed small binary64 clouds; independent exact-dyadic deletion "
          "certificates and literal support checks apply only to represented inputs; "
          "single-adapter 100-call batches with no comparator, speedup, "
          "source-mapped limiter profile, or scalability claim")


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    record = source.check(bundle)
    if re.fullmatch(r"opt07-[0-9a-f]{16}", bundle.name) is None:
        raise ValueError("unsafe OPT-07 source identity")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    common.validate_source_inventory(bundle, manifest["files"], FILES,
                                     label="OPT-07")
    identity = {"schema": "csl.registered-publication-identity/1",
                "source_report_id": bundle.name,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                                 for name in sorted(STAGE_FILES)},
                "source_zip_sha256": hashlib.sha256(
                    (bundle.parent / (bundle.name + ".source.zip")).read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(
                    Path(__file__).read_text(encoding="utf-8").replace(
                        "\r\n", "\n").encode("utf-8")).hexdigest()}
    public_id = bundle.name.rsplit("-", 1)[0] + "-" + common._digest(identity)
    scope = ("21 verified measured 100-call batches across three fixed ordered-hull "
             "clouds; performance interpretation inconclusive")
    return common.PublicationRecord(KIND, public_id, common._digest(record),
                                    record["source_commit"], scope, LIMITS,
                                    tuple(sorted(STAGE_FILES)), source.SCHEMA,
                                    record["payload_sha256"], bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    record = source.check(Path(bundle))
    original = source.page(record)
    if original.count("</body>") != 1:
        raise ValueError("OPT-07 source HTML structure is malformed")
    links = (f'<p>Publication <code>{html.escape(publication.report_id)}</code>; '
             f'native report <code>{html.escape(publication.source_report_id)}</code>. '
             '<a href="report-envelope.json">Versioned envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return original.replace("</body>", links + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict:
    bundle = Path(bundle)
    record = source.check(bundle)
    envelope = {"schema": "csl.algorithm-report-envelope/1",
                "report_id": publication.report_id,
                "report_kind": publication.kind,
                "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_report_id": publication.source_report_id,
                "payload": record}
    return common.assemble_publication(bundle, publication,
                                       page=render_page(bundle, publication),
                                       envelope=envelope,
                                       source_files=publication.files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id,
                                  publication_artifacts(bundle, publication))

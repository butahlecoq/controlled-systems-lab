"""Publish the reviewed GEO-06 QuickHull saved report without rerunning geometry."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import zipfile

import geo06_report as source
import registered_reports as common


KIND = "geo06-quickhull"
FILES = {"build-log.txt", "build-provenance.json", "index.html", "records.json", "trials.csv"}
STAGE_FILES = FILES | {"manifest.json"}
LIMITS = ("Descriptive single-adapter verified-call batches on three tiny analytic clouds; "
          "timed index copies and literal oracle comparisons are included; no comparator, speedup, "
          "application-scale, or scalability claim; no source-mapped limiter profile; "
          "binary64 input orientation is exact only for represented coordinates")


def _json(path):
    return source.strict_json(Path(path))


def adapt_payload(record):
    source.validate(record)
    rid = record["report_id"]
    if re.fullmatch(r"geo06-[0-9a-f]{16}", rid) is None:
        raise ValueError("unsafe GEO-06 report ID")
    measured = [row for row in record["rows"] if row["warmup"] == 0]
    scope = (f"{len(measured)} verified measured call batches across three analytic QuickHull clouds; "
             f"{record['calls_per_trial']} calls per batch; performance interpretation inconclusive")
    return common.PublicationRecord(KIND, rid, common._digest(record), record["source_commit"], scope, LIMITS,
                                    tuple(sorted(STAGE_FILES)), source.SCHEMA, record["payload_sha256"], rid)


def source_zip_bytes(bundle):
    bundle = Path(bundle)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(STAGE_FILES):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (bundle / name).read_bytes())
    return buffer.getvalue()


def adapt(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("GEO-06 source bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    native = adapt_payload(record)
    if bundle.name != native.source_report_id:
        raise ValueError("GEO-06 source bundle identity differs")
    manifest = _json(bundle / "manifest.json")
    if (set(manifest) != {"schema", "report_id", "files"} or
            manifest.get("schema") != "csl.geo06-report-manifest/1" or
            manifest.get("report_id") != native.source_report_id):
        raise ValueError("GEO-06 source manifest identity differs")
    common.validate_source_inventory(bundle, manifest["files"], FILES, label="GEO-06")
    with contextlib.redirect_stdout(io.StringIO()):
        source.check(SimpleNamespace(bundle=bundle))
    source_zip = bundle.parent / (bundle.name + ".source.zip")
    if source_zip.is_symlink() or not source_zip.is_file() or source_zip.read_bytes() != source_zip_bytes(bundle):
        raise ValueError("GEO-06 source offline ZIP differs from saved bundle")
    publisher_bytes = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    identity = {"schema": "csl.registered-publication-identity/1",
                "source_report_id": native.source_report_id,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                                 for name in sorted(STAGE_FILES)},
                "source_zip_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher_bytes).hexdigest()}
    public_id = native.source_report_id.rsplit("-", 1)[0] + "-" + common._digest(identity)
    return common.PublicationRecord(native.kind, public_id, native.payload_sha256, native.source_commit,
                                    native.measured_scope, native.evidence_limits, native.files,
                                    native.payload_schema, native.native_payload_sha256, native.source_report_id)


def render_page(bundle, publication):
    bundle = Path(bundle)
    record = _json(bundle / "records.json")
    source.validate(record)
    original = (bundle / "index.html").read_text(encoding="utf-8")
    # The square has a visible two-dimensional hull; the skinny triangle's
    # 2^-50 height cannot be honestly depicted at this page scale.
    figure = ('<figure aria-label="Square QuickHull fixture">'
              '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240" '
              'role="img" aria-label="Square hull with four corners and one interior point">'
              '<polyline points="20,220 220,220 220,20 20,20 20,220" fill="none" stroke="#165a72" stroke-width="3"/>'
              '<circle cx="20" cy="220" r="5" fill="#165a72"/><circle cx="220" cy="220" r="5" fill="#165a72"/>'
              '<circle cx="220" cy="20" r="5" fill="#165a72"/><circle cx="20" cy="20" r="5" fill="#165a72"/>'
              '<circle cx="120" cy="120" r="5" fill="#a04c24"/></svg>'
              '<figcaption>Square fixture: four hull corners and one interior point. Duplicate input rows overlay corners.</figcaption>'
              '</figure>')
    links = (f'<p>Publication <code>{publication.report_id}</code>; native report <code>{publication.source_report_id}</code>. '
             '<a href="report-envelope.json">Versioned envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a> · '
             '<a href="build-provenance.json">Release build evidence</a>.</p>')
    if original.count("</body>") != 1 or original.count("</head>") != 1:
        raise ValueError("GEO-06 source HTML structure is malformed")
    style = ('<style>body{max-width:72rem;margin:1.5rem auto;padding:0 1rem;line-height:1.45}'
             'pre{white-space:pre-wrap;overflow-wrap:anywhere}'
             'table{border-collapse:collapse}th,td{padding:.25rem .5rem;text-align:left}'
             'tr{border-bottom:1px solid #ddd}figure{margin:1.5rem 0}</style>')
    original = original.replace("</head>", style + "</head>")
    return original.replace("</body>", figure + links + "</body>")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    record = _json(bundle / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_report_id": publication.source_report_id, "payload": record}
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))

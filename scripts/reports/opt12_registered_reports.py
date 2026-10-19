"""Publish the reviewed OPT-12 saved measurements without rerunning the solver."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

import opt12_render as source
import registered_reports as common


KIND = "opt12-warm-start"
FILES = set(source.EVIDENCE_FILES) | {"records.json", "index.html", "comparison.svg"}
STAGE_FILES = FILES | {"manifest.json"}
SOURCE_PATTERN = r"opt12-[0-9a-f]{12}"
LIMITS = (
    "42 verified paired trials across three synthetic LPs on one recorded host; "
    "performance interpretation is inconclusive because observed transfer-cost ranges overlap "
    "and the separate source-mapped diagnostic profile does not attribute the cold/warm latency difference; no general speedup, "
    "application-scale, or worst-case complexity claim"
)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_bundle(bundle: Path):
    if bundle.is_symlink():
        raise ValueError("OPT-12 source bundle cannot be a symlink")
    record = _json(bundle / "records.json")
    metadata, trials, _ = source.parse_evidence(bundle / "records.json")
    rid = bundle.name
    if re.fullmatch(SOURCE_PATTERN, rid) is None:
        raise ValueError("unsafe OPT-12 source report ID")
    manifest = _json(bundle / "manifest.json")
    if (set(manifest) != {"schema", "report_id", "files"} or
            manifest.get("schema") != "csl.opt12-cost-manifest/1" or
            manifest.get("report_id") != rid or set(manifest.get("files", {})) != FILES):
        raise ValueError("OPT-12 source manifest identity or inventory differs")
    common.validate_source_inventory(bundle, manifest["files"], FILES, label="OPT-12")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != STAGE_FILES:
        raise ValueError("OPT-12 source bundle has missing or unregistered files")
    if (bundle / "index.html").read_text(encoding="utf-8").count("Performance interpretation is inconclusive") != 1:
        raise ValueError("OPT-12 report does not disclose its inconclusive performance interpretation")
    return record, metadata, trials


def adapt_payload(record: dict) -> common.PublicationRecord:
    if (not isinstance(record, dict) or not isinstance(record.get("metadata"), dict) or
            record["metadata"].get("schema") != "csl.opt12-cost-report/1" or
            not isinstance(record.get("trials"), list)):
        raise ValueError("unsupported OPT-12 saved report payload")
    metadata = record["metadata"]
    source_commit = metadata.get("source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("OPT-12 source commit is missing or invalid")
    repetitions = metadata.get("policy", {}).get("repetitions_per_side_per_case")
    if type(repetitions) is not int or repetitions < 5 or len(record["trials"]) != repetitions * 6:
        raise ValueError("OPT-12 report does not contain the required paired measurements")
    scope = (f"{len(record['trials'])} verified paired trial rows across three synthetic LP fixtures; "
             f"{repetitions} alternating repetitions per side; performance interpretation inconclusive")
    publication_payload = {"schema": metadata["schema"], **record}
    return common.PublicationRecord(KIND, "", common._digest(publication_payload), source_commit, scope, LIMITS,
                                    tuple(sorted(STAGE_FILES)), metadata["schema"],
                                    hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(),
                                    "")


def adapt(bundle):
    bundle = Path(bundle)
    record, _, _ = _validate_bundle(bundle)
    native = adapt_payload(record)
    source_id = bundle.name
    zip_path = bundle.parent / f"{source_id}.zip"
    sidecar = bundle.parent / f"{source_id}.zip.sha256"
    if zip_path.is_symlink() or sidecar.is_symlink() or not zip_path.is_file() or not sidecar.is_file():
        raise ValueError("OPT-12 source offline ZIP or digest sidecar is missing")
    if sidecar.read_text(encoding="ascii").strip() != f"{hashlib.sha256(zip_path.read_bytes()).hexdigest()}  {source_id}.zip":
        raise ValueError("OPT-12 source offline ZIP digest differs from its sidecar")
    with zipfile.ZipFile(zip_path) as saved:
        expected_names = {f"{source_id}/{name}" for name in STAGE_FILES} | {f"{source_id}/offline-index.html"}
        if len(saved.namelist()) != len(expected_names) or set(saved.namelist()) != expected_names:
            raise ValueError("OPT-12 source offline ZIP inventory differs")
        for name in STAGE_FILES:
            if saved.read(f"{source_id}/{name}") != (bundle / name).read_bytes():
                raise ValueError(f"OPT-12 source offline ZIP has stale content: {name}")
        if saved.read(f"{source_id}/offline-index.html") != b'<!doctype html><meta charset="utf-8"><a href="index.html">Open report</a>':
            raise ValueError("OPT-12 source offline ZIP launcher differs")
    publisher_bytes = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": source_id,
                "source_files": {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                                 for name in sorted(STAGE_FILES)},
                "source_zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                "publisher_sha256": hashlib.sha256(publisher_bytes).hexdigest()}
    public_id = "opt12-warm-start-" + common._digest(identity)
    return common.PublicationRecord(native.kind, public_id, native.payload_sha256, native.source_commit,
                                    native.measured_scope, native.evidence_limits, native.files,
                                    native.payload_schema, native.native_payload_sha256, source_id)


def render_page(bundle, publication):
    bundle = Path(bundle)
    record, _, _ = _validate_bundle(bundle)
    original = (bundle / "index.html").read_text(encoding="utf-8")
    original = original.replace(f"../{publication.source_report_id}.zip", f"../{publication.report_id}.zip")
    links = (f'<p>Publication <code>{publication.report_id}</code>; native report '
             f'<code>{publication.source_report_id}</code>. '
             '<a href="report-envelope.json">Versioned envelope</a> · '
             '<a href="publication-manifest.json">Publication manifest</a> · '
             '<a href="build-provenance.json">Release build evidence</a>.</p>')
    if original.count("</body>") != 1:
        raise ValueError("OPT-12 source HTML structure is malformed")
    return original.replace("</body>", links + "</body>")


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    record, _, _ = _validate_bundle(bundle)
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "source_commit": publication.source_commit,
                "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_report_id": publication.source_report_id,
                "payload": {"schema": record["metadata"]["schema"], **record}}
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))

"""Schema-3 publication adapter for the saved validated minimax report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import registered_reports as common

KIND = "issue3-validated-minimax"
SOURCE_ID = "issue3-validated-minimax-20261023-r1"
SOURCE_COMMIT = "c72f3480c8fea2575ba860890502857006e9b9f4"
SCOPE = ("Three fixed validated finite-action minimax fixtures; seven measured batches "
         "after one excluded warmup per fixture")
LIMITS = ("Descriptive single-adapter batch timings with possible host contention; no "
          "comparator, speedup, source-mapped limiter, per-call latency, or scalability "
          "claim; displayed-data B08 uses exact-real semantics for saved binary64 inputs")


def _json(path: Path):
    return _loads(path.read_text(encoding="utf-8"))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _loads(text):
    return json.loads(text, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    manifest_bytes = (bundle / "manifest.json").read_bytes()
    manifest = _loads(manifest_bytes.decode("utf-8"))
    if (manifest.get("schema") != "csl.issue3-validated-minimax-manifest/1"
            or manifest.get("report_id") != SOURCE_ID
            or manifest.get("source_commit") != SOURCE_COMMIT
            or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("harness_commit", ""))):
        raise ValueError("validated minimax source identity differs")
    expected = manifest.get("files")
    paths = list(bundle.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("validated minimax bundle cannot contain symlinks")
    actual = {p.relative_to(bundle).as_posix() for p in paths if p.is_file() and p.name != "manifest.json"}
    if not isinstance(expected, dict) or actual != set(expected):
        raise ValueError("validated minimax file inventory differs")
    for name, digest in expected.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid validated minimax manifest entry")
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
            raise ValueError("validated minimax source file hash differs: " + name)
    record = _json(bundle / "records.json")
    if (record.get("schema") != "csl.issue3-validated-minimax-record/1"
            or record.get("source_commit") != SOURCE_COMMIT
            or record.get("harness_commit") != manifest["harness_commit"]):
        raise ValueError("validated minimax record provenance differs")
    rows = record.get("rows")
    if not isinstance(rows, list) or len(rows) != 24:
        raise ValueError("validated minimax requires the saved 24-row capture")
    raw = (bundle / "evidence/measure.stdout.jsonl").read_bytes()
    raw_rows = [_json_line(line) for line in raw.splitlines()]
    if rows != raw_rows or hashlib.sha256(raw).hexdigest() != record.get("raw_jsonl_sha256"):
        raise ValueError("validated minimax raw records differ")
    expected_work = {"analytic_2d": (2, 2), "all_infeasible": (1, 0), "b08_rounded": (625, 160000)}
    measured = [row for row in rows if not row.get("warmup")]
    summaries = record.get("summary")
    if not isinstance(summaries, dict) or set(summaries) != set(expected_work):
        raise ValueError("validated minimax summary fixtures differ")
    fixture_hashes = {row.get("fixture_sha256") for row in rows}
    if len(fixture_hashes) != 1 or record.get("fixture_sha256") not in fixture_hashes:
        raise ValueError("validated minimax fixture identity differs")
    for name, (plans, histories) in expected_work.items():
        group = [row for row in rows if row.get("fixture") == name]
        trials = [row for row in measured if row.get("fixture") == name]
        if (len(group) != 8 or len(trials) != 7 or any(row.get("status") != "passed" for row in group)
                or any(row.get("source_commit") != SOURCE_COMMIT for row in group)
                or any(row.get("harness_commit") != manifest["harness_commit"] for row in group)
                or any(row.get("result", {}).get("plans", row.get("result", {}).get("plan_count")) != plans
                       or row.get("result", {}).get("histories_examined", 0) != histories for row in group)):
            raise ValueError("validated minimax fixture work differs: " + name)
        summary = summaries.get(name, {})
        times = [row["elapsed_ns"] for row in trials]
        if (summary.get("observations_ns") != times or summary.get("median_ns") != sorted(times)[3]
                or summary.get("min_ns") != min(times) or summary.get("max_ns") != max(times)):
            raise ValueError("validated minimax timing summary differs: " + name)
    identity = {"schema": "csl.issue3-validated-minimax-publication/1",
                "source_report_id": SOURCE_ID, "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "publisher_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    payload_hash = common._digest(record)
    return common.PublicationRecord(KIND, KIND + "-" + common._digest(identity), payload_hash,
                                    SOURCE_COMMIT, SCOPE, LIMITS, tuple(sorted(actual | {"manifest.json"})),
                                    record["schema"], payload_hash, SOURCE_ID)


def _json_line(line: bytes):
    return _loads(line.decode("utf-8"))


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    footer = (f'<p>Versioned publication <code>{publication.report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</html>", footer + "</html>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    record = _json(Path(bundle) / "records.json")
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256, "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits, "source_report_id": publication.source_report_id,
                "payload": record}
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def catalogue_entry(bundle: Path) -> dict:
    publication = adapt(bundle)
    return {"report_id": publication.report_id, "report_kind": publication.kind,
            "source_report_id": publication.source_report_id, "payload_schema": publication.payload_schema,
            "payload_sha256": publication.payload_sha256, "native_payload_sha256": publication.native_payload_sha256,
            "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "zip_sha256": hashlib.sha256(offline_zip(bundle, publication)).hexdigest()}

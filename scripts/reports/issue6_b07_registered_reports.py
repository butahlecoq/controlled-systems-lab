"""Publish the saved B07 fuel projections and evidence without rerunning the solver."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import registered_reports as common


KIND = "issue6-b07-reference"
SOURCE_PATTERN = r"b07-owner-approved-eight-case-v1"
FILES = ("README.md", "index.html", "independent-oracle-verification.json",
         "projections.png", "projections.svg", "results.jsonl", "run-provenance.json",
         "SHA256SUMS")
LIMITS = ("Eight owner-approved reconstructions, not historical reproductions; the modeled horizon is "
          "10 seconds while the paper states 100 seconds. Single-adapter timings only, without a "
          "limiter profile or speedup claim. Plotted points are numerical projections of 4D terminal sets.")


def _payload(bundle: Path) -> dict:
    rows = [json.loads(line) for line in (bundle / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    provenance = json.loads((bundle / "run-provenance.json").read_text(encoding="utf-8"))
    results = (bundle / "results.jsonl").read_bytes()
    if provenance.get("results_sha256") != hashlib.sha256(results).hexdigest():
        raise ValueError("B07 provenance results digest differs")
    return {"schema": "csl.issue6-b07-evidence/1", "report_id": bundle.name,
            "source_commit": provenance["source_commit"], "cases": rows}


def _close(actual, expected, absolute_tolerance: float) -> bool:
    numeric = (int, float)
    return (type(actual) in numeric and type(expected) in numeric and
            math.isfinite(actual) and math.isfinite(expected) and
            math.isclose(actual, expected, rel_tol=0, abs_tol=absolute_tolerance))


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("B07 source bundle must be a real directory")
    if bundle.name != SOURCE_PATTERN:
        raise ValueError("B07 saved report identity differs")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are forbidden in B07 bundle")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != set(FILES):
        raise ValueError("B07 registered source inventory mismatch")
    checksums = {}
    for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("B07 checksum inventory contains duplicate files")
        checksums[name] = digest
    if set(checksums) != set(FILES) - {"SHA256SUMS"}:
        raise ValueError("B07 checksum inventory differs")
    for name, digest in checksums.items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
            raise ValueError("B07 source file hash mismatch: " + name)
    provenance = json.loads((bundle / "run-provenance.json").read_text(encoding="utf-8"))
    if (provenance.get("schema") != "csl.issue6-b07-capture-provenance/1" or
            provenance.get("source_tree_clean") is not True or provenance.get("build_type") != "Release"):
        raise ValueError("B07 capture provenance is incomplete")
    results = (bundle / "results.jsonl").read_bytes()
    rows = [json.loads(line) for line in results.decode("utf-8").splitlines()]
    if len(rows) != 8 or len({row.get("case_id") for row in rows}) != 8:
        raise ValueError("B07 eight-case result inventory differs")
    oracle = json.loads((bundle / "independent-oracle-verification.json").read_text(encoding="utf-8"))
    rows_by_id = {row["case_id"]: row for row in rows}
    oracle_by_id = {item.get("case_id"): item for item in oracle}
    if len(oracle) != 8 or len(oracle_by_id) != 8 or set(oracle_by_id) != set(rows_by_id):
        raise ValueError("B07 independent oracle evidence differs")
    for case_id, row in rows_by_id.items():
        item = oracle_by_id[case_id]
        if any(row.get(field) != provenance.get(source_field) for field, source_field in (
                ("source_commit", "source_commit"), ("driver_sha256", "driver_sha256"),
                ("scenario_sha256", "scenario_sha256"), ("executable_sha256", "executable_sha256"),
                ("build_type", "build_type"))):
            raise ValueError("B07 row provenance differs from capture provenance: " + case_id)
        if (item.get("solver_feasible") != row.get("plans_feasible") or
                item.get("oracle_feasible") != row.get("plans_feasible") or
                item.get("solver_winners") != row.get("minimizing_plan_indices") or
                item.get("oracle_winners") != row.get("minimizing_plan_indices") or
                not _close(item.get("solver_squared"), row.get("value_squared"), 1e-12) or
                not _close(item.get("oracle_squared"), row.get("value_squared"), 1e-7) or
                not _close(item.get("abs_diff"), abs(item["solver_squared"]-item["oracle_squared"]), 1e-15) or
                item["abs_diff"] > 1e-7 or not _close(row.get("value_norm")**2 if type(row.get("value_norm")) in (int,float) else None, row.get("value_squared"), 1e-12)):
            raise ValueError("B07 row and independent oracle differ: " + case_id)
    payload = _payload(bundle)
    identity = {"schema": "csl.issue6-b07-publication-identity/1", "source_report_id": bundle.name,
                "source_files": checksums,
                "publisher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    public_id = KIND + "-" + common._digest(identity)
    scope = "Eight five-stage finite-action minimax cases; 3,125 plans x up to 1,024 disturbance histories per case; one excluded warmup and seven measured Release calls per case"
    return common.PublicationRecord(KIND, public_id, common._digest(payload), provenance["source_commit"],
                                    scope, LIMITS, FILES, payload["schema"],
                                    hashlib.sha256((bundle / "results.jsonl").read_bytes()).hexdigest(), bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = (Path(bundle) / "index.html").read_text(encoding="utf-8")
    if page.count("</html>") != 1:
        raise ValueError("B07 source page insertion point differs")
    footer = (f'<p>Versioned publication <code>{publication.report_id}</code>; '
              f'native report <code>{publication.source_report_id}</code>. '
              '<a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    return page.replace("</html>", footer + "</html>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    payload = _payload(Path(bundle))
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "source_report_id": publication.source_report_id, "payload": payload}
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=publication.files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def catalogue_entry(bundle: Path) -> dict:
    publication = adapt(bundle)
    archive = offline_zip(bundle, publication)
    return {"report_id": publication.report_id, "report_kind": publication.kind,
            "source_report_id": publication.source_report_id, "payload_schema": publication.payload_schema,
            "payload_sha256": publication.payload_sha256,
            "native_payload_sha256": publication.native_payload_sha256,
            "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "zip_sha256": hashlib.sha256(archive).hexdigest()}

"""Typed, hash-checked publication adapter for the B04-C research dossier."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import registered_reports as common

from docs.research.tools.check_b04_c_exact_fiber import check
from docs.research.tools.render_b04_c_exact_fiber_report import render

ROOT = Path(__file__).resolve().parents[2]
KIND = "b04-c-research-dossier"
SOURCE_ID = "b04-c-exact-dyadic-v1"
MANIFEST_SHA256 = "8ee378c901c36a148166fa5dd5a2bf2747352847ff1510869bd9babaaf32aee8"
SNAPSHOT_ROOT = Path("docs/research/evidence/b04-c-publication-source-snapshot")
SPINE_SNAPSHOT_ROOT = Path("docs/research/evidence/b04-c-publication-spine-source-v1")
SPINE_SNAPSHOT_MANIFEST_SHA256 = "a3307b6537b5a40c4d8b485fe50313e6be062ed4e34fc20aba926bd43541abc4"
SPINE_SOURCE_FILES = frozenset(
    {
        "scripts/reports/report_data.py",
        "scripts/reports/publication_policy.py",
        "scripts/reports/registered_reports.py",
    }
)
SNAPSHOT_FILES = frozenset(
    {
        "scripts/reports/b04_c_exact_registered_reports.py",
        "scripts/reports/schema3_publication_policies.py",
        "scripts/reports/site.py",
        "scripts/reports/landing.py",
        "scripts/reports/visual_examples.py",
        "scripts/reports/algorithm_visual_coverage.json",
        ".github/workflows/algorithm-reports.yml",
    }
)
SOURCE_FILES = (
    "docs/research/tools/b04_c_exact_profile.py",
    "docs/research/tools/build_b04_c_exact_fiber.py",
    "docs/research/tools/check_b04_c_exact_fiber.py",
    "docs/research/tools/render_b04_c_exact_fiber.py",
    "docs/research/tools/render_b04_c_exact_fiber_report.py",
    "docs/research/tools/finalize_b04_c_exact_fiber.py",
    "tests/reporting/test_b04_c_exact_fiber.py",
    ".github/workflows/algorithm-reports.yml",
    "scripts/reports/b04_c_exact_registered_reports.py",
    "scripts/reports/b04_c_exact_publication_policy.py",
    "scripts/reports/registered_reports.py",
    "scripts/reports/publication_policy.py",
    "scripts/reports/report_data.py",
    "scripts/reports/schema3_publication_policies.py",
    "scripts/reports/site.py",
    "scripts/reports/landing.py",
    "scripts/reports/visual_examples.py",
    "scripts/reports/algorithm_visual_coverage.json",
)
FROZEN_SOURCE_HASHES = {
    # These values identify historical inputs to the published report. They
    # remain provenance after prose removal or tooling changes; neither file
    # is a current runtime dependency.
    "docs/research/tools/README.md": "cfefd0e48e8dba4789af5b1055c4dae997b5a8216287ebf97622161803d50d25",
    "docs/research/tools/finalize_b04_c_exact_fiber.py": "b6ea85fe3835344f6ec17ec003e0dbf6ccd501f035212ea54879a2c2f9e0367d",
}
FILES = {"README.md", "record.json", "trajectory.svg", "verification.json", "tests.txt"}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _pretty(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def _checked_spine_sources(root: Path, recorded: dict[str, str]) -> dict[str, bytes]:
    if root.is_symlink():
        raise ValueError("B04-C publication source root is unsafe")
    for relative in (SPINE_SNAPSHOT_ROOT, SNAPSHOT_ROOT):
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise ValueError("B04-C publication source directory is missing or unsafe")
    snapshot = root / SPINE_SNAPSHOT_ROOT
    manifest_path = snapshot / "manifest.json"
    if snapshot.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("B04-C publication spine source manifest is missing or unsafe")
    raw_manifest = manifest_path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != SPINE_SNAPSHOT_MANIFEST_SHA256:
        raise ValueError("B04-C publication spine source manifest hash mismatch")
    manifest = json.loads(raw_manifest)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "csl.b04-c-publication-spine-source/1"
        or manifest.get("owner_report_id") != SOURCE_ID
        or manifest.get("owner_manifest_sha256") != MANIFEST_SHA256
    ):
        raise ValueError("B04-C publication spine source owner mismatch")
    files = manifest.get("files")
    if files != {name: recorded[name] for name in SPINE_SOURCE_FILES}:
        raise ValueError("B04-C publication spine recorded source hashes differ")
    common.validate_source_inventory(
        snapshot, files, SPINE_SOURCE_FILES, label="B04-C publication spine"
    )
    previous = manifest.get("existing_snapshot")
    if not isinstance(previous, dict) or previous.get("root") != SNAPSHOT_ROOT.as_posix():
        raise ValueError("B04-C existing publication source owner mismatch")
    previous_root = root / SNAPSHOT_ROOT
    previous_files = previous.get("files_sha256")
    paths = list(previous_root.rglob("*"))
    actual = {path.relative_to(previous_root).as_posix(): path for path in paths if path.is_file()}
    if (
        previous_root.is_symlink()
        or any(path.is_symlink() for path in paths)
        or not isinstance(previous_files, dict)
        or set(actual) != set(previous_files)
    ):
        raise ValueError("B04-C existing publication source inventory mismatch")
    for name, path in actual.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != previous_files[name]:
            raise ValueError("B04-C source hash mismatch: " + name)
    return {name: (snapshot / name).read_bytes() for name in SPINE_SOURCE_FILES}


def _verify_bundle(bundle: Path):
    if bundle.is_symlink() or any(item.is_symlink() for item in bundle.rglob("*")):
        raise ValueError("B04-C bundle cannot contain symlinks")
    if hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError("B04-C manifest hash mismatch")
    manifest = _json(bundle / "manifest.json")
    if (
        manifest.get("schema") != "csl.b04-c-exact-dyadic-manifest/1"
        or manifest.get("scenario_id") != "B04-c-exact-dyadic-20261102"
        or bundle.name != SOURCE_ID
    ):
        raise ValueError("B04-C bundle identity differs")
    evidence = manifest.get("evidence_files")
    actual = {item.name for item in bundle.iterdir() if item.is_file()}
    if not isinstance(evidence, dict) or actual != set(evidence) | {"manifest.json"}:
        raise ValueError("B04-C evidence inventory differs")
    for name, expected in evidence.items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected:
            raise ValueError("B04-C evidence hash mismatch: " + name)
    source_hashes = manifest.get("source_files")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(SOURCE_FILES) | set(
        FROZEN_SOURCE_HASHES
    ):
        raise ValueError("B04-C source hash inventory differs")
    spine_sources = _checked_spine_sources(ROOT, source_hashes)
    for name, expected in source_hashes.items():
        if name in FROZEN_SOURCE_HASHES:
            if expected != FROZEN_SOURCE_HASHES[name]:
                raise ValueError("B04-C frozen source hash differs: " + name)
            continue
        if name in spine_sources:
            if hashlib.sha256(spine_sources[name]).hexdigest() != expected:
                raise ValueError("B04-C source hash mismatch: " + name)
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe B04-C source path")
        source = ROOT / SNAPSHOT_ROOT / relative if name in SNAPSHOT_FILES else ROOT / relative
        if (
            source.is_symlink()
            or not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("B04-C source hash mismatch: " + name)
    record = _json(bundle / "record.json")
    verified = check(bundle / "record.json")
    if verified != _json(bundle / "verification.json"):
        raise ValueError("B04-C stored verification differs from the independent checker")
    if (bundle / "index.html").read_text(encoding="utf-8") != render(bundle / "record.json"):
        raise ValueError("B04-C report page differs from the checked record")
    return manifest, record, verified


@common.preserve_publication
def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    _, record, _ = _verify_bundle(bundle)
    payload_hash = common._digest(record)
    identity = {
        "schema": "csl.b04-c-research-publication-identity/1",
        "source_report_id": bundle.name,
        "evidence_manifest_sha256": hashlib.sha256(
            (bundle / "manifest.json").read_bytes()
        ).hexdigest(),
        "payload_sha256": payload_hash,
    }
    report_id = "b04-c-research-dossier-" + hashlib.sha256(_canonical(identity)).hexdigest()
    return common.PublicationRecord(
        KIND,
        report_id,
        payload_hash,
        record["source_commit"],
        "External exact mathematical audit of the owner-authorized corrected-track B04-C profile",
        "Research evidence only: no compiled verifier or prepared Strategy A result; does not satisfy the registered complete-family requirement; not a historical reproduction; A40 unit scaling remains unresolved",
        tuple(sorted(FILES)),
        record["schema"],
        payload_hash,
        bundle.name,
    )


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    page = render(Path(bundle) / "record.json")
    page = page.replace('href="manifest.json"', 'href="evidence-manifest.json"')
    links = (
        f"<p>Publication <code>{publication.report_id}</code>; source report "
        f"<code>{publication.source_report_id}</code>. "
        '<a href="report-envelope.json">Versioned report envelope</a> · '
        '<a href="publication-manifest.json">Publication manifest</a></p>'
    )
    return page.replace("</body>", links + "</body>")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    bundle = Path(bundle)
    files = {name: (bundle / name).read_bytes() for name in publication.files}
    files["evidence-manifest.json"] = (bundle / "manifest.json").read_bytes()
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    record = _json(bundle / "record.json")
    files["report-envelope.json"] = _pretty(
        {
            "schema": "csl.algorithm-report-envelope/1",
            "report_id": publication.report_id,
            "report_kind": publication.kind,
            "payload_schema": publication.payload_schema,
            "payload_sha256": publication.payload_sha256,
            "native_payload_sha256": publication.native_payload_sha256,
            "source_commit": publication.source_commit,
            "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "source_report_id": publication.source_report_id,
            "payload": record,
        }
    )
    files["publication-manifest.json"] = _pretty(
        {
            "schema": "csl.algorithm-report-publication-manifest/1",
            "report_id": publication.report_id,
            "report_kind": publication.kind,
            "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)},
        }
    )
    return files


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir: Path, expected: dict) -> bool:
    return common.validate_publication_manifest(report_dir, expected)

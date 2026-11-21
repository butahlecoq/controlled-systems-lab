"""Validate EXT-01 saved bytes and stage one content-bound Pages report route."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from dataclasses import replace
from html import escape
from pathlib import Path

import registered_reports as common
import report_data

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "csl_ext01_saved_renderer", ROOT / "scripts/reports/ext01/render_saved.py"
)
if spec is None or spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "csl_ext01_site_validator", Path(__file__).with_name("site.py")
)
if site_spec is None or site_spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
site = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(site)

HISTORICAL_REPORT_ID = (
    "ext01-fixed-plan-303ad863ca3af58dc6a515844c474fe0e1af9349e55cb8acd1ff1a3f220f1b54"
)
HISTORICAL_INVENTORY_SHA256 = "8b69dd7cec7525b3e809f4a35cbc2678fe0a60f461384e3059609d6349bd6631"
HISTORICAL_ZIP_SHA256 = "dbdb977b50c9e0f18bebdfe50e8ea6b01cb8c9373389a4e9f575f268058864e1"

KIND = "ext01-fixed-plan"
SCOPE = "Four native fixed-plan and convex worst-case numerical fixtures; seven Release batch observations each"
LIMITS = (
    "Single adapter, no comparator or speedup; displayed rounded B08 finite-action catalogue only; "
    "binary64 numerical assurance, no validated enclosure, nonlinear result or feedback optimal-family claim"
)
FILES = report.SOURCE_FILES | report.RENDERED_FILES | {report.MANIFEST, report.ARCHIVE}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path) -> dict:
    value = report.read_json(path.read_bytes())
    require(isinstance(value, dict), "JSON object required")
    return value


def validate(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    require(
        bundle.name == report.REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
        "unsafe EXT-01 source identity",
    )
    require(
        {path.name for path in bundle.iterdir()} == FILES
        and all(path.is_file() and not path.is_symlink() for path in bundle.iterdir()),
        "EXT-01 exact allowlisted bundle inventory differs",
    )
    report.render(bundle, check=True)
    record = read_json(bundle / "records.json")
    manifest = read_json(bundle / report.MANIFEST)
    require(
        manifest.get("schema") == "csl.ext01-native-manifest/1"
        and manifest.get("report_id") == bundle.name
        and manifest.get("source_commit") == report.SOURCE
        and manifest.get("harness_commit") == report.HARNESS
        and set(manifest.get("files", {})) == FILES - {report.MANIFEST, report.ARCHIVE},
        "native manifest identity/inventory differs",
    )
    for name, expected in manifest["files"].items():
        require(
            re.fullmatch(r"[0-9a-f]{64}", expected) is not None
            and digest_bytes((bundle / name).read_bytes()) == expected,
            "native manifest hash differs: " + name,
        )
    report_data.validate_svg((bundle / "b08-trials.svg").read_bytes())
    site.OfflineHTML(FILES | {"report-envelope.json", "publication-manifest.json"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8")
    )
    identity = {
        "schema": "csl.ext01-publication-identity/1",
        "source_report_id": bundle.name,
        "source_files": {
            name: digest_bytes((bundle / name).read_bytes()) for name in sorted(FILES)
        },
        "publisher": {
            name: digest_bytes((ROOT / "scripts/reports" / name).read_bytes())
            for name in ("stage_ext01.py", "ext01/render_saved.py")
        },
    }
    public_id = "ext01-fixed-plan-" + common._digest(identity)
    payload_hash = common._digest(record)
    publication = common.PublicationRecord(
        KIND,
        public_id,
        payload_hash,
        report.SOURCE,
        SCOPE,
        LIMITS,
        tuple(sorted(FILES)),
        record["schema"],
        payload_hash,
        bundle.name,
    )
    # Reuse the route only when the original source inventory and regenerated ZIP both match.
    if common._digest(identity["source_files"]) == HISTORICAL_INVENTORY_SHA256:
        historical = replace(publication, report_id=HISTORICAL_REPORT_ID)
        archive = common.publication_zip(historical.report_id, public_artifacts(bundle, historical))
        if digest_bytes(archive) == HISTORICAL_ZIP_SHA256:
            return historical
    return publication


def public_artifacts(bundle: Path, item: common.PublicationRecord) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in item.files}
    footer = (
        "<p>Versioned publication <code>"
        + escape(item.report_id)
        + '</code>. <a href="report-envelope.json">Report envelope</a> · '
        '<a href="publication-manifest.json">Publication manifest</a>.</p>'
    )
    source_page = files["index.html"].decode("utf-8")
    require(source_page.count("</body>") == 1, "EXT-01 page insertion point differs")
    files["index.html"] = source_page.replace("</body>", footer + "</body>").encode("utf-8")
    record = read_json(bundle / "records.json")
    files["report-envelope.json"] = report.json_bytes(
        {
            "schema": "csl.algorithm-report-envelope/1",
            "report_id": item.report_id,
            "report_kind": item.kind,
            "payload_schema": item.payload_schema,
            "payload_sha256": item.payload_sha256,
            "native_payload_sha256": item.native_payload_sha256,
            "source_commit": item.source_commit,
            "measured_scope": item.measured_scope,
            "evidence_limits": item.evidence_limits,
            "source_report_id": item.source_report_id,
            "payload": record,
        }
    )
    files["publication-manifest.json"] = report.json_bytes(
        {
            "schema": "csl.algorithm-report-publication-manifest/1",
            "report_id": item.report_id,
            "report_kind": item.kind,
            "files": {name: digest_bytes(files[name]) for name in sorted(files)},
        }
    )
    return files


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    archive = common.publication_zip(item.report_id, public_artifacts(bundle, item))
    return {
        "report_id": item.report_id,
        "report_kind": item.kind,
        "source_report_id": item.source_report_id,
        "payload_schema": item.payload_schema,
        "payload_sha256": item.payload_sha256,
        "native_payload_sha256": item.native_payload_sha256,
        "source_commit": item.source_commit,
        "measured_scope": item.measured_scope,
        "evidence_limits": item.evidence_limits,
        "zip_sha256": digest_bytes(archive),
    }


def stage(catalogue_path: Path, site_dir: Path) -> str:
    catalogue_path = Path(catalogue_path)
    site_dir = Path(site_dir)
    catalogue = read_json(catalogue_path)
    require(
        catalogue.get("schema") == "csl.ext01-report-extension/1"
        and isinstance(catalogue.get("reports"), list)
        and len(catalogue["reports"]) == 1,
        "EXT-01 extension catalogue differs",
    )
    source_id = catalogue["reports"][0].get("source_report_id")
    require(source_id == report.REPORT_ID, "EXT-01 catalogue source differs")
    bundle = catalogue_path.parent / source_id
    expected = catalogue_entry(bundle)
    require(catalogue["reports"][0] == expected, "EXT-01 extension catalogue differs from source")
    item = validate(bundle)
    files = public_artifacts(bundle, item)
    archive = common.publication_zip(item.report_id, files)
    require(digest_bytes(archive) == expected["zip_sha256"], "public ZIP hash differs")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    destination = site_dir / item.report_id
    require(
        site_dir.is_dir()
        and not site_dir.is_symlink()
        and not destination.exists()
        and not (site_dir / (item.report_id + ".zip")).exists(),
        "EXT-01 public route must be a fresh staged destination",
    )
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    require(
        index.count("</ul>") == 1 and item.report_id not in index,
        "EXT-01 site index insertion point differs",
    )
    link = (
        '<li><a href="'
        + escape(item.report_id)
        + '/index.html">'
        + escape(item.report_id)
        + "</a> — "
        + escape(SCOPE)
        + "; limits: "
        + escape(LIMITS)
        + ' · <a href="'
        + escape(item.report_id)
        + '/records.json">raw JSON</a> · <a href="'
        + escape(item.report_id)
        + '/trials.csv">trials CSV</a> · <a href="'
        + escape(item.report_id)
        + '.zip">offline ZIP</a></li>'
    )
    site.OfflineHTML(
        {
            item.report_id + "/index.html",
            item.report_id + "/records.json",
            item.report_id + "/trials.csv",
            item.report_id + ".zip",
        }
    ).feed(link)
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    require(
        common.validate_publication_manifest(destination, expected),
        "EXT-01 public manifest validation failed",
    )
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    (site_dir / "index.html").write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return item.report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(
            json.dumps(
                {
                    "schema": "csl.ext01-report-extension/1",
                    "reports": [catalogue_entry(args.source)],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")


if __name__ == "__main__":
    main()

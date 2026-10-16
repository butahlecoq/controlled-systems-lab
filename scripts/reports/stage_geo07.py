"""Validate saved GEO-07 bytes and stage one content-bound Pages report route."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path

import registered_reports as common


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "csl_geo07_saved_renderer", ROOT / "scripts/reports/geo07/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location("csl_geo07_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)

KIND = "geo07-generator-sets"
SCOPE = "21 verified measured batches across three bounded public generator-set fixtures; 5,000 fresh calls per batch"
LIMITS = ("Exploratory and inconclusive single-adapter timings; no comparator, limiter profile, speedup or complete-family claim; "
          "binary64 evaluation has no validated rounding enclosure")
FILES = report.SOURCE_FILES | report.RENDERED_FILES


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path) -> dict:
    return report.json_object(path.read_bytes())


def validate(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    require(bundle.name == report.REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "unsafe GEO-07 source identity")
    require({path.name for path in bundle.iterdir()} == FILES and
            all(path.is_file() and not path.is_symlink() for path in bundle.iterdir()),
            "GEO-07 exact allowlisted bundle inventory differs")
    report.render(bundle, check=True)
    site.OfflineHTML(FILES | {"report-envelope.json", "publication-manifest.json"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    identity = {
        "schema": "csl.geo07-publication-identity/1", "source_report_id": bundle.name,
        "source_files": {name: digest((bundle / name).read_bytes()) for name in sorted(FILES)},
        "publisher": {name: digest((ROOT / "scripts/reports" / name).read_bytes())
                      for name in ("stage_geo07.py", "geo07/render_saved.py")},
    }
    public_id = "geo07-generator-sets-" + common._digest(identity)
    record = read_json(bundle / "records.json")
    payload_hash = common._digest(record)
    return common.PublicationRecord(KIND, public_id, payload_hash, report.SOURCE,
                                    SCOPE, LIMITS, tuple(sorted(FILES)), record["schema"],
                                    payload_hash, bundle.name)


def public_artifacts(bundle: Path, item: common.PublicationRecord) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in item.files}
    footer = ('<p>Versioned publication <code>' + escape(item.report_id) +
              '</code>. <a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    source_page = files["index.html"].decode("utf-8")
    require(source_page.count("</body>") == 1, "GEO-07 page insertion point differs")
    files["index.html"] = source_page.replace("</body>", footer + "</body>").encode("utf-8")
    record = read_json(bundle / "records.json")
    files["report-envelope.json"] = report.collect.json_bytes({
        "schema": "csl.algorithm-report-envelope/1", "report_id": item.report_id,
        "report_kind": item.kind, "payload_schema": item.payload_schema,
        "payload_sha256": item.payload_sha256,
        "native_payload_sha256": item.native_payload_sha256,
        "source_commit": item.source_commit, "measured_scope": item.measured_scope,
        "evidence_limits": item.evidence_limits, "source_report_id": item.source_report_id,
        "payload": record})
    files["publication-manifest.json"] = report.collect.json_bytes({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": item.report_id, "report_kind": item.kind,
        "files": {name: digest(files[name]) for name in sorted(files)}})
    return files


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    archive = common.publication_zip(item.report_id, public_artifacts(bundle, item))
    return {"report_id": item.report_id, "report_kind": item.kind,
            "source_report_id": item.source_report_id,
            "payload_schema": item.payload_schema, "payload_sha256": item.payload_sha256,
            "native_payload_sha256": item.native_payload_sha256,
            "source_commit": item.source_commit, "measured_scope": item.measured_scope,
            "evidence_limits": item.evidence_limits, "zip_sha256": digest(archive)}


def stage(catalogue_path: Path, site_dir: Path) -> str:
    catalogue_path = Path(catalogue_path)
    site_dir = Path(site_dir)
    catalogue = read_json(catalogue_path)
    require(catalogue.get("schema") == "csl.geo07-report-extension/1" and
            isinstance(catalogue.get("reports"), list) and len(catalogue["reports"]) == 1,
            "GEO-07 extension catalogue differs")
    source_id = catalogue["reports"][0].get("source_report_id")
    require(source_id == report.REPORT_ID, "GEO-07 catalogue source differs")
    bundle = catalogue_path.parent / source_id
    expected = catalogue_entry(bundle)
    require(catalogue["reports"][0] == expected,
            "GEO-07 extension catalogue differs from source")
    item = validate(bundle)
    files = public_artifacts(bundle, item)
    archive = common.publication_zip(item.report_id, files)
    require(digest(archive) == expected["zip_sha256"], "public ZIP hash differs")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    destination = site_dir / item.report_id
    require(site_dir.is_dir() and not site_dir.is_symlink() and not destination.exists() and
            not (site_dir / (item.report_id + ".zip")).exists(),
            "GEO-07 public route must be a fresh staged destination")
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    require(common.validate_publication_manifest(destination, expected),
            "GEO-07 public manifest validation failed")
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    require(index.count("</ul>") == 1 and item.report_id not in index,
            "GEO-07 site index insertion point differs")
    link = ('<li><a href="' + escape(item.report_id) + '/index.html">' +
            escape(item.report_id) + '</a> — ' + escape(SCOPE) + '; limits: ' +
            escape(LIMITS) + ' · <a href="' + escape(item.report_id) +
            '/records.json">raw JSON</a> · <a href="' + escape(item.report_id) +
            '/trials.csv">trials CSV</a> · <a href="' + escape(item.report_id) +
            '.zip">offline ZIP</a></li>')
    (site_dir / "index.html").write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    site.OfflineHTML({item.report_id + "/index.html", item.report_id + "/records.json",
                      item.report_id + "/trials.csv", item.report_id + ".zip"}).feed(link)
    return item.report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.geo07-report-extension/1",
                          "reports": [catalogue_entry(args.source)]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")


if __name__ == "__main__":
    main()

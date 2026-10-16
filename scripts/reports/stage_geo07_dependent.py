"""Stage an immutable Pages route for the reviewed GEO-07 dependent-sum report."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import registered_reports as common

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "geo07_dependent_saved_renderer", ROOT / "scripts/reports/geo07_dependent/render_saved.py")
report = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(report)
_site_spec = importlib.util.spec_from_file_location("geo07_dependent_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(_site_spec)
assert _site_spec.loader is not None
_site_spec.loader.exec_module(site)

KIND = "geo07-registered-dependent-generator-sum"
SCOPE = "14 measured verified batches across two bounded public GeometryPort DependentSum fixtures; 2,000 fresh checked calls per batch"
LIMITS = ("Exploratory and inconclusive single-adapter observations; no comparator, limiter profile, speedup, "
          "application-scale claim or validated binary64 rounding enclosure")
PUBLISHERS = ("stage_geo07_dependent.py", "geo07_dependent/render_saved.py",
              "geo07_dependent/collect.py", "registered_reports.py")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publisher_digest(name: str) -> str:
    source = (ROOT / "scripts/reports" / name).read_bytes()
    return sha(source.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def read_json(path: Path) -> dict:
    return report.object_json(path.read_bytes())


def source_files(bundle: Path) -> set[str]:
    return report.saved_paths(bundle) | set(report.GENERATED)


def validate(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    report.render(bundle, check=True)
    files = source_files(bundle)
    require({str(path.relative_to(bundle)).replace("\\", "/") for path in bundle.rglob("*") if path.is_file()} == files and
            all(not path.is_symlink() for path in bundle.rglob("*")), "source report inventory changed")
    site.OfflineHTML(files | {"report-envelope.json", "publication-manifest.json"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    identity = {"schema": "csl.geo07-dependent-publication-identity/1",
                "source_report_id": bundle.name,
                "source_files": {name: sha((bundle / name).read_bytes()) for name in sorted(files)},
                "publisher": {name: publisher_digest(name) for name in PUBLISHERS}}
    report_id = "geo07-dependent-registered-" + common._digest(identity)
    record = read_json(bundle / "records.json")
    payload_hash = common._digest(record)
    return common.PublicationRecord(KIND, report_id, payload_hash, report.SOURCE,
                                    SCOPE, LIMITS, tuple(sorted(files)), record["schema"],
                                    payload_hash, bundle.name)


def public_artifacts(bundle: Path, item: common.PublicationRecord) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in item.files}
    footer = ('<p>Immutable publication <code>' + escape(item.report_id) +
              '</code>. <a href="report-envelope.json">Report envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    html = files["index.html"].decode("utf-8")
    require(html.count("</body>") == 1, "public page insertion point changed")
    files["index.html"] = html.replace("</body>", footer + "</body>").encode("utf-8")
    record = read_json(bundle / "records.json")
    files["report-envelope.json"] = report.collect.json_bytes({
        "schema": "csl.algorithm-report-envelope/1", "report_id": item.report_id,
        "report_kind": item.kind, "payload_schema": item.payload_schema,
        "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
        "source_commit": item.source_commit, "measured_scope": item.measured_scope,
        "evidence_limits": item.evidence_limits, "source_report_id": item.source_report_id,
        "payload": record})
    files["publication-manifest.json"] = report.collect.json_bytes({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": item.report_id, "report_kind": item.kind,
        "files": {name: sha(content) for name, content in sorted(files.items())}})
    return files


def public_zip(report_id: str, files: dict[str, bytes]) -> bytes:
    landing = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
               '<title>Offline GEO-07 dependent report</title></head><body>'
               '<h1>Offline GEO-07 dependent report</h1><a href="' + escape(report_id, quote=True) +
               '/index.html">Open registered dependent-sum report</a></body></html>\n').encode("utf-8")
    site.OfflineHTML({report_id + "/index.html"}).feed(landing.decode("utf-8"))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [("index.html", landing)] + [(report_id + "/" + name, files[name]) for name in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue()


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    archive = public_zip(item.report_id, public_artifacts(bundle, item))
    return {"report_id": item.report_id, "report_kind": item.kind,
            "source_report_id": item.source_report_id, "payload_schema": item.payload_schema,
            "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
            "source_commit": item.source_commit, "measured_scope": item.measured_scope,
            "evidence_limits": item.evidence_limits, "zip_sha256": sha(archive)}


def stage(catalogue_path: Path, site_dir: Path) -> str:
    catalogue_path, site_dir = Path(catalogue_path), Path(site_dir)
    catalogue = read_json(catalogue_path)
    require(catalogue.get("schema") == "csl.geo07-dependent-report-extension/1" and
            isinstance(catalogue.get("reports"), list) and len(catalogue["reports"]) == 1,
            "GEO-07 dependent publication catalogue changed")
    require(catalogue["reports"][0].get("source_report_id") == report.REPORT_ID,
            "GEO-07 dependent source report changed")
    bundle = catalogue_path.parent / report.REPORT_ID
    expected = catalogue_entry(bundle)
    require(catalogue["reports"][0] == expected, "catalogue differs from saved source")
    item = validate(bundle)
    files = public_artifacts(bundle, item)
    archive = public_zip(item.report_id, files)
    require(sha(archive) == expected["zip_sha256"], "public ZIP hash changed")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    destination = site_dir / item.report_id
    require(site_dir.is_dir() and not site_dir.is_symlink() and
            not destination.exists() and not (site_dir / (item.report_id + ".zip")).exists(),
            "public route must be fresh")
    destination.mkdir()
    for name, content in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    require(common.validate_publication_manifest(destination, expected),
            "public manifest validation failed")
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    require(index.count("</ul>") == 1 and item.report_id not in index,
            "site index insertion point changed")
    link = ('<li><a href="' + escape(item.report_id) + '/index.html">' + escape(item.report_id) +
            '</a> — ' + escape(SCOPE) + '; limits: ' + escape(LIMITS) +
            ' · <a href="' + escape(item.report_id) + '/records.json">saved JSON</a>'
            ' · <a href="' + escape(item.report_id) + '/trials.csv">trials CSV</a>'
            ' · <a href="' + escape(item.report_id) + '.zip">offline ZIP</a></li>')
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
        print(json.dumps({"schema": "csl.geo07-dependent-report-extension/1",
                          "reports": [catalogue_entry(args.source)]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")


if __name__ == "__main__":
    main()

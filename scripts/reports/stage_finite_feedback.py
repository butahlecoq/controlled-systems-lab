"""Stage the reviewed finite-feedback saved report at a content-bound Pages route."""
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
    "finite_feedback_saved_renderer", ROOT / "scripts/reports/finite_feedback/render_saved.py")
report = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(report)
_site_spec = importlib.util.spec_from_file_location("finite_feedback_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(_site_spec)
assert _site_spec.loader is not None
_site_spec.loader.exec_module(site)

KIND = "finite-feedback-registered-port"
SCOPE = "28 verified registered-port calls, seven per four authored finite games"
LIMITS = ("Exploratory and inconclusive single-adapter timings; concurrent work not quantified; "
          "all winning flags and selected action cells checked, other action-tensor cells unchecked; "
          "no comparator, source-mapped limiter, speedup, continuous-state, partial-observation, "
          "physical-model, or global causal minimax claim")
FILES = report.RAW_FILES | report.RENDERED_FILES
PUBLISHERS = ("stage_finite_feedback.py", "finite_feedback/render_saved.py",
              "finite_feedback/collect.py", "finite_feedback/capture.py",
              "registered_reports.py")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def publisher_digest(name: str) -> str:
    return digest((ROOT / "scripts/reports" / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def validate(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    report.collect.require(bundle.name.startswith("finite-feedback-") and
                           {path.name for path in bundle.iterdir()} == FILES and
                           all(path.is_file() and not path.is_symlink() for path in bundle.iterdir()),
                           "finite-feedback source inventory differs")
    record = report.render(bundle, check=True)
    site.OfflineHTML(set(FILES)).feed((bundle / "index.html").read_text(encoding="utf-8"))
    identity = {"schema": "csl.finite-feedback-publication-identity/1",
                "source_report_id": bundle.name,
                "source_files": {name: digest((bundle / name).read_bytes()) for name in sorted(FILES)},
                "publisher_files": {name: publisher_digest(name) for name in PUBLISHERS}}
    public_id = "finite-feedback-registered-" + common._digest(identity)
    payload_hash = common._digest(record)
    return common.PublicationRecord(KIND, public_id, payload_hash, record["source_commit"],
                                    SCOPE, LIMITS, tuple(sorted(FILES)), record["schema"],
                                    payload_hash, bundle.name)


def public_files(bundle: Path, item: common.PublicationRecord) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in item.files}
    page = files["index.html"].decode("utf-8")
    report.collect.require(page.count("</body>") == 1, "report page insertion point differs")
    footer = ('<p>Publication <code>' + escape(item.report_id) + '</code>. '
              '<a href="report-envelope.json">Versioned envelope</a> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    files["index.html"] = page.replace("</body>", footer + "</body>").encode()
    record = report.collect.read_json(bundle / "records.json")
    files["report-envelope.json"] = report.collect.encoded({
        "schema": "csl.algorithm-report-envelope/1", "report_id": item.report_id,
        "report_kind": item.kind, "payload_schema": item.payload_schema,
        "payload_sha256": item.payload_sha256, "native_payload_sha256": item.native_payload_sha256,
        "source_commit": item.source_commit, "measured_scope": item.measured_scope,
        "evidence_limits": item.evidence_limits, "source_report_id": item.source_report_id,
        "payload": record})
    files["publication-manifest.json"] = report.collect.encoded({
        "schema": "csl.algorithm-report-publication-manifest/1", "report_id": item.report_id,
        "report_kind": item.kind,
        "files": {name: digest(files[name]) for name in sorted(files)}})
    site.OfflineHTML(set(files)).feed(files["index.html"].decode())
    return files


def public_zip(public_id: str, files: dict[str, bytes]) -> bytes:
    landing = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline finite feedback</title>'
               '<p><a href="' + escape(public_id, quote=True) + '/index.html">Open saved report</a></p></html>\n').encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [("index.html", landing)] + [(public_id + "/" + key, files[key]) for key in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue()


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    archive = public_zip(item.report_id, public_files(bundle, item))
    return {"report_id": item.report_id, "report_kind": item.kind,
            "source_report_id": item.source_report_id,
            "payload_schema": item.payload_schema, "payload_sha256": item.payload_sha256,
            "native_payload_sha256": item.native_payload_sha256,
            "source_commit": item.source_commit, "measured_scope": item.measured_scope,
            "evidence_limits": item.evidence_limits, "zip_sha256": digest(archive)}


def stage(catalogue_path: Path, site_dir: Path) -> str:
    catalogue_path, site_dir = Path(catalogue_path), Path(site_dir)
    catalogue = report.collect.read_json(catalogue_path)
    report.collect.require(catalogue.get("schema") == "csl.finite-feedback-report-extension/1" and
                           isinstance(catalogue.get("reports"), list) and len(catalogue["reports"]) == 1,
                           "finite-feedback extension catalogue differs")
    bundle = catalogue_path.parent / catalogue["reports"][0]["source_report_id"]
    expected = catalogue_entry(bundle)
    report.collect.require(catalogue["reports"] == [expected], "catalogue differs from saved source")
    item = validate(bundle)
    files = public_files(bundle, item)
    archive = public_zip(item.report_id, files)
    report.collect.require(digest(archive) == expected["zip_sha256"], "public ZIP differs")
    destination = site_dir / item.report_id
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists() and not (site_dir / (item.report_id + ".zip")).exists(),
                           "public route must be a fresh staged destination")
    destination.mkdir()
    for name, content in files.items():
        (destination / name).write_bytes(content)
    report.collect.require(common.validate_publication_manifest(destination, expected),
                           "public manifest validation failed")
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and item.report_id not in index,
                           "site index insertion point differs")
    link = ('<li><a href="' + escape(item.report_id) + '/index.html">' + escape(item.report_id) +
            '</a> — ' + escape(SCOPE) + '; limits: ' + escape(LIMITS) +
            ' · <a href="' + escape(item.report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(item.report_id) + '/trials.csv">trials CSV</a>'
            ' · <a href="' + escape(item.report_id) + '.zip">offline ZIP</a></li>')
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
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
        print(json.dumps({"schema": "csl.finite-feedback-report-extension/1",
                          "reports": [catalogue_entry(args.source)]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")


if __name__ == "__main__":
    main()

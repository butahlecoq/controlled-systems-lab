from __future__ import annotations

import argparse
import csv
from html import escape
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import statistics
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
site_spec = importlib.util.spec_from_file_location("ext04_affine_site", ROOT / "scripts/reports/site.py")
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_entry(bundle: Path) -> dict:
    bundle = Path(bundle)
    records = read_json(bundle / "records.json")
    report_id = records.get("report_id")
    if (not isinstance(report_id, str) or
            re.fullmatch(r"ext04-affine-synthesis-[0-9a-f]{16}", report_id) is None or
            bundle.name != report_id or bundle.is_symlink() or not bundle.is_dir() or
            records.get("schema") != "csl.ext04-affine-synthesis-report/1"):
        raise ValueError("EXT-04 affine-synthesis report identity differs")
    files = {path.name: sha(path.read_bytes()) for path in sorted(bundle.iterdir())
             if path.is_file()}
    expected = {"driver.cpp", "environment.json", report_id + ".zip", "fixture.json",
                "index.html", "manifest.json", "records.json", "release-build-log.txt",
                "renderer.py", "result.json", "smoke.txt", "summary.csv",
                "synthesis-2d.svg", "trials.jsonl"}
    if set(files) != expected:
        raise ValueError("EXT-04 affine-synthesis file inventory differs")
    manifest = read_json(bundle / "manifest.json")
    if (manifest.get("schema") != "csl.ext04-affine-synthesis-manifest/1" or
            manifest.get("report_id") != report_id or
            manifest.get("files") != {name: digest for name, digest in files.items()
                if name not in {report_id + ".zip", "manifest.json"}}):
        raise ValueError("native report manifest differs")
    source_commit = records.get("source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("measured source identity differs")
    for path_name, record_key in (("driver.cpp", "driver_sha256"),
                                  ("renderer.py", "renderer_sha256"),
                                  ("release-build-log.txt", "release_build_log_sha256")):
        if files[path_name] != records.get(record_key):
            raise ValueError("retained source artifact hash differs: " + path_name)
    if files["smoke.txt"] != records.get("smoke_sha256"):
        raise ValueError("retained smoke output hash differs")

    trials = [json.loads(line) for line in
              (bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(trials) != 8:
        raise ValueError("one warmup and seven measurement rows are required")
    render_spec = importlib.util.spec_from_file_location("saved_affine_renderer", bundle / "renderer.py")
    if render_spec is None or render_spec.loader is None:
        raise ValueError("saved data renderer cannot load")
    renderer = importlib.util.module_from_spec(render_spec)
    render_spec.loader.exec_module(renderer)
    fixture = read_json(bundle / "fixture.json")
    if fixture != renderer.fixture() or records.get("environment") != read_json(bundle / "environment.json"):
        raise ValueError("saved fixture or environment differs from the report")
    for index, row in enumerate(trials):
        if (row.get("schema") != "csl.ext04-affine-synthesis-trial/1" or
                row.get("round") != index or row.get("warmup") is not (index == 0) or
                row.get("batch") != 100 or row.get("status") != "passed" or
                row.get("workspace_reused") is not True or row.get("generators_per_call") != 8 or
                row.get("fixture") != fixture or
                row.get("timing_scope") != records.get("timing_scope") or
                row.get("feasibility_tolerance") != fixture["feasibility_tolerance"] or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] <= 0):
            raise ValueError("raw measurement row identity differs")
        renderer.check_result(row.get("result", {}))
    saved_result = read_json(bundle / "result.json")
    if saved_result != trials[-1]["result"]:
        raise ValueError("saved result differs from the last measured outcome")
    smoke_text = (bundle / "smoke.txt").read_text(encoding="utf-8").lstrip()
    smoke_result, smoke_end = json.JSONDecoder().raw_decode(smoke_text)
    if smoke_text[smoke_end:].strip() != "affine-synthesis smoke passed":
        raise ValueError("standalone smoke marker differs")
    renderer.check_result(smoke_result)
    measured = [row["elapsed_ns"] for row in trials[1:]]
    if (records.get("measured_batches") != 7 or records.get("warmups_excluded") != 1 or
            records.get("batch_size") != 100 or records.get("failures") != 0 or
            records.get("median_batch_ns") != statistics.median(measured) or
            records.get("minimum_batch_ns") != min(measured) or
            records.get("maximum_batch_ns") != max(measured) or
            records.get("median_ns_per_call") != statistics.median(measured) / 100):
        raise ValueError("report timing summary differs from raw trials")
    with (bundle / "summary.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 7 or any(row != {
            "round": str(trial["round"]), "batch_calls": "100",
            "elapsed_ns": str(trial["elapsed_ns"]),
            "ns_per_call": str(trial["elapsed_ns"] / 100), "status": "passed"}
            for row, trial in zip(rows, trials[1:])):
        raise ValueError("summary CSV differs from raw rows")
    archive_path = bundle / (report_id + ".zip")
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        expected_archive = set(files) - {report_id + ".zip"}
        if (archive.testzip() is not None or names != expected_archive or
                any(archive.read(name) != (bundle / name).read_bytes() for name in names)):
            raise ValueError("native offline report ZIP is invalid")
    site.OfflineHTML(expected - {"manifest.json"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    return {
        "report_id": report_id,
        "source_report_id": report_id,
        "source_commit": source_commit,
        "payload_sha256": files["records.json"],
        "measured_scope": "Seven 100-call batches of one-stage affine policy synthesis with eight joint generators per call",
        "evidence_limits": records["evidence_limits"],
        "files": files,
        "publisher_sha256": sha(Path(__file__).read_bytes()),
    }


def public_files(bundle: Path, entry: dict) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in entry["files"]}
    report_id = entry["report_id"]
    page = files["index.html"].decode("utf-8")
    if page.count("</body>") != 1:
        raise ValueError("report page footer insertion point differs")
    footer = ('<p>Published report <code>' + escape(report_id) +
        '</code>. <a href="environment.json">Environment</a> · '
        '<a href="' + escape(report_id) + '.zip">Source offline ZIP</a> · '
        '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    files["index.html"] = page.replace("</body>", footer + "</body>").encode("utf-8")
    envelope = {
        "schema": "csl.algorithm-report-envelope/1",
        "report_id": report_id,
        "report_kind": "ext04-affine-policy-synthesis",
        "payload_schema": "csl.ext04-affine-synthesis-report/1",
        "payload_sha256": entry["payload_sha256"],
        "source_commit": entry["source_commit"],
        "measured_scope": entry["measured_scope"],
        "evidence_limits": entry["evidence_limits"],
        "source_report_id": report_id,
        "payload": read_json(bundle / "records.json"),
    }
    files["report-envelope.json"] = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode()
    files["publication-manifest.json"] = (json.dumps({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": report_id,
        "files": {name: sha(content) for name, content in sorted(files.items())},
    }, indent=2, sort_keys=True) + "\n").encode()
    return files


def archive(report_id: str, files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zipped:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(report_id + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, content)
    return buffer.getvalue()


def entry_for(bundle: Path) -> dict:
    entry = source_entry(bundle)
    files = public_files(bundle, entry)
    return {**entry,
            "public_files_sha256": {name: sha(content) for name, content in sorted(files.items())},
            "zip_sha256": sha(archive(entry["report_id"], files))}


def stage(catalog_path: Path, site_dir: Path) -> str:
    catalog = read_json(catalog_path)
    if (catalog.get("schema") != "csl.ext04-affine-synthesis-publications/1" or
            len(catalog.get("reports", [])) != 1):
        raise ValueError("EXT-04 affine-synthesis publication catalogue differs")
    entry = catalog["reports"][0]
    bundle = catalog_path.parent / entry["source_report_id"]
    if entry != entry_for(bundle):
        raise ValueError("publication catalogue differs from the report bundle")
    files = public_files(bundle, entry)
    zip_bytes = archive(entry["report_id"], files)
    site_dir = Path(site_dir)
    dest = site_dir / entry["report_id"]
    zip_dest = site_dir / (entry["report_id"] + ".zip")
    if (not site_dir.is_dir() or site_dir.is_symlink() or dest.exists() or zip_dest.exists()):
        raise ValueError("report destination must be fresh")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    dest.mkdir()
    for name, content in files.items():
        (dest / name).write_bytes(content)
    zip_dest.write_bytes(zip_bytes)
    index = site_dir / "index.html"
    text = index.read_text(encoding="utf-8")
    if text.count("</ul>") != 1 or entry["report_id"] in text:
        raise ValueError("algorithm-report index insertion point differs")
    link = ('<li><a href="' + escape(entry["report_id"]) +
        '/index.html">EXT-04 affine policy synthesis</a> — ' +
        escape(entry["measured_scope"]) + '; limits: ' +
        escape("; ".join(entry["evidence_limits"])) + ' · <a href="' +
        escape(entry["report_id"]) + '/records.json">raw record</a> · <a href="' +
        escape(entry["report_id"]) + '/trials.jsonl">raw trials</a> · <a href="' +
        escape(entry["report_id"]) + '.zip">offline ZIP</a></li>')
    site.OfflineHTML({entry["report_id"] + "/index.html",
                      entry["report_id"] + "/records.json",
                      entry["report_id"] + "/trials.jsonl",
                      entry["report_id"] + ".zip"}).feed(link)
    index.write_text(text.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return entry["report_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate and stage the saved EXT-04 affine-synthesis report.")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.ext04-affine-synthesis-publications/1",
                          "reports": [entry_for(args.source)]}, indent=2, sort_keys=True))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")

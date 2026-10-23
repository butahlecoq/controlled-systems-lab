"""Validate and stage the saved EXT-04 continuous-policy report on Pages."""
from __future__ import annotations

import argparse
import csv
from html import escape
import hashlib
import json
from pathlib import Path
import zipfile

import importlib.util
import io
import statistics
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ext04_continuous_site", ROOT / "scripts/reports/site.py")
site = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(site)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_entry(bundle: Path) -> dict:
    bundle = Path(bundle)
    records = read_json(bundle / "records.json")
    report_id = records["report_id"]
    if (bundle.name != report_id or records.get("schema") != "csl.ext04-continuous-policy-report/1" or
            not bundle.is_dir() or bundle.is_symlink()):
        raise ValueError("EXT-04 continuous report identity differs")
    files = {path.name: sha(path.read_bytes()) for path in sorted(bundle.iterdir())
             if path.is_file() and path.name != "publication-manifest.json"}
    expected = {"driver.cpp", "example-2d.svg", report_id + ".zip", "index.html",
                "manifest.json", "records.json", "release-build-log.txt", "renderer.py",
                "summary.csv", "trials.jsonl"}
    if set(files) != expected:
        raise ValueError("EXT-04 continuous report inventory differs")
    manifest = read_json(bundle / "manifest.json")
    if manifest.get("files") != {name: digest for name, digest in files.items()
                                  if name not in {report_id + ".zip", "manifest.json"}}:
        raise ValueError("native report manifest differs")
    if sha((bundle / "driver.cpp").read_bytes()) != records.get("harness_sha256"):
        raise ValueError("retained driver hash differs from report record")
    if sha((bundle / "renderer.py").read_bytes()) != records.get("renderer_sha256"):
        raise ValueError("retained saved-data renderer hash differs from report record")
    if sha((bundle / "release-build-log.txt").read_bytes()) != records.get("release_build_log_sha256"):
        raise ValueError("retained build log hash differs from report record")
    expected_result = [
        {"initial": [0, 0], "action": [0], "terminal": [0, 0], "action_margin": 1.25},
        {"initial": [0, 1], "action": [0], "terminal": [1, 1], "action_margin": 1.25},
        {"initial": [1, 0], "action": [1], "terminal": [1.5, 1], "action_margin": 0.25},
        {"initial": [1, 1], "action": [1], "terminal": [2.5, 2], "action_margin": 0.25},
    ]
    trials = [json.loads(line) for line in (bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()]
    if (len(trials) != 8 or any(row.get("schema") != "csl.ext04-continuous-policy-trial/1" or
            row.get("round") != index or row.get("warmup") != (index == 0) or
            row.get("batch") != 5000 or row.get("generators_per_call") != 4 or
            row.get("feasibility_tolerance") != 1e-9 or row.get("fixture_reused") is not True or
            row.get("outer_workers") != 1 or row.get("result") != expected_result or
            row.get("timing_scope") != records.get("timing_scope") or
            row.get("status") != "passed" or row.get("assurance") != "numerical" or
            row.get("feasibility") != "within_tolerance" or
            type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 20_000_000
            for index, row in enumerate(trials))):
        raise ValueError("saved raw trial outcomes or counts differ")
    measured = [row["elapsed_ns"] for row in trials[1:]]
    if (records.get("measured_batches") != 7 or records.get("successes") != 7 or
            records.get("failures") != 0 or records.get("warmups_excluded") != 1 or
            records.get("median_batch_ns") != statistics.median(measured) or
            records.get("min_batch_ns") != min(measured) or
            records.get("max_batch_ns") != max(measured) or
            records.get("median_ns_per_call") != statistics.median(measured) / 5000):
        raise ValueError("saved timing summary differs from raw trials")
    with (bundle / "summary.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != 7 or any(
            row != {"round": str(trial["round"]), "batch_calls": "5000",
                    "elapsed_ns": str(trial["elapsed_ns"]),
                    "ns_per_call": str(trial["elapsed_ns"] / 5000), "status": "passed"}
            for row, trial in zip(csv_rows, trials[1:])):
        raise ValueError("saved CSV differs from raw trial rows")
    renderer_spec = importlib.util.spec_from_file_location(
        "saved_ext04_continuous_renderer", bundle / "renderer.py")
    if renderer_spec is None or renderer_spec.loader is None:
        raise ValueError("saved renderer could not be loaded")
    saved_renderer = importlib.util.module_from_spec(renderer_spec)
    renderer_spec.loader.exec_module(saved_renderer)
    with tempfile.TemporaryDirectory(prefix="ext04-continuous-render-") as temporary:
        replayed = Path(temporary) / report_id
        saved_renderer.render(
            trials_path=bundle / "trials.jsonl",
            build_log_path=bundle / "release-build-log.txt",
            example_path=bundle / "example-2d.svg",
            out=replayed,
            source_commit=records["source_commit"],
            collected_utc=records["collected_utc"],
            load_observation=records["load_observation_before_build_and_measurement"],
            driver_path=bundle / "driver.cpp")
        if ({path.name for path in replayed.iterdir()} != expected or
                any((replayed / name).read_bytes() != (bundle / name).read_bytes()
                    for name in expected)):
            raise ValueError("saved report does not regenerate byte-for-byte")
    allowed = set(expected)
    site.OfflineHTML(allowed).feed((bundle / "index.html").read_text(encoding="utf-8"))
    records_sha = sha((bundle / "records.json").read_bytes())
    return {
        "report_id": report_id,
        "source_report_id": report_id,
        "source_commit": records["source_commit"],
        "payload_sha256": records_sha,
        "measured_scope": ("Seven verified 5,000-call batches of continuous affine policy evaluation; "
                           "four supplied joint generators per call"),
        "evidence_limits": records["evidence_limits"],
        "files": files,
        "publisher_sha256": sha(Path(__file__).read_bytes()),
    }


def public_files(bundle: Path, entry: dict) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in entry["files"]}
    page = files["index.html"].decode("utf-8")
    if page.count("</body>") != 1:
        raise ValueError("continuous report page footer point differs")
    footer = ('<p>Published report <code>' + escape(entry["report_id"]) +
              '</code>. <a href="publication-manifest.json">Publication manifest</a>.</p>')
    files["index.html"] = page.replace("</body>", footer + "</body>").encode("utf-8")
    envelope = {
        "schema": "csl.algorithm-report-envelope/1",
        "report_id": entry["report_id"],
        "report_kind": "ext04-continuous-policy",
        "payload_schema": "csl.ext04-continuous-policy-report/1",
        "payload_sha256": entry["payload_sha256"],
        "source_commit": entry["source_commit"],
        "measured_scope": entry["measured_scope"],
        "evidence_limits": entry["evidence_limits"],
        "source_report_id": entry["source_report_id"],
        "payload": read_json(bundle / "records.json"),
    }
    files["report-envelope.json"] = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode()
    manifest = {name: sha(content) for name, content in sorted(files.items())}
    files["publication-manifest.json"] = (json.dumps({
        "schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": entry["report_id"], "files": manifest}, indent=2, sort_keys=True) + "\n").encode()
    return files


def public_zip(report_id: str, files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [(report_id + "/" + name, files[name]) for name in sorted(files)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buf.getvalue()


def entry_for(bundle: Path) -> dict:
    entry = source_entry(bundle)
    files = public_files(bundle, entry)
    archive = public_zip(entry["report_id"], files)
    return {**entry, "public_files_sha256": {name: sha(content)
                                            for name, content in sorted(files.items())},
            "zip_sha256": sha(archive)}


def stage(catalog_path: Path, site_dir: Path) -> str:
    catalog = read_json(catalog_path)
    if catalog.get("schema") != "csl.ext04-continuous-publications/1" or len(catalog.get("reports", [])) != 1:
        raise ValueError("EXT-04 continuous publication catalog differs")
    entry = catalog["reports"][0]
    bundle = catalog_path.parent / entry["source_report_id"]
    expected = entry_for(bundle)
    if entry != expected:
        raise ValueError("continuous publication catalog differs from bundle")
    files = public_files(bundle, entry)
    archive = public_zip(entry["report_id"], files)
    site_dir = Path(site_dir)
    dest = site_dir / entry["report_id"]
    zip_dest = site_dir / (entry["report_id"] + ".zip")
    if not site_dir.is_dir() or site_dir.is_symlink() or dest.exists() or zip_dest.exists():
        raise ValueError("continuous report destination must be fresh")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    dest.mkdir()
    for name, content in files.items():
        (dest / name).write_bytes(content)
    zip_dest.write_bytes(archive)
    index = site_dir / "index.html"
    text = index.read_text(encoding="utf-8")
    if text.count("</ul>") != 1 or entry["report_id"] in text:
        raise ValueError("algorithm-report index insertion point differs")
    scope = escape(entry["measured_scope"])
    limits = escape("; ".join(entry["evidence_limits"]))
    link = ('<li><a href="' + escape(entry["report_id"]) + '/index.html">EXT-04 continuous policy evaluation</a> — ' +
            scope + '; limits: ' + limits + ' · <a href="' + escape(entry["report_id"]) +
            '/records.json">raw record</a> · <a href="' + escape(entry["report_id"]) +
            '/trials.jsonl">raw trials</a> · <a href="' + escape(entry["report_id"]) +
            '.zip">offline ZIP</a></li>')
    site.OfflineHTML({entry["report_id"] + "/index.html",
                      entry["report_id"] + "/records.json",
                      entry["report_id"] + "/trials.jsonl",
                      entry["report_id"] + ".zip"}).feed(link)
    index.write_text(text.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return entry["report_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.ext04-continuous-publications/1",
                          "reports": [entry_for(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")

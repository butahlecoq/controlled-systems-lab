"""Validate and stage the saved EXT-04 joint H-domain policy report."""
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
spec = importlib.util.spec_from_file_location("ext04_h_site", ROOT / "scripts/reports/site.py")
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
    report_id = records.get("report_id")
    if (not isinstance(report_id, str) or
            re.fullmatch(r"ext04-h-policy-[0-9a-f]{16}", report_id) is None or
            bundle.name != report_id or bundle.is_symlink() or not bundle.is_dir() or
            records.get("schema") != "csl.ext04-h-policy-report/1"):
        raise ValueError("EXT-04 H-policy report identity differs")
    files = {path.name: sha(path.read_bytes()) for path in sorted(bundle.iterdir())
             if path.is_file()}
    expected = {"driver.cpp", "environment.json", report_id + ".zip", "figure_style.py",
                "h-domain-2d.png", "h-domain-2d.svg", "index.html", "manifest.json",
                "plot.py", "records.json", "release-build-log.txt", "renderer.py",
                "report_data.py", "summary.csv", "trials.jsonl"}
    if set(files) != expected:
        raise ValueError("EXT-04 H-policy report inventory differs")
    source_commit = records.get("source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("measured source identity differs")
    manifest = read_json(bundle / "manifest.json")
    if (manifest.get("schema") != "csl.ext04-h-policy-manifest/1" or
            manifest.get("report_id") != report_id or manifest.get("source_commit") != source_commit or
            manifest.get("files") != {name: digest for name, digest in files.items()
                if name not in {report_id + ".zip", "manifest.json"}}):
        raise ValueError("native report manifest differs")
    for path_name, record_key in (("driver.cpp", "driver_sha256"),
                                  ("renderer.py", "renderer_sha256"),
                                  ("release-build-log.txt", "build_log_sha256")):
        if files[path_name] != records["artifacts"].get(record_key):
            raise ValueError("retained report source hash differs: " + path_name)
    for path_name, record_key in (("figure_style.py", "figure_style_sha256"),
                                  ("plot.py", "plot_adapter_sha256"),
                                  ("report_data.py", "report_data_sha256")):
        if files[path_name] != records["artifacts"].get(record_key):
            raise ValueError("retained report figure helper hash differs: " + path_name)
    if files["environment.json"] != records["artifacts"].get("environment_sha256"):
        raise ValueError("retained environment hash differs")
    if (records.get("figure", {}).get("style") != "csl-report-quantitative-v1" or
            records["figure"].get("matplotlib") != "3.11.2" or
            records["figure"].get("timing_included") is not False or
            not (bundle / "h-domain-2d.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("quantitative figure provenance or PNG asset differs")

    trials = [json.loads(line) for line in
              (bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(trials) != 8:
        raise ValueError("one warmup and seven measurement rows are required")
    expected_maxima = [1.0, 1.0, 0.1, 0.1, 1.1, 1.1]
    for index, row in enumerate(trials):
        if (row.get("schema") != "csl.ext04-h-policy-trial/1" or
                row.get("round") != index or row.get("warmup") is not (index == 0) or
                row.get("batch") != 100 or row.get("status") != "passed" or
                row.get("assurance") != "numerical" or
                row.get("feasibility") != "within_tolerance" or
                row.get("safety_rows") != 6 or row.get("lp_solves_per_call") != 7 or
                row.get("workspace_reused") is not True or
                row.get("timing_scope") != records.get("timing_scope") or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 20_000_000):
            raise ValueError("raw H-policy measurement identity differs")
        result = row["result"]
        maxima = [entry["support_upper_bound"] for entry in result["constraints"]]
        if (len(maxima) != len(expected_maxima) or
                any(abs(value-target) > 1e-7 for value, target in zip(maxima, expected_maxima)) or
                abs(result["domain_witness"][1] - 0.1*result["domain_witness"][0]) > 1e-8):
            raise ValueError("raw H-policy result or correlated witness differs")
    measured = [row["elapsed_ns"] for row in trials[1:]]
    if (records.get("measured_batches") != 7 or records.get("successes") != 7 or
            records.get("failures") != 0 or records.get("warmups_excluded") != 1 or
            records.get("batch_size") != 100 or
            records.get("median_batch_ns") != statistics.median(measured) or
            records.get("min_batch_ns") != min(measured) or
            records.get("max_batch_ns") != max(measured) or
            records.get("median_ns_per_call") != statistics.median(measured)/100):
        raise ValueError("report timing summary differs from raw trials")
    with (bundle / "summary.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 7 or any(row != {
            "round": str(trial["round"]), "batch_calls": "100",
            "lp_solves_per_call": "7", "elapsed_ns": str(trial["elapsed_ns"]),
            "ns_per_call": str(trial["elapsed_ns"]/100), "status": "passed"}
            for row, trial in zip(rows, trials[1:])):
        raise ValueError("summary CSV differs from raw trials")
    with zipfile.ZipFile(bundle / (report_id + ".zip")) as archive:
        names = set(archive.namelist())
        expected_archive = set(files) - {report_id + ".zip"}
        if (archive.testzip() is not None or names != expected_archive or
                any(archive.read(name) != (bundle / name).read_bytes() for name in names)):
            raise ValueError("native offline report ZIP differs")

    renderer_spec = importlib.util.spec_from_file_location("saved_h_policy_renderer", bundle / "renderer.py")
    if renderer_spec is None or renderer_spec.loader is None:
        raise ValueError("saved report renderer cannot load")
    renderer = importlib.util.module_from_spec(renderer_spec)
    renderer_spec.loader.exec_module(renderer)
    with tempfile.TemporaryDirectory(prefix="ext04-h-policy-render-") as temporary:
        regenerated = Path(temporary) / report_id
        renderer.render(trials_path=bundle / "trials.jsonl",
            build_log_path=bundle / "release-build-log.txt",
            environment_path=bundle / "environment.json", out=regenerated,
            source_commit=source_commit, collected_utc=records["collected_utc"],
            driver_path=bundle / "driver.cpp")
        if ({path.name for path in regenerated.iterdir()} != expected or any(
                (regenerated / name).read_bytes() != (bundle / name).read_bytes()
                for name in expected)):
            raise ValueError("saved report does not regenerate byte-for-byte")
    site.OfflineHTML(expected - {"manifest.json"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    return {"report_id": report_id, "source_report_id": report_id,
        "source_commit": source_commit, "payload_sha256": files["records.json"],
        "measured_scope": "Seven verified 100-call batches of joint H-domain affine policy evaluation; six safety rows and seven LP solves per call",
        "evidence_limits": records["evidence_limits"], "files": files,
        "publisher_sha256": sha(Path(__file__).read_bytes())}


def public_files(bundle: Path, entry: dict) -> dict[str, bytes]:
    files = {name: (bundle / name).read_bytes() for name in entry["files"]}
    report_id = entry["report_id"]
    page = files["index.html"].decode("utf-8")
    footer = ('<p>Published report <code>' + escape(report_id) +
        '</code>. <a href="publication-manifest.json">Publication manifest</a>.</p>')
    if page.count("</body>") != 1:
        raise ValueError("report page footer insertion point differs")
    files["index.html"] = page.replace("</body>", footer + "</body>").encode("utf-8")
    files["report-envelope.json"] = (json.dumps({
        "schema":"csl.algorithm-report-envelope/1", "report_id":report_id,
        "report_kind":"ext04-h-domain-policy-evaluation",
        "payload_schema":"csl.ext04-h-policy-report/1",
        "payload_sha256":entry["payload_sha256"], "source_commit":entry["source_commit"],
        "measured_scope":entry["measured_scope"], "evidence_limits":entry["evidence_limits"],
        "source_report_id":report_id, "payload":read_json(bundle/"records.json")},
        indent=2, sort_keys=True)+"\n").encode()
    files["publication-manifest.json"] = (json.dumps({
        "schema":"csl.algorithm-report-publication-manifest/1", "report_id":report_id,
        "files":{name:sha(content) for name, content in sorted(files.items())}},
        indent=2, sort_keys=True)+"\n").encode()
    return files


def public_zip(report_id: str, files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(report_id + "/" + name, date_time=(2026,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def entry_for(bundle: Path) -> dict:
    entry = source_entry(bundle)
    files = public_files(bundle, entry)
    return {**entry, "public_files_sha256":{name:sha(data) for name,data in sorted(files.items())},
        "zip_sha256":sha(public_zip(entry["report_id"], files))}


def stage(catalog_path: Path, site_dir: Path) -> str:
    catalog = read_json(catalog_path)
    if (catalog.get("schema") != "csl.ext04-h-policy-publications/1" or
            len(catalog.get("reports", [])) != 1):
        raise ValueError("EXT-04 H-policy publication catalog differs")
    entry = catalog["reports"][0]
    bundle = catalog_path.parent / entry["source_report_id"]
    if entry != entry_for(bundle):
        raise ValueError("publication catalog differs from the report bundle")
    files = public_files(bundle, entry)
    archive = public_zip(entry["report_id"], files)
    site_dir = Path(site_dir)
    dest = site_dir / entry["report_id"]
    zip_dest = site_dir / (entry["report_id"] + ".zip")
    if not site_dir.is_dir() or site_dir.is_symlink() or dest.exists() or zip_dest.exists():
        raise ValueError("report destination must be fresh")
    site.OfflineHTML(set(files)).feed(files["index.html"].decode("utf-8"))
    dest.mkdir()
    for name, content in files.items():
        (dest/name).write_bytes(content)
    zip_dest.write_bytes(archive)
    index = site_dir / "index.html"
    page = index.read_text(encoding="utf-8")
    report_id = entry["report_id"]
    if page.count("</ul>") != 1 or report_id in page:
        raise ValueError("algorithm-report index insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">EXT-04 joint H-domain policy evaluation</a> — ' +
        escape(entry["measured_scope"]) + '; limits: ' + escape("; ".join(entry["evidence_limits"])) +
        ' · <a href="' + escape(report_id) + '/records.json">raw record</a> · <a href="' +
        escape(report_id) + '/trials.jsonl">raw trials</a> · <a href="' + escape(report_id) +
        '.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id+"/index.html", report_id+"/records.json",
        report_id+"/trials.jsonl", report_id+".zip"}).feed(link)
    index.write_text(page.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema":"csl.ext04-h-policy-publications/1",
            "reports":[entry_for(args.source)]}, indent=2, sort_keys=True))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")

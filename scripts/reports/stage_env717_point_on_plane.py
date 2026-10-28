"""Stage the independently verified PointOnThePlane pilot on Pages."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-point-on-plane-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_point_on_plane.py"
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
spec = importlib.util.spec_from_file_location("env717_point_on_plane_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)

FILES = ("README.md", "capture.json", "environment.json", "figure-data.json",
         "index.html", "projections.svg", "result.json", "SHA256SUMS")


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inputs(source: Path) -> tuple[dict[str, bytes], dict, dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("environment report source must be a directory")
    if {path.name for path in source.iterdir()} != set(FILES):
        raise ValueError("environment report file inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums: dict[str, str] = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate report checksum")
        sums[name] = sha
    expected_sums = {name: digest(content) for name, content in files.items()
                     if name != "SHA256SUMS"}
    if sums != expected_sums:
        raise ValueError("report checksum mismatch")
    try:
        result = json.loads(files["result.json"])
        figure_data = json.loads(files["figure-data.json"])
        environment = json.loads(files["environment.json"])
        capture = json.loads(files["capture.json"])
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("report contains invalid JSON") from error
    if result.get("source_repository_commit") != SOURCE_COMMIT:
        raise ValueError("upstream source commit differs")
    if result.get("source_file_blob") != checker.SOURCE_BLOB:
        raise ValueError("upstream source file identity differs")
    try:
        analysis = checker.verify(result)
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        raise ValueError("independent source replay rejected saved result") from error
    if figure_data != checker.figure_data_record(analysis):
        raise ValueError("saved projection data differs from independent replay")
    if files["projections.svg"].decode("utf-8") != checker.svg_figure(analysis):
        raise ValueError("saved SVG differs from independently derived projections")
    if files["index.html"].decode("utf-8") != checker.report_page(result, analysis):
        raise ValueError("saved HTML differs from verified result and projection data")
    if (environment.get("source_repository_commit") != SOURCE_COMMIT or
            environment.get("source_file_blob") != checker.SOURCE_BLOB or
            environment.get("algorithm_source_sha256") != result["algorithm_source_sha256"]):
        raise ValueError("environment metadata differs from the measured result")
    if (capture.get("source_commit") != result["source_commit"] or
            capture.get("driver_sha256") != result["driver_sha256"] or
            capture.get("algorithm_source_sha256") != result["algorithm_source_sha256"]):
        raise ValueError("capture metadata differs from the measured result")
    parser = LocalLinks()
    parser.feed(files["index.html"].decode("utf-8"))
    local_links = [href for href in parser.hrefs if not href.startswith("https://")]
    if (not local_links or any(href not in files for href in local_links) or
            any(not href.startswith("https://github.com/") for href in parser.hrefs
                if href not in local_links)):
        raise ValueError("report contains a missing local or unpinned external link")
    return files, result, analysis


def stage(source: Path, site: Path) -> str:
    files, result, analysis = _inputs(source)
    identity = {"source_repository_commit": SOURCE_COMMIT,
                "source_commit": result["source_commit"],
                "result_sha256": digest(files["result.json"]),
                "stager_sha256": digest(Path(__file__).read_bytes()),
                "source_files": {name: digest(content) for name, content in sorted(files.items())}}
    report_id = "env717-point-on-plane-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    if not site.is_dir():
        raise ValueError("staged Pages site directory does not exist")
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("content-addressed report route already exists")
    index = site / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages landing index insertion point differs")

    generated = dict(files)
    page = files["index.html"].decode("utf-8")
    footer = (f'<p>Immutable Pages report <code>{escape(report_id)}</code>. '
              f'<a href="publication-manifest.json">Publication manifest</a> · '
              f'<a href="../{escape(report_id)}.zip">Offline report ZIP</a>.</p>')
    generated["index.html"] = page.replace("</main>", footer + "</main>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n"
        for name in sorted(generated) if name not in ("SHA256SUMS", "publication-manifest.json")
    ).encode("ascii")
    manifest = {"schema": "csl.env717-publication/1", "report_id": report_id,
        "source_report_id": source.name, "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"], "result_sha256": digest(files["result.json"]),
        "stager_sha256": identity["stager_sha256"], "source_files": identity["source_files"],
        "published_files": {name: digest(content) for name, content in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    route_link = (f'<li><a href="{report_id}/index.html">PointOnThePlane minimax and reachability</a>'
                  f' — 125 finite plans; position and velocity projections'
                  f' · <a href="{report_id}/result.json">result JSON</a>'
                  f' · <a href="{report_id}/projections.svg">two-plane figure</a>'
                  f' · <a href="{report_id}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    offline_index = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                     f'<title>Offline PointOnThePlane report</title>'
                     f'<a href="{report_id}/index.html">Open the report</a></html>').encode()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = [("index.html", offline_index)] + [
            (f"{report_id}/{name}", content) for name, content in sorted(generated.items())]
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    index.write_text(index_text.replace("</ul>", route_link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

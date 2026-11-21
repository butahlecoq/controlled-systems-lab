"""Stage the independently verified Van der Pol finite-action report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.reports import environment_report_publication as publication
else:
    publication_path = Path(__file__).with_name("environment_report_publication.py")
    publication_spec = importlib.util.spec_from_file_location(
        "environment_report_publication", publication_path
    )
    if publication_spec is None or publication_spec.loader is None:
        raise ImportError(f"cannot load the environment publication helper: {publication_path}")
    publication = importlib.util.module_from_spec(publication_spec)
    publication_spec.loader.exec_module(publication)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-vanderpol-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_vanderpol.py"
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
spec = importlib.util.spec_from_file_location("env717_vanderpol_checker", CHECKER)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load the environment source checker: {CHECKER}")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
FILES = (
    "README.md",
    "capture.json",
    "environment.json",
    "figure-data.json",
    "index.html",
    "projections.svg",
    "result.json",
    "SHA256SUMS",
)


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for key, value in attrs:
                if key == "href":
                    if value is None:
                        raise ValueError("report contains a link without a destination")
                    self.hrefs.append(value)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(source: Path) -> tuple[dict[str, bytes], dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("report source must be a directory")
    if {path.name for path in source.iterdir()} != set(FILES):
        raise ValueError("report file inventory differs")
    files = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("report files must be regular non-symlink files")
        files[name] = path.read_bytes()
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate report checksum")
        sums[name] = sha
    if sums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("report checksum mismatch")
    try:
        result = json.loads(files["result.json"])
        figure = json.loads(files["figure-data.json"])
        capture = json.loads(files["capture.json"])
        environment = json.loads(files["environment.json"])
        analysis = checker.verify(result)
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as error:
        raise ValueError("source-bound report validation failed") from error
    expected_figure = checker.figure_data(analysis)
    expected_svg = checker.svg_figure(expected_figure)
    if figure != expected_figure or files["projections.svg"].decode("utf-8") != expected_svg:
        raise ValueError("figure differs from independent replay")
    if files["index.html"].decode("utf-8") != checker.report_page(result, figure, expected_svg):
        raise ValueError("HTML differs from verified result and figure")
    if (
        capture.get("source_commit") != result["source_commit"]
        or capture.get("driver_sha256") != result["driver_sha256"]
        or environment.get("scenario_id") != result["scenario_id"]
        or environment.get("reference_variant") != result["reference_variant"]
        or environment.get("source_repository_commit") != SOURCE_COMMIT
        or environment.get("source_file_blob") != checker.SOURCE_BLOB
        or environment.get("source_notebook_blob") != checker.NOTEBOOK_BLOB
        or environment.get("driver_sha256") != result["driver_sha256"]
        or not isinstance(environment.get("processor"), str)
        or not environment["processor"].strip()
        or not isinstance(environment.get("logical_cpu_count"), int)
        or environment["logical_cpu_count"] < 1
    ):
        raise ValueError("capture or environment identity differs")
    parser = LocalLinks()
    parser.feed(files["index.html"].decode("utf-8"))
    local = [href for href in parser.hrefs if not href.startswith("https://")]
    if (
        not local
        or any(href not in files for href in local)
        or any(
            not href.startswith("https://github.com/") for href in parser.hrefs if href not in local
        )
    ):
        raise ValueError("report contains an invalid local or external link")
    return files, result


def stage(source: Path, site: Path) -> str:
    files, result = inputs(source)
    publisher, archived_zip_sha256 = publication.archive_identity(
        source.name, files["SHA256SUMS"], Path(__file__)
    )
    identity = {
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "result_sha256": digest(files["result.json"]),
        **publisher,
        "source_files": {name: digest(data) for name, data in sorted(files.items())},
    }
    report_id = (
        "env717-vanderpol-"
        + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    if not site.is_dir():
        raise ValueError("Pages site directory does not exist")
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("content-addressed route already exists")
    index = site / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages landing index insertion point differs")
    generated = dict(files)
    generated["index.html"] = (
        files["index.html"]
        .decode()
        .replace(
            "</main>",
            f"<p>Immutable Pages report <code>{escape(report_id)}</code>. "
            '<a href="publication-manifest.json">Publication manifest</a> · '
            f'<a href="../{escape(report_id)}.zip">Offline report ZIP</a>.</p></main>',
        )
        .encode()
    )
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n"
        for name in sorted(generated)
        if name not in ("SHA256SUMS", "publication-manifest.json")
    ).encode("ascii")
    manifest = {
        "schema": "csl.env717-publication/1",
        "report_id": report_id,
        "source_report_id": source.name,
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "result_sha256": digest(files["result.json"]),
        **publisher,
        "source_files": identity["source_files"],
        "published_files": {name: digest(data) for name, data in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    route = (
        f'<li><a href="{report_id}/index.html">Van der Pol nonlinear control pilot</a>'
        f" — 243 finite open-loop plans with position–velocity phase plane"
        f' · <a href="{report_id}/result.json">result JSON</a>'
        f' · <a href="{report_id}/projections.svg">figure</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>'
    )
    offline = (
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<title>Offline Van der Pol report</title><a href="{report_id}/index.html">Open report</a></html>'
    ).encode()
    archive_bytes = publication.offline_zip(
        report_id, offline, generated, expected_sha256=archived_zip_sha256
    )
    destination.mkdir()
    for name, data in generated.items():
        (destination / name).write_bytes(data)
    archive_path.write_bytes(archive_bytes)
    index.write_text(index_text.replace("</ul>", route + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

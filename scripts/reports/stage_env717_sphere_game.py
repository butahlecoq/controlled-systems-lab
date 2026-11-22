"""Stage the immutable SphereGame pilot as a versioned Pages report."""

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
SOURCE = ROOT / "reports/algorithm-results/env717-sphere-game-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_sphere_game.py"
spec = importlib.util.spec_from_file_location("env717_sphere_game_checker", CHECKER)
if spec is None or spec.loader is None:
    raise ImportError("cannot load the environment report dependency")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

FILES = (
    "README.md",
    "capture.json",
    "figure-data.json",
    "index.html",
    "projections.svg",
    "result.json",
    "scenario.json",
    "SHA256SUMS",
)
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"


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


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inputs(source: Path) -> tuple[dict[str, bytes], dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("environment report source must be a directory")
    if {path.name for path in source.iterdir()} != set(FILES):
        raise ValueError("environment report source inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate report checksum")
        sums[name] = digest
    if sums != {name: _digest(content) for name, content in files.items() if name != "SHA256SUMS"}:
        raise ValueError("environment report checksum mismatch")
    result = json.loads(files["result.json"])
    if result.get("schema") != "csl.env717-sphere-game-pilot/1":
        raise ValueError("environment report schema differs")
    if result.get("source_repository_commit") != SOURCE_COMMIT:
        raise ValueError("upstream environment source commit differs")
    if files["scenario.json"] != checker.SCENARIO.read_bytes():
        raise ValueError("saved scenario input differs from the versioned fixture")
    for field in ("driver_sha256", "algorithm_source_sha256", "source_commit"):
        value = result.get(field)
        expected_length = 40 if field == "source_commit" else 64
        if (
            not isinstance(value, str)
            or len(value) != expected_length
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError(f"environment report provenance field is invalid: {field}")
    try:
        derived = checker.verify_record(result)
    except (AssertionError, KeyError, TypeError) as error:
        raise ValueError("independent environment replay failed") from error
    try:
        figure_data = json.loads(files["figure-data.json"])
        capture = json.loads(files["capture.json"])
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("environment report JSON is invalid") from error
    if figure_data != json.loads(json.dumps(derived)):
        raise ValueError("saved figure data differs from independent replay")
    if capture.get("renderer_sha256") != _digest(CHECKER.read_bytes()):
        raise ValueError("environment report renderer identity differs")
    host = capture.get("capture_environment")
    if (
        not isinstance(host, dict)
        or not host.get("processor")
        or not host.get("processor_identity_source")
        or not host.get("os")
        or not isinstance(host.get("logical_cpus"), int)
    ):
        raise ValueError("environment report capture metadata is incomplete")
    expected_svg = checker.svg(derived) + "\n"
    if files["projections.svg"].decode("utf-8") != expected_svg:
        raise ValueError("saved SVG differs from independent figure data")
    expected_page = checker.page(result, expected_svg[:-1], capture["capture_environment"]).encode(
        "utf-8"
    )
    if files["index.html"] != expected_page:
        raise ValueError("saved report page differs from verified result and SVG")
    parser = LocalLinks()
    parser.feed(files["index.html"].decode("utf-8"))
    local_hrefs = [href for href in parser.hrefs if not href.startswith("https://")]
    if (
        not parser.hrefs
        or any(href not in files for href in local_hrefs)
        or any(
            not href.startswith("https://github.com/")
            for href in parser.hrefs
            if href not in local_hrefs
        )
    ):
        raise ValueError("report page has a missing or nonlocal asset link")
    return files, result


def stage(source: Path, site_root: Path) -> str:
    files, result = _inputs(source)
    publisher, archived_zip_sha256 = publication.archive_identity(
        source.name, files["SHA256SUMS"], Path(__file__)
    )
    identity = {
        "schema": "csl.env717-publication-identity/1",
        "source_report_id": source.name,
        "result_sha256": _digest(files["result.json"]),
        "renderer_sha256": _digest(CHECKER.read_bytes()),
        **publisher,
        "source_file_hashes": {name: _digest(content) for name, content in sorted(files.items())},
    }
    report_id = (
        "env717-sphere-game-"
        + _digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    if not site_root.is_dir():
        raise ValueError("staged Pages site directory does not exist")
    destination = site_root / report_id
    archive_path = site_root / (report_id + ".zip")
    if destination.exists() or archive_path.exists():
        raise ValueError("versioned environment report route already exists")
    index = site_root / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages index insertion point or route identity differs")

    page = files["index.html"].decode("utf-8")
    footer = (
        f"<p>Immutable Pages report <code>{escape(report_id)}</code>. "
        f'<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{escape(report_id)}.zip">Offline report ZIP</a>.</p>'
    )
    if page.count("</main>") != 1:
        raise ValueError("source report page insertion point differs")
    generated = dict(files)
    generated["index.html"] = page.replace("</main>", footer + "</main>").encode()
    generated["SHA256SUMS"] = "".join(
        f"{_digest(generated[name])}  {name}\n"
        for name in sorted(generated)
        if name not in ("SHA256SUMS", "publication-manifest.json")
    ).encode("ascii")
    manifest = {
        "schema": "csl.env717-publication/1",
        "report_id": report_id,
        "source_report_id": source.name,
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "scenario_sha256": result["scenario_sha256"],
        "arithmetic": result["numerics"]["arithmetic"],
        "numerics": result["numerics"],
        "result_sha256": _digest(files["result.json"]),
        **publisher,
        "source_files": {name: _digest(content) for name, content in sorted(files.items())},
        "published_files": {name: _digest(content) for name, content in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    route_link = (
        f'<li><a href="{report_id}/index.html">SphereGame differential-game pilot</a>'
        f" — 27 fixed plans; residual-norm phase-plane reachability"
        f' · <a href="{report_id}/result.json">result JSON</a>'
        f' · <a href="{report_id}/projections.svg">projection figure</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>'
    )
    offline_landing = (
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>Offline SphereGame report</title>"
        f'<a href="{report_id}/index.html">Open the report</a></html>'
    ).encode()
    archive_bytes = publication.offline_zip(
        report_id, offline_landing, generated, expected_sha256=archived_zip_sha256
    )
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    archive_path.write_bytes(archive_bytes)
    index.write_text(index_text.replace("</ul>", route_link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

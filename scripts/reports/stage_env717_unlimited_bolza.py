#!/usr/bin/env python3
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
CHECKER = ROOT / "scripts/reports/env717/check_unlimited_bolza.py"
spec = importlib.util.spec_from_file_location("env717_unlimited_bolza_checker", CHECKER)
if spec is None or spec.loader is None:
    raise ImportError("cannot load the environment report dependency")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

SOURCE = ROOT / "reports/algorithm-results/env717-unlimited-bolza-pilot-v1"
FILES = (
    "README.md",
    "capture.json",
    "figure-data.json",
    "index.html",
    "phase-plane.svg",
    "result.json",
    "SHA256SUMS",
)


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
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
        raise ValueError("environment report source must be a real directory")
    entries = tuple(source.iterdir())
    if {path.name for path in entries} != set(FILES):
        raise ValueError("environment report source inventory differs")
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise ValueError("environment report entries must be regular files")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums: dict[str, str] = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate report checksum")
        sums[name] = digest
    expected_sums = {
        name: _digest(content) for name, content in files.items() if name != "SHA256SUMS"
    }
    if sums != expected_sums:
        raise ValueError("environment report checksum mismatch")

    result = json.loads(files["result.json"])
    checker.verify(result)
    if files["README.md"] != checker.make_readme(result, result["runtime_measurement"]).encode():
        raise ValueError("saved report README differs from verified result")
    if files["phase-plane.svg"] != (checker.make_svg(result) + "\n").encode():
        raise ValueError("saved phase-plane figure differs from verified result")
    if files["index.html"] != checker.make_html(result).encode():
        raise ValueError("saved report HTML differs from verified result")
    figure_data = {
        "schema": "csl.env717-figure-data/1",
        "coordinates": ["position", "velocity"],
        "tracks": {
            "continuous_analytic_reference": result["continuous_analytic_reference"]["trajectory"],
            "sampled_analytic_feedback_replay": result["sampled_analytic_feedback_replay"][
                "trajectory"
            ],
            "finite_catalogue_optimum": result["finite_catalogue_optimum"]["trajectory"],
        },
    }
    if (
        files["figure-data.json"]
        != (json.dumps(figure_data, indent=2, sort_keys=True) + "\n").encode()
    ):
        raise ValueError("saved figure data differs from verified trajectories")
    capture = json.loads(files["capture.json"])
    if capture.get("measurement") != result["runtime_measurement"]:
        raise ValueError("capture measurement differs from raw result")
    environment = capture.get("environment", {})
    if (
        not environment.get("captured_at_utc")
        or not environment.get("platform")
        or not environment.get("python")
        or not isinstance(environment.get("logical_cpu_count"), int)
    ):
        raise ValueError("capture environment record is incomplete")

    parser = LocalLinks()
    parser.feed(files["index.html"].decode("utf-8"))
    external = {
        checker.SOURCE_URL,
        "https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-33ebdad360671940fb54/index.html",
    }
    if not parser.hrefs or any(href not in files and href not in external for href in parser.hrefs):
        raise ValueError("report page has a missing or unexpected link")
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
        "source_file_hashes": {name: _digest(data) for name, data in sorted(files.items())},
    }
    report_id = (
        "env717-unlimited-bolza-"
        + _digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    if not site_root.is_dir() or site_root.is_symlink():
        raise ValueError("staged Pages site root must be a real directory")
    index = site_root / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ValueError("Pages index must be a regular file")
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages index insertion point or route identity differs")
    destination = site_root / report_id
    archive_path = site_root / f"{report_id}.zip"
    if (
        destination.exists()
        or destination.is_symlink()
        or archive_path.exists()
        or archive_path.is_symlink()
    ):
        raise ValueError("versioned environment route already exists")

    source_page = files["index.html"].decode("utf-8")
    footer = (
        f"<p>Immutable report route <code>{escape(report_id)}</code>. "
        f'<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{escape(report_id)}.zip">Offline ZIP</a>.</p>'
    )
    if source_page.count("</main>") != 1:
        raise ValueError("source report page insertion point differs")
    generated = dict(files)
    generated["index.html"] = source_page.replace("</main>", footer + "</main>").encode()
    generated["SHA256SUMS"] = "".join(
        f"{_digest(generated[name])}  {name}\n"
        for name in sorted(generated)
        if name != "SHA256SUMS"
    ).encode("ascii")
    manifest = {
        "schema": "csl.env717-publication/1",
        "report_id": report_id,
        "source_report_id": source.name,
        "source_repository_commit": result["source_repository_commit"],
        "source_commit": result["provenance"]["source_commit"],
        "result_sha256": _digest(files["result.json"]),
        **publisher,
        "source_files": {name: _digest(data) for name, data in sorted(files.items())},
        "published_files": {name: _digest(data) for name, data in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    route_link = (
        f'<li><a href="{report_id}/index.html">UnlimitedBolza analytic and finite-catalogue report</a>'
        f" — position–velocity phase plane; source Euler replay; exact 5^10 finite-catalogue minimum"
        f' · <a href="{report_id}/result.json">result</a>'
        f' · <a href="{report_id}/phase-plane.svg">SVG figure</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>'
    )

    offline_landing = (
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>Offline UnlimitedBolza report</title>"
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
    parser = argparse.ArgumentParser(description="Stage the immutable UnlimitedBolza report")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    arguments = parser.parse_args()
    print(stage(arguments.source, arguments.site))

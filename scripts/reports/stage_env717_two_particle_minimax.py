#!/usr/bin/env python3
"""Validate and publish the immutable TwoParticleGame finite-game report."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import stat
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
SOURCE = ROOT / "reports/algorithm-results/env717-two-particle-minimax-v1"
CHECKER_PATH = ROOT / "scripts/reports/env717/check_two_particle_minimax.py"
CAPTURE_PATH = ROOT / "scripts/reports/env717/capture_two_particle_minimax.py"
SPEC = importlib.util.spec_from_file_location("env717_two_particle_capture", CAPTURE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError("cannot load the environment report dependency")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)
CHECKER_SPEC = importlib.util.spec_from_file_location("env717_two_particle_checker", CHECKER_PATH)
if CHECKER_SPEC is None or CHECKER_SPEC.loader is None:
    raise ImportError("cannot load the environment report dependency")
checker = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(checker)
SOURCE_COMMIT = "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8"
FILES = (
    "README.md",
    "capture.json",
    "check.json",
    "figure-data.json",
    "index.html",
    "projections.svg",
    "result.json",
    "scenario.json",
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_bundle(source: Path) -> tuple[dict[str, bytes], bytes]:
    if not source.is_dir() or source.is_symlink():
        raise ValueError("report bundle must be a regular directory")
    sums_path = source / "SHA256SUMS"
    if not sums_path.is_file() or sums_path.is_symlink():
        raise ValueError("report checksum file is missing or unsafe")
    checksum_bytes = sums_path.read_bytes()
    checksums = {}
    for line in checksum_bytes.decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate checksum path")
        checksums[name] = sha
    if set(checksums) != set(FILES):
        raise ValueError("report checksum manifest has an unexpected file set")
    files = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("report bundle entries must be regular non-symlink files")
        content = path.read_bytes()
        if digest(content) != checksums[name]:
            raise ValueError(f"checksum mismatch: {name}")
        files[name] = content
    return files, checksum_bytes


def _validate_files(files: dict[str, bytes]) -> tuple[dict, dict, dict]:
    result = json.loads(files["result.json"])
    check = json.loads(files["check.json"])
    figure = json.loads(files["figure-data.json"])
    capture_record = json.loads(files["capture.json"])
    if checker.verify(result) != check:
        raise ValueError("saved independent check differs from a fresh exact graph replay")
    if capture.project_layers(result) != figure:
        raise ValueError("saved projection data differs from the checked state graph")
    if (capture.svg_figure(figure) + "\n").encode() != files["projections.svg"]:
        raise ValueError("saved plot differs from replayed projection data")
    if capture.make_page(result, check, capture_record).encode() != files["index.html"]:
        raise ValueError("saved page differs from the checked result and capture metadata")
    if (
        result.get("source_commit") != capture_record.get("source_commit")
        or capture_record.get("scenario_sha256") != result.get("scenario_sha256")
        or result.get("source", {}).get("repository_commit") != SOURCE_COMMIT
    ):
        raise ValueError("report source provenance does not match the pinned game")
    if check.get("status") != "verified" or capture_record.get("solver_failures") != 0:
        raise ValueError("report does not contain a successful independently verified solve")
    return result, check, capture_record


def validate_bundle(source: Path) -> tuple[dict[str, bytes], dict, dict, dict]:
    files, _ = _read_bundle(source)
    return files, *_validate_files(files)


def stage(source: Path, site: Path) -> str:
    files, checksum_bytes = _read_bundle(source)
    result, _, capture_record = _validate_files(files)
    if not site.is_dir():
        raise ValueError("staged Pages site directory does not exist")
    publisher, archived_zip_sha256 = publication.archive_identity(
        source.name, checksum_bytes, Path(__file__)
    )
    identity = {
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "result_sha256": digest(files["result.json"]),
        "capture_sha256": digest(files["capture.json"]),
        **publisher,
        "published_source_files": {
            name: digest(content) for name, content in sorted(files.items())
        },
    }
    report_id = (
        "env717-two-particle-minimax-"
        + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("content-addressed report route already exists")
    index = site / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages landing index insertion point differs")
    generated = dict(files)
    page = files["index.html"].decode("utf-8")
    footer = (
        f"<p>Immutable Pages report <code>{html.escape(report_id)}</code>. "
        f'<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{html.escape(report_id)}.zip">Offline report ZIP</a>.</p>'
    )
    generated["index.html"] = page.replace("</body>", footer + "</body>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(content)}  {name}\n"
        for name, content in sorted(generated.items())
        if name != "SHA256SUMS"
    ).encode("ascii")
    manifest = {
        "schema": "csl.env717-publication/1",
        "report_id": report_id,
        "source_report_id": source.name,
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "capture_sha256": digest(files["capture.json"]),
        **publisher,
        "source_files": identity["published_source_files"],
        "published_files": {name: digest(content) for name, content in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    route_link = (
        f'<li><a href="{report_id}/index.html">TwoParticleGame finite reachability and minimax</a>'
        f' · <a href="{report_id}/result.json">result JSON</a>'
        f' · <a href="{report_id}/projections.svg">position/velocity projections</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>'
    )
    offline_index = (
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>Offline TwoParticleGame report</title>"
        f'<a href="{report_id}/index.html">Open the report</a></html>'
    ).encode()
    archive_bytes = publication.offline_zip(
        report_id, offline_index, generated, expected_sha256=archived_zip_sha256
    )
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    archive_path.write_bytes(archive_bytes)
    index.write_text(index_text.replace("</ul>", route_link + "</ul>"), encoding="utf-8")
    return report_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

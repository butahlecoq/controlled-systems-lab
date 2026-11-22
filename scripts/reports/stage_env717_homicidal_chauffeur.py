#!/usr/bin/env python3
"""Validate and publish the immutable finite HomicidalChauffeur report."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType
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
SOURCE = ROOT / "reports/algorithm-results/env717-homicidal-chauffeur-v1"
SCENARIO = ROOT / "benchmarks/scenarios/env717-homicidal-chauffeur-pilot-v1.json"
CAPTURE_PATH = ROOT / "scripts/reports/env717/capture_homicidal_chauffeur.py"
CHECKER_PATH = ROOT / "scripts/reports/env717/check_homicidal_chauffeur.py"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the environment report dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load("env717_homicidal_capture", CAPTURE_PATH)
checker = load("env717_homicidal_checker", CHECKER_PATH)
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
    if source.is_symlink() or not source.is_dir():
        raise ValueError("report bundle must be a regular directory")
    sums = source / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise ValueError("report checksums are missing")
    checksum_bytes = sums.read_bytes()
    recorded = {}
    for line in checksum_bytes.decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in recorded:
            raise ValueError("duplicate report checksum path")
        recorded[name] = sha
    if set(recorded) != set(FILES):
        raise ValueError("report file inventory differs")
    result = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("report bundle entries must be regular files")
        content = path.read_bytes()
        if digest(content) != recorded[name]:
            raise ValueError(f"report checksum mismatch: {name}")
        result[name] = content
    return result, checksum_bytes


def read_bundle(source: Path) -> dict[str, bytes]:
    files, _ = _read_bundle(source)
    return files


def _validate_files(files: dict[str, bytes]) -> tuple[dict, dict]:
    result = json.loads(files["result.json"])
    check = json.loads(files["check.json"])
    figure = json.loads(files["figure-data.json"])
    captured = json.loads(files["capture.json"])
    scenario = json.loads(files["scenario.json"])
    if checker.verify(result) != check:
        raise ValueError("saved independent check differs from a fresh full graph replay")
    if capture.project_layers(result) != figure:
        raise ValueError("saved figure data differs from the checked graph")
    if (capture.svg_figure(figure) + "\n").encode() != files["projections.svg"]:
        raise ValueError("saved SVG differs from checked figure data")
    if capture.make_page(result, check, captured).encode() != files["index.html"]:
        raise ValueError("saved report page differs from result and metadata")
    if (
        scenario != json.loads(SCENARIO.read_text(encoding="utf-8"))
        or scenario.get("source", {}).get("commit") != SOURCE_COMMIT
        or result.get("source", {}).get("repository_commit") != SOURCE_COMMIT
        or result.get("scenario_sha256") != digest(SCENARIO.read_bytes())
        or captured.get("scenario_sha256") != result.get("scenario_sha256")
    ):
        raise ValueError("source or scenario provenance differs")
    if check.get("status") != "verified" or captured.get("solver_failures") != 0:
        raise ValueError("report lacks successful independent verification")
    return result, captured


def validate_bundle(source: Path) -> tuple[dict[str, bytes], dict, dict]:
    files = read_bundle(source)
    return files, *_validate_files(files)


def stage(source: Path, site: Path) -> str:
    files, checksum_bytes = _read_bundle(source)
    result, captured = _validate_files(files)
    if not site.is_dir():
        raise ValueError("Pages staging directory does not exist")
    publisher, archived_zip_sha256 = publication.archive_identity(
        source.name, checksum_bytes, Path(__file__)
    )
    identity = {
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": captured["source_commit"],
        "capture_sha256": digest(files["capture.json"]),
        "result_sha256": digest(files["result.json"]),
        **publisher,
        "source_files": {name: digest(content) for name, content in sorted(files.items())},
    }
    report_id = (
        "env717-homicidal-chauffeur-"
        + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    if (
        destination.exists()
        or archive_path.exists()
        or report_id in page
        or page.count("</ul>") != 1
    ):
        raise ValueError("immutable route already exists or landing insertion point differs")
    generated = dict(files)
    footer = (
        f"<p>Immutable Pages report <code>{html.escape(report_id)}</code> · "
        '<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{html.escape(report_id)}.zip">Offline ZIP</a>.</p>'
    )
    generated["index.html"] = (
        files["index.html"].decode().replace("</body>", footer + "</body>").encode()
    )
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
        "source_commit": captured["source_commit"],
        **publisher,
        "measured_scope": "Four 0.1-second stages; complete finite reachable graph, terminal capture sweep, causal minimax value with independent replay, and five fresh-process runtime observations for the single adapter.",
        "evidence_limits": [
            "Finite action catalogues and a quantized lattice only.",
            "The zero-sum payoff signs and sequential response are analysis assumptions because the source environment does not assign per-agent payoff signs.",
            "Runtime is descriptive for one adapter and machine; it is not a comparison or speedup claim.",
            "No continuous-action RL reproduction or continuous-game optimality claim.",
        ],
        "source_files": identity["source_files"],
        "published_files": {name: digest(content) for name, content in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    link = (
        f'<li><a href="{report_id}/index.html">HomicidalChauffeur reachability and minimax</a>'
        f' · <a href="{report_id}/result.json">result JSON</a>'
        f' · <a href="{report_id}/projections.svg">player position projections</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>'
    )
    offline = (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline HomicidalChauffeur report</title>'
        f'<a href="{report_id}/index.html">Open the report</a></html>'
    ).encode()
    archive_bytes = publication.offline_zip(
        report_id, offline, generated, expected_sha256=archived_zip_sha256
    )
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    archive_path.write_bytes(archive_bytes)
    index.write_text(page.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

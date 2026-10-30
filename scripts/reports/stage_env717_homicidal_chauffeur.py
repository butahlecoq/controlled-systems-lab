#!/usr/bin/env python3
"""Validate and publish the immutable finite HomicidalChauffeur report."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-homicidal-chauffeur-v1"
SCENARIO = ROOT / "benchmarks/scenarios/env717-homicidal-chauffeur-pilot-v1.json"
CAPTURE_PATH = ROOT / "scripts/reports/env717/capture_homicidal_chauffeur.py"
CHECKER_PATH = ROOT / "scripts/reports/env717/check_homicidal_chauffeur.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


capture = load("env717_homicidal_capture", CAPTURE_PATH)
checker = load("env717_homicidal_checker", CHECKER_PATH)
SOURCE_COMMIT = "af5f0a2ee498c0edcf88d60f1d6c49a39bd08bc8"
FILES = ("README.md", "capture.json", "check.json", "figure-data.json", "index.html",
         "projections.svg", "result.json", "scenario.json")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_bundle(source: Path):
    if source.is_symlink() or not source.is_dir():
        raise ValueError("report bundle must be a regular directory")
    sums = source / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise ValueError("report checksums are missing")
    recorded = {}
    for line in sums.read_text(encoding="ascii").splitlines():
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
    return result


def validate_bundle(source: Path):
    files = read_bundle(source)
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
    if (scenario != json.loads(SCENARIO.read_text(encoding="utf-8")) or
            scenario.get("source", {}).get("commit") != SOURCE_COMMIT or
            result.get("source", {}).get("repository_commit") != SOURCE_COMMIT or
            result.get("scenario_sha256") != digest(SCENARIO.read_bytes()) or
            captured.get("scenario_sha256") != result.get("scenario_sha256")):
        raise ValueError("source or scenario provenance differs")
    if check.get("status") != "verified" or captured.get("solver_failures") != 0:
        raise ValueError("report lacks successful independent verification")
    return files, result, captured


def stage(source: Path, site: Path) -> str:
    files, result, captured = validate_bundle(source)
    if not site.is_dir():
        raise ValueError("Pages staging directory does not exist")
    identity = {"source_repository_commit": SOURCE_COMMIT,
        "source_commit": captured["source_commit"], "capture_sha256": digest(files["capture.json"]),
        "result_sha256": digest(files["result.json"]),
        "stager_sha256": digest(Path(__file__).read_bytes()),
        "source_files": {name: digest(content) for name, content in sorted(files.items())}}
    report_id = "env717-homicidal-chauffeur-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    if destination.exists() or archive_path.exists() or report_id in page or page.count("</ul>") != 1:
        raise ValueError("immutable route already exists or landing insertion point differs")
    generated = dict(files)
    footer = (f'<p>Immutable Pages report <code>{html.escape(report_id)}</code> · '
        '<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{html.escape(report_id)}.zip">Offline ZIP</a>.</p>')
    generated["index.html"] = files["index.html"].decode().replace(
        "</body>", footer + "</body>").encode()
    generated["SHA256SUMS"] = "".join(
        f"{digest(content)}  {name}\n" for name, content in sorted(generated.items())
        if name != "SHA256SUMS").encode("ascii")
    manifest = {"schema": "csl.env717-publication/1", "report_id": report_id,
        "source_report_id": source.name, "source_repository_commit": SOURCE_COMMIT,
        "source_commit": captured["source_commit"], "stager_sha256": identity["stager_sha256"],
        "measured_scope": "Four 0.1-second stages; complete finite reachable graph, terminal capture sweep, and causal minimax value with independent replay; no timing result.",
        "evidence_limits": ["Finite action catalogues and a quantized lattice only.",
            "The zero-sum payoff signs and sequential response are analysis assumptions because the source environment does not assign per-agent payoff signs.",
            "No continuous-action RL reproduction or continuous-game optimality claim."],
        "source_files": identity["source_files"],
        "published_files": {name: digest(content) for name, content in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    link = (f'<li><a href="{report_id}/index.html">HomicidalChauffeur reachability and minimax</a>'
        f' · <a href="{report_id}/result.json">result JSON</a>'
        f' · <a href="{report_id}/projections.svg">player position projections</a>'
        f' · <a href="{report_id}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    offline = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline HomicidalChauffeur report</title>'
        f'<a href="{report_id}/index.html">Open the report</a></html>').encode()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = [("index.html", offline)] + [(f"{report_id}/{name}", content)
                                               for name, content in sorted(generated.items())]
        for name, content in entries:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
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

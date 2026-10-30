#!/usr/bin/env python3
"""Validate and stage the immutable MPC-04 MaxCoordinateGame report."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REPOSITORY_URL = "https://github.com/butahlecoq/controlled-systems-lab.git"
SOURCE = ROOT / "reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030"
REPORT_PATH = ROOT / "scripts/reports/mpc04/max_coordinate_replanning.py"
CHECKER_PATH = ROOT / "scripts/reports/mpc04/check_max_coordinate.py"
PAYLOAD_FILES = ("README.md", "build-config.json", "build.log", "capture.json",
                 "environment.json", "index.html", "result.json", "trajectory.svg")
ZIP_FILE = "mpc04-max-coordinate-replanning-pilot.zip"
BUNDLE_SUMS = "BUNDLE-SHA256SUMS"
OUTER_FILES = (*PAYLOAD_FILES, BUNDLE_SUMS, ZIP_FILE)
SOURCE_PATHS = {
    "native_driver": "benchmarks/reporting/mpc04/max_coordinate_replanning.cpp",
    "report_driver": "scripts/reports/mpc04/max_coordinate_replanning.py",
    "independent_checker": "scripts/reports/mpc04/check_max_coordinate.py",
    "cmake_target": "cmake/OptionalReports.cmake",
}
SOURCE_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


report = load_module("mpc04_max_coordinate_report", REPORT_PATH)
checker = load_module("mpc04_max_coordinate_checker", CHECKER_PATH)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_sums(content: bytes, expected: set[str], label: str) -> dict[str, str]:
    try:
        lines = content.decode("ascii").splitlines()
        parsed = {}
        for line in lines:
            checksum, name = line.split("  ", 1)
            if name in parsed or SHA256_RE.fullmatch(checksum) is None:
                raise ValueError
            parsed[name] = checksum
    except (UnicodeDecodeError, ValueError):
        raise ValueError(f"malformed {label}") from None
    if set(parsed) != expected:
        raise ValueError(f"{label} inventory differs")
    return parsed


def _regular_file(directory: Path, name: str) -> bytes:
    path = directory / name
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"MPC-04 bundle entry must be a regular file: {name}")
    return path.read_bytes()


def read_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("MPC-04 report source must be a regular directory")
    outer = parse_sums(_regular_file(source, "SHA256SUMS"), set(OUTER_FILES),
                       "MPC-04 outer checksums")
    files = {name: _regular_file(source, name) for name in OUTER_FILES}
    for name, content in files.items():
        if digest(content) != outer[name]:
            raise ValueError(f"MPC-04 outer checksum mismatch: {name}")
    inner = parse_sums(files[BUNDLE_SUMS], set(PAYLOAD_FILES),
                       "MPC-04 bundle checksums")
    for name in PAYLOAD_FILES:
        if digest(files[name]) != inner[name]:
            raise ValueError(f"MPC-04 bundle checksum mismatch: {name}")
    try:
        with zipfile.ZipFile(io.BytesIO(files[ZIP_FILE])) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            expected = {*PAYLOAD_FILES, BUNDLE_SUMS}
            if len(names) != len(set(names)) or set(names) != expected:
                raise ValueError("MPC-04 offline ZIP inventory differs")
            for entry in entries:
                member = PurePosixPath(entry.filename)
                mode = entry.external_attr >> 16
                if (member.is_absolute() or ".." in member.parts or len(member.parts) != 1 or
                        entry.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))):
                    raise ValueError("MPC-04 offline ZIP contains an unsafe entry")
                content = archive.read(entry)
                expected_content = files[BUNDLE_SUMS] if entry.filename == BUNDLE_SUMS else files[entry.filename]
                if content != expected_content:
                    raise ValueError(f"MPC-04 offline ZIP content differs: {entry.filename}")
    except (zipfile.BadZipFile, OSError):
        raise ValueError("MPC-04 offline ZIP is invalid") from None
    return files


def verify_source_fingerprints(commit: str, fingerprints: dict[str, str]) -> None:
    repository = ROOT
    present = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True, check=False)
    temporary = None
    if present.returncode != 0:
        temporary = tempfile.TemporaryDirectory(prefix="mpc04-source-commit-")
        repository = Path(temporary.name) / "repository.git"
        initialized = subprocess.run(["git", "init", "--bare", str(repository)],
                                     capture_output=True, check=False)
        fetched = subprocess.run(
            ["git", "-C", str(repository), "fetch", "--quiet", "--no-tags", "--depth=1",
             SOURCE_REPOSITORY_URL, commit], capture_output=True, check=False)
        if initialized.returncode != 0 or fetched.returncode != 0:
            temporary.cleanup()
            raise ValueError("MPC-04 captured source commit is unavailable for verification")
    try:
        for key, path in SOURCE_PATHS.items():
            blob = subprocess.run(
                ["git", "-C", str(repository), "cat-file", "blob", f"{commit}:{path}"],
                capture_output=True, check=False)
            if blob.returncode != 0:
                raise ValueError(f"MPC-04 captured source is absent: {path}")
            if digest(blob.stdout) != fingerprints[key]:
                raise ValueError(f"MPC-04 captured source fingerprint differs: {key}")
    finally:
        if temporary is not None:
            temporary.cleanup()


def validate_bundle(source: Path):
    files = read_bundle(source)
    try:
        result_data = json.loads(files["result.json"])
        capture = json.loads(files["capture.json"])
        environment = json.loads(files["environment.json"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("MPC-04 saved JSON is invalid") from None
    if capture.get("schema") != "csl.mpc04-capture/4":
        raise ValueError("MPC-04 capture schema differs")
    implementation = result_data.get("algorithm_implementation", {})
    provenance = capture.get("source", {})
    commit = provenance.get("report_code_commit")
    fingerprints = provenance.get("source_sha256")
    if (not isinstance(commit, str) or SOURCE_COMMIT_RE.fullmatch(commit) is None or
            not isinstance(fingerprints, dict) or set(fingerprints) != set(SOURCE_PATHS) or
            any(not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
                for value in fingerprints.values())):
        raise ValueError("MPC-04 captured source provenance is malformed")
    if implementation.get("commit") != commit or implementation.get("source_sha256") != fingerprints:
        raise ValueError("MPC-04 result and capture source provenance differ")
    build = provenance.get("build", {})
    if (provenance.get("algorithm_sources_dirty") is not False or
            build.get("algorithm_sources_clean_at_build") is not True or
            build.get("type") != "Release" or
            build.get("target") != "csl_mpc04_max_coordinate_replanning" or
            build.get("native_driver_sha256") != fingerprints["native_driver"] or
            SHA256_RE.fullmatch(str(provenance.get("binary_sha256", ""))) is None or
            not files["build.log"].strip()):
        raise ValueError("MPC-04 clean Release build evidence is incomplete")
    if (environment.get("schema") != "csl.mpc04-runtime/4" or environment != provenance):
        raise ValueError("MPC-04 environment schema differs")
    if (capture.get("episode_count") != len(result_data.get("episodes", [])) or
            capture.get("variants") != len(result_data.get("variants", {})) or
            capture.get("state_transitions") != 512 or
            capture.get("complete_histories_per_variant") != 16):
        raise ValueError("MPC-04 capture counts differ from the saved result")

    with tempfile.TemporaryDirectory(prefix="mpc04-report-replay-") as temporary:
        replay_dir = Path(temporary)
        result_path = replay_dir / "result.json"
        result_path.write_bytes(files["result.json"])
        (replay_dir / "trajectory.svg").write_bytes(files["trajectory.svg"])
        checker.check(result_path)
        generated_svg = replay_dir / "regenerated.svg"
        report.write_svg(generated_svg, result_data["episodes"])
        if generated_svg.read_bytes() != files["trajectory.svg"]:
            raise ValueError("MPC-04 SVG differs from saved result")
        generated_html = replay_dir / "regenerated.html"
        report.write_html(generated_html, result_data)
        if generated_html.read_bytes() != files["index.html"]:
            raise ValueError("MPC-04 HTML differs from saved result")

    verify_source_fingerprints(commit, fingerprints)
    return files, result_data, capture, environment


def stage(source: Path, site: Path) -> str:
    files, result_data, capture, environment = validate_bundle(source)
    if site.is_symlink() or not site.is_dir():
        raise ValueError("MPC-04 Pages site must be a regular directory")
    index_path = site / "index.html"
    if index_path.is_symlink() or not index_path.is_file():
        raise ValueError("MPC-04 Pages landing page is missing")
    page = index_path.read_text(encoding="utf-8")
    if page.count("</ul>") != 1:
        raise ValueError("MPC-04 archive insertion point differs")

    source_commit = capture["source"]["report_code_commit"]
    identity = {
        "source_commit": source_commit,
        "capture_sha256": digest(files["capture.json"]),
        "result_sha256": digest(files["result.json"]),
        "stager_sha256": digest(Path(__file__).read_bytes()),
        "source_bundle_sha256": {name: digest(content) for name, content in sorted(files.items())},
    }
    route = "mpc04-max-coordinate-replanning-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    if destination.exists() or archive_path.exists() or route in page:
        raise ValueError("MPC-04 immutable route already exists")

    generated = {name: files[name] for name in PAYLOAD_FILES}
    footer = (f'<p>Immutable report <code>{html.escape(route)}</code> · '
              '<a href="publication-manifest.json">Publication manifest</a> · '
              f'<a href="../{html.escape(route)}.zip">Offline ZIP</a>.</p>')
    generated["index.html"] = generated["index.html"].decode("utf-8").replace(
        "</html>", footer + "</html>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)).encode("ascii")
    manifest = {
        "schema": "csl.mpc04-max-coordinate-publication/1",
        "report_id": route,
        "source_report_id": source.name,
        "source_commit": source_commit,
        "stager_sha256": identity["stager_sha256"],
        "measured_scope": "128 four-step episodes, 512 transitions, eight finite or QP replanning variants, and complete 16-history disturbance catalogues per variant.",
        "evidence_limits": [
            "The source continuous-action task is reduced to a four-step adaptation and finite disturbance catalogue.",
            "Measurements are descriptive for one adapter and host; no limiter profile or performance winner is claimed.",
            "Finite-episode evidence does not establish recursive feasibility, stability, or globally optimal causal minimax control.",
        ],
        "verification": {"status": "passed", "checker": "scripts/reports/mpc04/check_max_coordinate.py"},
        "source_bundle_sha256": identity["source_bundle_sha256"],
        "published_files": {name: digest(content) for name, content in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    link = (f'<li><a href="{route}/index.html">MaxCoordinateGame replanning and QP comparison</a>'
            f' · <a href="{route}/result.json">all episode records</a>'
            f' · <a href="{route}/trajectory.svg">phase plane and decision timeline</a>'
            f' · <a href="{route}.zip">offline ZIP</a></li>')

    with tempfile.TemporaryDirectory(prefix=f".{route}-", dir=site) as temporary:
        temporary_path = Path(temporary)
        staged_route = temporary_path / route
        staged_route.mkdir()
        for name, content in generated.items():
            (staged_route / name).write_bytes(content)
        offline = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                   f'<title>Offline MPC-04 report</title><a href="{route}/index.html">'
                   "Open the MaxCoordinateGame replanning report</a></html>").encode("utf-8")
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            entries = [("index.html", offline)] + [
                (f"{route}/{name}", content) for name, content in sorted(generated.items())]
            for name, content in entries:
                item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                archive.writestr(item, content)
        staged_archive = temporary_path / f"{route}.zip"
        staged_archive.write_bytes(archive_bytes.getvalue())
        staged_index = temporary_path / "index.html"
        staged_index.write_text(page.replace("</ul>", link + "</ul>"), encoding="utf-8")
        if destination.exists() or archive_path.exists():
            raise ValueError("MPC-04 immutable route appeared during staging")
        try:
            os.replace(staged_route, destination)
            os.link(staged_archive, archive_path)
            os.replace(staged_index, index_path)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            archive_path.unlink(missing_ok=True)
            raise
    return route


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

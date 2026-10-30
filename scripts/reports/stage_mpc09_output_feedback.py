#!/usr/bin/env python3
"""Validate and stage the immutable MPC-09 output-feedback Pages report."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/mpc09-two-particle-output-feedback-v1"
CHECKER_PATH = ROOT / "scripts/reports/mpc09/check_output_feedback.py"
REPORT_PATH = ROOT / "scripts/reports/mpc09/make_report.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_module("mpc09_output_feedback_checker", CHECKER_PATH)
report = load_module("mpc09_output_feedback_report", REPORT_PATH)
FILES = ("README.md", "build.log", "capture.json", "environment.json", "figure-data.json",
         "index.html", "projections.svg", "result.json")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def source_blob(commit: str, name: str) -> bytes:
    if not isinstance(commit, str) or len(commit) != 40 or any(
            character not in "0123456789abcdef" for character in commit):
        raise ValueError("MPC-09 source commit must be a full lowercase Git object ID")
    path = Path(name)
    if path.is_absolute() or not name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("MPC-09 source path must be a normalized repository-relative path")
    try:
        return subprocess.run(
            ["git", "cat-file", "blob", f"{commit}:{path.as_posix()}"],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise ValueError(f"MPC-09 captured source is unavailable: {name}") from error


def read_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("MPC-09 report source must be a regular directory")
    sums = source / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise ValueError("MPC-09 checksum file is missing")
    recorded = {}
    for line in sums.read_text(encoding="ascii").splitlines():
        checksum, name = line.split("  ", 1)
        if name in recorded:
            raise ValueError("duplicate MPC-09 checksum path")
        recorded[name] = checksum
    if set(recorded) != set(FILES):
        raise ValueError("MPC-09 bundle file inventory differs")
    files = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("MPC-09 bundle entries must be regular files")
        content = path.read_bytes()
        if digest(content) != recorded[name]:
            raise ValueError(f"MPC-09 checksum mismatch: {name}")
        files[name] = content
    return files


def validate_bundle(source: Path):
    files = read_bundle(source)
    result_data = json.loads(files["result.json"])
    report.validate_scenario(result_data)
    verification = checker.verify(result_data)
    if result_data.get("independent_verification") != verification:
        raise ValueError("stored independent output-feedback verification differs")
    figure_data = json.loads(files["figure-data.json"])
    if report.svg_figure(figure_data).encode("utf-8") != files["projections.svg"]:
        raise ValueError("MPC-09 SVG differs from saved figure data")
    capture = json.loads(files["capture.json"])
    if not files["build.log"].strip() or not capture.get("report_executable_sha256"):
        raise ValueError("MPC-09 build and executable provenance are required")
    if capture.get("working_tree_clean") is not True:
        raise ValueError("MPC-09 capture must identify a clean source tree")
    commit = capture.get("source_commit")
    if capture.get("scenario_sha256") != digest(source_blob(
            commit, "benchmarks/scenarios/mpc09-two-particle-output-feedback-v1.json")):
        raise ValueError("MPC-09 scenario hash differs from its captured source commit")
    for name, expected in capture.get("source_sha256", {}).items():
        if digest(source_blob(commit, name)) != expected:
            raise ValueError(f"MPC-09 captured source fingerprint differs: {name}")
    if verification["causal_reference"]["scope"].find("complete finite observation-history") < 0:
        raise ValueError("MPC-09 finite-history reference scope is absent")
    return files, result_data, verification, capture


def stage(source: Path, site: Path) -> str:
    files, result_data, verification, capture = validate_bundle(source)
    if not site.is_dir():
        raise ValueError("staged Pages site does not exist")
    index_path = site / "index.html"
    page = index_path.read_text(encoding="utf-8")
    if page.count("</ul>") != 1:
        raise ValueError("algorithm archive insertion point differs")
    identity = {"source_commit": capture["source_commit"],
                "capture_sha256": digest(files["capture.json"]),
                "result_sha256": digest(files["result.json"]),
                "stager_sha256": digest(Path(__file__).read_bytes()),
                "published_source_files": {name: digest(value) for name, value in sorted(files.items())}}
    route = "mpc09-output-feedback-" + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    if destination.exists() or archive_path.exists() or route in page:
        raise ValueError("MPC-09 immutable route already exists")
    generated = dict(files)
    report_page = generated["index.html"].decode("utf-8")
    footer = (f'<p>Immutable report <code>{html.escape(route)}</code> · '
              '<a href="publication-manifest.json">Publication manifest</a> · '
              f'<a href="../{html.escape(route)}.zip">Offline ZIP</a>.</p>')
    generated["index.html"] = report_page.replace("</html>", footer + "</html>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
        if name != "SHA256SUMS").encode("ascii")
    manifest = {"schema": "csl.mpc09-output-feedback-publication/1", "report_id": route,
                "source_report_id": source.name, "source_commit": capture["source_commit"],
                "measured_scope": "864 rows per controller over two initial states, finite disturbance/error catalogues, and a three-stage horizon",
                "evidence_limits": ["Finite catalogue only; no continuous-noise or global output-feedback guarantee.",
                                    "The adapted task is not a reproduction of the source continuous-action RL run."],
                "stager_sha256": identity["stager_sha256"],
                "verification": verification, "source_bundle_sha256": {name: digest(value) for name, value in sorted(files.items())},
                "published_files": {name: digest(value) for name, value in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    link = (f'<li><a href="{route}/index.html">TwoParticleGame output-feedback MPC</a>'
            f' · <a href="{route}/result.json">all finite rows</a>'
            f' · <a href="{route}/projections.svg">particle phase planes</a>'
            f' · <a href="{route}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    offline = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline MPC-09 report</title>'
               f'<a href="{route}/index.html">Open the output-feedback report</a></html>').encode()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in [("index.html", offline)] + [
                (f"{route}/{name}", content) for name, content in sorted(generated.items())]:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
    index_path.write_text(page.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return route


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()

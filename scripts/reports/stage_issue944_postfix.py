"""Validate and stage the source-qualified post-fix issue #944 publication."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "issue944-strategy-a-each-choice-postfix-v1"
FILES = {
    "index.html", "pipeline-2d.svg", "pipeline-2d-mobile.svg", "pipeline-2d-print.svg",
    "terminal-membership-regression.svg", "terminal-membership-regression-mobile.svg",
    "terminal-membership-regression-print.svg", "records.json", "terminal-membership-regression.json",
    "role-matrix.csv", "provenance.json", "publication-provenance.json", "capture-SHA256SUMS",
    "checker.stdout.txt", "checker.stderr.txt", "records.stderr.txt", "terminal-membership-regression.stderr.txt",
    "SHA256SUMS",
}
EXAMPLE_FILES = {
    "qhull-highs-strategy-a-2d.html", "qhull-highs-strategy-a-2d.svg", "qhull-highs-strategy-a-2d-record.json",
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def verified_files(source: Path) -> None:
    if source.is_symlink() or not source.is_dir() or {item.name for item in source.iterdir()} != FILES:
        raise ValueError("#944 post-fix bundle inventory differs")
    checks = (source / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    listed = set()
    for line in checks:
        expected, name = line.split("  ", 1)
        if name not in FILES - {"SHA256SUMS"} or name in listed:
            raise ValueError("unexpected #944 post-fix checksum entry")
        listed.add(name)
        path = source / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("#944 post-fix checksum mismatch: " + name)
    if listed != FILES - {"SHA256SUMS"}:
        raise ValueError("#944 post-fix checksum inventory differs")
    capture_lines = (source / "capture-SHA256SUMS").read_text(encoding="ascii").splitlines()
    captured = set()
    for line in capture_lines:
        expected, name = line.split("  ", 1)
        if name in captured or name not in FILES - {"SHA256SUMS", "capture-SHA256SUMS"}:
            raise ValueError("unexpected preserved capture checksum entry")
        captured.add(name)
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("preserved capture checksum mismatch: " + name)
    if not {"records.json", "terminal-membership-regression.json", "provenance.json"} <= captured:
        raise ValueError("preserved numerical capture inputs are not checksum-bound")


def stage(source: Path, site_root: Path) -> str:
    source, site_root = Path(source), Path(site_root)
    verified_files(source)
    if site_root.is_symlink() or not site_root.is_dir():
        raise ValueError("an existing site directory is required")
    example = load_module(ROOT / "scripts/reports/qhull_highs_strategy_a_example.py", "issue944_postfix_example")
    generated = example.build()
    if set(generated) != EXAMPLE_FILES:
        raise ValueError("public Qhull example producer inventory differs")
    examples = site_root / "examples"
    if examples.is_symlink():
        raise ValueError("examples route must not be a symlink")
    examples.mkdir(exist_ok=True)
    design = load_module(ROOT / "scripts/reports/site_design.py", "issue944_postfix_site_design")
    stylesheet = design.stylesheet()
    style_path = examples / "examples.css"
    if style_path.exists() and style_path.is_symlink():
        raise ValueError("public example stylesheet must not be a symlink")
    style_path.write_bytes(stylesheet)
    for name, content in generated.items():
        destination = examples / name
        if destination.exists() and destination.is_symlink():
            raise ValueError("public example output must not be a symlink: " + name)
        data = content.encode("utf-8") if isinstance(content, str) else content
        destination.write_bytes(data)
    if examples.joinpath("qhull-highs-strategy-a-2d-record.json").read_bytes() != \
            (ROOT / "docs/examples/qhull-highs-strategy-a-2d-record.json").read_bytes():
        raise ValueError("staged Qhull example record differs from its source record")

    destination = site_root / REPORT_ID
    if destination.exists() or destination.is_symlink():
        raise ValueError("#944 post-fix Pages route must be fresh")
    shutil.copytree(source, destination, symlinks=False)
    local_files = FILES | {"../examples/" + name for name in EXAMPLE_FILES} | {
        "../issue944-strategy-a-each-choice-v1/index.html",
        "https://github.com/butahlecoq/controlled-systems-lab/issues/974",
    }
    site = load_module(ROOT / "scripts/reports/site.py", "issue944_postfix_offline_site")
    parser = site.OfflineHTML(local_files)
    parser.feed((destination / "index.html").read_text(encoding="utf-8"))
    for href in ("../examples/qhull-highs-strategy-a-2d.html", "../examples/qhull-highs-strategy-a-2d.svg",
                 "../examples/qhull-highs-strategy-a-2d-record.json"):
        resolved = (destination / href).resolve(strict=True)
        if not resolved.is_relative_to(site_root.resolve()):
            raise ValueError("#944 local example link escapes the staged site")
    old_report = (site_root / "issue944-strategy-a-each-choice-v1/index.html")
    if not old_report.is_file():
        raise ValueError("historical source-5a report must be staged before the follow-up")
    return REPORT_ID


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

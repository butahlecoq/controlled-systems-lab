"""Stage the saved Strategy A choice-pipeline report into an algorithm report site."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil

_site_spec = importlib.util.spec_from_file_location("issue944_report_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(_site_spec)
assert _site_spec.loader is not None
_site_spec.loader.exec_module(site)

REPORT_ID = "issue944-strategy-a-each-choice-v1"
FILES = {
    "index.html", "pipeline-2d.svg", "pipeline-2d-mobile.svg", "pipeline-2d-print.svg",
    "terminal-membership-regression.svg", "terminal-membership-regression-mobile.svg",
    "terminal-membership-regression-print.svg", "records.json",
    "terminal-membership-regression.json", "role-matrix.csv", "provenance.json", "SHA256SUMS",
}


def stage(source: Path, site_root: Path) -> str:
    source, site_root = Path(source), Path(site_root)
    if source.is_symlink() or not source.is_dir() or not site_root.is_dir():
        raise ValueError("report source and existing site directory are required")
    if {entry.name for entry in source.iterdir()} != FILES:
        raise ValueError("#944 report bundle inventory differs")
    for line in (source / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name not in FILES - {"SHA256SUMS"}:
            raise ValueError("unexpected #944 report checksum entry")
        path = source / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("#944 report checksum mismatch: " + name)
    if set(line.split("  ", 1)[1] for line in (source / "SHA256SUMS").read_text().splitlines()) != FILES - {"SHA256SUMS"}:
        raise ValueError("#944 report checksum inventory differs")
    for name in FILES - {"SHA256SUMS"}:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or unsafe #944 report asset: " + name)
    allowed = FILES | {"https://github.com/butahlecoq/controlled-systems-lab/pull/976"}
    site.OfflineHTML(allowed).feed((source / "index.html").read_text(encoding="utf-8"))
    destination = site_root / REPORT_ID
    if destination.exists() or destination.is_symlink():
        raise ValueError("#944 Pages route must be fresh")
    shutil.copytree(source, destination, symlinks=False)
    return REPORT_ID

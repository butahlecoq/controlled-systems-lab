"""Validate and stage the versioned ITIS17/QuickHull adaptation report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import zipfile

site_spec = importlib.util.spec_from_file_location(
    "algorithm_report_site", Path(__file__).with_name("site.py"))
site_module = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site_module)


REPORT_ID = "quickhull-it17-paper-adaptations-20261024-r1"
FILES = {
    "README.md", "build-config.txt", "build-flags.make", "build.log",
    "executable.sha256", "fixture-geometry.svg", "host-after.txt",
    "host-before.txt", "index.html", "paper-identities.txt",
    "preliminary_driver.cpp", "raw-capture.jsonl", "raw-rows.jsonl",
    "summarize.py", "summary.csv", "validation.txt",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle(source: Path) -> None:
    if source.is_symlink() or not source.is_dir() or source.name != REPORT_ID:
        raise ValueError("expected the versioned ITIS17 report directory")
    if {path.name for path in source.iterdir()} != FILES | {"SHA256SUMS"}:
        raise ValueError("report bundle inventory differs")
    entries = {}
    for line in (source / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  reports/algorithm-results/[^/]+/([^/]+)", line)
        if not match or match.group(2) in entries:
            raise ValueError("invalid or duplicate SHA256SUMS entry")
        entries[match.group(2)] = match.group(1)
    if set(entries) != FILES:
        raise ValueError("SHA256SUMS inventory differs")
    if any(digest(source / name) != sha for name, sha in entries.items()):
        raise ValueError("report bundle file hash mismatch")
    if "144 rows" not in (source / "validation.txt").read_text(encoding="utf-8"):
        raise ValueError("validated measurement count is absent")


def stage(source: Path, site_root: Path) -> str:
    validate_bundle(source)
    if not site_root.is_dir():
        raise ValueError("site root must already exist")
    destination = site_root / REPORT_ID
    archive_path = site_root / (REPORT_ID + ".zip")
    if destination.exists() or archive_path.exists():
        raise ValueError("versioned report route already exists")

    generated = (source / "index.html").read_bytes()
    site_module.OfflineHTML(FILES).feed(generated.decode("utf-8"))
    destination.mkdir()
    for name in sorted(FILES | {"SHA256SUMS"}):
        (destination / name).write_bytes((source / name).read_bytes())

    offline_index = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Offline hull adaptation report</title><h1>Offline report</h1>'
        f'<a href="{REPORT_ID}/index.html">{REPORT_ID}</a></html>'
    ).encode("utf-8")
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("index.html", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, offline_index)
        for name in sorted(FILES | {"SHA256SUMS"}):
            info = zipfile.ZipInfo(f"{REPORT_ID}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (source / name).read_bytes())

    index = site_root / "index.html"
    text = index.read_text(encoding="utf-8")
    if text.count("</ul>") != 1 or REPORT_ID in text:
        raise ValueError("site index insertion point differs")
    link = (
        f'<li><a href="{REPORT_ID}/index.html">QuickHull and ITIS17 LP hull methods</a>'
        ' — exploratory 2D comparison of six reducers on three exact square fixtures'
        f' · <a href="{REPORT_ID}/raw-rows.jsonl">raw rows</a>'
        f' · <a href="{REPORT_ID}.zip">offline bundle</a></li>'
    )
    site_module.OfflineHTML({f"{REPORT_ID}/index.html", f"{REPORT_ID}/raw-rows.jsonl",
                             f"{REPORT_ID}.zip"}).feed(link)
    index.write_text(text.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return REPORT_ID


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

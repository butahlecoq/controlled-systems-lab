"""Validate and stage the repeated EXP-02 dyadic ITIS17 pilot."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile

site_spec = importlib.util.spec_from_file_location(
    "algorithm_report_site", Path(__file__).with_name("site.py"))
site_module = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site_module)

REPORT_ID = "exp02-it17-dyadic-interior-20261027-r1"
REPORT_IDS = {
    REPORT_ID,
    "exp02-it17-a44-paper-order-20261027-r2",
}


def bundle_files(source: Path) -> set[str]:
    found = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are not allowed in a published bundle")
        if path.is_file() and path.name != "SHA256SUMS":
            found.add(path.relative_to(source).as_posix())
    return found


def validate_bundle(source: Path) -> None:
    report_id = source.name
    if source.is_symlink() or not source.is_dir() or report_id not in REPORT_IDS:
        raise ValueError("expected the versioned EXP-02 dyadic report directory")
    entries = {}
    for line in (source / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("invalid SHA256SUMS entry")
        name = match.group(2)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name in entries:
            raise ValueError("unsafe or duplicate SHA256SUMS path")
        entries[name] = match.group(1)
    if set(entries) != bundle_files(source):
        raise ValueError("SHA256SUMS inventory differs from the bundle")
    for name, expected in entries.items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("report bundle file hash mismatch: " + name)
    record = json.loads((source / "record.json").read_text(encoding="utf-8"))
    if record.get("report_id") != report_id or record.get("attempts") != 72:
        raise ValueError("report identity or attempt count differs")
    for page in sorted(path for path in source.rglob("*.html") if path.is_file()):
        page_assets = set()
        for candidate in source.rglob("*"):
            if candidate.is_file():
                try:
                    page_assets.add(candidate.relative_to(page.parent).as_posix())
                except ValueError:
                    continue
        site_module.OfflineHTML(page_assets).feed(page.read_text(encoding="utf-8"))
    for figure in sorted(path for path in source.rglob("*.svg") if path.is_file()):
        site_module.data.validate_svg(figure.read_bytes())


def stage(source: Path, site_root: Path) -> str:
    validate_bundle(source)
    report_id = source.name
    if not site_root.is_dir():
        raise ValueError("site root must already exist")
    destination = site_root / report_id
    archive_path = site_root / (report_id + ".zip")
    if destination.exists() or archive_path.exists():
        raise ValueError("versioned report route already exists")
    shutil.copytree(source, destination, symlinks=False)

    offline_index = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Offline EXP-02 pilot</title><h1>Offline report</h1>'
        f'<a href="{report_id}/index.html">{report_id}</a></html>'
    ).encode("utf-8")
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in [("index.html", offline_index)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
        for name in sorted(bundle_files(source) | {"SHA256SUMS"}):
            info = zipfile.ZipInfo(f"{report_id}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (source / name).read_bytes())

    index = site_root / "index.html"
    text = index.read_text(encoding="utf-8")
    if text.count("</ul>") != 1 or report_id in text:
        raise ValueError("site index insertion point differs")
    title = ("QuickHull and ITIS17 A44 source-aligned rerun" if report_id.endswith("-r2")
             else "QuickHull and ITIS17 dyadic hull pilot")
    link = (
        f'<li><a href="{report_id}/index.html">{title}</a>'
        ' — repeated exploratory 2D comparison on two interior-heavy square clouds'
        f' · <a href="{report_id}/summary.csv">measured table</a>'
        f' · <a href="{report_id}.zip">offline bundle</a></li>'
    )
    site_module.OfflineHTML({
        f"{report_id}/index.html", f"{report_id}/summary.csv", report_id + ".zip"
    }).feed(link)
    index.write_text(text.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

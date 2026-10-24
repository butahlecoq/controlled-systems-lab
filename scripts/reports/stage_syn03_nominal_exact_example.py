"""Stage the saved Strategy A nominal linear exact 2D example for Pages."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import shutil

site_spec = importlib.util.spec_from_file_location("nominal_exact_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


REPORT_ID = "syn03-nominal-exact-2d-example"
FILES = {"README.md", "index.html", "optimal-face.svg", "records.json"}


def stage(source: Path, site_root: Path) -> str:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("nominal exact 2D example bundle required")
    if {path.name for path in source.iterdir()} != FILES | {"SHA256SUMS"}:
        raise ValueError("nominal exact example bundle inventory differs")
    for line in (source / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name not in FILES:
            raise ValueError("unexpected nominal exact example checksum entry")
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError("nominal exact example checksum mismatch: " + name)
    for name in FILES:
        if (source / name).is_symlink() or not (source / name).is_file():
            raise ValueError("missing or unsafe nominal exact example file: " + name)
    site.OfflineHTML(FILES | {"../examples/index.html"}).feed(
        (source / "index.html").read_text(encoding="utf-8"))
    destination = site_root / REPORT_ID
    if not site_root.is_dir() or destination.exists():
        raise ValueError("site must exist and the nominal exact example route must be fresh")
    shutil.copytree(source, destination, symlinks=False)
    return REPORT_ID


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
        default=Path(__file__).resolve().parents[2] / "reports/algorithm-results" / REPORT_ID)
    parser.add_argument("--site", type=Path, required=True)
    arguments = parser.parse_args()
    print(stage(arguments.source, arguments.site))

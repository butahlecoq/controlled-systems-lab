"""Stage the immutable sampled Lotka–Volterra illustration for Pages."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lotka_volterra_report", Path(__file__).with_name("lotka_volterra_sampled.py"))
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location("lotka_volterra_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def stage(source: Path, site_root: Path) -> str:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("sampled example bundle required")
    report.build(source, None, True)
    files = {path.name for path in source.iterdir()}
    site.OfflineHTML(files | {"../examples/index.html"}).feed(
        (source / "index.html").read_text(encoding="utf-8"))
    destination = site_root / report.REPORT_ID
    if not site_root.is_dir() or destination.exists():
        raise ValueError("site must exist and the sampled example route must be fresh")
    shutil.copytree(source, destination, symlinks=False)
    return report.REPORT_ID


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=report.REPORT_DIR)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

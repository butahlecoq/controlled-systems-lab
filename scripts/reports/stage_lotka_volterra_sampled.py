"""Stage the immutable sampled Lotka–Volterra illustration for Pages."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

FROZEN_GENERATOR_SHA256 = "321ac099e8185c8b1b9a76af9859c9b818682b429ba705f1410a19d648238f1c"


def _load_sibling(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise ImportError(f"Sampled Lotka publication requires {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = _load_sibling("lotka_volterra_report", "lotka_volterra_sampled.py")
frozen_report = _load_sibling(
    "lotka_volterra_frozen_report", "lotka_volterra_sampled_frozen_321ac099.py"
)
site = _load_sibling("lotka_volterra_site", "site.py")


def stage(source: Path, site_root: Path) -> str:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("sampled example bundle required")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    producer = (
        frozen_report if manifest.get("generator_sha256") == FROZEN_GENERATOR_SHA256 else report
    )
    producer.build(source, None, True)
    files = {path.name for path in source.iterdir()}
    site.OfflineHTML(files | {"../examples/index.html"}).feed(
        (source / "index.html").read_text(encoding="utf-8")
    )
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

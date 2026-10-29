"""Stage the saved bounded EXP-06 geometry pilot on the algorithm report site."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
spec = importlib.util.spec_from_file_location(
    "exp06_saved_renderer", ROOT / "scripts/reports/exp06/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "exp06_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_bundle(bundle: Path) -> str:
    rendered, report_id = report.render(bundle)
    for name, data in rendered.items():
        if (bundle / name).read_bytes() != data:
            raise ValueError("saved EXP-06 renderer differs: " + name)
    manifest = report.strict_json(bundle / "manifest.json")
    expected = {name: sha(data) for name, data in rendered.items()}
    for name in ("comparison-record.json", "capture.json", "pack-request.json", "packer.stdout", "packer.stderr"):
        expected[name] = sha((bundle / name).read_bytes())
    for directory in ("raw-attempts", "fixture"):
        for path in sorted((bundle / directory).glob("*")):
            expected[directory + "/" + path.name] = sha(path.read_bytes())
    if manifest != {"schema": "csl.exp06-report-manifest/1", "report_id": report_id, "files": expected}:
        raise ValueError("EXP-06 file hash manifest differs")
    inventory = set(expected) | {"manifest.json"}
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    if actual != inventory:
        raise ValueError("EXP-06 report inventory differs")
    for name in ("index.html", "hulls.svg"):
        site.OfflineHTML(inventory).feed((bundle / name).read_text(encoding="utf-8"))
    return report_id


def stage(source: Path, site_dir: Path) -> str:
    report_id = validate_bundle(source)
    destination = site_dir / report_id
    if not site_dir.is_dir() or site_dir.is_symlink() or destination.exists():
        raise ValueError("EXP-06 route must be staged into a fresh site directory")
    shutil.copytree(source, destination)
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    if index.count("</ul>") != 1 or report_id in index:
        raise ValueError("algorithm report index insertion point differs")
    link = (f'<li><a href="{escape(report_id)}/index.html">EXP-06 bounded geometry pilot</a>'
            f' · <a href="{escape(report_id)}/hulls.svg">2D hull illustration</a>'
            f' · <a href="{escape(report_id)}/comparison-record.json">paired record</a></li>')
    site.OfflineHTML({report_id + "/index.html", report_id + "/hulls.svg",
                      report_id + "/comparison-record.json"}).feed(link)
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))

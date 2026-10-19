"""Stage the reviewed EXT-05 bundle and link its 2D example on Pages."""
from __future__ import annotations

import argparse
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ext05_saved_renderer", ROOT / "scripts/reports/ext05/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "ext05_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def catalog_entry(bundle: Path) -> dict:
    details = report.render(bundle, check=True)
    allowed = set((*report.collect.SOURCE_FILES, "records.json", *report.RENDERED,
                   "manifest.json", bundle.name + ".zip"))
    report.collect.require({path.name for path in bundle.iterdir()} == allowed,
                           "EXT-05 saved inventory differs")
    for name in ("index.html", "example-2d.html"):
        site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
    return {**details, "schema": "csl.ext05-discretization-report/1",
            "renderer_sha256": report.collect.sha(
                (ROOT / "scripts/reports/ext05/render_saved.py").read_bytes()),
            "stager_sha256": report.collect.sha(Path(__file__).read_bytes())}


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.ext05-publications/1" and
                           isinstance(data.get("reports"), list) and len(data["reports"]) == 1,
                           "EXT-05 publication catalog differs")
    entry = data["reports"][0]
    report_id = entry["report_id"]
    report.collect.require(report_id.startswith("ext05-discretization-") and
                           len(report_id) == len("ext05-discretization-") + 16 and
                           all(ch in "0123456789abcdef" for ch in report_id[-16:]),
                           "Unsafe EXT-05 report ID")
    bundle = catalog.parent / report_id
    report.collect.require(entry == catalog_entry(bundle),
                           "EXT-05 catalog differs from saved evidence")
    destination = site_dir / report_id
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists(), "EXT-05 site route must be fresh")
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and report_id not in index,
                           "EXT-05 site insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">EXT-05 continuous-model discretization</a>'
            ' — 2D double integrator and 700 verified measured calls'
            ' · <a href="' + escape(report_id) + '/example-2d.html">2D visual example</a>'
            ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(report_id) + '/' + escape(report_id) + '.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id + "/index.html", report_id + "/example-2d.html",
                      report_id + "/records.json", report_id + "/" + report_id + ".zip"}).feed(link)
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.ext05-publications/1",
                          "reports": [catalog_entry(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

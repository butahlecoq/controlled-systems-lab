"""Stage one reviewed content-bound APP-04 report and its 2D example."""
from __future__ import annotations

import argparse
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "app04_saved_renderer", ROOT / "scripts/reports/app04/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "app04_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def catalog_entry(bundle: Path) -> dict:
    report.render(bundle, check=True)
    record = report.validate(bundle)
    expected = set((*report.collect.SOURCE_FILES, *report.RENDERED, "manifest.json"))
    report.collect.require({path.name for path in bundle.iterdir()} == expected,
                           "APP-04 saved inventory differs")
    site.OfflineHTML(expected | {"../" + bundle.name + ".zip"}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    site.OfflineHTML(expected | {"../" + bundle.name + ".zip"}).feed(
        (bundle / "example-2d.html").read_text(encoding="utf-8"))
    return {"report_id": record["report_id"], "source_commit": record["source_commit"],
            "schema": record["schema"],
            "manifest_sha256": report.collect.sha((bundle / "manifest.json").read_bytes()),
            "zip_sha256": report.collect.sha(
                (bundle.parent / (bundle.name + ".zip")).read_bytes()),
            "renderer_sha256": report.collect.sha(
                (ROOT / "scripts/reports/app04/render_saved.py").read_bytes()),
            "stager_sha256": report.collect.sha(Path(__file__).read_bytes())}


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.app04-publications/1" and
                           isinstance(data.get("reports"), list) and len(data["reports"]) == 1,
                           "APP-04 publication catalog differs")
    report_id = data["reports"][0]["report_id"]
    report.collect.require(report_id.startswith("app04-ellipsoid-") and
                           len(report_id) == len("app04-ellipsoid-") + 16 and
                           all(ch in "0123456789abcdef" for ch in report_id[-16:]),
                           "Unsafe APP-04 report ID")
    bundle = catalog.parent / report_id
    report.collect.require(data["reports"][0] == catalog_entry(bundle),
                           "APP-04 catalog differs from saved evidence")
    destination = site_dir / report_id
    zip_destination = site_dir / (report_id + ".zip")
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists() and
                           not zip_destination.exists(), "APP-04 routes must be fresh")
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    zip_destination.write_bytes((bundle.parent / (report_id + ".zip")).read_bytes())
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and report_id not in index,
                           "APP-04 site insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">APP-04 directional ellipsoid report</a>'
            ' — three planar cases and 2,100 verified measured calls'
            ' · <a href="' + escape(report_id) + '/example-2d.html">2D visual example</a>'
            ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(report_id) + '.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id + "/index.html", report_id + "/example-2d.html",
                      report_id + "/records.json", report_id + ".zip"}).feed(link)
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.app04-publications/1",
                          "reports": [catalog_entry(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

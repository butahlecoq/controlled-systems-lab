"""Stage the reviewed, content-bound GEO-08 report on the static site."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "geo08_saved_renderer", ROOT / "scripts/reports/geo08/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "geo08_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def catalog_entry(bundle: Path) -> dict:
    report.render(bundle, check=True)
    record = report.validate(bundle)
    expected = set(report.expected_files(bundle))
    report.collect.require({path.name for path in bundle.iterdir()} == expected,
                           "GEO-08 saved inventory differs")
    for name in ("index.html", "example-2d.html"):
        site.OfflineHTML(expected).feed((bundle / name).read_text(encoding="utf-8"))
    return {"report_id": record["report_id"], "source_commit": record["source_commit"],
            "schema": record["schema"],
            "manifest_sha256": sha((bundle / "manifest.json").read_bytes()),
            "zip_sha256": sha((bundle / "bundle.zip").read_bytes()),
            "renderer_sha256": sha((ROOT / "scripts/reports/geo08/render_saved.py").read_bytes()),
            "stager_sha256": sha(Path(__file__).read_bytes())}


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.geo08-publications/1" and
                           isinstance(data.get("reports"), list) and len(data["reports"]) == 1,
                           "GEO-08 publication catalog differs")
    report_id = data["reports"][0]["report_id"]
    report.collect.require(report_id.startswith("geo08-lazy-") and
                           len(report_id) == len("geo08-lazy-") + 16 and
                           all(char in "0123456789abcdef" for char in report_id[-16:]),
                           "Unsafe GEO-08 report ID")
    bundle = catalog.parent / report_id
    report.collect.require(data["reports"][0] == catalog_entry(bundle),
                           "GEO-08 catalog differs from saved evidence")
    destination = site_dir / report_id
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists(), "GEO-08 route must be fresh")
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and report_id not in index,
                           "GEO-08 site insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">GEO-08 lazy geometry report</a>'
            ' — checked planar expression, support and materialization'
            ' · <a href="' + escape(report_id) + '/example-2d.html">2D visual example</a>'
            ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(report_id) + '/bundle.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id + "/index.html", report_id + "/example-2d.html",
                      report_id + "/records.json", report_id + "/bundle.zip"}).feed(link)
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.geo08-publications/1",
                          "reports": [catalog_entry(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

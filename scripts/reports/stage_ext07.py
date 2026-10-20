"""Stage the reviewed EXT-07 report and its standalone 2D example on Pages."""
from __future__ import annotations

import argparse
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ext07_saved_renderer", ROOT / "scripts/reports/ext07/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "ext07_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)
two_spec = importlib.util.spec_from_file_location(
    "ext07_two_parameter_saved_renderer",
    ROOT / "scripts/reports/ext07/two_parameter_render_saved.py")
two_parameter_report = importlib.util.module_from_spec(two_spec)
assert two_spec.loader is not None
two_spec.loader.exec_module(two_parameter_report)


def catalog_entry(bundle: Path) -> dict:
    if bundle.name.startswith("ext07-hybrid-two-parameter-"):
        details = two_parameter_report.render(bundle, check=True)
        allowed = set((*two_parameter_report.collect.SOURCE_FILES, "records.json",
                       *two_parameter_report.RENDERED, "manifest.json",
                       bundle.name + ".zip"))
        two_parameter_report.collect.require(
            {path.name for path in bundle.iterdir()} == allowed,
            "EXT-07 two-parameter saved inventory differs")
        for name in ("index.html", "two-control-example.html"):
            site.OfflineHTML(allowed).feed(
                (bundle / name).read_text(encoding="utf-8"))
        return {**details,
                "schema": "csl.ext07-hybrid-two-parameter-report/1",
                "collector_sha256": two_parameter_report.collect.sha(
                    (ROOT / "scripts/reports/ext07/two_parameter_collect.py").read_bytes()),
                "renderer_sha256": two_parameter_report.collect.sha(
                    (ROOT / "scripts/reports/ext07/two_parameter_render_saved.py").read_bytes()),
                "stager_sha256": two_parameter_report.collect.sha(
                    Path(__file__).read_bytes())}
    details = report.render(bundle, check=True)
    allowed = set((*report.collect.SOURCE_FILES, "records.json", *report.RENDERED,
                   "manifest.json", bundle.name + ".zip"))
    report.collect.require({path.name for path in bundle.iterdir()} == allowed,
                           "EXT-07 saved inventory differs")
    for name in ("index.html", "example-2d.html"):
        site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
    return {**details, "schema": "csl.ext07-hybrid-profile-report/1",
            "collector_sha256": report.collect.sha(
                (ROOT / "scripts/reports/ext07/ext07_collect.py").read_bytes()),
            "renderer_sha256": report.collect.sha(
                (ROOT / "scripts/reports/ext07/render_saved.py").read_bytes()),
            "stager_sha256": report.collect.sha(Path(__file__).read_bytes())}


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.ext07-publications/1" and
                           isinstance(data.get("reports"), list) and data["reports"],
                           "EXT-07 publication catalog differs")
    site_dir = Path(site_dir)
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           index.count("</ul>") == 1,
                           "EXT-07 Pages index insertion point differs")
    report_ids = []
    routes = []
    staged_bundles = []
    for entry in data["reports"]:
        report_id = entry["report_id"]
        if report_id.startswith("ext07-hybrid-two-parameter-"):
            prefix = "ext07-hybrid-two-parameter-"
            example = "two-control-example.html"
            label = "EXT-07 two-parameter verifier; 140 measured calls"
        else:
            prefix = "ext07-hybrid-"
            example = "example-2d.html"
            label = "EXT-07 one-step scalar verifier; 140 measured calls"
        report.collect.require(report_id.startswith(prefix) and
                               len(report_id) == len(prefix) + 16 and
                               all(char in "0123456789abcdef" for char in report_id[-16:]) and
                               report_id not in index and report_id not in report_ids,
                               "Unsafe or duplicate EXT-07 report ID")
        bundle = catalog.parent / report_id
        report.collect.require(entry == catalog_entry(bundle),
                               "EXT-07 publication catalog differs from saved evidence")
        destination = site_dir / report_id
        report.collect.require(not destination.exists(),
                               "EXT-07 Pages route must be fresh")
        allowed = {path.name for path in bundle.iterdir()}
        route = ('<li><a href="' + escape(report_id) + '/index.html">' + label + '</a>'
                 ' · <a href="' + escape(report_id) + '/' + example + '">2D example</a>'
                 ' · <a href="' + escape(report_id) + '/records.json">raw record</a>'
                 ' · <a href="' + escape(report_id) + '/' + escape(report_id) +
                 '.zip">offline ZIP</a></li>')
        site.OfflineHTML({report_id + "/index.html", report_id + "/" + example,
                          report_id + "/records.json",
                          report_id + "/" + report_id + ".zip"}).feed(route)
        for name in ("index.html", example):
            site.OfflineHTML(allowed).feed(
                (bundle / name).read_text(encoding="utf-8"))
        staged_bundles.append((report_id, bundle,
                               {path.name: path.read_bytes() for path in bundle.iterdir()}))
        report_ids.append(report_id)
        routes.append(route)
    # Do not leave earlier routes behind when a later catalog entry is invalid.
    for report_id, bundle, files in staged_bundles:
        destination = site_dir / report_id
        report.collect.require(not destination.exists(),
                               "EXT-07 Pages route must be fresh")
        destination.mkdir()
        for name, content in files.items():
            (destination / name).write_bytes(content)
    report.collect.require(index.count("</ul>") == 1,
                           "EXT-07 Pages index insertion point differs")
    index_path.write_text(index.replace("</ul>", "".join(routes) + "</ul>"),
                          encoding="utf-8")
    return report_ids[0] if len(report_ids) == 1 else ",".join(report_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.ext07-publications/1",
                          "reports": [catalog_entry(path) for path in args.source]},
                         sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

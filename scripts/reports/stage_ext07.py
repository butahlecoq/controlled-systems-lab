"""Stage the reviewed EXT-07 report and its standalone 2D example on Pages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_STAGER_SHA256 = "5a8803e9f51ae96b61342d7470c7ba4ce74a4232a49a9ec1a875037ed90ae434"
# These exact saved manifests were admitted by the original stager.
HISTORICAL_MANIFEST_SHA256 = {
    "4699fb473b04daa04f35141489ba39914bc91cf0870f88cf1b774977dcd429df",
    "eff251f06895cb801429b52ccfeda085f7016134bbd92719aee94ad8e3a5dcbf",
    "0f07aee507bd028410fe1b37c51bf7c2dc32baf8b7bd0b7cd80c2b2b61076dea",
    "341de72cf4c6c4d0c6d541cff7e67108386049537972527138ab95f675e47d6f",
    "0c76939bf36b4548d53c68c1a90b5226d6602ca3e4842e5589134f312193496c",
    "f8e0b6e7cef02a6056b19bc4ccefc90bdf80a3ae15159d77f1c67dc44928e830",
    "276f73009adeba343e659a80928f4f61731331c413bd27b3e1be00df769d4d96",
    "37e39e02799831c597118453ae00c6569a35fed569fc7cbd3f808094dc9af023",
    "a57b3c52cc012702a536f184bd81a0ea363fb198286caeda35b9d4645c3b7e26",
    "b7dd21b9ecd0405a3ddbb209121ae4f3fdc412e7ff595bef24a252f47087cbce",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"EXT-07 publication module could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = _load_module("ext07_saved_renderer", ROOT / "scripts/reports/ext07/render_saved.py")
site = _load_module("ext07_site_validator", Path(__file__).with_name("site.py"))
two_parameter_report = _load_module(
    "ext07_two_parameter_saved_renderer",
    ROOT / "scripts/reports/ext07/two_parameter_render_saved.py",
)
resource_report = _load_module(
    "ext07_resource_observation", ROOT / "scripts/reports/ext07/resource_observation.py"
)


def _stager_sha256(manifest_sha256: str) -> str:
    if manifest_sha256 in HISTORICAL_MANIFEST_SHA256:
        return HISTORICAL_STAGER_SHA256
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def catalog_entry(bundle: Path) -> dict:
    if bundle.name.startswith("ext07-resource-observation-"):
        details = resource_report.render(bundle, check=True)
        allowed = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        for name in ("index.html",):
            site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
        return {
            **details,
            "schema": "csl.ext07-resource-observation/1",
            "collector_sha256": resource_report.sha(
                (ROOT / "scripts/reports/ext07/resource_observation.py").read_bytes()
            ),
            "stager_sha256": _stager_sha256(details["manifest_sha256"]),
        }
    if bundle.name.startswith("ext07-hybrid-two-parameter-"):
        details = two_parameter_report.render(bundle, check=True)
        record = two_parameter_report.validate(bundle)
        source_files = two_parameter_report.collect.source_files_for_record(record)
        allowed = set(
            (
                *source_files,
                "records.json",
                *two_parameter_report.RENDERED,
                "manifest.json",
                bundle.name + ".zip",
            )
        )
        two_parameter_report.collect.require(
            {path.name for path in bundle.iterdir()} == allowed,
            "EXT-07 two-parameter saved inventory differs",
        )
        for name in ("index.html", "two-control-example.html"):
            site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
        return {
            **details,
            "schema": record["schema"],
            "verifier_id": record["measurement"]["trials"][0]["verifier"],
            "collector_sha256": two_parameter_report.collect.sha(
                (ROOT / "scripts/reports/ext07/two_parameter_collect.py").read_bytes()
            ),
            "renderer_sha256": two_parameter_report.collect.sha(
                (ROOT / "scripts/reports/ext07/two_parameter_render_saved.py").read_bytes()
            ),
            "stager_sha256": _stager_sha256(details["manifest_sha256"]),
        }
    details = report.render(bundle, check=True)
    record = report.validate(bundle)
    source_files = report.collect.source_files_for_record(record)
    allowed = set(
        (*source_files, "records.json", *report.RENDERED, "manifest.json", bundle.name + ".zip")
    )
    report.collect.require(
        {path.name for path in bundle.iterdir()} == allowed, "EXT-07 saved inventory differs"
    )
    for name in ("index.html", "example-2d.html"):
        site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
    return {
        **details,
        "schema": record["schema"],
        "collector_sha256": report.collect.sha(
            (ROOT / "scripts/reports/ext07/ext07_collect.py").read_bytes()
        ),
        "renderer_sha256": report.collect.sha(
            (ROOT / "scripts/reports/ext07/render_saved.py").read_bytes()
        ),
        "stager_sha256": _stager_sha256(details["manifest_sha256"]),
    }


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(
        data.get("schema") == "csl.ext07-publications/1"
        and isinstance(data.get("reports"), list)
        and data["reports"],
        "EXT-07 publication catalog differs",
    )
    site_dir = Path(site_dir)
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(
        site_dir.is_dir() and not site_dir.is_symlink() and index.count("</ul>") == 1,
        "EXT-07 Pages index insertion point differs",
    )
    report_ids = []
    routes = []
    hybrid_route_indices = []
    related_links = []
    staged_bundles = []
    for entry in data["reports"]:
        report_id = entry["report_id"]
        related = report_id.startswith("ext07-resource-observation-")
        if report_id.startswith("ext07-resource-observation-"):
            prefix = "ext07-resource-observation-"
            example = "resource-scope.svg"
            label = "EXT-07 bounded resource observations; two profiles"
            example_label = "resource plot"
        elif report_id.startswith("ext07-hybrid-two-parameter-"):
            prefix = "ext07-hybrid-two-parameter-"
            example = "two-control-example.html"
            label = (
                "EXT-07 exact-H solver capacity; 350 calls, up to 16 tied paths"
                if entry.get("schema") == "csl.ext07-hybrid-two-parameter-report/5"
                else "EXT-07 " + entry["verifier_id"] + "; 140 measured calls"
            )
            example_label = "2D example"
        else:
            prefix = "ext07-hybrid-"
            example = "example-2d.html"
            label = "EXT-07 one-step scalar verifier; 140 measured calls"
            example_label = "2D example"
        report.collect.require(
            report_id.startswith(prefix)
            and len(report_id) == len(prefix) + 16
            and all(char in "0123456789abcdef" for char in report_id[-16:])
            and report_id not in index
            and report_id not in report_ids,
            "Unsafe or duplicate EXT-07 report ID",
        )
        bundle = catalog.parent / report_id
        report.collect.require(
            entry == catalog_entry(bundle), "EXT-07 publication catalog differs from saved evidence"
        )
        destination = site_dir / report_id
        report.collect.require(not destination.exists(), "EXT-07 Pages route must be fresh")
        allowed = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        route = (
            '<li><a href="' + escape(report_id) + '/index.html">' + label + "</a>"
            ' · <a href="' + escape(report_id) + "/" + example + '">' + example_label + "</a>"
            ' · <a href="' + escape(report_id) + '/records.json">raw record</a>'
            ' · <a href="'
            + escape(report_id)
            + "/"
            + escape(report_id)
            + '.zip">offline ZIP</a></li>'
        )
        if related:
            route = (
                '<a href="' + escape(report_id) + '/index.html">' + label + "</a>"
                ' · <a href="' + escape(report_id) + "/" + example + '">' + example_label + "</a>"
            )
            site.OfflineHTML({report_id + "/index.html", report_id + "/" + example}).feed(route)
            related_links.append(route)
        else:
            site.OfflineHTML(
                {
                    report_id + "/index.html",
                    report_id + "/" + example,
                    report_id + "/records.json",
                    report_id + "/" + report_id + ".zip",
                }
            ).feed(route)
            if prefix in ("ext07-hybrid-", "ext07-hybrid-two-parameter-"):
                hybrid_route_indices.append(len(routes))
        for name in ("index.html", example):
            site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
        staged_bundles.append(
            (
                report_id,
                {
                    path.relative_to(bundle).as_posix(): path.read_bytes()
                    for path in bundle.rglob("*")
                    if path.is_file() and not path.is_symlink()
                },
            )
        )
        report_ids.append(report_id)
        routes.append(route)
    report.collect.require(
        not related_links or hybrid_route_indices,
        "EXT-07 resource observations require a hybrid report route",
    )
    if related_links:
        for route_index in hybrid_route_indices:
            routes[route_index] = routes[route_index].replace(
                "</li>", " · " + " · ".join(related_links) + "</li>"
            )
    # Do not leave earlier routes behind when a later catalog entry is invalid.
    for report_id, files in staged_bundles:
        destination = site_dir / report_id
        report.collect.require(not destination.exists(), "EXT-07 Pages route must be fresh")
        destination.mkdir()
        for name, content in files.items():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
    report.collect.require(index.count("</ul>") == 1, "EXT-07 Pages index insertion point differs")
    index = index.replace("</ul>", "".join(routes) + "</ul>")
    index_path.write_text(index, encoding="utf-8")
    return report_ids[0] if len(report_ids) == 1 else ",".join(report_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(
            json.dumps(
                {
                    "schema": "csl.ext07-publications/1",
                    "reports": [catalog_entry(path) for path in args.source],
                },
                sort_keys=True,
                indent=2,
            )
        )
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

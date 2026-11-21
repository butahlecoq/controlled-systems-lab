"""Stage the reviewed OPT-10 bundle and link its 2D example on Pages."""

from __future__ import annotations

import argparse
import importlib.util
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_REPORT_ID = "opt10-smooth-188130d94d7bf2de"
HISTORICAL_MANIFEST_SHA256 = "a055711b30a6823cc01a7ee1b3571d644dca79344408c2141c2c51c800b66851"
HISTORICAL_ZIP_SHA256 = "7ae9ea3675e9fc52aedcc4d4f6ce710f871fff07ea5bb073896dfc9f9641daeb"
HISTORICAL_RENDERER_SHA256 = "8c42e70b58aeb7c5921629d7d658d860bfe90375f349b597f69914ad75b2bcb8"
HISTORICAL_STAGER_SHA256 = "b34daa0c11454d725f393ee6ea6ac87fc176d9977bf9b77dc3351d07556e8b9a"
spec = importlib.util.spec_from_file_location(
    "opt10_saved_renderer", ROOT / "scripts/reports/opt10/render_saved.py"
)
if spec is None or spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "opt10_site_validator", Path(__file__).with_name("site.py")
)
if site_spec is None or site_spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
site = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(site)


def catalog_entry(bundle: Path) -> dict:
    details = report.render(bundle, check=True)
    allowed = set(
        (
            *report.collect.SOURCE_FILES,
            "records.json",
            *report.RENDERED,
            "manifest.json",
            bundle.name + ".zip",
        )
    )
    report.collect.require(
        {path.name for path in bundle.iterdir()} == allowed, "OPT-10 saved inventory differs"
    )
    for name in ("index.html", "example-2d.html"):
        site.OfflineHTML(allowed).feed((bundle / name).read_text(encoding="utf-8"))
    entry = {
        **details,
        "schema": "csl.opt10-smooth-convex-report/1",
        "renderer_sha256": report.collect.sha(
            (ROOT / "scripts/reports/opt10/render_saved.py").read_bytes()
        ),
        "stager_sha256": report.collect.sha(Path(__file__).read_bytes()),
    }
    if entry["report_id"] == HISTORICAL_REPORT_ID:
        report.collect.require(
            entry["manifest_sha256"] == HISTORICAL_MANIFEST_SHA256
            and entry["zip_sha256"] == HISTORICAL_ZIP_SHA256,
            "Historical saved report manifest or ZIP checksum differs",
        )
        entry["renderer_sha256"] = HISTORICAL_RENDERER_SHA256
        entry["stager_sha256"] = HISTORICAL_STAGER_SHA256
    return entry


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(
        data.get("schema") == "csl.opt10-publications/1"
        and isinstance(data.get("reports"), list)
        and len(data["reports"]) == 1,
        "OPT-10 publication catalog differs",
    )
    entry = data["reports"][0]
    report_id = entry["report_id"]
    report.collect.require(
        report_id.startswith("opt10-smooth-")
        and len(report_id) == len("opt10-smooth-") + 16
        and all(ch in "0123456789abcdef" for ch in report_id[-16:]),
        "Unsafe OPT-10 report ID",
    )
    bundle = catalog.parent / report_id
    report.collect.require(
        entry == catalog_entry(bundle), "OPT-10 catalog differs from saved evidence"
    )
    destination = site_dir / report_id
    report.collect.require(
        site_dir.is_dir() and not site_dir.is_symlink() and not destination.exists(),
        "OPT-10 site route must be fresh",
    )
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(
        index.count("</ul>") == 1 and report_id not in index, "OPT-10 site insertion point differs"
    )
    link = (
        '<li><a href="'
        + escape(report_id)
        + '/index.html">OPT-10 declared smooth-convex adapter</a>'
        " — 2D box quadratic and 700 verified measured calls"
        ' · <a href="' + escape(report_id) + '/example-2d.html">2D visual example</a>'
        ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
        ' · <a href="' + escape(report_id) + "/" + escape(report_id) + '.zip">offline ZIP</a></li>'
    )
    site.OfflineHTML(
        {
            report_id + "/index.html",
            report_id + "/example-2d.html",
            report_id + "/records.json",
            report_id + "/" + report_id + ".zip",
        }
    ).feed(link)
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
        print(
            json.dumps(
                {"schema": "csl.opt10-publications/1", "reports": [catalog_entry(args.source)]},
                sort_keys=True,
                indent=2,
            )
        )
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")

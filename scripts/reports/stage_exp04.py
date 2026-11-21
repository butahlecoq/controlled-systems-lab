"""Stage one saved, immutable EXP-04 report into the main-only Pages site."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_REPORT_ID = "exp04-replay-93fe3b87795e1d3a"
HISTORICAL_MANIFEST_SHA256 = "b62c04246047f4c4aa9fb257c83eb1e5e0827170d35ccb51efea57f40b630e71"
HISTORICAL_ZIP_SHA256 = "f9994f627b8928fb7ec8ac286ae90db6c0f9fc8b3ff749454f1e4b80b2af0d66"
HISTORICAL_STAGER_SHA256 = "546ad0a0a8e54a55c8b8374be20fd90d8c3edf63eee21048505e349edc694fcf"
spec = importlib.util.spec_from_file_location(
    "exp04_saved_renderer", ROOT / "scripts/reports/exp04/render_saved.py"
)
if spec is None or spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "exp04_site_validator", Path(__file__).with_name("site.py")
)
if site_spec is None or site_spec.loader is None:
    raise ImportError("Cannot load the saved report dependency")
site = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(site)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def catalog_entry(bundle: Path) -> dict:
    report.render(bundle, check=True)
    record = report.validate(bundle)
    expected = set(report.expected_files(bundle))
    report.collect.require(
        {path.name for path in bundle.iterdir()} == expected, "EXP-04 source inventory differs"
    )
    site.OfflineHTML(expected).feed((bundle / "index.html").read_text(encoding="utf-8"))
    entry = {
        "report_id": record["report_id"],
        "source_commit": record["source_commit"],
        "schema": record["schema"],
        "manifest_sha256": sha((bundle / "manifest.json").read_bytes()),
        "zip_sha256": sha((bundle / "bundle.zip").read_bytes()),
        "renderer_sha256": sha((ROOT / "scripts/reports/exp04/render_saved.py").read_bytes()),
        "stager_sha256": sha(Path(__file__).read_bytes()),
    }
    if entry["report_id"] == HISTORICAL_REPORT_ID:
        report.collect.require(
            entry["manifest_sha256"] == HISTORICAL_MANIFEST_SHA256
            and entry["zip_sha256"] == HISTORICAL_ZIP_SHA256,
            "Historical saved report manifest or ZIP checksum differs",
        )
        entry["stager_sha256"] = HISTORICAL_STAGER_SHA256
    return entry


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(
        data.get("schema") == "csl.exp04-publications/1"
        and isinstance(data.get("reports"), list)
        and len(data["reports"]) == 1,
        "EXP-04 extension catalog differs",
    )
    report_id = data["reports"][0]["report_id"]
    report.collect.require(
        report_id.startswith("exp04-replay-") and len(report_id) == len("exp04-replay-") + 16,
        "unsafe EXP-04 report ID",
    )
    bundle = catalog.parent / report_id
    report.collect.require(
        data["reports"][0] == catalog_entry(bundle),
        "EXP-04 extension catalog differs from saved source",
    )
    destination = site_dir / report_id
    report.collect.require(
        site_dir.is_dir() and not site_dir.is_symlink() and not destination.exists(),
        "EXP-04 public route must be fresh",
    )
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(
        index.count("</ul>") == 1 and report_id not in index,
        "EXP-04 site catalogue insertion point differs",
    )
    link = (
        '<li><a href="' + escape(report_id) + '/index.html">EXP-04 independent plant replay</a>'
        " — four analytic histories, 28,000 verified measured calls; no historical B04 or"
        ' speedup claim · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
        ' · <a href="' + escape(report_id) + '/measure.csv">raw trials</a>'
        ' · <a href="' + escape(report_id) + '/bundle.zip">offline ZIP</a></li>'
    )
    site.OfflineHTML(
        {
            report_id + "/index.html",
            report_id + "/records.json",
            report_id + "/measure.csv",
            report_id + "/bundle.zip",
        }
    ).feed(link)
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(
            json.dumps(
                {"schema": "csl.exp04-publications/1", "reports": [catalog_entry(args.source)]},
                sort_keys=True,
                indent=2,
            )
        )
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("use --source alone, or --catalog and --site")


if __name__ == "__main__":
    main()

"""Stage the matched native-history lesson from its immutable offline ZIP."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from frozen_native_bundle import checked_file

ROUTE = "native-history-strategies-d57739b3"
SOURCE = "d57739b300e26810f02240c4029bde68028fdb3d"
SDK = "b1aee9c1caa9ccfb245cc966eb8c1ef79978cdd0"
ARCHIVE_SHA256 = "0bc9536f12303dd4b94a733a655852600b0e8ddc7fb85bb0aa8ab9cea369b43a"
FIGURES = (
    "syn-nl-lv-01-x1-x2",
    "earth-orbit-x1-x2",
    "earth-orbit-x3-x4",
    "syn-nl-fuel-01-x1-x2",
    "syn-nl-fuel-01-x3-x4",
)
PAGE_ASSETS = {
    "index.html",
    "offline-examples.css",
    "path-normalization.json",
    "campaign-summary.json",
    "task/syn-nl-lv-01.json",
    "figures/lotka-polytope.svg",
    *(f"figures/{stem}{detail}.svg" for stem in FIGURES for detail in ("", "-detail")),
}


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    archive_name = ROUTE + ".zip"
    archive_path = checked_file(
        repository_root, f"reports/algorithm-results/{ROUTE}/{archive_name}"
    )
    content = archive_path.read_bytes()
    checksum = checked_file(
        repository_root, f"reports/algorithm-results/{ROUTE}/{archive_name}.sha256"
    ).read_bytes()
    if (
        hashlib.sha256(content).hexdigest() != ARCHIVE_SHA256
        or checksum != f"{ARCHIVE_SHA256}  {archive_name}\n".encode()
    ):
        raise ValueError("Native history lesson archive does not match the frozen checksum")
    assets = {archive_name: content, archive_name + ".sha256": checksum}
    with ZipFile(BytesIO(content)) as archive:
        raw_manifest = archive.read("manifest.json")
        manifest = json.loads(raw_manifest)
        if (
            manifest["schema"] != "csl.native-history-strategy-lesson/1"
            or manifest["source_commit"] != SOURCE
            or manifest["sdk_commit"] != SDK
        ):
            raise ValueError("Native history lesson source binding differs")
        expected = manifest["files_sha256"]
        names = set(archive.namelist())
        if (
            len(names) != len(archive.infolist())
            or names != expected.keys() | {"manifest.json"}
            or not PAGE_ASSETS <= expected.keys()
        ):
            raise ValueError("Native history lesson archive members differ")
        for name, digest in expected.items():
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Native history lesson member checksum differs: {name}")
            if name in PAGE_ASSETS:
                assets[name] = data
        assets["manifest.json"] = raw_manifest
    entry = {
        "family": "Predictive control",
        "title": "Full-history feedback with reachable sets",
        "status": "saved-data-companion",
        "anchor": ROUTE,
        "page": ROUTE + "/index.html",
        "figure": ROUTE + "/figures/lotka-polytope.svg",
        "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{SOURCE}/benchmarks/reporting/closed_loop",
        "raw_record": ROUTE + "/campaign-summary.json",
    }
    card = (
        f'<article class="saved-figure" id="{ROUTE}"><h3><a href="{entry["page"]}">'
        f'{entry["title"]}</a></h3><a href="{entry["page"]}"><img src="{entry["figure"]}" '
        'alt="All Lotka–Volterra stage projections with the executed feedback trajectory"></a>'
        "<p>Inspect the full-history policy on Lotka–Volterra and compare five set "
        "representations on Lotka–Volterra, orbit, and fuel.</p>"
        f'<p><a href="{ROUTE}/{archive_name}">Download the lesson and raw records</a> · '
        f'<a href="{ROUTE}/{archive_name}.sha256">ZIP checksum</a></p></article>'
    )
    return {f"{ROUTE}/{key}": data for key, data in assets.items()}, [entry], card

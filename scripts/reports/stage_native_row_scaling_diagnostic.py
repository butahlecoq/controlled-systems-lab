"""Stage the locked source-only row-scaling diagnostic; never compile or solve."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

ROUTE = "native-row-scaling-diagnostic-v1"
SOURCE = "428bbdcaca4adca6a8d5af2ba3f1d64a80c97f6e"
MANIFEST_SHA256 = "2338fdc18f7402030f7fe0982db9c39c9261867571cbba411b2d6db7e34eab51"
ARCHIVE_SHA256 = "c21f22c40027abfefe51ff2025e1e047c65ee3c3bfd40d03eb9182260b0fdf25"


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    files = read_bundle(
        repository_root,
        FrozenNativeBundle(
            route=ROUTE,
            source_commit=SOURCE,
            schema="csl.native-row-scaling-diagnostic/1",
            manifest_sha256=MANIFEST_SHA256,
            archive_sha256=ARCHIVE_SHA256,
        ),
    )
    outputs = {ROUTE + "/" + name: content for name, content in files.items()}
    entry = {
        "family": "Native mathematical models",
        "title": "Positive row scaling: three retained native QP outcomes",
        "status": "saved-data-companion",
        "anchor": "native-row-scaling-diagnostic",
        "page": ROUTE + "/index.html",
        "figure": ROUTE + "/toy.svg",
        "source_page": ROUTE + "/source/row_scaling_driver.cpp",
        "raw_record": ROUTE + "/records/execution-manifest.json",
    }
    card = (
        '<article class="saved-figure" id="native-row-scaling-diagnostic">'
        '<p class="eyebrow">Native C++ · source-only numerical diagnostic</p>'
        f'<h3><a href="{entry["page"]}">{escape(entry["title"])}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" '
        'alt="Saved native and analytic toy optima at one point five, one point five '
        'on the original equality x plus y equals three"></a>'
        "<p>Model 23 completes a trivial zero-state case. Models 27 and 28 retain numerical "
        "failures; neither is labelled infeasible. The 2D toy shows positive row equivalence.</p>"
        f'<p><a href="{entry["page"]}">Read the report and full failure logs →</a> · '
        f'<a href="{ROUTE}/{ROUTE}.zip">Download source-only evidence</a></p></article>'
    )
    return outputs, [entry], card


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    outputs, _, _ = build(args.repository_root)
    print(f"Verified {len(outputs)} locked source-only diagnostic assets")


if __name__ == "__main__":
    main()

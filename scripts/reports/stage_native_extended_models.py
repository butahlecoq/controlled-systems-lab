"""Publish saved native forward-model examples and their mathematical lessons."""

from __future__ import annotations

from html import escape
from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, checked_file, read_bundle

ROUTE = "native-extended-models-v1"
SOURCE = "e487affa2ad0edb3d6e615fe0a8f4dd6aeabd785"
MANIFEST_SHA256 = "ea1e0661397526d4629f36747d7fa218aea31a140d7b811e0b28a4d00aaea38d"
ARCHIVE_SHA256 = "9b3e65ec5189b930571a1e4e81e02cfbba091843e68f0c9a5ddc44e9b527155c"


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    files = read_bundle(
        repository_root,
        FrozenNativeBundle(
            route=ROUTE,
            source_commit=SOURCE,
            schema="csl.native-extended-models-functional/1",
            manifest_sha256=MANIFEST_SHA256,
            archive_sha256=ARCHIVE_SHA256,
        ),
    )
    outputs = {ROUTE + "/" + name: content for name, content in files.items()}
    entries: list[dict[str, str]] = []
    cards: list[str] = []
    lessons = (
        (
            "native-slide50-reachability",
            "Two-input reachability from a separately authored initial box",
            "slide50/stages-6-x1-x3-screen.svg",
            "Printed three-state dynamics, independent inputs, and all stages of two horizon variants.",
        ),
        (
            "native-spatial-flight",
            "Nine-state deviations about a nonlinear flight reference",
            "spatial-flight/spatial-flight-plane-1-screen.svg",
            "Synthetic coupled physics, a native reference and Jacobians, and full-state propagation before projection.",
        ),
    )
    for anchor, title, image, description in lessons:
        page = anchor + ".html"
        figure = ROUTE + "/" + image
        if figure not in outputs:
            raise ValueError("native extended example figure is missing: " + figure)
        outputs[page] = checked_file(repository_root / "docs/examples", page).read_bytes()
        entries.append(
            {
                "family": "Native mathematical models",
                "title": title,
                "status": "educational-example",
                "anchor": anchor,
                "page": page,
                "figure": figure,
                "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/"
                + SOURCE,
                "raw_record": ROUTE + "/manifest.json",
            }
        )
        cards.append(
            f'<article class="saved-figure" id="{anchor}">'
            '<p class="eyebrow">Native C++ · forward reachability</p>'
            f'<h3><a href="{page}">{escape(title)}</a></h3>'
            f'<a href="{page}"><img src="{figure}" alt="{escape(description)}"></a>'
            f'<p>{escape(description)}</p><p><a href="{page}">Model, all-stage figures and reproduction →</a></p></article>'
        )
    return outputs, entries, "".join(cards)

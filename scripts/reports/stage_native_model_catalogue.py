"""Validate and stage frozen native model examples; no model computation runs here."""

from __future__ import annotations

from html import escape
from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle
from frozen_native_bundle import checked_file as _file
from report_data import require

ROUTE = "native-model-catalogue-v1"
SOURCE = "19d32a3c37b6860dbf881996da1bf5e2b3f92353"
MANIFEST_SHA256 = "4c1c25872414f9ac7c12fa3fdfb9c9cff24b43174f462ac7f72a795889b0e3ad"
ARCHIVE_SHA256 = "f2c3576403cd367a78d4a81fbdca59db970da43094ad456070561c8ce49bbf30"


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    files = read_bundle(
        repository_root,
        FrozenNativeBundle(
            route=ROUTE,
            source_commit=SOURCE,
            schema="csl.native-model-catalogue-functional/1",
            manifest_sha256=MANIFEST_SHA256,
            archive_sha256=ARCHIVE_SHA256,
        ),
    )
    outputs = {ROUTE + "/" + name: content for name, content in files.items()}
    entries, cards = [], []
    lessons = (
        (
            "native-model-catalogue",
            "Three-state native model: seven or eight transitions",
            "three-state/stages-8-x1-x2-screen.svg",
            "Two source-qualified horizon variants, independently checked in all three coordinates.",
            "All stages of the three-state reachable sets projected onto x1 and x2",
        ),
        (
            "native-four-state-reachability",
            "Four-state reachable sets through fifteen transitions",
            "four-state/stages-x1-x2-screen.svg",
            "Full four-state generator propagation with independent support checks and both paired projections.",
            "All sixteen four-state reachable sets projected onto x1 and x2",
        ),
    )
    for anchor, title, image, summary, alt in lessons:
        page = anchor + ".html"
        outputs[page] = _file(repository_root / "docs/examples", page).read_bytes()
        figure = ROUTE + "/" + image
        require(figure in outputs, "native catalogue lesson figure is missing")
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
            f'<a href="{page}"><img src="{figure}" alt="{escape(alt)}"></a>'
            f'<p>{escape(summary)}</p><p><a href="{page}">Matrices, all-stage figures and reproduction →</a></p></article>'
        )
    return outputs, entries, "".join(cards)

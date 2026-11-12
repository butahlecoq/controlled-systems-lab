"""Stage the saved, source-qualified 2D feedback example without rerunning it."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DATA = "feedback-geometry-tiny-fd28"
PAGE = "feedback_geometry_2d.html"
FIGURE = "feedback_geometry_2d.svg"
ANCHOR = "saved-feedback-geometry-2d"


def build(root: Path = ROOT):
    source = root / "examples" / DATA
    page = root / "examples" / PAGE
    if source.is_symlink() or page.is_symlink() or not page.is_file():
        raise ValueError("feedback example source is missing or unsafe")
    manifest = source / "files.sha256"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("feedback example evidence manifest is missing")
    assets = {PAGE: page.read_bytes(), f"{DATA}/files.sha256": manifest.read_bytes()}
    names = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = source / name
        parts = Path(name).parts
        if (name in names or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or not parts or any(part in {".", ".."} for part in parts)
                or not path.resolve().is_relative_to(source.resolve())
                or any((source.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts) + 1))
                or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("feedback example evidence does not match its manifest: " + name)
        names.add(name)
        assets[f"{DATA}/{name}"] = path.read_bytes()
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file() and p != manifest}
    if names != actual:
        raise ValueError("feedback example evidence file set differs from its manifest")
    html = assets[PAGE].decode("utf-8")
    match = re.search(r"<svg\b.*?</svg>", html, re.DOTALL)
    if not match:
        raise ValueError("feedback example has no SVG figure")
    svg = match.group(0).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    svg = svg.replace(">", "><style>.axis{stroke:#d5c4a1;stroke-width:2}.label{font:16px system-ui;fill:#f8f8f2}</style>", 1)
    assets[FIGURE] = svg.encode("utf-8")
    entry = {"family": "Feedback geometry", "title": "Five-family 2D feedback query",
        "status": "saved-data-companion", "anchor": ANCHOR, "page": PAGE,
        "figure": FIGURE,
        "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/fd28cb652bd8a20839b73abaf184881fd7bcf1b4",
        "raw_record": f"{DATA}/independent-audit.json"}
    card = ('<article class="saved-figure" id="' + ANCHOR + '"><p class="eyebrow">Feedback geometry · Saved-data companion</p>'
        '<h3>Five-family 2D feedback query</h3><a href="' + PAGE + '"><img src="' + FIGURE +
        '" alt="Exact reachable square and recorded one-step control"></a>'
        '<p>Follow a saved one-step query through five family memberships, provider calls and independent checks.</p>'
        '<p><a href="' + PAGE + '">Open the feedback example →</a></p></article>')
    return assets, entry, card

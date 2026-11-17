"""Stage the frozen native four-state projection approximation comparison."""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

ROUTE = "four-state-projection-approximations-v1"
SCHEMA = "csl.four-state-projection-approximation-run/1"


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root) / "reports/algorithm-results" / ROUTE
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError("four-state approximation manifest schema differs")
    source = manifest.get("source_commit")
    if not isinstance(source, str) or len(source) != 40:
        raise ValueError("four-state approximation source commit is invalid")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict) or not expected_files:
        raise ValueError("four-state approximation file inventory is missing")

    outputs: dict[str, bytes] = {}
    for name, details in expected_files.items():
        if Path(name).name != name or not isinstance(details, dict):
            raise ValueError("four-state approximation file entry is invalid")
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("four-state approximation asset is missing: " + name)
        content = path.read_bytes()
        if len(content) != details.get("bytes") or hashlib.sha256(
            content
        ).hexdigest() != details.get("sha256"):
            raise ValueError("four-state approximation asset hash differs: " + name)
        outputs[f"{ROUTE}/{name}"] = content

    page = root / "index.html"
    if page.is_symlink() or not page.is_file():
        raise ValueError("four-state approximation report page is missing")
    outputs[f"{ROUTE}/index.html"] = page.read_bytes()
    outputs[f"{ROUTE}/manifest.json"] = manifest_path.read_bytes()
    archive = root / f"{ROUTE}.zip"
    archive_hash = archive.with_suffix(archive.suffix + ".sha256")
    if (
        archive.is_symlink()
        or not archive.is_file()
        or archive_hash.is_symlink()
        or not archive_hash.is_file()
    ):
        raise ValueError("four-state approximation offline bundle is missing")
    archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if archive_hash.read_text(encoding="ascii").split()[0] != archive_digest:
        raise ValueError("four-state approximation offline bundle hash differs")
    outputs[f"{ROUTE}/{archive.name}"] = archive.read_bytes()
    outputs[f"{ROUTE}/{archive_hash.name}"] = archive_hash.read_bytes()
    entry = {
        "family": "Reachable-set approximations",
        "title": "Four-state projection approximations across all stages",
        "status": "saved-data-companion",
        "anchor": ROUTE,
        "page": f"{ROUTE}/index.html",
        "figure": f"{ROUTE}/x1-x2-approximation-stages.svg",
        "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source}/examples/native_four_state_approximation.cpp",
        "raw_record": f"{ROUTE}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{ROUTE}">'
        '<p class="eyebrow">Native C++ · reachable-set approximations</p>'
        f'<h3><a href="{ROUTE}/index.html">{escape(entry["title"])}</a></h3>'
        f'<a href="{ROUTE}/index.html"><img src="{ROUTE}/x1-x2-approximation-stages.svg" '
        'alt="All stages of computed x1-x2 generator-set projections and four admitted outer approximations"></a>'
        "<p>Four registered 2D approximation policies applied to both projections of a source-qualified four-state scalar-input model.</p>"
        f'<p><a href="{ROUTE}/index.html">Open report, data and reproduction details →</a></p></article>'
    )
    return outputs, [entry], card

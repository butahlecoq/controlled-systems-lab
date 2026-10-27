"""Prepared files and gallery card for the layered fuel illustration."""
from __future__ import annotations

from html import escape
from pathlib import Path

from report_data import require


ROUTE = "fuel-reachability-layers"
FIGURE = "fuel-reachability-x1-x2.png"


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    source = Path(repository_root) / "docs/examples" / ROUTE
    require(source.is_dir(), "missing source-bound fuel reachability illustration")
    files = {}
    for path in sorted(source.iterdir()):
        if path.is_file():
            files[f"{ROUTE}/{path.name}"] = path.read_bytes()
    page = f"{ROUTE}/index.html"
    figure = f"{ROUTE}/{FIGURE}"
    raw_record = f"{ROUTE}/plot-data.json"
    require(page in files and figure in files and raw_record in files,
            "fuel reachability illustration is missing its page, figure, or saved geometry")
    anchor = "fuel-reachability-layers"
    card = (
        f'<article class="saved-figure" id="{anchor}">'
        '<p class="eyebrow">Fuel reachability · numerical illustration</p>'
        '<h3>Oxidizer and fuel reachable-set layers</h3>'
        f'<a href="{escape(page, quote=True)}"><img src="{escape(figure, quote=True)}" '
        'alt="Forward and backward reachable sets, full-state intersections, and one selected minimizing path in the oxidizer projection"></a>'
        '<p>Shows R0 through RT, backward sets, full-state intersections, and one minimizing open-loop trajectory. '
        'This deterministic source-based reconstruction is distinct from the B06/L09 minimax report.</p>'
        f'<p><a href="{escape(page, quote=True)}">Open both primary projections and the supplementary views →</a></p>'
        '</article>')
    inventory = [{
        "family": "Fuel reachability layers",
        "title": "Oxidizer and fuel reachable-set layers",
        "status": "saved-data-companion",
        "anchor": anchor,
        "page": page,
        "figure": figure,
        "source_page": page,
        "raw_record": raw_record,
    }]
    return files, inventory, card

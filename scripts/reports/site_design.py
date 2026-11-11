"""Shared HTML framing for mutable learning and report companion pages."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "docs/examples/examples.css"


def stylesheet() -> bytes:
    """Return the one stylesheet staged beside the mutable examples."""
    return STYLE.read_bytes()


def stylesheet_link(href: str = "examples.css") -> str:
    return '<link rel="stylesheet" href="' + escape(href, quote=True) + '">'


def breadcrumbs(items: Iterable[tuple[str, str]], *, current_href: str | None = None) -> str:
    """Render named route steps; the final item is the current page."""
    links = list(items)
    parts = ['<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>']
    for index, (label, href) in enumerate(links):
        if index == len(links) - 1:
            current = escape(label)
            if current_href is not None:
                current = '<a href="' + escape(current_href, quote=True) + '">' + current + '</a>'
            parts.append('<li aria-current="page">' + current + '</li>')
        else:
            parts.append('<li><a href="' + escape(href, quote=True) + '">' + escape(label) + '</a></li>')
    parts.append('</ol></nav>')
    return ''.join(parts)


def lesson_neighbors(previous: tuple[str, str] | None,
                     following: tuple[str, str] | None) -> str:
    """Render accessible previous/next topic links where a sequence exists."""
    if previous is None and following is None:
        return ''
    parts = ['<nav class="lesson-neighbors" aria-label="Lesson navigation">']
    if previous is None:
        parts.append('<span></span>')
    else:
        label, href = previous
        parts.append('<a rel="prev" href="' + escape(href, quote=True) + '"><span>Previous</span>'
                     '<strong>' + escape(label) + '</strong></a>')
    if following is None:
        parts.append('<span></span>')
    else:
        label, href = following
        parts.append('<a rel="next" href="' + escape(href, quote=True) + '"><span>Next</span>'
                     '<strong>' + escape(label) + '</strong></a>')
    parts.append('</nav>')
    return ''.join(parts)


def page_start(title: str, *, stylesheet_href: str | None = None,
               crumbs: Iterable[tuple[str, str]] = (), main_class: str = "page-content",
               current_href: str | None = None) -> str:
    """Start a responsive standalone page using the shared site appearance."""
    escaped_title = escape(title)
    nav = breadcrumbs(crumbs, current_href=current_href) if crumbs else ''
    stylesheet_tag = (stylesheet_link(stylesheet_href) if stylesheet_href is not None
                      else '<style>\n' + stylesheet().decode("utf-8") + '\n</style>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escaped_title + '</title>'
            + stylesheet_tag + '</head><body><a class="skip" href="#main">Skip to content</a>'
            '<main id="main" class="' + escape(main_class, quote=True) + '">' + nav)


def page_end(neighbors: str = "") -> str:
    return neighbors + '</main></body></html>'
